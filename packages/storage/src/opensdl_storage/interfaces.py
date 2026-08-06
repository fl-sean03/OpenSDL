from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from opensdl_core import (
    ArtifactKind,
    ArtifactRecord,
    CapabilityDefinition,
    EventRecord,
    Resource,
    RunRecord,
    RunState,
    TaskRecord,
)


@runtime_checkable
class RepositoryStore(Protocol):
    """Persistence boundary used by runtimes, gateways, and exporters."""

    def create_run(self, record: RunRecord) -> RunRecord: ...

    def update_run(
        self,
        run_id: str,
        *,
        state: RunState | None = None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> RunRecord: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...

    def list_runs(
        self,
        states: Iterable[RunState] | None = None,
    ) -> list[RunRecord]: ...

    def upsert_task(self, record: TaskRecord) -> TaskRecord: ...

    def get_task(self, task_id: str) -> TaskRecord | None: ...

    def get_task_for_step(self, run_id: str, step_id: str) -> TaskRecord | None: ...

    def list_tasks(self, run_id: str) -> list[TaskRecord]: ...

    def append_event(self, event: EventRecord) -> EventRecord: ...

    def list_events(
        self,
        *,
        run_id: str | None = None,
        campaign_id: str | None = None,
        types: Iterable[str] | None = None,
        limit: int | None = 500,
        newest_first: bool = False,
    ) -> list[EventRecord]: ...

    def upsert_resource(self, resource: Resource) -> Resource: ...

    def list_resources(self) -> list[Resource]: ...

    def missing_resources(self, resource_ids: list[str]) -> list[str]: ...

    def upsert_capability(
        self,
        definition: CapabilityDefinition,
        adapter_name: str,
    ) -> CapabilityDefinition: ...

    def list_capabilities(self) -> list[tuple[CapabilityDefinition, str]]: ...

    def acquire_leases(
        self,
        resource_ids: list[str],
        holder_id: str,
        ttl_seconds: float,
    ) -> bool: ...

    def release_leases(self, holder_id: str) -> None: ...

    def add_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord: ...

    def list_artifacts(self, run_id: str | None = None) -> list[ArtifactRecord]: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Immutable artifact storage boundary."""

    root: Path

    def put_bytes(
        self,
        data: bytes,
        *,
        media_type: str,
        kind: ArtifactKind = ArtifactKind.OTHER,
        run_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord: ...

    def put_json(self, value: Any, **kwargs: Any) -> ArtifactRecord: ...

    def read_bytes(self, artifact: ArtifactRecord) -> bytes: ...
