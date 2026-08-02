from __future__ import annotations

from typing import Any

from opensdl_capabilities import CapabilityAdapter
from opensdl_core import (
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    RiskClass,
    utc_now,
)


class HumanTaskAdapter(CapabilityAdapter):
    """Record structured completion evidence for a person-executed task."""

    name = "human-task"

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="human.attest",
                name="Record human task completion",
                description=(
                    "Record who completed a defined laboratory step, its outcome, "
                    "and optional evidence references."
                ),
                executor_type=ExecutorType.HUMAN,
                input_schema={
                    "type": "object",
                    "required": ["instruction", "completed_by", "outcome"],
                    "properties": {
                        "instruction": {"type": "string", "minLength": 1},
                        "completed_by": {"type": "string", "minLength": 1},
                        "outcome": {
                            "type": "string",
                            "enum": ["completed", "not_completed", "deviated"],
                        },
                        "notes": {"type": "string"},
                        "evidence": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "uniqueItems": True,
                        },
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "instruction",
                        "completed_by",
                        "outcome",
                        "notes",
                        "evidence",
                        "recorded_at",
                    ],
                    "properties": {
                        "instruction": {"type": "string"},
                        "completed_by": {"type": "string"},
                        "outcome": {"type": "string"},
                        "notes": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "recorded_at": {"type": "string", "format": "date-time"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R1,
                side_effects=["records a human attestation in run provenance"],
                simulator_available=False,
                tags=["human", "assisted"],
            )
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = utc_now()
        output: dict[str, Any] = {
            "instruction": str(request.inputs["instruction"]),
            "completed_by": str(request.inputs["completed_by"]),
            "outcome": str(request.inputs["outcome"]),
            "notes": str(request.inputs.get("notes", "")),
            "evidence": [str(item) for item in request.inputs.get("evidence", [])],
            "recorded_at": utc_now().isoformat(),
        }
        return ExecutionResult(
            request_id=request.request_id,
            output=output,
            started_at=started,
            completed_at=utc_now(),
            metadata={"adapter": self.name, "attested": True},
        )

    def conformance_cases(self) -> list[ExecutionRequest]:
        return [
            ExecutionRequest(
                capability_id="human.attest",
                operator_id="operator/conformance",
                inputs={
                    "instruction": "Confirm the reference work area is ready.",
                    "completed_by": "operator/conformance",
                    "outcome": "completed",
                    "notes": "Synthetic conformance attestation.",
                    "evidence": ["urn:opensdl:test-evidence"],
                },
            )
        ]
