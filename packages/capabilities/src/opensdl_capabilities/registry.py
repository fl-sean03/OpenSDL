from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opensdl_core import CapabilityDefinition, CapabilityNotFoundError, ExecutionRequest

from .adapter import CapabilityAdapter
from .execution import AdapterCall, AdapterExecutor


class CapabilityRegistry:
    """Which adapter provides which capability, and the context that adapter's code runs in.

    The registry owns the execution context because it already owns the adapter lifecycle: an
    adapter's `start`, `execute`, `health` and `close` have to run on one loop for the adapter to
    be able to hold state across them, and that loop is not the caller's. See `execution.py` for
    why adapter code runs off the calling loop at all.
    """

    def __init__(self, *, executor: AdapterExecutor | None = None) -> None:
        self._adapters: dict[str, CapabilityAdapter] = {}
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._capability_adapter: dict[str, str] = {}
        self._executor = executor or AdapterExecutor()

    def register(self, adapter: CapabilityAdapter) -> None:
        if adapter.name in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.name}")
        definitions = adapter.capability_definitions()
        for definition in definitions:
            if definition.id in self._capabilities:
                owner = self._capability_adapter[definition.id]
                raise ValueError(f"capability {definition.id} already registered by {owner}")
        self._adapters[adapter.name] = adapter
        for definition in definitions:
            self._capabilities[definition.id] = definition
            self._capability_adapter[definition.id] = adapter.name

    def restrict(self, capability_ids: Iterable[str]) -> None:
        """Expose only explicitly bound capabilities while retaining adapter lifecycle."""
        allowed = set(capability_ids)
        unknown = allowed - set(self._capabilities)
        if unknown:
            raise CapabilityNotFoundError(", ".join(sorted(unknown)))
        self._capabilities = {
            capability_id: definition
            for capability_id, definition in self._capabilities.items()
            if capability_id in allowed
        }
        self._capability_adapter = {
            capability_id: adapter_name
            for capability_id, adapter_name in self._capability_adapter.items()
            if capability_id in allowed
        }

    def _unknown(self, capability_id: str) -> CapabilityNotFoundError:
        """A misspelled capability is the commonest authoring mistake, so say what exists.

        The message used to be the identifier alone, which reads as an assertion that
        something is wrong with a name the author already knows they typed.
        """
        available = ", ".join(sorted(self._capabilities)) or "none"
        return CapabilityNotFoundError(
            f"unknown capability {capability_id!r}; this laboratory exposes: {available}"
        )

    def get_adapter(self, capability_id: str) -> CapabilityAdapter:
        try:
            return self._adapters[self._capability_adapter[capability_id]]
        except KeyError as exc:
            raise self._unknown(capability_id) from exc

    def get_definition(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise self._unknown(capability_id) from exc

    def list_capabilities(self) -> list[CapabilityDefinition]:
        return sorted(self._capabilities.values(), key=lambda item: item.id)

    def list_adapters(self) -> list[CapabilityAdapter]:
        return sorted(self._adapters.values(), key=lambda item: item.name)

    def dispatch(self, capability_id: str, request: ExecutionRequest) -> AdapterCall:
        """Hand one execution to the providing adapter and return a handle the caller can drop.

        The handle is what makes a declared timeout binding: waiting on it is bounded even when the
        adapter's `async def` contains a blocking call and never yields. It bounds the wait only.
        """
        return self._executor.dispatch(self.get_adapter(capability_id), request)

    async def health(self, adapter: CapabilityAdapter) -> dict[str, Any]:
        return await self._executor.health(adapter)

    async def start(self) -> None:
        for adapter in self.list_adapters():
            await self._executor.start(adapter)

    async def close(self) -> None:
        try:
            for adapter in reversed(self.list_adapters()):
                await self._executor.close(adapter)
        finally:
            self._executor.shutdown()
