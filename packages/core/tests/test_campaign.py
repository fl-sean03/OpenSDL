"""The campaign contract a third party writes an optimizer against.

These tests exist because of where this code lives, not only because of what it does. An optimizer
plugin is the extension point a self-driving-laboratory framework most needs outsiders to write,
and until this contract moved, importing it meant depending on storage, policy, workflows and
SQLAlchemy. So the first test here is an import, and the second is that the import drags nothing
with it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError as PydanticValidationError

import opensdl_core
from opensdl_core import (
    BatchOptimizer,
    CampaignDefinition,
    CampaignObservation,
    CampaignObservationStatus,
    CampaignProblem,
    CandidateConstraint,
    ConfigurableOptimizer,
    IterationDecision,
    Objective,
    ObjectiveValue,
    Optimizer,
    OutcomeConstraint,
    Parameter,
    ParameterKind,
    ResumableOptimizer,
    SearchSpace,
    StatefulOptimizer,
    Suggestion,
)

#: Every name a third-party optimizer needs to implement the contract, and nothing about how the
#: laboratory executes it.
CONTRACT = (
    "BatchOptimizer",
    "CampaignObservation",
    "CampaignObservationStatus",
    "CampaignProblem",
    "CandidateConstraint",
    "ConfigurableOptimizer",
    "IterationDecision",
    "Objective",
    "ObjectiveValue",
    "Optimizer",
    "OutcomeConstraint",
    "Parameter",
    "ParameterKind",
    "ResumableOptimizer",
    "SearchSpace",
    "StatefulOptimizer",
    "Suggestion",
)


def test_the_optimizer_contract_is_reachable_from_core() -> None:
    for name in CONTRACT:
        assert name in opensdl_core.__all__, f"{name} is not exported from opensdl_core"
        assert getattr(opensdl_core, name) is not None


def test_importing_the_contract_imports_no_execution_stack() -> None:
    """The point of the move: a BoTorch or Ax plugin depends on this and on nothing else.

    `opensdl_core` declares one third-party dependency, pydantic. If the contract needed anything
    from the runtime, the runtime — and with it storage, policy, workflows and SQLAlchemy — would
    be in every optimizer plugin's dependency tree.
    """

    graph = _top_level_imports_of(opensdl_core)
    assert not [name for name in graph if name.startswith("opensdl_")]
    assert "sqlalchemy" not in graph


def _top_level_imports_of(module: ModuleType) -> set[str]:
    """Every top-level module named by an import anywhere in this package's source."""

    root = Path(module.__file__ or "").parent
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


def test_a_campaign_definition_can_declare_the_problem_the_runner_searches() -> None:
    """A stored definition that cannot state its objectives cannot describe a real campaign.

    Before this, `objectives`, `search_space` and both constraint lists existed only as
    `CampaignRunner.run` arguments, so a campaign file could name a search it could not express.
    """

    definition = CampaignDefinition(
        id="campaign.color",
        name="Match a target color",
        objective="minimize distance to the target RGB",
        workflow_id="color-mix-and-score",
        optimizer="grid",
        objectives=[
            Objective(name="distance", output="score", minimize=True, target=0.05),
            Objective(name="cost", output="cost", minimize=True),
        ],
        search_space=SearchSpace(
            parameters=[
                Parameter.continuous("red", 0.0, 1.0),
                Parameter.continuous("blue", 0.0, 1.0),
            ]
        ),
        candidate_constraints=[
            CandidateConstraint(
                name="unit", weights={"red": 1.0, "blue": 1.0}, lower=1.0, upper=1.0
            )
        ],
        outcome_constraints=[OutcomeConstraint(name="pressure", output="pressure", upper=9.0)],
        batch_size=2,
        max_parallel_runs=2,
    )

    assert CampaignDefinition.model_validate_json(definition.model_dump_json()) == definition
    problem = definition.problem()
    assert isinstance(problem, CampaignProblem)
    assert [item.name for item in problem.objectives] == ["distance", "cost"]
    assert problem.space.parameters[0].kind is ParameterKind.CONTINUOUS
    assert problem.violations({"red": 0.4, "blue": 0.6}) == []
    assert problem.violations({"red": 0.4, "blue": 0.4}) == ["unit: 0.8 is below 1"]


def test_a_definition_declaring_objectives_cannot_also_declare_the_scalar_triple() -> None:
    """One statement of the objective, refused at load rather than resolved silently."""

    with pytest.raises(ValueError, match="score_output and minimize"):
        CampaignDefinition(
            id="campaign.color",
            name="Match a target color",
            objective="minimize distance",
            workflow_id="color-mix-and-score",
            optimizer="grid",
            score_output="distance",
            objectives=[Objective(name="distance", output="distance")],
        )


def test_a_definition_that_declares_nothing_still_states_one_objective() -> None:
    definition = CampaignDefinition(
        id="campaign.color",
        name="Match a target color",
        objective="minimize distance",
        workflow_id="color-mix-and-score",
        optimizer="grid",
    )
    problem = definition.problem()
    assert [item.name for item in problem.objectives] == ["score"]
    assert problem.primary.minimize is True
    assert problem.space.parameters == []


def test_the_problem_reads_every_declared_objective_out_of_a_run() -> None:
    """`measure` lives with the declaration so the runner and the definition read it one way."""

    problem = CampaignProblem(
        objectives=[
            Objective(name="score", output="result.score", uncertainty_output="result.sigma"),
            Objective(name="cost", output="cost", minimize=False),
        ]
    )
    measured = problem.measure({"result": {"score": 1.5, "sigma": 0.25}, "cost": 9.0})
    assert measured == {
        "score": ObjectiveValue(value=1.5, uncertainty=0.25),
        "cost": ObjectiveValue(value=9.0),
    }
    with pytest.raises(KeyError, match="campaign score output not found: result.score"):
        problem.measure({"cost": 9.0})


