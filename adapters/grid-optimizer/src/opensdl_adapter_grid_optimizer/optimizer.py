"""A deterministic, dependency-free optimizer, and the reference for the plugin contract.

This is not a method anyone should search with. It exists so the closed loop has a baseline that
behaves identically on every machine, and so the optimizer contract has one published
implementation to check itself against.

It implements three of the four optional capabilities and deliberately not the fourth: a grid has
no model, so it has no state worth preserving and does not implement `state()`. That is the point
of the capabilities being optional.
"""

from __future__ import annotations

from itertools import product
from typing import Any

from opensdl_runtime import CampaignObservation, CampaignProblem, Suggestion


class GridOptimizer:
    """Deterministic candidate generator suitable for tests and baseline campaigns."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        if "candidates" in config:
            self.candidates = [dict(item) for item in config["candidates"]]
        else:
            parameters = config.get("parameters", {})
            names = list(parameters)
            self.candidates = [
                dict(zip(names, values, strict=True))
                for values in product(*(parameters[name] for name in names))
            ]
        self.problem: CampaignProblem | None = None

    def configure(self, problem: CampaignProblem) -> None:
        """Check the configured grid against the space the campaign declared.

        A grid is enumerated up front, so every candidate it will ever propose can be checked
        against the declared space before the campaign runs a single iteration. Raising here turns
        a misconfigured sweep from a rejected candidate at iteration 1 — or at iteration 40, if the
        bad point is late in the grid — into an error at campaign start, before anything is leased.
        """
        self.problem = problem
        refused = [
            f"{candidate!r}: {'; '.join(violations)}"
            for candidate, violations in (
                (candidate, problem.violations(candidate)) for candidate in self.candidates
            )
            if violations
        ]
        if refused:
            raise ValueError(
                "the configured grid leaves the search space the campaign declared: "
                + " | ".join(refused)
            )

    def suggest(self, history: list[CampaignObservation]) -> Suggestion | None:
        proposed = self.suggest_batch(history, count=1)
        return proposed[0] if proposed else None

    def suggest_batch(
        self,
        history: list[CampaignObservation],
        *,
        count: int,
    ) -> list[Suggestion]:
        """Return the next `count` untried grid points, in the order the grid was written.

        A grid has no acquisition function and predicts nothing, so a batch here is only a
        throughput claim: these points are independent and may run together. It says so rather than
        inventing an acquisition value it did not compute.
        """
        tried = [item.candidate for item in history]
        untried = [candidate for candidate in self.candidates if candidate not in tried]
        return [
            Suggestion(
                parameters=dict(candidate),
                rationale=(
                    f"grid point {self.candidates.index(candidate) + 1} of "
                    f"{len(self.candidates)}, chosen by enumeration order rather than by any "
                    "model of the response"
                ),
                acquisition_function="none/enumeration",
                model={"optimizer": "grid", "points": len(self.candidates)},
            )
            for candidate in untried[:count]
        ]

    def observe(self, observation: CampaignObservation) -> None:
        return None
