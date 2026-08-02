from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .adapter import CapabilityAdapter
from .validation import validate_instance, validate_schema


class ConformanceReport(BaseModel):
    adapter: str
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)


async def run_adapter_conformance(adapter: CapabilityAdapter) -> ConformanceReport:
    """Exercise the minimum adapter contract without hiding extension failures."""
    checks: list[dict[str, Any]] = []
    definitions = adapter.capability_definitions()
    definition_by_id = {item.id: item for item in definitions}

    checks.append(
        {
            "name": "capability definitions present",
            "passed": bool(definitions),
        }
    )
    checks.append(
        {
            "name": "unique capability identifiers",
            "passed": len(definition_by_id) == len(definitions),
        }
    )

    for definition in definitions:
        try:
            validate_schema(definition.input_schema, label=f"{definition.id} input")
            validate_schema(definition.output_schema, label=f"{definition.id} output")
            checks.append(
                {
                    "name": f"schemas {definition.id}",
                    "passed": True,
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": f"schemas {definition.id}",
                    "passed": False,
                    "error": str(exc),
                }
            )

    try:
        health = await adapter.health()
        checks.append(
            {
                "name": "health",
                "passed": health.get("status") == "healthy",
                "details": health,
            }
        )
    except Exception as exc:
        checks.append({"name": "health", "passed": False, "error": str(exc)})

    cases = adapter.conformance_cases()
    covered = {request.capability_id for request in cases}
    missing = sorted(set(definition_by_id) - covered)
    checks.append(
        {
            "name": "conformance case coverage",
            "passed": not missing,
            "missing": missing,
        }
    )

    for request in cases:
        definition = definition_by_id.get(request.capability_id)
        if definition is None:
            checks.append(
                {
                    "name": f"execute {request.capability_id}",
                    "passed": False,
                    "error": "case references an undeclared capability",
                }
            )
            continue
        try:
            validate_instance(
                request.inputs,
                definition.input_schema,
                label=f"{request.capability_id} input",
            )
            result = await adapter.execute(request)
            validate_instance(
                result.output,
                definition.output_schema,
                label=f"{request.capability_id} output",
            )
            checks.append(
                {
                    "name": f"execute {request.capability_id}",
                    "passed": result.request_id == request.request_id,
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": f"execute {request.capability_id}",
                    "passed": False,
                    "error": str(exc),
                }
            )

    return ConformanceReport(
        adapter=adapter.name,
        passed=all(check["passed"] for check in checks),
        checks=checks,
    )
