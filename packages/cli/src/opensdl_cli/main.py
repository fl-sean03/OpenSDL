from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperGroup

from opensdl_controller import OpenSDLSystem
from opensdl_controller import migrate as migrate_laboratory
from opensdl_operators import CampaignLauncher
from opensdl_provenance import PropagationGraph
from opensdl_schemas import validate_manifest_file, validate_workflow_file
from opensdl_twin import TwinProjectionError, load_twin_definition

from .scaffold import create_adapter, create_capability, create_domain_pack, create_laboratory
from .schemas import generate_all_json_schemas

#: Exit codes. A supervising script has to be able to tell a refusal from a crash without parsing
#: prose, and an operator has to be able to tell whether to fix the manifest, wait for equipment,
#: or file a bug. `2` is Click's own code for a usage error and is left alone.
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_NOT_FOUND = 4
EXIT_DENIED = 5
EXIT_BUSY = 6
EXIT_TIMEOUT = 7
EXIT_CONFLICT = 8
EXIT_FAILED = 9

#: Public failure classes mapped to an exit code and the word that leads the reported line.
#:
#: `scripts/check-boundaries.py` deliberately keeps `opensdl_cli` off most of the workspace, so the
#: boundary classifies by class name walked over the exception's method resolution order rather
#: than by `isinstance`. `test_cli_errors.py` pins every name here against the classes
#: `opensdl_core` actually exports, so a renamed class fails a test instead of silently falling
#: through to `EXIT_INTERNAL`.
#:
#: A key may be a bare class name or a fully qualified `module.Class`, and the qualified form wins.
#: OpenSDL's own class names are distinctive enough to match bare; a third party's are not, and a
#: wrong match here is not harmless — it reports a defect in OpenSDL as an ordinary refusal and
#: takes away the "re-run with --traceback" line that goes with `EXIT_INTERNAL`.
EXIT_BY_FAILURE: dict[str, tuple[int, str]] = {
    # The public OpenSDL taxonomy.
    "CapabilityNotFoundError": (EXIT_NOT_FOUND, "Not found"),
    "ExecutionDeniedError": (EXIT_DENIED, "Denied by policy"),
    "LifecycleError": (EXIT_CONFLICT, "Refused"),
    "OpenSDLError": (EXIT_FAILED, "Failed"),
    "ResourceBusyError": (EXIT_BUSY, "Unavailable"),
    "ValidationError": (EXIT_INVALID, "Invalid"),
    "WorkflowExecutionError": (EXIT_FAILED, "Failed"),
    # Digital twin loading and projection.
    "TwinLoadError": (EXIT_INVALID, "Invalid"),
    "TwinProjectionError": (EXIT_INVALID, "Invalid"),
    "TwinSceneNotFoundError": (EXIT_NOT_FOUND, "Not found"),
    # Library failures the ordinary mistakes provoke.
    "FileNotFoundError": (EXIT_NOT_FOUND, "Not found"),
    "IsADirectoryError": (EXIT_INVALID, "Invalid"),
    "JSONDecodeError": (EXIT_INVALID, "Invalid"),
    "KeyError": (EXIT_NOT_FOUND, "Not found"),
    "LookupError": (EXIT_NOT_FOUND, "Not found"),
    "NotADirectoryError": (EXIT_NOT_FOUND, "Not found"),
    "PermissionError": (EXIT_INVALID, "Invalid"),
    "TimeoutError": (EXIT_TIMEOUT, "Timed out"),
    "ValueError": (EXIT_INVALID, "Invalid"),
    "YAMLError": (EXIT_INVALID, "Invalid"),
    # Alembic's one failure class, behind `opensdl migrate`. A store at an unknown revision, a
    # branched history, or a target that cannot be resolved is a real refusal about a real store,
    # not a defect. Qualified because `CommandError` is a name several libraries use.
    "alembic.util.exc.CommandError": (EXIT_FAILED, "Failed"),
}

TRACEBACK_ENV_VAR = "OPENSDL_TRACEBACK"


def _lookup(exc: BaseException) -> tuple[int, str] | None:
    for base in type(exc).__mro__:
        known = EXIT_BY_FAILURE.get(f"{base.__module__}.{base.__name__}") or EXIT_BY_FAILURE.get(
            base.__name__
        )
        if known is not None:
            return known
    return None


