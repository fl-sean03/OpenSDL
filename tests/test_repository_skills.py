from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
import yaml


ROOT = Path(__file__).parents[1]


def load_validator() -> ModuleType:
    path = ROOT / "scripts" / "validate-repository.py"
    spec = importlib.util.spec_from_file_location("opensdl_repository_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def write_skill(
    skills_root: Path,
    name: str,
    *,
    description: str = "Perform a test procedure. Use when testing skill validation.",
    body: str = "# Test skill\n\nRun the procedure.\n",
    extra_frontmatter: str = "",
) -> Path:
    skill_root = skills_root / name
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"{extra_frontmatter}"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return skill_root


def test_current_repository_skills_and_adapters_are_valid() -> None:
    skills_root = ROOT / ".agents" / "skills"
    assert VALIDATOR.skill_failures(skills_root) == []
    assert (
        VALIDATOR.claude_skill_adapter_failures(
            skills_root,
            ROOT / ".claude" / "skills",
        )
        == []
    )


@pytest.mark.parametrize(
    ("name", "description", "body", "extra_frontmatter", "message"),
    [
        ("Bad_Name", "Do work. Use when requested.", "# Body\n", "", "single hyphens"),
        ("test-skill", "x" * 1025, "# Body\n", "", "1 to 1024"),
        ("test-skill", "Do work on request.", "# Body\n", "", "when to use"),
        ("test-skill", "Do work. Use when requested.", "", "", "must not be empty"),
        (
            "test-skill",
            "Do work. Use when requested.",
            "# Body\n",
            "allowed-tools: Bash\n",
            "only name and description",
        ),
    ],
)
def test_skill_validation_rejects_malformed_content(
    tmp_path: Path,
    name: str,
    description: str,
    body: str,
    extra_frontmatter: str,
    message: str,
) -> None:
    skills_root = tmp_path / ".agents" / "skills"
    write_skill(
        skills_root,
        name,
        description=description,
        body=body,
        extra_frontmatter=extra_frontmatter,
    )
    assert any(message in failure for failure in VALIDATOR.skill_failures(skills_root))


def test_skill_validation_rejects_missing_entrypoint(tmp_path: Path) -> None:
    skills_root = tmp_path / ".agents" / "skills"
    (skills_root / "missing-entrypoint").mkdir(parents=True)
    assert any(
        "missing SKILL.md" in failure
        for failure in VALIDATOR.skill_failures(skills_root)
    )


def test_skill_validation_checks_helpers(tmp_path: Path) -> None:
    skills_root = tmp_path / ".agents" / "skills"
    skill_root = write_skill(skills_root, "helper-test")
    helper = skill_root / "run.sh"
    helper.write_text("#!/usr/bin/env bash\nif\n", encoding="utf-8")
    helper.chmod(0o755)
    failures = VALIDATOR.skill_failures(skills_root)
    assert any("not referenced" in failure for failure in failures)
    assert any("invalid shell syntax" in failure for failure in failures)


def test_claude_adapters_must_match_canonical_skills(tmp_path: Path) -> None:
    skills_root = tmp_path / ".agents" / "skills"
    claude_root = tmp_path / ".claude" / "skills"
    canonical = write_skill(skills_root, "test-skill")
    claude_root.mkdir(parents=True)
    (claude_root / "test-skill").symlink_to(
        Path("../../.agents/skills/test-skill"),
        target_is_directory=True,
    )
    assert VALIDATOR.claude_skill_adapter_failures(skills_root, claude_root) == []
    (claude_root / "extra-skill").symlink_to(canonical, target_is_directory=True)
    assert any(
        "has no canonical skill" in failure
        for failure in VALIDATOR.claude_skill_adapter_failures(skills_root, claude_root)
    )


