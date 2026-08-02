from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".opensdl",
    ".pyright",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "site",
}


def repository_files(pattern: str):
    for path in ROOT.rglob(pattern):
        relative = path.relative_to(ROOT)
        if not any(part in IGNORED_DIRECTORIES for part in relative.parts):
            yield path


def validate_toml() -> None:
    for path in repository_files("*.toml"):
        with path.open("rb") as handle:
            tomllib.load(handle)


def validate_yaml() -> None:
    for pattern in ("*.yaml", "*.yml"):
        for path in repository_files(pattern):
            # Compose validates YAML syntax without resolving application-specific tags
            # such as MkDocs' ``!!python/name`` formatter references.
            yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)


def validate_json() -> None:
    for path in repository_files("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def validate_skills() -> None:
    failures: list[str] = []
    skills_root = ROOT / ".agents" / "skills"
    for skill_path in sorted(skills_root.glob("*/SKILL.md")):
        relative = skill_path.relative_to(ROOT)
        content = skill_path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            failures.append(f"{relative}: missing YAML frontmatter")
            continue
        try:
            _, frontmatter, _ = content.split("---\n", 2)
            metadata = yaml.safe_load(frontmatter)
        except (ValueError, yaml.YAMLError) as error:
            failures.append(f"{relative}: invalid YAML frontmatter ({error})")
            continue
        if not isinstance(metadata, dict):
            failures.append(f"{relative}: frontmatter must be a mapping")
            continue
        if set(metadata) != {"name", "description"}:
            failures.append(f"{relative}: frontmatter must contain only name and description")
        if metadata.get("name") != skill_path.parent.name:
            failures.append(f"{relative}: name must match directory {skill_path.parent.name!r}")
        if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            failures.append(f"{relative}: description must be a non-empty string")
    if failures:
        raise SystemExit("invalid repository skills:\n" + "\n".join(failures))


def validate_markdown_links() -> None:
    failures: list[str] = []
    for path in repository_files("*.md"):
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
    validate_skills()
    validate_markdown_links()
    print("TOML, YAML, JSON, repository skills, and relative Markdown links are valid")


if __name__ == "__main__":
    main()
