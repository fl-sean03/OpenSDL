from __future__ import annotations

from enum import StrEnum


class OperatorType(StrEnum):
    HUMAN = "human"
    SOFTWARE = "software"
    SERVICE = "service"
    DEVICE = "device"
    SYSTEM = "system"


class ExecutorType(StrEnum):
    HUMAN = "human"
    INSTRUMENT = "instrument"
    ROBOT = "robot"
    COMPUTE = "compute"
    ANALYSIS = "analysis"
    OPTIMIZER = "optimizer"
    SIMULATOR = "simulator"


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class RunState(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    INTERVENTION_REQUIRED = "intervention_required"
    ABORTING = "aborting"
    ABORTED = "aborted"
    FAILED = "failed"
    COMPLETED = "completed"


class TaskState(StrEnum):
    PENDING = "pending"
    WAITING_FOR_RESOURCES = "waiting_for_resources"
    WAITING_FOR_AUTHORIZATION = "waiting_for_authorization"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERVENTION_REQUIRED = "intervention_required"


class AuthorizationEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class ArtifactKind(StrEnum):
    RAW = "raw"
    DERIVED = "derived"
    LOG = "log"
    MODEL = "model"
    REPORT = "report"
    OTHER = "other"
