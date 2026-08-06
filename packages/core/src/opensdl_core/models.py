from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    ArtifactKind,
    AuthorizationEffect,
    ExecutorType,
    OperatorType,
    RiskClass,
    RunState,
    TaskState,
)
from .ids import RunId, new_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class OpenSDLModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class Quantity(OpenSDLModel):
    value: float
    unit: str
    uncertainty: float | None = Field(default=None, ge=0)

    @field_validator("unit")
    @classmethod
    def unit_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("unit cannot be blank")
        return value.strip()


class LabMetadata(OpenSDLModel):
    name: str
    owner: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class Operator(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("operator"))
    name: str
    type: OperatorType = OperatorType.HUMAN
    roles: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Location(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("location"))
    name: str
    type: str = "generic"
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Resource(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("resource"))
    name: str
    type: str
    state: str = "available"
    location_id: str | None = None
    quantity: Quantity | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilityDefinition(OpenSDLModel):
    id: str
    version: str = "0.1.0"
    name: str
    description: str = ""
    executor_type: ExecutorType
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_class: RiskClass = RiskClass.R0
    required_resources: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, gt=0)
    max_retries: int = Field(default=0, ge=0)
    supports_cancellation: bool = False
    simulator_available: bool = False
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStep(OpenSDLModel):
    id: str
    capability: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    retries: int | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)


class WorkflowDefinition(OpenSDLModel):
    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStep]
    outputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignDefinition(OpenSDLModel):
    """Declarative description of a closed loop: what to search, and when to stop searching.

    Every field below `optimizer` names a `CampaignRunner.run` keyword argument and carries the
    same default. The submission facts — which environment the work runs in, and which operator is
    accountable for it — are deliberately absent: they come from the laboratory manifest and the
    caller, so a stored definition can never assert an environment its laboratory did not declare.
    """

    id: str
    name: str
    objective: str
    workflow_id: str
    optimizer: str
    max_iterations: int = Field(default=10, gt=0)
    base_inputs: dict[str, Any] = Field(default_factory=dict)
    score_output: str = "score"
    minimize: bool = True
    #: Stop once an observation reaches this score. `None` searches the whole budget.
    target_score: float | None = None
    #: Stop once this many iterations fail in a row: failure has stopped being routine.
    max_consecutive_failures: int = Field(default=3, ge=1)
    #: Wall-clock budget, checked before each iteration. `None` is unbounded.
    max_duration_seconds: float | None = Field(default=None, gt=0)
    #: Workflow input that receives a unique per-iteration identifier, for laboratories whose
    #: workflows need one (a sample, a specimen, a plate well). `None` injects nothing, which is
    #: what a computational workflow needs.
    iteration_id_input: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionRequest(OpenSDLModel):
    request_id: str = Field(default_factory=lambda: new_id("request"))
    capability_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/local"
    environment: str = "simulation"
    run_id: RunId | None = None
    task_id: str | None = None
    authorization_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(OpenSDLModel):
    request_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunRecord(OpenSDLModel):
    id: RunId = Field(default_factory=lambda: new_id("run"))
    workflow_id: str
    workflow_version: str = "0.1.0"
    state: RunState = RunState.PLANNED
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/local"
    environment: str = "simulation"
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskRecord(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    run_id: RunId
    step_id: str
    capability_id: str
    state: TaskState = TaskState.PENDING
    attempt: int = Field(default=0, ge=0)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EventRecord(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    type: str
    occurred_at: datetime = Field(default_factory=utc_now)
    actor_id: str = "system/runtime"
    run_id: RunId | None = None
    task_id: str | None = None
    campaign_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("artifact"))
    sha256: str
    media_type: str
    size_bytes: int = Field(ge=0)
    kind: ArtifactKind = ArtifactKind.OTHER
    storage_path: str
    run_id: RunId | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Observation(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("observation"))
    name: str
    value: Any
    unit: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    run_id: RunId | None = None
    task_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Decision(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("decision"))
    campaign_id: str
    iteration: int = Field(ge=0)
    selected: dict[str, Any]
    rationale: str
    evidence_run_ids: list[RunId] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class AuthorizationReceipt(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("authorization"))
    actor_id: str
    environment: str
    capability_id: str
    effect: AuthorizationEffect
    reason: str
    policy_version: str = "built-in/v0alpha1"
    scope: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class Incident(OpenSDLModel):
    id: str = Field(default_factory=lambda: new_id("incident"))
    title: str
    severity: str
    description: str
    run_id: RunId | None = None
    task_id: str | None = None
    status: str = "open"
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
