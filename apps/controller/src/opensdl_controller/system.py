from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opensdl_capabilities import CapabilityRegistry, PluginManager
from opensdl_operators import ContextPackBuilder, OperatorGateway
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_provenance import RunBundleExporter
from opensdl_runtime import ReferenceRuntime
from opensdl_schemas import LabManifest, load_manifest
from opensdl_storage import Database, LocalArtifactStore, Repositories
from opensdl_workflows import load_workflow


class OpenSDLSystem:
    """Composition root for one configured laboratory environment."""

    def __init__(
        self,
        *,
        manifest_path: Path,
        manifest: LabManifest,
        database: Database,
        repositories: Repositories,
        registry: CapabilityRegistry,
        policy: PolicyEngine,
        artifact_store: LocalArtifactStore,
        runtime: ReferenceRuntime,
        domain_packs: list[dict[str, Any]],
    ) -> None:
        self.manifest_path = manifest_path
        self.manifest = manifest
        self.database = database
        self.repositories = repositories
        self.registry = registry
        self.policy = policy
        self.artifact_store = artifact_store
        self.runtime = runtime
        self.domain_packs = domain_packs
        self.context_builder = ContextPackBuilder(
            manifest,
            registry,
            repositories,
            policy.version,
            domain_packs,
        )
        self.gateway = OperatorGateway(runtime, repositories, self.context_builder)
        self.exporter = RunBundleExporter(repositories, artifact_store)
        self.started = False

    @classmethod
    def from_manifest(cls, path: str | Path) -> "OpenSDLSystem":
        manifest_path = Path(path).expanduser().resolve()
        manifest = load_manifest(manifest_path)
        base = manifest_path.parent
        database_url = os.getenv("OPENSDL_DATABASE_URL", manifest.spec.storage.database.url)
        database_url = _resolve_database_url(database_url, base)
        artifact_root = Path(os.getenv("OPENSDL_ARTIFACT_ROOT", manifest.spec.storage.artifacts.root))
        if not artifact_root.is_absolute():
            artifact_root = (base / artifact_root).resolve()

        database = Database(database_url)
        database.initialize()
        repositories = Repositories(database)
        registry = CapabilityRegistry()
        plugins = PluginManager()
        adapter_names: set[str] = set()
        for adapter_config in manifest.spec.adapters:
            if not adapter_config.enabled:
                continue
            adapter = plugins.load_adapter(adapter_config.plugin, adapter_config.config)
            if adapter_config.name != adapter.name:
                adapter.name = adapter_config.name
            registry.register(adapter)
            adapter_names.add(adapter.name)

        if manifest.spec.capabilities:
            available = {
                item.id: registry.get_adapter(item.id).name
                for item in registry.list_capabilities()
            }
            enabled_capabilities: list[str] = []
            for binding in manifest.spec.capabilities:
                if not binding.enabled:
                    continue
                if binding.capability not in available:
                    raise ValueError(
                        f"manifest binds unavailable capability: {binding.capability}"
                    )
                if available[binding.capability] != binding.adapter:
                    raise ValueError(
                        f"capability {binding.capability} is provided by "
                        f"{available[binding.capability]}, not {binding.adapter}"
                    )
                enabled_capabilities.append(binding.capability)
            registry.restrict(enabled_capabilities)

        domain_packs: list[dict[str, Any]] = []
        for pack_config in manifest.spec.domain_packs:
            pack = plugins.load_domain_pack(pack_config.plugin)
            if not isinstance(pack, dict):
                raise TypeError(
                    f"domain pack {pack_config.plugin!r} did not return a mapping"
                )
            if pack.get("name") != pack_config.name:
                raise ValueError(
                    f"domain pack {pack_config.plugin!r} reports name "
                    f"{pack.get('name')!r}, expected {pack_config.name!r}"
                )
            domain_packs.append({**pack, "config": pack_config.config})

        for adapter in registry.list_adapters():
            for definition in adapter.capability_definitions():
                repositories.upsert_capability(definition, adapter.name)
        for resource in manifest.spec.resources:
            repositories.upsert_resource(resource)

        rules = [PolicyRule.model_validate(rule.model_dump(mode="json")) for rule in manifest.spec.policy.rules]
        policy = PolicyEngine(
            rules=rules,
            default_effect=manifest.spec.policy.default_effect,
            version=manifest.spec.policy.version,
        )
        artifact_store = LocalArtifactStore(artifact_root, repositories)
        runtime = ReferenceRuntime(
            registry,
            repositories,
            policy,
            artifact_store,
            max_concurrency=manifest.spec.runtime.max_concurrency,
            default_timeout_seconds=manifest.spec.runtime.default_timeout_seconds,
            lease_ttl_seconds=manifest.spec.runtime.lease_ttl_seconds,
        )
        return cls(
            manifest_path=manifest_path,
            manifest=manifest,
            database=database,
            repositories=repositories,
            registry=registry,
            policy=policy,
            artifact_store=artifact_store,
            runtime=runtime,
            domain_packs=domain_packs,
        )

    async def start(self) -> None:
        if self.started:
            return
        await self.registry.start()
        self.runtime.recover_incomplete_runs()
        self.started = True

    async def close(self) -> None:
        if not self.started:
            self.database.dispose()
            return
        await self.registry.close()
        self.database.dispose()
        self.started = False

    async def run_workflow_file(
        self,
        workflow_path: str | Path,
        inputs: dict[str, Any],
        *,
        operator_id: str = "operator/local",
    ):
        workflow = load_workflow(workflow_path)
        return await self.runtime.run_workflow(
            workflow,
            inputs,
            operator_id=operator_id,
            environment=self.manifest.spec.environment,
        )

    async def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for adapter in self.registry.list_adapters():
            try:
                health = await adapter.health()
                checks.append({"name": f"adapter:{adapter.name}", "passed": health.get("status") == "healthy", "details": health})
            except Exception as exc:
                checks.append({"name": f"adapter:{adapter.name}", "passed": False, "error": str(exc)})
        checks.append({"name": "database", "passed": True, "details": {"url": _redact_url(self.database.url)}})
        checks.append({"name": "artifact-store", "passed": self.artifact_store.root.exists(), "details": {"root": str(self.artifact_store.root)}})
        return {
            "laboratory": self.manifest.metadata.name,
            "environment": self.manifest.spec.environment,
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
        }


def _resolve_database_url(url: str, base: Path) -> str:
    prefix = "sqlite:///./"
    if url.startswith(prefix):
        path = (base / url[len(prefix):]).resolve()
        return f"sqlite:///{path}"
    return url


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    return f"{scheme}://***@{remainder.split('@', 1)[1]}"
