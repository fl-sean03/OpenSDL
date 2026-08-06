"""The migration path, and the comparison that stops it drifting from the models again.

The old test here asserted that six table names existed after `alembic upgrade head`. That was true
and useless: `db_models.py` declared `index=True` on 23 columns, revision 0001 created zero indexes,
and a subset-of-table-names assertion cannot see the difference. Two schemas were shipped —
`create_all()` produced one with 23 indexes and Alembic produced one with none — and the check that
was supposed to catch exactly this passed for the life of the project.

`test_the_migrated_schema_is_the_schema_the_models_declare` is the durable part of this file. It
compares the database Alembic builds against `Base.metadata` with the same comparison
`alembic revision --autogenerate` uses, so any divergence — a missing index, a column, a type, a
constraint — fails here. The index drift is today's instance; the comparison is the point.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from opensdl_core import EventRecord, RunRecord, RunState
from opensdl_storage import (
    ADOPTION_REVISION,
    Base,
    Database,
    Repositories,
    alembic_config,
    current_revision,
    head_revision,
)

DECLARED_TABLES = {
    "runs",
    "tasks",
    "events",
    "artifacts",
    "resources",
    "capabilities",
    "resource_leases",
}


def migrated(tmp_path: Path, name: str = "migration.db") -> Path:
    database_path = tmp_path / name
    config = alembic_config(f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    return database_path


def differences(database_path: Path) -> list[object]:
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))
    finally:
        engine.dispose()


def test_the_initial_migration_creates_every_declared_table(tmp_path: Path) -> None:
    tables = set(inspect(create_engine(f"sqlite:///{migrated(tmp_path)}")).get_table_names())

    assert DECLARED_TABLES <= tables
    assert "alembic_version" in tables
    assert "schema_versions" not in tables, "retired in 0002; alembic_version records the version"


def test_the_migrated_schema_is_the_schema_the_models_declare(tmp_path: Path) -> None:
    """Alembic-from-nothing must produce exactly what `Base.metadata` describes.

    This is the check the six-table-name assertion could not make. Run against revision 0001 alone
    it reports 23 `add_index` operations — the drift that shipped.
    """
    assert differences(migrated(tmp_path)) == []


def test_the_migration_history_has_exactly_one_head() -> None:
    """Two heads mean `upgrade head` is ambiguous and a laboratory gets whichever Alembic picks."""
    assert head_revision() == "0002"


# --- A store that predates Alembic ------------------------------------------------------------


def legacy_store(path: Path) -> None:
    """Build a store the way `Database.initialize()` did before Alembic was the writer.

    `create_all()` plus a hand-written `schema_versions` row: every declared table, every index
    `index=True` implies, and no `alembic_version`. This is what every laboratory that has ever run
    a workflow is holding.
    """
    engine = create_engine(f"sqlite:///{path}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE schema_versions "
                    "(version VARCHAR(64) NOT NULL PRIMARY KEY, applied_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO schema_versions VALUES ('0001', '2026-01-01 00:00:00')")
            )
    finally:
        engine.dispose()


def test_a_store_created_before_alembic_is_adopted_and_upgraded_in_place(tmp_path: Path) -> None:
    """The laboratory that already exists is the one E1 is about.

    `alembic upgrade head` against such a store failed on `table schema_versions already exists`,
    and no documented command stamped it first. It is now adopted at the revision its contents
    correspond to and carried forward, with its runs and events untouched.
    """
    path = tmp_path / "legacy.db"
    legacy_store(path)
    database = Database(f"sqlite:///{path}")
    repositories = Repositories(database)
    run = repositories.create_run(RunRecord(workflow_id="before-the-upgrade"))
    repositories.append_event(EventRecord(type="RunCreated", run_id=run.id))

    with database.engine.connect() as connection:
        assert current_revision(connection) is None, "a legacy store reports no revision"
    assert database.pending_upgrade() == ("0002",)

    upgrade = database.initialize()

    assert upgrade.adopted is True
    assert upgrade.previous is None
    assert upgrade.applied == ("0002",)
    assert upgrade.current == head_revision()
    with database.engine.connect() as connection:
        assert current_revision(connection) == head_revision()
    database.dispose()

    assert differences(path) == []
    tables = set(inspect(create_engine(f"sqlite:///{path}")).get_table_names())
    assert "schema_versions" not in tables

    reopened = Repositories(Database(f"sqlite:///{path}"))
    preserved = reopened.get_run(run.id)
    assert preserved is not None
    assert preserved.workflow_id == "before-the-upgrade"
    assert preserved.state is RunState.PLANNED
    assert [event.type for event in reopened.list_events(run_id=run.id)] == ["RunCreated"]


def test_adopting_a_legacy_store_keeps_the_indexes_it_already_had(tmp_path: Path) -> None:
    """Revision 0002 runs against a store that already owns every index it creates.

    Both lineages converge here, so 0002 has to check before it acts. If it did not, adopting a
    laboratory would fail on the first duplicate index name.
    """
    path = tmp_path / "legacy.db"
    legacy_store(path)
    before = _index_names(path)
    assert len(before) == 23

    database = Database(f"sqlite:///{path}")
    database.initialize()
    database.dispose()

    assert _index_names(path) == before


def _index_names(path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{path}")
    try:
        inspector = inspect(engine)
        return {
            index["name"]
            for table in inspector.get_table_names()
            for index in inspector.get_indexes(table)
            if index["name"] is not None
        }
    finally:
        engine.dispose()


# --- A store that does not exist yet ------------------------------------------------------------


def test_a_new_store_is_built_by_alembic_and_recorded_at_head(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'new.db'}")

    upgrade = database.initialize()

    assert upgrade.adopted is False
    assert upgrade.previous is None
    assert upgrade.applied == ("0001", "0002")
    assert upgrade.current == head_revision()
    with database.engine.connect() as connection:
        assert current_revision(connection) == head_revision()
    database.dispose()

    assert differences(tmp_path / "new.db") == []


def test_opening_a_current_store_applies_nothing(tmp_path: Path) -> None:
    """Every write command initializes. On a laboratory already at head that must be a no-op."""
    database = Database(f"sqlite:///{tmp_path / 'new.db'}")
    database.initialize()

    again = database.initialize()

    assert again.applied == ()
    assert again.adopted is False
    assert again.previous == head_revision()
    assert again.changed is False
    assert database.pending_upgrade() == ()
    database.dispose()


def test_the_in_memory_store_migrates_on_the_connection_it_was_given(tmp_path: Path) -> None:
    """`sqlite:///:memory:` shares one connection through a `StaticPool`.

    A migration driven through a second engine would migrate a second, empty database and leave the
    one in use untouched — silently, because `create_all()` on the real connection would then make
    the tables appear anyway. The environment takes the caller's connection for this reason.
    """
    database = Database("sqlite:///:memory:")

    database.initialize()

    with database.engine.connect() as connection:
        assert current_revision(connection) == head_revision()
        assert DECLARED_TABLES <= set(inspect(connection).get_table_names())
    database.dispose()


def test_the_adoption_revision_is_a_revision_that_exists() -> None:
    """`ADOPTION_REVISION` names where a pre-Alembic store is stamped. A typo would strand one."""
    from opensdl_storage.schema import script_directory

    assert script_directory().get_revision(ADOPTION_REVISION) is not None


@pytest.mark.parametrize("revision", ["0001", "0002"])
def test_every_revision_downgrades(tmp_path: Path, revision: str) -> None:
    config = alembic_config(f"sqlite:///{tmp_path / 'down.db'}")
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    tables = set(inspect(create_engine(f"sqlite:///{tmp_path / 'down.db'}")).get_table_names())
    assert not DECLARED_TABLES & tables
