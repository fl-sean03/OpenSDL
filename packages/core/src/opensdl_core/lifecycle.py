from __future__ import annotations

from .enums import RunState, TaskState
from .errors import LifecycleError

#: Declared run state machine. Enforced by the persistence layer on every state write, so every
#: transition a runtime legitimately performs must appear here.
RUN_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PLANNED: {RunState.QUEUED, RunState.RUNNING, RunState.ABORTED},
    RunState.QUEUED: {RunState.RUNNING, RunState.ABORTED, RunState.FAILED},
    RunState.RUNNING: {
        RunState.PAUSED,
        RunState.INTERVENTION_REQUIRED,
        RunState.ABORTING,
        RunState.FAILED,
        RunState.COMPLETED,
    },
    RunState.PAUSED: {RunState.RUNNING, RunState.ABORTING, RunState.ABORTED},
    RunState.INTERVENTION_REQUIRED: {RunState.RUNNING, RunState.ABORTING, RunState.FAILED},
    # Restart reconciliation also reconciles runs that were aborting when the controller stopped:
    # the abort itself has an unknown outcome and needs a human, not an automatic conclusion.
    RunState.ABORTING: {RunState.ABORTED, RunState.FAILED, RunState.INTERVENTION_REQUIRED},
    RunState.ABORTED: set(),
    RunState.FAILED: {RunState.RUNNING},
    RunState.COMPLETED: set(),
}

#: Declared task state machine. `SUCCEEDED`, `CANCELLED`, and `INTERVENTION_REQUIRED` never lead
#: back to a dispatching state: an action whose outcome is settled or unknown is not replayed.
TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING: {
        TaskState.WAITING_FOR_RESOURCES,
        TaskState.WAITING_FOR_AUTHORIZATION,
        TaskState.RUNNING,
        TaskState.CANCELLED,
        TaskState.FAILED,
    },
    TaskState.WAITING_FOR_RESOURCES: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.WAITING_FOR_AUTHORIZATION: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {
        TaskState.RETRYING,
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.INTERVENTION_REQUIRED,
    },
    # A retried attempt is a dispatched attempt: it can succeed, and it can be cancelled or left
    # ambiguous by a restart exactly as a first attempt can.
    TaskState.RETRYING: {
        TaskState.RUNNING,
        TaskState.SUCCEEDED,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.INTERVENTION_REQUIRED,
    },
    TaskState.SUCCEEDED: set(),
    # Resuming a failed run re-acquires the step's resource leases before dispatching it again.
    TaskState.FAILED: {TaskState.WAITING_FOR_RESOURCES, TaskState.RETRYING, TaskState.RUNNING},
    TaskState.CANCELLED: set(),
    TaskState.INTERVENTION_REQUIRED: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
}


def validate_run_transition(current: RunState, target: RunState) -> None:
    if current == target:
        return
    if target not in RUN_TRANSITIONS[current]:
        raise LifecycleError(f"invalid run transition: {current} -> {target}")


def validate_task_transition(current: TaskState, target: TaskState) -> None:
    if current == target:
        return
    if target not in TASK_TRANSITIONS[current]:
        raise LifecycleError(f"invalid task transition: {current} -> {target}")