def test_develop_workflow_helper_stops_outside_simulation(tmp_path: Path) -> None:
    source = ROOT / "examples/simulated-color-mixing/opensdl.yaml"
    manifest = tmp_path / "assisted.yaml"
    manifest.write_text(
        source.read_text(encoding="utf-8").replace(
            "environment: simulation",
            "environment: assisted",
            1,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(ROOT / ".agents/skills/develop-workflow/run.sh"),
            str(ROOT / "examples/simulated-color-mixing/workflow.yaml"),
            str(manifest),
            "{}",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "only executes a simulation manifest" in result.stderr


def test_develop_workflow_helper_checks_bound_adapter_plugins(tmp_path: Path) -> None:
    source = ROOT / "examples/simulated-color-mixing/opensdl.yaml"
    manifest = tmp_path / "unsafe-simulation.yaml"
    manifest.write_text(
        source.read_text(encoding="utf-8").replace(
            "plugin: simulated-lab",
            "plugin: physical-balance",
            1,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(ROOT / ".agents/skills/develop-workflow/run.sh"),
            str(ROOT / "examples/simulated-color-mixing/workflow.yaml"),
            str(manifest),
            "{}",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "enabled adapter simulated-lab resolves to plugin physical-balance" in result.stderr
    assert "allowed plugins are human-task, local-compute, simulated-lab" in result.stderr


def test_develop_workflow_helper_blocks_unused_adapter_before_start(
    tmp_path: Path,
) -> None:
    sentinel = tmp_path / "physical-adapter-started"
    module = tmp_path / "physical_probe.py"
    module.write_text(
        "from pathlib import Path\n"
        "from opensdl_capabilities import CapabilityAdapter\n\n"
        "class PhysicalProbeAdapter(CapabilityAdapter):\n"
        "    name = 'physical-probe'\n\n"
        "    def capability_definitions(self):\n"
        "        return []\n\n"
        "    async def start(self):\n"
        "        Path(self.config['sentinel']).write_text('started', encoding='utf-8')\n\n"
        "    async def execute(self, request):\n"
        "        raise AssertionError('unused physical adapter executed')\n",
        encoding="utf-8",
    )
    distribution = tmp_path / "physical_probe-0.0.0.dist-info"
    distribution.mkdir()
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: physical-probe\nVersion: 0.0.0\n",
        encoding="utf-8",
    )
    (distribution / "entry_points.txt").write_text(
        "[opensdl.adapters]\nphysical-probe = physical_probe:PhysicalProbeAdapter\n",
        encoding="utf-8",
    )

    source = ROOT / "examples/simulated-color-mixing/opensdl.yaml"
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["spec"]["adapters"].append(
        {
            "name": "physical-probe",
            "plugin": "physical-probe",
            "config": {"sentinel": str(sentinel)},
        }
    )
    manifest = tmp_path / "unused-physical-adapter.yaml"
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    workflow = ROOT / "examples/simulated-color-mixing/workflow.yaml"
    environment = os.environ.copy()
    python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(tmp_path)
        if not python_path
        else f"{tmp_path}{os.pathsep}{python_path}"
    )
    inputs = (
        '{"sample_id":"probe-test","red_fraction":0.5,"blue_fraction":0.5,'
        '"total_mass_g":5,"target_rgb":[127.5,0,127.5]}'
    )

    control = subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "opensdl",
            "run",
            str(workflow),
            "--manifest",
            str(manifest),
            "--inputs",
            inputs,
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert control.returncode == 0, control.stderr
    assert sentinel.read_text(encoding="utf-8") == "started"
    sentinel.unlink()

    blocked = subprocess.run(
        [
            str(ROOT / ".agents/skills/develop-workflow/run.sh"),
            str(workflow),
            str(manifest),
            inputs,
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode != 0
    assert "enabled adapter physical-probe resolves to plugin physical-probe" in blocked.stderr
    assert not sentinel.exists()


def test_release_helper_refreshes_lock_before_locked_validation() -> None:
    helper = (ROOT / ".agents/skills/release/run.sh").read_text(encoding="utf-8")
    assert helper.index("find dist") < helper.index('scripts/release.py "$version"')
    assert helper.index('scripts/release.py "$version"') < helper.index("uv lock")
    assert helper.index("uv lock") < helper.index("make test lint example")


def test_orient_helper_does_not_create_runtime_state(tmp_path: Path) -> None:
    manifest = tmp_path / "opensdl.yaml"
    manifest.write_text(
        (ROOT / "examples/simulated-color-mixing/opensdl.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(ROOT / ".agents/skills/orient-lab/run.sh"), str(manifest)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Manifest valid" in result.stdout
    assert not (tmp_path / ".opensdl").exists()
