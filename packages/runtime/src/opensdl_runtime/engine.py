from __future__ import annotations

import asyncio
import random
import time
from copy import deepcopy
from typing import Any

from opensdl_capabilities import CapabilityRegistry, NotDispatchedError, validate_instance
from opensdl_core import (
    STARTABLE_RUN_STATES,
    CapabilityDefinition,
    CapabilityNotFoundError,
    EventRecord,
    ExecutionDeniedError,
    ExecutionRequest,
    LifecycleError,
    ResourceBusyError,
    RetrySafety,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
    ValidationError,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowStep,
    canonical_digest,
    utc_now,
    validate_run_transition,
)
from opensdl_policy import PolicyEvaluator
from opensdl_storage import ArtifactStore, RepositoryStore
from opensdl_workflows import resolve_mapping, topological_layers, validate_workflow_graph

#: How long a task waits before asking again for equipment somebody else holds, and the ceiling
#: that backoff climbs to. Short enough that a freed instrument is picked up promptly, long enough
#: that a queue of tasks is not a busy loop against the store.
_LEASE_POLL_SECONDS = 0.05
_LEASE_POLL_CEILING = 2.0

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


def may_repeat_without_outcome(definition: CapabilityDefinition) -> bool:
    """Whether this capability may be dispatched again when nothing reported an outcome at all.

    The question below, asked where there is no failure to inspect: an abandoned wait, a
    controller that died holding the task. Only `REPEATABLE` answers it, because
    `REPEATABLE_IF_NOT_DISPATCHED` is a claim about evidence the adapter supplies and silence is
    not that evidence.
    """
    return definition.retry_safety is RetrySafety.REPEATABLE


def may_repeat_after(definition: CapabilityDefinition, failure: BaseException) -> bool:
    """Whether this failure permits dispatching this capability again.

    One question, asked in one place, from one declaration. The runtime cannot answer it from
    what it observed: an adapter error is no more proof that nothing happened than an adapter
    success is proof that something did. So `retry_safety` answers it, and the only failure that
    can add anything is one the adapter raised to say the command never left the client.
    """
    if may_repeat_without_outcome(definition):
        return True
    if definition.retry_safety is RetrySafety.REPEATABLE_IF_NOT_DISPATCHED:
        return isinstance(failure, NotDispatchedError)
    return False


#: Retry backoff, doubling from this and capped below.
RETRY_BACKOFF_SECONDS = 0.05
RETRY_BACKOFF_CAP_SECONDS = 1.0


