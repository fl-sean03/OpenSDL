from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass, field
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


_LABWARE_ID = {"type": "string", "minLength": 1}
_LOCATIONS = ("input", "dispenser", "mixer", "characterizer", "output")
_LOCATION = {"type": "string", "enum": list(_LOCATIONS)}
_WELL_COUNT = 96
_ADDITION = {
    "type": "object",
    "required": ["material_id", "volume_per_well_ul"],
    "properties": {
        "material_id": {"type": "string", "minLength": 1},
        "volume_per_well_ul": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": False,
}
_ADDITIONS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 16,
    "items": _ADDITION,
}
_SPEED_RPM = {
    "type": "number",
    "exclusiveMinimum": 0,
    "maximum": 5000,
}
_DURATION_SECONDS = {
    "type": "number",
    "exclusiveMinimum": 0,
    "maximum": 3600,
}


def build_capability_definitions() -> list[CapabilityDefinition]:
    """Return fresh semantic contracts shared by surrogate and physical implementations."""

    return [
        CapabilityDefinition(
            id="cell.transfer_labware",
            version="0.1.0",
            name="Transfer labware",
            description="Transfer one labware item between declared cell locations.",
            executor_type=ExecutorType.ROBOT,
            input_schema={
                "type": "object",
                "required": ["labware_id", "source", "destination"],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "source": _LOCATION,
                    "destination": _LOCATION,
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["labware_id", "source", "destination"],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "source": _LOCATION,
                    "destination": _LOCATION,
                },
                "additionalProperties": False,
            },
            risk_class=RiskClass.R1,
            required_resources=["cell-transport"],
            side_effects=["changes declared labware location"],
            timeout_seconds=30,
            max_retries=0,
            supports_cancellation=False,
            simulator_available=True,
            tags=["cell", "labware", "transport"],
        ),
        CapabilityDefinition(
            id="cell.dispense",
            version="0.1.0",
            name="Dispense formulation",
            description=("Add declared per-well material volumes across one 96-well plate."),
            executor_type=ExecutorType.INSTRUMENT,
            input_schema={
                "type": "object",
                "required": ["labware_id", "additions"],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "additions": _ADDITIONS,
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "labware_id",
                    "dispensed",
                    "well_count",
                    "volume_per_well_ul",
                    "aggregate_volume_ul",
                ],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "dispensed": _ADDITIONS,
                    "well_count": {"type": "integer", "const": _WELL_COUNT},
                    "volume_per_well_ul": {"type": "number", "exclusiveMinimum": 0},
                    "aggregate_volume_ul": {"type": "number", "exclusiveMinimum": 0},
                },
                "additionalProperties": False,
            },
            risk_class=RiskClass.R1,
            required_resources=["cell-dispenser"],
            side_effects=["adds declared materials to labware contents"],
            timeout_seconds=60,
            max_retries=0,
            supports_cancellation=False,
            simulator_available=True,
            tags=["cell", "liquid-handling", "formulation"],
        ),
        CapabilityDefinition(
            id="cell.mix",
            version="0.1.0",
            name="Mix formulation",
            description=(
                "Mix the current contents of labware using declared speed and duration set points."
            ),
            executor_type=ExecutorType.INSTRUMENT,
            input_schema={
                "type": "object",
                "required": ["labware_id", "speed_rpm", "duration_seconds"],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "speed_rpm": _SPEED_RPM,
                    "duration_seconds": _DURATION_SECONDS,
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "labware_id",
                    "mixture_id",
                    "speed_rpm",
                    "duration_seconds",
                    "well_count",
                    "volume_per_well_ul",
                    "aggregate_volume_ul",
                    "mixed",
                ],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "mixture_id": {"type": "string", "minLength": 1},
                    "speed_rpm": _SPEED_RPM,
                    "duration_seconds": _DURATION_SECONDS,
                    "well_count": {"type": "integer", "const": _WELL_COUNT},
                    "volume_per_well_ul": {"type": "number", "exclusiveMinimum": 0},
                    "aggregate_volume_ul": {"type": "number", "exclusiveMinimum": 0},
                    "mixed": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            risk_class=RiskClass.R1,
            required_resources=["cell-mixer"],
            side_effects=["changes labware contents through mixing"],
            timeout_seconds=90,
            max_retries=0,
            supports_cancellation=False,
            simulator_available=True,
            tags=["cell", "mixing", "formulation"],
        ),
        CapabilityDefinition(
            id="cell.characterize",
            version="0.1.0",
            name="Characterize formulation",
            description="Measure the normalized response of a mixed formulation.",
            executor_type=ExecutorType.INSTRUMENT,
            input_schema={
                "type": "object",
                "required": ["labware_id", "method"],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "method": {"type": "string", "enum": ["normalized-response"]},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": [
                    "labware_id",
                    "mixture_id",
                    "method",
                    "value",
                    "unit",
                    "quality",
                ],
                "properties": {
                    "labware_id": _LABWARE_ID,
                    "mixture_id": {"type": "string", "minLength": 1},
                    "method": {"type": "string", "enum": ["normalized-response"]},
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "unit": {"type": "string", "enum": ["1"]},
                    "quality": {"type": "string", "enum": ["ok"]},
                },
                "additionalProperties": False,
            },
            risk_class=RiskClass.R0,
            required_resources=["cell-characterizer"],
            side_effects=["records a characterization result"],
            timeout_seconds=60,
            max_retries=0,
            supports_cancellation=False,
            simulator_available=True,
            tags=["cell", "characterization", "measurement"],
        ),
    ]


