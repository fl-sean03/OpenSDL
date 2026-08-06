"""Tests for the composition root's side effects and its plugin authorization.

Two properties are asserted here that the composition root did not have:

* **Reading a laboratory does not write to it.** `from_manifest` created the store, created its
  tables and seeded every capability and resource, and `start()` reconciled every active run. Seven
  read-only commands went through that path, so `opensdl inspect` against a run that does not exist
  created a database, and `opensdl doctor` during a live campaign moved every `RUNNING` run to
  `INTERVENTION_REQUIRED` and reported `"passed": true`.
* **A manifest cannot load arbitrary code unchecked.** Loading a plugin imports and executes
  installed code in the process that talks to equipment, and in a laboratory repository the manifest
  is a file an agent edits.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from opensdl_capabilities import PLUGIN_ALLOWLIST_ENV, PluginNotAllowedError
from opensdl_capabilities import plugins as plugin_module
from opensdl_controller import OpenSDLSystem, migrate
from opensdl_controller.system import StoreNotFoundError, _redact_url
from opensdl_core import RunRecord, RunState
from opensdl_storage import head_revision


MANIFEST: dict[str, Any] = {
    "apiVersion": "opensdl.dev/v0alpha1",
    "kind": "Laboratory",
    "metadata": {"name": "test-lab", "owner": "test"},
    "spec": {
        "environment": "simulation",
        "storage": {
            "database": {"url": "sqlite:///./.opensdl/opensdl.db"},
            "artifacts": {"root": ".opensdl/artifacts"},
        },
        "adapters": [{"name": "simulated-lab", "plugin": "simulated-lab", "config": {"seed": 7}}],
        "resources": [{"id": "virtual-mixer", "name": "Virtual mixer", "type": "simulator"}],
        "policy": {
            "default_effect": "deny",
            "version": "test/v1",
            "rules": [
                {
                    "id": "allow-simulation",
                    "effect": "allow",
                    "environments": ["simulation"],
                    "risk_classes": ["R0", "R1"],
                    "priority": 10,
                }
            ],
        },
        "domain_packs": [{"name": "materials", "plugin": "materials"}],
    },
}


def write_manifest(root: Path, **spec: Any) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "opensdl.yaml"
    document = {**MANIFEST, "spec": {**MANIFEST["spec"], **spec}}
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def seed_store(manifest: Path) -> None:
    """Bring a store into existence the way normal write-path use does."""
    system = OpenSDLSystem.from_manifest(manifest)
    system.database.dispose()


@pytest.fixture(autouse=True)
def unconstrained_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's own allowlist must not decide what these tests assert."""
    monkeypatch.delenv(PLUGIN_ALLOWLIST_ENV, raising=False)


# --- Reading a laboratory does not write to it ------------------------------------------------


def test_read_only_construction_refuses_a_store_that_does_not_exist(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "lab")

    with pytest.raises(StoreNotFoundError) as raised:
        OpenSDLSystem.from_manifest(manifest, read_only=True)

    assert "opensdl.db" in str(raised.value)
    assert not (tmp_path / "lab/.opensdl/opensdl.db").exists()


async def test_health_can_be_reported_without_bringing_a_store_into_existence(
    tmp_path: Path,
) -> None:
    """`opensdl doctor` on a laboratory that has never run must still answer, and still not write.

    `doctor()` reads no repository, so a system that does not require a store never connects to one.
    """
    manifest = write_manifest(tmp_path / "lab")

    system = OpenSDLSystem.from_manifest(manifest, read_only=True, require_store=False)
    try:
        report = await system.doctor()
        assert report["passed"] is True
        assert {check["name"] for check in report["checks"]} >= {"database", "artifact-store"}
    finally:
        await system.close()

    assert not (tmp_path / "lab/.opensdl/opensdl.db").exists()


