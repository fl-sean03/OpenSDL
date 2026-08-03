from __future__ import annotations

import asyncio
import json
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from opensdl_controller import OpenSDLSystem
from opensdl_provenance import PropagationGraph
from opensdl_schemas import generate_json_schemas, validate_manifest_file, validate_workflow_file

from .scaffold import create_adapter, create_capability, create_domain_pack, create_laboratory

app = typer.Typer(no_args_is_help=True, help="Build, validate, run, and extend OpenSDL laboratories.")
adapter_app = typer.Typer(no_args_is_help=True, help="Create and inspect adapters.")
capability_app = typer.Typer(no_args_is_help=True, help="Create and inspect capabilities.")
schema_app = typer.Typer(no_args_is_help=True, help="Generate public schemas.")
domain_app = typer.Typer(no_args_is_help=True, help="Create scientific domain packs.")
app.add_typer(adapter_app, name="adapter")
app.add_typer(capability_app, name="capability")
app.add_typer(domain_app, name="domain-pack")
app.add_typer(schema_app, name="schema")
console = Console()


def _json_input(value: str) -> dict[str, Any]:
    if value.startswith("@"):
        value = Path(value[1:]).read_text(encoding="utf-8")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise typer.BadParameter("inputs must be a JSON object")
    return parsed


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
    """Validate a laboratory manifest and optional workflows."""
    loaded = validate_manifest_file(manifest)
    console.print(f"Manifest valid: [bold]{loaded.metadata.name}[/bold]")
    for path in workflow or []:
        definition = validate_workflow_file(path)
        console.print(f"Workflow valid: {definition.id}")


@app.command()
def doctor(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Check database, artifact store, and adapter health."""
    result = asyncio.run(_doctor(manifest))
    console.print_json(data=result)
    if not result["passed"]:
        raise typer.Exit(1)


async def _doctor(manifest: Path) -> dict[str, Any]:
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        await system.start()
        return await system.doctor()
    finally:
        await system.close()


@app.command("run")
def run_workflow(
    workflow: Annotated[Path, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    inputs: Annotated[str, typer.Option(help="JSON object or @path/to/file.json")] = "{}",
    operator_id: Annotated[str, typer.Option()] = "operator/cli",
) -> None:
    """Execute a workflow through the durable reference runtime."""
    result = asyncio.run(_run(manifest, workflow, _json_input(inputs), operator_id))
    console.print_json(data=result)


async def _run(manifest: Path, workflow: Path, inputs: dict[str, Any], operator_id: str) -> dict[str, Any]:
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        await system.start()
        run = await system.run_workflow_file(workflow, inputs, operator_id=operator_id)
        return system.gateway.inspect_run(run.id)
    finally:
        await system.close()


@app.command()
def inspect(
    run_id: Annotated[str, typer.Argument()],
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Inspect one persisted run, its tasks, and events."""
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        console.print_json(data=system.gateway.inspect_run(run_id))
    finally:
        system.database.dispose()


@app.command()
def events(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
    run_id: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option()] = 200,
) -> None:
    """Query execution events."""
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        payload = [event.model_dump(mode="json") for event in system.repositories.list_events(run_id=run_id, limit=limit)]
        console.print_json(data=payload)
    finally:
        system.database.dispose()


@app.command()
def export(
    run_id: Annotated[str, typer.Argument()],
    destination: Annotated[Path, typer.Option("--destination", "-d")] = Path("exports"),
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    """Export a run as a portable RO-Crate-style ZIP bundle."""
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        path = system.exporter.export(run_id, destination)
        console.print(str(path))
    finally:
        system.database.dispose()


@app.command()
def propagate(
    paths: Annotated[list[str], typer.Argument(help="Changed repository paths")],
    graph: Annotated[Path, typer.Option("--graph", "-g")] = Path("propagation.yaml"),
) -> None:
    """Find contracts, code, tests, examples, and docs affected by a change."""
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


@capability_app.command("list")
def list_capabilities(
    manifest: Annotated[Path, typer.Option("--manifest", "-m")] = Path("opensdl.yaml"),
) -> None:
    system = OpenSDLSystem.from_manifest(manifest)
    try:
        table = Table("Capability", "Executor", "Risk", "Adapter")
        adapters = {definition.id: adapter for definition, adapter in system.repositories.list_capabilities()}
        for definition in system.registry.list_capabilities():
            table.add_row(definition.id, definition.executor_type.value, definition.risk_class.value, adapters.get(definition.id, ""))
        console.print(table)
    finally:
        system.database.dispose()


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
    paths = generate_json_schemas(destination)
    console.print(f"Generated {len(paths)} schemas in {destination}")


if __name__ == "__main__":
    app()
