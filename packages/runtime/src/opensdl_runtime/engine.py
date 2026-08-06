from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from opensdl_capabilities import CapabilityRegistry, validate_instance
from opensdl_core import (
    EventRecord,
    ExecutionDeniedError,
    ExecutionRequest,
    LifecycleError,
    ResourceBusyError,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
    ValidationError,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowStep,
    utc_now,
    validate_run_transition,
)
from opensdl_policy import PolicyEvaluator
from opensdl_storage import ArtifactStore, RepositoryStore
from opensdl_workflows import resolve_mapping, topological_layers, validate_workflow_graph

#: Task states a resumed run must never dispatch again. Either the task is active or was active
#: (`RUNNING`, `RETRYING`), or the record already says the physical outcome is unknown
#: (`INTERVENTION_REQUIRED`, `CANCELLED`). Re-dispatching any of them can repeat a physical action.
UNRESUMABLE_TASK_STATES = frozenset(
    {
        TaskState.RUNNING,
        TaskState.RETRYING,
        TaskState.INTERVENTION_REQUIRED,
        TaskState.CANCELLED,
    }
)


class ReferenceRuntime:
    """Small, durable workflow runtime used by local deployments and conformance tests."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        repositories: RepositoryStore,
        policy: PolicyEvaluator,
        artifact_store: ArtifactStore,
        *,
        max_concurrency: int = 4,
        default_timeout_seconds: float = 60.0,
        lease_ttl_seconds: float = 300.0,
        default_run_context: dict[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.repositories = repositories
        self.policy = policy
        self.artifact_store = artifact_store
        self.max_concurrency = max_concurrency
        self.default_timeout_seconds = default_timeout_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.default_run_context = deepcopy(default_run_context or {})
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def run_workflow(
        self,
        workflow: WorkflowDefinition,
        inputs: dict[str, Any],
        *,
        operator_id: str = "operator/local",
        environment: str = "simulation",
        run_id: str | None = None,
        run_context: dict[str, Any] | None = None,
        campaign_id: str | None = None,
    ) -> RunRecord:
        effective_context = deepcopy(self.default_run_context)
        if run_context:
            effective_context.update(deepcopy(run_context))
        validate_workflow_graph(workflow)
        if workflow.input_schema:
            validate_instance(inputs, workflow.input_schema, label=f"{workflow.id} inputs")
        existing = self.repositories.get_run(run_id) if run_id else None
        existing_tasks: dict[str, TaskRecord] = {}
        if existing is None:
            run = RunRecord(
                id=run_id or RunRecord(workflow_id=workflow.id).id,
                workflow_id=workflow.id,
                workflow_version=workflow.version,
                state=RunState.PLANNED,
                inputs=inputs,
                operator_id=operator_id,
                environment=environment,
            )
            self.repositories.create_run(run)
            created_payload: dict[str, Any] = {"workflow": workflow.model_dump(mode="json")}
            if effective_context:
                created_payload["context"] = effective_context
            self._emit("RunCreated", run=run, payload=created_payload, campaign_id=campaign_id)
        else:
            if existing.workflow_id != workflow.id:
                raise ValueError(f"run {existing.id} belongs to workflow {existing.workflow_id}")
            self._assert_run_can_resume(existing)
            existing_tasks = {
                task.step_id: task for task in self.repositories.list_tasks(existing.id)
            }
            self._assert_tasks_can_resume(existing, list(existing_tasks.values()))
            run = existing
            inputs = run.inputs
            existing_events = self.repositories.list_events(run_id=run.id, limit=None)
            if not any(event.type == "RunCreated" for event in existing_events):
                created_payload = {"workflow": workflow.model_dump(mode="json")}
                if effective_context:
                    created_payload["context"] = effective_context
                self._emit("RunCreated", run=run, payload=created_payload, campaign_id=campaign_id)

        self.repositories.update_run(run.id, state=RunState.RUNNING, error=None)
        self._emit("RunStarted", run=run, campaign_id=campaign_id)

        step_outputs = {
            step_id: task.outputs
            for step_id, task in existing_tasks.items()
            if task.state == TaskState.SUCCEEDED
        }

        try:
            for layer in topological_layers(workflow):
                pending = [step for step in layer if step.id not in step_outputs]
                if not pending:
                    continue
                results = await asyncio.gather(
                    *[
                        self._execute_step(
                            run=run,
                            step=step,
                            workflow_inputs=inputs,
                            step_outputs=step_outputs,
                            operator_id=operator_id,
                            environment=environment,
                            campaign_id=campaign_id,
                            existing_task=existing_tasks.get(step.id),
                        )
                        for step in pending
                    ],
                    return_exceptions=True,
                )
                first_error: BaseException | None = None
                for step, result in zip(pending, results, strict=True):
                    if isinstance(result, BaseException):
                        first_error = first_error or result
                    else:
                        step_outputs[step.id] = result
                if first_error is not None:
                    raise first_error

            outputs = resolve_mapping(workflow.outputs, inputs, step_outputs)
            completed = self.repositories.update_run(
                run.id, state=RunState.COMPLETED, outputs=outputs
            )
            self._emit(
                "RunCompleted",
                run=completed,
                payload={"outputs": outputs},
                campaign_id=campaign_id,
            )
            self.artifact_store.put_json(
                {
                    "run": completed.model_dump(mode="json"),
                    "tasks": [
                        task.model_dump(mode="json")
                        for task in self.repositories.list_tasks(run.id)
                    ],
                },
                run_id=run.id,
                metadata={"role": "run-record"},
            )
            return completed
        except asyncio.CancelledError:
            run_error = "workflow execution was cancelled while active; physical outcome is unknown"
            interrupted = self.repositories.update_run(
                run.id,
                state=RunState.INTERVENTION_REQUIRED,
                error=run_error,
            )
            self._emit(
                "RunInterventionRequired",
                run=interrupted,
                payload={"error": run_error, "reason": "execution_cancelled"},
                campaign_id=campaign_id,
            )
            raise
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            failed = self.repositories.update_run(run.id, state=RunState.FAILED, error=error)
            self._emit(
                "RunFailed",
                run=failed,
                payload={"error": error, "errorType": type(exc).__name__},
                campaign_id=campaign_id,
            )
            if isinstance(
                exc,
                (
                    ExecutionDeniedError,
                    ResourceBusyError,
                    ValidationError,
                    WorkflowExecutionError,
                ),
            ):
                raise
            raise WorkflowExecutionError(error) from exc

    def _assert_run_can_resume(self, run: RunRecord) -> None:
        """Refuse to reuse a run identifier whose run can no longer legitimately start."""
        try:
            validate_run_transition(run.state, RunState.RUNNING)
        except LifecycleError as exc:
            raise LifecycleError(
                f"run {run.id} is recorded as '{run.state.value}' and cannot start again. "
                f"Its inputs, outputs, tasks, and events are the record of the work submitted by "
                f"{run.operator_id}; running new steps under this run identifier would attribute "
                "them to that operator and overwrite that record. Submit the new work as a new "
                "run instead."
            ) from exc

    def _assert_tasks_can_resume(self, run: RunRecord, tasks: list[TaskRecord]) -> None:
        """Refuse to replay a task whose physical outcome the record does not establish."""
        for task in sorted(tasks, key=lambda item: item.step_id):
            if task.state not in UNRESUMABLE_TASK_STATES:
                continue
            raise WorkflowExecutionError(
                f"cannot resume run {run.id}: task {task.id} for step '{task.step_id}' "
                f"(capability {task.capability_id}) is recorded as '{task.state.value}', so "
                "OpenSDL does not know whether the physical action already happened and will not "
                f"dispatch it again. Recorded task error: {task.error or 'none recorded'}. "
                "A human must inspect the equipment and establish what actually happened. "
                "OpenSDL has no operation for acknowledging an intervention yet, so record the "
                "finding outside the run and submit the remaining work as a new run."
            )

    async def execute_capability(
        self,
        capability_id: str,
        inputs: dict[str, Any],
        *,
        operator_id: str = "operator/local",
        environment: str = "simulation",
    ) -> RunRecord:
        workflow = WorkflowDefinition(
            id=f"direct.{capability_id}",
            name=f"Direct execution of {capability_id}",
            steps=[WorkflowStep(id="execute", capability=capability_id, inputs=inputs)],
            outputs={"result": "${steps.execute.output}"},
        )
        return await self.run_workflow(
            workflow, {}, operator_id=operator_id, environment=environment
        )

    async def _execute_step(
        self,
        *,
        run: RunRecord,
        step: WorkflowStep,
        workflow_inputs: dict[str, Any],
        step_outputs: dict[str, dict[str, Any]],
        operator_id: str,
        environment: str,
        campaign_id: str | None,
        existing_task: TaskRecord | None,
    ) -> dict[str, Any]:
        async with self._semaphore:
            definition = self.registry.get_definition(step.capability)
            decision = self.policy.evaluate(definition, operator_id, environment)
            task = existing_task or TaskRecord(
                run_id=run.id,
                step_id=step.id,
                capability_id=step.capability,
            )
            resolved_inputs = resolve_mapping(step.inputs, workflow_inputs, step_outputs)
            validate_instance(
                resolved_inputs,
                definition.input_schema,
                label=f"{step.capability} input",
            )
            task.inputs = resolved_inputs
            task.updated_at = utc_now()
            self.repositories.upsert_task(task)
            self._emit(
                "PolicyEvaluated",
                run=run,
                task=task,
                payload=decision.model_dump(mode="json"),
                campaign_id=campaign_id,
            )
            if not decision.allowed:
                task.state = TaskState.FAILED
                task.error = decision.reason
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ExecutionDeniedError(
                    f"execution of {step.capability} denied: {decision.reason}",
                    decision=decision,
                )

            resources = sorted(set(definition.required_resources + step.resources))
            missing_resources = self.repositories.missing_resources(resources)
            if missing_resources:
                task.state = TaskState.FAILED
                task.error = f"required resources are not registered: {missing_resources}"
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ResourceBusyError(task.error)
            task.state = TaskState.WAITING_FOR_RESOURCES
            task.updated_at = utc_now()
            self.repositories.upsert_task(task)
            if not self.repositories.acquire_leases(resources, task.id, self.lease_ttl_seconds):
                task.state = TaskState.FAILED
                task.error = f"resources busy: {resources}"
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ResourceBusyError(task.error)

            max_retries = step.retries if step.retries is not None else definition.max_retries
            # What this timeout bounds is how long the runtime waits, and nothing else. Adapter
            # code runs on its own thread and loop so that the bound holds even for a blocking
            # call inside an `async def` and so that one adapter cannot stall the rest of the
            # laboratory; see `opensdl_capabilities.execution`. Abandoning the wait does not stop
            # the instrument, which is why a timed-out task's physical outcome is not established
            # by this code and must be established by a person.
            timeout = (
                step.timeout_seconds or definition.timeout_seconds or self.default_timeout_seconds
            )
            request = ExecutionRequest(
                capability_id=step.capability,
                inputs=resolved_inputs,
                operator_id=operator_id,
                environment=environment,
                run_id=run.id,
                task_id=task.id,
            )
            adapter_name = self.registry.get_adapter(step.capability).name
            try:
                for attempt in range(max_retries + 1):
                    task.attempt = attempt + 1
                    task.state = TaskState.RUNNING if attempt == 0 else TaskState.RETRYING
                    task.error = None
                    task.updated_at = utc_now()
                    self.repositories.upsert_task(task)
                    self._emit(
                        "TaskStarted" if attempt == 0 else "TaskRetrying",
                        run=run,
                        task=task,
                        payload={"attempt": task.attempt, "inputs": resolved_inputs},
                        campaign_id=campaign_id,
                    )
                    try:
                        call = self.registry.dispatch(step.capability, request)
                        result = await call.result(timeout)
                    except asyncio.CancelledError:
                        task_error = (
                            f"execution of {step.capability} was cancelled while active; "
                            "physical outcome is unknown"
                        )
                        task.state = TaskState.INTERVENTION_REQUIRED
                        task.error = task_error
                        task.updated_at = utc_now()
                        self.repositories.upsert_task(task)
                        self._emit(
                            "TaskInterventionRequired",
                            run=run,
                            task=task,
                            payload={
                                "attempt": task.attempt,
                                "error": task_error,
                                "reason": "execution_cancelled",
                            },
                            campaign_id=campaign_id,
                        )
                        raise
                    except Exception as exc:
                        timed_out = isinstance(exc, TimeoutError)
                        error = (
                            f"execution of {step.capability} timed out after "
                            f"{timeout:g} seconds on attempt {task.attempt}"
                            if timed_out
                            else str(exc) or type(exc).__name__
                        )
                        task.error = error
                        task.updated_at = utc_now()
                        if attempt >= max_retries:
                            task.state = TaskState.FAILED
                            self.repositories.upsert_task(task)
                            self._emit(
                                "TaskFailed",
                                run=run,
                                task=task,
                                payload={"attempt": task.attempt, "error": error},
                                campaign_id=campaign_id,
                            )
                            if timed_out:
                                raise WorkflowExecutionError(error) from exc
                            raise
                        task.state = TaskState.RETRYING
                        self.repositories.upsert_task(task)
                        await asyncio.sleep(min(0.05 * (2**attempt), 1.0))
                        continue

                    # The adapter reported completion, so the physical action has happened. A
                    # result that violates the declared contract is a contract failure, not a
                    # transient fault: retrying it would repeat the action, so the task fails here.
                    try:
                        validate_instance(
                            result.output,
                            definition.output_schema,
                            label=f"{step.capability} output",
                        )
                    except ValidationError as exc:
                        invalid_output_error = (
                            f"execution of {step.capability} returned a result that violates its "
                            f"declared output schema on attempt {task.attempt}: {exc}. The "
                            "adapter reported that the action completed, so the runtime does not "
                            "retry it: a retry would repeat the physical action. Fix the adapter "
                            "or the capability contract before running this step again."
                        )
                        task.state = TaskState.FAILED
                        task.error = invalid_output_error
                        task.updated_at = utc_now()
                        self.repositories.upsert_task(task)
                        self._emit(
                            "TaskFailed",
                            run=run,
                            task=task,
                            payload={
                                "attempt": task.attempt,
                                "error": invalid_output_error,
                                "reason": "invalid_output",
                            },
                            campaign_id=campaign_id,
                        )
                        raise ValidationError(invalid_output_error) from exc

                    task.state = TaskState.SUCCEEDED
                    task.outputs = result.output
                    task.updated_at = utc_now()
                    self.repositories.upsert_task(task)
                    self._emit(
                        "TaskSucceeded",
                        run=run,
                        task=task,
                        payload={
                            "attempt": task.attempt,
                            "output": result.output,
                            "adapter": adapter_name,
                        },
                        campaign_id=campaign_id,
                    )
                    return result.output
                raise AssertionError("retry loop exited unexpectedly")
            finally:
                self.repositories.release_leases(task.id)

    def recover_incomplete_runs(self) -> list[RunRecord]:
        recovered: list[RunRecord] = []
        for run in self.repositories.list_runs(states=[RunState.RUNNING, RunState.ABORTING]):
            run_error = "controller restarted while run was active"
            updated = self.repositories.update_run(
                run.id,
                state=RunState.INTERVENTION_REQUIRED,
                error=run_error,
            )
            for task in self.repositories.list_tasks(run.id):
                if task.state not in {TaskState.RUNNING, TaskState.RETRYING}:
                    continue
                previous_state = task.state
                task_error = (
                    "controller restarted while task was active; physical outcome is unknown"
                )
                task.state = TaskState.INTERVENTION_REQUIRED
                task.error = task_error
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                self.repositories.release_leases(task.id)
                self._emit(
                    "TaskRecoveryRequired",
                    run=updated,
                    task=task,
                    payload={
                        "previousState": previous_state.value,
                        "error": task_error,
                    },
                )
            self._emit(
                "RunRecoveryRequired",
                run=updated,
                payload={"error": run_error},
            )
            recovered.append(updated)
        return recovered

    def _emit(
        self,
        event_type: str,
        *,
        run: RunRecord,
        task: TaskRecord | None = None,
        payload: dict[str, Any] | None = None,
        campaign_id: str | None = None,
    ) -> EventRecord:
        return self.repositories.append_event(
            EventRecord(
                type=event_type,
                actor_id=run.operator_id,
                run_id=run.id,
                task_id=task.id if task else None,
                campaign_id=campaign_id,
                correlation_id=run.id,
                payload=payload or {},
            )
        )