def _classify(exc: BaseException) -> tuple[int, str]:
    """Classify a failure by its own class, then by the cause it was raised from.

    The runtime wraps a timeout and an unknown capability in `WorkflowExecutionError` with
    `raise ... from exc`, so the cause is the only place the specific failure survives. A direct
    classification that is already specific wins; the generic `EXIT_FAILED` defers to the cause.
    """
    direct = _lookup(exc)
    if direct is not None and direct[0] != EXIT_FAILED:
        return direct
    cause = exc.__cause__
    while cause is not None:
        found = _lookup(cause)
        if found is not None and found[0] != EXIT_FAILED:
            return found
        cause = cause.__cause__
    return direct or (EXIT_INTERNAL, "Internal error")


def _one_line(exc: BaseException) -> str:
    """Render a failure as exactly one line, without discarding what it says.

    The runtime writes several deliberately long refusals — an ambiguous resume, an adapter result
    that violates its contract — whose whole value is the reasoning they carry. They are collapsed
    onto one line, never truncated.
    """
    if isinstance(exc, KeyError) and exc.args:
        message = str(exc.args[0])
    elif isinstance(exc, OSError) and exc.strerror:
        message = f"{exc.strerror}: {exc.filename}" if exc.filename else exc.strerror
    else:
        message = str(exc)
    collapsed = " ".join(message.split())
    return collapsed or type(exc).__name__


