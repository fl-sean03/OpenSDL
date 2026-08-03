from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from opensdl_capabilities import CapabilityRegistry, PluginManager
from opensdl_operators import ContextPackBuilder, OperatorGateway
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_provenance import RunBundleExporter
from opensdl_runtime import ReferenceRuntime
from opensdl_core import RunRecord, WorkflowDefinition
from opensdl_schemas import LabManifest, load_manifest
from opensdl_storage import Database, LocalArtifactStore, Repositories
from opensdl_twin import TwinProjectionError, TwinService, load_twin_definition
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
        twin: TwinService | None = None,
        twin_viewer_root: Path | None = None,
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
        self.twin = twin
        self.twin_viewer_root = twin_viewer_root
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
        artifact_root = Path(
            os.getenv("OPENSDL_ARTIFACT_ROOT", manifest.spec.storage.artifacts.root)
        )
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
                item.id: registry.get_adapter(item.id).name for item in registry.list_capabilities()
            }
            enabled_capabilities: list[str] = []
            for binding in manifest.spec.capabilities:
                if not binding.enabled:
                    continue
                if binding.capability not in available:
                    raise ValueError(f"manifest binds unavailable capability: {binding.capability}")
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
                raise TypeError(f"domain pack {pack_config.plugin!r} did not return a mapping")
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

        rules = [
            PolicyRule.model_validate(rule.model_dump(mode="json"))
            for rule in manifest.spec.policy.rules
        ]
        policy = PolicyEngine(
            rules=rules,
            default_effect=manifest.spec.policy.default_effect,
            version=manifest.spec.policy.version,
        )
        artifact_store = LocalArtifactStore(artifact_root, repositories)
        twin: TwinService | None = None
        twin_viewer_root: Path | None = None
        if manifest.spec.twin is not None:
            definition_path = _resolve_path(manifest.spec.twin.definition, base)
            twin = TwinService(load_twin_definition(definition_path))
            if manifest.spec.twin.viewer_root is not None:
                twin_viewer_root = _resolve_path(manifest.spec.twin.viewer_root, base)
        twin_binding = _twin_binding(twin) if twin is not None else None
        runtime = ReferenceRuntime(
            registry,
            repositories,
            policy,
            artifact_store,
            max_concurrency=manifest.spec.runtime.max_concurrency,
            default_timeout_seconds=manifest.spec.runtime.default_timeout_seconds,
            lease_ttl_seconds=manifest.spec.runtime.lease_ttl_seconds,
            default_run_context=(
                {"twinBinding": twin_binding} if twin_binding is not None else None
            ),
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
            twin=twin,
            twin_viewer_root=twin_viewer_root,
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
        run_id: str | None = None,
    ) -> RunRecord:
        workflow = load_workflow(workflow_path)
        return await self.run_workflow_definition(
            workflow,
            inputs,
            operator_id=operator_id,
            run_id=run_id,
        )

    async def run_workflow_definition(
        self,
        workflow: WorkflowDefinition,
        inputs: dict[str, Any],
        *,
        operator_id: str = "operator/local",
        run_id: str | None = None,
    ) -> RunRecord:
        """Run a workflow and durably pin the twin binding used for replay."""

        effective_run_id = run_id or RunRecord(workflow_id=workflow.id).id
        twin_binding = self._current_twin_binding()
        run_context = {"twinBinding": twin_binding} if twin_binding is not None else None
        return await self.runtime.run_workflow(
            workflow,
            inputs,
            operator_id=operator_id,
            environment=self.manifest.spec.environment,
            run_id=effective_run_id,
            run_context=run_context,
        )

    def _current_twin_binding(self) -> dict[str, str] | None:
        if self.twin is None:
            return None
        return _twin_binding(self.twin)

    async def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for adapter in self.registry.list_adapters():
            try:
                health = await adapter.health()
                checks.append(
                    {
                        "name": f"adapter:{adapter.name}",
                        "passed": health.get("status") == "healthy",
                        "details": health,
                    }
                )
            except Exception as exc:
                checks.append(
                    {"name": f"adapter:{adapter.name}", "passed": False, "error": str(exc)}
                )
        checks.append(
            {"name": "database", "passed": True, "details": {"url": _redact_url(self.database.url)}}
        )
        checks.append(
            {
                "name": "artifact-store",
                "passed": self.artifact_store.root.exists(),
                "details": {"root": str(self.artifact_store.root)},
            }
        )
        return {
            "laboratory": self.manifest.metadata.name,
            "environment": self.manifest.spec.environment,
            "passed": all(check["passed"] for check in checks),
            "checks": checks,
        }

    def project_twin_run(self, run_id: str) -> dict[str, Any]:
        if self.twin is None:
            raise LookupError("digital twin is not configured")
        if self.repositories.get_run(run_id) is None:
            raise KeyError(run_id)
        tasks = self.repositories.list_tasks(run_id)
        events = self.repositories.list_events(run_id=run_id, limit=None)
        created_events = [event for event in events if event.type == "RunCreated"]
        current_binding = self._current_twin_binding()
        if len(created_events) != 1 or current_binding is None:
            raise TwinProjectionError(
                f"run {run_id!r} does not have exactly one pinned twin definition"
            )
        recorded_context = created_events[0].payload.get("context")
        recorded_binding = (
            recorded_context.get("twinBinding") if isinstance(recorded_context, dict) else None
        )
        if recorded_binding != current_binding:
            raise TwinProjectionError(
                f"run {run_id!r} was recorded against a different twin definition"
            )
        cues = self.twin.project_run(
            events,
            {task.id: task.capability_id for task in tasks},
        )
        return {
            "definition_revision": self.twin.definition.revision,
            "run_id": run_id,
            "cues": [cue.model_dump(mode="json", by_alias=True) for cue in cues],
        }


def _resolve_database_url(url: str, base: Path) -> str:
    prefix = "sqlite:///./"
    if url.startswith(prefix):
        path = (base / url[len(prefix) :]).resolve()
        return f"sqlite:///{path}"
    return url


def _twin_binding(twin: TwinService) -> dict[str, str]:
    definition = twin.definition.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    canonical = json.dumps(
        definition,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "definitionRevision": twin.definition.revision,
        "definitionSha256": hashlib.sha256(canonical).hexdigest(),
        "sceneSha256": twin.definition.scene.sha256,
    }


def _resolve_path(path: str | Path, base: Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = base / resolved
    return resolved.resolve()


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    return f"{scheme}://***@{remainder.split('@', 1)[1]}"
