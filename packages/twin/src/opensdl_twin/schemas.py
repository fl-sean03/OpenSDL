from __future__ import annotations

import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from .models import TwinCue, TwinDefinition

TWIN_SCHEMAS: dict[str, Type[BaseModel]] = {
    "twin-definition": TwinDefinition,
    "twin-cue": TwinCue,
}


def generate_twin_json_schemas(output_dir: str | Path) -> list[Path]:
    """Write the public twin contracts as language-neutral JSON Schema documents.

    The twin package owns this generator because ``opensdl_schemas`` may not import it.
    Callers compose both generators into one canonical schema directory.
    """

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in TWIN_SCHEMAS.items():
        path = destination / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written
