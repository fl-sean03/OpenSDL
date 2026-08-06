from datetime import UTC, datetime, timedelta

import pytest

from opensdl_core import (
    ArtifactKind,
    EventRecord,
    LifecycleError,
    Resource,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
)
from opensdl_storage import (
    ArtifactStore,
    Database,
    LocalArtifactStore,
    Repositories,
    RepositoryStore,
)


def build_repository(tmp_path):
    database = Database("sqlite:///:memory:")
    database.initialize()
    return database, Repositories(database)


def test_run_task_event_round_trip(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo"))
    repo.update_run(run.id, state=RunState.RUNNING)
    task = repo.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="one",
            capability_id="echo",
            state=TaskState.SUCCEEDED,
            outputs={"x": 1},
        )
    )
    repo.append_event(EventRecord(type="TaskSucceeded", run_id=run.id, task_id=task.id))
    stored_run = repo.get_run(run.id)
    assert stored_run is not None
    assert stored_run.state == RunState.RUNNING
    assert repo.list_tasks(run.id)[0].outputs == {"x": 1}
    assert repo.list_events(run_id=run.id)[0].type == "TaskSucceeded"
    assert isinstance(repo, RepositoryStore)
    database.dispose()


def test_leases_and_artifacts(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    repo.upsert_resource(Resource(id="balance", name="Balance", type="instrument"))
    assert repo.acquire_leases(["balance"], "task-a", 60)
    assert not repo.acquire_leases(["balance"], "task-b", 60)
    repo.release_leases("task-a")
    assert repo.acquire_leases(["balance"], "task-b", 60)
    store = LocalArtifactStore(tmp_path / "artifacts", repo)
    assert isinstance(store, ArtifactStore)
    artifact = store.put_json({"ok": True}, kind=ArtifactKind.DERIVED)
    assert store.read_bytes(artifact).startswith(b"{")


def test_event_queries_support_complete_and_deterministic_newest_first_results(
    tmp_path,
) -> None:
    database, repo = build_repository(tmp_path)
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    for event in [
        EventRecord(id="event_b", type="second", occurred_at=occurred_at),
        EventRecord(
            id="event_c",
            type="third",
            occurred_at=occurred_at + timedelta(seconds=1),
        ),
        EventRecord(id="event_a", type="first", occurred_at=occurred_at),
    ]:
        repo.append_event(event)

    assert [event.id for event in repo.list_events(limit=2)] == ["event_a", "event_b"]
    assert [event.id for event in repo.list_events(limit=None)] == [
        "event_a",
        "event_b",
        "event_c",
    ]
    assert [event.id for event in repo.list_events(limit=2, newest_first=True)] == [
        "event_c",
        "event_b",
    ]
    database.dispose()


def test_update_run_enforces_the_declared_lifecycle(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo"))
    repo.update_run(run.id, state=RunState.RUNNING)
    repo.update_run(run.id, state=RunState.COMPLETED, outputs={"score": 5})

    with pytest.raises(LifecycleError) as raised:
        repo.update_run(run.id, state=RunState.RUNNING, outputs={"score": 10})

    assert "completed" in str(raised.value)
    assert "running" in str(raised.value)
    stored = repo.get_run(run.id)
    assert stored is not None
    assert stored.state == RunState.COMPLETED
    assert stored.outputs == {"score": 5}
    database.dispose()


def test_update_run_allows_repeated_and_metadata_only_writes(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo"))
    repo.update_run(run.id, state=RunState.RUNNING)
    repo.update_run(run.id, state=RunState.RUNNING, error=None)
    repo.update_run(run.id, outputs={"partial": True})
    stored = repo.get_run(run.id)
    assert stored is not None
    assert stored.state == RunState.RUNNING
    assert stored.outputs == {"partial": True}
    database.dispose()


def test_upsert_task_enforces_the_declared_lifecycle(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo"))
    task = TaskRecord(run_id=run.id, step_id="one", capability_id="echo")
    repo.upsert_task(task)
    task.state = TaskState.WAITING_FOR_RESOURCES
    repo.upsert_task(task)
    task.state = TaskState.RUNNING
    repo.upsert_task(task)
    task.state = TaskState.SUCCEEDED
    task.outputs = {"x": 1}
    repo.upsert_task(task)

    task.state = TaskState.RUNNING
    task.outputs = {"x": 2}
    with pytest.raises(LifecycleError) as raised:
        repo.upsert_task(task)

    assert "succeeded" in str(raised.value)
    stored = repo.list_tasks(run.id)[0]
    assert stored.state == TaskState.SUCCEEDED
    assert stored.outputs == {"x": 1}
    database.dispose()


def test_upsert_task_creates_rows_in_any_state(tmp_path) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo", state=RunState.RUNNING))
    recovered = repo.upsert_task(
        TaskRecord(
            run_id=run.id,
            step_id="one",
            capability_id="echo",
            state=TaskState.INTERVENTION_REQUIRED,
        )
    )
    assert repo.list_tasks(run.id)[0].state == TaskState.INTERVENTION_REQUIRED
    recovered.state = TaskState.FAILED
    repo.upsert_task(recovered)
    assert repo.list_tasks(run.id)[0].state == TaskState.FAILED
    database.dispose()
