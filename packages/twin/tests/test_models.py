from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from opensdl_twin import TwinCue, TwinDefinition, validate_json_pointer, validate_safe_relative_path


def cue_data() -> dict[str, Any]:
    return {
        "id": "cue_0123456789abcdef01234567",
        "sequence": 0,
        "sourceEventId": "event-started",
        "taskId": "task-transfer",
        "capabilityId": "cell.transfer_labware",
        "occurredAt": "2026-08-03T12:00:00+00:00",
        "phase": "started",
        "action": "highlight",
        "target": "robot",
    }


def test_definition_accepts_camel_case_contract_and_dumps_aliases(
    definition_data: dict[str, Any],
) -> None:
    definition = TwinDefinition.model_validate(definition_data)

    assert definition.coordinate_frame.up_axis.value == "Z"
    assert definition.scene.sha256 == "a" * 64
    assert definition.entities[0].resources == ("cell.robot",)
    dumped = definition.model_dump(mode="json", by_alias=True)
    assert dumped["apiVersion"] == "opensdl.dev/v0alpha1"
    assert dumped["coordinateFrame"]["upAxis"] == "Z"
    assert dumped["projectionRules"][1]["parameterPointers"]["source"].startswith("/")


def test_sha256_is_normalized_to_lowercase(definition_data: dict[str, Any]) -> None:
    definition_data["scene"]["sha256"] = "A" * 64
    assert TwinDefinition.model_validate(definition_data).scene.sha256 == "a" * 64


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/scene.glb",
        "../scene.glb",
        "generated/../../scene.glb",
        "C:/scene.glb",
        r"generated\scene.glb",
        "https://example.test/scene.glb",
        "generated//scene.glb",
        "generated/scene.glb/",
        "./scene.glb",
        "",
    ],
)
def test_scene_path_rejects_unsafe_or_non_normalized_values(path: str) -> None:
    with pytest.raises(ValueError):
        validate_safe_relative_path(path)


def test_scene_path_accepts_definition_relative_posix_path() -> None:
    assert validate_safe_relative_path("generated/scene.glb") == "generated/scene.glb"


@pytest.mark.parametrize("pointer", ["", "/", "/event/payload/a~1b", "/event/~0key/0"])
def test_json_pointer_accepts_rfc_6901_syntax(pointer: str) -> None:
    assert validate_json_pointer(pointer) == pointer


@pytest.mark.parametrize(
    "pointer",
    ["event/payload", "#event", "/event/~", "/event/~2bad", "/event/bad~x"],
)
def test_json_pointer_rejects_invalid_syntax(pointer: str) -> None:
    with pytest.raises(ValueError):
        validate_json_pointer(pointer)


@pytest.mark.parametrize(
    ("field", "mutate", "message"),
    [
        (
            "entity ids",
            lambda data: data["entities"].append(
                {"id": data["entities"][0]["id"], "node": "another_node"}
            ),
            "entity ids must be unique",
        ),
        (
            "entity nodes",
            lambda data: data["entities"].append(
                {"id": "another", "node": data["entities"][0]["node"]}
            ),
            "entity nodes must be unique",
        ),
        (
            "anchor ids",
            lambda data: data["anchors"].append(
                {"id": data["anchors"][0]["id"], "position": [3, 0, 0]}
            ),
            "anchor ids must be unique",
        ),
        (
            "rule ids",
            lambda data: data["projectionRules"].append(deepcopy(data["projectionRules"][0])),
            "projection rule ids must be unique",
        ),
    ],
)
def test_definition_rejects_duplicate_stable_references(
    definition_data: dict[str, Any],
    field: str,
    mutate: Any,
    message: str,
) -> None:
    del field
    mutate(definition_data)
    with pytest.raises(ValidationError, match=message):
        TwinDefinition.model_validate(definition_data)


def test_definition_rejects_duplicate_entity_resources(definition_data: dict[str, Any]) -> None:
    definition_data["entities"][0]["resources"] = ["cell.robot", "cell.robot"]
    with pytest.raises(ValidationError, match="resources must be unique"):
        TwinDefinition.model_validate(definition_data)


def test_definition_rejects_entity_anchor_id_collision(definition_data: dict[str, Any]) -> None:
    definition_data["anchors"][0]["id"] = "robot"
    with pytest.raises(ValidationError, match="entity and anchor ids overlap"):
        TwinDefinition.model_validate(definition_data)


def test_definition_rejects_unknown_rule_target(definition_data: dict[str, Any]) -> None:
    definition_data["projectionRules"][0]["target"] = "missing"
    with pytest.raises(ValidationError, match="targets unknown entity"):
        TwinDefinition.model_validate(definition_data)


