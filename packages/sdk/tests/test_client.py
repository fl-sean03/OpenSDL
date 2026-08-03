from unittest.mock import Mock

import pytest

import opensdl
from opensdl import OpenSDLClient


def test_client_constructs() -> None:
    client = OpenSDLClient("http://localhost:9999")
    client.close()


def test_sdk_exports_core_contracts() -> None:
    assert "RunRecord" in opensdl.__all__
    assert opensdl.RunRecord is not None


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
