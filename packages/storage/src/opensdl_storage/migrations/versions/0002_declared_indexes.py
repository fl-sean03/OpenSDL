"""Create the indexes the models declare, and retire the hand-rolled version table.

Two lineages of store existed before this revision and both arrive here.

A store created by `Database.initialize()` went through SQLAlchemy `create_all()`, which honours
`index=True`, so it already has all 23 indexes and a `schema_versions` row reading `"0001"`. A store
created by `alembic upgrade head` has neither: revision 0001 creates the tables and not one index.
That divergence is what `tests/integration/test_migrations.py` now compares for, and it is why this
revision checks before it acts rather than asserting a single prior shape. Idempotence here is not
defensive habit; it is the only way one revision can serve both histories.

`schema_versions` goes because `alembic_version` now does its job. It was written once at store
creation, never read, never compared, and never advanced — a version record that could not detect a
version difference, sitting next to one that can.
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


#: `(table, column)` for every `index=True` in `db_models.py`. The index name is the one SQLAlchemy
#: generates for that declaration, so a store built by `create_all()` already owns it under exactly
#: this name and is left alone.
DECLARED_INDEXES: tuple[tuple[str, str], ...] = (
    ("artifacts", "run_id"),
    ("artifacts", "sha256"),
    ("artifacts", "task_id"),
    ("capabilities", "adapter_name"),
    ("events", "actor_id"),
    ("events", "campaign_id"),
    ("events", "correlation_id"),
    ("events", "occurred_at"),
    ("events", "run_id"),
    ("events", "task_id"),
    ("events", "type"),
    ("resource_leases", "expires_at"),
    ("resource_leases", "holder_id"),
    ("resources", "location_id"),
    ("resources", "state"),
    ("resources", "type"),
    ("runs", "environment"),
    ("runs", "operator_id"),
    ("runs", "state"),
    ("runs", "workflow_id"),
    ("tasks", "capability_id"),
    ("tasks", "run_id"),
    ("tasks", "state"),
)


def _index_name(table: str, column: str) -> str:
    return f"ix_{table}_{column}"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in DECLARED_INDEXES:
        if table not in tables:
            continue
        name = _index_name(table, column)
        if name in {index["name"] for index in inspector.get_indexes(table)}:
            continue
        op.create_index(name, table, [column])

    if "schema_versions" in tables:
        op.drop_table("schema_versions")


def downgrade() -> None:
    op.create_table(
        "schema_versions",
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, column in DECLARED_INDEXES:
        if table not in tables:
            continue
        name = _index_name(table, column)
        if name in {index["name"] for index in inspector.get_indexes(table)}:
            op.drop_index(name, table_name=table)
