from __future__ import annotations

from opensdl_adapter_cell_surrogate import CellSurrogateAdapter
from opensdl_core import ExecutionRequest, ExecutionResult


class FakePhysicalCellAdapter(CellSurrogateAdapter):
    """Test double proving that execution metadata can change without changing semantics."""

    name = "fake-physical-cell"

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        result = await super().execute(request)
        return result.model_copy(
            update={
                "metadata": {
                    **result.metadata,
                    "adapter": self.name,
                    "execution_mode": "fake-physical",
                    "fake": True,
                }
            }
        )
