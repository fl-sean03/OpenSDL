import asyncio
import threading
import time
from typing import Any, Literal

import pytest

from opensdl_adapter_local_compute import LocalComputeAdapter
from opensdl_capabilities import CapabilityAdapter, CapabilityRegistry
from opensdl_core import (
    CapabilityDefinition,
    ExecutionDeniedError,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    LifecycleError,
    Resource,
    ResourceBusyError,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
    ValidationError,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowStep,
)
from opensdl_policy import PolicyEngine
from opensdl_runtime import ReferenceRuntime
from opensdl_storage import Database, LocalArtifactStore, Repositories


class ProbeAdapter(CapabilityAdapter):
    name = "probe"

    def __init__(
        self,
        *,
        failures: int = 0,
        delay_seconds: float = 0,
        max_retries: int = 0,
        timeout_seconds: float | None = None,
        required_resources: list[str] | None = None,
        output: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.failures = failures
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.required_resources = (
            ["probe-resource"] if required_resources is None else required_resources
        )
        self.output = {"ok": True} if output is None else output
        self.calls = 0
        # A `threading.Event`, not an `asyncio.Event`: adapter code runs on the adapter's own loop
        # in its own thread, so an asyncio primitive shared with the calling loop is a cross-loop
        # write. See `opensdl_capabilities.execution`.
        self.started = threading.Event()

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.probe",
                name="Runtime probe",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
                required_resources=list(self.required_resources),
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
                simulator_available=True,
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        self.started.set()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.calls <= self.failures:
            raise RuntimeError(f"transient failure {self.calls}")
        return ExecutionResult(request_id=request.request_id, output=dict(self.output))


class BlockingAdapter(CapabilityAdapter):
    """An `async def` with no await in it, which is the shape of every blocking vendor SDK.

    The audit measured this exact adapter shape against a declared timeout of 0.1 seconds and
    watched it run for 2.00 seconds without raising, because `asyncio.wait_for` can only interrupt
    a coroutine at an await point and this one never yields.
    """

    name = "blocking"

    def __init__(self, *, seconds: float, timeout_seconds: float | None = None) -> None:
        super().__init__()
        self.seconds = seconds
        self.timeout_seconds = timeout_seconds
        self.calls = 0
        self.entered = threading.Event()
        self.finished = threading.Event()

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.blocking",
                name="Blocking work",
                executor_type=ExecutorType.COMPUTE,
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
                timeout_seconds=self.timeout_seconds,
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        self.entered.set()
        deadline = time.monotonic() + self.seconds
        while time.monotonic() < deadline:  # pure synchronous computation, no await point
            pass
        self.finished.set()
        return ExecutionResult(request_id=request.request_id, output={"ok": True})


class AwaitingAdapter(CapabilityAdapter):
    """A genuinely asynchronous adapter: it yields, so the loop is free while it works."""

    name = "awaiting"

    def __init__(self, *, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="test.awaiting",
                name="Awaiting work",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={"type": "object"},
                output_schema={
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
                timeout_seconds=30.0,
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        await asyncio.sleep(self.seconds)
        return ExecutionResult(request_id=request.request_id, output={"ok": True})


def build_runtime(tmp_path, *, default_run_context=None):
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    registry.register(LocalComputeAdapter())
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
        default_run_context=default_run_context,
    )
    return runtime, repositories


def build_probe_runtime(
    tmp_path,
    adapter: ProbeAdapter,
    *,
    policy_effect: Literal["allow", "deny"] = "allow",
):
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    repositories.upsert_resource(
        Resource(id="probe-resource", name="Probe resource", type="simulator")
    )
    registry = CapabilityRegistry()
    registry.register(adapter)
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect=policy_effect),
        LocalArtifactStore(tmp_path, repositories),
    )
    return runtime, repositories


