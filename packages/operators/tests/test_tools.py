import pytest

import opensdl_operators.mcp as mcp_module
from opensdl_operators import ToolSpec


def test_tool_spec_declares_side_effects() -> None:
    spec = ToolSpec(name="x", description="x", side_effects=["writes data"])
    assert spec.side_effects == ["writes data"]


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
