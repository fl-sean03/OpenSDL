from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from opensdl_core import CapabilityDefinition, ExecutionRequest, ExecutionResult


class CapabilityAdapter(ABC):
    """Boundary implemented by instruments, robots, compute, humans, and simulators."""

    name: str

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @abstractmethod
    def capability_definitions(self) -> list[CapabilityDefinition]:
        raise NotImplementedError

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy", "adapter": self.name}

    async def abort(self, request_id: str) -> bool:
        return False

    def conformance_cases(self) -> list[ExecutionRequest]:
        return []
