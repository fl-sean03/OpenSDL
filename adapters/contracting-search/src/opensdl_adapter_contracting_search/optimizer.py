"""A deterministic contracting random search, and the reference for a stateful optimizer.

The method is Luus-Jaakola: sample a batch uniformly inside a region centred on the best point
seen so far, re-centre on the best of what came back, then shrink the region and repeat. It fits
no model and computes no acquisition function, so it is not competitive with Bayesian optimization
on a budget where evaluations are expensive. What it is, is honest about converging: the region
provably contracts, the trace flattens onto the noise floor of the instrument, and it does all of
that in a hundred lines with no dependency beyond `opensdl-core`.

It exists next to `GridOptimizer` because the two divide the plugin contract between them. A grid
has no state worth preserving, so it implements neither `state()` nor `load_state()` and says so.
This one carries a trust region and a random stream — the two things the `ResumableOptimizer`
docstring names as unrecoverable by replay — so it implements both, and a campaign resumed from a
recorded state continues the same search rather than restarting a differently-seeded one.
"""

from __future__ import annotations

import random
from typing import Any

from opensdl_core import (
    CampaignObservation,
    CampaignObservationStatus,
    CampaignProblem,
    Parameter,
    ParameterKind,
    Suggestion,
)

#: How much of each dimension's range the sampling region spans on the first round. Searching the
#: whole declared space is the only defensible default: the optimizer has been told the bounds and
#: nothing else, so anything narrower would be a prior it was never given.
INITIAL_REGION = 1.0

#: What the region is multiplied by after each round. Luus and Jaakola used 0.95 over many single
#: point iterations; a campaign that evaluates a full plate per round takes far fewer, larger
#: steps, so it contracts harder. At 0.7 the region is a fifth of the space by round five and a
#: twentieth by round nine, which is the difference between a plate that still looks like a search
#: and one that has visibly stopped moving.
CONTRACTION = 0.7

#: Attempts to draw a feasible point before the sampler gives up on that slot. A region straddling
#: the edge of a constraint can reject a great many draws, and a campaign that quietly returned a
#: short batch would look like an optimizer with nothing to say rather than a region in a corner.
FEASIBLE_DRAW_ATTEMPTS = 200