def test_an_observation_and_a_suggestion_are_the_two_halves_of_one_iteration() -> None:
    suggestion = Suggestion(
        parameters={"x": 1.0},
        predictions={"score": ObjectiveValue(value=0.5, uncertainty=0.1)},
        acquisition=0.9,
        acquisition_function="qEI",
    )
    observation = CampaignObservation(
        iteration=0,
        candidate=suggestion.parameters,
        score=0.4,
        objectives={"score": ObjectiveValue(value=0.4)},
        suggestion=suggestion,
    )
    assert observation.succeeded and observation.attempted and observation.feasible
    assert observation.status is CampaignObservationStatus.SUCCEEDED
    assert IterationDecision(rationale="because").evidence_run_ids == []


def test_every_optional_capability_is_checkable_one_at_a_time() -> None:
    """A protocol that bundled two methods would silently stop matching an optimizer with one.

    `runtime_checkable` `isinstance` requires *every* member of the protocol, so putting
    `load_state` beside `configure` would have made an optimizer that only configures fail the
    check that calls `configure` — losing the pre-loop validation without an error anywhere.
    """

    class ConfiguresOnly:
        def suggest(self, history: list[CampaignObservation]) -> dict[str, float] | None:
            return None

        def observe(self, observation: CampaignObservation) -> None:
            return None

        def configure(self, problem: CampaignProblem) -> None:
            return None

    optimizer = ConfiguresOnly()
    assert isinstance(optimizer, Optimizer)
    assert isinstance(optimizer, ConfigurableOptimizer)
    assert not isinstance(optimizer, ResumableOptimizer)
    assert not isinstance(optimizer, StatefulOptimizer)
    assert not isinstance(optimizer, BatchOptimizer)


def test_an_observation_states_what_its_status_permits() -> None:
    """`__post_init__` was the only validation these carried; it is now the model's."""

    with pytest.raises(PydanticValidationError, match="must carry the score"):
        CampaignObservation(iteration=0, candidate={"x": 1})
    with pytest.raises(PydanticValidationError, match="cannot carry an error"):
        CampaignObservation(iteration=0, candidate={"x": 1}, score=1.0, error="but it worked")
    with pytest.raises(PydanticValidationError, match="failed observation has no score"):
        CampaignObservation(
            iteration=0,
            candidate={"x": 1},
            score=1.0,
            status=CampaignObservationStatus.FAILED,
            error="stalled",
        )
    with pytest.raises(PydanticValidationError, match="must record why it failed"):
        CampaignObservation(
            iteration=0, candidate={"x": 1}, status=CampaignObservationStatus.FAILED
        )
    with pytest.raises(PydanticValidationError, match="names no run"):
        CampaignObservation(
            iteration=0,
            candidate={"x": 1},
            status=CampaignObservationStatus.REJECTED,
            error="outside the space",
            run_id="run_0123456789abcdef0123456789abcdef",
        )


def test_an_observation_and_a_suggestion_round_trip_through_their_serialised_form() -> None:
    suggestion = Suggestion(
        parameters={"x": 1.0},
        predictions={"score": ObjectiveValue(value=0.5, uncertainty=0.1)},
        acquisition=0.9,
        acquisition_function="qEI",
        model={"kernel": "matern"},
        rationale="expected improvement",
        evidence_run_ids=("run_0123456789abcdef0123456789abcdef",),
    )
    observation = CampaignObservation(
        iteration=2,
        candidate={"x": 1.0},
        score=0.4,
        run_id="run_0123456789abcdef0123456789abcdee",
        objectives={"score": ObjectiveValue(value=0.4)},
        constraint_violations=("pressure: 10 is above 9",),
        suggestion=suggestion,
        batch=1,
    )

    document = observation.model_dump(mode="json", by_alias=True)

    assert document["runId"] == observation.run_id
    assert document["constraintViolations"] == ["pressure: 10 is above 9"]
    assert document["suggestion"]["acquisitionFunction"] == "qEI"
    assert document["suggestion"]["evidenceRunIds"] == list(suggestion.evidence_run_ids or ())
    assert CampaignObservation.model_validate(document) == observation
    assert not observation.feasible


def test_the_contract_models_are_immutable_and_refuse_an_undeclared_field() -> None:
    observation = CampaignObservation(iteration=0, candidate={"x": 1}, score=1.0)

    with pytest.raises(PydanticValidationError):
        observation.score = 2.0  # type: ignore[misc]
    with pytest.raises(PydanticValidationError):
        CampaignObservation.model_validate(
            {"iteration": 0, "candidate": {"x": 1}, "score": 1.0, "invented": True}
        )
    with pytest.raises(PydanticValidationError):
        Suggestion.model_validate({"parameters": {"x": 1}, "invented": True})


def test_an_optimizer_may_still_spell_the_contract_in_python() -> None:
    """The camelCase spelling is the recorded document's, not the plugin author's."""

    suggestion = Suggestion(parameters={"x": 1}, acquisition_function="qEI")

    assert suggestion.acquisition_function == "qEI"
    assert Suggestion.model_validate({"parameters": {"x": 1}, "acquisitionFunction": "qEI"}) == (
        suggestion
    )