@dataclass
class _LabwareState:
    location: str | None = None
    contents_per_well_ul: dict[str, float] = field(default_factory=dict)
    mix_revision: int = 0
    mixture_id: str | None = None
    last_characterization: dict[str, Any] | None = None


class CellSurrogateAdapter(CapabilityAdapter):
    """Deterministic, stateful surrogate for one linear laboratory cell."""

    name = "cell-surrogate"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._latency_seconds = float(self.config.get("latency_seconds", 0.0))
        if self._latency_seconds < 0:
            raise ValueError("latency_seconds must be non-negative")

        configured_stations = self.config.get("stations", {})
        if not isinstance(configured_stations, dict):
            raise TypeError("stations must be a mapping")
        defaults = {
            "dispenser": "dispenser",
            "mixer": "mixer",
            "characterizer": "characterizer",
        }
        self._stations = {
            key: str(configured_stations.get(key, default)) for key, default in defaults.items()
        }
        if any(not value.strip() for value in self._stations.values()):
            raise ValueError("station locations cannot be blank")

        configured_responses = self.config.get("material_responses", {})
        if not isinstance(configured_responses, dict):
            raise TypeError("material_responses must be a mapping")
        self._material_responses: dict[str, float] = {}
        for material_id, response in configured_responses.items():
            value = float(response)
            if not 0 <= value <= 1:
                raise ValueError("material response values must be between 0 and 1")
            self._material_responses[str(material_id)] = value

        self._labware: dict[str, _LabwareState] = {}
        self._revision = 0
        self._lock = asyncio.Lock()
        self._closed = False

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return build_capability_definitions()

    async def start(self) -> None:
        self._closed = False

    async def close(self) -> None:
        async with self._lock:
            self._closed = True

    async def health(self) -> dict[str, Any]:
        return {
            "status": "closed" if self._closed else "healthy",
            "adapter": self.name,
            "execution_mode": "surrogate",
            "state_revision": self._revision,
        }

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = utc_now()
        if self._closed:
            raise RuntimeError("cell surrogate is closed")
        if self._latency_seconds:
            await asyncio.sleep(self._latency_seconds)

        async with self._lock:
            if self._closed:
                raise RuntimeError("cell surrogate is closed")
            if request.capability_id == "cell.transfer_labware":
                output = self._transfer_labware(request.inputs)
            elif request.capability_id == "cell.dispense":
                output = self._dispense(request.inputs)
            elif request.capability_id == "cell.mix":
                output = self._mix(request.inputs)
            elif request.capability_id == "cell.characterize":
                output = self._characterize(request.inputs)
            else:
                raise LookupError(request.capability_id)
            self._revision += 1
            revision = self._revision

        return ExecutionResult(
            request_id=request.request_id,
            output=output,
            started_at=started,
            completed_at=utc_now(),
            metadata={
                "adapter": self.name,
                "execution_mode": "surrogate",
                "deterministic": True,
                "state_revision": revision,
            },
        )

    def _transfer_labware(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        source = str(inputs["source"])
        destination = str(inputs["destination"])
        unknown = {source, destination} - set(_LOCATIONS)
        if unknown:
            raise ValueError(f"unknown cell location: {sorted(unknown)[0]}")
        if source == destination:
            raise ValueError("source and destination must differ")

        state = self._labware.setdefault(labware_id, _LabwareState(location=source))
        if state.location != source:
            raise ValueError(
                f"labware {labware_id} is at {state.location}, not requested source {source}"
            )
        state.location = destination
        return {
            "labware_id": labware_id,
            "source": source,
            "destination": destination,
        }

    def _dispense(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        state = self._require_location(labware_id, self._stations["dispenser"])
        additions = [
            {
                "material_id": str(item["material_id"]),
                "volume_per_well_ul": float(item["volume_per_well_ul"]),
            }
            for item in inputs["additions"]
        ]
        if not additions:
            raise ValueError("at least one addition is required")
        for addition in additions:
            material_id = addition["material_id"]
            volume_per_well_ul = addition["volume_per_well_ul"]
            if not material_id:
                raise ValueError("material_id cannot be blank")
            if volume_per_well_ul <= 0:
                raise ValueError("dispense volumes must be positive")
            state.contents_per_well_ul[material_id] = (
                state.contents_per_well_ul.get(material_id, 0.0) + volume_per_well_ul
            )

        state.mixture_id = None
        state.last_characterization = None
        return {
            "labware_id": labware_id,
            "dispensed": additions,
            "well_count": _WELL_COUNT,
            "volume_per_well_ul": self._volume_per_well(state),
            "aggregate_volume_ul": self._aggregate_volume(state),
        }

    def _mix(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        state = self._require_location(labware_id, self._stations["mixer"])
        if not state.contents_per_well_ul:
            raise ValueError(f"labware {labware_id} has no contents to mix")
        speed_rpm = float(inputs["speed_rpm"])
        duration_seconds = float(inputs["duration_seconds"])
        if not 0 < speed_rpm <= 5000:
            raise ValueError("speed_rpm must be greater than 0 and at most 5000")
        if not 0 < duration_seconds <= 3600:
            raise ValueError("duration_seconds must be greater than 0 and at most 3600")

        state.mix_revision += 1
        signature_payload = {
            "labware_id": labware_id,
            "contents_per_well_ul": sorted(state.contents_per_well_ul.items()),
            "speed_rpm": speed_rpm,
            "duration_seconds": duration_seconds,
            "mix_revision": state.mix_revision,
        }
        signature = hashlib.sha256(
            json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        state.mixture_id = f"mixture-{signature}"
        state.last_characterization = None
        return {
            "labware_id": labware_id,
            "mixture_id": state.mixture_id,
            "speed_rpm": speed_rpm,
            "duration_seconds": duration_seconds,
            "well_count": _WELL_COUNT,
            "volume_per_well_ul": self._volume_per_well(state),
            "aggregate_volume_ul": self._aggregate_volume(state),
            "mixed": True,
        }

    def _characterize(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        state = self._require_location(labware_id, self._stations["characterizer"])
        method = str(inputs["method"])
        if method != "normalized-response":
            raise ValueError(f"unsupported characterization method: {method}")
        if state.mixture_id is None:
            raise ValueError(f"labware {labware_id} must be mixed before characterization")

        volume_per_well_ul = self._volume_per_well(state)
        weighted_response = (
            math.fsum(
                material_volume * self._response_for(material_id)
                for material_id, material_volume in sorted(state.contents_per_well_ul.items())
            )
            / volume_per_well_ul
        )
        output = {
            "labware_id": labware_id,
            "mixture_id": state.mixture_id,
            "method": method,
            "value": round(weighted_response, 6),
            "unit": "1",
            "quality": "ok",
        }
        state.last_characterization = dict(output)
        return output

    def _require_location(self, labware_id: str, expected: str) -> _LabwareState:
        try:
            state = self._labware[labware_id]
        except KeyError as exc:
            raise LookupError(f"unknown labware: {labware_id}") from exc
        if state.location != expected:
            raise ValueError(f"labware {labware_id} is at {state.location}, expected {expected}")
        return state

    @staticmethod
    def _volume_per_well(state: _LabwareState) -> float:
        return round(math.fsum(state.contents_per_well_ul.values()), 6)

    @classmethod
    def _aggregate_volume(cls, state: _LabwareState) -> float:
        return round(cls._volume_per_well(state) * _WELL_COUNT, 6)

    def _response_for(self, material_id: str) -> float:
        configured = self._material_responses.get(material_id)
        if configured is not None:
            return configured
        digest = hashlib.sha256(material_id.encode()).digest()
        return int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)

    def snapshot(self) -> dict[str, Any]:
        """Return a stable copy of surrogate state for tests and local inspection."""

        return {
            "revision": self._revision,
            "labware": {
                labware_id: {
                    "location": state.location,
                    "contents_per_well_ul": dict(sorted(state.contents_per_well_ul.items())),
                    "mix_revision": state.mix_revision,
                    "mixture_id": state.mixture_id,
                    "last_characterization": (
                        dict(state.last_characterization)
                        if state.last_characterization is not None
                        else None
                    ),
                }
                for labware_id, state in sorted(self._labware.items())
            },
        }

    def conformance_cases(self) -> list[ExecutionRequest]:
        return [
            ExecutionRequest(
                capability_id="cell.transfer_labware",
                inputs={
                    "labware_id": "conformance-plate",
                    "source": "input",
                    "destination": "dispenser",
                },
            ),
            ExecutionRequest(
                capability_id="cell.dispense",
                inputs={
                    "labware_id": "conformance-plate",
                    "additions": [{"material_id": "reference", "volume_per_well_ul": 10.0}],
                },
            ),
            ExecutionRequest(
                capability_id="cell.transfer_labware",
                inputs={
                    "labware_id": "conformance-plate",
                    "source": "dispenser",
                    "destination": "mixer",
                },
            ),
            ExecutionRequest(
                capability_id="cell.mix",
                inputs={
                    "labware_id": "conformance-plate",
                    "speed_rpm": 500.0,
                    "duration_seconds": 10.0,
                },
            ),
            ExecutionRequest(
                capability_id="cell.transfer_labware",
                inputs={
                    "labware_id": "conformance-plate",
                    "source": "mixer",
                    "destination": "characterizer",
                },
            ),
            ExecutionRequest(
                capability_id="cell.characterize",
                inputs={
                    "labware_id": "conformance-plate",
                    "method": "normalized-response",
                },
            ),
        ]
