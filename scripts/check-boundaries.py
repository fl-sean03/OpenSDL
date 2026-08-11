"""Enforce the declared import boundaries between workspace packages.

Every importable package a distribution ships under ``src`` must appear in ``ALLOWED``. A package
missing from the map is a failure, not a skip: an unmapped package would otherwise ship with no
boundary at all, which is how the digital-twin surrogate adapter went unchecked. The reverse is
also a failure, so a renamed or deleted package cannot leave a stale entry behind that silently
stops constraining anything.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).parents[1]

# Directories that hold generated, vendored, or virtual-environment copies of real distributions.
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".opensdl",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "site",
}

ALLOWED: dict[str, set[str]] = {
    "opensdl_core": set(),
    "opensdl_schemas": {"opensdl_core"},
    "opensdl_twin": {"opensdl_core"},
    "opensdl_capabilities": {"opensdl_core"},
    "opensdl_policy": {"opensdl_core"},
    "opensdl_workflows": {"opensdl_core"},
    "opensdl_storage": {"opensdl_core"},
    "opensdl_simulation": {"opensdl_core", "opensdl_capabilities"},
    "opensdl_runtime": {
        "opensdl_core",
        "opensdl_capabilities",
        "opensdl_policy",
        "opensdl_storage",
        "opensdl_workflows",
    },
    "opensdl_provenance": {"opensdl_core", "opensdl_storage"},
    "opensdl_operators": {
        "opensdl_core",
        "opensdl_capabilities",
        "opensdl_runtime",
        "opensdl_storage",
        "opensdl_schemas",
    },
    "opensdl": {"opensdl_core", "opensdl_schemas"},
    "opensdl_controller": {
        "opensdl_core",
        "opensdl_schemas",
        "opensdl_capabilities",
        "opensdl_policy",
        "opensdl_storage",
        "opensdl_workflows",
        "opensdl_runtime",
        "opensdl_provenance",
        "opensdl_operators",
        "opensdl_twin",
    },
    "opensdl_api": {"opensdl_controller", "opensdl_core"},
    # The CLI is an application: it composes packages and serves their interfaces. It reaches
    # opensdl_operators for the same reason it reaches opensdl_api — to serve a transport,
    # not to borrow logic. An MCP transport nothing can start is dead code with a test.
    "opensdl_cli": {
        "opensdl_controller",
        "opensdl_operators",
        "opensdl_provenance",
        "opensdl_schemas",
        "opensdl_api",
        "opensdl_twin",
    },
    "opensdl_adapter_simulated_lab": {"opensdl_core", "opensdl_capabilities", "opensdl_simulation"},
    "opensdl_adapter_local_compute": {"opensdl_core", "opensdl_capabilities"},
    # An optimizer plugin is an extension point third parties write, so it may depend only on the
    # contract. This entry used to read `{"opensdl_runtime"}` and was the sole exception in this
    # map: the optimizer contract lived in the runtime, so implementing two methods meant
    # depending on storage, policy, workflows and SQLAlchemy. The contract moved to
    # `opensdl_core.campaign`; the exception is gone.
    "opensdl_adapter_grid_optimizer": {"opensdl_core"},
    # The second published optimizer, and the same boundary as the first: an optimizer plugin
    # costs a dependency on the declarations and protocols, and on nothing that runs a laboratory.
    "opensdl_adapter_contracting_search": {"opensdl_core"},
    "opensdl_adapter_human_task": {"opensdl_core", "opensdl_capabilities"},
    "opensdl_adapter_cell_surrogate": {"opensdl_core", "opensdl_capabilities"},
    "opensdl_domain_materials": {"opensdl_core"},
    "opensdl_domain_chemistry": {"opensdl_core"},
    "opensdl_domain_physics": {"opensdl_core"},
}


def distribution_sources() -> Iterator[Path]:
    """Yield the ``src`` directory of every distribution in the repository."""
    for pyproject in ROOT.rglob("pyproject.toml"):
        relative = pyproject.relative_to(ROOT)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        source = pyproject.parent / "src"
        if source.is_dir():
            yield source


def shipped_packages() -> dict[str, Path]:
    """Map every importable package name to the directory the distribution ships."""
    found: dict[str, Path] = {}
    for source in sorted(distribution_sources()):
        for package_dir in sorted(source.iterdir()):
            if package_dir.is_dir() and (package_dir / "__init__.py").is_file():
                found[package_dir.name] = package_dir
    return found


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def main() -> None:
    packages = shipped_packages()
    internal = set(ALLOWED) | set(packages)
    failures: list[str] = []

    for name in sorted(set(packages) - set(ALLOWED)):
        failures.append(
            f"{packages[name].relative_to(ROOT)} has no declared dependency boundary: "
            f"add {name!r} to ALLOWED in scripts/check-boundaries.py"
        )
    for name in sorted(set(ALLOWED) - set(packages)):
        failures.append(
            f"{name!r} is declared in ALLOWED but no distribution ships it: "
            "remove the stale entry from scripts/check-boundaries.py"
        )

    for name, package_dir in sorted(packages.items()):
        allowed = ALLOWED.get(name, set()) | {name}
        for path in sorted(package_dir.rglob("*.py")):
            forbidden = (imports(path) & internal) - allowed
            if forbidden:
                failures.append(
                    f"{path.relative_to(ROOT)} imports forbidden internal packages: {sorted(forbidden)}"
                )

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"package dependency boundaries are valid ({len(packages)} packages checked)")


if __name__ == "__main__":
    main()
