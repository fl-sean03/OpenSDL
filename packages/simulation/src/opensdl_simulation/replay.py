from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from opensdl_capabilities import CapabilityAdapter
from opensdl_core import CapabilityDefinition, ExecutionRequest, ExecutionResult


class ReplayAdapter(CapabilityAdapter):
    """Returns previously captured results in request order."""

    name = "replay"

    def __init__(
        self,
        definitions: list[CapabilityDefinition],
        results: Iterable[tuple[str, ExecutionResult]],
    ) -> None:
        super().__init__({})
        self._definitions = definitions
        self._results: dict[str, deque[ExecutionResult]] = defaultdict(deque)
        for capability_id, result in results:
            self._results[capability_id].append(result)

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return self._definitions

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self._results[request.capability_id]:
            raise LookupError(f"no replay result for {request.capability_id}")
        captured = self._results[request.capability_id].popleft()
        return captured.model_copy(update={"request_id": request.request_id})