def _traceback_requested(ctx: Any) -> bool:
    configured = os.getenv(TRACEBACK_ENV_VAR, "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    return bool(isinstance(ctx.obj, dict) and ctx.obj.get("traceback"))


def _raised_by_the_command_line_framework(exc: BaseException) -> bool:
    """Whether Typer or Click raised this to control the command line rather than report a failure.

    Requested exits, aborts, and usage errors are the framework's own control flow: it already
    prints them well and already chooses their exit code. Matching on the defining module rather
    than on a class keeps this correct across Typer's vendored Click shim, where `typer.Exit` is
    not a `click.exceptions.Exit`.
    """
    return type(exc).__module__.split(".")[0] in {"click", "typer"}


class ErrorBoundaryGroup(TyperGroup):
    """Turn every known failure into one actionable line instead of a framework traceback.

    Everything that escapes a command other than the framework's own control flow is a laboratory
    failure, and an operator reading a wrapped traceback through `asyncio`, SQLAlchemy and Pydantic
    internals — with our absolute virtualenv paths in it — learns nothing from it. The traceback
    stays one flag away.
    """

    def invoke(self, ctx: Any) -> Any:
        try:
            return super().invoke(ctx)
        except Exception as exc:
            if _raised_by_the_command_line_framework(exc) or _traceback_requested(ctx):
                raise
            code, label = _classify(exc)
            detail = _one_line(exc)
            if code == EXIT_INTERNAL:
                detail = (
                    f"{type(exc).__name__}: {detail} "
                    f"(re-run with --traceback, or set {TRACEBACK_ENV_VAR}=1, for the traceback)"
                )
            typer.echo(f"{label}: {detail}", err=True)
            raise typer.Exit(code) from None


app = typer.Typer(
    cls=ErrorBoundaryGroup,
    no_args_is_help=True,
    help="Build, validate, run, and extend OpenSDL laboratories.",
)
adapter_app = typer.Typer(no_args_is_help=True, help="Create and inspect adapters.")
campaign_app = typer.Typer(no_args_is_help=True, help="Run and inspect closed-loop campaigns.")
capability_app = typer.Typer(no_args_is_help=True, help="Create and inspect capabilities.")
schema_app = typer.Typer(no_args_is_help=True, help="Generate public schemas.")
domain_app = typer.Typer(no_args_is_help=True, help="Create scientific domain packs.")
twin_app = typer.Typer(no_args_is_help=True, help="Validate and project digital twins.")
app.add_typer(adapter_app, name="adapter")
app.add_typer(campaign_app, name="campaign")
app.add_typer(capability_app, name="capability")
app.add_typer(domain_app, name="domain-pack")
app.add_typer(schema_app, name="schema")
app.add_typer(twin_app, name="twin")
console = Console()


@app.callback()
def configure(
    ctx: typer.Context,
    traceback: Annotated[
        bool,
        typer.Option(
            "--traceback",
            help=f"Show the full traceback instead of one line. Same as {TRACEBACK_ENV_VAR}=1.",
        ),
    ] = False,
) -> None:
    ctx.obj = {"traceback": traceback}


def _json_input(value: str) -> dict[str, Any]:
    if value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise typer.BadParameter("inputs must be a JSON object")
    return parsed


@contextmanager
def _composed(
    manifest: Path,
    *,
    read_only: bool = True,
    require_store: bool = True,
) -> Iterator[OpenSDLSystem]:
    """Compose one laboratory for a command that only reads, and dispose of it afterwards.

    `from_manifest` used to initialize the configured database and write every capability and
    resource into it on any path, so `opensdl inspect` against a laboratory that had never run
    created its store (audit F6). A read-only system creates nothing, seeds nothing, reconciles
    nothing, and refuses to execute. `require_store=False` additionally answers for a laboratory
    that has never run, which is the case `validate` and `capability list` are for.
    """
    system = OpenSDLSystem.from_manifest(
        manifest,
        read_only=read_only,
        require_store=require_store,
    )
    try:
        yield system
    finally:
        system.database.dispose()


def _assert_capabilities_exposed(workflow: Path, system: OpenSDLSystem) -> None:
    """Refuse a workflow step that names a capability this laboratory does not expose.

    Reaching dispatch first costs an operator a created run, a `RunFailed` event and an error that
    is nothing but the misspelled identifier. The manifest already says exactly which capabilities
    exist, so the answer — and the list to choose from — is available before anything is recorded.
    """
    available = sorted(definition.id for definition in system.registry.list_capabilities())
    definition = validate_workflow_file(workflow)
    unknown = sorted({step.capability for step in definition.steps} - set(available))
    if unknown:
        raise LookupError(
            f"workflow {definition.id} names {', '.join(unknown)}, which this laboratory does not "
            f"expose; available: {', '.join(available) or 'none'}"
        )


@app.command()
def version() -> None:
    """Print the workspace version."""
    console.print(distribution_version("opensdl-cli"))


@app.command()
def init(
    destination: Annotated[Path, typer.Argument(help="New organization laboratory repository")],
    name: Annotated[str | None, typer.Option()] = None,
    owner: Annotated[str, typer.Option()] = "your-organization",
) -> None:
    """Create a working organization-specific laboratory repository."""
    root = create_laboratory(destination, name=name, owner=owner)
    console.print(f"Created laboratory repository at [bold]{root}[/bold]")


@app.command()
def validate(
    manifest: Annotated[Path, typer.Argument()] = Path("opensdl.yaml"),
    workflow: Annotated[list[Path] | None, typer.Option("--workflow", "-w")] = None,
) -> None:
    """Validate a laboratory manifest and optional workflows.

    Validation resolves what it certifies: the manifest's adapter plugins are loaded, its
    capability bindings and domain packs are resolved, and every workflow step is checked against
    the capabilities the laboratory actually exposes. Nothing is started and the configured store
    is not touched.
    """
    loaded = validate_manifest_file(manifest)
    with _composed(manifest, require_store=False) as system:
        console.print(f"Manifest valid: [bold]{loaded.metadata.name}[/bold]")
        for path in workflow or []:
            _assert_capabilities_exposed(path, system)
            console.print(f"Workflow valid: {validate_workflow_file(path).id}")


@app.command()
def doctor(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    reconcile: Annotated[
        bool,
        typer.Option(
            "--reconcile",
            help="Also move runs left RUNNING by a stopped controller to INTERVENTION_REQUIRED "
            "and release their leases. Never do this during a live run.",
        ),
    ] = False,
) -> None:
    """Check database, artifact store, and adapter health. Writes nothing unless --reconcile.

    Reconciliation used to happen on every invocation, silently, because starting the system did
    it: a `doctor` run during a live campaign moved every active run to `INTERVENTION_REQUIRED`
    and exited zero reporting healthy. It is now asked for, and what it moved is reported.
    """
    result = asyncio.run(_doctor(manifest, reconcile=reconcile))
    console.print_json(data=result)
    if not result["passed"]:
        raise typer.Exit(EXIT_FAILED)


async def _doctor(manifest: Path, *, reconcile: bool) -> dict[str, Any]:
    system = (
        OpenSDLSystem.from_manifest(manifest)
        if reconcile
        else OpenSDLSystem.from_manifest(manifest, read_only=True, require_store=False)
    )
    try:
        reconciled = await system.start(reconcile=reconcile)
        report = await system.doctor()
        report["reconciled_runs"] = [{"id": run.id, "state": run.state.value} for run in reconciled]
        return report
    finally:
        await system.close()


@app.command()
def migrate(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Report pending revisions and write nothing. Exits non-zero when the store is "
            "behind the current schema.",
        ),
    ] = False,
) -> None:
    """Bring this laboratory's store to the current schema, or report what that would take.

    Migrating does not compose the laboratory. No adapter or domain pack is imported, so a plugin
    that fails to load never stands between a laboratory and its schema. `--check` writes nothing
    and, against a laboratory that has never run, does not bring a store into existence.

    A store created before Alembic owned the schema is adopted rather than rejected: it is stamped
    at the revision its contents correspond to and upgraded from there.
    """
    report = migrate_laboratory.plan(manifest) if check else migrate_laboratory.upgrade(manifest)
    console.print_json(data=report)
    if check and report["pending"]:
        raise typer.Exit(EXIT_FAILED)


