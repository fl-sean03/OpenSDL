from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from opensdl_core import CampaignDefinition, WorkflowDefinition

from .manifest import LabManifest, load_manifest


def validate_manifest_file(path: str | Path) -> LabManifest:
    return load_manifest(path)


def validate_workflow_file(path: str | Path) -> WorkflowDefinition:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(data)


def validate_campaign_file(path: str | Path) -> CampaignDefinition:
    """Load a declared campaign, so a search can be reviewed and versioned like a workflow."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return CampaignDefinition.model_validate(data)


def validate_against_json_schema(instance: Any, schema_path: str | Path) -> None:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=instance, schema=schema)
