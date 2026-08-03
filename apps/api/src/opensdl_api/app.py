from __future__ import annotations

import os
from contextlib import asynccontextmanager
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from opensdl_controller import OpenSDLSystem
from opensdl_core import WorkflowDefinition


class RunRequest(BaseModel):
    workflow: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"


class CapabilityRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"


def create_app(
    system: OpenSDLSystem | None = None,
    *,
    manifest_path: str | Path | None = None,
) -> FastAPI:
    owned = system is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        selected = system or OpenSDLSystem.from_manifest(
            manifest_path or os.getenv("OPENSDL_MANIFEST", "opensdl.yaml")
        )
        app.state.opensdl = selected
        await selected.start()
        try:
            yield
        finally:
            if owned:
                await selected.close()

    app = FastAPI(
        title="OpenSDL API",
        version=distribution_version("opensdl-api"),
        description="Typed access to laboratory context, capabilities, resources, runs, and events.",
        lifespan=lifespan,
    )

    def current() -> OpenSDLSystem:
        return app.state.opensdl

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return await current().doctor()

    @app.get("/context")
    def context() -> dict[str, Any]:
        return current().context_builder.build().model_dump(mode="json")

    @app.get("/tools")
    def tools() -> list[dict[str, Any]]:
        return [tool.model_dump(mode="json") for tool in current().gateway.tool_specs()]

    @app.get("/capabilities")
    def capabilities() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().registry.list_capabilities()]

    @app.post("/capabilities/{capability_id}/execute")
    async def execute_capability(capability_id: str, request: CapabilityRequest) -> dict[str, Any]:
        try:
            return await current().gateway.execute_capability(
                capability_id,
                request.inputs,
                operator_id=request.operator_id,
                environment=current().manifest.spec.environment,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/resources")
    def resources() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().repositories.list_resources()]

    @app.get("/runs")
    def runs() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().repositories.list_runs()]

    @app.post("/runs")
    async def submit_run(request: RunRequest) -> dict[str, Any]:
        try:
            workflow = WorkflowDefinition.model_validate(request.workflow)
            run = await current().runtime.run_workflow(
                workflow,
                request.inputs,
                operator_id=request.operator_id,
                environment=current().manifest.spec.environment,
            )
            return current().gateway.inspect_run(run.id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runs/{run_id}")
    def inspect_run(run_id: str) -> dict[str, Any]:
        try:
            return current().gateway.inspect_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/events")
    def events(run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().repositories.list_events(run_id=run_id, limit=limit)]

    return app
