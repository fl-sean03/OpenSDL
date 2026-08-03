from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, select

from opensdl_core import (
    ArtifactKind,
    ArtifactRecord,
    CapabilityDefinition,
    EventRecord,
    Quantity,
    Resource,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
    utc_now,
)

from .database import Database
from .db_models import ArtifactRow, CapabilityRow, EventRow, LeaseRow, ResourceRow, RunRow, TaskRow


class Repositories:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_run(self, record: RunRecord) -> RunRecord:
        with self.database.session() as session:
            session.add(
                RunRow(
                    id=record.id,
                    workflow_id=record.workflow_id,
                    workflow_version=record.workflow_version,
                    state=record.state.value,
                    inputs_json=record.inputs,
                    outputs_json=record.outputs,
                    operator_id=record.operator_id,
                    environment=record.environment,
                    error=record.error,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            )
        return record

    def update_run(
        self,
        run_id: str,
        *,
        state: RunState | None = None,
        outputs: dict | None = None,
        error: str | None = None,
    ) -> RunRecord:
        with self.database.session() as session:
            row = session.get(RunRow, run_id)
            if row is None:
                raise KeyError(run_id)
            if state is not None:
                row.state = state.value
            if outputs is not None:
                row.outputs_json = outputs
            row.error = error
            row.updated_at = utc_now()
            session.flush()
            return self._run_from_row(row)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self.database.session() as session:
            row = session.get(RunRow, run_id)
            return self._run_from_row(row) if row else None

    def list_runs(self, states: Iterable[RunState] | None = None) -> list[RunRecord]:
        with self.database.session() as session:
            statement = select(RunRow).order_by(RunRow.created_at.desc())
            if states:
                statement = statement.where(RunRow.state.in_([state.value for state in states]))
            return [self._run_from_row(row) for row in session.scalars(statement)]

    def upsert_task(self, record: TaskRecord) -> TaskRecord:
        with self.database.session() as session:
            row = session.get(TaskRow, record.id)
            if row is None:
                row = TaskRow(
                    id=record.id,
                    run_id=record.run_id,
                    step_id=record.step_id,
                    capability_id=record.capability_id,
                    state=record.state.value,
                )
                session.add(row)
            row.state = record.state.value
            row.attempt = record.attempt
            row.inputs_json = record.inputs
            row.outputs_json = record.outputs
            row.error = record.error
            row.created_at = record.created_at
            row.updated_at = record.updated_at
            session.flush()
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self.database.session() as session:
            row = session.get(TaskRow, task_id)
            return self._task_from_row(row) if row else None

    def get_task_for_step(self, run_id: str, step_id: str) -> TaskRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TaskRow).where(TaskRow.run_id == run_id, TaskRow.step_id == step_id)
            )
            return self._task_from_row(row) if row else None

    def list_tasks(self, run_id: str) -> list[TaskRecord]:
        with self.database.session() as session:
            rows = session.scalars(
                select(TaskRow).where(TaskRow.run_id == run_id).order_by(TaskRow.created_at)
            )
            return [self._task_from_row(row) for row in rows]

    def append_event(self, event: EventRecord) -> EventRecord:
        with self.database.session() as session:
            session.add(
                EventRow(
                    id=event.id,
                    type=event.type,
                    occurred_at=event.occurred_at,
                    actor_id=event.actor_id,
                    run_id=event.run_id,
                    task_id=event.task_id,
                    campaign_id=event.campaign_id,
                    causation_id=event.causation_id,
                    correlation_id=event.correlation_id,
                    payload_json=event.payload,
                )
            )
        return event

    def list_events(
        self,
        *,
        run_id: str | None = None,
        campaign_id: str | None = None,
        limit: int | None = 500,
        newest_first: bool = False,
    ) -> list[EventRecord]:
        with self.database.session() as session:
            ordering = (
                (EventRow.occurred_at.desc(), EventRow.id.desc())
                if newest_first
                else (EventRow.occurred_at.asc(), EventRow.id.asc())
            )
            statement = select(EventRow).order_by(*ordering)
            if run_id is not None:
                statement = statement.where(EventRow.run_id == run_id)
            if campaign_id is not None:
                statement = statement.where(EventRow.campaign_id == campaign_id)
            if limit is not None:
                statement = statement.limit(limit)
            return [self._event_from_row(row) for row in session.scalars(statement)]

    def upsert_resource(self, resource: Resource) -> Resource:
        with self.database.session() as session:
            row = session.get(ResourceRow, resource.id)
            if row is None:
                row = ResourceRow(
                    id=resource.id, name=resource.name, type=resource.type, state=resource.state
                )
                session.add(row)
            row.name = resource.name
            row.type = resource.type
            row.state = resource.state
            row.location_id = resource.location_id
            row.quantity_json = (
                resource.quantity.model_dump(mode="json") if resource.quantity else None
            )
            row.metadata_json = resource.metadata
            row.updated_at = utc_now()
        return resource

    def list_resources(self) -> list[Resource]:
        with self.database.session() as session:
            rows = session.scalars(select(ResourceRow).order_by(ResourceRow.id))
            return [self._resource_from_row(row) for row in rows]

    def missing_resources(self, resource_ids: list[str]) -> list[str]:
        if not resource_ids:
            return []
        requested = set(resource_ids)
        with self.database.session() as session:
            known = set(
                session.scalars(select(ResourceRow.id).where(ResourceRow.id.in_(requested)))
            )
        return sorted(requested - known)

    def upsert_capability(
        self, definition: CapabilityDefinition, adapter_name: str
    ) -> CapabilityDefinition:
        with self.database.session() as session:
            row = session.get(CapabilityRow, definition.id)
            if row is None:
                row = CapabilityRow(id=definition.id, adapter_name=adapter_name, definition_json={})
                session.add(row)
            row.adapter_name = adapter_name
            row.definition_json = definition.model_dump(mode="json")
            row.updated_at = utc_now()
        return definition

    def list_capabilities(self) -> list[tuple[CapabilityDefinition, str]]:
        with self.database.session() as session:
            return [
                (CapabilityDefinition.model_validate(row.definition_json), row.adapter_name)
                for row in session.scalars(select(CapabilityRow).order_by(CapabilityRow.id))
            ]

    def acquire_leases(self, resource_ids: list[str], holder_id: str, ttl_seconds: float) -> bool:
        if not resource_ids:
            return True
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=ttl_seconds)
        with self.database.session() as session:
            for resource_id in sorted(set(resource_ids)):
                row = session.get(LeaseRow, resource_id)
                if row and self._aware(row.expires_at) > now and row.holder_id != holder_id:
                    return False
            for resource_id in sorted(set(resource_ids)):
                row = session.get(LeaseRow, resource_id)
                if row is None:
                    session.add(
                        LeaseRow(resource_id=resource_id, holder_id=holder_id, expires_at=expires)
                    )
                else:
                    row.holder_id = holder_id
                    row.expires_at = expires
        return True

    def release_leases(self, holder_id: str) -> None:
        with self.database.session() as session:
            session.execute(delete(LeaseRow).where(LeaseRow.holder_id == holder_id))

    def add_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord:
        with self.database.session() as session:
            session.add(
                ArtifactRow(
                    id=artifact.id,
                    sha256=artifact.sha256,
                    media_type=artifact.media_type,
                    size_bytes=artifact.size_bytes,
                    kind=artifact.kind.value,
                    storage_path=artifact.storage_path,
                    run_id=artifact.run_id,
                    task_id=artifact.task_id,
                    metadata_json=artifact.metadata,
                    created_at=artifact.created_at,
                )
            )
        return artifact

    def list_artifacts(self, run_id: str | None = None) -> list[ArtifactRecord]:
        with self.database.session() as session:
            statement = select(ArtifactRow).order_by(ArtifactRow.created_at)
            if run_id:
                statement = statement.where(ArtifactRow.run_id == run_id)
            return [self._artifact_from_row(row) for row in session.scalars(statement)]

    @staticmethod
    def _run_from_row(row: RunRow) -> RunRecord:
        return RunRecord(
            id=row.id,
            workflow_id=row.workflow_id,
            workflow_version=row.workflow_version,
            state=RunState(row.state),
            inputs=row.inputs_json or {},
            outputs=row.outputs_json or {},
            operator_id=row.operator_id,
            environment=row.environment,
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _task_from_row(row: TaskRow) -> TaskRecord:
        return TaskRecord(
            id=row.id,
            run_id=row.run_id,
            step_id=row.step_id,
            capability_id=row.capability_id,
            state=TaskState(row.state),
            attempt=row.attempt,
            inputs=row.inputs_json or {},
            outputs=row.outputs_json or {},
            error=row.error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _event_from_row(row: EventRow) -> EventRecord:
        return EventRecord(
            id=row.id,
            type=row.type,
            occurred_at=row.occurred_at,
            actor_id=row.actor_id,
            run_id=row.run_id,
            task_id=row.task_id,
            campaign_id=row.campaign_id,
            causation_id=row.causation_id,
            correlation_id=row.correlation_id,
            payload=row.payload_json or {},
        )

    @staticmethod
    def _resource_from_row(row: ResourceRow) -> Resource:
        quantity = Quantity.model_validate(row.quantity_json) if row.quantity_json else None
        return Resource(
            id=row.id,
            name=row.name,
            type=row.type,
            state=row.state,
            location_id=row.location_id,
            quantity=quantity,
            metadata=row.metadata_json or {},
        )

    @staticmethod
    def _artifact_from_row(row: ArtifactRow) -> ArtifactRecord:
        return ArtifactRecord(
            id=row.id,
            sha256=row.sha256,
            media_type=row.media_type,
            size_bytes=row.size_bytes,
            kind=ArtifactKind(row.kind),
            storage_path=row.storage_path,
            run_id=row.run_id,
            task_id=row.task_id,
            metadata=row.metadata_json or {},
            created_at=row.created_at,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)
