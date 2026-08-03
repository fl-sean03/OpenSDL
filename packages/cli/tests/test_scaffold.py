from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from opensdl_cli.scaffold import create_adapter, create_domain_pack, create_laboratory
from opensdl_controller import OpenSDLSystem
from opensdl_schemas import load_manifest, validate_workflow_file


def test_laboratory_scaffold_is_complete_and_valid(tmp_path: Path) -> None:
    root = create_laboratory(tmp_path / "my-lab", owner="example")
    manifest = load_manifest(root / "opensdl.yaml")

    assert manifest.metadata.owner == "example"
    assert {item.plugin for item in manifest.spec.adapters} == {
        "human-task",
        "local-compute",
        "simulated-lab",
    }
    assert (root / ".github/workflows/ci.yml").exists()
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "uv run --no-project --with pyyaml" in workflow
    assert "if: vars.OPENSDL_PACKAGES_AVAILABLE == 'true'" in workflow
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / ".agents/CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "scripts/check.sh").stat().st_mode & 0o111
    skill_names = {
        path.name for path in (root / ".agents/skills").iterdir() if path.is_dir()
    }
    assert skill_names == {
        "author-skill",
        "debug-run",
        "develop-workflow",
        "orient-lab",
    }
    for name in skill_names:
        adapter = root / ".claude/skills" / name
        canonical = root / ".agents/skills" / name
        assert adapter.is_dir()
        if adapter.is_symlink():
            assert adapter.resolve() == canonical.resolve()
    subprocess.run(
        [sys.executable, str(root / "scripts/validate-skills.py")],
        cwd=root,
        check=True,
    )
    for generated in root.rglob("*"):
        if generated.is_file():
            assert "{{" not in generated.read_text(encoding="utf-8")
    assert validate_workflow_file(root / "workflows/first-run.yaml").steps
    assert validate_workflow_file(root / "workflows/manual-check.yaml").steps


@pytest.mark.asyncio
async def test_laboratory_scaffold_runs_physical_compute_and_human_examples(
    tmp_path: Path,
) -> None:
    root = create_laboratory(tmp_path / "my-lab", owner="example")
    system = OpenSDLSystem.from_manifest(root / "opensdl.yaml")
    try:
        await system.start()
        first = await system.run_workflow_file(
            root / "workflows/first-run.yaml",
            {
                "sample_id": "plate-1",
                "red_fraction": 0.5,
                "blue_fraction": 0.5,
                "total_mass_g": 5,
            },
        )
        manual = await system.run_workflow_file(
            root / "workflows/manual-check.yaml",
            {"completed_by": "operator/test"},
        )
        assert first.outputs["score"] == 0
        assert manual.outputs == {
            "outcome": "completed",
            "completed_by": "operator/test",
        }
    finally:
        await system.close()


def test_generated_adapter_is_simulator_first(tmp_path: Path) -> None:
    root = create_adapter(
        tmp_path / "networked-balance",
        name="networked-balance",
        capability_id="instrument.measure_mass",
    )
    source = (root / "src/opensdl_adapter_networked_balance/adapter.py").read_text()
    assert "conformance_cases" in source
    assert 'simulator_available=True' in source
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "tests/test_adapter.py").exists()


def test_generated_domain_pack_is_installable_shape(tmp_path: Path) -> None:
    root = create_domain_pack(tmp_path / "electrochemistry", name="electrochemistry")
    assert (root / "pyproject.toml").exists()
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (
        root
        / "src/opensdl_domain_electrochemistry/pack.py"
    ).exists()
    assert (root / "tests/test_pack.py").exists()


def test_laboratory_scaffold_falls_back_to_validated_skill_mirrors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_symlink(*args: object, **kwargs: object) -> None:
        raise OSError("directory symlinks unavailable")

    monkeypatch.setattr(Path, "symlink_to", reject_symlink)
    root = create_laboratory(tmp_path / "mirrored-lab", owner="example")
    canonical = root / ".agents/skills/orient-lab"
    adapter = root / ".claude/skills/orient-lab"
    assert adapter.is_dir()
    assert not adapter.is_symlink()
    assert (adapter / "SKILL.md").read_bytes() == (canonical / "SKILL.md").read_bytes()

    valid = subprocess.run(
        [sys.executable, str(root / "scripts/validate-skills.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert valid.returncode == 0, valid.stderr

    (canonical / "SKILL.md").write_text(
        (canonical / "SKILL.md").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    drifted = subprocess.run(
        [sys.executable, str(root / "scripts/validate-skills.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert drifted.returncode != 0
    assert "generated mirror has drifted" in drifted.stderr


def test_generated_validator_checks_instruction_imports_and_malformed_metadata(
    tmp_path: Path,
) -> None:
    root = create_laboratory(tmp_path / "invalid-agent-files", owner="example")
    validator = [sys.executable, str(root / "scripts/validate-skills.py")]

    (root / "CLAUDE.md").unlink()
    missing_import = subprocess.run(
        validator,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_import.returncode != 0
    assert "AGENTS.md: missing adjacent CLAUDE.md" in missing_import.stderr

    (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
    skill_path = root / ".agents/skills/orient-lab/SKILL.md"
    original = skill_path.read_text(encoding="utf-8")
    skill_path.write_text("unexpected prefix\n" + original, encoding="utf-8")
    malformed = subprocess.run(
        validator,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert malformed.returncode != 0
    assert "frontmatter must start at the beginning" in malformed.stderr
    assert "Traceback" not in malformed.stderr


def test_cli_wheel_contains_and_renders_hidden_skill_templates(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--package",
            "opensdl-cli",
            "--out-dir",
            str(wheelhouse),
        ],
        cwd=Path(__file__).parents[3],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheelhouse.glob("opensdl_cli-*.whl"))
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert any(
        name.endswith("templates/laboratory/.agents/skills/orient-lab/SKILL.md.j2")
        for name in names
    )

    destination = tmp_path / "wheel-lab"
    script = (
        "from pathlib import Path; "
        "import opensdl_cli; "
        "from opensdl_cli.scaffold import create_laboratory; "
        "assert '.whl/' in str(opensdl_cli.__file__); "
        f"root = create_laboratory(Path({str(destination)!r}), owner='wheel-test'); "
        "assert (root / '.agents/skills/orient-lab/SKILL.md').is_file(); "
        "assert (root / '.claude/skills/orient-lab').is_dir()"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(wheel)
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
