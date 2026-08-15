"""The committed showcase must still be what the code produces.

`plates.json` is the campaign behind the frame in the README: every well of every round, what went
into it, and what the colorimeter read. The frame is rendered from that file, so the file is the
claim, and nothing until now re-derived it. A change to the optimizer, the dye model, or the
instrument's noise would have left a published picture describing a campaign the code no longer
runs, and every test would still have passed — the campaign is an example, and examples are not on
the default test path.

The comparison ignores identifiers and keeps everything else. A campaign mints a fresh
`campaign_id` and a fresh `run_id` per well on every execution, so byte equality is not available
and demanding it would make this fail for the one reason that means nothing. What must not move is
the science: the recipes tried, the colours measured, the errors, and where the search ended up.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

EXAMPLE = Path(__file__).resolve().parents[1]
COMMITTED = EXAMPLE / "plates.json"

#: Minted fresh on every run and carrying no scientific content.
VOLATILE = frozenset({"campaign_id", "run_id"})


def _stable(node: Any) -> Any:
    """The document with its identifiers removed, at any depth."""

    if isinstance(node, dict):
        return {key: _stable(value) for key, value in node.items() if key not in VOLATILE}
    if isinstance(node, list):
        return [_stable(value) for value in node]
    return node


def _first_difference(committed: Any, regenerated: Any, path: str = "") -> str | None:
    """Where the two documents first disagree, in enough detail to act on.

    A bare "the campaign changed" would send somebody diffing a six-hundred-well JSON file by eye.
    """
    if isinstance(committed, dict) and isinstance(regenerated, dict):
        for key in sorted(set(committed) | set(regenerated)):
            if key not in committed:
                return f"{path}.{key}: only in the regenerated campaign"
            if key not in regenerated:
                return f"{path}.{key}: only in the committed campaign"
            found = _first_difference(committed[key], regenerated[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(committed, list) and isinstance(regenerated, list):
        if len(committed) != len(regenerated):
            return f"{path}: {len(committed)} entries committed, {len(regenerated)} regenerated"
        for index, (left, right) in enumerate(zip(committed, regenerated, strict=True)):
            found = _first_difference(left, right, f"{path}[{index}]")
            if found:
                return found
        return None
    if committed != regenerated:
        return f"{path}: committed {committed!r}, regenerated {regenerated!r}"
    return None


@pytest.mark.e2e
def test_the_committed_campaign_is_what_the_code_still_produces(tmp_path: Path) -> None:
    """Re-run the published campaign and compare it with the file the frame was rendered from."""

    laboratory = tmp_path / "discovering-colors"
    # The renders are the output and the store is the previous run's evidence; neither is an input.
    shutil.copytree(
        EXAMPLE,
        laboratory,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__", "renders", "tests"),
    )

    completed = subprocess.run(
        [sys.executable, "run_campaign.py"],
        cwd=laboratory,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]

    regenerated = json.loads((laboratory / "plates.json").read_text(encoding="utf-8"))
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))

    difference = _first_difference(_stable(committed), _stable(regenerated))
    assert difference is None, (
        f"the committed campaign no longer matches what the code produces at {difference}. "
        "The README frame is rendered from this file, so regenerate it and the frame together: "
        "`uv run --locked python examples/discovering-colors/run_campaign.py`"
    )
