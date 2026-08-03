from __future__ import annotations

import importlib.util
import subprocess
from datetime import date
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).parents[1]


def load_release_module() -> ModuleType:
    path = ROOT / "scripts/release.py"
    spec = importlib.util.spec_from_file_location("opensdl_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_release_versions_are_consistent() -> None:
    result = subprocess.run(
        ["uv", "run", "--locked", "python", "scripts/check-version.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_release_update_synchronizes_public_version_surfaces(tmp_path: Path) -> None:
    (tmp_path / "member").mkdir()
    (tmp_path / "packages/cli/src/opensdl_cli/templates/laboratory").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "root"\nversion = "0.1.0a0"\n'
        '[tool.uv.workspace]\nmembers = ["member"]\n',
        encoding="utf-8",
    )
    (tmp_path / "member/pyproject.toml").write_text(
        '[project]\nname = "member"\nversion = "0.1.0a0"\n',
        encoding="utf-8",
    )
    template = tmp_path / "packages/cli/src/opensdl_cli/templates/laboratory/pyproject.toml.j2"
    template.write_text(
        '[project]\ndependencies = ["opensdl-cli>=0.1.0a0"]\n',
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        "cff-version: 1.2.0\nversion: 0.1.0a0\ndate-released: 2026-08-02\n",
        encoding="utf-8",
    )

    release = load_release_module()
    changed = release.update_release_version(
        tmp_path,
        "0.1.0a1",
        released_on=date(2026, 8, 3),
    )

    assert len(changed) == 4
    assert 'version = "0.1.0a1"' in (tmp_path / "pyproject.toml").read_text()
    assert 'version = "0.1.0a1"' in (tmp_path / "member/pyproject.toml").read_text()
    assert "opensdl-cli>=0.1.0a1" in template.read_text()
    assert "version: 0.1.0a1" in (tmp_path / "CITATION.cff").read_text()
    assert "date-released: 2026-08-03" in (tmp_path / "CITATION.cff").read_text()
