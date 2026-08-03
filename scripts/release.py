from __future__ import annotations

import argparse
import re
import tomllib
from datetime import date
from pathlib import Path

from packaging.version import InvalidVersion, Version


ROOT = Path(__file__).parents[1]
PROJECT_VERSION = re.compile(r'(?m)^version = "[^"]+"$')
OPENSDL_FLOOR = re.compile(r'("opensdl-[a-z0-9-]+>=)[^"]+(")')


def workspace_project_paths(root: Path) -> list[Path]:
    with (root / "pyproject.toml").open("rb") as handle:
        configuration = tomllib.load(handle)
    members = configuration["tool"]["uv"]["workspace"]["members"]
    return [root / "pyproject.toml", *(root / member / "pyproject.toml" for member in members)]


def update_release_version(
    root: Path,
    version: str,
    *,
    released_on: date | None = None,
) -> list[Path]:
    changed: list[Path] = []
    for path in workspace_project_paths(root):
        text = path.read_text(encoding="utf-8")
        updated, count = PROJECT_VERSION.subn(f'version = "{version}"', text, count=1)
        if count != 1:
            raise ValueError(f"expected one project version in {path.relative_to(root)}")
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path)

    for path in sorted(
        (root / "packages/cli/src/opensdl_cli/templates").glob("**/pyproject.toml.j2")
    ):
        text = path.read_text(encoding="utf-8")
        updated = OPENSDL_FLOOR.sub(rf"\g<1>{version}\2", text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            changed.append(path)

    citation = root / "CITATION.cff"
    text = citation.read_text(encoding="utf-8")
    updated, version_count = re.subn(
        r"(?m)^version: .+$",
        f"version: {version}",
        text,
        count=1,
    )
    updated, date_count = re.subn(
        r"(?m)^date-released: .+$",
        f"date-released: {(released_on or date.today()).isoformat()}",
        updated,
        count=1,
    )
    if version_count != 1 or date_count != 1:
        raise ValueError("CITATION.cff must contain one version and one release date")
    if updated != text:
        citation.write_text(updated, encoding="utf-8")
        changed.append(citation)
    return changed


def normalized_version(value: str) -> str:
    try:
        normalized = str(Version(value))
    except InvalidVersion as error:
        raise ValueError(f"invalid PEP 440 version: {value!r}") from error
    if normalized != value:
        raise ValueError(f"use normalized PEP 440 version {normalized!r}")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize release version metadata")
    parser.add_argument("version")
    args = parser.parse_args()
    try:
        version = normalized_version(args.version)
        changed = update_release_version(ROOT, version)
    except ValueError as error:
        parser.error(str(error))
    relative = ", ".join(str(path.relative_to(ROOT)) for path in changed) or "none"
    print(f"updated release version to {version}: {relative}")
    print("run the full test, schema, migration, metadata, and build checks before tagging")


if __name__ == "__main__":
    main()