def test_definition_rejects_unknown_static_transfer_anchor(
    definition_data: dict[str, Any],
) -> None:
    rule = definition_data["projectionRules"][1]
    rule["parameterPointers"] = {}
    rule["parameters"] = {"source": "input", "destination": "missing"}
    with pytest.raises(ValidationError, match="unknown static destination anchor"):
        TwinDefinition.model_validate(definition_data)


def test_rule_rejects_invalid_action(definition_data: dict[str, Any]) -> None:
    definition_data["projectionRules"][0]["action"] = "execute"
    with pytest.raises(ValidationError):
        TwinDefinition.model_validate(definition_data)


def test_rule_requires_action_specific_parameters(definition_data: dict[str, Any]) -> None:
    del definition_data["projectionRules"][2]["parameters"]["clip"]
    with pytest.raises(ValidationError, match="requires parameters: clip"):
        TwinDefinition.model_validate(definition_data)


def test_rule_rejects_static_pointer_parameter_overlap(definition_data: dict[str, Any]) -> None:
    definition_data["projectionRules"][1]["parameters"] = {"source": "input"}
    with pytest.raises(ValidationError, match="static and pointer parameters overlap"):
        TwinDefinition.model_validate(definition_data)


def test_rule_rejects_canonical_event_phase_mismatch(definition_data: dict[str, Any]) -> None:
    definition_data["projectionRules"][0]["match"]["phase"] = "succeeded"
    with pytest.raises(ValidationError, match="has phase 'started'"):
        TwinDefinition.model_validate(definition_data)


def test_rule_rejects_non_json_or_non_finite_parameters(definition_data: dict[str, Any]) -> None:
    definition_data["projectionRules"][0]["parameters"] = {"active": float("nan")}
    with pytest.raises(ValidationError, match="finite JSON-compatible"):
        TwinDefinition.model_validate(definition_data)


def test_definition_rejects_invalid_origin_length(definition_data: dict[str, Any]) -> None:
    definition_data["coordinateFrame"]["origin"] = [0, 0]
    with pytest.raises(ValidationError):
        TwinDefinition.model_validate(definition_data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unit", "mm", "Input should be 'm'"),
        ("handedness", "left", "must be right-handed"),
        ("origin", [0.001, 0, 0], r"origin must be \[0, 0, 0\]"),
        ("origin", [float("nan"), 0, 0], "finite coordinates"),
        ("origin", [float("inf"), 0, 0], "finite coordinates"),
    ],
)
def test_v0alpha1_coordinate_frame_rejects_unsupported_values(
    definition_data: dict[str, Any],
    field: str,
    value: Any,
    message: str,
) -> None:
    definition_data["coordinateFrame"][field] = value
    with pytest.raises(ValidationError, match=message):
        TwinDefinition.model_validate(definition_data)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), float("-inf")])
def test_anchor_positions_reject_non_finite_coordinates(
    definition_data: dict[str, Any],
    coordinate: float,
) -> None:
    definition_data["anchors"][0]["position"] = [coordinate, 0, 0]
    with pytest.raises(ValidationError, match="finite coordinates"):
        TwinDefinition.model_validate(definition_data)


def test_twin_definition_is_deeply_immutable_and_serializable(
    definition_data: dict[str, Any],
) -> None:
    definition_data["projectionRules"][0]["parameters"] = {
        "active": True,
        "style": {"colors": ["cyan", "white"]},
    }
    definition = TwinDefinition.model_validate(definition_data)
    rule = definition.projection_rules[0]
    definition_data["projectionRules"][0]["parameters"]["style"]["colors"][0] = "red"

    with pytest.raises(ValidationError):
        definition.revision = "mutated"
    mutable_parameters: Any = rule.parameters
    with pytest.raises(TypeError):
        mutable_parameters["active"] = False
    with pytest.raises(TypeError):
        mutable_parameters["style"]["colors"][0] = "red"
    mutable_pointers: Any = rule.parameter_pointers
    with pytest.raises(TypeError):
        mutable_pointers["value"] = "/event/payload/value"

    copied = rule.model_copy(update={"parameters": {"nested": {"values": [1, 2]}}})
    copied_parameters: Any = copied.parameters
    with pytest.raises(TypeError):
        copied_parameters["nested"]["values"][0] = 9

    dumped = definition.model_dump(mode="json", by_alias=True)
    assert dumped["projectionRules"][0]["parameters"]["style"] == {"colors": ["cyan", "white"]}