def probe_workflow(step_id: str = "probe") -> WorkflowDefinition:
    return WorkflowDefinition(
        id="probe-workflow",
        name="Probe workflow",
        steps=[WorkflowStep(id=step_id, capability="test.probe", inputs={})],
        outputs={"result": f"${{steps.{step_id}.output}}"},
    )


@pytest.mark.asyncio
async def test_workflow_executes_and_persists(tmp_path) -> None:
    runtime, repositories = build_runtime(tmp_path)
    workflow = WorkflowDefinition(
        id="distance",
        name="Distance",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "array", "items": {"type": "number"}},
                "b": {"type": "array", "items": {"type": "number"}},
            },
        },
        steps=[
            WorkflowStep(
                id="score",
                capability="compute.euclidean_distance",
                inputs={"a": "${inputs.a}", "b": "${inputs.b}"},
            )
        ],
        outputs={"score": "${steps.score.output.distance}"},
    )
    run = await runtime.run_workflow(workflow, {"a": [0, 0], "b": [3, 4]})
    assert run.outputs["score"] == 5
    assert repositories.list_tasks(run.id)[0].outputs["distance"] == 5
    assert repositories.list_events(run_id=run.id)[-1].type == "RunCompleted"


@pytest.mark.asyncio
async def test_runtime_rejects_invalid_capability_inputs(tmp_path) -> None:
    runtime, _ = build_runtime(tmp_path)
    with pytest.raises(ValidationError, match="compute.quadratic input"):
        await runtime.execute_capability(
            "compute.quadratic",
            {"x": "not-a-number", "a": 1, "b": 0, "c": 0},
        )


@pytest.mark.asyncio
async def test_direct_capability_execution_returns_complete_output(tmp_path) -> None:
    runtime, _ = build_runtime(tmp_path)
    run = await runtime.execute_capability(
        "compute.quadratic",
        {"x": 2, "a": 1, "b": 0, "c": -1},
    )
    assert run.outputs["result"] == {"value": 3.0}


@pytest.mark.asyncio
async def test_default_run_context_is_copied_into_run_created_event(tmp_path) -> None:
    binding = {
        "definitionRevision": "reference-1",
        "definitionSha256": "a" * 64,
        "sceneSha256": "b" * 64,
    }
    context = {"twinBinding": binding}
    runtime, repositories = build_runtime(
        tmp_path,
        default_run_context=context,
    )
    binding["definitionRevision"] = "mutated-after-construction"

    run = await runtime.execute_capability(
        "compute.quadratic",
        {"x": 2, "a": 1, "b": 0, "c": -1},
    )

    created = next(
        event
        for event in repositories.list_events(run_id=run.id, limit=None)
        if event.type == "RunCreated"
    )
    assert created.payload["context"]["twinBinding"]["definitionRevision"] == ("reference-1")


@pytest.mark.asyncio
async def test_cancelled_execution_is_not_retried_and_requires_intervention(
    tmp_path,
) -> None:
    adapter = ProbeAdapter(delay_seconds=30, max_retries=1)
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    execution = asyncio.create_task(runtime.execute_capability("test.probe", {}))
    assert await asyncio.to_thread(adapter.started.wait, 5)

    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution

    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert adapter.calls == 1
    assert run.state == RunState.INTERVENTION_REQUIRED
    assert task.state == TaskState.INTERVENTION_REQUIRED
    assert "physical outcome is unknown" in (run.error or "")
    assert "physical outcome is unknown" in (task.error or "")
    assert task.attempt == 1
    events = repositories.list_events(run_id=run.id, limit=None)
    task_event = next(event for event in events if event.type == "TaskInterventionRequired")
    run_event = next(event for event in events if event.type == "RunInterventionRequired")
    assert task_event.payload["error"] == task.error
    assert run_event.payload["error"] == run.error
    assert [event.type for event in events].count("TaskInterventionRequired") == 1
    assert [event.type for event in events].count("RunInterventionRequired") == 1
    assert not any(event.type in {"TaskRetrying", "TaskFailed", "RunFailed"} for event in events)
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-cancellation", 60)


