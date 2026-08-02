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

    def inspect_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def submit_workflow(self, workflow: dict[str, Any], inputs: dict[str, Any] | None = None, *, operator_id: str = "operator/sdk") -> dict[str, Any]:
        return self._request("POST", "/runs", json={"workflow":workflow,"inputs":inputs or {},"operator_id":operator_id})

    def execute_capability(self, capability_id: str, inputs: dict[str, Any], *, operator_id: str = "operator/sdk") -> dict[str, Any]:
        return self._request("POST", f"/capabilities/{capability_id}/execute", json={"inputs":inputs,"operator_id":operator_id})

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def __enter__(self) -> "OpenSDLClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
