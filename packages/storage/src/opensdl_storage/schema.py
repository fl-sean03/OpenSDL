"""Bringing a laboratory's schema into existence, and moving it forward.

Before this module, `Database.initialize()` called SQLAlchemy `create_all()` and inserted the
literal string `"0001"` into a `schema_versions` table. `create_all()` is CREATE TABLE IF NOT
EXISTS: it creates a missing table and never alters an existing one, so no laboratory that had ever
run could gain a column, an index, or a backfill. The stamped string was never compared against
anything and was not Alembic's `alembic_version`, so the shipped revision under `migrations/` was
unreachable from any command. `alembic upgrade head` against such a store failed on
`table schema_versions already exists`, and nothing anywhere told an operator to stamp first.

Alembic is now the single way a schema comes into existence and the single way it moves. The
alternative — keeping `create_all()` and reconciling it with Alembic — was rejected because it
leaves two writers of the same schema and the reconciliation is exactly the thing that had already
silently failed: `create_all()` honours `index=True` and revision 0001 created no indexes, so the
two paths produced databases differing by 23 indexes and no check noticed for the life of the
project. One writer cannot drift from itself.

A store that predates this change keeps working. It carries the declared tables and no
`alembic_version`, which is a state Alembic has a name for: it is adopted with `stamp` at
`ADOPTION_REVISION` and then upgraded like any other. Nothing is dropped and nothing is recreated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from .db_models import Base

#: The migration environment, inside the distribution so it travels with the models it describes.
MIGRATIONS = Path(__file__).parent / "migrations"

#: The revision a store created by the pre-Alembic `create_all()` path is equivalent to. Such a
#: store has 0001's tables plus the indexes `create_all()` derived from `index=True`; revision 0002
#: checks for each index before creating it, so both lineages converge without conflict.
ADOPTION_REVISION = "0001"

REVISION_KINDS = ("additive", "destructive")

#: Destructive revisions applied when a laboratory is opened for writing anyway, because every
#: laboratory passes through them. `0002` drops `schema_versions`, the hand-rolled version table
#: `alembic_version` replaced: `0001` creates it and `0002` removes it, so refusing it would refuse
#: a store created today. Adding to this list is the decision the refusal below exists to force.
GRANDFATHERED_DESTRUCTIVE = frozenset({"0002"})


class DestructiveUpgradeRefused(RuntimeError):
    """A store is behind a revision that destroys something, and nobody was asked."""


def revision_kind(revision: str) -> str:
    """What a revision says it does. A revision that does not say cannot be applied unattended."""
    module = script_directory().get_revision(revision).module
    kind = getattr(module, "opensdl_kind", None)
    if kind not in REVISION_KINDS:
        raise RuntimeError(
            f"revision {revision} declares opensdl_kind={kind!r}; a revision that does not say "
            f"whether it destroys anything cannot be applied unattended"
        )
    return kind


def destructive_revisions(revisions: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        revision
        for revision in revisions
        if revision_kind(revision) == "destructive" and revision not in GRANDFATHERED_DESTRUCTIVE
    )


@dataclass(frozen=True)
class SchemaUpgrade:
    """What `upgrade_to_head` found and what it did about it."""

    previous: str | None
    current: str
    applied: tuple[str, ...]
    adopted: bool

    @property
    def changed(self) -> bool:
        return bool(self.applied) or self.adopted


def alembic_config(url: str | None = None) -> Config:
    """An Alembic configuration pointing at the packaged migration environment.

    No `.ini` file is read, so Alembic's logging configuration is not applied and a host
    application's logging is left alone.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("file_template", "%%(rev)s_%%(slug)s")
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    return config


def script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def head_revision() -> str:
    """The single revision this release migrates to.

    Raises when the history has branched, which is a packaging error rather than a laboratory's
    problem and should never reach one.
    """
    heads = script_directory().get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"the OpenSDL migration history has {len(heads)} heads: {heads}")
    return heads[0]


def current_revision(connection: Connection) -> str | None:
    """The revision a store reports, or `None` when it has never been migrated."""
    return MigrationContext.configure(connection).get_current_revision()


def pending_revisions(connection: Connection) -> tuple[str, ...]:
    """Revisions between the store's current revision and head, oldest first."""
    current = current_revision(connection)
    if current is None and _carries_declared_tables(connection):
        current = ADOPTION_REVISION
    return _revisions_after(current)


def upgrade_to_head(engine: Engine, *, allow_destructive: bool = False) -> SchemaUpgrade:
    """Bring one store to the current schema, adopting it first if it predates Alembic.

    Opening a laboratory for writing applies additive revisions and stops at a destructive
    one, so a migration that drops data never runs inside an ordinary run with nobody asked
    and no backup taken. `opensdl migrate` is the opt-in.
    """
    with engine.connect() as connection:
        previous = current_revision(connection)
        adopt = previous is None and _carries_declared_tables(connection)
    refused = (
        ()
        if allow_destructive
        else destructive_revisions(_revisions_after(ADOPTION_REVISION if adopt else previous))
    )
    if refused:
        raise DestructiveUpgradeRefused(
            f"this store is behind {', '.join(refused)}, which destroys data. Opening a "
            "laboratory for writing applies additive revisions and stops here. Back the store "
            "up, then run `opensdl migrate`."
        )
    if adopt:
        _run(engine, command.stamp, ADOPTION_REVISION)
        previous = ADOPTION_REVISION
    applied = _revisions_after(previous)
    if applied:
        _run(engine, command.upgrade, "head")
    return SchemaUpgrade(
        previous=None if adopt else previous,
        current=head_revision(),
        applied=applied,
        adopted=adopt,
    )


def _run(engine: Engine, action: Callable[..., Any], argument: str) -> None:
    with engine.begin() as connection:
        config = alembic_config()
        config.attributes["connection"] = connection
        action(config, argument)


def _revisions_after(current: str | None) -> tuple[str, ...]:
    script = script_directory()
    walked = script.iterate_revisions(head_revision(), current or "base")
    return tuple(revision.revision for revision in reversed(list(walked)))


def _carries_declared_tables(connection: Connection) -> bool:
    """Whether this store already holds OpenSDL data written before Alembic tracked it.

    Only the tables OpenSDL declares are consulted, so a shared schema carrying another
    application's tables is not mistaken for a laboratory.
    """
    existing = set(inspect(connection).get_table_names())
    return bool(existing & set(Base.metadata.tables))
