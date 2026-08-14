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


class RetrySafety(StrEnum):
    """Whether repeating an operation is safe when its first attempt's outcome is unknown.

    This is the "retry safety" `SAFETY.md` requires every operational adapter to define. It is
    asked at one moment only: the runtime dispatched the operation, and it cannot establish
    whether that dispatch took effect. A timeout, a dropped connection, a cancelled wait and a
    restarted controller all land there. The runtime cannot infer the answer — an API success is
    not proof a physical action occurred, and an API failure is not proof it did not — so the
    capability declares it.

    It says nothing about whether an operation is *correct* to repeat, only whether repeating it
    can hurt. A measurement that returns a different value each time is still `REPEATABLE`.
    """

    #: Repeating this operation under uncertainty cannot harm anything: it has no physical
    #: effect, or its effect is idempotent. Simulators and pure computations belong here.
    REPEATABLE = "repeatable"

    #: Repeating is safe only when something has established that the first attempt never reached
    #: the equipment. A dispense that failed to open a connection may be re-sent; the same dispense
    #: abandoned mid-pour may not. The proof has to come from the adapter, which is the only party
    #: that knows whether the command went out: it raises `opensdl_capabilities.NotDispatchedError`.
    REPEATABLE_IF_NOT_DISPATCHED = "repeatable_if_not_dispatched"

    #: Never repeat automatically. A person establishes what the equipment did. This is the
    #: default, so it is also what an undeclared capability means.
    NOT_REPEATABLE = "not_repeatable"


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


class AttestationFinding(StrEnum):
    """What a person established about a task whose outcome the laboratory never learned.

    Deliberately three answers and no fourth. A person standing at the bench can see whether an
    operation happened; they cannot see what an instrument measured, and there is no finding here
    that would let them say so. Recovering a reading means running the measurement again.
    """

    #: The operation happened. The task is settled and must not be dispatched again.
    COMPLETED = "completed"
    #: The operation did not happen, so repeating it carries the risk it always did and no more.
    DID_NOT_OCCUR = "did_not_occur"
    #: Neither is established, or the work should stop regardless. Nothing further is attempted.
    ABANDONED = "abandoned"
