from __future__ import annotations
from typing import Any
from pydantic import Field
from opensdl_core import OpenSDLModel, Quantity


class Apparatus(OpenSDLModel):
    id: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    calibration_ids: list[str] = Field(default_factory=list)


class Scan(OpenSDLModel):
    independent_variable: str
    start: Quantity
    stop: Quantity
    points: int


class Signal(OpenSDLModel):
    name: str
    values: list[float]
    unit: str
    metadata: dict[str, Any] = Field(default_factory=dict)
