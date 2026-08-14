"""Turn a command line into an agent.

The benchmark takes an agent as a callable and knows nothing about how one is built. This is the
adapter that makes that useful outside Python: an agent is anything that can be started as a
process in a directory, which covers a coding harness, a shell script, a compiled binary, and
somebody's in-house orchestrator that will never be a pip package.

It also means the thing being measured is the whole harness rather than the model inside it. That
is the honest unit. A model that scores badly through one harness and well through another has told
you something about the harness, and a benchmark that could only ever see the model would report
the difference as a property of the model.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

from .models import BenchmarkTask
from .running import Agent, AgentOutcome

#: Substituted into the command before it is started.
PROMPT = "{prompt}"
LABORATORY = "{laboratory}"

#: How much of a failing process's output to quote back. Enough to see the traceback that ended it,
#: short enough that a report of fifty failed attempts stays readable.
_QUOTED_OUTPUT = 2000


def _substituted(command: Sequence[str], task: BenchmarkTask, laboratory: Path) -> list[str]:
    return [
        argument.replace(PROMPT, task.prompt).replace(LABORATORY, str(laboratory))
        for argument in command
    ]


class _Usage(NamedTuple):
    """What a harness reported spending. Absent fields are zero rather than unknown."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def _reported_usage(stdout: str) -> _Usage:
    """Read what the harness said it spent, if it said anything.

    The convention is one JSON object on the last line of stdout, carrying any of `input_tokens`,
    `output_tokens` and `cost_usd`. It is optional and unenforced: a harness that reports nothing
    scores exactly the same and reports zero cost, which is visibly zero rather than quietly wrong.

    Token counts come from the harness because they come from the provider, and the provider's
    count is what the bill is computed from. A tokenizer run locally would agree with it most of
    the time, and "most of the time" is not a unit of currency.
    """
    line = stdout.strip().rsplit("\n", 1)[-1].strip() if stdout.strip() else ""
    if not line.startswith("{"):
        return _Usage()
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return _Usage()
    if not isinstance(payload, dict):
        return _Usage()

    def number(field: str) -> float:
        value = payload.get(field)
        # `bool` is an `int` and `True` is not one token. A negative cost is a bug in the harness
        # rather than a discount, and either way neither is believed.
        if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
            return 0.0
        return float(value)

    return _Usage(
        input_tokens=int(number("input_tokens")),
        output_tokens=int(number("output_tokens")),
        cost_usd=number("cost_usd"),
    )


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Kill the process and anything it started.

    A harness is usually a wrapper that starts the real thing, so killing the process that was
    started leaves the process that matters running, holding the laboratory it was given and
    spending money against a task that has already been scored. The session is what gets signalled.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(Exception):
        await process.wait()


def command_agent(
    command: Sequence[str],
    *,
    timeout_seconds: float = 900.0,
    env: Mapping[str, str] | None = None,
) -> Agent:
    """An agent that runs `command` inside the laboratory it was given.

    `{prompt}` and `{laboratory}` in any argument are replaced before the process starts. A command
    naming neither is handed the prompt on stdin, which is what most harnesses read by default.

    The process runs with the laboratory as its working directory, so a harness that knows nothing
    about this benchmark can find the manifest where a manifest is normally found. It is a
    throwaway copy, which is what makes handing a directory to an arbitrary command reasonable.
    """
    if not command:
        raise ValueError("an agent needs a command to run")
    baseline = dict(os.environ)
    baseline.update(env or {})

    async def agent(task: BenchmarkTask, laboratory: Path) -> AgentOutcome:
        arguments = _substituted(command, task, laboratory)
        # A command naming `{laboratory}` but not `{prompt}` still has to be told what to do, so
        # this asks whether the prompt was placed rather than whether anything was substituted.
        on_stdin = not any(PROMPT in argument for argument in command)

        process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=laboratory,
            env=baseline,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # So a timeout can reach the harness's children as well as the harness.
            start_new_session=True,
        )
        fed = task.prompt.encode() if on_stdin else None
        try:
            out, err = await asyncio.wait_for(process.communicate(fed), timeout=timeout_seconds)
        except TimeoutError:
            await _terminate(process)
            # Graded anyway by the caller: an agent that did the work and then hung still did the
            # work, and the laboratory's records are what settle that rather than the exit status.
            return AgentOutcome(error=f"the agent did not finish within {timeout_seconds:g}s")

        stdout = out.decode(errors="replace")
        usage = _reported_usage(stdout)
        error = None
        if process.returncode:
            quoted = (err.decode(errors="replace") or stdout).strip()[-_QUOTED_OUTPUT:]
            failed = f"the agent exited {process.returncode}"
            error = f"{failed}: {quoted}" if quoted else failed
        return AgentOutcome(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            error=error,
        )

    return agent
