from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class FaultPlan:
    """Deterministic failure and latency controls for virtual equipment."""

    latency_seconds: float = 0.0
    fail_on_calls: set[int] = field(default_factory=set)
    message: str = "injected simulator failure"
    _calls: int = 0

    async def before_call(self) -> None:
        self._calls += 1
        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)
        if self._calls in self.fail_on_calls:
            raise RuntimeError(self.message)

    @property
    def calls(self) -> int:
        return self._calls
