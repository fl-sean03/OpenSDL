"""Run several independent lineages at once and keep the best one.

A single refine chain is a hill climb from wherever the first attempt happened to land, and the
first attempt is the least informed thing the model will ever produce. Running lineages in parallel
turns that into a search: each starts from its own generation, iterates on its own critique, and the
best surviving render wins.

This is only sensible because the model is cheap. A full lineage costs a fraction of a cent, so
eight of them cost less than one frontier-model call and finish in the time the slowest one takes
rather than the sum. The wall clock is dominated by Blender, not by tokens, so the useful width is
roughly the core count.

The second round is where it earns its keep: the winning script is handed to every lineage as a
starting point, with its own critique attached, so the next generation begins from the best thing
found rather than from the brief again.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .client import GENERATOR_MODEL
from .loop import Attempt, run

#: Beyond this the Blender processes contend and everything gets slower together.
DEFAULT_WIDTH = 6


def _best(attempts: list[Attempt]) -> Attempt | None:
    """The highest-scoring attempt that actually rendered."""

    scored = [a for a in attempts if a.ok and a.score is not None]
    return max(scored, key=lambda a: a.score or 0) if scored else None


def race(
    brief: str,
    out_dir: Path,
    *,
    lineages: int = DEFAULT_WIDTH,
    iterations: int = 4,
    rounds: int = 2,
    target_score: int = 88,
    model: str = GENERATOR_MODEL,
    key: str | None = None,
    width: int = 1280,
    height: int = 720,
    samples: int = 256,
    engine: str = "CYCLES",
) -> dict[str, Any]:
    """Search for a scene, widthways then depthwise. Returns a summary of what was found."""

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief.md").write_text(brief, encoding="utf-8")

    champion: Attempt | None = None
    history: list[dict[str, Any]] = []
    seed_note = ""

    for round_index in range(1, rounds + 1):
        round_dir = out_dir / f"round-{round_index}"
        prompt = brief + seed_note

        def one(index: int, directory: Path = round_dir, text: str = prompt) -> list[Attempt]:
            return run(
                text,
                directory / f"lineage-{index}",
                iterations=iterations,
                target_score=target_score,
                model=model,
                key=key,
                width=width,
                height=height,
                samples=samples,
                engine=engine,
            )

        results: list[list[Attempt]] = []
        with ThreadPoolExecutor(max_workers=lineages) as pool:
            futures = {pool.submit(one, i): i for i in range(1, lineages + 1)}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    history.append(
                        {"round": round_index, "lineage": futures[future], "error": str(exc)}
                    )

        for attempts in results:
            best = _best(attempts)
            if best is None:
                continue
            history.append(
                {
                    "round": round_index,
                    "score": best.score,
                    "attempts": len(attempts),
                    "image": best.image,
                }
            )
            if champion is None or (best.score or 0) > (champion.score or 0):
                champion = best

        if champion is None:
            break
        if (champion.score or 0) >= target_score:
            break

        seed_note = (
            "\n\n---\nA previous attempt scored "
            f"{champion.score}/100 and was judged: {champion.verdict}\n"
            f"Its remaining defects were:\n{json.dumps(champion.defects, indent=1)}\n\n"
            "Start from this script and fix those defects. Do not start over.\n"
            f"```python\n{champion.script}\n```"
        )

    summary = {
        "champion_score": champion.score if champion else None,
        "champion_image": champion.image if champion else None,
        "rounds_run": round_index if champion else 0,
        "lineages": lineages,
        "history": history,
    }
    if champion is not None:
        (out_dir / "champion.py").write_text(champion.script, encoding="utf-8")
        (out_dir / "champion.json").write_text(
            json.dumps(asdict(champion) | {"script": "champion.py"}, indent=2), encoding="utf-8"
        )
    (out_dir / "race.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
