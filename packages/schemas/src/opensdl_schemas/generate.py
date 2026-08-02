from __future__ import annotations

import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from opensdl_core import (
    ArtifactRecord,
    CampaignDefinition,
    CapabilityDefinition,
    EventRecord,
    ExecutionRequest,
    ExecutionResult,
    Resource,
    RunRecord,
    TaskRecord,
    WorkflowDefinition,
)

from .manifest import LabManifest

SCHEMAS: dict[str, Type[BaseModel]] = {
    "lab-manifest": LabManifest,
    "capability": CapabilityDefinition,
    "workflow": WorkflowDefinition,
    "campaign": CampaignDefinition,
    "resource": Resource,
    "run": RunRecord,
    "task": TaskRecord,
    "event": EventRecord,
    "artifact": ArtifactRecord,
    "execution-request": ExecutionRequest,
    "execution-result": ExecutionResult,
}


def generate_json_schemas(output_dir: str | Path) -> list[Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in SCHEMAS.items():
        path = destination / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written