class ContractingSearch:
    """Batch random search over a region that shrinks toward the best point observed."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        self.contraction = float(config.get("contraction", CONTRACTION))
        if not 0.0 < self.contraction <= 1.0:
            raise ValueError("contraction must be greater than zero and at most one")
        self.initial_region = float(config.get("initial_region", INITIAL_REGION))
        if not 0.0 < self.initial_region <= 1.0:
            raise ValueError("initial_region must be greater than zero and at most one")
        self.random = random.Random(int(config.get("seed", 0)))
        self.rounds = 0
        self.problem: CampaignProblem | None = None

    def configure(self, problem: CampaignProblem) -> None:
        """Take the declared space, and refuse a problem this method cannot search.

        A region is a box, and a box needs bounds. A categorical dimension has none — there is no
        distance between "red" and "blue" to contract along — so the honest answer is to say the
        method does not apply rather than to invent an ordering over the choices.
        """
        unbounded = sorted(
            parameter.name
            for parameter in problem.space.parameters
            if parameter.kind is ParameterKind.CATEGORICAL
        )
        if unbounded:
            raise ValueError(
                "contracting search needs an ordered range in every dimension; "
                f"these are categorical: {', '.join(unbounded)}"
            )
        if not problem.space.parameters:
            raise ValueError("contracting search needs a declared search space to contract within")
        self.problem = problem

    def suggest(self, history: list[CampaignObservation]) -> Suggestion | None:
        proposed = self.suggest_batch(history, count=1)
        return proposed[0] if proposed else None

    def suggest_batch(
        self,
        history: list[CampaignObservation],
        *,
        count: int,
    ) -> list[Suggestion]:
        """Propose one round: `count` points drawn inside the current region.

        The centre is read from `history` rather than accumulated in `observe`, because history is
        the campaign's record and this optimizer's memory of it can only be wrong. The region width
        is the part that cannot be recovered that way, and it is what `state()` hands over.
        """
        if self.problem is None:
            raise RuntimeError("configure() must be called before the first proposal")
        parameters = self.problem.space.parameters
        centre = self._centre(history)
        region = self.initial_region * self.contraction**self.rounds
        self.rounds += 1
        drawn = [self._feasible_point(parameters, centre, region) for _ in range(count)]
        return [
            Suggestion(
                parameters=point,
                rationale=(
                    f"round {self.rounds}: drawn uniformly from a region spanning "
                    f"{region:.3g} of each declared range, centred on "
                    + (
                        "the best candidate observed so far"
                        if any(item.score is not None for item in history)
                        else "the middle of the declared space, nothing having been measured yet"
                    )
                ),
                acquisition_function="none/uniform-in-region",
                model={
                    "optimizer": "contracting-search",
                    "round": self.rounds,
                    "region": region,
                    "centre": centre,
                },
            )
            for point in drawn
            if point is not None
        ]

    def observe(self, observation: CampaignObservation) -> None:
        return None

    def state(self) -> dict[str, Any]:
        """Hand over the region width and the random stream.

        Replaying observations restores the centre, because the centre is derived from them.
        Neither the number of rounds already taken nor the position of the generator can be
        recovered that way, and a resumed campaign that restarted either would search a region it
        had already contracted past, with a stream it had already drawn from.
        """
        return {"rounds": self.rounds, "random_state": _encode(self.random.getstate())}

    def load_state(self, state: dict[str, Any]) -> None:
        rounds = state.get("rounds")
        if not isinstance(rounds, int) or rounds < 0:
            raise ValueError(f"recorded state carries no usable round count: {rounds!r}")
        self.rounds = rounds
        recorded = state.get("random_state")
        if recorded is not None:
            self.random.setstate(_decode(recorded))

    def _centre(self, history: list[CampaignObservation]) -> dict[str, Any]:
        """The best feasible candidate observed, or the middle of the space if there is none.

        Only succeeded observations carry a usable score. A failed run and a rejected candidate are
        both in history on purpose, and neither is evidence about where the optimum is.
        """
        assert self.problem is not None
        # The score is carried alongside rather than read back off the observation, so that the
        # comparison below is over floats the filter has already established.
        scored = [
            (item, float(item.score))
            for item in history
            if item.status is CampaignObservationStatus.SUCCEEDED and item.score is not None
        ]
        if not scored:
            return {
                parameter.name: _midpoint(parameter) for parameter in self.problem.space.parameters
            }
        minimize = all(objective.minimize for objective in self.problem.objectives)
        best, _ = (min if minimize else max)(scored, key=lambda pair: pair[1])
        return dict(best.candidate)

    def _feasible_point(
        self,
        parameters: list[Parameter],
        centre: dict[str, Any],
        region: float,
    ) -> dict[str, Any] | None:
        for _ in range(FEASIBLE_DRAW_ATTEMPTS):
            point = {
                parameter.name: self._draw(parameter, centre.get(parameter.name), region)
                for parameter in parameters
            }
            assert self.problem is not None
            if not self.problem.violations(point):
                return point
        return None

    def _draw(self, parameter: Parameter, centre: Any, region: float) -> float | int:
        lower = float(parameter.lower if parameter.lower is not None else 0.0)
        upper = float(parameter.upper if parameter.upper is not None else 0.0)
        middle = float(centre) if isinstance(centre, int | float) else _midpoint(parameter)
        half = (upper - lower) * region / 2.0
        value = self.random.uniform(max(lower, middle - half), min(upper, middle + half))
        if parameter.kind is ParameterKind.INTEGER:
            return max(int(lower), min(int(upper), round(value)))
        return value


def _midpoint(parameter: Parameter) -> float:
    lower = float(parameter.lower if parameter.lower is not None else 0.0)
    upper = float(parameter.upper if parameter.upper is not None else 0.0)
    return (lower + upper) / 2.0


def _encode(state: tuple[Any, ...]) -> list[Any]:
    """`random.getstate` returns nested tuples; recorded state is JSON and has only lists."""

    return [list(item) if isinstance(item, tuple) else item for item in state]


def _decode(state: Any) -> tuple[Any, ...]:
    if not isinstance(state, list | tuple):
        raise ValueError(f"recorded random state is not a sequence: {state!r}")
    return tuple(tuple(item) if isinstance(item, list) else item for item in state)
