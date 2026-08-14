"""Give an agent a laboratory, let it work, then read what the laboratory recorded.

The agent is injected and this module knows nothing about it. That is deliberate twice over: a
benchmark tied to one provider measures that provider, and a benchmark that cannot be driven by a
scripted agent has no control to check itself against.

Each attempt gets its own copy of the laboratory. Runs, events and artifacts accumulate in the
store, so a second attempt against the same directory would be graded on the first attempt's work
as well as its own, and a suite that leaked state between attempts would report a model improving
as it went.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from opensdl_core import OpenSDLModel
from opensdl_storage import Database, Repositories
from pydantic import Field

from .grading import grade
from .models import BenchmarkReport, BenchmarkTask, TaskAttempt, TaskScore

#: Directories that are the previous occupant's evidence rather than the laboratory's definition.
_NOT_COPIED = shutil.ignore_patterns(".opensdl", "__pycache__", ".git", "renders")


class AgentOutcome(OpenSDLModel):
    """What an agent reports about its own attempt.

    Everything here is the agent's word: what it spent, and whether it fell over. What it achieved
    is not on this model on purpose — that is read from the laboratory, and an agent that could
    report its own success would be grading itself.
    """

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    #: The attempt failing to happen — a transport error, a crash — rather than the agent being
    #: wrong. The two are scored differently: this is retried, being wrong is a result.
    error: str | None = None


#: An agent is anything that will act on a laboratory directory when handed a task.
Agent = Callable[[BenchmarkTask, Path], Awaitable[AgentOutcome]]


def _store_at(laboratory: Path, task: BenchmarkTask) -> Repositories:
    database = Database(f"sqlite:///{(laboratory / task.store).resolve()}")
    database.initialize()
    return Repositories(database)


async def attempt_task(
    task: BenchmarkTask,
    source: Path,
    agent: Agent,
    *,
    repeat: int = 1,
) -> TaskAttempt:
    """One agent, one task, one fresh copy of the laboratory."""

    with TemporaryDirectory(prefix=f"opensdl-benchmark-{task.id}-") as workspace:
        laboratory = Path(workspace) / "lab"
        shutil.copytree(source, laboratory, ignore=_NOT_COPIED)

        started = time.monotonic()
        try:
            reported = await agent(task, laboratory)
        except Exception as exc:  # noqa: BLE001 - an agent that raises is an attempt that failed
            reported = AgentOutcome(error=f"{type(exc).__name__}: {exc}")
        seconds = time.monotonic() - started

        # Graded even when the agent reported an error, because an agent that crashed after doing
        # the work correctly still did the work, and the records are what settle it.
        outcomes = grade(_store_at(laboratory, task), task.checks)

    return TaskAttempt(
        task_id=task.id,
        repeat=repeat,
        outcomes=outcomes,
        seconds=seconds,
        input_tokens=reported.input_tokens,
        output_tokens=reported.output_tokens,
        cost_usd=reported.cost_usd,
        error=reported.error,
    )


async def run_task(
    task: BenchmarkTask,
    source: Path,
    agent: Agent,
    *,
    repeats: int = 1,
) -> TaskScore:
    """Attempt one task the declared number of times.

    Repeats are what turn one lucky answer into a measurement, and every published suite uses
    between one and five of them. They run in sequence rather than together: the point is to sample
    the agent, and attempts racing each other would sample the machine.
    """
    if repeats < 1:
        raise ValueError("a task needs at least one attempt to establish anything")
    attempts = [
        await attempt_task(task, source, agent, repeat=index + 1) for index in range(repeats)
    ]
    return TaskScore(task_id=task.id, category=task.category, attempts=attempts)


async def run_suite(
    tasks: list[BenchmarkTask],
    source_for: Callable[[BenchmarkTask], Path],
    agent: Agent,
    *,
    model: str,
    repeats: int = 1,
) -> BenchmarkReport:
    """Every task, the same agent, the same conditions."""

    scores = [await run_task(task, source_for(task), agent, repeats=repeats) for task in tasks]
    return BenchmarkReport(model=model, scores=scores)
