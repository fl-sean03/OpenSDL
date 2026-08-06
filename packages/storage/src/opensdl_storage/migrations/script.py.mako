"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

# `Database.initialize()` runs the migration history whenever a laboratory is opened for writing,
# so a destructive revision would otherwise run inside an ordinary `opensdl run` with nobody asked
# and no backup taken. Declare what this one does. `tests/integration/test_migrations.py` applies
# the revision and compares the schema it leaves behind against these two lines, so an inaccurate
# declaration fails there rather than in a laboratory.
#
# `opensdl_kind` is "destructive" when `opensdl_destroys` is non-empty, and also when the revision
# issues raw SQL — a DELETE leaves the schema identical and no comparison can see it.
# `opensdl_destroys` names every table, column or column type this revision takes away, as
# "table:name", "column:table.name" or "type:table.column".
opensdl_kind: str = "additive"
opensdl_destroys: tuple[str, ...] = ()

def upgrade() -> None:
    ${upgrades if upgrades else "pass"}

def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
