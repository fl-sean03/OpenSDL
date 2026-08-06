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

The same comparison answers a second question, at the bottom of this file: does a revision do what
it says it does? Every revision declares `opensdl_kind`, because `Database.initialize()` runs the
migration history whenever a laboratory is opened for writing, and a destructive revision would
therefore run inside an ordinary `opensdl run` with nobody asked and no backup taken. A declaration
nothing verifies would be worth nothing, so the declaration is compared against the schema the
revision actually leaves behind.
"""

import ast
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import Script
from sqlalchemy import MetaData, create_engine, inspect, text

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
from opensdl_storage.schema import script_directory

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


# --- What a revision declares, checked against what it does --------------------------------------
#
# `Database.initialize()` migrates a store whenever a laboratory is opened for writing. That is what
# keeps every existing laboratory working, and it is also how a destructive revision would run
# inside an ordinary campaign. Each revision therefore declares whether applying it can destroy
# something:
#
#   opensdl_kind = "additive" | "destructive"
#   opensdl_destroys = ("table:name", "column:table.name", "type:table.column", ...)
#
# Nothing enforces a comment, so nothing here trusts one. `observed_destruction` applies a revision
# in isolation and reads what it removed off the schema it left behind, using the comparison
# `alembic revision --autogenerate` uses. A revision that drops a table, drops a column or changes a
# column's type is destructive whatever it declares, and the declaration has to name exactly what it
# takes.

REVISION_KINDS = ("additive", "destructive")

#: Calls that reach the database outside the schema — a `DELETE` deletes rows and leaves the schema
#: identical, so no comparison can see it. A revision that makes one cannot be proved harmless.
OPAQUE_CALLS = frozenset({"execute", "bulk_insert"})


def revisions() -> list[Script]:
    """Every revision in the history, oldest first."""
    return sorted(script_directory().walk_revisions(), key=lambda script: script.revision)


REVISION_IDS = [script.revision for script in revisions()]


def declaration(revision: str) -> tuple[str | None, tuple[str, ...] | None]:
    module = script_directory().get_revision(revision).module
    return getattr(module, "opensdl_kind", None), getattr(module, "opensdl_destroys", None)


def reflected(url: str) -> MetaData:
    engine = create_engine(url)
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine)
        return metadata
    finally:
        engine.dispose()


def destruction_since(before: MetaData, url: str) -> set[str]:
    """What the store at `url` no longer holds, compared against the schema `before` describes.

    `compare_metadata` reports the operations that would turn the database back into the metadata,
    so the direction reads inverted and is the point: an `add_table` in the result means the table
    was there before and is not there now.
    """
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            difference = compare_metadata(MigrationContext.configure(connection), before)
    finally:
        engine.dispose()
    return {name for operation in _operations(difference) if (name := _destroyed(operation))}


def _operations(difference: Any) -> Iterator[Any]:
    """Alembic groups several modifications of one column into a nested list."""
    for entry in difference:
        if isinstance(entry, list):
            yield from entry
        else:
            yield entry


def _destroyed(operation: Any) -> str | None:
    if operation[0] == "add_table":
        return f"table:{operation[1].name}"
    if operation[0] == "add_column":
        return f"column:{operation[2]}.{operation[3].name}"
    if operation[0] == "modify_type":
        # Widening is as invisible here as narrowing, and telling them apart across two backends is
        # not something a test should guess at. Every type change counts.
        return f"type:{operation[2]}.{operation[3]}"
    return None


def observed_destruction(revision: str, tmp_path: Path) -> set[str]:
    """Apply one revision to a store already at its predecessor, and read off what it removed."""
    script = script_directory().get_revision(revision)
    previous = script.down_revision
    assert previous is None or isinstance(previous, str), (
        f"revision {revision} merges branches; this comparison assumes a linear history, "
        "which test_the_migration_history_has_exactly_one_head also assumes"
    )
    url = f"sqlite:///{tmp_path / f'{revision}.db'}"
    config = alembic_config(url)
    if previous is not None:
        command.upgrade(config, previous)
    before = reflected(url)
    command.upgrade(config, revision)
    return destruction_since(before, url)


def opaque_calls(revision: str) -> list[str]:
    """Every statement in the revision's `upgrade` that a schema comparison cannot account for.

    `upgrade` only: a downgrade is destructive by definition and is never what
    `Database.initialize()` runs, so raw SQL there says nothing about applying the revision.
    """
    source = Path(script_directory().get_revision(revision).path).read_text(encoding="utf-8")
    return opaque_calls_in(source, revision)


def opaque_calls_in(source: str, revision: str = "under test") -> list[str]:
    upgrades = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
    ]
    assert len(upgrades) == 1, f"revision {revision} does not define exactly one upgrade()"
    return [
        node.func.attr
        for node in ast.walk(upgrades[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in OPAQUE_CALLS
    ]


@pytest.mark.parametrize("revision", REVISION_IDS)
def test_every_revision_declares_whether_it_is_destructive(revision: str) -> None:
    kind, destroys = declaration(revision)

    assert kind in REVISION_KINDS, (
        f"revision {revision} declares opensdl_kind={kind!r}; a revision that does not say "
        f"whether it destroys anything cannot be applied unattended. Use one of {REVISION_KINDS}."
    )
    assert isinstance(destroys, tuple) and all(isinstance(entry, str) for entry in destroys), (
        f"revision {revision} must declare opensdl_destroys as a tuple of strings, empty when it "
        "destroys nothing"
    )


@pytest.mark.parametrize("revision", REVISION_IDS)
def test_a_revision_destroys_exactly_what_it_declares(revision: str, tmp_path: Path) -> None:
    """The check that makes the declaration worth having.

    Applying the revision to a store at its predecessor and comparing the schema before against the
    schema after says what it really removed. A revision that quietly grew a `drop_column` fails
    here rather than in a laboratory.
    """
    _, destroys = declaration(revision)

    assert set(destroys or ()) == observed_destruction(revision, tmp_path)


@pytest.mark.parametrize("revision", REVISION_IDS)
def test_a_revision_is_declared_destructive_exactly_when_it_can_destroy(revision: str) -> None:
    """Raw SQL counts as destructive, because nothing can prove it is not.

    A `DELETE` or an `UPDATE` empties a column without touching the schema, so the comparison above
    would report nothing at all. Unprovable is treated as dangerous, which is the only reading that
    keeps this check honest.
    """
    kind, destroys = declaration(revision)
    opaque = opaque_calls(revision)

    assert (kind == "destructive") is bool(destroys or opaque), (
        f"revision {revision} declares {kind!r} while destroying {sorted(destroys or ())} and "
        f"issuing {opaque or 'no'} unverifiable statements"
    )


def test_the_history_ships_one_destructive_revision_and_it_is_0002(tmp_path: Path) -> None:
    """Today's ground truth, written down because the enforcement half depends on it.

    Revision 0002 drops `schema_versions` — the hand-rolled version table this project retired in
    favour of `alembic_version`. It is mechanically destructive and every laboratory has to apply
    it: a new store creates the table in 0001 and drops it here, and an adopted store is stamped at
    0001 and arrives here next. So "apply additive revisions on open and refuse destructive ones"
    cannot be read as "refuse every revision declared destructive" without breaking every
    laboratory including new ones. Whatever exempts 0002 has to be written down and reviewable
    rather than inferred from the fact that it happens to be old.
    """
    destructive = {
        revision for revision in REVISION_IDS if declaration(revision)[0] == "destructive"
    }

    assert destructive == {"0002"}
    assert observed_destruction("0002", tmp_path) == {"table:schema_versions"}
    assert opaque_calls("0002") == []


def test_a_generated_revision_already_carries_the_declaration(tmp_path: Path) -> None:
    """`alembic revision` has to produce a file the checks above can read.

    Asserting the template merely contains the word would pass on a template that no longer
    renders, so a revision is actually generated from it, into a copy of the environment. Without
    this the next author never sees the field and the checks above fail on a revision that has
    already been written and reviewed.
    """
    environment = tmp_path / "migrations"
    shutil.copytree(
        script_directory().dir, environment, ignore=shutil.ignore_patterns("__pycache__")
    )
    config = Config()
    config.set_main_option("script_location", str(environment))
    config.set_main_option("file_template", "%%(rev)s_%%(slug)s")

    command.revision(config, message="probe", rev_id="9999")

    generated: dict[str, Any] = {}
    exec(  # noqa: S102 - the file under test was generated by the template being tested
        compile(
            (environment / "versions" / "9999_probe.py").read_text(encoding="utf-8"),
            "9999_probe.py",
            "exec",
        ),
        generated,
    )
    assert generated["opensdl_kind"] == "additive"
    assert generated["opensdl_destroys"] == ()


@pytest.mark.parametrize(
    ("body", "found"),
    [
        ("op.execute(\"DELETE FROM runs WHERE state = 'FAILED'\")", ["execute"]),
        ("op.get_bind().execute(sa.text('UPDATE runs SET error = NULL'))", ["execute"]),
        ("op.bulk_insert(runs, [])", ["bulk_insert"]),
        ("op.add_column('runs', sa.Column('note', sa.Text()))", []),
    ],
    ids=["execute", "execute-on-a-bind", "bulk-insert", "declared-operation"],
)
def test_raw_sql_in_an_upgrade_is_seen(body: str, found: list[str]) -> None:
    """The other half of the proof: a revision that reaches past the schema is recognised.

    A `DELETE` empties a column and leaves the schema byte-identical, so `destruction_since` sees
    nothing at all. Treating that as additive would let exactly the migration this whole check is
    about run unattended.
    """
    source = f"def upgrade() -> None:\n    {body}\n\n\ndef downgrade() -> None:\n    pass\n"

    assert opaque_calls_in(source) == found


def test_raw_sql_in_a_downgrade_is_ignored() -> None:
    """A downgrade is destructive by definition and is never what opening a laboratory runs."""
    source = 'def upgrade() -> None:\n    pass\n\n\ndef downgrade() -> None:\n    op.execute("x")\n'

    assert opaque_calls_in(source) == []


@pytest.mark.parametrize(
    ("statements", "destroyed"),
    [
        (["DROP TABLE keepsake"], {"table:keepsake"}),
        (["ALTER TABLE keepsake DROP COLUMN note"], {"column:keepsake.note"}),
        (
            [
                "ALTER TABLE keepsake RENAME TO superseded",
                "CREATE TABLE keepsake (id VARCHAR(8) PRIMARY KEY, note VARCHAR(8))",
                "INSERT INTO keepsake SELECT * FROM superseded",
                "DROP TABLE superseded",
            ],
            {"type:keepsake.note"},
        ),
        (["ALTER TABLE keepsake ADD COLUMN extra TEXT"], set()),
        (["CREATE INDEX ix_keepsake_note ON keepsake (note)"], set()),
    ],
    ids=["drop-table", "drop-column", "narrow-type", "add-column", "add-index"],
)
def test_the_comparison_catches_each_shape_of_destruction(
    tmp_path: Path, statements: list[str], destroyed: set[str]
) -> None:
    """Proof the check above is not vacuous.

    Both shipped revisions could be truthful for reasons that have nothing to do with the
    comparison working — that is exactly how the six-table-name assertion this file replaced
    survived. Each destructive shape is performed directly here and has to be reported, and the two
    additive ones have to not be.
    """
    url = f"sqlite:///{tmp_path / 'shape.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE keepsake (id VARCHAR(8) PRIMARY KEY, note TEXT)"))
    engine.dispose()
    before = reflected(url)

    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    engine.dispose()

    assert destruction_since(before, url) == destroyed
