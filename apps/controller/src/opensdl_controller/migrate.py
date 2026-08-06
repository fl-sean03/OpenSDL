"""The entry point behind `opensdl migrate`.

Schema upgrades deliberately do not compose a laboratory. `OpenSDLSystem.from_manifest` imports and
constructs every declared adapter and domain pack, so an adapter that fails to import — a plugin
uninstalled, a credential unset, a dependency moved — would block the schema upgrade that has
nothing to do with it. Migrating needs the manifest's storage configuration and nothing else.

`plan` answers without writing. That matters for SQLite, where connecting to a URL creates the file:
a laboratory that has never run has no store, and reporting on it must not bring one into existence.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opensdl_schemas import load_manifest
from opensdl_storage import Database, head_revision

from .system import _redact_url, _resolve_database_url, _sqlite_store_path


def laboratory_database_url(manifest_path: str | Path) -> tuple[str, str]:
    """The laboratory's name and the database URL it is configured to use.

    Resolved exactly the way `OpenSDLSystem.from_manifest` resolves it, `OPENSDL_DATABASE_URL`
    included, so `opensdl migrate` and `opensdl run` can never disagree about which store they mean.
    """
    resolved = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(resolved)
    url = os.getenv("OPENSDL_DATABASE_URL", manifest.spec.storage.database.url)
    return manifest.metadata.name, _resolve_database_url(url, resolved.parent)


def plan(manifest_path: str | Path) -> dict[str, Any]:
    """Report what upgrading this laboratory's store would apply, without touching it."""
    name, url = laboratory_database_url(manifest_path)
    report: dict[str, Any] = {
        "laboratory": name,
        "database": _redact_url(url),
        "head": head_revision(),
        "applied": [],
    }
    store = _sqlite_store_path(url)
    if store is not None and not store.exists():
        report["current"] = None
        report["pending"] = [head_revision()]
        report["exists"] = False
        return report
    database = Database(url, create=False)
    try:
        report["current"] = _current(database)
        report["pending"] = list(database.pending_upgrade())
        report["exists"] = True
    finally:
        database.dispose()
    return report


def upgrade(manifest_path: str | Path) -> dict[str, Any]:
    """Bring this laboratory's store to the current schema and report what it took."""
    name, url = laboratory_database_url(manifest_path)
    database = Database(url)
    try:
        before = _current(database)
        result = database.initialize()
        return {
            "laboratory": name,
            "database": _redact_url(url),
            "head": result.current,
            "current": result.current,
            "previous": before,
            "pending": [],
            "applied": list(result.applied),
            "adopted": result.adopted,
            "exists": True,
        }
    finally:
        database.dispose()


def _current(database: Database) -> str | None:
    from opensdl_storage import current_revision

    with database.engine.connect() as connection:
        return current_revision(connection)
