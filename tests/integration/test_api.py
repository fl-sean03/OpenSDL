import hashlib
from pathlib import Path
import shutil
from importlib.metadata import version as distribution_version
from typing import Any, Callable

import pytest
import yaml

from fastapi.testclient import TestClient

from opensdl_api import create_app
from opensdl_controller import OpenSDLSystem
from opensdl_core import EventRecord, RunRecord, RunState
from opensdl_storage import Database, Repositories
from opensdl_twin import TwinProjectionError, TwinService

EXAMPLE = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
VALID_INPUTS = {
    "sample_id": "api",
    "red_fraction": 0.5,
    "blue_fraction": 0.5,
    "total_mass_g": 5,
    "target_rgb": [127.5, 0, 127.5],
}
MIX_INPUTS = {key: value for key, value in VALID_INPUTS.items() if key != "target_rgb"}


def _copy_example(tmp_path: Path) -> Path:
    target = tmp_path / "lab"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return target


def _edit(path: Path, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return document


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


@pytest.mark.integration
def test_a_denied_request_is_not_reported_as_a_malformed_one(tmp_path: Path) -> None:
    """Denial, malformed input, and a crash were all `400 {"detail": "<str(exc)>"}`.

    A client had no way to tell "policy will never allow this" from "you sent nonsense", and the
    only thing distinguishing them was prose lifted out of an exception.
    """
    lab = _copy_example(tmp_path)
    _edit(
        lab / "opensdl.yaml",
        lambda document: document["spec"]["policy"].update(default_effect="deny", rules=[]),
    )

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        denied = client.post(
            "/capabilities/sim.mix_color/execute",
            json={"inputs": MIX_INPUTS},
        )

    assert denied.status_code == 403, denied.text
    assert "default policy effect" not in denied.text


@pytest.mark.integration
def test_an_unknown_capability_is_a_not_found(tmp_path: Path) -> None:
    lab = _copy_example(tmp_path)

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        response = client.post("/capabilities/sim.mix_colour/execute", json={"inputs": {}})

    assert response.status_code == 404, response.text


@pytest.mark.integration
def test_an_unavailable_resource_is_a_conflict(tmp_path: Path) -> None:
    lab = _copy_example(tmp_path)
    workflow = _edit(
        lab / "workflow.yaml",
        lambda document: document["steps"][0].update(resources=["instrument-nobody-registered"]),
    )

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        response = client.post("/runs", json={"workflow": workflow, "inputs": VALID_INPUTS})

    assert response.status_code == 409, response.text
    assert "instrument-nobody-registered" not in response.text


@pytest.mark.integration
def test_a_declared_timeout_is_a_gateway_timeout(tmp_path: Path) -> None:
    lab = _copy_example(tmp_path)
    _edit(
        lab / "opensdl.yaml",
        lambda document: document["spec"]["adapters"][0]["config"].update(latency_seconds=2.0),
    )
    workflow = _edit(
        lab / "workflow.yaml",
        lambda document: document["steps"][0].update(timeout_seconds=0.05, retries=0),
    )

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        response = client.post("/runs", json={"workflow": workflow, "inputs": VALID_INPUTS})

    assert response.status_code == 504, response.text


@pytest.mark.integration
def test_a_workflow_that_is_not_a_workflow_is_unprocessable(tmp_path: Path) -> None:
    lab = _copy_example(tmp_path)

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        response = client.post("/runs", json={"workflow": {"id": "not-a-workflow"}})

    assert response.status_code == 422, response.text


@pytest.mark.integration
def test_the_event_query_limit_is_bounded(tmp_path: Path) -> None:
    """An unbounded limit is a request for the entire permanent event log in one response."""
    lab = _copy_example(tmp_path)

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        assert client.get("/events", params={"limit": 1_000_000}).status_code == 422
        assert client.get("/events", params={"limit": 0}).status_code == 422
        assert client.get("/events", params={"limit": 50}).status_code == 200


@pytest.mark.integration
def test_the_documented_contract_includes_the_failures_the_code_returns(tmp_path: Path) -> None:
    """A generated client only knows the statuses OpenAPI declares. Every route said `200`."""
    lab = _copy_example(tmp_path)

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        paths = client.get("/openapi.json").json()["paths"]

    submit = set(paths["/runs"]["post"]["responses"])
    execute = set(paths["/capabilities/{capability_id}/execute"]["post"]["responses"])
    assert {"403", "404", "409", "422", "500", "504"} <= submit
    assert {"403", "404", "409", "422", "500", "504"} <= execute
    assert "404" in paths["/runs/{run_id}"]["get"]["responses"]
    assert "404" in paths["/twin"]["get"]["responses"]
    assert {"404", "409"} <= set(paths["/twin/scene.glb"]["get"]["responses"])
    assert {"404", "422"} <= set(paths["/twin/runs/{run_id}"]["get"]["responses"])
    assert "404" in paths["/viewer/{asset_path}"]["get"]["responses"]


@pytest.mark.integration
def test_the_advertised_tools_can_be_called_over_the_transport_that_advertises_them(
    tmp_path: Path,
) -> None:
    """`GET /tools` published five names that appeared nowhere else in the project."""
    lab = _copy_example(tmp_path)

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        catalogue = client.get("/tools").json()
        names = [tool["name"] for tool in catalogue]
        assert names == sorted(names, key=names.index)

        for tool in catalogue:
            assert tool["input_schema"]["type"] == "object"
            declared = set(tool["input_schema"].get("required", []))
            assert declared <= set(tool["input_schema"]["properties"]), tool["name"]

        executed = client.post(
            "/tools/execute_capability",
            json={"arguments": {"capability_id": "sim.mix_color", "inputs": MIX_INPUTS}},
        )
        assert executed.status_code == 200, executed.text
        run_id = executed.json()["run"]["id"]
        assert client.post("/tools/describe_lab", json={}).status_code == 200
        assert client.post("/tools/list_capabilities", json={}).status_code == 200
        assert (
            client.post("/tools/inspect_run", json={"arguments": {"run_id": run_id}}).json()["run"][
                "id"
            ]
            == run_id
        )
        assert (
            client.post("/tools/query_events", json={"arguments": {"limit": 5}}).status_code == 200
        )
        assert client.post("/tools/capability.execute", json={}).status_code == 404
        assert client.post("/tools/inspect_run", json={"arguments": {}}).status_code == 422


@pytest.mark.integration
def test_the_server_reconciles_runs_a_stopped_controller_left_active(tmp_path: Path) -> None:
    """A restarting server is exactly where crash recovery is wanted, and the only place left.

    `OpenSDLSystem.start()` stopped reconciling implicitly, which was right — it made
    `opensdl doctor` destroy the record of a live experiment. Without an explicit request here,
    a controller that died mid-run leaves those runs `RUNNING` with their leases held forever.
    """
    lab = _copy_example(tmp_path)
    database = Database(f"sqlite:///{lab / '.opensdl' / 'opensdl.db'}")
    database.initialize()
    Repositories(database).create_run(
        RunRecord(
            id="run-left-active",
            workflow_id="color-mix-and-score",
            state=RunState.RUNNING,
            operator_id="operator/crashed",
            environment="simulation",
        )
    )
    database.dispose()

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        health = client.get("/health").json()
        assert [run["id"] for run in health["reconciled_runs"]] == ["run-left-active"]
        recovered = client.get("/runs/run-left-active").json()["run"]
        assert recovered["state"] == "intervention_required"


def _seed_campaign(lab: Path, campaign_id: str) -> None:
    """Write a campaign that started and never recorded a completion, as a live one looks."""
    database = Database(f"sqlite:///{lab / '.opensdl' / 'opensdl.db'}")
    database.initialize()
    repositories = Repositories(database)
    repositories.append_event(
        EventRecord(
            type="CampaignStarted",
            actor_id="software/campaign",
            campaign_id=campaign_id,
            payload={
                "workflowId": "color-mix-and-score",
                "workflowVersion": "0.1.0",
                "environment": "simulation",
                "operatorId": "software/campaign",
                "maxIterations": 5,
                "scoreOutput": "score",
                "minimize": True,
                "targetScore": None,
                "maxConsecutiveFailures": 3,
                "maxDurationSeconds": None,
                "iterationIdInput": "sample_id",
                "baseInputs": {"total_mass_g": 5.0},
            },
        )
    )
    repositories.append_event(
        EventRecord(
            type="CampaignIterationStarted",
            actor_id="software/campaign",
            campaign_id=campaign_id,
            payload={
                "iteration": 0,
                "candidate": {"red_fraction": 0.5},
                "runId": "run-campaign-0",
                "environment": "simulation",
            },
        )
    )
    database.dispose()


@pytest.mark.integration
def test_a_campaign_can_be_read_over_http(tmp_path: Path) -> None:
    """`campaign` appeared in no route at all, so no remote client could see the closed loop.

    The read half is served here. There is deliberately no `POST /campaigns`: a campaign runs for
    days and `POST /runs` already demonstrates what awaiting long work inside a request handler
    costs.
    """
    lab = _copy_example(tmp_path)
    _seed_campaign(lab, "campaign-http")

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        listed = client.get("/campaigns")
        assert listed.status_code == 200, listed.text
        assert [item["campaign_id"] for item in listed.json()] == ["campaign-http"]

        inspected = client.get("/campaigns/campaign-http")
        assert inspected.status_code == 200, inspected.text
        campaign = inspected.json()["campaign"]
        assert campaign["state"] == "running"
        assert campaign["environment"] == "simulation"
        assert campaign["operator_id"] == "software/campaign"
        assert [item["run_id"] for item in campaign["iterations"]] == ["run-campaign-0"]
        assert {event["type"] for event in inspected.json()["events"]} == {
            "CampaignStarted",
            "CampaignIterationStarted",
        }

        assert client.get("/campaigns/campaign-absent").status_code == 404
        assert client.get("/campaigns/%5C..%5Cescape").status_code in {404, 422}

        scoped = client.get("/events", params={"campaign_id": "campaign-http"})
        assert scoped.status_code == 200, scoped.text
        assert {event["campaign_id"] for event in scoped.json()} == {"campaign-http"}

        context = client.get("/context").json()
        assert [item["campaign_id"] for item in context["active_campaigns"]] == ["campaign-http"]

        paths = client.get("/openapi.json").json()["paths"]
        assert "404" in paths["/campaigns/{campaign_id}"]["get"]["responses"]


@pytest.mark.integration
def test_the_campaign_tools_are_callable_over_the_transport_that_advertises_them(
    tmp_path: Path,
) -> None:
    lab = _copy_example(tmp_path)
    _seed_campaign(lab, "campaign-tools")

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        names = {tool["name"] for tool in client.get("/tools").json()}
        assert {"list_campaigns", "inspect_campaign"} <= names

        listed = client.post("/tools/list_campaigns", json={})
        assert [item["campaign_id"] for item in listed.json()] == ["campaign-tools"]
        inspected = client.post(
            "/tools/inspect_campaign",
            json={"arguments": {"campaign_id": "campaign-tools"}},
        )
        assert inspected.json()["campaign"]["campaign_id"] == "campaign-tools"
        assert (
            client.post(
                "/tools/inspect_campaign",
                json={"arguments": {"campaign_id": "campaign-absent"}},
            ).status_code
            == 404
        )


@pytest.mark.integration
def test_resuming_a_failed_run_with_a_repaired_workflow_is_a_conflict(tmp_path: Path) -> None:
    """The whole operator loop over HTTP: a run fails, is repaired, and is refused a resume.

    `POST /runs` with a caller-supplied `run_id` naming an existing run is a resume, and the run
    here ends `failed` — non-terminal, so the lifecycle check that closed the terminal case does
    not fire and the workflow of record is the only thing standing between the repaired workflow
    and the original run's record. `supersedes` is the path out.
    """
    lab = _copy_example(tmp_path)
    repaired = yaml.safe_load((lab / "workflow.yaml").read_text(encoding="utf-8"))
    broken = _edit(
        lab / "workflow.yaml",
        lambda document: document["steps"][0].update(resources=["instrument-nobody-registered"]),
    )

    with TestClient(create_app(OpenSDLSystem.from_manifest(lab / "opensdl.yaml"))) as client:
        first = client.post(
            "/runs",
            json={"workflow": broken, "inputs": VALID_INPUTS, "run_id": "run-of-record"},
        )
        assert first.status_code == 409, first.text
        assert client.get("/runs/run-of-record").json()["run"]["state"] == "failed"
        conflict = client.post(
            "/runs",
            json={"workflow": repaired, "inputs": VALID_INPUTS, "run_id": "run-of-record"},
        )
        resumed = client.post(
            "/runs",
            json={"workflow": broken, "inputs": VALID_INPUTS, "run_id": "run-of-record"},
        )
        replacement = client.post(
            "/runs",
            json={"workflow": repaired, "inputs": VALID_INPUTS, "supersedes": "run-of-record"},
        )
        events = client.get("/events", params={"run_id": "run-of-record"}).json()

    assert conflict.status_code == 409, conflict.text
    # The workflow the run recorded still resumes, and still fails for its own reason.
    assert resumed.status_code == 409, resumed.text
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["run"]["id"] != "run-of-record"
    assert replacement.json()["run"]["outputs"]["score"] == 0
    superseded = [event for event in events if event["type"] == "RunSuperseded"]
    assert [event["payload"]["runId"] for event in superseded] == [replacement.json()["run"]["id"]]
