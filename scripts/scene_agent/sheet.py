"""Write the run as one page: every attempt, its render, and what the critic said about it.

A score in a log tells you the loop converged. It does not tell you *how*, and it does not let
anybody else check the critic's judgement against the image it was judging. This page puts the
render, the score, the defects and the next actions side by side for every iteration, so the
progression is legible without opening seven directories.

Plain HTML with inlined images and no dependencies, because the point is that it opens.
"""

from __future__ import annotations

import base64
import html
from dataclasses import asdict
from pathlib import Path
from typing import Any

CSS = """
:root { --bg:#faf9f7; --ink:#1a1a1a; --dim:#6b6b6b; --line:#e2ded9; --bad:#a33; --good:#2c6e49; }
* { box-sizing: border-box; }
body { margin:0; padding:2rem; background:var(--bg); color:var(--ink);
       font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",sans-serif; }
h1 { font-size:1.4rem; margin:0 0 .25rem; letter-spacing:-.01em; }
.sub { color:var(--dim); margin:0 0 2rem; font-size:.9rem; }
.brief { background:#fff; border:1px solid var(--line); border-radius:6px; padding:1rem 1.25rem;
         margin-bottom:2rem; white-space:pre-wrap; font-size:.9rem; }
.step { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); gap:1.5rem;
        background:#fff; border:1px solid var(--line); border-radius:6px; padding:1.25rem;
        margin-bottom:1.25rem; }
@media (max-width:900px){ .step { grid-template-columns:1fr; } }
.step img { width:100%; height:auto; border-radius:4px; border:1px solid var(--line);
            background:#111; display:block; }
.none { padding:3rem 1rem; text-align:center; color:var(--bad); border:1px dashed var(--bad);
        border-radius:4px; font-size:.9rem; }
.head { display:flex; align-items:baseline; gap:.75rem; margin-bottom:.5rem; }
.n { font-weight:600; }
.score { font-variant-numeric:tabular-nums; font-weight:600; }
.score.hi { color:var(--good); } .score.lo { color:var(--bad); }
.verdict { margin:.25rem 0 .9rem; }
h3 { font-size:.72rem; text-transform:uppercase; letter-spacing:.07em; color:var(--dim);
     margin:1rem 0 .35rem; }
ul { margin:0; padding-left:1.1rem; } li { margin-bottom:.3rem; font-size:.88rem; }
li.probe { color:var(--bad); }
pre { background:#f4f2ef; border:1px solid var(--line); border-radius:4px; padding:.6rem .8rem;
      overflow-x:auto; font-size:.78rem; margin:.3rem 0 0; }
footer { color:var(--dim); font-size:.85rem; margin-top:2rem; border-top:1px solid var(--line);
         padding-top:1rem; }
"""


def _img(path: str | None) -> str:
    """Inline the render so the page is one self-contained file."""

    if not path:
        return '<div class="none">nothing rendered</div>'
    source = Path(path)
    if not source.is_file():
        return '<div class="none">render missing</div>'
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f'<img alt="render" src="data:image/png;base64,{encoded}">'


def _items(values: list[str], css: str = "") -> str:
    if not values:
        return '<p style="color:var(--dim);font-size:.88rem;margin:.2rem 0">none</p>'
    cls = f' class="{css}"' if css else ""
    return "<ul>" + "".join(f"<li{cls}>{html.escape(v)}</li>" for v in values) + "</ul>"


def write_sheet(brief: str, attempts: list[Any], destination: Path, *, model: str) -> Path:
    """Render the contact sheet and return where it was written."""

    rows = []
    for attempt in attempts:
        data = attempt if isinstance(attempt, dict) else asdict(attempt)
        score = data.get("score")
        shown = "n/a" if score is None else str(score)
        tone = "hi" if isinstance(score, int) and score >= 85 else "lo"
        stderr = data.get("stderr") or ""
        rows.append(
            f"""<section class="step">
  <div>{_img(data.get("image"))}</div>
  <div>
    <div class="head"><span class="n">attempt {data.get("index")}</span>
      <span class="score {tone}">{shown}</span></div>
    <p class="verdict">{html.escape(str(data.get("verdict") or ""))}</p>
    <h3>defects the critic saw</h3>{_items([str(d) for d in data.get("defects") or []])}
    <h3>defects the scene report saw</h3>
    {_items([str(d) for d in data.get("probe_defects") or []], "probe")}
    <h3>next actions</h3>{_items([str(a) for a in data.get("next_actions") or []])}
    {f"<h3>blender stderr</h3><pre>{html.escape(stderr[:1200])}</pre>" if stderr else ""}
  </div>
</section>"""
        )

    scores = [a.get("score") if isinstance(a, dict) else a.score for a in attempts]
    scores = [s for s in scores if isinstance(s, int)]
    best = max(scores) if scores else None
    last = attempts[-1] if attempts else None
    spent = (last.get("cost_usd") if isinstance(last, dict) else last.cost_usd) if last else 0.0

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>scene agent run</title><style>{CSS}</style></head><body>
<h1>Scene agent run</h1>
<p class="sub">{len(attempts)} attempts &middot; best score {best if best is not None else "n/a"}
 &middot; {html.escape(model)} &middot; ${spent:.4f}</p>
<div class="brief">{html.escape(brief)}</div>
{"".join(rows)}
<footer>Each attempt shows the render the critic saw and the scene-graph report it saw alongside it.
The two channels catch different failures: an image cannot show a mesh with no faces, and a report
cannot show a camera pointed at the back of the instrument.</footer>
</body></html>""",
        encoding="utf-8",
    )
    return destination
