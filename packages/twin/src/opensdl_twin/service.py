from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from opensdl_core import EventRecord

from .loader import (
    LoadedTwinDefinition,
    VerifiedTwinScene,
    load_twin_definition,
    read_verified_scene,
)
from .models import TwinCue, TwinDefinition
from .projector import project_events


class TwinService:
    """Read-only façade over one verified twin definition and its event projector."""

    def __init__(self, loaded: LoadedTwinDefinition) -> None:
        self._loaded = loaded

    @classmethod
    def from_file(cls, path: str | Path) -> "TwinService":
        return cls(load_twin_definition(path))

    @property
    def definition(self) -> TwinDefinition:
        return self._loaded.definition

    @property
    def definition_path(self) -> Path:
        return self._loaded.definition_path

    @property
    def scene_path(self) -> Path:
        return self._loaded.scene_path

    def read_scene(self) -> VerifiedTwinScene:
        """Return the exact scene bytes after re-verifying their declared digest."""

        return read_verified_scene(self.scene_path, self.definition.scene.sha256)

    def project_run(
        self,
        events: Iterable[EventRecord],
        task_capabilities: Mapping[str, str],
    ) -> tuple[TwinCue, ...]:
        return project_events(self.definition, events, task_capabilities)
