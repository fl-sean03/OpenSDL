from __future__ import annotations

import os
import re
import shutil
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

from importlib.resources.abc import Traversable
from jinja2 import Template


_TEMPLATE_ROOT = files("opensdl_cli").joinpath("templates")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not value:
        raise ValueError("name must contain letters or numbers")
    return value


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)


def _walk(
    root: Traversable, prefix: PurePosixPath = PurePosixPath()
) -> list[tuple[PurePosixPath, Traversable]]:
    found: list[tuple[PurePosixPath, Traversable]] = []
    for item in sorted(root.iterdir(), key=lambda value: value.name):
        relative = prefix / item.name
        if item.is_dir():
            found.extend(_walk(item, relative))
        else:
            found.append((relative, item))
    return found


def _render_tree(template_name: str, destination: Path, context: dict[str, Any]) -> None:
    template_root = _TEMPLATE_ROOT.joinpath(template_name)
    if not template_root.is_dir():
        raise FileNotFoundError(f"unknown scaffold template: {template_name}")
    for relative, source in _walk(template_root):
        rendered_relative = Template(relative.as_posix()).render(**context)
        if not rendered_relative.endswith(".j2"):
            raise ValueError(f"template filename must end with .j2: {relative}")
        rendered_relative = rendered_relative[:-3]
        rendered = Template(source.read_text(encoding="utf-8")).render(**context)
        target = destination / Path(rendered_relative)
        _write(target, rendered, executable=target.suffix == ".sh")


def _expose_skills_to_claude(root: Path) -> None:
    """Expose canonical Agent Skills through Claude Code's project discovery path."""
    canonical_root = root / ".agents" / "skills"
    claude_root = root / ".claude" / "skills"
    claude_root.mkdir(parents=True, exist_ok=True)
    for canonical in sorted(canonical_root.iterdir()):
        if not canonical.is_dir():
            continue
        target = claude_root / canonical.name
        relative = Path("../../.agents/skills") / canonical.name
        try:
            target.symlink_to(relative, target_is_directory=True)
        except OSError:
            # Some Windows checkouts cannot create directory symlinks. A byte-for-byte mirror keeps
            # both harnesses usable; generated validation detects later drift.
            shutil.copytree(canonical, target)


#: How far a source path may climb before an absolute path is the more honest spelling.
_RELATIVE_CLIMB_LIMIT = 3

#: The framework packages a generated laboratory depends on.
FRAMEWORK_PACKAGES = (
    "opensdl-cli",
    "opensdl-adapter-simulated-lab",
    "opensdl-adapter-local-compute",
    "opensdl-adapter-human-task",
)


def find_framework_checkout(start: Path | None = None) -> Path | None:
    """The OpenSDL source tree this CLI is running out of, if it is running out of one.

    None of the framework packages are published yet, so a generated laboratory that declares them
    as registry dependencies cannot install. When the CLI is running from a checkout, that checkout
    is a resolvable source for all of them, and pointing at it is what makes `uv sync` work in the
    laboratory that was just created.

    Identified by the workspace member list rather than by directory name, so a renamed or
    relocated clone is still recognised and an unrelated `adapters/` directory is not.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        manifest = candidate / "pyproject.toml"
        if not manifest.is_file():
            continue
        try:
            text = manifest.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable parent on the way up
            continue
        if "[tool.uv.workspace]" in text and "adapters/simulated-lab" in text:
            return candidate
    return None


def _framework_sources(root: Path, checkout: Path | None) -> list[dict[str, str]]:
    """Where each framework package should be resolved from, as template rows."""

    if checkout is None:
        return []
    locations = {
        "opensdl-cli": checkout / "packages" / "cli",
        "opensdl-adapter-simulated-lab": checkout / "adapters" / "simulated-lab",
        "opensdl-adapter-local-compute": checkout / "adapters" / "local-compute",
        "opensdl-adapter-human-task": checkout / "adapters" / "human-task",
    }
    rows = []
    for package in FRAMEWORK_PACKAGES:
        location = locations[package]
        if not location.is_dir():
            return []
        # Relative where the two sit near each other, because a laboratory beside its framework
        # stays workable when the pair is moved or cloned together. A relative path that climbs
        # most of the way to the root is worse than an absolute one on every count: unreadable,
        # and no more portable.
        path = str(location)
        try:
            relative = os.path.relpath(location, root)
        except ValueError:  # pragma: no cover - different drives on Windows
            relative = None
        if relative is not None and relative.count("..") <= _RELATIVE_CLIMB_LIMIT:
            path = relative
        rows.append({"name": package, "path": Path(path).as_posix()})
    return rows


def create_laboratory(
    destination: str | Path,
    *,
    name: str | None = None,
    owner: str = "your-organization",
    framework_path: str | Path | None = None,
    use_registry: bool = False,
) -> Path:
    """Generate an organization-owned laboratory repository.

    `framework_path` names an OpenSDL checkout to resolve the framework packages from. Left unset,
    the checkout this CLI is running out of is used when there is one. `use_registry` declares the
    dependencies against a package index instead, which is correct once the packages are published
    and produces a laboratory that cannot install until they are.
    """
    root = Path(destination).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"destination is not empty: {root}")
    checkout: Path | None = None
    if not use_registry:
        if framework_path is not None:
            checkout = Path(framework_path).expanduser().resolve()
            if not (checkout / "pyproject.toml").is_file():
                raise FileNotFoundError(f"no OpenSDL checkout at {checkout}")
        else:
            checkout = find_framework_checkout()
    root.mkdir(parents=True, exist_ok=True)
    lab_name = _slug(name or root.name)
    _render_tree(
        "laboratory",
        root,
        {
            "name": lab_name,
            "package": lab_name.replace("-", "_"),
            "owner": owner,
            "framework_sources": _framework_sources(root, checkout),
        },
    )
    _expose_skills_to_claude(root)
    return root


def create_adapter(destination: str | Path, *, name: str, capability_id: str) -> Path:
    """Generate a passing simulator-first adapter package."""
    root = Path(destination).expanduser().resolve()
    slug = _slug(name)
    module = slug.replace("-", "_")
    _render_tree(
        "adapter",
        root,
        {
            "name": slug,
            "module": module,
            "class_name": ("".join(part.title() for part in re.split(r"[-_]", slug)) + "Adapter"),
            "capability_id": capability_id,
        },
    )
    return root


def create_domain_pack(destination: str | Path, *, name: str) -> Path:
    """Generate a complete, installable scientific domain-pack package."""
    root = Path(destination).expanduser().resolve()
    slug = _slug(name)
    _render_tree(
        "domain-pack",
        root,
        {"name": slug, "module": slug.replace("-", "_")},
    )
    return root


def create_capability(destination: str | Path, *, capability_id: str, name: str) -> Path:
    """Generate a language-neutral capability card."""
    root = Path(destination).expanduser().resolve()
    target = root / f"{capability_id.replace('.', '-')}.yaml"
    source = _TEMPLATE_ROOT.joinpath("capability", "capability.yaml.j2")
    rendered = Template(source.read_text(encoding="utf-8")).render(
        capability_id=capability_id,
        name=name,
    )
    _write(target, rendered)
    return target
