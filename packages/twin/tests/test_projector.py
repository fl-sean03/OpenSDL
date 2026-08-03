from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from opensdl_core import EventRecord
from opensdl_twin import (
    LoadedTwinDefinition,
    TwinAction,
    TwinDefinition,
    TwinPhase,
    TwinProjectionError,
    TwinService,
    project_events,
    resolve_json_pointer,
)


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def _event(
    event_id: str,
    event_type: str,
    *,
    task_id: str | None = "task-transfer",
    seconds: int = 0,
    payload: dict | None = None,
) -> EventRecord:
    return EventRecord(
        id=event_id,
        type=event_type,
        occurred_at=NOW + timedelta(seconds=seconds),
        run_id="run-demo",
        task_id=task_id,
        payload=payload or {},
    )


def test_projection_is_deterministic_and_orders_events_before_rules(
    twin_definition: TwinDefinition,
) -> None:
    started = _event(
        "event-started",
        "TaskStarted",
        seconds=1,
        payload={"inputs": {"source": "input", "destination": "output"}},
    )
    succeeded = _event(
        "event-succeeded",
        "TaskSucceeded",
        seconds=2,
        payload={
            "output": {
                "labware_id": "sample-1",
                "source": "input",
                "destination": "output",
            }
        },
    )
    mapping = {"task-transfer": "cell.transfer_labware"}

    forward = project_events(twin_definition, [started, succeeded], mapping)
    reverse = project_events(twin_definition, [succeeded, started], mapping)

    assert forward == reverse
    assert tuple(item.sequence for item in forward) == (0, 1)
    assert forward[0].action == TwinAction.HIGHLIGHT
    assert forward[1].action == TwinAction.TRANSFER
    assert forward[1].parameters == {
        "source": "input",
        "destination": "output",
        "labware": "sample-1",
    }
    assert forward[1].source_event_id == "event-succeeded"
    assert forward[1].capability_id == "cell.transfer_labware"
    assert forward[1].phase == TwinPhase.SUCCEEDED


def test_cue_ids_are_stable_and_include_definition_revision(
    twin_definition: TwinDefinition,
) -> None:
    event = _event("event-started", "TaskStarted")
    mapping = {"task-transfer": "cell.transfer_labware"}
    first = project_events(twin_definition, [event], mapping)[0]
    second = project_events(twin_definition, [event], mapping)[0]
    revised = twin_definition.model_copy(update={"revision": "revision-2"})
    third = project_events(revised, [event], mapping)[0]

    assert first.id == second.id
    assert first.id != third.id


def test_cues_are_frozen_pydantic_records(twin_definition: TwinDefinition) -> None:
    cue = project_events(
        twin_definition,
        [_event("event-started", "TaskStarted")],
        {"task-transfer": "cell.transfer_labware"},
    )[0]

    with pytest.raises(ValidationError):
        cue.sequence = 99


def test_cue_parameters_are_deeply_immutable_and_serialize_as_json(
    definition_data: dict,
) -> None:
    definition_data["projectionRules"][0]["parameters"] = {
        "active": True,
        "style": {"colors": ["cyan", "white"]},
    }
    definition = TwinDefinition.model_validate(definition_data)
    cue = project_events(
        definition,
        [_event("event-started", "TaskStarted")],
        {"task-transfer": "cell.transfer_labware"},
    )[0]

    mutable_parameters: Any = cue.parameters
    with pytest.raises(TypeError):
        mutable_parameters["active"] = False
    with pytest.raises(TypeError):
        mutable_parameters["style"]["colors"][0] = "red"
    assert cue.model_dump(mode="json", by_alias=True)["parameters"] == {
        "active": True,
        "style": {"colors": ["cyan", "white"]},
    }


def test_projection_ignores_unmatched_events_and_capabilities(
    twin_definition: TwinDefinition,
) -> None:
    events = [
        _event("run", "RunStarted", task_id=None),
        _event("other", "TaskStarted", task_id="task-other"),
    ]

    cues = project_events(
        twin_definition,
        events,
        {"task-other": "cell.unmapped"},
    )

    assert cues == ()


def test_failure_does_not_apply_success_projection(twin_definition: TwinDefinition) -> None:
    failed = _event(
        "event-failed",
        "TaskFailed",
        payload={"error": "gripper fault", "output": {"destination": "output"}},
    )
    cues = project_events(
        twin_definition,
        [failed],
        {"task-transfer": "cell.transfer_labware"},
    )
    assert cues == ()


def test_projection_requires_capability_mapping_for_candidate_event(
    twin_definition: TwinDefinition,
) -> None:
    with pytest.raises(TwinProjectionError, match="without a capability mapping"):
        project_events(
            twin_definition,
            [_event("event-started", "TaskStarted")],
            {},
        )


def test_projection_requires_task_id_for_candidate_event(twin_definition: TwinDefinition) -> None:
    with pytest.raises(TwinProjectionError, match="has no task id"):
        project_events(
            twin_definition,
            [_event("event-started", "TaskStarted", task_id=None)],
            {},
        )


def test_projection_rejects_duplicate_persisted_event_ids(
    twin_definition: TwinDefinition,
) -> None:
    event = _event("duplicate", "TaskStarted")
    with pytest.raises(TwinProjectionError, match="event identifiers must be unique"):
        project_events(
            twin_definition,
            [event, event.model_copy()],
            {"task-transfer": "cell.transfer_labware"},
        )


