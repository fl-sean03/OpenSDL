from __future__ import annotations

from typing import Any

from pydantic import Field

from opensdl_core import OpenSDLModel
from opensdl_storage import RepositoryStore


class GraphNode(OpenSDLModel):
    id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(OpenSDLModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ResearchGraph(OpenSDLModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def build_run_graph(repositories: RepositoryStore, run_id: str) -> ResearchGraph:
    run = repositories.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    nodes = [GraphNode(id=run.id, type="Run", properties=run.model_dump(mode="json"))]
    edges: list[GraphEdge] = []
    for task in repositories.list_tasks(run_id):
        nodes.append(GraphNode(id=task.id, type="Task", properties=task.model_dump(mode="json")))
        edges.append(GraphEdge(source=run.id, target=task.id, type="hasTask"))
    for artifact in repositories.list_artifacts(run_id=run_id):
        nodes.append(
            GraphNode(id=artifact.id, type="Artifact", properties=artifact.model_dump(mode="json"))
        )
        edges.append(
            GraphEdge(source=artifact.task_id or run.id, target=artifact.id, type="generated")
        )
    return ResearchGraph(nodes=nodes, edges=edges)