@app.command("run")
def run_workflow(
    workflow: Annotated[Path, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    inputs: Annotated[str, typer.Option(help="JSON object or @path/to/file.json")] = "{}",
    operator_id: Annotated[str, typer.Option()] = "operator/cli",
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Execute a workflow through the durable reference runtime."""
    result = asyncio.run(
        _run(
            manifest,
            workflow,
            _json_input(inputs),
            operator_id,
            run_id=run_id,
        )
    )
    console.print_json(data=result)


async def _run(
    manifest: Path,
    workflow: Path,
    inputs: dict[str, Any],
    operator_id: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        _assert_capabilities_exposed(workflow, system)
        # A controller that died mid-run left those runs RUNNING with their leases held, and this
        # is the next process able to release them. `start()` no longer does it implicitly.
        await system.start(reconcile=True)
        run = await system.run_workflow_file(
            workflow,
            inputs,
            operator_id=operator_id,
            run_id=run_id,
        )
        return system.gateway.inspect_run(run.id)
    finally:
        await system.close()


@app.command()
def inspect(
    run_id: Annotated[str, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Inspect one persisted run, its tasks, and events."""
    with _composed(manifest) as system:
        try:
            console.print_json(data=system.gateway.inspect_run(run_id))
        except KeyError:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(EXIT_NOT_FOUND) from None


@app.command()
def events(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    run_id: Annotated[str | None, typer.Option()] = None,
    campaign_id: Annotated[
        str | None,
        typer.Option("--campaign-id", help="Restrict to one campaign, including its runs."),
    ] = None,
    limit: Annotated[int, typer.Option()] = 200,
) -> None:
    """Query execution events."""
    with _composed(manifest) as system:
        console.print_json(
            data=system.gateway.query_events(
                run_id=run_id,
                campaign_id=campaign_id,
                limit=limit,
            )
        )


@app.command()
def export(
    run_id: Annotated[str, typer.Argument()],
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("exports"),
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Export a run as a portable RO-Crate-style ZIP bundle."""
    with _composed(manifest) as system:
        try:
            path = system.exporter.export(run_id, destination)
        except KeyError:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(EXIT_NOT_FOUND) from None
        console.print(str(path))


@app.command()
def propagate(
    paths: Annotated[list[str], typer.Argument(help="Changed repository paths")],
    graph: Annotated[Path, typer.Option("--graph", "-g")] = Path("propagation.yaml"),
    allow_missing: Annotated[bool, typer.Option("--allow-missing")] = False,
) -> None:
    """Find contracts, code, tests, examples, and docs affected by a change."""
    # An empty result and a path that does not exist are otherwise indistinguishable,
    # so a typo reports "nothing is affected" and exits zero.  A deleted path is a
    # legitimate question to ask, which is what --allow-missing is for.
    if not allow_missing:
        missing = sorted(path for path in paths if not Path(path).exists())
        if missing:
            console.print(
                f"[red]no such path: {', '.join(missing)}[/red]\n"
                "pass --allow-missing to report the blast radius of a deleted path"
            )
            raise typer.Exit(code=EXIT_USAGE)
    impact = PropagationGraph.from_file(graph).affected(paths)
    console.print_json(data=impact.model_dump(mode="json"))


@app.command("serve-api")
def serve_api(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """Serve the HTTP API for a configured laboratory."""
    import uvicorn
    from opensdl_api import create_app

    uvicorn.run(create_app(manifest_path=manifest), host=host, port=port)


@app.command("serve-mcp")
def serve_mcp(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Serve the MCP tool surface for a configured laboratory over stdio.

    The transport dispatches through the same operator gateway the HTTP API uses, so policy,
    leasing and provenance apply identically. It executes capabilities: a client that reaches
    this process reaches the laboratory, and nothing here authenticates it.
    """
    from opensdl_operators import build_mcp_server

    system = OpenSDLSystem.from_manifest(manifest)
    try:
        # A server starting up is where reconciliation belongs, for the same reason the HTTP API
        # asks for it: a controller that died mid-run left those runs holding their leases.
        asyncio.run(system.start(reconcile=True))
        build_mcp_server(system.gateway).run()
    finally:
        asyncio.run(system.close())


@campaign_app.command("start")
def start_campaign(
    workflow: Annotated[Path, typer.Argument(help="Workflow each iteration executes")],
    optimizer: Annotated[
        str,
        typer.Option("--optimizer", help="Optimizer plugin that proposes candidates."),
    ],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    optimizer_config: Annotated[
        str,
        typer.Option(help="JSON object or @path/to/file.json passed to the optimizer plugin"),
    ] = "{}",
    base_inputs: Annotated[
        str,
        typer.Option(help="JSON object or @path/to/file.json merged under every candidate"),
    ] = "{}",
    score_output: Annotated[str, typer.Option()] = "score",
    max_iterations: Annotated[int, typer.Option()] = 10,
    minimize: Annotated[
        bool,
        typer.Option("--minimize/--maximize", help="Direction of the objective."),
    ] = True,
    target_score: Annotated[
        float | None, typer.Option(help="Stop once an iteration reaches this score.")
    ] = None,
    max_consecutive_failures: Annotated[int, typer.Option()] = 3,
    max_duration_seconds: Annotated[
        float | None, typer.Option(help="Wall-clock budget, checked before each iteration.")
    ] = None,
    iteration_id_input: Annotated[
        str | None,
        typer.Option(help="Workflow input that receives a unique per-iteration identifier."),
    ] = None,
    batch_size: Annotated[
        int,
        typer.Option(
            "--batch-size",
            min=1,
            help="How many candidates the optimizer proposes at once. Requires an optimizer "
            "that implements suggest_batch.",
        ),
    ] = 1,
    max_parallel_runs: Annotated[
        int,
        typer.Option(
            "--max-parallel-runs",
            min=1,
            help="How many candidates execute at once. A property of the laboratory, not of "
            "the method: raising it starts instruments concurrently.",
        ),
    ] = 1,
    operator_id: Annotated[str, typer.Option()] = "software/campaign",
    campaign_id: Annotated[str | None, typer.Option("--campaign-id")] = None,
) -> None:
    """Run a closed-loop campaign in the foreground until a stopping rule fires.

    The campaign runs in this process: it stops when a stopping rule fires or when this process
    stops, and there is no detached submission and no remote stop. That is deliberate rather than
    unfinished — `POST /runs` already awaits an entire workflow inside an HTTP handler, and doing
    the same for something that runs for days would be worse. Reading a campaign back does not
    need this process and is available from `campaign list`, `campaign inspect`, the HTTP API,
    the SDK, and the agent tool surface.

    The environment is the one the manifest declares and is deliberately not an option here:
    policy is evaluated against it and every run records it, so a campaign that could state its
    own would write a provenance record its laboratory never authorized.
    """
    record = asyncio.run(
        _run_campaign(
            manifest,
            workflow,
            optimizer=optimizer,
            optimizer_config=_json_input(optimizer_config),
            base_inputs=_json_input(base_inputs),
            score_output=score_output,
            max_iterations=max_iterations,
            batch_size=batch_size,
            max_parallel_runs=max_parallel_runs,
            minimize=minimize,
            target_score=target_score,
            max_consecutive_failures=max_consecutive_failures,
            max_duration_seconds=max_duration_seconds,
            iteration_id_input=iteration_id_input,
            operator_id=operator_id,
            campaign_id=campaign_id,
        )
    )
    console.print_json(data=record)


async def _run_campaign(
    manifest: Path,
    workflow: Path,
    *,
    optimizer: str,
    optimizer_config: dict[str, Any],
    base_inputs: dict[str, Any],
    score_output: str,
    max_iterations: int,
    minimize: bool,
    target_score: float | None,
    max_consecutive_failures: int,
    max_duration_seconds: float | None,
    iteration_id_input: str | None,
    batch_size: int,
    max_parallel_runs: int,
    operator_id: str,
    campaign_id: str | None,
) -> dict[str, Any]:
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        _assert_capabilities_exposed(workflow, system)
        launcher = CampaignLauncher(system.runtime, system.repositories)
        # Resolve the optimizer before anything is recorded. A misspelled plugin name is otherwise
        # discovered after `CampaignStarted`, leaving a campaign in the log that never ran.
        launcher.load_optimizer(optimizer, optimizer_config)
        await system.start(reconcile=True)
        record = await launcher.run(
            validate_workflow_file(workflow),
            environment=system.manifest.spec.environment,
            operator_id=operator_id,
            optimizer=optimizer,
            optimizer_config=optimizer_config,
            base_inputs=base_inputs,
            score_output=score_output,
            max_iterations=max_iterations,
            minimize=minimize,
            target_score=target_score,
            max_consecutive_failures=max_consecutive_failures,
            max_duration_seconds=max_duration_seconds,
            iteration_id_input=iteration_id_input,
            batch_size=batch_size,
            max_parallel_runs=max_parallel_runs,
            campaign_id=campaign_id,
        )
        return record.model_dump(mode="json")
    finally:
        await system.close()


@campaign_app.command("list")
def list_campaigns(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """List every campaign this laboratory has recorded, newest first."""
    with _composed(manifest) as system:
        console.print_json(data=system.gateway.list_campaigns())


@campaign_app.command("inspect")
def inspect_campaign(
    campaign_id: Annotated[str, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Inspect one campaign, its iterations, and its events."""
    with _composed(manifest) as system:
        try:
            console.print_json(data=system.gateway.inspect_campaign(campaign_id))
        except KeyError:
            typer.echo(f"Campaign not found: {campaign_id}", err=True)
            raise typer.Exit(EXIT_NOT_FOUND) from None


@capability_app.command("list")
def list_capabilities(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    # The registry is the live truth about which adapter provides a capability. A read-only
    # system does not seed the store, so the stored adapter name can be absent or stale.
    with _composed(manifest, require_store=False) as system:
        table = Table("Capability", "Executor", "Risk", "Adapter")
        for definition in system.registry.list_capabilities():
            table.add_row(
                definition.id,
                definition.executor_type.value,
                definition.risk_class.value,
                system.registry.get_adapter(definition.id).name,
            )
        console.print(table)


@capability_app.command("create")
def scaffold_capability(
    capability_id: Annotated[str, typer.Argument()],
    name: Annotated[str, typer.Option()],
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("capabilities"),
) -> None:
    path = create_capability(destination, capability_id=capability_id, name=name)
    console.print(f"Created {path}")


@adapter_app.command("create")
def scaffold_adapter(
    name: Annotated[str, typer.Argument()],
    capability_id: Annotated[str, typer.Option()],
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("adapters"),
) -> None:
    path = create_adapter(destination / name, name=name, capability_id=capability_id)
    console.print(f"Created adapter at {path}")


@domain_app.command("create")
def scaffold_domain_pack(
    name: Annotated[str, typer.Argument()],
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("domain-packs"),
) -> None:
    path = create_domain_pack(destination / name, name=name)
    console.print(f"Created domain pack at {path}")


@schema_app.command("generate")
def generate_schemas(
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("schemas"),
) -> None:
    paths = generate_all_json_schemas(destination)
    console.print(f"Generated {len(paths)} schemas in {destination}")


@twin_app.command("validate")
def validate_twin(
    path: Annotated[Path, typer.Argument(help="Path to a twin definition")],
) -> None:
    """Validate a twin definition and its configured scene asset."""
    try:
        loaded = load_twin_definition(path)
    except (OSError, ValueError) as exc:
        typer.echo(f"Twin validation failed: {exc}", err=True)
        raise typer.Exit(EXIT_INVALID) from None
    console.print(f"Twin valid: [bold]{loaded.definition_path}[/bold]")


@twin_app.command("project")
def project_twin_run(
    run_id: Annotated[str, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Project one persisted run into the configured twin cue timeline."""
    with _composed(manifest) as system:
        if system.twin is None:
            typer.echo("Digital twin is not configured.", err=True)
            raise typer.Exit(EXIT_NOT_FOUND)
        try:
            projection = system.project_twin_run(run_id)
        except KeyError:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(EXIT_NOT_FOUND) from None
        except TwinProjectionError as exc:
            typer.echo(f"Twin projection failed: {exc}", err=True)
            raise typer.Exit(EXIT_INVALID) from None
        console.print_json(data=projection)


if __name__ == "__main__":
    app()
