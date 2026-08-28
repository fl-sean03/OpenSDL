"""Every intervention reason the engine emits is declared, and the declaration is the whole list.

`intervention_required` is the state that says a physical outcome is unknown, and it is the one a
human has to resolve. The benchmark grades on reaching it honestly, a policy may want to route on
why it happened, and two facility features in the buildout plan extend the vocabulary: a long-latency
capability whose answer is overdue, and a resource lease swept after a controller restart.

A reason that is a free string cannot be graded, filtered, or matched by a policy rule, and nothing
would notice a typo. So the vocabulary lives in one frozenset and this test holds the code to it, in
both directions: an emitted reason that is not declared fails, and a declared reason nothing emits
fails too, because a vocabulary that has drifted ahead of the code is the same defect wearing better
clothes.

The scan is over the syntax tree rather than the text. A regular expression would match the reason
strings in the `TaskFailed` and `RunFailed` payloads, which are a different vocabulary and are not
governed here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from opensdl_runtime.engine import INTERVENTION_REASONS

ENGINE = Path(__file__).parents[1] / "src" / "opensdl_runtime" / "engine.py"

#: The event whose reasons this vocabulary governs.
EVENT = "TaskInterventionRequired"


def emitted_reasons() -> set[str]:
    """Every literal `reason` passed in a `TaskInterventionRequired` payload."""

    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    found: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != EVENT:
            continue
        for keyword in node.keywords:
            if keyword.arg != "payload" or not isinstance(keyword.value, ast.Dict):
                continue
            for key, value in zip(keyword.value.keys, keyword.value.values, strict=True):
                if not isinstance(key, ast.Constant) or key.value != "reason":
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.add(value.value)
    return found


def test_every_intervention_reason_is_declared() -> None:
    """An emitted reason outside the vocabulary is invisible to policy and to grading."""

    undeclared = sorted(emitted_reasons() - INTERVENTION_REASONS)
    assert not undeclared, (
        f"engine.py emits {EVENT} with undeclared reasons: {', '.join(undeclared)}. Add them to "
        "INTERVENTION_REASONS so a policy can match on them and the benchmark can grade them."
    )


def test_every_declared_reason_is_emitted() -> None:
    """A vocabulary that has drifted ahead of the code is as wrong as one that lags behind it."""

    unused = sorted(INTERVENTION_REASONS - emitted_reasons())
    assert not unused, (
        f"INTERVENTION_REASONS declares reasons nothing emits: {', '.join(unused)}. Either the "
        "feature that would emit them was dropped, or the emit site was removed. Delete them or "
        "land the feature."
    )


def test_the_scan_finds_the_reasons_that_exist_today() -> None:
    """A scan that silently matched nothing would make both tests above pass forever."""

    reasons = emitted_reasons()
    assert reasons, (
        f"the syntax-tree scan found no {EVENT} payload carrying a literal reason. Either the emit "
        "sites moved, or the payload is built somewhere the scan cannot see, and the two tests "
        "above are now vacuous."
    )
