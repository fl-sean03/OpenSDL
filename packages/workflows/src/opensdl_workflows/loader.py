from __future__ import annotations

from pathlib import Path

import yaml

from opensdl_core import WorkflowDefinition


def load_workflow(path: str | Path) -> WorkflowDefinition:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("workflow must contain a mapping")
    return WorkflowDefinition.model_validate(data)
