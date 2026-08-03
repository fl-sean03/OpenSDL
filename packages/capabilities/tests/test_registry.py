from types import SimpleNamespace

import pytest

from opensdl_capabilities import (
    CapabilityAdapter,
    CapabilityRegistry,
    PluginManager,
    run_adapter_conformance,
    validate_reference_adapter_plugins,
)
from opensdl_capabilities import plugins
from opensdl_core import (
    CapabilityDefinition,
    ExecutionRequest,
    ExecutionResult,
    ExecutorType,
)


class EchoAdapter(CapabilityAdapter):
    name = "echo"

    def capability_definitions(self) -> list[CapabilityDefinition]:
        return [
            CapabilityDefinition(
                id="echo",
                name="Echo",
                executor_type=ExecutorType.COMPUTE,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            CapabilityDefinition(
                id="echo.other",
                name="Other echo",
                executor_type=ExecutorType.COMPUTE,
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
        ]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(request_id=request.request_id, output=request.inputs)


class IncompleteAdapter(EchoAdapter):
    name = "incomplete"

    def conformance_cases(self) -> list[ExecutionRequest]:
        return [ExecutionRequest(capability_id="echo", inputs={})]


def test_registry_routes_and_restricts_capabilities() -> None:
    registry = CapabilityRegistry()
    adapter = EchoAdapter()
    registry.register(adapter)
    assert registry.get_adapter("echo") is adapter

    registry.restrict(["echo"])
    assert [item.id for item in registry.list_capabilities()] == ["echo"]
    with pytest.raises(Exception):
        registry.get_definition("echo.other")


@pytest.mark.asyncio
async def test_conformance_requires_case_for_each_capability() -> None:
    report = await run_adapter_conformance(IncompleteAdapter())
    assert not report.passed
    coverage = next(item for item in report.checks if item["name"] == "conformance case coverage")
    assert coverage["missing"] == ["echo.other"]


def test_plugin_manager_rejects_duplicate_entry_point_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = [
        SimpleNamespace(name="simulated-lab"),
        SimpleNamespace(name="simulated-lab"),
    ]

    def fake_entry_points(*, group: str) -> list[SimpleNamespace]:
        return duplicate if group == "opensdl.adapters" else []

    monkeypatch.setattr(plugins, "entry_points", fake_entry_points)
    with pytest.raises(LookupError, match="duplicate adapter plugin entry points"):
        PluginManager()


def test_reference_plugin_validation_accepts_installed_references() -> None:
    validate_reference_adapter_plugins(["local-compute", "simulated-lab"])


def test_reference_plugin_validation_rejects_shadowed_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow = SimpleNamespace(
        name="simulated-lab",
        value="vendor_hardware.adapter:PhysicalAdapter",
        dist=SimpleNamespace(name="vendor-hardware"),
    )

    def fake_entry_points(*, group: str) -> list[SimpleNamespace]:
        return [shadow] if group == "opensdl.adapters" else []

    monkeypatch.setattr(plugins, "entry_points", fake_entry_points)
    with pytest.raises(LookupError, match="resolved to"):
        validate_reference_adapter_plugins(["simulated-lab"])
