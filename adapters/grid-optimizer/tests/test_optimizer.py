from opensdl_adapter_grid_optimizer import GridOptimizer


def test_grid_optimizer_order() -> None:
    optimizer = GridOptimizer({"parameters": {"x": [1, 2], "y": [3, 4]}})
    assert optimizer.suggest([]) == {"x": 1, "y": 3}
