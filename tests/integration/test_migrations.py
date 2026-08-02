from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    database_path = tmp_path / "migration.db"
    config = Config(str(root / "database" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(f"sqlite:///{database_path}")).get_table_names())
    assert {"runs", "tasks", "events", "artifacts", "resources", "capabilities"} <= tables
