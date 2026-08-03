import hashlib
from pathlib import Path
import shutil
from importlib.metadata import version as distribution_version

import yaml

from fastapi.testclient import TestClient

from opensdl_api import create_app
from opensdl_controller import OpenSDLSystem
from opensdl_twin import TwinProjectionError, TwinService


def _write_twin(target: Path, scene_content: bytes) -> TwinService:
    scene = target / "scene.glb"
    scene.write_bytes(scene_content)
    definition = {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "DigitalTwin",
        "version": "0.1.0",
        "revision": "rev-1",
        "coordinateFrame": {
            "unit": "m",
            "handedness": "right",
            "upAxis": "Z",
            "origin": [0, 0, 0],
        },
        "scene": {
            "path": "scene.glb",
            "sha256": hashlib.sha256(scene_content).hexdigest(),
        },
        "entities": [{"id": "robot", "node": "RobotRoot"}],
        "anchors": [{"id": "input", "position": [0, 0, 0]}],
    }
    path = target / "twin.yaml"
    path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    return TwinService.from_file(path)


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
    assert app.version == distribution_version("opensdl-api")
    workflow = __import__("yaml").safe_load((target / "workflow.yaml").read_text())
    with TestClient(app) as client:
        assert client.get("/health").json()["passed"]
        response = client.post(
            "/runs",
            json={
                "workflow": workflow,
                "inputs": {
                    "sample_id": "api",
                    "red_fraction": 0.5,
                    "blue_fraction": 0.5,
                    "total_mass_g": 5,
                    "target_rgb": [127.5, 0, 127.5],
                },
                "run_id": "run-api-stable",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["run"]["id"] == "run-api-stable"
        assert response.json()["run"]["outputs"]["score"] == 0
        unsafe_response = client.post(
            "/runs",
            json={"workflow": workflow, "run_id": "../../escape"},
        )
        assert unsafe_response.status_code == 422
        assert client.get("/events", params={"run_id": "../escape"}).status_code == 422
        assert client.get(r"/runs/run%5C..%5Cescape").status_code == 422
        for path in (
            "/twin",
            "/twin/scene.glb",
            "/twin/runs/run-api-stable",
            "/viewer",
            "/viewer/app.js",
        ):
            assert client.get(path).status_code == 404


def test_api_serves_only_configured_twin_and_viewer_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
    viewer_root = target / "viewer"
    viewer_root.mkdir()
    (viewer_root / "index.html").write_text("<main>Twin viewer</main>", encoding="utf-8")
    (viewer_root / "app.js").write_text("const configured = true;", encoding="utf-8")
    secret = target / "secret.txt"
    secret.write_text("not public", encoding="utf-8")
    (viewer_root / "escape.txt").symlink_to(secret)
    scene_content = b"configured-scene"
    twin = _write_twin(target, scene_content)

    system = OpenSDLSystem.from_manifest(target / "opensdl.yaml")
    monkeypatch.setattr(system, "twin", twin)
    monkeypatch.setattr(system, "twin_viewer_root", viewer_root)
    monkeypatch.setattr(
        system,
        "project_twin_run",
        lambda run_id: {
            "definition_revision": "rev-1",
            "run_id": run_id,
            "cues": [],
        },
    )

    with TestClient(create_app(system)) as client:
        openapi = client.get("/openapi.json").json()
        twin_schema = openapi["paths"]["/twin"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        projection_schema = openapi["paths"]["/twin/runs/{run_id}"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        scene_response_content = openapi["paths"]["/twin/scene.glb"]["get"]["responses"]["200"][
            "content"
        ]
        assert twin_schema["$ref"].endswith("/TwinDefinition")
        assert projection_schema["$ref"].endswith("/TwinProjectionResponse")
        assert "model/gltf-binary" in scene_response_content

        twin_response = client.get("/twin")
        assert twin_response.json()["kind"] == "DigitalTwin"
        assert "node" not in twin_response.json()["anchors"][0]
        scene_response = client.get("/twin/scene.glb")
        assert scene_response.status_code == 200
        assert scene_response.content == scene_content
        assert scene_response.headers["content-type"] == "model/gltf-binary"
        digest = hashlib.sha256(scene_content).hexdigest()
        assert scene_response.headers["etag"] == f'"{digest}"'
        assert scene_response.headers["x-content-sha256"] == digest
        assert client.get("/twin/runs/run-1").json() == {
            "definition_revision": "rev-1",
            "run_id": "run-1",
            "cues": [],
        }
        assert "Twin viewer" in client.get("/viewer").text
        assert client.get("/viewer/app.js").text == "const configured = true;"
        assert client.get("/viewer/escape.txt").status_code == 404
        assert client.get("/viewer/%2e%2e/secret.txt").status_code == 404

        twin.scene_path.write_bytes(b"replaced-after-startup")
        replaced = client.get("/twin/scene.glb")
        assert replaced.status_code == 409
        assert replaced.json() == {"detail": "twin scene verification failed"}

        def fail_projection(_: str) -> dict[str, object]:
            raise TwinProjectionError("invalid persisted event projection")

        monkeypatch.setattr(system, "project_twin_run", fail_projection)
        invalid_projection = client.get("/twin/runs/run-1")
        assert invalid_projection.status_code == 422
        assert invalid_projection.json() == {"detail": "twin run projection failed"}
