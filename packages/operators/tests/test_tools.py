from pathlib import Path

import pytest

import opensdl_operators.mcp as mcp_module
from opensdl_capabilities import CapabilityRegistry
from opensdl_operators import ContextPackBuilder, OperatorGateway
from opensdl_policy import PolicyEngine
from opensdl_runtime import ReferenceRuntime
from opensdl_schemas import LabManifest
from opensdl_storage import Database, LocalArtifactStore, Repositories


def build_gateway(tmp_path: Path) -> OperatorGateway:
    database = Database("sqlite:///:memory:")
    database.initialize()
    repositories = Repositories(database)
    registry = CapabilityRegistry()
    manifest = LabManifest.model_validate(
        {"metadata": {"name": "Test Lab", "owner": "OpenSDL"}, "spec": {}}
    )
    runtime = ReferenceRuntime(
        registry,
        repositories,
        PolicyEngine(),
        LocalArtifactStore(tmp_path / "artifacts", repositories),
    )
    builder = ContextPackBuilder(manifest, registry, repositories, "test/v1")
    return OperatorGateway(runtime, repositories, builder)


def test_only_the_executing_tool_declares_side_effects(tmp_path: Path) -> None:
    """The tool surface is what an agent reads before deciding whether an action is safe.

    A read-only tool that claims side effects makes an agent needlessly cautious; an executing
    tool that claims none invites an agent to call it freely. `capability.execute` is the only
    entry point that can move physical equipment, so it must be the only one carrying a warning.
    """
    specs = build_gateway(tmp_path).tool_specs()

    with_side_effects = {spec.name for spec in specs if spec.side_effects}
    assert with_side_effects == {"capability.execute"}


def test_every_advertised_tool_is_named_described_and_unique(tmp_path: Path) -> None:
    specs = build_gateway(tmp_path).tool_specs()
    names = [spec.name for spec in specs]

    assert len(names) == len(set(names))
    assert all(spec.description.endswith(".") for spec in specs)
    assert {"lab.describe", "capability.list", "run.inspect", "event.query"} <= set(names)


def test_the_tools_that_take_arguments_declare_their_required_inputs(tmp_path: Path) -> None:
    """An input schema is the only thing telling a caller what a tool needs."""
    specs = {spec.name: spec for spec in build_gateway(tmp_path).tool_specs()}

    assert specs["run.inspect"].input_schema["required"] == ["run_id"]
    assert specs["capability.execute"].input_schema["required"] == ["capability_id", "inputs"]
    assert specs["lab.describe"].input_schema == {}


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
