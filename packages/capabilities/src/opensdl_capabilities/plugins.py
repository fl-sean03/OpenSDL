from __future__ import annotations

import re
from collections.abc import Iterable
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from .adapter import CapabilityAdapter


REFERENCE_ADAPTERS = {
    "simulated-lab": "opensdl_adapter_simulated_lab.adapter:SimulatedLabAdapter",
    "local-compute": "opensdl_adapter_local_compute.adapter:LocalComputeAdapter",
    "human-task": "opensdl_adapter_human_task.adapter:HumanTaskAdapter",
}
REFERENCE_ADAPTER_DISTRIBUTIONS = {
    "simulated-lab": "opensdl-adapter-simulated-lab",
    "local-compute": "opensdl-adapter-local-compute",
    "human-task": "opensdl-adapter-human-task",
}
REFERENCE_OPTIMIZERS = {
    "grid": "opensdl_adapter_grid_optimizer.optimizer:GridOptimizer",
}
REFERENCE_DOMAIN_PACKS = {
    "materials": "opensdl_domain_materials.pack:get_pack",
    "chemistry": "opensdl_domain_chemistry.pack:get_pack",
    "physics": "opensdl_domain_physics.pack:get_pack",
}


class PluginManager:
    def __init__(self) -> None:
        self._adapter_points = _index_entry_points("opensdl.adapters", "adapter")
        self._optimizer_points = _index_entry_points("opensdl.optimizers", "optimizer")
        self._domain_points = _index_entry_points("opensdl.domain_packs", "domain pack")

    def available_adapters(self) -> list[str]:
        return sorted(set(self._adapter_points) | set(REFERENCE_ADAPTERS))

    def load_adapter(self, plugin: str, config: dict[str, Any] | None = None) -> CapabilityAdapter:
        if plugin in self._adapter_points:
            factory = self._adapter_points[plugin].load()
        elif plugin in REFERENCE_ADAPTERS:
            factory = self._load_reference(REFERENCE_ADAPTERS[plugin])
        else:
            self._require(self._adapter_points, plugin, "adapter")
            raise AssertionError("unreachable")
        adapter = factory(config or {})
        if not isinstance(adapter, CapabilityAdapter):
            raise TypeError(f"plugin {plugin!r} did not produce a CapabilityAdapter")
        return adapter

    def load_optimizer(self, plugin: str, config: dict[str, Any] | None = None) -> Any:
        if plugin in self._optimizer_points:
            factory = self._optimizer_points[plugin].load()
        elif plugin in REFERENCE_OPTIMIZERS:
            factory = self._load_reference(REFERENCE_OPTIMIZERS[plugin])
        else:
            self._require(self._optimizer_points, plugin, "optimizer")
            raise AssertionError("unreachable")
        return factory(config or {})

    def load_domain_pack(self, plugin: str) -> Any:
        if plugin in self._domain_points:
            factory = self._domain_points[plugin].load()
        elif plugin in REFERENCE_DOMAIN_PACKS:
            factory = self._load_reference(REFERENCE_DOMAIN_PACKS[plugin])
        else:
            self._require(self._domain_points, plugin, "domain pack")
            raise AssertionError("unreachable")
        return factory()

    @staticmethod
    def _load_reference(reference: str) -> Any:
        module_name, attribute = reference.split(":", 1)
        return getattr(import_module(module_name), attribute)

    @staticmethod
    def _require(points: dict[str, EntryPoint], name: str, kind: str) -> EntryPoint:
        try:
            return points[name]
        except KeyError as exc:
            available = ", ".join(sorted(points)) or "none"
            raise LookupError(f"unknown {kind} plugin {name!r}; available: {available}") from exc


def validate_reference_adapter_plugins(plugin_names: Iterable[str]) -> None:
    """Require installed reference adapter entry points to have unique expected provenance."""
    points = _index_entry_points("opensdl.adapters", "adapter")
    for name in sorted(set(plugin_names)):
        expected_value = REFERENCE_ADAPTERS.get(name)
        expected_distribution = REFERENCE_ADAPTER_DISTRIBUTIONS.get(name)
        if expected_value is None or expected_distribution is None:
            raise LookupError(f"{name!r} is not a reference adapter plugin")
        point = points.get(name)
        if point is None:
            raise LookupError(f"reference adapter plugin {name!r} has no installed entry point")
        distribution = point.dist.name if point.dist is not None else None
        if (
            point.value != expected_value
            or distribution is None
            or _normalized_distribution(distribution)
            != _normalized_distribution(expected_distribution)
        ):
            raise LookupError(
                f"reference adapter plugin {name!r} resolved to {point.value!r} from "
                f"{distribution!r}; expected {expected_value!r} from {expected_distribution!r}"
            )


def _index_entry_points(group: str, kind: str) -> dict[str, EntryPoint]:
    indexed: dict[str, EntryPoint] = {}
    duplicates: set[str] = set()
    for point in entry_points(group=group):
        if point.name in indexed:
            duplicates.add(point.name)
        indexed[point.name] = point
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise LookupError(f"duplicate {kind} plugin entry points: {names}")
    return indexed


def _normalized_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()
