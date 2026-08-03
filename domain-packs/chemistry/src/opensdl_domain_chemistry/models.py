from __future__ import annotations
from typing import Any
from pydantic import Field
from opensdl_core import OpenSDLModel, Quantity


class Chemical(OpenSDLModel):
    id: str
    name: str
    identifiers: dict[str, str] = Field(default_factory=dict)
    hazards: list[str] = Field(default_factory=list)


class Solution(OpenSDLModel):
    id: str
    components: dict[str, Quantity]
    solvent: str | None = None


class Reaction(OpenSDLModel):
    reactants: list[str]
    products: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