def test_read_only_construction_reads_the_store_without_seeding_it(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "lab")
    seed_store(manifest)

    later = write_manifest(
        tmp_path / "lab",
        resources=[
            {"id": "virtual-mixer", "name": "Virtual mixer", "type": "simulator"},
            {"id": "bench-balance", "name": "Bench balance", "type": "instrument"},
        ],
    )
    reader = OpenSDLSystem.from_manifest(later, read_only=True)
    try:
        assert reader.read_only is True
        assert {definition.id for definition, _ in reader.repositories.list_capabilities()}
        assert {resource.id for resource in reader.repositories.list_resources()} == {
            "virtual-mixer"
        }, "a read must not upsert the manifest's resources"
    finally:
        reader.database.dispose()

    writer = OpenSDLSystem.from_manifest(later)
    try:
        assert {resource.id for resource in writer.repositories.list_resources()} == {
            "virtual-mixer",
            "bench-balance",
        }, "the write path still seeds"
    finally:
        writer.database.dispose()


async def test_a_read_only_system_never_reconciles_and_never_executes(tmp_path: Path) -> None:
    """`opensdl doctor` during a live campaign is the case this exists for."""
    manifest = write_manifest(tmp_path / "lab")
    seed_store(manifest)
    writable = OpenSDLSystem.from_manifest(manifest)
    live = writable.repositories.create_run(RunRecord(workflow_id="live", state=RunState.RUNNING))
    writable.database.dispose()

    reader = OpenSDLSystem.from_manifest(manifest, read_only=True)
    try:
        assert await reader.start() == []
        assert reader.repositories.list_runs()[0].state is RunState.RUNNING

        with pytest.raises(ValueError, match="read-only"):
            await reader.start(reconcile=True)
        with pytest.raises(ValueError, match="read-only"):
            await reader.run_workflow_definition(workflow_stub(), {})
        # The gateway is the surface every read-only command actually uses, and one of its methods
        # dispatches an action.
        with pytest.raises(ValueError, match="read-only"):
            await reader.gateway.execute_capability(
                "sim.mix_color",
                {},
                operator_id="operator/test",
                environment="simulation",
            )
        assert reader.gateway.inspect_run(live.id)["run"]["id"] == live.id

        assert reader.repositories.get_run(live.id) is not None
    finally:
        await reader.close()


async def test_reconciliation_is_opt_in_and_reports_what_it_moved(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "lab")
    system = OpenSDLSystem.from_manifest(manifest)
    live = system.repositories.create_run(RunRecord(workflow_id="live", state=RunState.RUNNING))
    try:
        assert await system.start() == [], "a plain start must not move a live run"
        current = system.repositories.get_run(live.id)
        assert current is not None and current.state is RunState.RUNNING
    finally:
        await system.close()

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        reconciled = await system.start(reconcile=True)
        assert [run.id for run in reconciled] == [live.id]
        assert reconciled[0].state is RunState.INTERVENTION_REQUIRED
    finally:
        await system.close()


# --- A manifest cannot load arbitrary code unchecked ------------------------------------------


def test_a_plugin_outside_the_allowlist_is_refused_before_it_is_imported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path / "lab")
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "local-compute")

    loaded: list[str] = []
    original = plugin_module.PluginManager.load_adapter

    def record(self: Any, plugin: str, config: Any = None) -> Any:
        loaded.append(plugin)
        return original(self, plugin, config)

    monkeypatch.setattr(plugin_module.PluginManager, "load_adapter", record)

    with pytest.raises(PluginNotAllowedError, match="simulated-lab"):
        OpenSDLSystem.from_manifest(manifest)

    assert loaded == [], "the refusal has to precede the import, not follow it"


def test_a_domain_pack_outside_the_allowlist_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path / "lab")
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "simulated-lab")

    with pytest.raises(PluginNotAllowedError, match="materials"):
        OpenSDLSystem.from_manifest(manifest)


async def test_an_allowlist_naming_every_declared_plugin_loads_normally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path / "lab")
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "simulated-lab, materials")

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        assert [pack["name"] for pack in system.domain_packs] == ["materials"]
    finally:
        await system.close()


