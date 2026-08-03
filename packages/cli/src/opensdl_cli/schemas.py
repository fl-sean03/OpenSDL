from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from opensdl_schemas import generate_json_schemas
from opensdl_twin import generate_twin_json_schemas

SchemaGenerator = Callable[[str | Path], list[Path]]

SCHEMA_GENERATORS: tuple[SchemaGenerator, ...] = (
    generate_json_schemas,
    generate_twin_json_schemas,
)


def generate_all_json_schemas(output_dir: str | Path) -> list[Path]:
    """Write every public OpenSDL contract into one schema directory.

    Each package generates the contracts it owns, because ``opensdl_schemas`` and
    ``opensdl_twin`` may only import ``opensdl_core`` and cannot see each other. This
    module is the single place that composes them, so the CLI command and the
    repository script cannot drift apart on what "every public schema" means.
    """

    destination = Path(output_dir)
    return [path for generate in SCHEMA_GENERATORS for path in generate(destination)]
