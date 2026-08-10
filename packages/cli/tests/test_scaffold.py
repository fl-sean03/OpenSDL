from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from opensdl_cli.scaffold import create_adapter, create_domain_pack, create_laboratory
from opensdl_controller import OpenSDLSystem
from opensdl_schemas import load_manifest, validate_workflow_file


def skill_tree(root: Path) -> dict[str, bytes]:
    """Every file under a skill directory, keyed by its path relative to that directory."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    instructions = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "only when operational evidence is required" in instructions
    assert (root / "scripts/check.sh").stat().st_mode & 0o111
    assert "`my-lab`" in (root / "docs/lab/context.md").read_text(encoding="utf-8")
    assert "`example`" in (root / "docs/lab/context.md").read_text(encoding="utf-8")
    assert (root / "docs/lab/inventory.md").exists()
    assert (root / "docs/lab/setup-plan.md").exists()
    assert (root / "docs/lab/decisions.md").exists()
    start_here = (root / ".agents/skills/start-here/SKILL.md").read_text(encoding="utf-8")
    assert "Do not run `doctor`" in start_here
    assert "no model catalog" in start_here
    assert "opensdl doctor" not in (root / "scripts/check.sh").read_text(encoding="utf-8")
    skill_names = {path.name for path in (root / ".agents/skills").iterdir() if path.is_dir()}
    assert skill_names == {
        "author-skill",
        "debug-run",
        "develop-workflow",
        "orient-lab",
        "start-here",
    }
    for name in sorted(skill_names):
        adapter = root / ".claude/skills" / name
        canonical = root / ".agents/skills" / name
        assert adapter.is_dir()
        # Unconditional: the previous `if adapter.is_symlink()` guard meant the mirror path,
        # which is what non-symlink platforms actually get, asserted nothing.
        assert skill_tree(adapter) == skill_tree(canonical)
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


def ignored(root: Path, *paths: str) -> dict[str, bool]:
    """Ask Git itself which paths the generated `.gitignore` excludes.

    Asserting on the file's text would pass for a pattern in the wrong order — `!.env.example`
    before `.env.*` re-includes nothing — so the question is put to the tool that decides.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return {
        path: subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=root,
            check=False,
        ).returncode
        == 0
        for path in paths
    }


def test_generated_laboratory_ignores_every_environment_file_but_the_example(
    tmp_path: Path,
) -> None:
    """Environment variables are the only sanctioned credential channel in this alpha.

    The template ignored `.env` alone while the documented multi-manifest workflow produces
    `.env.production` and `.env.staging`, so the one file most likely to hold a real credential was
    the one Git tracked.
    """
    root = create_laboratory(tmp_path / "my-lab", owner="example")

    assert ignored(
        root,
        ".env",
        ".env.production",
        ".env.staging",
        ".env.local",
        ".env.example",
    ) == {
        ".env": True,
        ".env.production": True,
        ".env.staging": True,
        ".env.local": True,
        ".env.example": False,
    }


def test_generated_laboratory_ignores_a_lockfile_it_cannot_make_portable(tmp_path: Path) -> None:
    """A lock is normally committed. This one records the machine that generated it.

    The only way to install a generated laboratory today is `uv sync --find-links` against a local
    wheelhouse, which writes that directory into `uv.lock` as a registry for all 22 OpenSDL
    distributions. Committing it makes a fresh clone unresolvable and says nothing about why, so the
    lock stays out of Git until the packages resolve from a real index — and the template says so,
    with the step that reverses it.
    """
    root = create_laboratory(tmp_path / "my-lab", owner="example")

    assert ignored(root, "uv.lock") == {"uv.lock": True}
    recovery = (root / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "uv.lock" in recovery
    assert ".gitignore" in recovery, "the note has to name the line to delete"


def test_generated_laboratory_caps_its_framework_dependencies(tmp_path: Path) -> None:
    """A floor with no ceiling is satisfied by every future release, including a breaking one.

    OpenSDL is pre-1.0, so the next minor may change any contract it publishes. Without a cap an
    unrelated `uv sync` carries a laboratory across that boundary silently.
    """
    root = create_laboratory(tmp_path / "my-lab", owner="example")
    project = (root / "pyproject.toml").read_text(encoding="utf-8")

    for distribution in (
        "opensdl-cli",
        "opensdl-adapter-simulated-lab",
        "opensdl-adapter-local-compute",
        "opensdl-adapter-human-task",
    ):
        assert f'"{distribution}>=0.1.0a0,<0.2.0"' in project
    assert "==" in project, "the note has to name the pin that fixes it for a real run"


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
    assert "simulator_available=True" in source
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "tests/test_adapter.py").exists()