async def test_a_disabled_adapter_is_not_subject_to_the_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disabled adapter is never imported, so it is not what an allowlist protects."""
    manifest = write_manifest(
        tmp_path / "lab",
        adapters=[
            {"name": "simulated-lab", "plugin": "simulated-lab", "config": {"seed": 7}},
            {"name": "vendor", "plugin": "vendor-hardware", "enabled": False},
        ],
    )
    monkeypatch.setenv(PLUGIN_ALLOWLIST_ENV, "simulated-lab, materials")

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        assert {adapter.name for adapter in system.registry.list_adapters()} == {"simulated-lab"}
    finally:
        await system.close()


def test_a_squatted_reference_adapter_name_is_refused_at_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provenance check that lived only inside a skill helper now runs on the load path."""
    manifest = write_manifest(tmp_path / "lab")
    shadow = SimpleNamespace(
        name="simulated-lab",
        value="vendor_hardware.adapter:PhysicalAdapter",
        dist=SimpleNamespace(name="vendor-hardware"),
    )

    def fake_entry_points(*, group: str) -> list[Any]:
        return [shadow] if group == "opensdl.adapters" else []

    monkeypatch.setattr(plugin_module, "entry_points", fake_entry_points)

    with pytest.raises(LookupError, match="resolved to"):
        OpenSDLSystem.from_manifest(manifest)


def workflow_stub() -> Any:
    from opensdl_core import WorkflowDefinition, WorkflowStep

    return WorkflowDefinition(
        id="stub",
        name="Stub",
        steps=[WorkflowStep(id="only", capability="sim.mix_color")],
    )


@pytest.mark.asyncio
async def test_the_artifact_store_check_reports_on_the_store_and_not_on_its_own_side_effect(
    tmp_path: Path,
) -> None:
    """A root that cannot hold artifacts must fail the health check.

    It used to read `root.exists()` while the store's constructor had just created that directory,
    so the check reported on its own side effect and could not fail. Two states it now separates:
    a laboratory that has recorded nothing has no root yet and is healthy, and a root occupied by
    something that is not a directory is not.
    """

    manifest = write_manifest(tmp_path)
    fresh = OpenSDLSystem.from_manifest(manifest, read_only=True, require_store=False)
    try:
        report = await fresh.doctor()
    finally:
        await fresh.close()
    artifact = next(c for c in report["checks"] if c["name"] == "artifact-store")
    assert artifact["passed"] is True
    assert artifact["details"]["state"] == "creatable"
    assert not Path(artifact["details"]["root"]).exists(), "reporting must not create the root"

    Path(artifact["details"]["root"]).parent.mkdir(parents=True, exist_ok=True)
    Path(artifact["details"]["root"]).write_text("occupied by a file", encoding="utf-8")
    blocked = OpenSDLSystem.from_manifest(manifest, read_only=True, require_store=False)
    try:
        report = await blocked.doctor()
    finally:
        await blocked.close()
    artifact = next(c for c in report["checks"] if c["name"] == "artifact-store")
    assert artifact["passed"] is False
    assert artifact["details"]["state"] == "unusable"
    assert report["passed"] is False


# --- A named credential does not become a printed one -----------------------------------------