@pytest.mark.asyncio
async def test_timeout_records_diagnostic_and_releases_lease(tmp_path) -> None:
    adapter = ProbeAdapter(delay_seconds=30, timeout_seconds=0.01)
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    expected = "execution of test.probe timed out after 0.01 seconds on attempt 1"

    with pytest.raises(WorkflowExecutionError) as raised:
        await runtime.execute_capability("test.probe", {})

    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert str(raised.value) == expected
    assert adapter.calls == 1
    assert run.state == RunState.FAILED
    assert run.error == expected
    assert task.state == TaskState.FAILED
    assert task.error == expected
    assert task.attempt == 1
    events = repositories.list_events(run_id=run.id, limit=None)
    task_failed = next(event for event in events if event.type == "TaskFailed")
    run_failed = next(event for event in events if event.type == "RunFailed")
    assert task_failed.payload["error"] == expected
    assert run_failed.payload["error"] == expected
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-timeout", 60)


@pytest.mark.asyncio
async def test_retry_then_success_records_attempts_events_and_releases_lease(
    tmp_path,
) -> None:
    adapter = ProbeAdapter(failures=1, max_retries=1)
    runtime, repositories = build_probe_runtime(tmp_path, adapter)

    run = await runtime.execute_capability("test.probe", {})

    task = repositories.list_tasks(run.id)[0]
    assert adapter.calls == 2
    assert run.state == RunState.COMPLETED
    assert task.state == TaskState.SUCCEEDED
    assert task.attempt == 2
    assert task.error is None
    task_events = [
        event
        for event in repositories.list_events(run_id=run.id, limit=None)
        if event.type in {"TaskStarted", "TaskRetrying", "TaskSucceeded"}
    ]
    assert [event.type for event in task_events] == [
        "TaskStarted",
        "TaskRetrying",
        "TaskSucceeded",
    ]
    assert [event.payload["attempt"] for event in task_events] == [1, 2, 2]
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-retry", 60)


@pytest.mark.asyncio
async def test_policy_denial_prevents_adapter_execution_and_records_decision(
    tmp_path,
) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_probe_runtime(
        tmp_path,
        adapter,
        policy_effect="deny",
    )

    with pytest.raises(ExecutionDeniedError):
        await runtime.execute_capability("test.probe", {})

    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert adapter.calls == 0
    assert run.state == RunState.FAILED
    assert task.state == TaskState.FAILED
    assert task.attempt == 0
    events = repositories.list_events(run_id=run.id, limit=None)
    policy_event = next(event for event in events if event.type == "PolicyEvaluated")
    assert policy_event.payload["allowed"] is False
    assert not any(event.type == "TaskStarted" for event in events)
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-denial", 60)


