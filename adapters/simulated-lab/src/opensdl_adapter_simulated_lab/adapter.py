from __future__ import annotations

import math
import random
from typing import Any

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
from opensdl_simulation import FaultPlan, SimulationState

#: Decadic absorbance of each dye stock at the colorimeter's three channels, per unit of well
#: volume, at the reference fill depth below. The off-diagonal terms are the point: an ideal cyan
#: would absorb red alone, and a real one does not. These unwanted absorptions are why subtractive
#: primaries do not compose linearly in sRGB, why the printing industry needs a fourth ink to hit
#: a neutral black, and why recovering a recipe from a color is worth searching for rather than
#: solving in closed form. The values are representative of aqueous food-safe dyes; they are a
#: plausible instrument, not a calibration of a real one.
DYE_ABSORBANCE: dict[str, tuple[float, float, float]] = {
    #          red     green   blue
    "cyan": (2.60, 0.55, 0.20),
    "magenta": (0.35, 2.40, 0.55),
    "yellow": (0.10, 0.30, 2.75),
}

#: The fill depth the absorbances above are quoted at. A plate read from above is a cuvette whose
#: path length is however deep the operator filled it, so the same recipe in a fuller well reads
#: darker. Beer's law makes that proportionality exact, and carrying it here keeps well volume an
#: experimental variable rather than a constant the model quietly ignores.
REFERENCE_WELL_VOLUME_UL = 200.0

#: Every capability below acts on a dictionary in this process. Nothing is aspirated, moved, or
#: heated, so an abandoned wait leaves no equipment in an unknown state and repeating the call
#: costs nothing. That is why these are `REPEATABLE`, and it is the *only* reason: an adapter
#: driving the same semantic operations on real hardware would declare `NOT_REPEATABLE` for
#: `sim.mix_color` and at most `REPEATABLE_IF_NOT_DISPATCHED` for `sim.move_labware`, because a
#: mixer that may already have dispensed and an arm that may already have moved are not
#: recoverable by trying again. Copy the semantics from this adapter; do not copy this line.
_SIMULATED = RetrySafety.REPEATABLE


