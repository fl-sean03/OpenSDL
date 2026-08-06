"""Pytest plugin that turns a skipped test into a failure.

The scene reproducibility test skips itself when Blender is absent or reports a different version.
That is correct for a developer machine and worthless in CI, where the skip is the only outcome
anyone has ever seen. A job that has installed the recorded Blender must treat a skip as a broken
environment, not as success, so a Blender point release or a renamed executable fails loudly
instead of quietly disabling the strongest correctness check the repository owns.

Enable it by putting `scripts` on `PYTHONPATH` and passing `-p pytest_no_skip`:

    PYTHONPATH=scripts pytest -p pytest_no_skip examples/digital-twin-surrogate/tests

Expected failures (`xfail`) are left alone; they are a declared outcome, not a missing one.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.skipped and not hasattr(report, "wasxfail"):
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} was skipped where skipping is not permitted: {_reason(report)}"
        )
    return report


def _reason(report: pytest.TestReport) -> str:
    longrepr: Any = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    return str(longrepr)
