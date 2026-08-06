from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from opensdl_core import CapabilityDefinition, ExecutionRequest, ExecutionResult, OpenSDLError


class NotDispatchedError(OpenSDLError):
    """The command never reached the equipment, so nothing physical can have happened.

    This is the one thing an adapter can tell the runtime that makes repeating an operation safe
    when its declared `retry_safety` is `REPEATABLE_IF_NOT_DISPATCHED`. The adapter is the only
    party in a position to know it: a refused connection, a rejected handshake, a request that
    never left the client. Raise it only for those. Anything after the command is on the wire —
    a reset connection, a vendor timeout, an unparseable reply — is not this, because the
    instrument may already have acted on what it received. `SAFETY.md` separates command dispatch
    from physical acknowledgement for exactly this reason, and an API failure is no more proof
    that nothing happened than an API success is proof that something did.

    A wrong claim here is not caught by anything: it authorizes a repeat of a physical action. If
    the adapter is unsure, it raises an ordinary error and the operation is not repeated.
    """


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
