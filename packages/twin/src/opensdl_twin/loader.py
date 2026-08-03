from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import TwinDefinition


class TwinLoadError(ValueError):
    """A twin definition's scene asset could not be loaded safely or verified."""


class TwinSceneNotFoundError(TwinLoadError):
    """A configured twin scene no longer exists as a readable file."""


@dataclass(frozen=True, slots=True)
class LoadedTwinDefinition:
    definition: TwinDefinition
    definition_path: Path
    scene_path: Path


@dataclass(frozen=True, slots=True)
class VerifiedTwinScene:
    """Scene bytes whose digest was verified after they were read."""

    content: bytes
    sha256: str


def load_twin_definition(path: str | Path) -> LoadedTwinDefinition:
    """Load a twin definition and verify its definition-relative scene asset."""

    definition_path = Path(path).expanduser().resolve(strict=True)
    if not definition_path.is_file():
        raise TwinLoadError(f"twin definition is not a file: {definition_path}")
    data: Any = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TwinLoadError("twin definition must contain a mapping")
    definition = TwinDefinition.model_validate(data)

    base = definition_path.parent.resolve(strict=True)
    scene_path = (base / definition.scene.path).resolve(strict=False)
    if not scene_path.is_relative_to(base):
        raise TwinLoadError("resolved scene path escapes the twin definition directory")
    if not scene_path.is_file():
        raise TwinLoadError(f"twin scene is not a file: {scene_path}")
    digest = _sha256_file(scene_path)
    if digest != definition.scene.sha256:
        raise TwinLoadError(
            f"twin scene digest mismatch: expected {definition.scene.sha256}, got {digest}"
        )
    return LoadedTwinDefinition(
        definition=definition,
        definition_path=definition_path,
        scene_path=scene_path,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_verified_scene(path: Path, expected_sha256: str) -> VerifiedTwinScene:
    """Read once, hash those exact bytes, and return them only when verified."""

    try:
        content = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError) as exc:
        raise TwinSceneNotFoundError(f"twin scene is not a file: {path}") from exc
    except OSError as exc:
        raise TwinLoadError(f"twin scene could not be read: {path}") from exc
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_sha256:
        raise TwinLoadError(f"twin scene digest mismatch: expected {expected_sha256}, got {digest}")
    return VerifiedTwinScene(content=content, sha256=digest)
