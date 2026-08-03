from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opensdl_capabilities import CapabilityRegistry
from opensdl_core import OpenSDLModel
from opensdl_schemas import LabManifest
from opensdl_storage import RepositoryStore


class ContextPack(OpenSDLModel):
    generated_at: datetime
    laboratory: dict[str, Any]
    environment: str
    capabilities: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    domain_packs: list[dict[str, Any]]
    active_runs: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    policy_version: str


class ContextPackBuilder:
    def __init__(
        self,
        manifest: LabManifest,
        registry: CapabilityRegistry,
        repositories: RepositoryStore,
        policy_version: str,
        domain_packs: list[dict[str, Any]] | None = None,
    ) -> None:
        self.manifest = manifest
        self.registry = registry
        self.repositories = repositories
        self.policy_version = policy_version
        self.domain_packs = domain_packs or []

    def build(self, *, event_limit: int = 50) -> ContextPack:
        terminal_states = {"completed", "failed", "aborted"}
        active = [
            run for run in self.repositories.list_runs() if run.state.value not in terminal_states
        ]
        recent_events = self.repositories.list_events(
            limit=event_limit,
            newest_first=True,
        )
        return ContextPack(
            generated_at=datetime.now(UTC),
            laboratory=self.manifest.metadata.model_dump(mode="json"),
            environment=self.manifest.spec.environment,
            capabilities=[
                item.model_dump(mode="json") for item in self.registry.list_capabilities()
            ],
            resources=[item.model_dump(mode="json") for item in self.repositories.list_resources()],
            domain_packs=self.domain_packs,
            active_runs=[item.model_dump(mode="json") for item in active],
            recent_events=[item.model_dump(mode="json") for item in reversed(recent_events)],
            policy_version=self.policy_version,
        )
