from __future__ import annotations

import math
import statistics

from opensdl_capabilities import CapabilityAdapter
from opensdl_core import (
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
    RetrySafety,
    RiskClass,
    utc_now,
)


_NUMBER_ARRAY = {
    "type": "array",
    "items": {"type": "number"},
}

#: These are pure functions of their inputs, evaluated in this process. There is no equipment to
#: leave in an unknown state, so repeating one after an abandoned wait costs a few microseconds
#: and nothing else. This is the one executor class where `REPEATABLE` needs no qualification.
_RETRY_SAFETY = RetrySafety.REPEATABLE


class LocalComputeAdapter(CapabilityAdapter):
    name = "local-compute"

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="compute.euclidean_distance",
                name="Euclidean distance",
                executor_type=ExecutorType.COMPUTE,
                input_schema={
                    "type": "object",
                    "required": ["a", "b"],
                    "properties": {"a": _NUMBER_ARRAY, "b": _NUMBER_ARRAY},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["distance"],
                    "properties": {"distance": {"type": "number", "minimum": 0}},
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                retry_safety=_RETRY_SAFETY,
            ),
            CapabilityDefinition(
                id="compute.summary",
                name="Summary statistics",
                executor_type=ExecutorType.COMPUTE,
                input_schema={
                    "type": "object",
                    "required": ["values"],
                    "properties": {
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 1,
                        }
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["count", "mean", "min", "max"],
                    "properties": {
                        "count": {"type": "integer", "minimum": 1},
                        "mean": {"type": "number"},
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                retry_safety=_RETRY_SAFETY,
            ),
            CapabilityDefinition(
                id="compute.quadratic",
                name="Evaluate quadratic",
                executor_type=ExecutorType.COMPUTE,
                input_schema={
                    "type": "object",
                    "required": ["x", "a", "b", "c"],
                    "properties": {
                        "x": {"type": "number"},
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                        "c": {"type": "number"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "number"}},
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                retry_safety=_RETRY_SAFETY,
            ),
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = utc_now()
        if request.capability_id == "compute.euclidean_distance":
            a = [float(value) for value in request.inputs["a"]]
            b = [float(value) for value in request.inputs["b"]]
            if len(a) != len(b):
                raise ValueError("vectors must have equal length")
            output = {"distance": math.dist(a, b)}
        elif request.capability_id == "compute.summary":
            values = [float(value) for value in request.inputs["values"]]
            if not values:
                raise ValueError("values cannot be empty")
            output = {
                "count": len(values),
                "mean": statistics.fmean(values),
                "min": min(values),
                "max": max(values),
            }
        elif request.capability_id == "compute.quadratic":
            x = float(request.inputs["x"])
            output = {
                "value": (
                    float(request.inputs["a"]) * x * x
                    + float(request.inputs["b"]) * x
                    + float(request.inputs["c"])
                )
            }
        else:
            raise LookupError(request.capability_id)
        return ExecutionResult(
            request_id=request.request_id,
            output=output,
            started_at=started,
            completed_at=utc_now(),
            metadata={"adapter": self.name},
        )

    def conformance_cases(self) -> list[ExecutionRequest]:
        return [
            ExecutionRequest(
                capability_id="compute.euclidean_distance",
                inputs={"a": [0, 0], "b": [3, 4]},
            ),
            ExecutionRequest(
                capability_id="compute.summary",
                inputs={"values": [1, 2, 3]},
            ),
            ExecutionRequest(
                capability_id="compute.quadratic",
                inputs={"x": 2, "a": 1, "b": 0, "c": 0},
            ),
        ]
