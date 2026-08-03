from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from opensdl_capabilities import CapabilityRegistry, validate_instance
from opensdl_core import (
    EventRecord,
    ExecutionDeniedError,
    ExecutionRequest,
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
)
from opensdl_policy import PolicyEvaluator
from opensdl_storage import ArtifactStore, RepositoryStore
from opensdl_workflows import resolve_mapping, topological_layers, validate_workflow_graph


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
    ) -> RunRecord:
        effective_context = deepcopy(self.default_run_context)
        if run_context:
            effective_context.update(deepcopy(run_context))
        validate_workflow_graph(workflow)
        if workflow.input_schema:
            validate_instance(inputs, workflow.input_schema, label=f"{workflow.id} inputs")
        existing = self.repositories.get_run(run_id) if run_id else None
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
            self._emit("RunCreated", run=run, payload=created_payload)
        else:
            if existing.workflow_id != workflow.id:
                raise ValueError(f"run {existing.id} belongs to workflow {existing.workflow_id}")
            run = existing
            inputs = run.inputs
            existing_events = self.repositories.list_events(run_id=run.id, limit=None)
            if not any(event.type == "RunCreated" for event in existing_events):
                created_payload = {"workflow": workflow.model_dump(mode="json")}
                if effective_context:
                    created_payload["context"] = effective_context
                self._emit("RunCreated", run=run, payload=created_payload)

        self.repositories.update_run(run.id, state=RunState.RUNNING, error=None)
        self._emit("RunStarted", run=run)

        existing_tasks = {task.step_id: task for task in self.repositories.list_tasks(run.id)}
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
            self._emit("RunCompleted", run=completed, payload={"outputs": outputs})
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
            )
            raise
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            failed = self.repositories.update_run(run.id, state=RunState.FAILED, error=error)
            self._emit(
                "RunFailed",
                run=failed,
                payload={"error": error, "errorType": type(exc).__name__},
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
            )
            if not decision.allowed:
                task.state = TaskState.FAILED
                task.error = decision.reason
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ExecutionDeniedError(
                    f"execution of {step.capability} denied: {decision.reason}"
                )

            resources = sorted(set(definition.required_resources + step.resources))
            missing_resources = self.repositories.missing_resources(resources)
            if missing_resources:
                raise ResourceBusyError(
                    f"required resources are not registered: {missing_resources}"
                )
            task.state = TaskState.WAITING_FOR_RESOURCES
            task.updated_at = utc_now()
            self.repositories.upsert_task(task)
            if not self.repositories.acquire_leases(resources, task.id, self.lease_ttl_seconds):
                task.state = TaskState.FAILED
                task.error = f"resources busy: {resources}"
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ResourceBusyError(task.error)

            adapter = self.registry.get_adapter(step.capability)
            max_retries = step.retries if step.retries is not None else definition.max_retries
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
                    )
                    try:
                        result = await asyncio.wait_for(adapter.execute(request), timeout=timeout)
                        validate_instance(
                            result.output,
                            definition.output_schema,
                            label=f"{step.capability} output",
                        )
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
                                "adapter": adapter.name,
                            },
                        )
                        return result.output
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
                            )
                            if timed_out:
                                raise WorkflowExecutionError(error) from exc
                            raise
                        task.state = TaskState.RETRYING
                        self.repositories.upsert_task(task)
                        await asyncio.sleep(min(0.05 * (2**attempt), 1.0))
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