def test_projection_rejects_missing_pointer_value(twin_definition: TwinDefinition) -> None:
    with pytest.raises(TwinProjectionError, match="has no key 'output'"):
        project_events(
            twin_definition,
            [_event("event-succeeded", "TaskSucceeded")],
            {"task-transfer": "cell.transfer_labware"},
        )


def test_projection_rejects_transfer_to_unknown_anchor(twin_definition: TwinDefinition) -> None:
    event = _event(
        "event-succeeded",
        "TaskSucceeded",
        payload={
            "output": {
                "labware_id": "sample-1",
                "source": "input",
                "destination": "not-declared",
            }
        },
    )
    with pytest.raises(TwinProjectionError, match="unknown anchor"):
        project_events(
            twin_definition,
            [event],
            {"task-transfer": "cell.transfer_labware"},
        )


def test_dynamic_clip_and_property_values_are_validated(
    definition_data: dict,
) -> None:
    definition_data["projectionRules"][2]["parameters"] = {}
    definition_data["projectionRules"][2]["parameterPointers"] = {"clip": "/event/payload/clip"}
    definition = TwinDefinition.model_validate(definition_data)
    event = _event(
        "mix-started",
        "TaskStarted",
        task_id="task-mix",
        payload={"clip": ""},
    )

    with pytest.raises(TwinProjectionError, match="invalid animation clip"):
        project_events(definition, [event], {"task-mix": "cell.mix"})


def test_custom_event_uses_explicit_payload_phase(definition_data: dict) -> None:
    definition_data["projectionRules"] = [
        {
            "id": "custom-highlight",
            "match": {
                "eventType": "CustomEquipmentEvent",
                "capability": "cell.custom",
                "phase": "started",
            },
            "action": "highlight",
            "target": "robot",
        }
    ]
    definition = TwinDefinition.model_validate(definition_data)
    event = _event(
        "custom",
        "CustomEquipmentEvent",
        task_id="task-custom",
        payload={"phase": "started"},
    )

    cues = project_events(definition, [event], {"task-custom": "cell.custom"})

    assert len(cues) == 1
    assert cues[0].phase == TwinPhase.STARTED


def test_custom_event_without_recognized_phase_is_rejected(definition_data: dict) -> None:
    definition_data["projectionRules"] = [
        {
            "id": "custom-highlight",
            "match": {
                "eventType": "CustomEquipmentEvent",
                "capability": "cell.custom",
                "phase": "started",
            },
            "action": "highlight",
            "target": "robot",
        }
    ]
    definition = TwinDefinition.model_validate(definition_data)

    with pytest.raises(TwinProjectionError, match="no recognized projection phase"):
        project_events(
            definition,
            [_event("custom", "CustomEquipmentEvent", task_id="task-custom")],
            {"task-custom": "cell.custom"},
        )


def test_json_pointer_resolves_escaped_keys_and_array_indices() -> None:
    document = {"a/b": {"~key": ["zero", "one"]}}
    assert resolve_json_pointer(document, "/a~1b/~0key/1") == "one"
    assert resolve_json_pointer(document, "") is document


@pytest.mark.parametrize("pointer", ["/items/01", "/items/-1", "/items/3"])
def test_json_pointer_rejects_invalid_or_out_of_range_array_indices(pointer: str) -> None:
    with pytest.raises(TwinProjectionError):
        resolve_json_pointer({"items": [1, 2]}, pointer)


def test_service_exposes_verified_paths_and_delegates_projection(
    tmp_path,
    twin_definition: TwinDefinition,
) -> None:
    definition_path = tmp_path / "twin.yaml"
    scene_path = tmp_path / "scene.glb"
    loaded = LoadedTwinDefinition(
        definition=twin_definition,
        definition_path=definition_path,
        scene_path=scene_path,
    )
    service = TwinService(loaded)
    event = _event("event-started", "TaskStarted")

    cues = service.project_run(
        [event],
        {"task-transfer": "cell.transfer_labware"},
    )

    assert service.definition is twin_definition
    assert service.definition_path == definition_path
    assert service.scene_path == scene_path
    assert cues == project_events(
        twin_definition,
        [event],
        {"task-transfer": "cell.transfer_labware"},
    )


def test_cue_timestamps_are_rfc_3339_date_times(twin_definition: TwinDefinition) -> None:
    started = _event("event-started", "TaskStarted", seconds=1)

    cues = project_events(twin_definition, [started], {"task-transfer": "cell.transfer_labware"})

    parsed = datetime.fromisoformat(cues[0].occurred_at)
    assert parsed.utcoffset() is not None
    assert parsed == NOW + timedelta(seconds=1)


def test_naive_event_timestamps_are_published_with_an_explicit_offset(
    twin_definition: TwinDefinition,
) -> None:
    naive = EventRecord(
        id="event-started",
        type="TaskStarted",
        occurred_at=datetime(2026, 8, 3, 12, 0),
        run_id="run-demo",
        task_id="task-transfer",
    )

    cues = project_events(twin_definition, [naive], {"task-transfer": "cell.transfer_labware"})

    assert cues[0].occurred_at == "2026-08-03T12:00:00+00:00"
    assert datetime.fromisoformat(cues[0].occurred_at).utcoffset() is not None
