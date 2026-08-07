from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from opensdl_core import (
    CampaignObservation,
    CampaignProblem,
    CandidateConstraint,
    Objective,
    ObjectiveValue,
    OutcomeConstraint,
    Parameter,
    SearchSpace,
    Suggestion,
)
from opensdl_schemas import SCHEMAS, validate_against_json_schema

CANONICAL_DIRECTORY = Path(__file__).parents[3] / "packages" / "schemas" / "jsonschema"
TWIN_DEFINITION_SCHEMA = CANONICAL_DIRECTORY / "twin-definition.schema.json"


def twin_definition_document() -> dict[str, Any]:
    return {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "DigitalTwin",
        "version": "0.1.0",
        "revision": "scene-revision-1",
        "coordinateFrame": {"unit": "m", "handedness": "right", "upAxis": "Z"},
        "scene": {"path": "generated/scene.glb", "sha256": "a" * 64},
        "entities": [{"id": "robot", "node": "robot_root", "resources": ["cell.robot"]}],
    }


def test_canonical_directory_holds_every_public_contract() -> None:
    committed = {path.name for path in CANONICAL_DIRECTORY.glob("*.schema.json")}

    assert {f"{name}.schema.json" for name in SCHEMAS} <= committed
    assert "twin-definition.schema.json" in committed


@pytest.mark.parametrize(
    "path",
    sorted(CANONICAL_DIRECTORY.glob("*.schema.json")),
    ids=lambda path: path.name,
)
def test_committed_schema_is_valid_draft_2020_12(path: Path) -> None:
    Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_twin_definition_schema_accepts_a_valid_document() -> None:
    validate_against_json_schema(twin_definition_document(), TWIN_DEFINITION_SCHEMA)


def test_twin_definition_schema_rejects_an_unversioned_document() -> None:
    document = twin_definition_document()
    document["apiVersion"] = "opensdl.dev/v1"

    with pytest.raises(ValidationError):
        validate_against_json_schema(document, TWIN_DEFINITION_SCHEMA)


#: The campaign contract a third party implements. Each of these crosses a process boundary — it is
#: what an optimizer plugin receives or returns — and each is also written into the durable event
#: stream, so the repository rule that public models are exported as versioned schemas applies.
OPTIMIZER_CONTRACT_SCHEMAS = ("campaign-observation", "suggestion", "campaign-problem")


@pytest.mark.parametrize("name", OPTIMIZER_CONTRACT_SCHEMAS)
def test_the_optimizer_contract_is_published_as_a_schema(name: str) -> None:
    assert name in SCHEMAS
    assert (CANONICAL_DIRECTORY / f"{name}.schema.json").is_file()


def test_a_recorded_observation_validates_against_its_published_schema() -> None:
    """The document a campaign records and the schema it publishes are one thing.

    `CampaignCompleted` carried a hand-rolled camelCase mapping that matched no published schema.
    It is now the model's own serialisation, so this validates the same bytes the event stream
    holds against the same schema a consumer would be handed.
    """

    observation = CampaignObservation(
        iteration=3,
        candidate={"red_fraction": 0.5},
        score=0.25,
        run_id="run_0123456789abcdef0123456789abcdef",
        outputs={"score": 0.25},
        objectives={"score": ObjectiveValue(value=0.25, uncertainty=0.01)},
        suggestion=Suggestion(
            parameters={"red_fraction": 0.5},
            acquisition=0.9,
            acquisition_function="qEI",
            model={"kernel": "matern"},
            rationale="expected improvement",
            evidence_run_ids=("run_0123456789abcdef0123456789abcdee",),
        ),
        batch=1,
    )
    document = observation.model_dump(mode="json", by_alias=True)

    validate_against_json_schema(document, CANONICAL_DIRECTORY / "campaign-observation.schema.json")
    assert CampaignObservation.model_validate(document) == observation


def test_the_observation_schema_refuses_a_document_that_claims_more_than_it_carries() -> None:
    document = {
        "iteration": 0,
        "candidate": {"x": 1},
        "status": "failed",
        "error": "the mixer stalled",
        "invented": True,
    }

    with pytest.raises(ValidationError):
        validate_against_json_schema(
            document, CANONICAL_DIRECTORY / "campaign-observation.schema.json"
        )


def test_a_recorded_campaign_problem_validates_against_its_published_schema() -> None:
    """`CampaignStarted` embeds this document whole and a resume validates it back."""

    problem = CampaignProblem.declare(
        objectives=[Objective(name="distance", output="score", target=0.05)],
        space=SearchSpace(parameters=[Parameter.continuous("red", 0.0, 1.0)]),
        candidate_constraints=[
            CandidateConstraint(name="unit", weights={"red": 1.0}, lower=0.0, upper=1.0)
        ],
        outcome_constraints=[OutcomeConstraint(name="pressure", output="pressure", upper=9.0)],
    )
    document = problem.model_dump(mode="json")

    validate_against_json_schema(document, CANONICAL_DIRECTORY / "campaign-problem.schema.json")
    assert CampaignProblem.model_validate(document) == problem
