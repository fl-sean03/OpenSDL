from __future__ import annotations

from typing import Any

from pydantic import Field

from opensdl_core import OpenSDLModel
from opensdl_runtime import ReferenceRuntime
from opensdl_storage import RepositoryStore

from .context import ContextPackBuilder


class ToolSpec(OpenSDLModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)


class OperatorGateway:
    """Typed boundary shared by CLIs, APIs, MCP adapters, and automation systems."""

    def __init__(
        self,
        runtime: ReferenceRuntime,
        repositories: RepositoryStore,
        context_builder: ContextPackBuilder,
    ) -> None:
        self.runtime = runtime
        self.repositories = repositories
        self.context_builder = context_builder

    def tool_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name="lab.describe", description="Return current laboratory context."),
            ToolSpec(name="capability.list", description="List executable capabilities."),
            ToolSpec(
                name="run.inspect",
                description="Inspect a durable run.",
                input_schema={"type": "object", "required": ["run_id"]},
            ),
            ToolSpec(
                name="event.query",
                description="Query execution events.",
                input_schema={"type": "object", "properties": {"run_id": {"type": "string"}}},
            ),
            ToolSpec(
                name="capability.execute",
                description="Execute one declared capability through policy and provenance.",
                input_schema={"type": "object", "required": ["capability_id", "inputs"]},
                side_effects=["may execute configured laboratory capability"],
            ),
        ]

    def describe_lab(self) -> dict[str, Any]:
        return self.context_builder.build().model_dump(mode="json")

    def inspect_run(self, run_id: str) -> dict[str, Any]:
        run = self.repositories.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return {
            "run": run.model_dump(mode="json"),
            "tasks": [
                task.model_dump(mode="json") for task in self.repositories.list_tasks(run_id)
            ],
            "events": [
                event.model_dump(mode="json")
                for event in self.repositories.list_events(run_id=run_id)
            ],
        }

    async def execute_capability(
        self, capability_id: str, inputs: dict[str, Any], *, operator_id: str, environment: str
    ) -> dict[str, Any]:
        run = await self.runtime.execute_capability(
            capability_id, inputs, operator_id=operator_id, environment=environment
        )
        return self.inspect_run(run.id)
