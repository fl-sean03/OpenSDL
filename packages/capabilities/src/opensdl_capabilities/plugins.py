from __future__ import annotations

from importlib import import_module
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from .adapter import CapabilityAdapter


REFERENCE_ADAPTERS = {
    "simulated-lab": "opensdl_adapter_simulated_lab.adapter:SimulatedLabAdapter",
    "local-compute": "opensdl_adapter_local_compute.adapter:LocalComputeAdapter",
    "human-task": "opensdl_adapter_human_task.adapter:HumanTaskAdapter",
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
        self._adapter_points = {ep.name: ep for ep in entry_points(group="opensdl.adapters")}
        self._optimizer_points = {ep.name: ep for ep in entry_points(group="opensdl.optimizers")}
        self._domain_points = {ep.name: ep for ep in entry_points(group="opensdl.domain_packs")}

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
