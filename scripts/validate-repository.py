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


def validate_build_artifacts() -> None:
    """Fail when a build directory holds a stale copy of a real module.

    ``setuptools`` leaves ``<member>/build/lib/<package>/`` behind after ``uv build``. Those files
    are gitignored, so nothing notices them, and they are copies of modules that keep changing, so
    they go stale immediately. A recursive search of the worktree then returns two answers for
    every symbol and no indication which one ships -- an ambiguity that has already misled an
    analysis of this repository. Nothing reads them and no command needs them to survive a build.

    Release output is left alone: an ``sdist`` or wheel under ``dist/`` shadows nothing, because it
    is an archive rather than an importable file tree.
    """
    stale: list[str] = []
    for name in ("build", "dist"):
        for directory in ROOT.rglob(name):
            relative = directory.relative_to(ROOT)
            if not directory.is_dir() or directory.is_symlink():
                continue
            if any(part in {".git", ".venv", "node_modules"} for part in relative.parts):
                continue
            sources = sorted(path.relative_to(ROOT).as_posix() for path in directory.rglob("*.py"))
            if sources:
                count = f"{len(sources)} Python file" + ("s" if len(sources) != 1 else "")
                stale.append(f"{relative.as_posix()}/ ({count}, e.g. {sources[0]})")
    if stale:
        raise SystemExit(
            "build directories contain importable copies of repository modules:\n"
            + "\n".join(f"  {entry}" for entry in stale)
            + "\n  they are gitignored, go stale the moment the source changes, and make every "
            "recursive search ambiguous\n  remove them with `make clean`"
        )


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


AGENT_ACTION = "anthropics/claude-code-action"


def agent_workflow_failures() -> list[str]:
    """Enforce the one input that decides what an agent workflow's token can do.

    ``anthropics/claude-code-action`` has no default for ``github_token``. Its ``setupGitHubToken``
    returns the supplied token when there is one and otherwise exchanges the workflow's OIDC token
    for a Claude GitHub App token carrying Contents, Issues and Pull Requests *write*. So omitting
    the input does one of two things, and both are wrong here: with ``id-token: write`` the action
    quietly acquires a write token that ignores every permission the job narrowed, and without it
    the action fails before the model runs.

    Neither shows up in review. GitHub ignores unknown ``with:`` keys with a warning, so a typo in
    the input name reads exactly like the correct spelling, and nothing else in this repository
    inspects workflow semantics -- ``validate_yaml`` only parses. This repository shipped a
    reviewer workflow that could never start for precisely this reason while its own comments
    described the token it would have held.
    """
    failures: list[str] = []
    workflows = ROOT / ".github" / "workflows"
    if not workflows.is_dir():
        return failures
    for path in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        relative = path.relative_to(ROOT).as_posix()
        for job_name, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            permissions = job.get("permissions")
            grants_id_token = (
                isinstance(permissions, dict) and permissions.get("id-token") == "write"
            )
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                uses = str(step.get("uses", ""))
                if not uses.startswith(f"{AGENT_ACTION}@"):
                    continue
                where = f"{relative}: job '{job_name}'"
                if "github_token" not in (step.get("with") or {}):
                    failures.append(
                        f"{where} runs {AGENT_ACTION} without a `github_token:` input, so the "
                        "action falls back to exchanging an OIDC token for a Contents/Issues/"
                        "PullRequests-write GitHub App token"
                    )
                if grants_id_token:
                    failures.append(
                        f"{where} grants `id-token: write` alongside {AGENT_ACTION}, which lets "
                        "that exchange succeed if `github_token:` is ever dropped"
                    )
                if "@" in uses and len(uses.split("@", 1)[1].split()[0]) != 40:
                    failures.append(f"{where} does not pin {AGENT_ACTION} to a full commit SHA")
    return failures


def validate_agent_workflows() -> None:
    failures = agent_workflow_failures()
    if failures:
        raise SystemExit("unsafe agent workflow configuration:\n" + "\n".join(failures))


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
    validate_agent_workflows()
    validate_markdown_links()
    validate_build_artifacts()
    print(
        "TOML, YAML, JSON, agent instructions, repository skills, agent workflow tokens, "
        "relative Markdown links, and the absence of stale build output are valid"
    )


if __name__ == "__main__":
    main()
