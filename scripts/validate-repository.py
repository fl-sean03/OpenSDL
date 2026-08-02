from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def validate_toml() -> None:
    for path in ROOT.rglob("*.toml"):
        with path.open("rb") as handle:
            tomllib.load(handle)


def validate_yaml() -> None:
    for pattern in ("*.yaml", "*.yml"):
        for path in ROOT.rglob(pattern):
            # Compose validates YAML syntax without resolving application-specific tags
            # such as MkDocs' ``!!python/name`` formatter references.
            yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)


def validate_json() -> None:
    for path in ROOT.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def validate_markdown_links() -> None:
    failures: list[str] = []
    for path in ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for raw in LINK.findall(text):
            target = raw.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)} -> {raw}")
    if failures:
        raise SystemExit("broken relative Markdown links:\n" + "\n".join(failures))


def main() -> None:
    validate_toml()
    validate_yaml()
    validate_json()
    validate_markdown_links()
    print("TOML, YAML, JSON, and relative Markdown links are valid")


if __name__ == "__main__":
    main()
