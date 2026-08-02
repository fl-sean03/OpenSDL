from __future__ import annotations

from collections import deque
from fnmatch import fnmatch
from pathlib import Path

import yaml
from pydantic import Field

from opensdl_core import OpenSDLModel


class PropagationNode(OpenSDLModel):
    id: str
    paths: list[str] = Field(default_factory=list)
    description: str = ""


class PropagationEdge(OpenSDLModel):
    source: str
    target: str
    reason: str = ""


class PropagationDefinition(OpenSDLModel):
    version: str = "v0alpha1"
    nodes: list[PropagationNode]
    edges: list[PropagationEdge]


class PropagationImpact(OpenSDLModel):
    directly_changed: list[str]
    affected_nodes: list[str]
    affected_paths: list[str]
    reasons: dict[str, list[str]] = Field(default_factory=dict)


class PropagationGraph:
    def __init__(self, definition: PropagationDefinition) -> None:
        self.definition = definition
        self.nodes = {node.id: node for node in definition.nodes}
        self.outgoing: dict[str, list[PropagationEdge]] = {node_id: [] for node_id in self.nodes}
        for edge in definition.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ValueError(f"propagation edge references unknown node: {edge}")
            self.outgoing[edge.source].append(edge)

    @classmethod
    def from_file(cls, path: str | Path) -> "PropagationGraph":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(PropagationDefinition.model_validate(data))

    def affected(self, changed_paths: list[str]) -> PropagationImpact:
        direct = {
            node.id
            for node in self.nodes.values()
            if any(fnmatch(path, pattern) for path in changed_paths for pattern in node.paths)
        }
        seen = set(direct)
        queue = deque(direct)
        reasons: dict[str, list[str]] = {node_id: ["direct path match"] for node_id in direct}
        while queue:
            source = queue.popleft()
            for edge in self.outgoing[source]:
                reasons.setdefault(edge.target, []).append(edge.reason or f"depends on {source}")
                if edge.target not in seen:
                    seen.add(edge.target)
                    queue.append(edge.target)
        paths = sorted({pattern for node_id in seen for pattern in self.nodes[node_id].paths})
        return PropagationImpact(
            directly_changed=sorted(direct),
            affected_nodes=sorted(seen),
            affected_paths=paths,
            reasons=reasons,
        )
