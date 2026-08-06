from __future__ import annotations

from typing import Any

import httpx


class OpenSDLClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def context(self) -> dict[str, Any]:
        return self._request("GET", "/context")

    def capabilities(self) -> list[dict[str, Any]]:
        return self._request("GET", "/capabilities")

    def runs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/runs")

    def events(
        self,
        run_id: str | None = None,
        limit: int = 200,
        *,
        campaign_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit}
        if run_id is not None:
            params["run_id"] = run_id
        if campaign_id is not None:
            params["campaign_id"] = campaign_id
        return self._request("GET", "/events", params=params)

    def inspect_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def campaigns(self) -> list[dict[str, Any]]:
        """Every campaign the laboratory has recorded, newest first."""
        return self._request("GET", "/campaigns")

    def inspect_campaign(self, campaign_id: str) -> dict[str, Any]:
        """One campaign, its iterations, and its events.

        Reading is the whole campaign surface here. Starting one is `opensdl campaign start`,
        which runs in the foreground of its own process, because a campaign runs for days and no
        HTTP client should hold a request open for that.
        """
        return self._request("GET", f"/campaigns/{campaign_id}")

    def submit_workflow(
        self,
        workflow: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        *,
        operator_id: str = "operator/sdk",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "workflow": workflow,
            "inputs": inputs or {},
            "operator_id": operator_id,
        }
        if run_id is not None:
            request["run_id"] = run_id
        return self._request("POST", "/runs", json=request)

    def twin(self) -> dict[str, Any]:
        return self._request("GET", "/twin")

    def twin_scene(self) -> bytes:
        return self._request_bytes("GET", "/twin/scene.glb")

    def twin_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/twin/runs/{run_id}")

    def execute_capability(
        self, capability_id: str, inputs: dict[str, Any], *, operator_id: str = "operator/sdk"
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/capabilities/{capability_id}/execute",
            json={"inputs": inputs, "operator_id": operator_id},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _request_bytes(self, method: str, path: str, **kwargs: Any) -> bytes:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.content

    def __enter__(self) -> "OpenSDLClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
