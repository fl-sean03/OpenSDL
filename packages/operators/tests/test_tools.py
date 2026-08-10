from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest

import opensdl_operators.mcp as mcp_module
from opensdl_adapter_simulated_lab.adapter import SimulatedLabAdapter
from opensdl_capabilities import CapabilityRegistry
from opensdl_core import EventRecord, Resource, ValidationError
from opensdl_operators import ContextPackBuilder, OperatorGateway
from opensdl_operators.tools import MAX_EVENT_LIMIT, TOOL_SPECS
from opensdl_policy import PolicyEngine
from opensdl_runtime import ReferenceRuntime
from opensdl_schemas import LabManifest
from opensdl_storage import Database, LocalArtifactStore, Repositories

TOOL_NAMES = {
    "describe_lab",
    "list_capabilities",
    "inspect_run",
    "query_events",
    "execute_capability",
    "list_campaigns",
    "inspect_campaign",
}
MIX_INPUTS: dict[str, Any] = {
    "sample_id": "tool-1",
    "red_fraction": 0.5,
    "blue_fraction": 0.5,
    "total_mass_g": 5,
}


def build_gateway(tmp_path: Path, *, equipped: bool = False) -> OperatorGateway:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    if equipped:
        registry.register(SimulatedLabAdapter({"seed": 7, "color_noise": 0}))
        for resource_id in ("virtual-mixer", "virtual-colorimeter", "virtual-balance"):
            repositories.upsert_resource(
                Resource(id=resource_id, name=resource_id, type="simulator")
            )
    manifest = LabManifest.model_validate(
        {"metadata": {"name": "Test Lab", "owner": "OpenSDL"}, "spec": {}}
    )
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(default_effect="allow"),
        LocalArtifactStore(tmp_path / "artifacts", repositories),
    )
    builder = ContextPackBuilder(manifest, registry, repositories, "test/v1")
    return OperatorGateway(runtime, repositories, builder)


def _structured(result: Any) -> Any:
    """Read a tool's value out of the `CallToolResult` an `MCPServer` call returns."""
    payload = result.structured_content
    return payload.get("result", payload) if isinstance(payload, dict) else payload


def test_only_the_executing_tool_declares_side_effects(tmp_path: Path) -> None:
    """The tool surface is what an agent reads before deciding whether an action is safe.

    A read-only tool that claims side effects makes an agent needlessly cautious; an executing
    tool that claims none invites an agent to call it freely. `execute_capability` is the only
    entry point that can move physical equipment, so it must be the only one carrying a warning.
    """
    specs = build_gateway(tmp_path).tool_specs()

    with_side_effects = {spec.name for spec in specs if spec.side_effects}
    assert with_side_effects == {"execute_capability"}


def test_every_advertised_tool_is_named_described_and_unique(tmp_path: Path) -> None:
    specs = build_gateway(tmp_path).tool_specs()
    names = [spec.name for spec in specs]

    assert len(names) == len(set(names))
    assert all(spec.description.endswith(".") for spec in specs)
    assert set(names) == TOOL_NAMES


def test_every_advertised_tool_name_is_valid_where_it_will_be_used(tmp_path: Path) -> None:
    """A dotted name is rejected by the tool-name grammar most MCP clients enforce."""
    for spec in build_gateway(tmp_path).tool_specs():
        assert spec.name.replace("_", "").replace("-", "").isalnum(), spec.name


def test_every_declared_argument_is_described(tmp_path: Path) -> None:
    """`required` without `properties` names a mandatory field and never says what goes in it."""
    for spec in build_gateway(tmp_path).tool_specs():
        schema = spec.input_schema
        assert schema["type"] == "object", spec.name
        properties = schema["properties"]
        assert set(schema.get("required", [])) <= set(properties), spec.name
        assert all("type" in value for value in properties.values()), spec.name


