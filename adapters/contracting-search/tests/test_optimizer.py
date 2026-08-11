from __future__ import annotations

import ast
from pathlib import Path

import pytest

import opensdl_adapter_contracting_search
from opensdl_adapter_contracting_search import ContractingSearch
from opensdl_core import (
    BatchOptimizer,
    CampaignObservation,
    CampaignObservationStatus,
    CampaignProblem,
    CandidateConstraint,
    ConfigurableOptimizer,
    Objective,
    Optimizer,
    Parameter,
    ResumableOptimizer,
    SearchSpace,
    StatefulOptimizer,
)


def _problem(**kwargs: object) -> CampaignProblem:
    return CampaignProblem(
        objectives=[Objective(name="distance", output="score")],
        space=SearchSpace(
            parameters=[
                Parameter.continuous("x", 0.0, 1.0),
                Parameter.continuous("y", 0.0, 1.0),
            ]
        ),
        **kwargs,  # type: ignore[arg-type]
    )


def _observed(candidate: dict[str, float], score: float, iteration: int = 0) -> CampaignObservation:
    return CampaignObservation(
        iteration=iteration,
        candidate=candidate,
        score=score,
        status=CampaignObservationStatus.SUCCEEDED,
    )


def test_the_optimizer_depends_on_the_contract_and_not_on_the_execution_stack() -> None:
    """The same claim `GridOptimizer` makes: two protocols, no laboratory."""

    root = Path(opensdl_adapter_contracting_search.__file__ or "").parent
    imported: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
    assert {name for name in imported if name.startswith("opensdl")} == {"opensdl_core"}


def test_it_implements_the_capabilities_the_grid_deliberately_does_not() -> None:
    optimizer = ContractingSearch()
    assert isinstance(optimizer, Optimizer)
    assert isinstance(optimizer, BatchOptimizer)
    assert isinstance(optimizer, ConfigurableOptimizer)
    assert isinstance(optimizer, StatefulOptimizer)
    assert isinstance(optimizer, ResumableOptimizer)


def test_the_first_round_spans_the_whole_declared_space() -> None:
    """Nothing has been measured, so nowhere is preferred."""

    optimizer = ContractingSearch({"seed": 1})
    optimizer.configure(_problem())
    batch = optimizer.suggest_batch([], count=200)
    xs = [suggestion.parameters["x"] for suggestion in batch]
    assert min(xs) < 0.05 and max(xs) > 0.95


def test_the_region_contracts_around_the_best_point() -> None:
    optimizer = ContractingSearch({"seed": 1, "contraction": 0.5})
    optimizer.configure(_problem())
    history = [_observed({"x": 0.8, "y": 0.2}, score=0.1)]
    spreads = []
    for _ in range(4):
        batch = optimizer.suggest_batch(history, count=200)
        xs = [suggestion.parameters["x"] for suggestion in batch]
        spreads.append(max(xs) - min(xs))
    assert spreads == sorted(spreads, reverse=True)
    assert spreads[-1] < spreads[0] / 4
    # The last round is drawn tightly around the best candidate it was shown.
    final = optimizer.suggest_batch(history, count=200)
    assert all(abs(suggestion.parameters["x"] - 0.8) < 0.05 for suggestion in final)


def test_it_converges_on_a_target_it_was_never_told() -> None:
    """The whole claim: a closed loop of propose, score, re-centre reaches the optimum."""

    optimizer = ContractingSearch({"seed": 4})
    optimizer.configure(_problem())
    target = {"x": 0.31, "y": 0.72}
    history: list[CampaignObservation] = []
    for round_index in range(12):
        for suggestion in optimizer.suggest_batch(history, count=12):
            point = suggestion.parameters
            score = ((point["x"] - target["x"]) ** 2 + (point["y"] - target["y"]) ** 2) ** 0.5
            history.append(_observed(point, score=score, iteration=round_index))
    assert min(item.score for item in history if item.score is not None) < 1e-3


def test_a_failed_or_rejected_attempt_does_not_move_the_centre() -> None:
    """Both are in history on purpose, and neither is evidence about where the optimum is."""

    optimizer = ContractingSearch({"seed": 2, "contraction": 0.2})
    optimizer.configure(_problem())
    history = [
        _observed({"x": 0.9, "y": 0.9}, score=0.5),
        CampaignObservation(
            iteration=1,
            candidate={"x": 0.1, "y": 0.1},
            status=CampaignObservationStatus.FAILED,
            error="the colorimeter reported no reading",
        ),
        CampaignObservation(
            iteration=1,
            candidate={"x": 0.0, "y": 0.0},
            status=CampaignObservationStatus.REJECTED,
            error="left the declared search space",
            constraint_violations=("x below its lower bound",),
        ),
    ]
    first = optimizer.suggest_batch(history, count=50)
    assert all(item.model["centre"] == {"x": 0.9, "y": 0.9} for item in first)
    # Round one spans the whole space whatever the centre, so the centre only becomes visible in
    # the draw once the region has contracted around it.
    contracted = optimizer.suggest_batch(history, count=50)
    assert all(item.parameters["x"] > 0.5 for item in contracted)