def test_recovery_marks_ambiguous_tasks_and_releases_their_leases(tmp_path) -> None:
    runtime, repositories = build_runtime(tmp_path)
    run = repositories.create_run(RunRecord(workflow_id="recovery", state=RunState.RUNNING))
    running = repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="running",
            capability_id="instrument.run",
            state=TaskState.RUNNING,
        )
    )
    retrying = repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="retrying",
            capability_id="instrument.retry",
            state=TaskState.RETRYING,
        )
    )
    terminal_tasks = [
        repositories.upsert_task(
            TaskRecord(
                run_id=run.id,
                step_id="succeeded",
                capability_id="instrument.done",
                state=TaskState.SUCCEEDED,
                outputs={"result": "known"},
            )
        ),
        repositories.upsert_task(
            TaskRecord(
                run_id=run.id,
                step_id="failed",
                capability_id="instrument.failed",
                state=TaskState.FAILED,
                error="known failure",
            )
        ),
        repositories.upsert_task(
            TaskRecord(
                run_id=run.id,
                step_id="cancelled",
                capability_id="instrument.cancelled",
                state=TaskState.CANCELLED,
                error="operator cancelled",
            )
        ),
    ]
    for resource_id, holder_id in [
        ("resource-running", running.id),
        ("resource-retrying", retrying.id),
    ]:
        repositories.upsert_resource(Resource(id=resource_id, name=resource_id, type="instrument"))
        assert repositories.acquire_leases([resource_id], holder_id, 60)

    recovered = runtime.recover_incomplete_runs()

    assert [item.id for item in recovered] == [run.id]
    recovered_run = repositories.get_run(run.id)
    assert recovered_run is not None
    assert recovered_run.state == RunState.INTERVENTION_REQUIRED
    assert "controller restarted" in (recovered_run.error or "")

    tasks = {task.id: task for task in repositories.list_tasks(run.id)}
    for task in (running, retrying):
        assert tasks[task.id].state == TaskState.INTERVENTION_REQUIRED
        assert "physical outcome is unknown" in (tasks[task.id].error or "")
    assert [tasks[task.id].state for task in terminal_tasks] == [
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    ]
    assert tasks[terminal_tasks[0].id].outputs == {"result": "known"}
    assert tasks[terminal_tasks[1].id].error == "known failure"
    assert tasks[terminal_tasks[2].id].error == "operator cancelled"

    assert repositories.acquire_leases(["resource-running", "resource-retrying"], "replacement", 60)
    events = repositories.list_events(run_id=run.id, limit=None)
    recovery_events = [event for event in events if event.type == "TaskRecoveryRequired"]
    assert {event.task_id for event in recovery_events} == {running.id, retrying.id}
    assert {event.payload["previousState"] for event in recovery_events} == {
        TaskState.RUNNING.value,
        TaskState.RETRYING.value,
    }
    assert all("physical outcome is unknown" in event.payload["error"] for event in recovery_events)
    run_recovery_event = next(event for event in events if event.type == "RunRecoveryRequired")
    assert "controller restarted" in run_recovery_event.payload["error"]


@pytest.mark.asyncio
async def test_resume_refuses_a_task_whose_physical_outcome_is_unknown(tmp_path) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    workflow = probe_workflow()
    run = repositories.create_run(
        RunRecord(
            workflow_id=workflow.id,
            state=RunState.INTERVENTION_REQUIRED,
            error="controller restarted while run was active",
        )
    )
    task = repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="probe",
            capability_id="test.probe",
            state=TaskState.INTERVENTION_REQUIRED,
            attempt=1,
            error="controller restarted while task was active; physical outcome is unknown",
        )
    )

    with pytest.raises(WorkflowExecutionError) as raised:
        await runtime.run_workflow(workflow, {}, run_id=run.id)

    message = str(raised.value)
    assert adapter.calls == 0
    assert run.id in message
    assert task.id in message
    assert "probe" in message
    assert "test.probe" in message
    assert TaskState.INTERVENTION_REQUIRED.value in message
    assert "physical outcome" in message
    assert "controller restarted while task was active" in message
    stored_run = repositories.get_run(run.id)
    assert stored_run is not None
    assert stored_run.state == RunState.INTERVENTION_REQUIRED
    stored_task = repositories.list_tasks(run.id)[0]
    assert stored_task.state == TaskState.INTERVENTION_REQUIRED
    assert stored_task.attempt == 1
    events = repositories.list_events(run_id=run.id, limit=None)
    assert [event.type for event in events] == []


