"""Tests for the public Python SDK.

Most of these mock `_request` and therefore verify only that the client builds the request it was
asked to build. That leaves the question the SDK actually exists to answer — does the client reach
the API this repository ships — untested, so renaming a route passed every test.
`test_client_reaches_every_route_the_api_serves` closes that by driving the real FastAPI
application over an ASGI transport.

The `opensdl_api` import is a test-only, workspace-only dependency. The shipped `opensdl`
distribution depends on `opensdl-core`, `opensdl-schemas`, and `httpx` alone (see
`packages/sdk/pyproject.toml`), and `[tool.setuptools.packages.find] where = ["src"]` keeps this
directory out of the wheel, so the client-to-server boundary declared in
`scripts/check-boundaries.py` is unchanged.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
import pytest

import opensdl
from opensdl import OpenSDLClient

EXAMPLE = Path(__file__).parents[3] / "examples" / "simulated-color-mixing"


def test_client_normalizes_a_base_url_with_a_trailing_slash() -> None:
    with OpenSDLClient("http://localhost:9999/") as client:
        assert str(client._client.base_url) == "http://localhost:9999"


def test_sdk_reexports_the_core_contracts_it_advertises() -> None:
    # A stale `__all__` would advertise a name the package cannot deliver.
    missing = [name for name in opensdl.__all__ if not hasattr(opensdl, name)]
    assert missing == []

    import opensdl_core

    assert "RunRecord" in opensdl.__all__
    assert opensdl.RunRecord is opensdl_core.RunRecord


class _ServedApplication(httpx.BaseTransport):
    """Carry the SDK's requests into an in-process ASGI application.

    `TestClient` drives an ASGI app from synchronous code, which is what this client needs, but
    Starlette binds `TestClient` to `httpx2` whenever that package is importable and to `httpx`
    otherwise. Installing the optional `mcp` extra pulls `httpx2` in, so handing `TestClient`
    straight to the SDK made an unrelated extra decide which library's `Response` — and which
    library's `HTTPStatusError` — the SDK returned and raised.

    Bridging at the transport confines that choice to this class. Above it the SDK is an `httpx`
    client and stays one, no matter what else the environment has installed.
    """

    def __init__(self, served: Any) -> None:
        self._served = served

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._served.request(
            request.method,
            str(request.url),
            content=request.read(),
            headers=list(request.headers.items()),
        )
        # The inner client already decoded and framed the body, so its `content-encoding` and
        # `content-length` describe a payload that no longer exists. Forwarding them would have
        # `httpx` decode an already-decoded body or read past its end.
        headers = [
            (name, value)
            for name, value in response.headers.items()
            if name.lower() not in {"content-encoding", "content-length"}
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=response.content,
            request=request,
        )


@pytest.fixture
def live_client(tmp_path: Path) -> Iterator[OpenSDLClient]:
    """An `OpenSDLClient` whose transport is the FastAPI application this repository ships.

    Every line of `OpenSDLClient` — the paths, the query parameters, the JSON bodies, and
    `raise_for_status` — stays on the executed path; only the wire is replaced.
    """
    from fastapi.testclient import TestClient
    from opensdl_api import create_app

    lab = tmp_path / "lab"
    shutil.copytree(EXAMPLE, lab, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    app = create_app(manifest_path=lab / "opensdl.yaml")

    # Entering the context manager runs the application lifespan, which builds the laboratory.
    with TestClient(app, base_url="http://opensdl.test") as served:
        with OpenSDLClient("http://opensdl.test", transport=_ServedApplication(served)) as client:
            yield client


@pytest.mark.integration
def test_client_reaches_every_route_the_api_serves(live_client: OpenSDLClient) -> None:
    """Each accessor must resolve to a real route; a renamed route becomes a 404 here."""
    assert live_client.health()["passed"]

    context = live_client.context()
    assert context["environment"] == "simulation"
    assert context["policy_version"]

    capabilities = live_client.capabilities()
    assert capabilities and all("id" in capability for capability in capabilities)

    assert live_client.runs() == []
    assert live_client.events(limit=5) == []


@pytest.mark.integration
def test_client_submits_a_workflow_and_reads_the_run_back(live_client: OpenSDLClient) -> None:
    import yaml

    workflow: dict[str, Any] = yaml.safe_load(
        (EXAMPLE / "workflow.yaml").read_text(encoding="utf-8")
    )
    submitted = live_client.submit_workflow(
        workflow,
        {
            "sample_id": "sdk",
            "red_fraction": 0.5,
            "blue_fraction": 0.5,
            "total_mass_g": 5,
            "target_rgb": [127.5, 0, 127.5],
        },
        operator_id="operator/sdk-test",
        run_id="run-sdk-transport",
    )

    run_id = submitted["run"]["id"]
    assert run_id == "run-sdk-transport"

    inspected = live_client.inspect_run(run_id)
    assert inspected["run"]["id"] == run_id
    assert [record["id"] for record in live_client.runs()] == [run_id]

    events = live_client.events(run_id)
    assert events and all(event["run_id"] == run_id for event in events)


@pytest.mark.integration
def test_client_raises_for_a_route_the_api_does_not_serve(live_client: OpenSDLClient) -> None:
    """The twin routes 404 on a laboratory with no configured twin, and the client surfaces it.

    This is the failure the stubbed tests could never see: `_request` calls
    `response.raise_for_status()`, so a missing or renamed route reaches the caller as an error
    instead of a silently empty result.
    """
    with pytest.raises(httpx.HTTPStatusError) as error:
        live_client.twin()
    assert error.value.response.status_code == 404

    with pytest.raises(httpx.HTTPStatusError):
        live_client.twin_scene()


def test_client_exposes_event_and_twin_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OpenSDLClient("http://localhost:9999")
    request = Mock(return_value={})
    request_bytes = Mock(return_value=b"glb")
    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(client, "_request_bytes", request_bytes)
    try:
        client.events("run-1", limit=25)
        request.assert_called_once_with(
            "GET",
            "/events",
            params={"limit": 25, "run_id": "run-1"},
        )
        request.reset_mock()

        client.twin()
        request.assert_called_once_with("GET", "/twin")
        request.reset_mock()

        assert client.twin_scene() == b"glb"
        request_bytes.assert_called_once_with("GET", "/twin/scene.glb")

        client.twin_run("run-1")
        request.assert_called_once_with("GET", "/twin/runs/run-1")
    finally:
        client.close()


def test_submit_workflow_includes_caller_supplied_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OpenSDLClient("http://localhost:9999")
    request = Mock(return_value={})
    monkeypatch.setattr(client, "_request", request)
    try:
        client.submit_workflow(
            {"id": "workflow.test"},
            {"sample": "a"},
            operator_id="operator/test",
            run_id="run-stable",
        )
    finally:
        client.close()

    request.assert_called_once_with(
        "POST",
        "/runs",
        json={
            "workflow": {"id": "workflow.test"},
            "inputs": {"sample": "a"},
            "operator_id": "operator/test",
            "run_id": "run-stable",
        },
    )


@pytest.mark.integration
def test_client_reads_campaigns_the_api_serves(live_client: OpenSDLClient) -> None:
    """A remote client had no way to see a campaign at all; `campaign` was in no SDK method."""
    assert live_client.campaigns() == []

    with pytest.raises(httpx.HTTPStatusError) as error:
        live_client.inspect_campaign("campaign-absent")
    assert error.value.response.status_code == 404

    assert live_client.events(campaign_id="campaign-absent") == []


def test_client_builds_campaign_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    client = OpenSDLClient("http://localhost:9999")
    request = Mock(return_value={})
    monkeypatch.setattr(client, "_request", request)

    client.campaigns()
    client.inspect_campaign("campaign-1")
    client.events(campaign_id="campaign-1", limit=5)

    assert request.call_args_list[0].args == ("GET", "/campaigns")
    assert request.call_args_list[1].args == ("GET", "/campaigns/campaign-1")
    assert request.call_args_list[2].kwargs["params"] == {
        "limit": 5,
        "campaign_id": "campaign-1",
    }