def test_animation_timeline_accepts_engine_neutral_frame_bindings(
    definition_data: dict[str, Any],
) -> None:
    definition_data["animationTimeline"] = {
        "frameRate": 24,
        "frameStart": 1,
        "frameEnd": 960,
        "bindings": [
            {
                "id": "mix-cycle",
                "action": "play_clip",
                "parameterMatch": {"clip": "mix_cycle", "options": {"speed": [1, 2]}},
                "frameStart": 548,
                "frameEnd": 644,
            }
        ],
    }

    definition = TwinDefinition.model_validate(definition_data)
    timeline = definition.animation_timeline

    assert timeline is not None
    assert timeline.bindings[0].parameter_match["clip"] == "mix_cycle"
    mutable_match: Any = timeline.bindings[0].parameter_match
    with pytest.raises(TypeError):
        mutable_match["clip"] = "changed"
    with pytest.raises(TypeError):
        mutable_match["options"]["speed"][0] = 99
    assert definition.model_dump(mode="json", by_alias=True)["animationTimeline"] == {
        "frameRate": 24.0,
        "frameStart": 1,
        "frameEnd": 960,
        "bindings": [
            {
                "id": "mix-cycle",
                "action": "play_clip",
                "parameterMatch": {
                    "clip": "mix_cycle",
                    "options": {"speed": [1, 2]},
                },
                "frameStart": 548,
                "frameEnd": 644,
            }
        ],
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda timeline: timeline.update(frameRate=float("nan")), "frameRate must be finite"),
        (lambda timeline: timeline.update(frameRate=float("inf")), "frameRate must be finite"),
        (lambda timeline: timeline.update(frameRate=0), "greater than 0"),
        (lambda timeline: timeline.update(frameEnd=1), "frameEnd must be greater"),
        (
            lambda timeline: timeline["bindings"][0].update(parameterMatch={}),
            "parameterMatch cannot be empty",
        ),
        (
            lambda timeline: timeline["bindings"][0].update(parameterMatch={"clip": float("nan")}),
            "finite JSON-compatible",
        ),
        (lambda timeline: timeline.update(bindings=[]), "at least 1 item"),
        (
            lambda timeline: timeline["bindings"][0].update(frameEnd=961),
            "must stay within the timeline range",
        ),
        (
            lambda timeline: timeline["bindings"][0].update(frameEnd=100),
            "binding frameEnd must be greater",
        ),
        (
            lambda timeline: timeline["bindings"].append(
                {
                    **deepcopy(timeline["bindings"][0]),
                    "frameStart": 650,
                    "frameEnd": 700,
                }
            ),
            "binding ids must be unique",
        ),
    ],
)
def test_animation_timeline_rejects_invalid_contracts(
    definition_data: dict[str, Any],
    mutate: Any,
    message: str,
) -> None:
    timeline = {
        "frameRate": 24,
        "frameStart": 1,
        "frameEnd": 960,
        "bindings": [
            {
                "id": "mix-cycle",
                "action": "play_clip",
                "parameterMatch": {"clip": "mix_cycle"},
                "frameStart": 548,
                "frameEnd": 644,
            }
        ],
    }
    mutate(timeline)
    definition_data["animationTimeline"] = timeline

    with pytest.raises(ValidationError, match=message):
        TwinDefinition.model_validate(definition_data)


def test_animation_timeline_rejects_ambiguous_parameter_matches(
    definition_data: dict[str, Any],
) -> None:
    definition_data["animationTimeline"] = {
        "frameRate": 24,
        "frameStart": 1,
        "frameEnd": 960,
        "bindings": [
            {
                "id": "mix-general",
                "action": "play_clip",
                "parameterMatch": {"clip": "mix_cycle"},
                "frameStart": 548,
                "frameEnd": 644,
            },
            {
                "id": "mix-speed-specific",
                "action": "play_clip",
                "parameterMatch": {"clip": "mix_cycle", "speed": 2},
                "frameStart": 650,
                "frameEnd": 700,
            },
        ],
    }

    with pytest.raises(ValidationError, match="are ambiguous"):
        TwinDefinition.model_validate(definition_data)


def test_cue_accepts_a_complete_projected_contract() -> None:
    cue = TwinCue.model_validate(cue_data())

    assert cue.source_event_id == "event-started"
    assert cue.run_id is None
    assert cue.model_dump(mode="json", by_alias=True)["occurredAt"] == "2026-08-03T12:00:00+00:00"


@pytest.mark.parametrize(
    "field",
    ["id", "sourceEventId", "taskId", "capabilityId", "occurredAt", "target"],
)
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_cue_rejects_blank_identifier_values(field: str, value: str) -> None:
    data = cue_data()
    data[field] = value

    with pytest.raises(ValidationError, match="cannot be blank"):
        TwinCue.model_validate(data)


def test_cue_normalizes_surrounding_whitespace_like_its_sibling_contracts() -> None:
    data = cue_data()
    data["taskId"] = "  task-transfer  "
    data["target"] = "\trobot\n"

    cue = TwinCue.model_validate(data)

    assert cue.task_id == "task-transfer"
    assert cue.target == "robot"
