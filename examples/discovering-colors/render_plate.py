"""Photograph one round of the campaign, in the reference cell, from above.

    uv run --locked python examples/discovering-colors/render_plate.py --round 4

The build runs in a temporary directory with the scene scripts copied into it, which is how the
reproducibility test runs it too. That is not tidiness: a build writes the node inventory, the
motion report and the saved blend file next to itself, and those are committed artifacts checked
byte for byte against a rebuild that passes no arguments. Rendering a painted plate in the source
tree would overwrite them with a scene that has ninety-six extra materials in it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENE_ROOT = ROOT.parent / "digital-twin-surrogate" / "scene"
SCENE_SCRIPTS = (SCENE_ROOT / "build_scene.py", SCENE_ROOT / "check_scene.py")
CAMPAIGN = ROOT / "plates.json"
RENDER_DIR = ROOT / "renders"

#: The scene records the Blender it was built with, and the geometry is only reproducible under
#: that version. A plate render is a picture rather than a checked artifact, so a mismatch is worth
#: saying out loud and continuing, not refusing.
INVENTORY = SCENE_ROOT / "assets" / "node-inventory.json"


def expected_blender() -> str:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    return str(inventory["generator"]["blender"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, default=4, help="which campaign round to paint")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--engine", choices=("eevee", "cycles"), default="cycles")
    parser.add_argument("--samples", type=int, default=256)
    parser.add_argument("--resolution", default="1280x1080")
    parser.add_argument("--height", type=float, default=0.62, help="camera height, metres")
    parser.add_argument("--lens", type=float, default=85.0, help="camera lens, millimetres")
    parser.add_argument(
        "--light",
        type=float,
        default=0.22,
        help="scales the room lights; the wells emit, so only the deck and plate respond",
    )
    parser.add_argument("--out", default="")
    options = parser.parse_args()

    if not CAMPAIGN.is_file():
        print(f"no campaign record at {CAMPAIGN}; run run_campaign.py first", file=sys.stderr)
        return 1

    # Resolved, because the build runs with its working directory inside the staging area below.
    # A relative path would be written there and deleted with it.
    out = (
        Path(options.out) if options.out else RENDER_DIR / f"plate-round-{options.round}.png"
    ).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="opensdl-plate-") as workspace:
        staged = Path(workspace)
        for script in SCENE_SCRIPTS:
            shutil.copy(script, staged / script.name)
        command = [
            options.blender,
            "-b",
            "--factory-startup",
            "-noaudio",
            "-P",
            SCENE_SCRIPTS[0].name,
            "--",
            "--no-export",
            "--render-plate",
            "--well-colors",
            str(CAMPAIGN),
            "--plate-round",
            str(options.round),
            "--plate-out",
            str(out),
            "--plate-height",
            str(options.height),
            "--plate-lens",
            str(options.lens),
            "--plate-light",
            str(options.light),
            "--engine",
            options.engine,
            "--samples",
            str(options.samples),
            "--resolution",
            options.resolution,
        ]
        print(f"expected Blender {expected_blender()}; building in {staged}", flush=True)
        result = subprocess.run(command, cwd=staged, check=False, text=True)
        if result.returncode != 0:
            return result.returncode

    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
