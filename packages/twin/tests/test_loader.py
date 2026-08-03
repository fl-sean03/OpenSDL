from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from opensdl_twin import (
    TwinLoadError,
    TwinSceneNotFoundError,
    TwinService,
    load_twin_definition,
)


def _write_definition(root: Path, data: dict[str, Any], scene: bytes = b"scene") -> Path:
    scene_path = root / data["scene"]["path"]
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_bytes(scene)
    data["scene"]["sha256"] = hashlib.sha256(scene).hexdigest()
    definition_path = root / "twin.yaml"
    definition_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return definition_path


def test_loader_resolves_scene_relative_to_definition_and_verifies_digest(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    definition_path = _write_definition(tmp_path / "lab", definition_data)

    loaded = load_twin_definition(definition_path)

    assert loaded.definition_path == definition_path.resolve()
    assert loaded.scene_path == (definition_path.parent / "generated/scene.glb").resolve()
    assert loaded.definition.scene.sha256 == hashlib.sha256(b"scene").hexdigest()


def test_loader_rejects_digest_mismatch(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    definition_path = _write_definition(tmp_path, definition_data)
    (tmp_path / "generated/scene.glb").write_bytes(b"tampered")

    with pytest.raises(TwinLoadError, match="digest mismatch"):
        load_twin_definition(definition_path)


def test_loader_rejects_missing_scene(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    definition_path = _write_definition(tmp_path, definition_data)
    (tmp_path / "generated/scene.glb").unlink()

    with pytest.raises(TwinLoadError, match="scene is not a file"):
        load_twin_definition(definition_path)


def test_loader_rejects_scene_symlink_that_escapes_definition_directory(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    lab = tmp_path / "lab"
    definition_path = _write_definition(lab, definition_data)
    outside = tmp_path / "outside.glb"
    outside.write_bytes(b"scene")
    scene_path = lab / "generated/scene.glb"
    scene_path.unlink()
    scene_path.symlink_to(outside)

    with pytest.raises(TwinLoadError, match="escapes"):
        load_twin_definition(definition_path)


def test_loader_rejects_non_mapping_document(tmp_path: Path) -> None:
    path = tmp_path / "twin.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(TwinLoadError, match="must contain a mapping"):
        load_twin_definition(path)


def test_service_reverifies_the_exact_scene_bytes_on_every_read(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    definition_path = _write_definition(tmp_path, definition_data, scene=b"verified-scene")
    service = TwinService.from_file(definition_path)

    first = service.read_scene()

    assert first.content == b"verified-scene"
    assert first.sha256 == hashlib.sha256(first.content).hexdigest()

    service.scene_path.write_bytes(b"replacement")
    with pytest.raises(TwinLoadError, match="digest mismatch"):
        service.read_scene()


def test_service_reports_scene_removed_after_initial_verification(
    tmp_path: Path,
    definition_data: dict[str, Any],
) -> None:
    definition_path = _write_definition(tmp_path, definition_data)
    service = TwinService.from_file(definition_path)
    service.scene_path.unlink()

    with pytest.raises(TwinSceneNotFoundError, match="scene is not a file"):
        service.read_scene()
