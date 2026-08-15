"""Put a laboratory into the state a benchmark task starts from.

`opensdl_benchmark` declares what the starting state is and cannot produce it: reaching
`intervention_required` honestly means dispatching a real call and abandoning it, which needs a
running laboratory, and the benchmark package may not start one. So the runner is injected the same
way the agent is, and this is where it is composed.

Nothing here writes a state directly. The lifecycle machine refuses that anyway, and the refusal is
the machine working — a run cannot be declared stranded, it has to actually be stranded.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from opensdl_benchmark import BenchmarkTask, Setup
from opensdl_controller import OpenSDLSystem


async def _dispatch_and_maybe_abandon(task: BenchmarkTask, laboratory: Path) -> None:
    declared = task.setup
    if declared is None:  # pragma: no cover - callers check before calling
        return

    system = OpenSDLSystem.from_manifest(laboratory / task.manifest)
    await system.start()
    try:
        execution = asyncio.create_task(
            system.runtime.execute_capability(
                declared.capability,
                dict(declared.inputs),
                environment=declared.environment,
            )
        )
        if declared.cancel_after_seconds is None:
            await execution
            return

        # Abandon the wait the way a stopped controller abandons one. The instrument is not
        # stopped and nothing reports an outcome, which is what makes the task's state honest:
        # the laboratory genuinely does not know what happened.
        await asyncio.sleep(declared.cancel_after_seconds)
        execution.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await execution
    finally:
        await system.close()


def capability_setup() -> Setup:
    """A setup runner that performs a task's declared `setup` against its laboratory."""

    return _dispatch_and_maybe_abandon
