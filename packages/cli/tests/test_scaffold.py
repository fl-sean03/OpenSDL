from __future__ import annotations

from pathlib import Path

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
    assert (root / "scripts/check.sh").stat().st_mode & 0o111
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
    assert (root / "tests/test_adapter.py").exists()


def test_generated_domain_pack_is_installable_shape(tmp_path: Path) -> None:
    root = create_domain_pack(tmp_path / "electrochemistry", name="electrochemistry")
    assert (root / "pyproject.toml").exists()
    assert (
        root
        / "src/opensdl_domain_electrochemistry/pack.py"
    ).exists()
    assert (root / "tests/test_pack.py").exists()
