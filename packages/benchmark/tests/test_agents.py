"""An agent that is a command line, and the ways one goes wrong.

Nothing here starts a laboratory. What is under test is the contract between the benchmark and an
arbitrary process: where it runs, how it is told what to do, what happens when it fails, and what
of its own account is believed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from opensdl_benchmark import BenchmarkTask, Check, CheckKind, command_agent

TASK = BenchmarkTask(
    id="t",
    category="operate",
    prompt="mix one sample",
    manifest="opensdl.yaml",
    checks=[Check(kind=CheckKind.RUNS_COMPLETED, description="one run")],
)


def _python(script: str) -> list[str]:
    return [sys.executable, "-c", script]


@pytest.mark.asyncio
async def test_the_prompt_arrives_on_stdin_when_the_command_does_not_place_it(
    tmp_path: Path,
) -> None:
    """The default, because most harnesses read a prompt from stdin."""

    agent = command_agent(_python("import sys; open('seen.txt','w').write(sys.stdin.read())"))
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert (tmp_path / "seen.txt").read_text() == "mix one sample"


@pytest.mark.asyncio
async def test_placeholders_are_substituted_into_the_arguments(tmp_path: Path) -> None:
    agent = command_agent(
        _python("import sys; open('seen.txt','w').write('|'.join(sys.argv[1:]))")
        + ["{prompt}", "{laboratory}"]
    )
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert (tmp_path / "seen.txt").read_text() == f"mix one sample|{tmp_path}"


@pytest.mark.asyncio
async def test_a_command_naming_only_the_laboratory_is_still_told_what_to_do(
    tmp_path: Path,
) -> None:
    """The case that decides whether stdin is used, and the one an earlier version got wrong.

    Asking "did anything get substituted" rather than "was the prompt placed" left a command using
    `{laboratory}` alone with no instructions at all, which scores as an agent that chose to do
    nothing rather than as one that was never asked.
    """
    agent = command_agent(
        _python("import sys; open('seen.txt','w').write(sys.stdin.read())") + ["{laboratory}"]
    )
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert (tmp_path / "seen.txt").read_text() == "mix one sample"


@pytest.mark.asyncio
async def test_the_agent_runs_inside_the_laboratory_it_was_given(tmp_path: Path) -> None:
    """So a harness that knows nothing about this benchmark finds the manifest where it expects."""

    agent = command_agent(_python("import os; open('cwd.txt','w').write(os.getcwd())"))
    await agent(TASK, tmp_path)

    assert Path((tmp_path / "cwd.txt").read_text()).resolve() == tmp_path.resolve()


@pytest.mark.asyncio
async def test_a_failing_command_is_an_attempt_that_did_not_happen(tmp_path: Path) -> None:
    """And it quotes the output, because a report of a bare exit code is not diagnosable."""

    agent = command_agent(
        _python("import sys; print('the key was rejected', file=sys.stderr); sys.exit(3)")
    )
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is not None
    assert "exited 3" in outcome.error
    assert "the key was rejected" in outcome.error


@pytest.mark.asyncio
async def test_a_hanging_agent_is_killed_rather_than_waited_on(tmp_path: Path) -> None:
    agent = command_agent(_python("import time; time.sleep(120)"), timeout_seconds=0.5)

    started = time.monotonic()
    outcome = await agent(TASK, tmp_path)
    elapsed = time.monotonic() - started

    assert outcome.error is not None
    assert "did not finish" in outcome.error
    # The point of the timeout is that it returns. A wait that eventually gives up after two
    # minutes is the failure being tested for, not a slower version of passing.
    assert elapsed < 30


@pytest.mark.asyncio
async def test_what_the_harness_says_it_spent_is_read_from_the_last_line(tmp_path: Path) -> None:
    agent = command_agent(
        _python(
            "print('thinking about colours'); "
            'print(\'{"input_tokens": 900, "output_tokens": 120, "cost_usd": 0.004}\')'
        )
    )
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert outcome.input_tokens == 900
    assert outcome.output_tokens == 120
    assert outcome.cost_usd == pytest.approx(0.004)


@pytest.mark.asyncio
async def test_a_harness_that_reports_nothing_reports_zero_rather_than_failing(
    tmp_path: Path,
) -> None:
    """Cost is optional. A harness that cannot report it is still worth benchmarking, and a zero
    that is visibly zero is better than a number invented locally."""

    agent = command_agent(_python("print('done')"))
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert outcome.cost_usd == 0.0
    assert outcome.input_tokens == 0


@pytest.mark.asyncio
async def test_nonsense_usage_is_ignored_rather_than_believed(tmp_path: Path) -> None:
    """A negative cost is a bug in the harness, not a discount."""

    agent = command_agent(_python('print(\'{"cost_usd": -5, "output_tokens": "lots"}\')'))
    outcome = await agent(TASK, tmp_path)

    assert outcome.error is None
    assert outcome.cost_usd == 0.0
    assert outcome.output_tokens == 0


def test_an_agent_needs_something_to_run() -> None:
    with pytest.raises(ValueError, match="a command"):
        command_agent([])
