from __future__ import annotations

import re
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


def _walk(root: Traversable, prefix: PurePosixPath = PurePosixPath()) -> list[tuple[PurePosixPath, Traversable]]:
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


def create_laboratory(
    destination: str | Path,
    *,
    name: str | None = None,
    owner: str = "your-organization",
) -> Path:
    """Generate an organization-owned laboratory repository."""
    root = Path(destination).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"destination is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    lab_name = _slug(name or root.name)
    _render_tree(
        "laboratory",
        root,
        {
            "name": lab_name,
            "package": lab_name.replace("-", "_"),
            "owner": owner,
        },
    )
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
            "class_name": (
                "".join(part.title() for part in re.split(r"[-_]", slug)) + "Adapter"
            ),
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