async def test_every_advertised_tool_can_actually_be_dispatched(tmp_path: Path) -> None:
    """The catalogue used to publish five names with no dispatcher anywhere in the project.

    An agent that trusted it built calls that could not be made. Every advertised name must reach
    real code, including the one that executes laboratory work.
    """
    gateway = build_gateway(tmp_path, equipped=True)

    assert {spec.name for spec in TOOL_SPECS} == TOOL_NAMES
    assert (await gateway.call_tool("describe_lab"))["environment"] == "simulation"
    assert [item["id"] for item in await gateway.call_tool("list_capabilities")]
    executed = await gateway.call_tool(
        "execute_capability",
        {"capability_id": "sim.mix_color", "inputs": MIX_INPUTS},
    )
    run_id = executed["run"]["id"]
    assert executed["run"]["state"] == "completed"
    assert (await gateway.call_tool("inspect_run", {"run_id": run_id}))["run"]["id"] == run_id
    assert await gateway.call_tool("query_events", {"run_id": run_id, "limit": 10})


async def test_an_unknown_tool_names_the_ones_that_exist(tmp_path: Path) -> None:
    gateway = build_gateway(tmp_path)

    with pytest.raises(LookupError, match="unknown tool 'capability.execute'"):
        await gateway.call_tool("capability.execute", {})


async def test_tool_arguments_are_checked_against_the_schema_the_caller_was_given(
    tmp_path: Path,
) -> None:
    gateway = build_gateway(tmp_path)

    with pytest.raises(ValidationError):
        await gateway.call_tool("inspect_run", {})
    with pytest.raises(ValidationError):
        await gateway.call_tool("inspect_run", {"run_id": "run-1", "typo": 1})


async def test_the_event_query_is_bounded(tmp_path: Path) -> None:
    """An unbounded limit asks for the laboratory's entire permanent event log in one reply."""
    gateway = build_gateway(tmp_path)

    with pytest.raises(ValidationError):
        await gateway.call_tool("query_events", {"limit": MAX_EVENT_LIMIT + 1})
    with pytest.raises(ValidationError):
        gateway.query_events(limit=0)
    assert gateway.query_events(limit=MAX_EVENT_LIMIT) == []


async def test_the_mcp_server_registers_and_runs_the_tools_it_advertises(tmp_path: Path) -> None:
    """The five MCP registrations, including the write path, had never once been executed.

    The only test patched the import so that it raised. This one builds the real server against
    the real optional dependency and calls every tool through it. It is skipped, and therefore
    proves nothing, in any environment that does not install the `mcp` extra.

    An installed-but-unservable `mcp` fails rather than skips. Skipping is right when the extra is
    absent and wrong when it is present, because the only condition that produces it is a declared
    floor below what this code imports — and that is the case where the test needs to speak. It
    would otherwise go quiet at exactly the moment the transport stopped working.
    """
    if find_spec("mcp") is None:
        pytest.skip("the optional 'mcp' extra is not installed")
    assert mcp_module.mcp_available(), (
        f"'mcp' is installed without {mcp_module.SERVER_MODULE}, so this laboratory declares an"
        " MCP transport it cannot start; the extra requires mcp>=2"
    )
    gateway = build_gateway(tmp_path, equipped=True)

    server = mcp_module.build_mcp_server(gateway)
    registered = {tool.name: tool for tool in await server.list_tools()}

    assert set(registered) == {spec.name for spec in TOOL_SPECS}
    for spec in TOOL_SPECS:
        tool = registered[spec.name]
        assert tool.description == spec.description
        declared = set(spec.input_schema.get("required", []))
        assert set(tool.input_schema.get("required", [])) == declared, spec.name

    await server.call_tool("describe_lab", {})
    await server.call_tool("list_capabilities", {})
    executed = await server.call_tool(
        "execute_capability",
        {"capability_id": "sim.mix_color", "inputs": MIX_INPUTS},
    )
    run_id = _structured(executed)["run"]["id"]
    inspected = _structured(await server.call_tool("inspect_run", {"run_id": run_id}))
    assert inspected["run"]["id"] == run_id
    assert _structured(await server.call_tool("query_events", {"run_id": run_id, "limit": 5}))