@pytest.mark.asyncio
async def test_resume_refuses_a_cancelled_or_active_task(tmp_path) -> None:
    for state in (TaskState.CANCELLED, TaskState.RUNNING, TaskState.RETRYING):
        adapter = ProbeAdapter()
        runtime, repositories = build_probe_runtime(tmp_path / state.value, adapter)
        workflow = probe_workflow()
        run = repositories.create_run(
            RunRecord(workflow_id=workflow.id, state=RunState.INTERVENTION_REQUIRED)
        )
        repositories.upsert_task(
            TaskRecord(
                run_id=run.id,
                step_id="probe",
                capability_id="test.probe",
                state=state,
            )
        )

        with pytest.raises(WorkflowExecutionError) as raised:
            await runtime.run_workflow(workflow, {}, run_id=run.id)

        assert adapter.calls == 0
        assert state.value in str(raised.value)


@pytest.mark.asyncio
async def test_invalid_adapter_output_fails_without_repeating_the_action(tmp_path) -> None:
    adapter = ProbeAdapter(output={"ok": "definitely"}, max_retries=2)
    runtime, repositories = build_probe_runtime(tmp_path, adapter)

    with pytest.raises(ValidationError) as raised:
        await runtime.execute_capability("test.probe", {})

    message = str(raised.value)
    assert adapter.calls == 1
    assert "test.probe output failed at ok" in message
    assert "does not retry" in message
    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert run.state == RunState.FAILED
    assert run.error == message
    assert task.state == TaskState.FAILED
    assert task.error == message
    assert task.attempt == 1
    assert task.outputs == {}
    events = repositories.list_events(run_id=run.id, limit=None)
    assert not any(event.type == "TaskRetrying" for event in events)
    assert not any(event.type == "TaskSucceeded" for event in events)
    task_failed = next(event for event in events if event.type == "TaskFailed")
    assert task_failed.payload["reason"] == "invalid_output"
    assert task_failed.payload["error"] == message
    run_failed = next(event for event in events if event.type == "RunFailed")
    assert run_failed.payload["errorType"] == "ValidationError"
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-invalid-output", 60)


@pytest.mark.asyncio
async def test_unregistered_resource_stops_the_task_before_dispatch(tmp_path) -> None:
    adapter = ProbeAdapter(required_resources=["ghost-instrument"])
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    expected = "required resources are not registered: ['ghost-instrument']"

    with pytest.raises(ResourceBusyError) as raised:
        await runtime.execute_capability("test.probe", {})

    assert adapter.calls == 0
    assert str(raised.value) == expected
    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert run.state == RunState.FAILED
    assert run.error == expected
    assert task.state == TaskState.FAILED
    assert task.error == expected
    assert task.attempt == 0
    events = repositories.list_events(run_id=run.id, limit=None)
    assert not any(event.type == "TaskStarted" for event in events)
    run_failed = next(event for event in events if event.type == "RunFailed")
    assert run_failed.payload["errorType"] == "ResourceBusyError"


@pytest.mark.asyncio
async def test_held_lease_fails_the_task_and_leaves_the_holder_in_place(tmp_path) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    assert repositories.acquire_leases(["probe-resource"], "other-task", 60)
    expected = "resources busy: ['probe-resource']"

    with pytest.raises(ResourceBusyError) as raised:
        await runtime.execute_capability("test.probe", {})

    assert adapter.calls == 0
    assert str(raised.value) == expected
    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert run.state == RunState.FAILED
    assert task.state == TaskState.FAILED
    assert task.error == expected
    events = repositories.list_events(run_id=run.id, limit=None)
    assert not any(event.type == "TaskStarted" for event in events)
    assert not repositories.acquire_leases(["probe-resource"], "third-task", 60)
    assert repositories.acquire_leases(["probe-resource"], "other-task", 60)


