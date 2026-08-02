from __future__ import annotations

from typing import Protocol, runtime_checkable

from opensdl_core import CapabilityDefinition

from .engine import PolicyDecision


@runtime_checkable
class PolicyEvaluator(Protocol):
    """Authorization boundary consumed by the execution runtime."""

    version: str

    def evaluate(
        self,
        capability: CapabilityDefinition,
        operator_id: str,
        environment: str,
    ) -> PolicyDecision: ...
