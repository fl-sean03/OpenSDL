from __future__ import annotations

import ast
from pathlib import Path

import pytest

import opensdl_adapter_grid_optimizer
from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_core import (
    BatchOptimizer,
    CampaignObservation,
    CampaignProblem,
    ConfigurableOptimizer,
    Objective,
    Optimizer,
    Parameter,
    SearchSpace,
    StatefulOptimizer,
)


def test_the_reference_optimizer_depends_on_the_contract_and_not_on_the_execution_stack() -> None:
    """What a third party publishing a BoTorch or Ax plugin has to install.

    This adapter was the sole exception in `scripts/check-boundaries.py`: it alone was allowed to
    import `opensdl_runtime`, because the optimizer contract lived there. Depending on the runtime
    means depending on storage, policy, workflows and SQLAlchemy to implement two methods.
    """

    root = Path(opensdl_adapter_grid_optimizer.__file__ or "").parent
    imported: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])

    assert {name for name in imported if name.startswith("opensdl_")} == {"opensdl_core"}


def problem(*parameters: Parameter) -> CampaignProblem:
    return CampaignProblem(
        objectives=[Objective(name="score", output="score")],
        space=SearchSpace(parameters=list(parameters)),
    )


def test_grid_optimizer_order() -> None:
    optimizer = GridOptimizer({"parameters": {"x": [1, 2], "y": [3, 4]}})
    proposed = optimizer.suggest([])
    assert proposed is not None
    assert proposed.parameters == {"x": 1, "y": 3}


def test_the_grid_optimizer_implements_the_capabilities_a_grid_has() -> None:
    """A grid has no surrogate, so it has no state. The contract does not make it pretend."""

    optimizer = GridOptimizer({"parameters": {"x": [1, 2]}})
    assert isinstance(optimizer, Optimizer)
    assert isinstance(optimizer, BatchOptimizer)
    assert isinstance(optimizer, ConfigurableOptimizer)
    assert not isinstance(optimizer, StatefulOptimizer)


def test_a_batch_returns_the_next_untried_points_in_order() -> None:
    optimizer = GridOptimizer({"parameters": {"x": [1, 2, 3, 4]}})

    first = optimizer.suggest_batch([], count=2)
    assert [item.parameters for item in first] == [{"x": 1}, {"x": 2}]

    history = [
        CampaignObservation(iteration=0, candidate={"x": 1}, score=1.0),
        CampaignObservation(iteration=1, candidate={"x": 2}, score=2.0),
    ]
    assert [item.parameters for item in optimizer.suggest_batch(history, count=5)] == [
        {"x": 3},
        {"x": 4},
    ]
    assert optimizer.suggest_batch(history, count=0) == []


def test_a_grid_point_declares_that_it_ranked_nothing() -> None:
    """A baseline that reported an acquisition value would be reporting a number it never had."""

    proposed = GridOptimizer({"parameters": {"x": [1, 2]}}).suggest_batch([], count=1)[0]

    assert proposed.acquisition is None
    assert proposed.acquisition_function == "none/enumeration"
    assert proposed.model == {"optimizer": "grid", "points": 2}
    assert "enumeration order" in proposed.rationale


def test_a_grid_that_leaves_the_declared_space_is_refused_at_campaign_start() -> None:
    """The whole grid is known up front, so the whole grid can be checked before anything runs."""

    optimizer = GridOptimizer({"parameters": {"x": [0.5, 9.0]}})

    with pytest.raises(ValueError, match="leaves the search space"):
        optimizer.configure(problem(Parameter.continuous("x", 0.0, 1.0)))


def test_a_grid_inside_the_declared_space_is_accepted_and_keeps_the_declaration() -> None:
    optimizer = GridOptimizer({"parameters": {"x": [0.25, 0.75]}})
    declared = problem(Parameter.continuous("x", 0.0, 1.0))

    optimizer.configure(declared)

    assert optimizer.problem is declared
    assert [item.parameters for item in optimizer.suggest_batch([], count=2)] == [
        {"x": 0.25},
        {"x": 0.75},
    ]


def test_a_campaign_that_declares_no_space_constrains_nothing() -> None:
    optimizer = GridOptimizer({"candidates": [{"x": 1}, {"y": "anything"}]})

    optimizer.configure(CampaignProblem(objectives=[Objective(name="score", output="score")]))

    assert optimizer.problem is not None
