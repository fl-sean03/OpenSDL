from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class SchemaVersionRow(Base):
    __tablename__ = "schema_versions"
    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(255), index=True)
    workflow_version: Mapped[str] = mapped_column(String(64), default="0.1.0")
    state: Mapped[str] = mapped_column(String(64), index=True)
    inputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    operator_id: Mapped[str] = mapped_column(String(255), index=True)
    environment: Mapped[str] = mapped_column(String(64), index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("run_id", "step_id", name="uq_task_run_step"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String(255))
    capability_id: Mapped[str] = mapped_column(String(255), index=True)
    state: Mapped[str] = mapped_column(String(64), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    inputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    outputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(255), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(255), index=True)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    causation_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ResourceRow(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(128), index=True)
    state: Mapped[str] = mapped_column(String(128), index=True)
    location_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    quantity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CapabilityRow(Base):
    __tablename__ = "capabilities"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    adapter_name: Mapped[str] = mapped_column(String(255), index=True)
    definition_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LeaseRow(Base):
    __tablename__ = "resource_leases"
    resource_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    holder_id: Mapped[str] = mapped_column(String(80), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    media_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
