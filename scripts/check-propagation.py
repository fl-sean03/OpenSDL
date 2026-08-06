"""Fail when the propagation graph stops describing the repository.

`propagation.yaml` is the blast-radius map behind `opensdl propagate`. A tracked file that matches
no node is invisible to that tool: changing it reports no impact, which is indistinguishable from a
change that genuinely has none. This validator makes that state fail instead of pass, so coverage
cannot rot silently the way it did while 17% of tracked files — including every skill and every
script — matched nothing.

It loads the graph through `opensdl_provenance.PropagationGraph` and matches with the same
`fnmatch` call the graph itself uses, so the validator and the tool can never disagree.
"""

from __future__ import annotations

import subprocess
from fnmatch import fnmatch
from pathlib import Path

from opensdl_provenance import PropagationGraph

ROOT = Path(__file__).parents[1]
GRAPH = ROOT / "propagation.yaml"


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(name for name in result.stdout.split("\0") if name)


def main() -> None:
    # Raises on a malformed graph or an edge that names a node that does not exist.
    graph = PropagationGraph.from_file(GRAPH)
    files = tracked_files()
    failures: list[str] = []

    for node in graph.definition.nodes:
        if not node.paths:
            failures.append(f"node {node.id!r} declares no paths and can never match a change")

    patterns = [(node.id, pattern) for node in graph.definition.nodes for pattern in node.paths]

    unmatched = [name for name in files if not any(fnmatch(name, p) for _, p in patterns)]
    if unmatched:
        shown = "\n".join(f"  {name}" for name in unmatched)
        failures.append(
            f"{len(unmatched)} of {len(files)} tracked files match no propagation node, so a "
            f"change to them reports no impact:\n{shown}\n"
            f"  add them to a node in {GRAPH.name}, or add a node that describes them"
        )

    dead = [
        (node_id, pattern)
        for node_id, pattern in patterns
        if not any(fnmatch(name, pattern) for name in files)
    ]
    if dead:
        shown = "\n".join(f"  {node_id}: {pattern}" for node_id, pattern in dead)
        failures.append(
            f"{len(dead)} declared path patterns match no tracked file and describe nothing:\n"
            f"{shown}"
        )

    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"propagation graph covers {len(files)} tracked files "
        f"across {len(graph.nodes)} nodes and {len(graph.definition.edges)} edges"
    )


if __name__ == "__main__":
    main()
