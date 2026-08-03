from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .db_models import Base, SchemaVersionRow


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict = {"future": True}
        if url == "sqlite:///:memory:":
            kwargs.update(
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        elif url.startswith("sqlite:"):
            kwargs.update(connect_args={"check_same_thread": False})
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

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.session() as session:
            exists = session.scalar(
                select(SchemaVersionRow).where(SchemaVersionRow.version == "0001")
            )
            if exists is None:
                session.add(SchemaVersionRow(version="0001"))

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
