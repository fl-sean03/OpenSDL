from __future__ import annotations

from itertools import product
from typing import Any

from opensdl_runtime import CampaignObservation


class GridOptimizer:
    """Deterministic candidate generator suitable for tests and baseline campaigns."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        if "candidates" in config:
            self.candidates = [dict(item) for item in config["candidates"]]
        else:
            parameters = config.get("parameters", {})
            names = list(parameters)
            self.candidates = [dict(zip(names, values, strict=True)) for values in product(*(parameters[name] for name in names))]

    def suggest(self, history: list[CampaignObservation]) -> dict[str, Any] | None:
        tried = [item.candidate for item in history]
        for candidate in self.candidates:
            if candidate not in tried:
                return dict(candidate)
        return None

    def observe(self, observation: CampaignObservation) -> None:
        return None
