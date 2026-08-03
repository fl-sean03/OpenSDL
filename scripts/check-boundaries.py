from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]

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
        "opensdl_provenance",
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
    "opensdl_cli": {
        "opensdl_controller",
        "opensdl_provenance",
        "opensdl_operators",
        "opensdl",
        "opensdl_schemas",
        "opensdl_api",
        "opensdl_twin",
    },
    "opensdl_adapter_simulated_lab": {"opensdl_core", "opensdl_capabilities", "opensdl_simulation"},
    "opensdl_adapter_local_compute": {"opensdl_core", "opensdl_capabilities"},
    "opensdl_adapter_grid_optimizer": {"opensdl_runtime"},
    "opensdl_adapter_human_task": {"opensdl_core", "opensdl_capabilities"},
    "opensdl_domain_materials": {"opensdl_core"},
    "opensdl_domain_chemistry": {"opensdl_core"},
    "opensdl_domain_physics": {"opensdl_core"},
}
INTERNAL = set(ALLOWED)


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
    failures: list[str] = []
    for source in ROOT.glob("**/src"):
        for package_dir in source.iterdir():
            if not package_dir.is_dir() or package_dir.name not in ALLOWED:
                continue
            allowed = ALLOWED[package_dir.name] | {package_dir.name}
            for path in package_dir.rglob("*.py"):
                forbidden = (imports(path) & INTERNAL) - allowed
                if forbidden:
                    failures.append(
                        f"{path.relative_to(ROOT)} imports forbidden internal packages: {sorted(forbidden)}"
                    )
    if failures:
        raise SystemExit("\n".join(failures))
    print("package dependency boundaries are valid")


if __name__ == "__main__":
    main()
