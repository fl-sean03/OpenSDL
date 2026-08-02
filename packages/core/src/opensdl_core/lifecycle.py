from __future__ import annotations

from .enums import RunState, TaskState
from .errors import LifecycleError

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
    RunState.ABORTING: {RunState.ABORTED, RunState.FAILED},
    RunState.ABORTED: set(),
    RunState.FAILED: {RunState.RUNNING},
    RunState.COMPLETED: set(),
}

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
    TaskState.RETRYING: {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.SUCCEEDED: set(),
    TaskState.FAILED: {TaskState.RETRYING, TaskState.RUNNING},
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
