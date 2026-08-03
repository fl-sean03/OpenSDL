import asyncio
from typing import Literal

import pytest

from opensdl_adapter_local_compute import LocalComputeAdapter
from opensdl_capabilities import CapabilityAdapter, CapabilityRegistry
from opensdl_core import (
    CapabilityDefinition,
    ExecutionDeniedError,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    Resource,
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
    ) -> None:
        super().__init__()
        self.failures = failures
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.calls = 0
        self.started = asyncio.Event()

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
                required_resources=["probe-resource"],
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
    await asyncio.wait_for(adapter.started.wait(), timeout=1)

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
