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


def _campaign_started(campaign_id: str, *, operator_id: str) -> EventRecord:
    return EventRecord(
        type="CampaignStarted",
        actor_id=operator_id,
        campaign_id=campaign_id,
        payload={
            "workflowId": "color-mix-and-score",
            "workflowVersion": "0.1.0",
            "environment": "simulation",
            "operatorId": operator_id,
            "maxIterations": 5,
            "scoreOutput": "score",
            "minimize": True,
            "targetScore": None,
            "maxConsecutiveFailures": 3,
            "maxDurationSeconds": None,
            "iterationIdInput": "sample_id",
            "baseInputs": {},
        },
    )


def test_context_pack_says_when_a_campaign_is_running() -> None:
    """An agent that cannot see a campaign in flight will act as though the laboratory is idle.

    `describe_lab` is the first call an agent makes and the only one that describes the laboratory
    as a whole. Before this it listed active runs and never mentioned the loop that submitted them,
    so an agent could not tell an operator's one-off run from the twentieth iteration of an
    unattended search.
    """
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    repositories.append_event(_campaign_started("campaign-finished", operator_id="operator/alice"))
    repositories.append_event(
        EventRecord(
            type="CampaignCompleted",
            actor_id="operator/alice",
            campaign_id="campaign-finished",
            payload={
                "iterations": 1,
                "succeeded": 1,
                "failed": 0,
                "stopReason": "max_iterations",
                "stopDetail": "ran the configured budget of 1 iterations",
                "best": None,
            },
        )
    )
    repositories.append_event(_campaign_started("campaign-live", operator_id="software/campaign"))
    manifest = LabManifest.model_validate(
        {"metadata": {"name": "Test Lab", "owner": "OpenSDL"}, "spec": {}}
    )
    builder = ContextPackBuilder(manifest, CapabilityRegistry(), repositories, "test/v1")

    context = builder.build()

    assert [item["campaign_id"] for item in context.active_campaigns] == ["campaign-live"]
    running = context.active_campaigns[0]
    assert running["state"] == "running"
    assert running["operator_id"] == "software/campaign"
    assert running["workflow_id"] == "color-mix-and-score"
    assert running["max_iterations"] == 5
    database.dispose()
