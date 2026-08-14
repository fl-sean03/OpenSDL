from __future__ import annotations

import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from opensdl_core import (
    ArtifactRecord,
    Attestation,
    CampaignDefinition,
    CampaignObservation,
    CampaignProblem,
    CapabilityDefinition,
    EventRecord,
    ExecutionRequest,
    ExecutionResult,
    Resource,
    RunRecord,
    Suggestion,
    TaskRecord,
    WorkflowDefinition,
)

from .manifest import LabManifest

#: Every OpenSDL contract that crosses a process boundary, as a language-neutral document.
#:
#: The three campaign entries are the optimizer contract: `CampaignProblem` is what a campaign
#: declares it is searching and is handed to `ConfigurableOptimizer.configure`, `Suggestion` is
#: what an optimizer returns, and `CampaignObservation` is what it is given back and what the
#: campaign records as the iteration it found. Each is also written into the durable event stream.
#:
#: What is deliberately absent: `IterationDecision`, which nothing serialises — the framework
#: writes a `Decision` plus loose keys into `DecisionRecorded` and reads that back, so publishing
#: a schema for a document no writer produces would advertise a contract nobody can hold to.
#: `Objective`, `SearchSpace`, `Parameter` and both constraint types are components rather than
#: documents and appear as `$defs` of the schemas above. `CampaignRecord` and `CampaignResult`
#: live in `opensdl-runtime`, which this package may not import.
SCHEMAS: dict[str, Type[BaseModel]] = {
    "lab-manifest": LabManifest,
    "capability": CapabilityDefinition,
    "workflow": WorkflowDefinition,
    "campaign": CampaignDefinition,
    "campaign-problem": CampaignProblem,
    "campaign-observation": CampaignObservation,
    "suggestion": Suggestion,
    "resource": Resource,
    "run": RunRecord,
    "task": TaskRecord,
    "event": EventRecord,
    "artifact": ArtifactRecord,
    "attestation": Attestation,
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
