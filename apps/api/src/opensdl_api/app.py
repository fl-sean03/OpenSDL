from __future__ import annotations

import os
from contextlib import asynccontextmanager
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Iterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from pydantic import ValidationError as RequestValidationError

from opensdl_controller import (
    OpenSDLSystem,
    TwinCue,
    TwinDefinition,
    TwinLoadError,
    TwinProjectionError,
    TwinSceneNotFoundError,
)
from opensdl_core import (
    CapabilityNotFoundError,
    ExecutionDeniedError,
    LifecycleError,
    ResourceBusyError,
    RunId,
    ValidationError,
    WorkflowDefinition,
)

#: The largest event page a single request may ask for. The event log is append-only and unbounded,
#: and the route is unauthenticated, so an unbounded `limit` is a request to serialize the entire
#: operational history of the laboratory into one response.
MAX_EVENT_LIMIT = 1000


class ErrorResponse(BaseModel):
    """The body of every failure this API reports."""

    detail: str


#: How each public failure is reported, most specific first.
#:
#: The text is chosen here and never taken from the exception. Exception strings reached an
#: unauthenticated caller verbatim, so the first operational adapter that raises with a connection
#: string, a file path, or a sample identifier in its message would serve that to anyone who can
#: open a socket. The durable event log keeps the detail; an operator reads it through
#: `GET /events?run_id=`, which is inside the deployment rather than on the wire.
FAILURES: tuple[tuple[type[BaseException], int, str], ...] = (
    (ExecutionDeniedError, 403, "policy denied this execution"),
    (ResourceBusyError, 409, "a required resource is unregistered or already leased"),
    (LifecycleError, 409, "the run's recorded state does not allow this request"),
    (CapabilityNotFoundError, 404, "no such capability"),
    (KeyError, 404, "run not found"),
    (LookupError, 404, "the requested item does not exist"),
    (TimeoutError, 504, "execution exceeded its declared timeout"),
    (RequestValidationError, 422, "the request body is not a valid workflow"),
    (ValidationError, 422, "the request violates a declared schema"),
)

#: Everything the table above does not name, which is chiefly a laboratory that ran and could not
#: finish. That is a real outcome rather than a malformed request, and the run record and its
#: events are where it is described.
GENERIC_FAILURE = (500, "execution failed; inspect the run for the recorded reason")

#: Every status the two executing routes can return, so a generated client knows they exist.
EXECUTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "Policy denied the execution."},
    404: {"model": ErrorResponse, "description": "The capability or run does not exist."},
    409: {"model": ErrorResponse, "description": "A required resource is unavailable."},
    422: {"model": ErrorResponse, "description": "The request violates a declared contract."},
    500: {"model": ErrorResponse, "description": "Execution failed."},
    504: {"model": ErrorResponse, "description": "Execution exceeded its declared timeout."},
}
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "The requested item is not configured."},
}