@pytest.mark.asyncio
async def test_permanent_adapter_failure_stops_after_the_retry_budget(tmp_path) -> None:
    adapter = ProbeAdapter(failures=10, max_retries=2)
    runtime, repositories = build_probe_runtime(tmp_path, adapter)

    with pytest.raises(WorkflowExecutionError) as raised:
        await runtime.execute_capability("test.probe", {})

    assert adapter.calls == 3
    assert str(raised.value) == "transient failure 3"
    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert run.state == RunState.FAILED
    assert run.error == "transient failure 3"
    assert task.state == TaskState.FAILED
    assert task.error == "transient failure 3"
    assert task.attempt == 3
    events = repositories.list_events(run_id=run.id, limit=None)
    task_events = [
        event.type
        for event in events
        if event.type in {"TaskStarted", "TaskRetrying", "TaskFailed", "TaskSucceeded"}
    ]
    assert task_events == ["TaskStarted", "TaskRetrying", "TaskRetrying", "TaskFailed"]
    run_failed = next(event for event in events if event.type == "RunFailed")
    assert run_failed.payload["errorType"] == "RuntimeError"
    assert repositories.acquire_leases(["probe-resource"], "replacement-after-failure", 60)


def resume_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="resume",
        name="Resume",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "array", "items": {"type": "number"}},
                "b": {"type": "array", "items": {"type": "number"}},
            },
        },
        steps=[
            WorkflowStep(
                id="score",
                capability="compute.euclidean_distance",
                inputs={"a": "${inputs.a}", "b": "${inputs.b}"},
            ),
            WorkflowStep(id="probe", capability="test.probe", inputs={}),
        ],
        outputs={"score": "${steps.score.output.distance}", "probe": "${steps.probe.output}"},
    )


def build_resume_runtime(tmp_path, adapter: ProbeAdapter):
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    repositories.upsert_resource(
        Resource(id="probe-resource", name="Probe resource", type="simulator")
    )
    registry = CapabilityRegistry()
    registry.register(LocalComputeAdapter())
    registry.register(adapter)
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
    )
    return runtime, repositories


@pytest.mark.asyncio
async def test_resume_reruns_only_the_unfinished_step(tmp_path) -> None:
    adapter = ProbeAdapter(failures=1)
    runtime, repositories = build_resume_runtime(tmp_path, adapter)
    workflow = resume_workflow()
    inputs = {"a": [0, 0], "b": [3, 4]}

    with pytest.raises(WorkflowExecutionError):
        await runtime.run_workflow(workflow, inputs, operator_id="operator/alice")

    failed = repositories.list_runs()[0]
    tasks = {task.step_id: task for task in repositories.list_tasks(failed.id)}
    assert failed.state == RunState.FAILED
    assert tasks["score"].state == TaskState.SUCCEEDED
    assert tasks["probe"].state == TaskState.FAILED
    assert adapter.calls == 1

    resumed = await runtime.run_workflow(
        workflow, inputs, run_id=failed.id, operator_id="operator/alice"
    )

    assert resumed.id == failed.id
    assert resumed.state == RunState.COMPLETED
    assert resumed.outputs == {"score": 5, "probe": {"ok": True}}
    assert adapter.calls == 2
    resumed_tasks = {task.step_id: task for task in repositories.list_tasks(failed.id)}
    assert resumed_tasks["score"].id == tasks["score"].id
    assert resumed_tasks["score"].attempt == 1
    assert resumed_tasks["probe"].id == tasks["probe"].id
    assert resumed_tasks["probe"].state == TaskState.SUCCEEDED
    events = repositories.list_events(run_id=failed.id, limit=None)
    assert [event.type for event in events].count("RunCreated") == 1
    assert [event.type for event in events].count("RunStarted") == 2
    score_started = [
        event
        for event in events
        if event.type == "TaskStarted" and event.task_id == tasks["score"].id
    ]
    assert len(score_started) == 1


