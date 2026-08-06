from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ArtifactKind,
    AuthorizationEffect,
    ExecutorType,
    OperatorType,
    RetrySafety,
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
    #: Whether repeating this operation is safe when the runtime cannot establish whether the
    #: first attempt took effect. The runtime reads it twice — before repeating a dispatch, and
    #: when deciding what a timed-out task is allowed to claim — and both readings come from this
    #: one declaration so they cannot disagree.
    #:
    #: **The default is the strict one, and that is a deliberate incompatibility.** Every
    #: capability written before this field existed omits it, so a permissive default would have
    #: preserved today's behaviour exactly and left the hazard in place for every capability
    #: nobody revisits — silently, because an author who never heard of the field would ship a
    #: dispense the runtime repeats. `SAFETY.md` makes retry safety the adapter's statement to
    #: make; an omission is the absence of that statement, not a relaxed version of it. The
    #: asymmetry decides it: defaulting strict costs an unrevisited capability some automatic
    #: retries and turns some of its timeouts into interventions, while defaulting permissive
    #: costs an unrevisited physical capability a repeated dispense. Every shipped adapter
    #: declares honestly, so the strict default binds only definitions nobody has considered.
    retry_safety: RetrySafety = RetrySafety.NOT_REPEATABLE
    supports_cancellation: bool = False
    simulator_available: bool = False
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def retry_budget_must_be_declared_safe(self) -> CapabilityDefinition:
        """Refuse a retry budget the same definition says can never be spent.

        `max_retries` and `retry_safety` are one statement about the same behaviour. A definition
        asking for automatic attempts while declaring that repeating it is never safe cannot be
        honoured either way round, and the runtime resolving it silently is how a declared budget
        becomes a surprise at an instrument.
        """
        if self.max_retries > 0 and self.retry_safety is RetrySafety.NOT_REPEATABLE:
            raise ValueError(
                f"capability {self.id} declares max_retries={self.max_retries} and "
                f"retry_safety='{self.retry_safety.value}', which contradict each other: the "
                "runtime will never spend that budget. Declare the retry safety this operation "
                "actually has, or set max_retries=0."
            )
        return self


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
