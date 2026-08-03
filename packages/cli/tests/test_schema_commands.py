from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from opensdl_cli.main import app
from opensdl_cli.schemas import generate_all_json_schemas
from opensdl_schemas import SCHEMAS
from opensdl_twin import TWIN_SCHEMAS

CANONICAL_DIRECTORY = Path(__file__).parents[3] / "packages" / "schemas" / "jsonschema"
EXPECTED_FILENAMES = {f"{name}.schema.json" for name in (*SCHEMAS, *TWIN_SCHEMAS)}


def generate_through_cli(destination: Path) -> set[str]:
    result = CliRunner().invoke(app, ["schema", "generate", "--destination", str(destination)])

    assert result.exit_code == 0, result.output
    assert f"Generated {len(EXPECTED_FILENAMES)} schemas" in result.stdout
    return {path.name for path in destination.glob("*.schema.json")}


def test_schema_generate_writes_every_public_contract(tmp_path: Path) -> None:
    assert generate_through_cli(tmp_path) == EXPECTED_FILENAMES


def test_schema_generate_includes_the_twin_contracts(tmp_path: Path) -> None:
    written = generate_through_cli(tmp_path)

    assert {"twin-definition.schema.json", "twin-cue.schema.json"} <= written


def test_schema_generate_matches_the_committed_canonical_directory(tmp_path: Path) -> None:
    written = generate_through_cli(tmp_path)
    committed = {path.name for path in CANONICAL_DIRECTORY.glob("*.schema.json")}

    assert written == committed
    for name in sorted(committed):
        assert (tmp_path / name).read_bytes() == (CANONICAL_DIRECTORY / name).read_bytes()


def test_composed_generation_never_overwrites_a_shared_schema_name(tmp_path: Path) -> None:
    paths = generate_all_json_schemas(tmp_path)

    assert len(paths) == len(set(paths)) == len(EXPECTED_FILENAMES)
