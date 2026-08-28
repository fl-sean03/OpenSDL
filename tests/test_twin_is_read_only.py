"""The twin renders what happened. It never accepts an instruction.

This is the enforcement mechanism for decision D14 in `docs/development/buildout.md`. The digital
twin is a projection: task events reach the evidence store, a deterministic projector turns them
into visual cues, and the viewer renders those. Its entire value is that it can only show what the
runtime actually recorded.

The moment a twin or viewer route accepts a mutating method, that guarantee is gone and the twin
becomes an assertion about the laboratory rather than a record of it. The pressure to add one is
real and arrives disguised as a demo: an interactive scene, a "just move the arm from the viewer"
control, a simulated world someone wired into the wrong layer. A simulated world belongs behind a
capability adapter, where policy, leases, retry safety and provenance all apply to it.

`docs/architecture/digital-twin.md` states the rule in prose. Prose does not fail a build.
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute
from opensdl_api import create_app

#: Anything that is not a read. HEAD and OPTIONS are reads for this purpose.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Path prefixes that belong to the twin and its viewer.
PROJECTION_PREFIXES = ("/twin", "/viewer")

#: The command surface, named so that adding to it is a deliberate act. A new mutating route
#: outside this set fails the second test below, which is the point: the reviewer has to say why.
COMMAND_ROUTES = frozenset(
    {
        ("/tools/{tool_name}", "POST"),
        ("/capabilities/{capability_id}/execute", "POST"),
        ("/runs", "POST"),
    }
)


def _routes(app: Any) -> list[tuple[str, str]]:
    """Every (path, method) pair the application serves, ignoring framework internals."""

    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.append((route.path, method))
    return pairs


def test_no_twin_or_viewer_route_accepts_a_command() -> None:
    """A mutating twin route would let the viewer assert laboratory state it never observed."""

    offenders = [
        f"{method} {path}"
        for path, method in _routes(create_app())
        if path.startswith(PROJECTION_PREFIXES) and method in MUTATING_METHODS
    ]
    assert not offenders, (
        f"the twin gained a command endpoint: {', '.join(sorted(offenders))}. The twin is a "
        "projection of recorded evidence and has no authority to change the laboratory. A "
        "simulated world belongs behind a capability adapter, where policy, leases, retry safety "
        "and provenance apply to it. See docs/development/buildout.md decision D14."
    )


def test_the_command_surface_stays_the_declared_one() -> None:
    """Growth in the command surface should be argued for, so it is listed rather than inferred."""

    actual = {
        (path, method) for path, method in _routes(create_app()) if method in MUTATING_METHODS
    }
    added = sorted(f"{method} {path}" for path, method in actual - COMMAND_ROUTES)
    assert not added, (
        f"undeclared command routes: {', '.join(added)}. Every way to instruct the laboratory is "
        "listed in COMMAND_ROUTES so that adding one is deliberate. If this route is a legitimate "
        "command, add it here and say why in the pull request. See decision D14."
    )
    removed = sorted(f"{method} {path}" for path, method in COMMAND_ROUTES - actual)
    assert not removed, (
        f"declared command routes are gone: {', '.join(removed)}. Update COMMAND_ROUTES to match."
    )
