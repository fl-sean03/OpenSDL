from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from opensdl_capabilities import (
    CapabilityRegistry,
    PluginManager,
    enforce_plugin_allowlist,
    plugin_allowlist,
    validate_declared_adapter_plugins,
)
from opensdl_operators import ContextPackBuilder, OperatorGateway
from opensdl_policy import PolicyEngine, PolicyRule
from opensdl_provenance import RunBundleExporter
from opensdl_runtime import ReferenceRuntime
from opensdl_core import RunRecord, WorkflowDefinition
from opensdl_schemas import LabManifest, load_manifest, redacted_manifest_document
from opensdl_storage import Database, LocalArtifactStore, Repositories
from opensdl_twin import TwinProjectionError, TwinService, load_twin_definition
from opensdl_workflows import load_workflow


class StoreNotFoundError(FileNotFoundError):
    """A read-only system was asked for a laboratory store that does not exist yet."""


class ReadOnlyGateway(OperatorGateway):
    """The operator boundary of a read-only system, with its one write path closed.

    Every read-only command reaches the store through the gateway, and `execute_capability` is the
    single method on it that dispatches an action. Refusing it here means `read_only` constrains the
    whole surface a caller actually touches, not only `OpenSDLSystem`'s own methods. It does not
    make the repositories read-only: a caller holding `system.repositories` can still write, and
    only the storage layer can close that.
    """

    async def execute_capability(
        self, capability_id: str, inputs: dict[str, Any], *, operator_id: str, environment: str
    ) -> dict[str, Any]:
        raise ValueError("a read-only OpenSDL system cannot execute capabilities")


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
        read_only: bool = False,
    ) -> None:
        self.read_only = read_only
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
        gateway_type = ReadOnlyGateway if read_only else OperatorGateway
        self.gateway = gateway_type(runtime, repositories, self.context_builder)
        self.exporter = RunBundleExporter(repositories, artifact_store)
        self.started = False

    @classmethod
    def from_manifest(
        cls,
        path: str | Path,
        *,
        read_only: bool = False,
        require_store: bool = True,
    ) -> "OpenSDLSystem":
        """Compose one laboratory from its manifest.

        `read_only=True` builds a system that inspects an existing laboratory without changing it:
        it does not create the store, does not create tables, does not upsert the manifest's
        capabilities or resources, never reconciles, and refuses to execute a workflow. Every
        command that only reads — inspect, events, export, capability listing, twin projection —
        belongs on this path. A store that does not exist yet raises `StoreNotFoundError` rather
        than being created, because a laboratory that has never run has no runs to inspect.

        `require_store=False` relaxes that one check, for a read that has an answer before the
        laboratory has ever run. Adapter health is the case: `doctor()` touches no repository, so a
        system composed this way against a laboratory with no store never connects to one and never
        creates one. The flag is only consulted when `read_only` is set; the write path creates the
        store by design.
        """
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

        # A manifest names the code this process will import and run. Authorize the names before
        # any of them is loaded: the allowlist is what the deployment permits, and the provenance
        # check stops an installed third party from answering to a reference adapter's name.
        adapter_plugins = [
            adapter_config.plugin
            for adapter_config in manifest.spec.adapters
            if adapter_config.enabled
        ]
        pack_plugins = [pack_config.plugin for pack_config in manifest.spec.domain_packs]
        enforce_plugin_allowlist([*adapter_plugins, *pack_plugins], plugin_allowlist())
        validate_declared_adapter_plugins(adapter_plugins)

        if read_only and require_store:
            store = _sqlite_store_path(database_url)
            if store is not None and not store.exists():
                raise StoreNotFoundError(
                    f"no OpenSDL store at {store}: this laboratory has recorded no runs yet"
                )

        database = Database(database_url, create=not read_only)
        if not read_only:
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

        # `pack_config.config` is descriptive: `load_domain_pack` takes no configuration, and the
        # only consumer of this list is the context pack, which `GET /context`, the `describe_lab`
        # tool, and the SDK all serve without authentication. So the redacted document is what
        # belongs here — a credential named in the manifest would otherwise be resolved at load and
        # then published, which is a larger disclosure than the operator wrote down.
        pack_documents = redacted_manifest_document(manifest)["spec"].get("domain_packs", [])
        domain_packs: list[dict[str, Any]] = []
        for index, pack_config in enumerate(manifest.spec.domain_packs):
            pack = plugins.load_domain_pack(pack_config.plugin)
            if not isinstance(pack, dict):
                raise TypeError(f"domain pack {pack_config.plugin!r} did not return a mapping")
            if pack.get("name") != pack_config.name:
                raise ValueError(
                    f"domain pack {pack_config.plugin!r} reports name "
                    f"{pack.get('name')!r}, expected {pack_config.name!r}"
                )
            domain_packs.append({**pack, "config": pack_documents[index]["config"]})

        if not read_only:
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
        artifact_store = LocalArtifactStore(artifact_root, repositories, create=not read_only)
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
            read_only=read_only,
        )

    async def start(self, *, reconcile: bool = False) -> list[RunRecord]:
        """Start the configured adapters and return the runs reconciliation moved.

        Reconciliation is opt-in and reported. It transitions every `RUNNING` or `ABORTING` run to
        `INTERVENTION_REQUIRED`, releases its leases, and appends recovery events — the correct
        response to a controller restart, and the destruction of the operational record of an
        experiment in flight when it happens during one. It used to run unconditionally and
        silently on every `start()`, including the one behind `opensdl doctor`. A caller that wants
        it now asks for it and is told what moved.
        """
        if reconcile and self.read_only:
            raise ValueError("a read-only OpenSDL system cannot reconcile runs")
        if self.started:
            return []
        await self.registry.start()
        self.started = True
        if not reconcile:
            return []
        return self.runtime.recover_incomplete_runs()

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

        if self.read_only:
            raise ValueError("a read-only OpenSDL system cannot execute workflows")
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
                # Through the registry, so health reaches the adapter on the adapter's own
                # loop like every other call. No shipped adapter's health() touches
                # loop-bound state, but one that held a connection or a lock would break
                # here and nowhere else, which is the worst place to discover it.
                health = await self.registry.health(adapter)
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
        # Whether the root can hold artifacts, which is not the same question as whether it is
        # there yet. This check used to read `root.exists()` while the store's own constructor had
        # just created that directory, so it reported on its own side effect and could not fail. A
        # laboratory that has recorded nothing has no artifact root, and that is not a fault; a
        # root that exists as a file, or whose parent cannot be written, is.
        artifact_root = self.artifact_store.root
        if artifact_root.exists():
            usable = artifact_root.is_dir() and os.access(artifact_root, os.W_OK)
            artifact_state = "ready" if usable else "unusable"
        else:
            parent = next((p for p in artifact_root.parents if p.exists()), None)
            usable = parent is not None and os.access(parent, os.W_OK)
            artifact_state = "creatable" if usable else "unusable"
        checks.append(
            {
                "name": "artifact-store",
                "passed": usable,
                "details": {"root": str(artifact_root), "state": artifact_state},
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


def _sqlite_store_path(url: str) -> Path | None:
    """The file a SQLite URL points at, or `None` when the store is not a local SQLite file.

    A missing file is the one store absence that can be detected before connecting. SQLite creates
    the database on first connect, so without this check a read against a laboratory that has never
    run produces an empty database rather than an answer. No equivalent check exists for a server
    backend, which is why this returns `None` rather than guessing.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    if raw in {":memory:", ""} or raw.startswith("file:"):
        return None
    return Path(raw).expanduser()


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


#: Query-parameter names whose value is a credential. Matched as a substring of the lowercased
#: parameter name, so `sslpassword`, `api_key`, and `access_token` are all covered.
_CREDENTIAL_PARAMETERS = ("password", "passwd", "pwd", "secret", "token", "key", "credential")


def _redact_url(url: str) -> str:
    """A database URL fit to print, with every credential position hidden and the rest legible.

    `opensdl doctor` prints this and `GET /health` serves it unauthenticated, so it is the one
    place a laboratory's connection string reaches an operator's terminal and an open route. Two
    positions carry credentials: the userinfo before `@`, and query parameters — several managed
    backends take the password, key, or token that way, and PostgreSQL accepts `?password=`. The
    parameter name survives redaction; only its value is replaced, because a URL printed for
    diagnosis has to stay diagnosable.
    """
    remainder = url
    prefix = ""
    if "://" in remainder:
        scheme, remainder = remainder.split("://", 1)
        prefix = f"{scheme}://"
    if "@" in remainder:
        remainder = f"***@{remainder.split('@', 1)[1]}"
    if "?" in remainder:
        base, query = remainder.split("?", 1)
        parameters = []
        for parameter in query.split("&"):
            name, separator, _ = parameter.partition("=")
            if separator and any(word in name.lower() for word in _CREDENTIAL_PARAMETERS):
                parameters.append(f"{name}=***")
            else:
                parameters.append(parameter)
        remainder = f"{base}?{'&'.join(parameters)}"
    return prefix + remainder
