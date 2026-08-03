from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
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
    "node_modules",
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


def skill_failures(skills_root: Path) -> list[str]:
    failures: list[str] = []
    for skill_directory in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_path = skill_directory / "SKILL.md"
        relative = skill_path.relative_to(skills_root.parent.parent)
        if not skill_path.is_file():
            failures.append(f"{skill_directory.name}: missing SKILL.md")
            continue
        content = skill_path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            failures.append(f"{relative}: missing YAML frontmatter")
            continue
        try:
            _, frontmatter, body = content.split("---\n", 2)
            metadata = yaml.safe_load(frontmatter)
        except (ValueError, yaml.YAMLError) as error:
            failures.append(f"{relative}: invalid YAML frontmatter ({error})")
            continue
        if not isinstance(metadata, dict):
            failures.append(f"{relative}: frontmatter must be a mapping")
            continue
        if set(metadata) != {"name", "description"}:
            failures.append(f"{relative}: frontmatter must contain only name and description")
        name = metadata.get("name")
        if not isinstance(name, str):
            failures.append(f"{relative}: name must be a string")
        else:
            if name != skill_directory.name:
                failures.append(f"{relative}: name must match directory {skill_directory.name!r}")
            if len(name) > 64 or SKILL_NAME.fullmatch(name) is None:
                failures.append(
                    f"{relative}: name must use lowercase letters, digits, and single hyphens"
                )
        description = metadata.get("description")
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
            failures.append(f"{relative}: description must contain 1 to 1024 characters")
        elif "use when" not in description.lower():
            failures.append(f"{relative}: description must state when to use the skill")
        if not body.strip():
            failures.append(f"{relative}: body must not be empty")
        elif len(body.splitlines()) > 500:
            failures.append(f"{relative}: body must not exceed 500 lines")
        for helper in skill_directory.rglob("*.sh"):
            helper_relative = helper.relative_to(skill_directory).as_posix()
            if helper.name not in body and helper_relative not in body:
                failures.append(f"{relative}: helper {helper_relative!r} is not referenced")
            syntax = subprocess.run(
                ["bash", "-n", str(helper)],
                check=False,
                capture_output=True,
                text=True,
            )
            if syntax.returncode:
                failures.append(f"{relative}: helper {helper_relative!r} has invalid shell syntax")
            if not helper.stat().st_mode & 0o111:
                failures.append(f"{relative}: helper {helper_relative!r} is not executable")
    return failures


def claude_skill_adapter_failures(
    skills_root: Path,
    claude_root: Path,
) -> list[str]:
    failures: list[str] = []
    expected = {path.name for path in skills_root.iterdir() if path.is_dir()}
    actual = {path.name for path in claude_root.iterdir()} if claude_root.is_dir() else set()
    for name in sorted(expected):
        adapter = claude_root / name
        canonical = skills_root / name
        if not adapter.is_symlink():
            failures.append(f".claude/skills/{name}: must be a symlink to the canonical skill")
        elif adapter.resolve() != canonical.resolve():
            failures.append(f".claude/skills/{name}: points to the wrong canonical skill")
    for name in sorted(actual - expected):
        failures.append(f".claude/skills/{name}: has no canonical skill")
    return failures


def validate_instruction_adapters() -> None:
    failures: list[str] = []
    for agents_path in repository_files("AGENTS.md"):
        claude_path = agents_path.with_name("CLAUDE.md")
        if not claude_path.is_file():
            failures.append(f"{agents_path.relative_to(ROOT)}: missing adjacent CLAUDE.md")
            continue
        if "@AGENTS.md" not in claude_path.read_text(encoding="utf-8").splitlines():
            failures.append(f"{claude_path.relative_to(ROOT)}: must import @AGENTS.md")
    if failures:
        raise SystemExit("invalid Claude instruction adapters:\n" + "\n".join(failures))


def validate_skills() -> None:
    skills_root = ROOT / ".agents" / "skills"
    failures = skill_failures(skills_root)
    failures.extend(claude_skill_adapter_failures(skills_root, ROOT / ".claude" / "skills"))
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
    validate_instruction_adapters()
    validate_skills()
    validate_markdown_links()
    print(
        "TOML, YAML, JSON, agent instructions, repository skills, and relative Markdown links are valid"
    )


if __name__ == "__main__":
    main()
