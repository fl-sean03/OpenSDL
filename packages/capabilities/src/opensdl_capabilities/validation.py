from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from opensdl_core import ValidationError


def validate_schema(schema: dict[str, Any], *, label: str) -> None:
    """Validate that a public capability schema is itself valid JSON Schema."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(f"invalid {label} JSON Schema: {exc.message}") from exc


def validate_instance(instance: Any, schema: dict[str, Any], *, label: str) -> None:
    """Validate one value and return a stable, human-readable contract error."""
    validate_schema(schema, label=label)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    path = ".".join(str(item) for item in error.absolute_path) or "<root>"
    raise ValidationError(f"{label} failed at {path}: {error.message}")
