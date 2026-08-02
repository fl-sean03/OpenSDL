from datetime import UTC, datetime, timedelta

from opensdl_capabilities import CapabilityRegistry
from opensdl_core import EventRecord
from opensdl_operators import ContextPackBuilder
from opensdl_schemas import LabManifest
from opensdl_storage import Database, Repositories


def test_context_pack_selects_latest_events_and_presents_them_chronologically() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    for index in range(5):
        repositories.append_event(
            EventRecord(
                id=f"event_{index}",
                type=f"Event{index}",
                occurred_at=occurred_at + timedelta(seconds=index),
            )
        )
    manifest = LabManifest.model_validate(
        {
            "metadata": {"name": "Test Lab", "owner": "OpenSDL"},
            "spec": {},
        }
    )
    builder = ContextPackBuilder(
        manifest,
        CapabilityRegistry(),
        repositories,
        "test/v1",
    )

    context = builder.build(event_limit=3)

    assert [event["id"] for event in context.recent_events] == [
        "event_2",
        "event_3",
        "event_4",
    ]
    database.dispose()