def _causes(exc: BaseException) -> Iterator[BaseException]:
    """The exception and everything it was explicitly raised from.

    The runtime wraps a timeout and an unknown capability in `WorkflowExecutionError` with
    `raise ... from exc`, so the cause is the only place the specific failure survives.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__


def failure_response(exc: BaseException) -> HTTPException:
    """Report a failure with the status that says what kind of failure it was.

    Details are chosen here rather than taken from the exception, because adapter text can
    carry an endpoint or a credential and this response is unauthenticated. A denial is the
    one exception: which rule fired, under which policy revision, is the operator's own
    configuration, and without it they cannot find the rule that refused them.
    """
    for candidate in _causes(exc):
        for error_type, status, detail in FAILURES:
            if isinstance(candidate, error_type):
                decision = getattr(candidate, "decision", None)
                if decision is not None:
                    rule = getattr(decision, "rule_id", None) or "the default effect"
                    revision = getattr(decision, "policy_version", None) or "unversioned"
                    detail = f"{detail}: {rule} of policy {revision}"
                return HTTPException(status_code=status, detail=detail)
    status, detail = GENERIC_FAILURE
    return HTTPException(status_code=status, detail=detail)


class RunRequest(BaseModel):
    workflow: dict[str, Any]
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"
    run_id: RunId | None = None


class CapabilityRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    operator_id: str = "operator/api"


class ToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


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
        # A server starting up is the case reconciliation exists for: a controller that died
        # mid-run leaves those runs `RUNNING` with their leases held, and nothing else will
        # release them. `start()` stopped doing this implicitly, so it is asked for here — and
        # reported, because an operator restarting after a crash needs to know what moved.
        app.state.reconciled = [
            {"id": run.id, "state": run.state.value, "error": run.error}
            for run in await selected.start(reconcile=not selected.read_only)
        ]
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
        report = await current().doctor()
        report["reconciled_runs"] = list(getattr(app.state, "reconciled", []))
        return report

    @app.get("/context")
    def context() -> dict[str, Any]:
        return current().context_builder.build().model_dump(mode="json")

    @app.get("/tools")
    def tools() -> list[dict[str, Any]]:
        return [tool.model_dump(mode="json") for tool in current().gateway.tool_specs()]

    @app.post("/tools/{tool_name}", responses=EXECUTION_RESPONSES)
    async def call_tool(tool_name: str, request: ToolCallRequest) -> Any:
        """Run one tool from `GET /tools`.

        A catalogue an agent cannot call is a catalogue that misleads it. Every name published by
        `GET /tools` is dispatched here, through the same gateway MCP uses and therefore through
        the same policy, leasing, persistence, and provenance path as every other entry point.
        """
        try:
            return await current().gateway.call_tool(tool_name, request.arguments)
        except HTTPException:
            raise
        except Exception as exc:
            raise failure_response(exc) from exc

    @app.get("/capabilities")
    def capabilities() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().registry.list_capabilities()]

    @app.post("/capabilities/{capability_id}/execute", responses=EXECUTION_RESPONSES)
    async def execute_capability(capability_id: str, request: CapabilityRequest) -> dict[str, Any]:
        try:
            return await current().gateway.execute_capability(
                capability_id,
                request.inputs,
                operator_id=request.operator_id,
                environment=current().manifest.spec.environment,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise failure_response(exc) from exc

    @app.get("/resources")
    def resources() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().repositories.list_resources()]

    @app.get("/runs")
    def runs() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in current().repositories.list_runs()]

    @app.post("/runs", responses=EXECUTION_RESPONSES)
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
        except HTTPException:
            raise
        except Exception as exc:
            raise failure_response(exc) from exc

    @app.get("/runs/{run_id}", responses=NOT_FOUND_RESPONSE)
    def inspect_run(run_id: RunId) -> dict[str, Any]:
        try:
            return current().gateway.inspect_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    @app.get("/events")
    def events(
        run_id: RunId | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_EVENT_LIMIT)] = 200,
    ) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in current().repositories.list_events(run_id=run_id, limit=limit)
        ]

    @app.get(
        "/twin",
        response_model=TwinDefinition,
        response_model_by_alias=True,
        response_model_exclude_none=True,
        responses=NOT_FOUND_RESPONSE,
    )
    def twin() -> dict[str, Any]:
        return configured_twin().definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )

    @app.get(
        "/twin/scene.glb",
        response_class=GLBResponse,
        responses={
            **NOT_FOUND_RESPONSE,
            409: {
                "model": ErrorResponse,
                "description": "The scene on disk no longer matches its declared digest.",
            },
        },
    )
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
        responses={
            **NOT_FOUND_RESPONSE,
            422: {
                "model": ErrorResponse,
                "description": "The persisted run cannot be projected onto the configured twin.",
            },
        },
    )
    def twin_run(run_id: RunId) -> dict[str, Any]:
        configured_twin()
        try:
            return current().project_twin_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        except TwinProjectionError as exc:
            raise HTTPException(status_code=422, detail="twin run projection failed") from exc

    @app.get("/viewer", responses=NOT_FOUND_RESPONSE)
    def viewer() -> FileResponse:
        return viewer_asset("index.html")

    @app.get("/viewer/{asset_path:path}", responses=NOT_FOUND_RESPONSE)
    def viewer_path(asset_path: str) -> FileResponse:
        return viewer_asset(asset_path)

    return app