def test_optional_mcp_loader_reports_availability_and_missing_dependency(
    monkeypatch,
) -> None:
    monkeypatch.setattr(mcp_module, "find_spec", lambda name: None)
    assert not mcp_module.mcp_available()
    monkeypatch.setattr(mcp_module, "find_spec", lambda name: object())
    assert mcp_module.mcp_available()

    def missing_module(name: str):
        raise ImportError(name)

    monkeypatch.setattr(mcp_module, "import_module", missing_module)
    with pytest.raises(RuntimeError, match="optional MCP dependency"):
        mcp_module.build_mcp_server(None)  # type: ignore[arg-type]


def _campaign_events(campaign_id: str) -> list[EventRecord]:
    return [
        EventRecord(
            type="CampaignStarted",
            actor_id="software/campaign",
            campaign_id=campaign_id,
            payload={
                "workflowId": "color-mix-and-score",
                "workflowVersion": "0.1.0",
                "environment": "simulation",
                "operatorId": "software/campaign",
                "maxIterations": 2,
                "scoreOutput": "score",
                "minimize": True,
                "targetScore": None,
                "maxConsecutiveFailures": 3,
                "maxDurationSeconds": None,
                "iterationIdInput": "sample_id",
                "baseInputs": {"total_mass_g": 5.0},
            },
        ),
        EventRecord(
            type="CampaignIterationStarted",
            actor_id="software/campaign",
            campaign_id=campaign_id,
            payload={
                "iteration": 0,
                "candidate": {"red_fraction": 0.5},
                "runId": "run-campaign-0",
                "environment": "simulation",
            },
        ),
    ]


async def test_an_agent_can_see_and_read_a_campaign_through_the_tool_surface(
    tmp_path: Path,
) -> None:
    """A campaign appeared in no tool, no route and no context pack: it was Python-only.

    An agent asking what its laboratory is doing could not learn that the laboratory was mid
    search, could not list the campaigns that had run, and could not read one back.
    """
    gateway = build_gateway(tmp_path)
    for event in _campaign_events("campaign-tool"):
        gateway.repositories.append_event(event)

    listed = await gateway.call_tool("list_campaigns")
    assert [item["campaign_id"] for item in listed] == ["campaign-tool"]
    assert listed[0]["state"] == "running"

    inspected = await gateway.call_tool("inspect_campaign", {"campaign_id": "campaign-tool"})
    assert inspected["campaign"]["campaign_id"] == "campaign-tool"
    assert inspected["campaign"]["environment"] == "simulation"
    assert [item["run_id"] for item in inspected["campaign"]["iterations"]] == ["run-campaign-0"]
    assert {event["type"] for event in inspected["events"]} == {
        "CampaignStarted",
        "CampaignIterationStarted",
    }

    described = await gateway.call_tool("describe_lab")
    assert [item["campaign_id"] for item in described["active_campaigns"]] == ["campaign-tool"]


async def test_a_campaign_nothing_recorded_is_reported_as_absent(tmp_path: Path) -> None:
    gateway = build_gateway(tmp_path)

    with pytest.raises(KeyError):
        await gateway.call_tool("inspect_campaign", {"campaign_id": "campaign-nothing"})


async def test_events_can_be_queried_by_campaign(tmp_path: Path) -> None:
    """A campaign identifier reaches every run and task event, so history is one query."""
    gateway = build_gateway(tmp_path)
    for event in _campaign_events("campaign-query"):
        gateway.repositories.append_event(event)
    gateway.repositories.append_event(EventRecord(type="RunCreated", run_id="run-unrelated"))

    scoped = await gateway.call_tool("query_events", {"campaign_id": "campaign-query"})

    assert {event["campaign_id"] for event in scoped} == {"campaign-query"}
    assert len(scoped) == 2
