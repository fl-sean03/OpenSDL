from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from opensdl_twin import TwinDefinition


@pytest.fixture
def definition_data() -> dict[str, Any]:
    return {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "DigitalTwin",
        "version": "0.1.0",
        "revision": "scene-revision-1",
        "coordinateFrame": {
            "unit": "m",
            "handedness": "right",
            "upAxis": "Z",
            "origin": [0.0, 0.0, 0.0],
        },
        "scene": {
            "path": "generated/scene.glb",
            "sha256": "a" * 64,
        },
        "entities": [
            {"id": "robot", "node": "robot_root", "resources": ["cell.robot"]},
            {"id": "sample", "node": "sample_root"},
            {"id": "mixer", "node": "mixer_root", "resources": ["cell.mixer"]},
        ],
        "anchors": [
            {"id": "input", "position": [0.0, 0.0, 0.0], "node": "input_anchor"},
            {
                "id": "mixer_station",
                "position": [1.0, 0.0, 0.0],
                "node": "mixer_anchor",
            },
            {"id": "output", "position": [2.0, 0.0, 0.0], "node": "output_anchor"},
        ],
        "projectionRules": [
            {
                "id": "highlight-robot-start",
                "match": {
                    "eventType": "TaskStarted",
                    "capability": "cell.transfer_labware",
                    "phase": "started",
                },
                "action": "highlight",
                "target": "robot",
                "parameters": {"active": True},
            },
            {
                "id": "transfer-sample-success",
                "match": {
                    "eventType": "TaskSucceeded",
                    "capability": "cell.transfer_labware",
                    "phase": "succeeded",
                },
                "action": "transfer",
                "target": "sample",
                "parameterPointers": {
                    "source": "/event/payload/output/source",
                    "destination": "/event/payload/output/destination",
                    "labware": "/event/payload/output/labware_id",
                },
            },
            {
                "id": "play-mixer",
                "match": {
                    "eventType": "TaskStarted",
                    "capability": "cell.mix",
                    "phase": "started",
                },
                "action": "play_clip",
                "target": "mixer",
                "parameters": {"clip": "mix_cycle"},
            },
            {
                "id": "set-sample-color",
                "match": {
                    "eventType": "TaskSucceeded",
                    "capability": "cell.characterize",
                    "phase": "succeeded",
                },
                "action": "set_property",
                "target": "sample",
                "parameters": {"property": "color"},
                "parameterPointers": {"value": "/event/payload/output/rgb"},
            },
        ],
    }


@pytest.fixture
def twin_definition(definition_data: dict[str, Any]) -> TwinDefinition:
    return TwinDefinition.model_validate(deepcopy(definition_data))
