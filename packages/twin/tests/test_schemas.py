from __future__ import annotations

import json
from pathlib import Path

from opensdl_twin import TWIN_SCHEMAS, generate_twin_json_schemas

CANONICAL_DIRECTORY = Path(__file__).parents[3] / "packages" / "schemas" / "jsonschema"


def test_generator_writes_every_public_twin_contract(tmp_path: Path) -> None:
    written = generate_twin_json_schemas(tmp_path)

    assert sorted(path.name for path in written) == sorted(
        f"{name}.schema.json" for name in TWIN_SCHEMAS
    )
    assert "twin-definition" in TWIN_SCHEMAS
    assert all(path.exists() for path in written)


def test_definition_schema_exports_the_versioned_camel_case_contract(tmp_path: Path) -> None:
    generate_twin_json_schemas(tmp_path)
    schema = json.loads((tmp_path / "twin-definition.schema.json").read_text(encoding="utf-8"))

    assert schema["title"] == "TwinDefinition"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["apiVersion"]["const"] == "opensdl.dev/v0alpha1"
    assert schema["properties"]["kind"]["const"] == "DigitalTwin"
    assert {"coordinateFrame", "projectionRules", "animationTimeline"} <= set(schema["properties"])
    assert set(schema["required"]) == {
        "version",
        "revision",
        "coordinateFrame",
        "scene",
        "entities",
    }
    assert {"CoordinateFrame", "ProjectionRule", "TwinAnchor", "TwinEntity", "TwinScene"} <= set(
        schema["$defs"]
    )


def test_cue_schema_declares_the_timestamp_format(tmp_path: Path) -> None:
    generate_twin_json_schemas(tmp_path)
    schema = json.loads((tmp_path / "twin-cue.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["occurredAt"] == {
        "format": "date-time",
        "title": "Occurredat",
        "type": "string",
    }
    assert "occurredAt" in schema["required"]


def test_generation_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_twin_json_schemas(first)
    generate_twin_json_schemas(second)

    for name in TWIN_SCHEMAS:
        filename = f"{name}.schema.json"
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_committed_schemas_match_generated_output(tmp_path: Path) -> None:
    generate_twin_json_schemas(tmp_path)

    for name in TWIN_SCHEMAS:
        filename = f"{name}.schema.json"
        committed = CANONICAL_DIRECTORY / filename
        assert committed.exists(), f"{filename} is missing from the canonical schema directory"
        assert committed.read_bytes() == (tmp_path / filename).read_bytes()
