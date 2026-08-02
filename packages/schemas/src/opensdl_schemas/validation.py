from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from opensdl_core import WorkflowDefinition

from .manifest import LabManifest, load_manifest


def validate_manifest_file(path: str | Path) -> LabManifest:
    return load_manifest(path)


def validate_workflow_file(path: str | Path) -> WorkflowDefinition:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(data)


def validate_against_json_schema(instance: Any, schema_path: str | Path) -> None:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(instance=instance, schema=schema)
