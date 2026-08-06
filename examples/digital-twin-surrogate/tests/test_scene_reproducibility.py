from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SCENE_ROOT = EXAMPLE_ROOT / "scene"
ASSET_ROOT = SCENE_ROOT / "assets"
BUILD_SCRIPT = SCENE_ROOT / "build_scene.py"
# The build imports the spatial invariants from the same directory, so the rebuild needs both.
SCENE_SCRIPTS = (BUILD_SCRIPT, SCENE_ROOT / "check_scene.py")

# The build takes about five minutes: it constructs 2340 nodes, then runs every scalar checkpoint,
# the spatial invariants and the eye trace across all 1176 frames before it exports anything.  The
# ceiling guards against a hung headless Blender, so it has to sit far enough above that figure to
# survive a slow CI runner, where the same work takes appreciably longer than on a workstation.
BUILD_TIMEOUT_SECONDS = 900

# Reproduced byte-for-byte: the glTF export is deterministic for a given Blender version.
# `surrogate-cell.blend` is deliberately absent. Blender embeds session state in a saved file, so
# it is not byte-stable across runs and asserting on it would produce a false failure.
REPRODUCIBLE_OUTPUTS = ("surrogate-cell.glb", "node-inventory.json", "motion-validation.json")


def _inventory() -> dict[str, object]:
    return json.loads((ASSET_ROOT / "node-inventory.json").read_text(encoding="utf-8"))


def _expected_blender_version() -> str:
    generator = _inventory()["generator"]
    assert isinstance(generator, dict)
    return str(generator["blender"])


def _installed_blender_version(executable: str) -> str | None:
    result = subprocess.run(
        [executable, "--version"], check=False, capture_output=True, text=True, timeout=120
    )
    match = re.search(r"Blender\s+(\d+\.\d+\.\d+)", result.stdout)
    return match.group(1) if match else None


def _blender_matching_the_recorded_generator() -> tuple[str, str]:
    executable = shutil.which("blender")
    if executable is None:
        pytest.skip("blender is not on PATH; scene reproducibility was not verified")
    installed = _installed_blender_version(executable)
    expected = _expected_blender_version()
    if installed is None:
        pytest.skip("could not read the installed Blender version")
    if installed != expected:
        pytest.skip(
            f"installed Blender {installed} differs from the recorded generator {expected}; "
            "the committed digests describe that version only"
        )
    return executable, expected


def test_the_reference_scene_rebuilds_to_the_committed_bytes(tmp_path: Path) -> None:
    executable, _ = _blender_matching_the_recorded_generator()
    for script in SCENE_SCRIPTS:
        shutil.copy(script, tmp_path / script.name)

    result = subprocess.run(
        [executable, "-b", "--factory-startup", "-noaudio", "-P", BUILD_SCRIPT.name],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    rebuilt_assets = tmp_path / "assets"
    for name in REPRODUCIBLE_OUTPUTS:
        rebuilt = rebuilt_assets / name
        assert rebuilt.is_file(), f"{name} was not produced by the rebuild"
        assert rebuilt.read_bytes() == (ASSET_ROOT / name).read_bytes(), (
            f"{name} does not match the committed artifact"
        )


def test_the_committed_digests_describe_the_recorded_generator() -> None:
    inventory = _inventory()
    scene_digest = hashlib.sha256((ASSET_ROOT / "surrogate-cell.glb").read_bytes()).hexdigest()
    motion = json.loads((ASSET_ROOT / "motion-validation.json").read_text(encoding="utf-8"))

    assert inventory["sha256"] == scene_digest
    assert motion["sha256"] == scene_digest
    assert re.fullmatch(r"\d+\.\d+\.\d+", _expected_blender_version())
