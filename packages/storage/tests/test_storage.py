import threading
from datetime import UTC, datetime, timedelta

import pytest

from opensdl_core import (
    STARTABLE_RUN_STATES,
    ArtifactKind,
    EventRecord,
    LifecycleError,
    Resource,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
)
from opensdl_storage.db_models import LeaseRow
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


def test_a_run_is_claimed_once(tmp_path) -> None:
    """`start_run` is a conditional write, so a second claim on the same run fails."""
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo", state=RunState.FAILED))

    claimed = repo.start_run(run.id)

    assert claimed is not None
    assert claimed.state == RunState.RUNNING
    assert claimed.error is None
    assert repo.start_run(run.id) is None
    assert repo.get_run(run.id).state == RunState.RUNNING  # type: ignore[union-attr]
    database.dispose()


#: Split from the declared machine rather than listed, so a new run state joins one of these two
#: parametrisations automatically and cannot arrive untested.
STARTABLE: list[RunState] = sorted(STARTABLE_RUN_STATES, key=lambda item: item.value)
UNSTARTABLE: list[RunState] = sorted(set(RunState) - STARTABLE_RUN_STATES, key=lambda i: i.value)


@pytest.mark.parametrize("state", STARTABLE)
def test_every_declared_start_state_can_be_claimed(tmp_path, state: RunState) -> None:
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo", state=state))

    claimed = repo.start_run(run.id)

    assert claimed is not None and claimed.state == RunState.RUNNING
    database.dispose()


@pytest.mark.parametrize("state", UNSTARTABLE)
def test_no_other_state_can_be_claimed(tmp_path, state: RunState) -> None:
    """Including `RUNNING`: the declared machine never let a run start from it."""
    database, repo = build_repository(tmp_path)
    run = repo.create_run(RunRecord(workflow_id="demo", state=state))

    assert repo.start_run(run.id) is None
    assert repo.get_run(run.id).state == state  # type: ignore[union-attr]
    database.dispose()


def test_claiming_a_run_that_does_not_exist_reports_it(tmp_path) -> None:
    database, repo = build_repository(tmp_path)

    assert repo.start_run("run_absent") is None
    database.dispose()


def _expired_lease(database, resource_id: str, holder_id: str) -> None:
    """Leave `resource_id` holding a lease that has already run out."""

    with database.session() as session:
        session.add(
            LeaseRow(
                resource_id=resource_id,
                holder_id=holder_id,
                expires_at=datetime.now(UTC) - timedelta(seconds=60),
            )
        )


def test_a_lease_that_has_run_out_goes_to_exactly_one_of_the_callers_racing_for_it(
    tmp_path,
) -> None:
    """Two holders of one instrument is the failure this lease exists to prevent.

    Acquisition used to read every resource and then write every resource. Between those two
    steps another caller fits: both read the lease as expired, both take it, and both are told
    they hold it. The row records one of them; the other drives the same instrument believing it
    is alone. Against that implementation this test granted four or five of six callers on every
    run of ten, so it is not a probabilistic guard — it is the defect, reproduced.

    A file-backed store is required: `sqlite:///:memory:` gives each connection its own database,
    so the callers would not contend at all and this would pass against anything.
    """

    database = Database(f"sqlite:///{tmp_path / 'lab.db'}")
    database.initialize()
    _expired_lease(database, "balance", "the-holder-that-timed-out")

    contenders = 6
    ready = threading.Barrier(contenders, timeout=30)
    outcomes: dict[str, object] = {}

    def contend(holder_id: str) -> None:
        repositories = Repositories(Database(f"sqlite:///{tmp_path / 'lab.db'}"))
        ready.wait()
        try:
            outcomes[holder_id] = repositories.acquire_leases(["balance"], holder_id, 60)
        except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
            outcomes[holder_id] = f"{type(exc).__name__}: {exc}"

    threads = [
        threading.Thread(target=contend, args=(f"task-{index}",)) for index in range(contenders)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    granted = [holder for holder, result in outcomes.items() if result is True]
    assert len(granted) == 1, outcomes
    # Losing a race is an answer, not an error: contention must reach the caller as `False`.
    assert [result for result in outcomes.values() if isinstance(result, str)] == []
    assert sorted(outcomes.values(), key=repr) == sorted([True] + [False] * 5, key=repr)


def test_a_lease_is_taken_whole_or_not_at_all(tmp_path) -> None:
    """A caller told it does not hold the set must hold no part of it.

    Claiming resource by resource means the refusal can arrive with earlier claims already
    written. Leaving those behind would strand an instrument nobody is using and nobody released,
    until its lease ran out. Removing the rollback turns the last assertion here red.
    """

    database, repositories = build_repository(tmp_path)
    assert repositories.acquire_leases(["mixer"], "task-incumbent", 60)

    # `balance` sorts first, so it is claimed before `mixer` refuses the set.
    assert not repositories.acquire_leases(["balance", "mixer"], "task-latecomer", 60)

    # `balance` must be free for the next caller, and the incumbent must still hold `mixer`.
    assert repositories.acquire_leases(["balance"], "task-third-party", 60)
    assert not repositories.acquire_leases(["mixer"], "task-third-party", 60)


def test_a_lease_is_refused_while_live_taken_over_once_expired_and_renewed_by_its_holder(
    tmp_path,
) -> None:
    """The three answers the conditional write has to give, stated one at a time."""

    database, repositories = build_repository(tmp_path)

    assert repositories.acquire_leases(["balance"], "task-a", 60)
    assert not repositories.acquire_leases(["balance"], "task-b", 60)
    # Its own holder renews rather than refusing itself.
    assert repositories.acquire_leases(["balance"], "task-a", 60)

    _expired_lease(database, "colorimeter", "task-departed")
    assert repositories.acquire_leases(["colorimeter"], "task-c", 60)
    assert not repositories.acquire_leases(["colorimeter"], "task-d", 60)
