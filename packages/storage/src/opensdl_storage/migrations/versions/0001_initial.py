"""Initial OpenSDL metadata and execution schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_versions",
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("workflow_id", sa.String(255), nullable=False),
        sa.Column("workflow_version", sa.String(64), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
        sa.Column("outputs_json", sa.JSON(), nullable=False),
        sa.Column("operator_id", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(64), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "run_id", sa.String(80), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("step_id", sa.String(255), nullable=False),
        sa.Column("capability_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("inputs_json", sa.JSON(), nullable=False),
        sa.Column("outputs_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "step_id", name="uq_task_run_step"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=True),
        sa.Column("task_id", sa.String(80), nullable=True),
        sa.Column("campaign_id", sa.String(80), nullable=True),
        sa.Column("causation_id", sa.String(80), nullable=True),
        sa.Column("correlation_id", sa.String(80), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("state", sa.String(128), nullable=False),
        sa.Column("location_id", sa.String(80), nullable=True),
        sa.Column("quantity_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("adapter_name", sa.String(255), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "resource_leases",
        sa.Column("resource_id", sa.String(80), primary_key=True),
        sa.Column("holder_id", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("run_id", sa.String(80), nullable=True),
        sa.Column("task_id", sa.String(80), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "artifacts",
        "resource_leases",
        "capabilities",
        "resources",
        "events",
        "tasks",
        "runs",
        "schema_versions",
    ]:
        op.drop_table(table)