def _retry_backoff_seconds(attempt: int) -> float:
    """How long the runtime waits before the attempt after this one.

    One definition, used both to wait and to size the resource lease that has to cover the
    waiting. Two copies of it would let the lease silently stop covering the retry loop the
    moment either changed.
    """

    return min(RETRY_BACKOFF_SECONDS * (2**attempt), RETRY_BACKOFF_CAP_SECONDS)


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
        lease_wait_seconds: float = 120.0,
        default_run_context: dict[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.repositories = repositories
        self.policy = policy
        self.artifact_store = artifact_store
        self.max_concurrency = max_concurrency
        self.default_timeout_seconds = default_timeout_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.lease_wait_seconds = lease_wait_seconds
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
        supersedes: str | None = None,
    ) -> RunRecord:
        """Execute a workflow, or continue the run that already recorded this exact workflow.

        ``run_id`` naming an existing run is a *resume*, not a resubmission. The run's
        ``RunCreated`` carries the workflow it was asked to execute and a digest of that captured
        document, and a resume that does not present the same document is refused: a run whose
        record says one thing while its tasks did another is not evidence of anything.

        ``supersedes`` is the path that refusal leaves open. Fixing a broken step and continuing is
        a real thing an operator wants, and it is a new execution rather than a correction to an
        old one, so it mints a new run that names the run it replaces — recorded on both, so the
        old run says what became of it and the new one says what it grew out of.
        """

        effective_context = deepcopy(self.default_run_context)
        if run_context:
            effective_context.update(deepcopy(run_context))
        validate_workflow_graph(workflow)
        if workflow.input_schema:
            validate_instance(inputs, workflow.input_schema, label=f"{workflow.id} inputs")
        document = workflow.model_dump(mode="json")
        digest = canonical_digest(document)
        existing = self.repositories.get_run(run_id) if run_id else None
        superseded = self._resolve_superseded(supersedes, existing)
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
            created_payload: dict[str, Any] = {"workflow": document, "workflowDigest": digest}
            if effective_context:
                created_payload["context"] = effective_context
            if superseded is not None:
                created_payload["supersedes"] = superseded.id
            self._emit("RunCreated", run=run, payload=created_payload, campaign_id=campaign_id)
            if superseded is not None:
                self._emit_superseded(superseded, run, digest=digest, operator_id=operator_id)
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
            created = next((event for event in existing_events if event.type == "RunCreated"), None)
            if created is None:
                # No workflow of record to match against: this run was written straight to the
                # store rather than submitted, so the definition is being captured now. The
                # workflow-id check above is the only claim the record can support.
                created_payload = {"workflow": document, "workflowDigest": digest}
                if effective_context:
                    created_payload["context"] = effective_context
                self._emit("RunCreated", run=run, payload=created_payload, campaign_id=campaign_id)
            else:
                self._assert_workflow_of_record(run, created, digest)

        started = self.repositories.start_run(run.id)
        if started is None:
            raise self._cannot_start(run)
        run = started
        self._emit(
            "RunStarted",
            run=run,
            payload={"operatorId": operator_id},
            campaign_id=campaign_id,
        )

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
            # The run's recorded state is read off its tasks rather than off the exception. A
            # task the runtime left ambiguous is the record of what is not known, and a run that
            # reported a clean failure over one would be resumable while its own task is not.
            ambiguous = [
                task
                for task in self.repositories.list_tasks(run.id)
                if task.state == TaskState.INTERVENTION_REQUIRED
            ]
            if ambiguous:
                interrupted = self.repositories.update_run(
                    run.id,
                    state=RunState.INTERVENTION_REQUIRED,
                    error=error,
                )
                self._emit(
                    "RunInterventionRequired",
                    run=interrupted,
                    payload={
                        "error": error,
                        "reason": "task_outcome_unknown",
                        "tasks": [task.id for task in ambiguous],
                    },
                    campaign_id=campaign_id,
                )
            else:
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

    def _resolve_superseded(
        self, supersedes: str | None, existing: RunRecord | None
    ) -> RunRecord | None:
        """The run a new run declares it replaces, checked before anything is written."""

        if supersedes is None:
            return None
        if existing is not None:
            raise ValueError(
                f"run {existing.id} already exists, so this submission is a resume rather than a "
                f"replacement, and a run cannot supersede {supersedes}. Submit the repaired "
                "workflow without a run_id: superseding mints a new run precisely so the record "
                "of the old one is left as it was found."
            )
        replaced = self.repositories.get_run(supersedes)
        if replaced is None:
            raise LookupError(
                f"cannot supersede run {supersedes}: no run is recorded under that identifier. "
                "A replacement names the run it grew out of, so the identifier has to be one this "
                "laboratory recorded."
            )
        return replaced

    async def _hold_resources(
        self,
        resources: list[str],
        *,
        task: TaskRecord,
        run: RunRecord,
        seconds: float,
        campaign_id: str | None,
    ) -> bool:
        """Take every resource this task needs, waiting for whoever holds them.

        A laboratory queues for equipment. Failing the moment another task holds the balance is
        what made `max_parallel_runs` above one produce one success and a row of busy failures:
        the candidates were dispatched together, and the ones that lost the race were already runs
        by the time they lost it.

        Waiting is safe here for a reason worth stating, because it would not be safe in general.
        A task holds its resources only for its own duration and releases them in a `finally`, so
        no task ever holds one resource while waiting for another. Without that, this loop would
        be a deadlock. `acquire_leases` is also all-or-nothing and claims in sorted order, so two
        tasks wanting overlapping sets contend over the same resource first and neither walks away
        holding half of what the other needs.

        The wait is bounded. When it runs out the caller fails exactly as it did before, because a
        task that queues forever is worse than one that says the bench is busy.
        """
        first = self.repositories.acquire_leases(resources, task.id, seconds)
        if first or self.lease_wait_seconds <= 0:
            return first

        # Say that the task is waiting rather than let a gap in the timestamps imply it.
        self._emit(
            "TaskWaitingForResources",
            run=run,
            task=task,
            payload={"resources": sorted(resources), "waitSeconds": self.lease_wait_seconds},
            campaign_id=campaign_id,
        )
        deadline = time.monotonic() + self.lease_wait_seconds
        delay = _LEASE_POLL_SECONDS
        while time.monotonic() < deadline:
            # Jittered so that several tasks released together do not retry in lockstep and hand
            # the resource to the same one every round.
            await asyncio.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            if self.repositories.acquire_leases(resources, task.id, seconds):
                self._emit(
                    "TaskResourcesAcquired",
                    run=run,
                    task=task,
                    payload={"resources": sorted(resources)},
                    campaign_id=campaign_id,
                )
                return True
            delay = min(delay * 2, _LEASE_POLL_CEILING) * (0.5 + random.random())
        return False

    def _lease_seconds_for(self, timeout: float, max_retries: int) -> float:
        """How long this task's resource lease has to last.

        A lease shorter than the work it protects becomes reclaimable while that work is still
        running, and the instrument then has two holders — the failure the lease exists to
        prevent, reached with no race at all and no concurrency beyond one other task starting.
        The configured TTL is a floor rather than a ceiling: the lease covers every attempt the
        retry loop may make and the backoff between them.

        What this bounds is how long the *runtime* may hold the task, which is the only quantity
        it knows. An instrument still moving after the runtime stopped waiting is a different
        problem; the timeout path records it and this does not solve it.
        """

        backoff = sum(_retry_backoff_seconds(attempt) for attempt in range(max_retries))
        return max(self.lease_ttl_seconds, (max_retries + 1) * timeout + backoff)

    def _emit_superseded(
        self,
        superseded: RunRecord,
        replacement: RunRecord,
        *,
        digest: str,
        operator_id: str,
    ) -> None:
        """Record on the replaced run that it was replaced, and by whom.

        The new run's `RunCreated` already names the old one. This is the other direction, so an
        operator reading the run that failed finds what became of it without scanning the log. It
        appends to the old run's stream and changes nothing else about it: its state, outputs,
        tasks and operator are the record of what was submitted then, and this is a later claim by
        a later submitter, which is why `actor_id` is that submitter rather than the run's owner.
        """

        self.repositories.append_event(
            EventRecord(
                type="RunSuperseded",
                actor_id=operator_id,
                run_id=superseded.id,
                correlation_id=superseded.id,
                payload={
                    "runId": replacement.id,
                    "workflowDigest": digest,
                    "operatorId": operator_id,
                },
            )
        )

    def _assert_workflow_of_record(self, run: RunRecord, created: EventRecord, digest: str) -> None:
        """Refuse a resume that presents a workflow the run was never asked to execute.

        The digest is read from `RunCreated` when the event carries one and recomputed from the
        workflow document that same event embedded when it does not, so a run recorded before
        `workflowDigest` existed still has a workflow of record and is neither refused nor
        silently exempted.
        """

        recorded = created.payload.get("workflowDigest")
        if not isinstance(recorded, str):
            document = created.payload.get("workflow")
            if document is None:  # pragma: no cover - RunCreated has always carried the workflow
                return
            recorded = canonical_digest(document)
        if recorded == digest:
            return
        raise LifecycleError(
            f"run {run.id} was created to execute the workflow with canonical digest {recorded}, "
            f"and this submission presents {digest}. Running it under this identifier would leave "
            f"the run's own RunCreated describing work it did not do, attributed to "
            f"{run.operator_id}, which is not a record anything can be concluded from. Resume with "
            "the workflow the run recorded, or submit the repaired workflow as a new run with "
            f"supersedes={run.id!r} so the replacement names what it grew out of."
        )

    def _cannot_start(self, run: RunRecord) -> LifecycleError:
        """Say why the store refused to claim this run, from the state it is actually in."""

        current = self.repositories.get_run(run.id)
        if current is None:  # pragma: no cover - the run existed a moment ago
            return LifecycleError(f"run {run.id} no longer exists and cannot be started")
        return LifecycleError(
            f"run {run.id} is recorded as '{current.state.value}' and could not be claimed for "
            f"execution; a run may only start from {sorted(state.value for state in STARTABLE_RUN_STATES)}. "
            "Either another caller is already executing it, or a controller stopped while it was "
            "active and nothing has reconciled it since — `opensdl doctor --reconcile` reconciles "
            "such a run against what the tasks it left in flight declare: 'failed', which this "
            "run can then be resumed from, when every one of them declares repeating safe, and "
            "'intervention_required' otherwise, so a person can establish what the equipment did."
        )

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
            max_retries = step.retries if step.retries is not None else definition.max_retries
            # What this timeout bounds is how long the runtime waits, and nothing else. Adapter
            # code runs on its own thread and loop so that the bound holds even for a blocking
            # call inside an `async def` and so that one adapter cannot stall the rest of the
            # laboratory; see `opensdl_capabilities.execution`. Abandoning the wait does not stop
            # the instrument, which is why a timed-out task's physical outcome is not established
            # by this code. What the record is allowed to claim about it comes from
            # `definition.retry_safety` below, and so does whether a failed dispatch is repeated.
            timeout = (
                step.timeout_seconds or definition.timeout_seconds or self.default_timeout_seconds
            )
            if not await self._hold_resources(
                resources,
                task=task,
                run=run,
                seconds=self._lease_seconds_for(timeout, max_retries),
                campaign_id=campaign_id,
            ):
                task.state = TaskState.FAILED
                task.error = f"resources busy: {resources}"
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                raise ResourceBusyError(task.error)
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
                        # A timeout is the runtime giving up on the answer, not the adapter
                        # supplying one. Nothing stopped, nothing reported, and the abandoned
                        # call keeps running on its own thread. For a capability that has not
                        # declared repeating it safe, recording a clean failure would both
                        # overstate what is known and leave the task resumable, so the next
                        # resume would dispatch the action a second time.
                        if timed_out and not may_repeat_without_outcome(definition):
                            unknown = (
                                f"{error}. The runtime stopped waiting; it did not stop the "
                                "equipment, and nothing reported an outcome, so the physical "
                                f"outcome is unknown. {step.capability} declares retry_safety "
                                f"'{definition.retry_safety.value}', so this is recorded as "
                                "requiring intervention rather than as a failure: a failed task "
                                "is resumable and resuming would dispatch the action again. A "
                                "person must establish what the equipment did before this run "
                                "continues."
                            )
                            task.state = TaskState.INTERVENTION_REQUIRED
                            task.error = unknown
                            task.updated_at = utc_now()
                            self.repositories.upsert_task(task)
                            self._emit(
                                "TaskInterventionRequired",
                                run=run,
                                task=task,
                                payload={
                                    "attempt": task.attempt,
                                    "error": unknown,
                                    "reason": "execution_timed_out",
                                },
                                campaign_id=campaign_id,
                            )
                            raise WorkflowExecutionError(unknown) from exc

                        # A budget was available and the declaration withheld it. Saying so is
                        # the difference between a capability that ran out of attempts and one
                        # that was never allowed to spend them.
                        remaining = max_retries - attempt
                        if remaining > 0 and not may_repeat_after(definition, exc):
                            because = (
                                "this failure does not establish that the command never reached "
                                "the equipment, which is the only evidence that would permit it"
                                if definition.retry_safety
                                is RetrySafety.REPEATABLE_IF_NOT_DISPATCHED
                                else "repeating this operation is never safe"
                            )
                            refused = (
                                f"execution of {step.capability} failed on attempt "
                                f"{task.attempt}: {error}. {step.capability} declares "
                                f"retry_safety '{definition.retry_safety.value}' and {because}, "
                                f"so the runtime does not dispatch it again: the {remaining} "
                                f"further attempt{'' if remaining == 1 else 's'} it was given "
                                "would risk performing the physical action twice. Establish "
                                "what the equipment did, then fix the fault or the capability "
                                "contract before running this step again."
                            )
                            task.state = TaskState.FAILED
                            task.error = refused
                            task.updated_at = utc_now()
                            self.repositories.upsert_task(task)
                            self._emit(
                                "TaskFailed",
                                run=run,
                                task=task,
                                payload={
                                    "attempt": task.attempt,
                                    "error": refused,
                                    "reason": "retry_refused",
                                },
                                campaign_id=campaign_id,
                            )
                            raise WorkflowExecutionError(refused) from exc

                        task.error = error
                        task.updated_at = utc_now()
                        if remaining <= 0:
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
                        await asyncio.sleep(_retry_backoff_seconds(attempt))
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
        """Reconcile the runs a stopped controller left active, from what each task may claim.

        A restart poses the question `may_repeat_without_outcome` answers, and the same one the
        timeout path answers: the runtime dispatched the task and never learned what became of it.
        This path used to answer it for itself, driving every active task to
        `INTERVENTION_REQUIRED` — which is unresumable by design, and which no operation clears —
        so a restart permanently ended a run even for a capability that had declared repeating it
        harmless. Both paths now read the same declaration.
        """

        recovered: list[RunRecord] = []
        for run in self.repositories.list_runs(states=[RunState.RUNNING, RunState.ABORTING]):
            tasks = self.repositories.list_tasks(run.id)
            reconciled: list[tuple[TaskRecord, TaskState, str]] = []
            for task in tasks:
                if task.state not in {TaskState.RUNNING, TaskState.RETRYING}:
                    continue
                previous_state = task.state
                if self._interrupted_task_may_repeat(task.capability_id):
                    # The interruption is a fact and is recorded as one. What the old message
                    # added to it — that the physical outcome is unknown in the sense that stops
                    # the run — is the claim this declaration withdraws.
                    task.state = TaskState.FAILED
                    task.error = (
                        "controller restarted while task was active, so nothing reported an "
                        f"outcome. {task.capability_id} declares retry_safety "
                        f"'{RetrySafety.REPEATABLE.value}', so repeating it under that "
                        "uncertainty cannot harm anything: the attempt is recorded as a failure, "
                        "which a resume dispatches again, rather than as requiring intervention, "
                        "which nothing clears."
                    )
                    event_type = "TaskFailed"
                else:
                    task.state = TaskState.INTERVENTION_REQUIRED
                    task.error = (
                        "controller restarted while task was active; physical outcome is unknown"
                    )
                    event_type = "TaskRecoveryRequired"
                task.updated_at = utc_now()
                self.repositories.upsert_task(task)
                self.repositories.release_leases(task.id)
                reconciled.append((task, previous_state, event_type))

            # The run's recorded state is read off its tasks, as it is on the failure path in
            # `run_workflow`: a run reporting a clean failure over a task whose outcome is unknown
            # would be resumable while its own task is not. A run with nothing in flight is left
            # as it was handled before — no declaration was consulted, so nothing new is known
            # about where the controller died, and the conservative answer stands. So is a run
            # that was aborting: `retry_safety` says whether a task may be dispatched again, not
            # whether an operator's abort took effect, and `RUN_TRANSITIONS` records that an
            # interrupted abort needs a human rather than an automatic conclusion.
            unknown = any(task.state is TaskState.INTERVENTION_REQUIRED for task in tasks)
            if reconciled and not unknown and run.state is RunState.RUNNING:
                run_error = (
                    "controller restarted while run was active. Every task it left in flight "
                    "declares repeating safe, so this is recorded as a failure the run resumes "
                    "from rather than as requiring intervention."
                )
                run_state = RunState.FAILED
                run_event = "RunFailed"
            else:
                run_error = "controller restarted while run was active"
                run_state = RunState.INTERVENTION_REQUIRED
                run_event = "RunRecoveryRequired"
            updated = self.repositories.update_run(run.id, state=run_state, error=run_error)

            for task, previous_state, event_type in reconciled:
                self._emit(
                    event_type,
                    run=updated,
                    task=task,
                    payload={
                        "previousState": previous_state.value,
                        "error": task.error,
                        "reason": "controller_restarted",
                    },
                )
            self._emit(
                run_event,
                run=updated,
                payload={"error": run_error, "reason": "controller_restarted"},
            )
            recovered.append(updated)
        return recovered

    def _interrupted_task_may_repeat(self, capability_id: str) -> bool:
        """Whether a task this controller left in flight may be dispatched again.

        A capability this laboratory no longer exposes has no declaration to read, and an absent
        declaration is not permission: an undeclared capability already means `NOT_REPEATABLE`.
        """

        try:
            definition = self.registry.get_definition(capability_id)
        except CapabilityNotFoundError:
            return False
        return may_repeat_without_outcome(definition)

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
