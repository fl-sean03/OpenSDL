"""Compose the showcase frame: the plate on the left, the campaign that produced it on the right.

    uv run --locked python examples/discovering-colors/compose_frame.py --round 2

Everything on the right panel is read back out of the run: the recorded plates for the scatter and
the trace, and the laboratory's own event stream for the log. Nothing is written by hand, and
nothing from a round later than the one being shown is used — the frame is a moment inside a
campaign that has not finished, so the panel is only allowed to know what had happened by then.

The page is laid out in HTML and photographed with headless Chrome, which is the same posture the
scene build takes toward ffmpeg: an external tool that is already on the machine, driven by a
checked-in script, rather than a new Python dependency.
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CAMPAIGN = ROOT / "plates.json"
DATABASE = ROOT / ".opensdl" / "opensdl.db"
RENDER_DIR = ROOT / "renders"

PLATE_WIDTH = 1280
PANEL_WIDTH = 640
HEIGHT = 1080

# A quiet, near-neutral ground so the only saturated things in the frame are the samples.
INK = "#16181a"
MUTED = "#6d747a"
FAINT = "#aeb5ba"
GROUND = "#f7f6f3"
RULE = "#e0e2e3"
#: Fill for the median bar. Light enough to sit under the text, dark enough to read as a quantity.
BAR = "#d2d6d8"


def load_campaign() -> dict[str, Any]:
    if not CAMPAIGN.is_file():
        sys.exit(f"no campaign record at {CAMPAIGN}; run run_campaign.py first")
    return json.loads(CAMPAIGN.read_text(encoding="utf-8"))


def css_rgb(rgb: list[float] | None) -> str:
    if not rgb:
        return "transparent"
    return "rgb(%d,%d,%d)" % tuple(max(0, min(255, round(channel))) for channel in rgb)


def laboratory_totals(run_ids: list[str]) -> dict[str, int]:
    """How much work the laboratory actually recorded for the plates on screen.

    A tail of the event stream was here, and it was the wrong thing: timestamps at 10px are
    illegible in a timeline and read as decoration when they are legible. The counts say what the
    log was there to say — every well was a run, every step a task, and all of it is in the store.
    """
    totals = {"runs": len(run_ids), "tasks": 0, "events": 0}
    if not DATABASE.is_file() or not run_ids:
        return totals
    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)
    try:
        placeholders = ",".join("?" for _ in run_ids)
        for key, table in (("tasks", "tasks"), ("events", "events")):
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE run_id IN ({placeholders})",  # noqa: S608
                run_ids,
            ).fetchone()
            totals[key] = int(row[0]) if row else 0
    finally:
        connection.close()
    return totals


def scatter(plates: list[dict[str, Any]], width: int, height: int) -> str:
    """Every recipe tried so far, placed by two of its three dyes and filled with its own result.

    The point of the chart is that it is the same data as the plate, drawn against what was
    varied instead of against where it was pipetted. The box is the region the optimizer drew the
    current round from, which is the thing that shrinks.

    The two axes are scaled independently so the plot fills the column it is given. Both stay
    linear over the same declared zero-to-one range, so the sampling region is still a rectangle
    and the well-volume bound is still a straight line; only their angles change.
    """
    pad_x, pad_y = 34.0, 28.0
    span_x = width - 2 * pad_x
    span_y = height - 2 * pad_y

    def place_x(value: float) -> float:
        return pad_x + span_x * max(0.0, min(1.0, value))

    def place_y(value: float) -> float:
        return height - (pad_y + span_y * max(0.0, min(1.0, value)))

    marks = []
    for plate in plates:
        latest = plate is plates[-1]
        for well in plate["wells"]:
            recipe = well["recipe"]
            if recipe.get("cyan") is None or recipe.get("yellow") is None:
                continue
            x = place_x(float(recipe["cyan"]))
            y = place_y(float(recipe["yellow"]))
            fill = css_rgb(well.get("measured_rgb"))
            if latest:
                marks.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7.6" fill="{fill}" '
                    f'stroke="{GROUND}" stroke-width="1.2"/>'
                )
            else:
                marks.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{fill}" opacity="0.36"/>'
                )

    region = plates[-1].get("region")
    box = ""
    if region:
        best = min(
            (well for well in plates[-1]["wells"] if well["score"] is not None),
            key=lambda well: well["score"],
            default=None,
        )
        if best is not None:
            cx = float(best["recipe"]["cyan"])
            cy = float(best["recipe"]["yellow"])
            half = float(region) / 2.0
            x0, x1 = place_x(max(0.0, cx - half)), place_x(min(1.0, cx + half))
            y0, y1 = place_y(min(1.0, cy + half)), place_y(max(0.0, cy - half))
            box = (
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" '
                f'fill="none" stroke="{MUTED}" stroke-width="1.2" stroke-dasharray="4 5"/>'
            )

    frame = (
        f'<rect x="{pad_x}" y="{pad_y}" width="{span_x}" height="{span_y}" fill="none" '
        f'stroke="{RULE}" stroke-width="1"/>'
    )
    # The empty upper-right corner is not missing data: no recipe can use more than a wellful of
    # dye, so cyan plus yellow cannot exceed one. Drawing the bound says the optimizer proposed
    # nothing there because the campaign declared it infeasible, and the campaign refused it.
    infeasible = (
        f'<line x1="{place_x(1.0):.1f}" y1="{place_y(0.0):.1f}" '
        f'x2="{place_x(0.0):.1f}" y2="{place_y(1.0):.1f}" '
        f'stroke="{FAINT}" stroke-width="1.2"/>'
    )
    labels = (
        f'<text x="{pad_x}" y="{height - 5}" fill="{FAINT}" font-size="11" '
        f'font-family="DejaVu Sans Mono, monospace">cyan →</text>'
        f'<text x="{pad_x}" y="{pad_y - 8}" fill="{FAINT}" font-size="11" '
        f'font-family="DejaVu Sans Mono, monospace">yellow ↑</text>'
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f"{frame}{infeasible}{box}{''.join(marks)}{labels}</svg>"
    )


def build_html(campaign: dict[str, Any], round_number: int, plate_png: Path) -> str:
    """Lay out the panel for the size it is actually looked at.

    This image gets seen in a timeline about six hundred pixels wide, which leaves the panel two
    hundred, and full screen at maybe fourteen hundred, which leaves it under five. Type that reads
    on a monitor at 1:1 disappears at both. So there are four things on the panel instead of six,
    and the smallest of them is fifteen pixels.
    """
    plates = [plate for plate in campaign["plates"] if plate["round"] <= round_number]
    if not plates:
        sys.exit(f"round {round_number} is not in the campaign record")
    current = plates[-1]

    scored = [well for plate in plates for well in plate["wells"] if well.get("score") is not None]
    best = min(scored, key=lambda well: well["score"])
    target_rgb = campaign["target"]["rgb"]
    total_rounds = campaign["rounds"]
    wells_run = sum(len(plate["wells"]) for plate in plates)

    run_ids = [well["run_id"] for plate in plates for well in plate["wells"] if well.get("run_id")]
    totals = laboratory_totals(run_ids)

    encoded = base64.b64encode(plate_png.read_bytes()).decode("ascii")
    delta = float(best["score"])
    # The one number that carries the result wears the color it is chasing, taken down far enough
    # to hold its own as text on a light ground.
    accent = css_rgb([channel * 0.74 for channel in target_rgb])

    return f"""<!doctype html>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {PLATE_WIDTH + PANEL_WIDTH}px; height: {HEIGHT}px; overflow: hidden; }}
  body {{ display: flex; background: {GROUND}; -webkit-font-smoothing: antialiased; }}
  .plate {{ width: {PLATE_WIDTH}px; height: {HEIGHT}px; object-fit: cover; display: block; }}
  .panel {{
    width: {PANEL_WIDTH}px; height: {HEIGHT}px; padding: 42px 40px 30px;
    display: flex; flex-direction: column; color: {INK}; overflow: hidden;
    font-family: "DejaVu Sans", "Liberation Sans", sans-serif;
  }}
  .eyebrow {{
    font-size: 13px; letter-spacing: .18em; text-transform: uppercase; color: {MUTED};
  }}
  h1 {{
    font-size: 62px; font-weight: 700; letter-spacing: -.035em;
    line-height: 0.98; margin-top: 12px;
  }}
  .hook {{ font-size: 20px; color: {INK}; margin-top: 14px; line-height: 1.45; }}
  .hook em {{ font-style: normal; color: {MUTED}; }}
  hr {{ border: 0; border-top: 1px solid {RULE}; margin: 14px 0; }}
  .swatches {{ display: flex; gap: 22px; align-items: flex-end; }}
  .sw {{ flex: 1; }}
  .sw .chip {{ width: 100%; height: 84px; border-radius: 3px; }}
  .sw .lbl {{
    font-size: 12px; letter-spacing: .15em; text-transform: uppercase;
    color: {MUTED}; margin-bottom: 10px;
  }}
  .sw .val {{
    font-family: "DejaVu Sans Mono", monospace; font-size: 15px;
    color: {MUTED}; margin-top: 10px;
  }}
  .arrow {{ font-size: 26px; color: {MUTED}; padding-bottom: 32px; }}
  .delta {{ display: flex; align-items: baseline; gap: 14px; margin-top: 16px; }}
  .delta b {{
    font-size: 68px; font-weight: 700; letter-spacing: -.04em; line-height: 1;
    color: {accent};
  }}
  .delta span {{ font-size: 17px; color: {MUTED}; line-height: 1.35; }}
  .row {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .cap {{ font-size: 12px; letter-spacing: .15em; text-transform: uppercase; color: {MUTED}; }}
  .note {{ font-family: "DejaVu Sans Mono", monospace; font-size: 15px; color: {MUTED}; }}
  .chart {{ margin-top: 10px; }}
  .key {{
    display: flex; gap: 26px; align-items: center; justify-content: center;
    font-size: 15px; color: {MUTED}; margin-top: 12px;
  }}
  .key i {{
    display: inline-block; width: 12px; height: 12px; border-radius: 50%;
    background: {MUTED}; margin-right: 9px; font-style: normal; vertical-align: -1px;
  }}
  .key i.box {{
    border-radius: 0; background: none; border: 1.5px dashed {MUTED}; width: 12px; height: 12px;
  }}
  .ledger {{ font-size: 17px; color: {MUTED}; line-height: 1.5; }}
  .ledger b {{ color: {INK}; font-weight: 700; }}
  .spacer {{ flex: 1; min-height: 6px; }}
</style>
<img class="plate" src="data:image/png;base64,{encoded}">
<div class="panel">
  <div class="eyebrow">OpenSDL &nbsp;·&nbsp; autonomous lab, simulated end to end</div>
  <h1>Discovering<br>Colors</h1>
  <p class="hook">
    The lab was shown one color and asked to make it.<br>
    <em>96 mixtures a plate. No recipe, no chemistry, no hints.</em>
  </p>

  <hr>

  <div class="swatches">
    <div class="sw">
      <div class="lbl">Make this</div>
      <div class="chip" style="background:{css_rgb(target_rgb)}"></div>
      <div class="val">{" ".join(f"{channel:.0f}" for channel in target_rgb)}</div>
    </div>
    <div class="arrow">&rarr;</div>
    <div class="sw">
      <div class="lbl">Closest of {wells_run}</div>
      <div class="chip" style="background:{css_rgb(best["measured_rgb"])}"></div>
      <div class="val">{" ".join(f"{channel:.0f}" for channel in best["measured_rgb"])}</div>
    </div>
  </div>

  <div class="delta"><b>{delta:.1f}</b><span>&Delta;RGB apart<br>after round {round_number} of
    {total_rounds}</span></div>

  <hr>

  <div class="row"><div class="cap">Search space</div>
    <div class="note">region {current["region"]:.2f}</div></div>
  <div class="chart">{scatter(plates, PANEL_WIDTH - 80, 372)}</div>
  <div class="key">
    <span><i></i>this round</span>
    <span><i class="box"></i>sampling region</span>
  </div>

  <div class="spacer"></div>
  <hr>
  <div class="ledger">
    <b>{totals["runs"]}</b> runs and <b>{totals["tasks"]}</b> tasks recorded, every one
    policy-checked before the mixer was leased.
  </div>
</div>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=int, default=2)
    parser.add_argument("--plate", default="", help="the plate render to place on the left")
    parser.add_argument("--out", default="")
    parser.add_argument("--chrome", default="google-chrome")
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="device pixel ratio the page is shot at, before it is resampled to --width",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="delivered width; keep it near the size the image is actually viewed at",
    )
    parser.add_argument(
        "--keep-master", action="store_true", help="also keep the full-resolution shot"
    )
    options = parser.parse_args()

    campaign = load_campaign()
    plate_png = (
        Path(options.plate) if options.plate else RENDER_DIR / f"plate-round-{options.round}.png"
    )
    if not plate_png.is_file():
        sys.exit(f"no plate render at {plate_png}; run render_plate.py --round {options.round}")

    out = Path(options.out) if options.out else RENDER_DIR / f"showcase-round-{options.round}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    master = out.with_name(f"{out.stem}@{options.scale}x{out.suffix}")
    page = RENDER_DIR / f".frame-round-{options.round}.html"
    page.write_text(build_html(campaign, options.round, plate_png), encoding="utf-8")

    result = subprocess.run(
        [
            options.chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--force-device-scale-factor={options.scale}",
            "--default-background-color=00000000",
            f"--screenshot={master}",
            f"--window-size={PLATE_WIDTH + PANEL_WIDTH},{HEIGHT}",
            page.as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if not master.is_file():
        print(result.stdout + result.stderr, file=sys.stderr)
        return result.returncode or 1
    page.unlink()

    # Shoot large, deliver at the size it is looked at. A 3840-wide file is resampled by every
    # viewer that shows it, and their filtering is bilinear, which is what makes the type look
    # soft. Resampling here with Lanczos and a light unsharp keeps the supersampled edges on the
    # plate and the plot while giving the glyph stems their contrast back.
    width = options.width
    height = round(width * HEIGHT / (PLATE_WIDTH + PANEL_WIDTH))
    resample = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(master),
            "-vf",
            f"scale={width}:{height}:flags=lanczos,unsharp=5:5:0.8:5:5:0.0",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if resample.returncode != 0 or not out.is_file():
        print(resample.stdout + resample.stderr, file=sys.stderr)
        return resample.returncode or 1
    if not options.keep_master:
        master.unlink()
    print(f"wrote {out} ({width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
