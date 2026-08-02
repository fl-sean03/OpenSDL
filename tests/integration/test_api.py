from pathlib import Path
import shutil

from fastapi.testclient import TestClient

from opensdl_api import create_app
from opensdl_controller import OpenSDLSystem


def test_api_runs_workflow(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
    system = OpenSDLSystem.from_manifest(target / "opensdl.yaml")
    app = create_app(system)
    workflow = __import__("yaml").safe_load((target / "workflow.yaml").read_text())
    with TestClient(app) as client:
        assert client.get("/health").json()["passed"]
        response = client.post("/runs", json={
            "workflow": workflow,
            "inputs": {"sample_id":"api","red_fraction":0.5,"blue_fraction":0.5,"total_mass_g":5,"target_rgb":[127.5,0,127.5]},
        })
        assert response.status_code == 200, response.text
        assert response.json()["run"]["outputs"]["score"] == 0