def test_it_only_proposes_candidates_the_campaign_would_accept() -> None:
    """A region straddling a constraint must draw inside it, not propose work that gets refused."""

    optimizer = ContractingSearch({"seed": 3})
    problem = _problem(
        candidate_constraints=[
            CandidateConstraint(name="budget", weights={"x": 1.0, "y": 1.0}, upper=0.6)
        ]
    )
    optimizer.configure(problem)
    for _ in range(3):
        batch = optimizer.suggest_batch([], count=60)
        assert batch, "the sampler gave up on a region that has feasible points in it"
        assert all(not problem.violations(item.parameters) for item in batch)


def test_it_refuses_a_space_it_cannot_contract_within() -> None:
    optimizer = ContractingSearch()
    problem = CampaignProblem(
        objectives=[Objective(name="distance", output="score")],
        space=SearchSpace(parameters=[Parameter.categorical("dye", ["red", "blue"])]),
    )
    with pytest.raises(ValueError, match="categorical"):
        optimizer.configure(problem)


def test_it_refuses_to_propose_before_it_has_been_configured() -> None:
    with pytest.raises(RuntimeError, match="configure"):
        ContractingSearch().suggest_batch([], count=1)


def test_a_resumed_search_continues_rather_than_restarting() -> None:
    """The region width and the random stream are what replaying observations cannot restore."""

    original = ContractingSearch({"seed": 11})
    original.configure(_problem())
    history = [_observed({"x": 0.4, "y": 0.6}, score=0.2)]
    for _ in range(3):
        original.suggest_batch(history, count=8)
    recorded = original.state()

    resumed = ContractingSearch({"seed": 11})
    resumed.configure(_problem())
    resumed.load_state(recorded)
    assert [item.parameters for item in resumed.suggest_batch(history, count=8)] == [
        item.parameters for item in original.suggest_batch(history, count=8)
    ]

    # A campaign that restarted the optimizer instead would search a region it contracted past.
    restarted = ContractingSearch({"seed": 11})
    restarted.configure(_problem())
    assert [item.parameters for item in restarted.suggest_batch(history, count=8)] != [
        item.parameters for item in resumed.suggest_batch(history, count=8)
    ]


def test_recorded_state_survives_a_json_round_trip() -> None:
    """It is written into the durable event stream, where tuples do not exist."""

    import json

    optimizer = ContractingSearch({"seed": 5})
    optimizer.configure(_problem())
    optimizer.suggest_batch([], count=4)
    restored = ContractingSearch({"seed": 5})
    restored.configure(_problem())
    restored.load_state(json.loads(json.dumps(optimizer.state())))
    history = [_observed({"x": 0.5, "y": 0.5}, score=0.3)]
    assert [item.parameters for item in restored.suggest_batch(history, count=4)] == [
        item.parameters for item in optimizer.suggest_batch(history, count=4)
    ]


def test_it_refuses_recorded_state_it_cannot_use() -> None:
    optimizer = ContractingSearch()
    optimizer.configure(_problem())
    with pytest.raises(ValueError, match="round count"):
        optimizer.load_state({"rounds": "several"})


def test_the_same_seed_searches_the_same_way_twice() -> None:
    def trace() -> list[dict[str, float]]:
        optimizer = ContractingSearch({"seed": 7})
        optimizer.configure(_problem())
        history = [_observed({"x": 0.25, "y": 0.25}, score=0.4)]
        return [
            item.parameters for _ in range(3) for item in optimizer.suggest_batch(history, count=5)
        ]

    assert trace() == trace()


def test_a_suggestion_says_what_produced_it() -> None:
    optimizer = ContractingSearch({"seed": 9})
    optimizer.configure(_problem())
    first = optimizer.suggest_batch([], count=1)[0]
    assert "nothing having been measured yet" in first.rationale
    assert first.acquisition_function == "none/uniform-in-region"
    assert first.model["round"] == 1
    assert first.predictions == {}, "this optimizer fits no model and must not claim a prediction"

    later = optimizer.suggest_batch([_observed({"x": 0.5, "y": 0.5}, score=0.1)], count=1)[0]
    assert "best candidate observed so far" in later.rationale
    assert later.model["region"] < first.model["region"]
