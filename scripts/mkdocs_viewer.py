"""Publish the twin viewer with the documentation site.

The viewer replays a recorded run against the reference scene, and until now it was reachable only
by cloning the repository and starting an API. That is a high price for looking at something. This
copies the committed build and the scene it draws into the built site, so the page is one link.

It is a `mkdocs` hook rather than a workflow step because the documentation job has no Node: the
viewer's `static/` directory is committed and `make viewer` proves it matches its source, so
publishing is a copy rather than a build.

The scene is copied rather than committed a second time. It is 5.6 MB, it already lives beside the
Blender source that produces it, and a second copy in Git would be a second thing to keep in step.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "digital-twin-surrogate"
VIEWER_BUILD = EXAMPLE / "viewer" / "static"
SCENE = EXAMPLE / "scene" / "assets" / "surrogate-cell.glb"

#: Where the built page looks for the scene when no OpenSDL API answers, relative to itself.
SCENE_NAME = "scene.glb"


def on_post_build(config: Any, **_: Any) -> None:
    site = Path(config["site_dir"]) / "viewer"
    if not VIEWER_BUILD.is_dir():
        raise FileNotFoundError(
            f"no viewer build at {VIEWER_BUILD}; run `make viewer` to produce and commit it"
        )
    if not SCENE.is_file():
        raise FileNotFoundError(f"no reference scene at {SCENE}")

    shutil.copytree(VIEWER_BUILD, site, dirs_exist_ok=True)
    shutil.copy2(SCENE, site / SCENE_NAME)
    print(f"published the twin viewer to {site}")
