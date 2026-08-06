"""Alembic environment for the OpenSDL metadata store.

This lives inside `opensdl_storage` rather than beside `alembic.ini` so that the migration history
ships with the models it describes. A generated laboratory installs `opensdl-storage` from a wheel
and has no checkout of this repository; keeping the revisions here is what lets `opensdl migrate`
work there at all.

Two entry points reach this file. `alembic -c database/alembic.ini ...` authors revisions and
builds its own engine from `sqlalchemy.url`. `opensdl_storage.schema` drives migrations
programmatically and passes the connection the caller already holds through
`config.attributes["connection"]` — required, not merely tidy: the in-memory store shares one
SQLite connection through a `StaticPool`, and a second engine would open a second, empty database.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from opensdl_storage.db_models import Base

config = context.config
# Only when Alembic was started from a file. A programmatic `Config()` carries no logging section,
# and reconfiguring logging out from under a host application is not this module's business.
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(**options: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things in place. Batch mode makes a future column change
        # expressible against both supported backends instead of only PostgreSQL.
        render_as_batch=True,
        **options,
    )


def run_migrations_offline() -> None:
    url = os.getenv("OPENSDL_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    _configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if isinstance(connection, Connection):
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    section = dict(config.get_section(config.config_ini_section) or {})
    override = os.getenv("OPENSDL_DATABASE_URL")
    if override:
        section["sqlalchemy.url"] = override
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as opened:
        _configure(connection=opened)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