@pytest.mark.asyncio
async def test_resume_rejects_a_run_belonging_to_another_workflow(tmp_path) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    run = repositories.create_run(RunRecord(workflow_id="other-workflow", state=RunState.FAILED))

    with pytest.raises(ValueError) as raised:
        await runtime.run_workflow(probe_workflow(), {}, run_id=run.id)

    assert str(raised.value) == f"run {run.id} belongs to workflow other-workflow"
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_resubmitting_a_completed_run_is_rejected(tmp_path) -> None:
    runtime, repositories = build_runtime(tmp_path)
    workflow = WorkflowDefinition(
        id="distance",
        name="Distance",
        steps=[
            WorkflowStep(
                id="score",
                capability="compute.euclidean_distance",
                inputs={"a": [0, 0], "b": [3, 4]},
            )
        ],
        outputs={"score": "${steps.score.output.distance}"},
    )
    run = await runtime.run_workflow(workflow, {}, operator_id="operator/alice")
    assert run.state == RunState.COMPLETED
    forged = WorkflowDefinition(
        id="distance",
        name="Distance",
        steps=[
            WorkflowStep(
                id="forged",
                capability="compute.euclidean_distance",
                inputs={"a": [0, 0], "b": [6, 8]},
            )
        ],
        outputs={"score": "${steps.forged.output.distance}"},
    )

    with pytest.raises(LifecycleError) as raised:
        await runtime.run_workflow(forged, {}, run_id=run.id, operator_id="operator/mallory")

    message = str(raised.value)
    assert run.id in message
    assert RunState.COMPLETED.value in message
    stored = repositories.get_run(run.id)
    assert stored is not None
    assert stored.state == RunState.COMPLETED
    assert stored.outputs == {"score": 5}
    assert stored.operator_id == "operator/alice"
    assert [task.step_id for task in repositories.list_tasks(run.id)] == ["score"]
    events = repositories.list_events(run_id=run.id, limit=None)
    assert [event.type for event in events].count("RunStarted") == 1
    assert not any(event.actor_id == "operator/mallory" for event in events)


@pytest.mark.asyncio
async def test_resubmitting_an_aborted_run_is_rejected(tmp_path) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_probe_runtime(tmp_path, adapter)
    workflow = probe_workflow()
    run = repositories.create_run(
        RunRecord(workflow_id=workflow.id, state=RunState.ABORTED, error="operator aborted")
    )

    with pytest.raises(LifecycleError) as raised:
        await runtime.run_workflow(workflow, {}, run_id=run.id)

    assert adapter.calls == 0
    assert RunState.ABORTED.value in str(raised.value)
    stored = repositories.get_run(run.id)
    assert stored is not None
    assert stored.state == RunState.ABORTED
    assert repositories.list_events(run_id=run.id, limit=None) == []


def test_recovery_reconciles_a_run_that_was_aborting(tmp_path) -> None:
    runtime, repositories = build_runtime(tmp_path)
    run = repositories.create_run(RunRecord(workflow_id="abort", state=RunState.ABORTING))
    repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="retrying",
            capability_id="instrument.retry",
            state=TaskState.RETRYING,
        )
    )

    recovered = runtime.recover_incomplete_runs()

    assert [item.id for item in recovered] == [run.id]
    assert [item.state for item in recovered] == [RunState.INTERVENTION_REQUIRED]
    task = repositories.list_tasks(run.id)[0]
    assert task.state == TaskState.INTERVENTION_REQUIRED
    assert "physical outcome is unknown" in (task.error or "")


def build_multi_adapter_runtime(tmp_path, *adapters: CapabilityAdapter):
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    for adapter in adapters:
        registry.register(adapter)
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path, repositories),
    )
    return runtime, repositories


def single_step_workflow(workflow_id: str, capability: str) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=workflow_id,
        name=workflow_id,
        steps=[WorkflowStep(id="only", capability=capability, inputs={})],
        outputs={"result": "${steps.only.output}"},
    )