class SimulatedLabAdapter(CapabilityAdapter):
    name = "simulated-lab"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        seed = int(self.config.get("seed", 7))
        self.random = random.Random(seed)
        self.state = SimulationState()
        self.faults = FaultPlan(
            latency_seconds=float(self.config.get("latency_seconds", 0.0)),
            fail_on_calls=set(self.config.get("fail_on_calls", [])),
        )

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="sim.mix_color",
                name="Mix color sample",
                description="Create a virtual two-component color mixture.",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["sample_id", "red_fraction", "blue_fraction", "total_mass_g"],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "red_fraction": {"type": "number", "minimum": 0, "maximum": 1},
                        "blue_fraction": {"type": "number", "minimum": 0, "maximum": 1},
                        "total_mass_g": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "sample_id",
                        "red_fraction",
                        "blue_fraction",
                        "total_mass_g",
                        "rgb",
                    ],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "red_fraction": {"type": "number"},
                        "blue_fraction": {"type": "number"},
                        "total_mass_g": {"type": "number", "exclusiveMinimum": 0},
                        "rgb": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-mixer"],
                side_effects=["updates virtual sample state"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
            CapabilityDefinition(
                id="sim.mix_dyes",
                name="Mix dye sample",
                description=(
                    "Create a virtual three-dye subtractive mixture and predict its color."
                ),
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": [
                        "sample_id",
                        "cyan",
                        "magenta",
                        "yellow",
                        "well_volume_ul",
                    ],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "cyan": {"type": "number", "minimum": 0, "maximum": 1},
                        "magenta": {"type": "number", "minimum": 0, "maximum": 1},
                        "yellow": {"type": "number", "minimum": 0, "maximum": 1},
                        "well_volume_ul": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": [
                        "sample_id",
                        "cyan",
                        "magenta",
                        "yellow",
                        "well_volume_ul",
                        "absorbance",
                        "rgb",
                    ],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "cyan": {"type": "number"},
                        "magenta": {"type": "number"},
                        "yellow": {"type": "number"},
                        "well_volume_ul": {"type": "number", "exclusiveMinimum": 0},
                        "absorbance": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "rgb": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-mixer"],
                side_effects=["updates virtual sample state"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
            CapabilityDefinition(
                id="sim.measure_color",
                name="Measure sample color",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["sample_id"],
                    "properties": {"sample_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["sample_id", "rgb", "unit", "simulated"],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "rgb": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "unit": {"type": "string"},
                        "simulated": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-colorimeter"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
            CapabilityDefinition(
                id="sim.measure_mass",
                name="Measure sample mass",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["sample_id"],
                    "properties": {"sample_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["sample_id", "mass", "unit", "simulated"],
                    "properties": {
                        "sample_id": {"type": "string"},
                        "mass": {"type": "number"},
                        "unit": {"type": "string"},
                        "simulated": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-balance"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
            CapabilityDefinition(
                id="sim.move_labware",
                name="Move virtual labware",
                description="Move a virtual labware object between declared locations.",
                executor_type=ExecutorType.ROBOT,
                input_schema={
                    "type": "object",
                    "required": ["labware_id", "source", "destination"],
                    "properties": {
                        "labware_id": {"type": "string"},
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["labware_id", "source", "destination", "simulated"],
                    "properties": {
                        "labware_id": {"type": "string"},
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                        "simulated": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-robot"],
                side_effects=["updates virtual labware location"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
            CapabilityDefinition(
                id="sim.locate_labware",
                name="Locate virtual labware",
                executor_type=ExecutorType.SIMULATOR,
                input_schema={
                    "type": "object",
                    "required": ["labware_id"],
                    "properties": {"labware_id": {"type": "string"}},
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "required": ["labware_id", "location", "simulated"],
                    "properties": {
                        "labware_id": {"type": "string"},
                        "location": {"type": "string"},
                        "simulated": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                },
                risk_class=RiskClass.R0,
                required_resources=["virtual-robot"],
                simulator_available=True,
                retry_safety=_SIMULATED,
            ),
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        await self.faults.before_call()
        started = utc_now()
        if request.capability_id == "sim.mix_color":
            output = self._mix(request.inputs)
        elif request.capability_id == "sim.mix_dyes":
            output = self._mix_dyes(request.inputs)
        elif request.capability_id == "sim.measure_color":
            output = self._measure_color(request.inputs)
        elif request.capability_id == "sim.measure_mass":
            output = self._measure_mass(request.inputs)
        elif request.capability_id == "sim.move_labware":
            output = self._move_labware(request.inputs)
        elif request.capability_id == "sim.locate_labware":
            output = self._locate_labware(request.inputs)
        else:
            raise LookupError(request.capability_id)
        return ExecutionResult(
            request_id=request.request_id,
            output=output,
            started_at=started,
            completed_at=utc_now(),
            metadata={"adapter": self.name, "simulated": True},
        )

    def _mix(self, inputs: dict[str, Any]) -> dict[str, Any]:
        sample_id = str(inputs["sample_id"])
        red = float(inputs["red_fraction"])
        blue = float(inputs["blue_fraction"])
        mass = float(inputs["total_mass_g"])
        if red < 0 or blue < 0 or red + blue <= 0:
            raise ValueError("color fractions must be non-negative and have a positive sum")
        total = red + blue
        red /= total
        blue /= total
        rgb = [round(255 * red, 6), 0.0, round(255 * blue, 6)]
        sample = {
            "sample_id": sample_id,
            "red_fraction": red,
            "blue_fraction": blue,
            "total_mass_g": mass,
            "rgb": rgb,
        }
        self.state.set(f"sample:{sample_id}", sample)
        return sample

    def _mix_dyes(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Combine three dye stocks with water and predict the resulting color.

        Each fraction is the share of the well drawn from that dye stock; water makes up the
        remainder, so the three together cannot exceed one. Absorbances add, transmittance is
        their exponential, and the channel transmittances are the sRGB triple a colorimeter
        looking down the well would report.
        """
        sample_id = str(inputs["sample_id"])
        fractions = {name: float(inputs[name]) for name in DYE_ABSORBANCE}
        volume = float(inputs["well_volume_ul"])
        if volume <= 0:
            raise ValueError("well volume must be positive")
        negative = sorted(name for name, value in fractions.items() if value < 0)
        if negative:
            raise ValueError(f"dye fractions must be non-negative: {', '.join(negative)}")
        total = sum(fractions.values())
        if total > 1:
            raise ValueError(
                f"dye fractions total {total:.6g} of the well volume; water cannot be negative"
            )
        # Beer's law: absorbance is linear in both concentration and path length, and the path
        # length is the fill depth.
        depth = volume / REFERENCE_WELL_VOLUME_UL
        absorbance = [
            sum(fractions[dye] * DYE_ABSORBANCE[dye][channel] for dye in DYE_ABSORBANCE) * depth
            for channel in range(3)
        ]
        rgb = [round(255.0 * math.exp(-value), 6) for value in absorbance]
        sample = {
            "sample_id": sample_id,
            **{name: fractions[name] for name in DYE_ABSORBANCE},
            "well_volume_ul": volume,
            "absorbance": [round(value, 6) for value in absorbance],
            "rgb": rgb,
        }
        self.state.set(f"sample:{sample_id}", sample)
        return sample

    def _measure_color(self, inputs: dict[str, Any]) -> dict[str, Any]:
        sample_id = str(inputs["sample_id"])
        sample = self.state.get(f"sample:{sample_id}")
        if sample is None:
            raise LookupError(f"unknown sample: {sample_id}")
        noise = float(self.config.get("color_noise", 0.0))
        measured = [
            max(0.0, min(255.0, value + self.random.gauss(0, noise))) for value in sample["rgb"]
        ]
        return {"sample_id": sample_id, "rgb": measured, "unit": "sRGB-8bit", "simulated": True}

    def _measure_mass(self, inputs: dict[str, Any]) -> dict[str, Any]:
        sample_id = str(inputs["sample_id"])
        sample = self.state.get(f"sample:{sample_id}")
        if sample is None:
            raise LookupError(f"unknown sample: {sample_id}")
        if "total_mass_g" not in sample:
            # A dye mixture is dispensed by volume, so nothing recorded a mass for it. Saying so
            # is better than reporting a weight this laboratory never established.
            raise LookupError(f"sample {sample_id} was prepared by volume and has no recorded mass")
        noise = float(self.config.get("mass_noise_g", 0.0))
        return {
            "sample_id": sample_id,
            "mass": sample["total_mass_g"] + self.random.gauss(0, noise),
            "unit": "g",
            "simulated": True,
        }

    def _move_labware(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        source = str(inputs["source"])
        destination = str(inputs["destination"])
        state_key = f"labware:{labware_id}:location"
        current = self.state.get(state_key)
        if current is not None and current != source:
            raise ValueError(f"labware {labware_id} is at {current}, not requested source {source}")
        self.state.set(state_key, destination)
        return {
            "labware_id": labware_id,
            "source": source,
            "destination": destination,
            "simulated": True,
        }

    def _locate_labware(self, inputs: dict[str, Any]) -> dict[str, Any]:
        labware_id = str(inputs["labware_id"])
        location = self.state.get(f"labware:{labware_id}:location")
        if location is None:
            raise LookupError(f"unknown labware: {labware_id}")
        return {
            "labware_id": labware_id,
            "location": str(location),
            "simulated": True,
        }

    def conformance_cases(self) -> list[ExecutionRequest]:
        return [
            ExecutionRequest(
                capability_id="sim.mix_color",
                inputs={
                    "sample_id": "conformance",
                    "red_fraction": 0.5,
                    "blue_fraction": 0.5,
                    "total_mass_g": 1.0,
                },
            ),
            ExecutionRequest(
                capability_id="sim.mix_dyes",
                inputs={
                    "sample_id": "conformance-dyes",
                    "cyan": 0.2,
                    "magenta": 0.1,
                    "yellow": 0.4,
                    "well_volume_ul": 200.0,
                },
            ),
            ExecutionRequest(
                capability_id="sim.measure_color",
                inputs={"sample_id": "conformance"},
            ),
            ExecutionRequest(
                capability_id="sim.measure_mass",
                inputs={"sample_id": "conformance"},
            ),
            ExecutionRequest(
                capability_id="sim.move_labware",
                inputs={
                    "labware_id": "plate-1",
                    "source": "deck-a",
                    "destination": "deck-b",
                },
            ),
            ExecutionRequest(
                capability_id="sim.locate_labware",
                inputs={"labware_id": "plate-1"},
            ),
        ]
