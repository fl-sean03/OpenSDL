from __future__ import annotations

import os
from contextlib import asynccontextmanager
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from opensdl_controller import (
    OpenSDLSystem,
    TwinCue,
    TwinDefinition,
    TwinLoadError,
    TwinProjectionError,
    TwinSceneNotFoundError,
)
from opensdl_core import RunId, WorkflowDefinition


class RunRequest(BaseModel):
    workflow: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"
    run_id: RunId | None = None


class CapabilityRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"


class TwinProjectionResponse(BaseModel):
    definition_revision: str
    run_id: RunId
    cues: list[TwinCue]


class GLBResponse(Response):
    media_type = "model/gltf-binary"


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

    def configured_twin():
        twin = current().twin
        if twin is None:
            raise HTTPException(status_code=404, detail="digital twin is not configured")
        return twin

    def viewer_asset(asset_path: str) -> FileResponse:
        configured_twin()
        root = current().twin_viewer_root
        if root is None:
            raise HTTPException(status_code=404, detail="twin viewer is not configured")
        root = root.resolve()
        requested = (root / (asset_path or "index.html")).resolve()
        try:
            requested.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="viewer asset not found") from exc
        if not requested.is_file():
            raise HTTPException(status_code=404, detail="viewer asset not found")
        return FileResponse(requested)

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
            run = await current().run_workflow_definition(
                workflow,
                request.inputs,
                operator_id=request.operator_id,
                run_id=request.run_id,
            )
            return current().gateway.inspect_run(run.id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runs/{run_id}")
    def inspect_run(run_id: RunId) -> dict[str, Any]:
        try:
            return current().gateway.inspect_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/events")
    def events(run_id: RunId | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in current().repositories.list_events(run_id=run_id, limit=limit)
        ]

    @app.get(
        "/twin",
        response_model=TwinDefinition,
        response_model_by_alias=True,
        response_model_exclude_none=True,
    )
    def twin() -> dict[str, Any]:
        return configured_twin().definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )

    @app.get("/twin/scene.glb", response_class=GLBResponse)
    def twin_scene() -> GLBResponse:
        try:
            scene = configured_twin().read_scene()
        except TwinSceneNotFoundError as exc:
            raise HTTPException(status_code=404, detail="twin scene not found") from exc
        except TwinLoadError as exc:
            raise HTTPException(
                status_code=409,
                detail="twin scene verification failed",
            ) from exc
        return GLBResponse(
            content=scene.content,
            media_type="model/gltf-binary",
            headers={
                "ETag": f'"{scene.sha256}"',
                "X-Content-SHA256": scene.sha256,
            },
        )

    @app.get(
        "/twin/runs/{run_id}",
        response_model=TwinProjectionResponse,
        response_model_by_alias=True,
    )
    def twin_run(run_id: RunId) -> dict[str, Any]:
        configured_twin()
        try:
            return current().project_twin_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except TwinProjectionError as exc:
            raise HTTPException(status_code=422, detail="twin run projection failed") from exc

    @app.get("/viewer")
    def viewer() -> FileResponse:
        return viewer_asset("index.html")

    @app.get("/viewer/{asset_path:path}")
    def viewer_path(asset_path: str) -> FileResponse:
        return viewer_asset(asset_path)

    return app
