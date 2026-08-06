from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .schema import SchemaUpgrade, pending_revisions, upgrade_to_head


class Database:
    def __init__(self, url: str, *, create: bool = True) -> None:
        kwargs: dict = {"future": True}
        if url == "sqlite:///:memory:":
            kwargs.update(
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        elif url.startswith("sqlite:"):
            kwargs.update(connect_args={"check_same_thread": False})
            if create:
                self._ensure_sqlite_parent(url)
        self.url = url
        self.engine: Engine = create_engine(url, **kwargs)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    @staticmethod
    def _ensure_sqlite_parent(url: str) -> None:
        prefix = "sqlite:///"
        if not url.startswith(prefix):
            return
        raw = url[len(prefix) :]
        if raw in {":memory:", ""}:
            return
        Path(raw).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> SchemaUpgrade:
        """Bring this store to the current schema and report what that took.

        This used to be `create_all()` plus a hand-written `"0001"` row, which could create a
        missing table and could never change an existing one. It now runs the migration history,
        adopting a store that predates Alembic rather than failing against it. See
        `opensdl_storage.schema` for why Alembic is the only writer.

        The write path calls this when a laboratory is opened; a read-only system never does. A
        store therefore moves to head when something is about to write to it, which is why
        `docs/reference/compatibility.md` says to back up before upgrading OpenSDL. Use
        `pending_upgrade()` to see what would be applied without applying it.
        """
        return upgrade_to_head(self.engine)

    def pending_upgrade(self) -> tuple[str, ...]:
        """Revisions this store is behind, oldest first, without applying any of them."""
        with self.engine.connect() as connection:
            return pending_revisions(connection)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
