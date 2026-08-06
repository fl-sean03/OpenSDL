from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Any

from .tools import DEFAULT_TOOL_OPERATOR, TOOL_SPECS_BY_NAME, OperatorGateway


def mcp_available() -> bool:
    return find_spec("mcp") is not None


def build_mcp_server(gateway: OperatorGateway) -> Any:
    """Expose the configured gateway through MCP when the optional package is installed.

    Every tool here is registered under the name `OperatorGateway.tool_specs` advertises and
    dispatches through `OperatorGateway.call_tool`, so the MCP surface, the catalogue served at
    `GET /tools`, and the code that runs are one thing. They were three: five dotted names in the
    catalogue, five different names here, and no dispatcher for either.

    Execution is not artificially reduced to read-only access. Calls pass through the same
    capability validation, policy evaluation, resource leasing, persistence, and provenance path as
    the CLI, SDK, and HTTP API.
    """
    try:
        FastMCP = import_module("mcp.server.fastmcp").FastMCP
    except ImportError as exc:
        raise RuntimeError("install the optional MCP dependency to serve this interface") from exc

    server = FastMCP("OpenSDL")

    @server.tool(name="describe_lab", description=TOOL_SPECS_BY_NAME["describe_lab"].description)
    async def describe_lab() -> dict[str, Any]:
        return await gateway.call_tool("describe_lab")

    @server.tool(
        name="list_capabilities",
        description=TOOL_SPECS_BY_NAME["list_capabilities"].description,
    )
    async def list_capabilities() -> list[dict[str, Any]]:
        return await gateway.call_tool("list_capabilities")

    @server.tool(name="inspect_run", description=TOOL_SPECS_BY_NAME["inspect_run"].description)
    async def inspect_run(run_id: str) -> dict[str, Any]:
        return await gateway.call_tool("inspect_run", {"run_id": run_id})

    @server.tool(name="query_events", description=TOOL_SPECS_BY_NAME["query_events"].description)
    async def query_events(run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        arguments: dict[str, Any] = {"limit": limit}
        if run_id is not None:
            arguments["run_id"] = run_id
        return await gateway.call_tool("query_events", arguments)

    @server.tool(
        name="execute_capability",
        description=TOOL_SPECS_BY_NAME["execute_capability"].description,
    )
    async def execute_capability(
        capability_id: str,
        inputs: dict[str, Any],
        operator_id: str = DEFAULT_TOOL_OPERATOR,
    ) -> dict[str, Any]:
        return await gateway.call_tool(
            "execute_capability",
            {"capability_id": capability_id, "inputs": inputs, "operator_id": operator_id},
        )

    return server
