from __future__ import annotations

from typing import Any

from pydantic import Field

from opensdl_core import OpenSDLModel, Quantity


class Composition(OpenSDLModel):
    components: dict[str, float]
    basis: str = "mole_fraction"


class ProcessStep(OpenSDLModel):
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Specimen(OpenSDLModel):
    id: str
    composition: Composition
    processing_history: list[ProcessStep] = Field(default_factory=list)
    geometry: dict[str, Any] = Field(default_factory=dict)


class PropertyMeasurement(OpenSDLModel):
    property: str
    value: Quantity
    method: str
    conditions: dict[str, Any] = Field(default_factory=dict)
