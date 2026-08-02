from opensdl_operators import ToolSpec


def test_tool_spec_declares_side_effects() -> None:
    spec = ToolSpec(name="x", description="x", side_effects=["writes data"])
    assert spec.side_effects == ["writes data"]
