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


#: The states a run may be claimed for execution from, read off the declared machine rather than
#: listed a second time. `RUNNING` is deliberately absent, and that absence is the whole point:
#: `RUN_TRANSITIONS[RUNNING]` does not contain `RUNNING`, so the machine has always said a running
#: run cannot be started again. `validate_run_transition` could not enforce it, because it returns
#: early when `current == target` — which is right for an idempotent state write and wrong for
#: claiming a run, and is what let two callers both enter `run_workflow` on the same `RUNNING` run.
#: `Repositories.start_run` claims a run from exactly these states in one conditional write.
STARTABLE_RUN_STATES = frozenset(
    state for state, targets in RUN_TRANSITIONS.items() if RunState.RUNNING in targets
)


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