def test_generated_domain_pack_is_installable_shape(tmp_path: Path) -> None:
    root = create_domain_pack(tmp_path / "electrochemistry", name="electrochemistry")
    assert (root / "pyproject.toml").exists()
    assert (root / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (root / "src/opensdl_domain_electrochemistry/pack.py").exists()
    assert (root / "tests/test_pack.py").exists()


@pytest.mark.parametrize("symlinks_available", [True, False])
def test_claude_skills_match_their_canonical_agent_skills_on_both_platforms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlinks_available: bool,
) -> None:
    """Both mechanisms have to produce the same skills.

    A Linux checkout only ever takes the symlink branch, so asserting the mirror only when the
    platform happens to produce one leaves the mirror untested everywhere it matters.
    """
    if not symlinks_available:
        monkeypatch.setattr(Path, "symlink_to", reject_symlink)

    root = create_laboratory(tmp_path / "lab", owner="example")
    canonical_root = root / ".agents/skills"
    mirror_root = root / ".claude/skills"
    names = {path.name for path in canonical_root.iterdir() if path.is_dir()}

    assert names
    assert {path.name for path in mirror_root.iterdir()} == names
    for name in sorted(names):
        adapter = mirror_root / name
        canonical = canonical_root / name
        assert adapter.is_dir()
        assert adapter.is_symlink() is symlinks_available
        if symlinks_available:
            assert adapter.resolve() == canonical.resolve()
        assert skill_tree(adapter) == skill_tree(canonical)


def reject_symlink(*args: object, **kwargs: object) -> None:
    raise OSError("directory symlinks unavailable")


def test_laboratory_scaffold_falls_back_to_validated_skill_mirrors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "symlink_to", reject_symlink)
    root = create_laboratory(tmp_path / "mirrored-lab", owner="example")
    canonical = root / ".agents/skills/orient-lab"
    adapter = root / ".claude/skills/orient-lab"
    assert adapter.is_dir()
    assert not adapter.is_symlink()
    assert skill_tree(adapter) == skill_tree(canonical)

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
    try:
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
    finally:
        # setuptools runs in the package directory and leaves `packages/cli/build/lib/` behind: a
        # gitignored, importable copy of this package that goes stale the moment the source moves
        # on, and that answers every recursive search of the worktree twice. This test is the only
        # thing in the suite that creates it, so this test removes it.
        # `scripts/validate-repository.py` fails while any survives.
        shutil.rmtree(Path(__file__).parents[1] / "build", ignore_errors=True)
    wheel = next(wheelhouse.glob("opensdl_cli-*.whl"))
    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert any(
        name.endswith("templates/laboratory/.agents/skills/orient-lab/SKILL.md.j2")
        for name in names
    )
    assert any(
        name.endswith("templates/laboratory/.agents/skills/start-here/SKILL.md.j2")
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
        "assert (root / '.claude/skills/orient-lab').is_dir(); "
        "assert (root / '.agents/skills/start-here/SKILL.md').is_file(); "
        "assert (root / '.claude/skills/start-here').is_dir(); "
        "assert (root / 'docs/lab/context.md').is_file()"
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
