from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
OPENSDL_FLOOR = re.compile(r'"(opensdl-[a-z0-9-]+)>=([^"]+)"')


def project_version(path: Path) -> str:
    with path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def version_failures(root: Path) -> list[str]:
    root_project = root / "pyproject.toml"
    expected = project_version(root_project)
    with root_project.open("rb") as handle:
        configuration = tomllib.load(handle)
    failures: list[str] = []
    for member in configuration["tool"]["uv"]["workspace"]["members"]:
        path = root / member / "pyproject.toml"
        actual = project_version(path)
        if actual != expected:
            failures.append(f"{path.relative_to(root)}: {actual} != {expected}")

    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    if not isinstance(citation, dict) or str(citation.get("version")) != expected:
        failures.append("CITATION.cff: version does not match the workspace")

    templates = (root / "packages/cli/src/opensdl_cli/templates").glob("**/pyproject.toml.j2")
    for path in sorted(templates):
        for dependency, actual in OPENSDL_FLOOR.findall(path.read_text(encoding="utf-8")):
            if actual != expected:
                failures.append(
                    f"{path.relative_to(root)}: {dependency} floor {actual} != {expected}"
                )
    return failures


def main() -> None:
    failures = version_failures(ROOT)
    if failures:
        raise SystemExit("inconsistent release versions:\n" + "\n".join(failures))
    version = project_version(ROOT / "pyproject.toml")
    print(f"workspace, citation, and generated dependency versions are synchronized: {version}")


if __name__ == "__main__":
    main()
