from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Any

from .tools import OperatorGateway


def mcp_available() -> bool:
    return find_spec("mcp") is not None


def build_mcp_server(gateway: OperatorGateway) -> Any:
    """Expose the configured gateway through MCP when the optional package is installed.

    Execution is not artificially reduced to read-only access. Calls pass through the same
    capability validation, policy evaluation, resource leasing, persistence, and provenance
    path as the CLI, SDK, and HTTP API.
    """
    try:
        FastMCP = import_module("mcp.server.fastmcp").FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "install the optional MCP dependency to serve this interface"
        ) from exc

    server = FastMCP("OpenSDL")

    @server.tool()
    def describe_lab() -> dict[str, Any]:
        return gateway.describe_lab()

    @server.tool()
    def list_capabilities() -> list[dict[str, Any]]:
        return [
            capability.model_dump(mode="json")
            for capability in gateway.context_builder.registry.list_capabilities()
        ]

    @server.tool()
    def inspect_run(run_id: str) -> dict[str, Any]:
        return gateway.inspect_run(run_id)

    @server.tool()
    def query_events(
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return [
            event.model_dump(mode="json")
            for event in gateway.repositories.list_events(run_id=run_id, limit=limit)
        ]

    @server.tool()
    async def execute_capability(
        capability_id: str,
        inputs: dict[str, Any],
        operator_id: str = "operator/mcp",
    ) -> dict[str, Any]:
        return await gateway.execute_capability(
            capability_id,
            inputs,
            operator_id=operator_id,
            environment=gateway.context_builder.manifest.spec.environment,
        )

    return server
