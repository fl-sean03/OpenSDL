from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from opensdl_schemas import SCHEMAS, validate_against_json_schema

CANONICAL_DIRECTORY = Path(__file__).parents[3] / "packages" / "schemas" / "jsonschema"
TWIN_DEFINITION_SCHEMA = CANONICAL_DIRECTORY / "twin-definition.schema.json"


def twin_definition_document() -> dict[str, Any]:
    return {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "DigitalTwin",
        "version": "0.1.0",
        "revision": "scene-revision-1",
        "coordinateFrame": {"unit": "m", "handedness": "right", "upAxis": "Z"},
        "scene": {"path": "generated/scene.glb", "sha256": "a" * 64},
        "entities": [{"id": "robot", "node": "robot_root", "resources": ["cell.robot"]}],
    }


def test_canonical_directory_holds_every_public_contract() -> None:
    committed = {path.name for path in CANONICAL_DIRECTORY.glob("*.schema.json")}

    assert {f"{name}.schema.json" for name in SCHEMAS} <= committed
    assert "twin-definition.schema.json" in committed


@pytest.mark.parametrize(
    "path",
    sorted(CANONICAL_DIRECTORY.glob("*.schema.json")),
    ids=lambda path: path.name,
)
def test_committed_schema_is_valid_draft_2020_12(path: Path) -> None:
    Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_twin_definition_schema_accepts_a_valid_document() -> None:
    validate_against_json_schema(twin_definition_document(), TWIN_DEFINITION_SCHEMA)


def test_twin_definition_schema_rejects_an_unversioned_document() -> None:
    document = twin_definition_document()
    document["apiVersion"] = "opensdl.dev/v1"

    with pytest.raises(ValidationError):
        validate_against_json_schema(document, TWIN_DEFINITION_SCHEMA)