@pytest.mark.asyncio
async def test_a_resolved_domain_pack_secret_does_not_reach_the_context_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`spec.domain_packs[].config` is copied verbatim into every context read.

    `ContextPack.domain_packs` is served by `GET /context`, by the `describe_lab` MCP tool, and by
    the SDK, none of which is authenticated. Before secret references existed this printed whatever
    an operator had typed into the manifest; resolving references at load would have made it print
    what the environment supplies instead, which is a strictly larger disclosure than the one the
    operator chose. The composition root carries the reference, not the value.
    """
    monkeypatch.setenv("MATERIALS_API_KEY", "pack-secret-value")
    manifest = write_manifest(
        tmp_path / "lab",
        domain_packs=[
            {
                "name": "materials",
                "plugin": "materials",
                "config": {"api_key": "${env:MATERIALS_API_KEY}"},
            }
        ],
    )

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        pack = next(item for item in system.domain_packs if item["name"] == "materials")
        assert pack["config"]["api_key"] == "${env:MATERIALS_API_KEY}"
        pack_payload = system.context_builder.build().model_dump(mode="json")
        assert "pack-secret-value" not in json.dumps(pack_payload)
    finally:
        await system.close()


def test_the_database_url_doctor_prints_hides_a_credential_in_any_position() -> None:
    """`opensdl doctor` and `GET /health` both print the database check verbatim.

    `_redact_url` handled `user:pass@host` and nothing else. A driver that takes the credential as
    a query parameter — `?password=`, and the key and token forms several managed backends use —
    went through unredacted onto stdout and onto an unauthenticated route. Parameters that are not
    credentials stay legible, because the point of printing the URL at all is diagnosis.
    """
    assert _redact_url("sqlite:///./lab.db") == "sqlite:///./lab.db"
    assert _redact_url("postgresql://opensdl:hunter2@db:5432/lab") == (
        "postgresql://***@db:5432/lab"
    )

    redacted = _redact_url("postgresql://opensdl@db:5432/lab?password=hunter2&sslmode=require")
    assert "hunter2" not in redacted
    assert "sslmode=require" in redacted

    for parameter in ("password", "sslpassword", "api_key", "token", "SECRET"):
        redacted = _redact_url(f"postgresql://db/lab?{parameter}=hunter2")
        assert "hunter2" not in redacted, parameter
        assert parameter in redacted, "the parameter is still named, only its value is hidden"


@pytest.mark.asyncio
async def test_doctor_reports_the_database_through_that_redaction(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "lab")

    system = OpenSDLSystem.from_manifest(manifest, read_only=True, require_store=False)
    try:
        report = await system.doctor()
    finally:
        await system.close()

    database = next(check for check in report["checks"] if check["name"] == "database")
    assert database["details"]["url"] == _redact_url(system.database.url)


def test_the_manifest_the_controller_holds_still_carries_resolved_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redaction is for what is printed. An adapter still receives the credential it needs."""
    monkeypatch.setenv("SIM_SEED", "11")
    manifest = write_manifest(
        tmp_path / "lab",
        adapters=[
            {
                "name": "simulated-lab",
                "plugin": "simulated-lab",
                "config": {"seed": "${env:SIM_SEED}"},
            }
        ],
    )

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        assert system.manifest.spec.adapters[0].config["seed"] == "11"
    finally:
        system.database.dispose()


# --- The entry point behind `opensdl migrate` --------------------------------------------------


def test_migrate_reports_a_laboratory_that_has_never_run_without_creating_its_store(
    tmp_path: Path,
) -> None:
    """SQLite creates the file on connect, so reporting must answer before it connects."""
    manifest = write_manifest(tmp_path / "lab")

    report = migrate.plan(manifest)

    assert report["exists"] is False
    assert report["current"] is None
    assert report["pending"] == [head_revision()]
    assert not (tmp_path / "lab/.opensdl/opensdl.db").exists()


def test_migrate_upgrades_a_store_and_then_reports_nothing_pending(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "lab")

    upgraded = migrate.upgrade(manifest)

    assert upgraded["applied"] == ["0001", "0002"]
    assert upgraded["adopted"] is False
    assert upgraded["current"] == head_revision()
    assert migrate.plan(manifest)["pending"] == []


def test_migrating_does_not_import_the_manifest_s_plugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken adapter must not stand between a laboratory and its schema.

    `from_manifest` imports and constructs every declared plugin. An uninstalled adapter or an
    unset credential would otherwise make the store unupgradable — which is the failure mode E1
    describes, arrived at from the other direction.
    """
    manifest = write_manifest(
        tmp_path / "lab",
        adapters=[{"name": "gone", "plugin": "no-such-plugin-installed", "config": {}}],
    )

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("migrating must not load plugins")

    monkeypatch.setattr(plugin_module.PluginManager, "load_adapter", refuse)

    assert migrate.upgrade(manifest)["current"] == head_revision()


def test_migrate_reports_the_database_through_the_same_redaction_doctor_uses(
    tmp_path: Path,
) -> None:
    manifest = write_manifest(tmp_path / "lab")

    assert migrate.plan(manifest)["database"] == _redact_url(
        migrate.laboratory_database_url(manifest)[1]
    )
