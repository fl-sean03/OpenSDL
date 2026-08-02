from __future__ import annotations

import re
from typing import Any

from opensdl_core import ValidationError

REFERENCE = re.compile(r"^\$\{(?P<path>[a-zA-Z0-9_.-]+)\}$")


def resolve_value(value: Any, workflow_inputs: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str):
        match = REFERENCE.fullmatch(value)
        if not match:
            return value
        path = match.group("path").split(".")
        if path[0] == "inputs" and len(path) >= 2:
            return _walk(workflow_inputs, path[1:])
        if path[0] == "steps" and len(path) >= 3 and path[2] == "output":
            try:
                if len(path) == 3:
                    return step_outputs[path[1]]
                return _walk(step_outputs[path[1]], path[3:])
            except KeyError as exc:
                raise ValidationError(f"unresolved workflow reference: {value}") from exc
        raise ValidationError(f"unsupported workflow reference: {value}")
    if isinstance(value, list):
        return [resolve_value(item, workflow_inputs, step_outputs) for item in value]
    if isinstance(value, dict):
        return {key: resolve_value(item, workflow_inputs, step_outputs) for key, item in value.items()}
    return value


def resolve_mapping(mapping: dict[str, Any], workflow_inputs: dict[str, Any], step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {key: resolve_value(value, workflow_inputs, step_outputs) for key, value in mapping.items()}


def _walk(value: Any, segments: list[str]) -> Any:
    current = value
    for segment in segments:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            current = current[int(segment)]
        else:
            raise ValidationError(f"cannot resolve segment {segment!r} in reference")
    return current
