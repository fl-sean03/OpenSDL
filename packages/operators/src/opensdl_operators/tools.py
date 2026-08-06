from __future__ import annotations

from typing import Any

from pydantic import Field

from opensdl_capabilities import validate_instance
from opensdl_core import OpenSDLModel
from opensdl_runtime import CampaignReader, ReferenceRuntime
from opensdl_storage import RepositoryStore

from .context import ContextPackBuilder

#: The largest event page one tool call may ask for. The event log is append-only and unbounded.
MAX_EVENT_LIMIT = 1000

#: The operator identity recorded for a tool call that does not assert one. It is not a credential;
#: see `docs/reference/api.md` on caller-asserted `operator_id`.
DEFAULT_TOOL_OPERATOR = "operator/tool"


class ToolSpec(OpenSDLModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)


#: The tool surface an agent reads before deciding what it is allowed to do.
#:
#: Every name here is dispatchable through `OperatorGateway.call_tool`, and `build_mcp_server`
#: registers exactly these names against exactly these arguments. The catalogue previously
#: published five dotted names — `lab.describe`, `capability.list`, `run.inspect`, `event.query`,
#: `capability.execute` — that existed nowhere else in the project, while MCP registered five
#: different ones and nothing dispatched either set. The underscored names win because they are the
#: ones MCP already served and because a dot is not accepted by the tool-name grammar most MCP
#: clients enforce. Every schema names its properties: `required` without `properties` told a
#: caller a field was mandatory without telling it what to put there.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="describe_lab",
        description="Return current laboratory context.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="list_capabilities",
        description="List executable capabilities.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="inspect_run",
        description="Inspect a durable run, its tasks, and its events.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string", "description": "Durable run identifier."}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="query_events",
        description="Query execution events.",
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Restrict to one run."},
                "campaign_id": {
                    "type": "string",
                    "description": "Restrict to one campaign, including its runs and tasks.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_EVENT_LIMIT,
                    "default": 200,
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="list_campaigns",
        description="List closed-loop campaigns and whether each one is still running.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="inspect_campaign",
        description="Inspect one campaign, its iterations, and its events.",
        input_schema={
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "Campaign identifier recorded on every event it emitted.",
                }
            },
            "required": ["campaign_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="execute_capability",
        description="Execute one declared capability through policy and provenance.",
        input_schema={
            "type": "object",
            "properties": {
                "capability_id": {"type": "string", "description": "Declared capability."},
                "inputs": {"type": "object", "description": "Capability inputs."},
                "operator_id": {
                    "type": "string",
                    "description": "Subject policy evaluates and provenance records.",
                    "default": DEFAULT_TOOL_OPERATOR,
                },
            },
            "required": ["capability_id", "inputs"],
            "additionalProperties": False,
        },
        side_effects=["may execute configured laboratory capability"],
    ),
)
TOOL_SPECS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


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
        return list(TOOL_SPECS)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Dispatch one advertised tool.

        This is the whole point of publishing a catalogue: what `tool_specs` advertises is what
        this method runs, so an agent that reads the surface and builds a call can make it. The
        arguments are validated against the schema the caller was given, which is what turns a
        typo into one contract error instead of a `TypeError` from a keyword expansion.
        """
        spec = TOOL_SPECS_BY_NAME.get(name)
        if spec is None:
            available = ", ".join(sorted(TOOL_SPECS_BY_NAME))
            raise LookupError(f"unknown tool {name!r}; available: {available}")
        given = dict(arguments or {})
        validate_instance(given, spec.input_schema, label=f"{name} arguments")
        if name == "describe_lab":
            return self.describe_lab()
        if name == "list_capabilities":
            return self.list_capabilities()
        if name == "inspect_run":
            return self.inspect_run(given["run_id"])
        if name == "query_events":
            return self.query_events(
                run_id=given.get("run_id"),
                campaign_id=given.get("campaign_id"),
                limit=given.get("limit", 200),
            )
        if name == "list_campaigns":
            return self.list_campaigns()
        if name == "inspect_campaign":
            return self.inspect_campaign(given["campaign_id"])
        return await self.execute_capability(
            given["capability_id"],
            given["inputs"],
            operator_id=given.get("operator_id", DEFAULT_TOOL_OPERATOR),
            environment=self.context_builder.manifest.spec.environment,
        )

    def describe_lab(self) -> dict[str, Any]:
        return self.context_builder.build().model_dump(mode="json")

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [
            definition.model_dump(mode="json")
            for definition in self.context_builder.registry.list_capabilities()
        ]

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

    def query_events(
        self,
        *,
        run_id: str | None = None,
        campaign_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        validate_instance(
            {"limit": limit},
            TOOL_SPECS_BY_NAME["query_events"].input_schema,
            label="query_events arguments",
        )
        return [
            event.model_dump(mode="json")
            for event in self.repositories.list_events(
                run_id=run_id,
                campaign_id=campaign_id,
                limit=limit,
            )
        ]

    def list_campaigns(self) -> list[dict[str, Any]]:
        """Every campaign the store has a record of, newest first.

        This is a scan of the event log rather than a query against a table, because a campaign has
        neither a table nor a row: its state is the events it emitted. See
        `opensdl_runtime.CampaignReader`.
        """
        return [
            record.model_dump(mode="json") for record in CampaignReader(self.repositories).list()
        ]

    def inspect_campaign(self, campaign_id: str) -> dict[str, Any]:
        """One campaign and the events it produced, mirroring `inspect_run`.

        The events include every run and task event of every iteration, because a campaign
        identifier reaches them all. `KeyError` when nothing was recorded under this identifier.
        """
        record = CampaignReader(self.repositories).get(campaign_id)
        return {
            "campaign": record.model_dump(mode="json"),
            "events": [
                event.model_dump(mode="json")
                for event in self.repositories.list_events(campaign_id=campaign_id)
            ],
        }

    async def execute_capability(
        self, capability_id: str, inputs: dict[str, Any], *, operator_id: str, environment: str
    ) -> dict[str, Any]:
        run = await self.runtime.execute_capability(
            capability_id, inputs, operator_id=operator_id, environment=environment
        )
        return self.inspect_run(run.id)
