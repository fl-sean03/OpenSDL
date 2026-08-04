from datetime import UTC, datetime, timedelta
from pathlib import Path

from opensdl_core import EventRecord
from opensdl_twin import TwinService


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]


def test_failed_operation_does_not_play_success_motion() -> None:
    service = TwinService.from_file(EXAMPLE_ROOT / "twin.yaml")
    started = datetime(2026, 8, 3, tzinfo=UTC)
    events = [
        EventRecord(
            id="event-started",
            type="TaskStarted",
            occurred_at=started,
            run_id="run-failed",
            task_id="task-dispense",
        ),
        EventRecord(
            id="event-failed",
            type="TaskFailed",
            occurred_at=started + timedelta(seconds=1),
            run_id="run-failed",
            task_id="task-dispense",
            payload={"error": "simulated fault"},
        ),
    ]

    cues = service.project_run(events, {"task-dispense": "cell.dispense"})

    assert [(cue.phase.value, cue.action.value) for cue in cues] == [
        ("started", "highlight"),
        ("failed", "highlight"),
    ]
    assert cues[-1].target == "pipette-head"
    assert cues[-1].parameters == {"active": True, "tone": "red", "status": "failed"}