@pytest.mark.asyncio
async def test_a_declared_timeout_binds_a_blocking_adapter(tmp_path) -> None:
    """A timeout that only fires for adapters that yield is not a timeout.

    The runtime waits for the adapter somewhere it can stop waiting, so the declared bound holds
    for a synchronous call inside an `async def` — the shape a vendor SDK forces. It does not stop
    the work: the adapter runs to completion on its own thread, which is why the assertions below
    check the runtime's wait and not the adapter's.
    """

    adapter = BlockingAdapter(seconds=2.0, timeout_seconds=0.1)
    runtime, repositories = build_multi_adapter_runtime(tmp_path, adapter)
    expected = "execution of test.blocking timed out after 0.1 seconds on attempt 1"

    started = time.monotonic()
    with pytest.raises(WorkflowExecutionError) as raised:
        await runtime.run_workflow(single_step_workflow("blocking", "test.blocking"), {})
    elapsed = time.monotonic() - started

    assert str(raised.value) == expected
    assert elapsed < 1.0, f"the runtime waited {elapsed:.3f}s for a 0.1s timeout"
    assert adapter.calls == 1
    run = repositories.list_runs()[0]
    task = repositories.list_tasks(run.id)[0]
    assert run.state == RunState.FAILED
    assert task.state == TaskState.FAILED
    assert task.error == expected
    assert adapter.finished.wait(timeout=5), "the abandoned adapter call never finished"


@pytest.mark.asyncio
async def test_a_blocking_adapter_does_not_stall_a_concurrent_run(tmp_path) -> None:
    """A blocking adapter used to hold the event loop, so nothing else in the process ran.

    That made `max_concurrency` a fiction and stalled every other run's timeout and lease handling
    behind whichever adapter blocked first. The blocking capability here declares a timeout it
    never reaches, so this measures the stall rather than the timeout.
    """

    blocking = BlockingAdapter(seconds=2.0, timeout_seconds=30.0)
    awaiting = AwaitingAdapter(seconds=0.05)
    runtime, _ = build_multi_adapter_runtime(tmp_path, blocking, awaiting)
    started = time.monotonic()

    async def timed(workflow_id: str, capability: str) -> float:
        await runtime.run_workflow(single_step_workflow(workflow_id, capability), {})
        return time.monotonic() - started

    awaiting_elapsed, blocking_elapsed = await asyncio.gather(
        timed("awaiting", "test.awaiting"),
        timed("blocking", "test.blocking"),
    )

    assert blocking_elapsed >= 2.0, "the blocking adapter did not actually block"
    # Measured at 0.11-0.23s here and at the full 2.0s stall before adapter code moved off the
    # calling loop. The threshold is deliberately loose: a busy-wait holds the GIL between switch
    # intervals, so a loaded machine slows the concurrent run without stalling it.
    assert awaiting_elapsed < 1.0, (
        f"a 0.05s run finished {awaiting_elapsed:.3f}s after submission, so the blocking "
        "adapter stalled the event loop"
    )


@pytest.mark.asyncio
async def test_resume_continues_a_run_whose_recorded_tasks_are_settled(tmp_path) -> None:
    adapter = ProbeAdapter()
    runtime, repositories = build_resume_runtime(tmp_path, adapter)
    workflow = resume_workflow()
    inputs = {"a": [0, 0], "b": [3, 4]}
    run = repositories.create_run(
        RunRecord(
            workflow_id=workflow.id,
            state=RunState.INTERVENTION_REQUIRED,
            inputs=inputs,
            error="operator paused the cell between steps",
        )
    )
    repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="score",
            capability_id="compute.euclidean_distance",
            state=TaskState.SUCCEEDED,
            outputs={"distance": 5},
        )
    )
    repositories.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="probe",
            capability_id="test.probe",
            state=TaskState.PENDING,
        )
    )

    resumed = await runtime.run_workflow(workflow, inputs, run_id=run.id)

    assert resumed.state == RunState.COMPLETED
    assert resumed.outputs == {"score": 5, "probe": {"ok": True}}
    assert adapter.calls == 1
    states = {task.step_id: task.state for task in repositories.list_tasks(run.id)}
    assert states == {"score": TaskState.SUCCEEDED, "probe": TaskState.SUCCEEDED}
