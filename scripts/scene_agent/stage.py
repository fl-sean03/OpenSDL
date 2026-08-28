"""Build a scene one addition at a time, rendering after each.

A whole workcell in one prompt does not work. Measured against four models, a brief describing a
bench, an arm, two hotels, a reader, a shaker and their materials exhausts the completion budget in
reasoning and returns nothing, while a brief describing a bench alone answers in about thirty
seconds. The difference is not the length of the script; it is how much has to be held at once.

So the scene is assembled the way `examples/digital-twin-surrogate/scene/build_scene.py` is
organised: a base, then one body at a time, each in its own function, each verifiable on its own.
Every stage receives the working script and adds exactly one thing, and the render after each stage
localises the blame. When an arm comes out wrong, it is the arm that is wrong, not the scene.

A failed stage is retried on its own rather than restarting the build, because the cost of a stage
is one call and the cost of a restart is all of them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .client import CRITIC_MODEL, GENERATOR_MODEL, ask, fenced_python
from .loop import SYSTEM, _strings, critique
from .render import render_script

STAGE_SYSTEM = (
    SYSTEM
    + """

You are extending a script that already works. Return the COMPLETE script with your addition
folded in, in one fenced python block. Keep everything that is already there, keep the names it
already uses, and change nothing you were not asked to change. Organise each body into its own
function so the script stays readable as it grows."""
)


@dataclass
class Stage:
    """One addition, and how it went."""

    name: str
    instruction: str
    attempts: int = 0
    ok: bool = False
    score: int | None = None
    verdict: str = ""
    defects: list[str] = field(default_factory=list)
    probe_defects: list[str] = field(default_factory=list)
    stderr: str = ""
    image: str | None = None
    meshes: int = 0
    cost_usd: float = 0.0


def build(
    base_instruction: str,
    stages: list[tuple[str, str]],
    out_dir: Path,
    *,
    retries: int = 2,
    look_bar: int = 70,
    model: str = GENERATOR_MODEL,
    critic_model: str = CRITIC_MODEL,
    key: str | None = None,
    width: int = 1280,
    height: int = 720,
    samples: int = 128,
    engine: str = "CYCLES",
    blender: str | None = None,
) -> tuple[str, list[Stage]]:
    """Assemble the scene stage by stage. Returns the final script and the record of each stage."""

    out_dir.mkdir(parents=True, exist_ok=True)
    script = ""
    record: list[Stage] = []
    spent = 0.0

    todo = [("base", base_instruction), *stages]
    for index, (name, instruction) in enumerate(todo):
        step_dir = out_dir / f"{index:02d}-{name}"
        step_dir.mkdir(parents=True, exist_ok=True)
        stage = Stage(name=name, instruction=instruction)
        last_error = ""

        for attempt in range(1, retries + 2):
            stage.attempts = attempt
            if script:
                prompt = (
                    f"CURRENT SCRIPT\n```python\n{script}\n```\n\n"
                    f"ADD THIS, changing nothing else:\n{instruction}"
                )
                if last_error:
                    prompt += (
                        f"\n\nYour previous attempt failed to run. Fix it.\n{last_error[:1500]}"
                    )
            else:
                prompt = instruction
                if last_error:
                    prompt += (
                        f"\n\nYour previous attempt failed to run. Fix it.\n{last_error[:1500]}"
                    )

            reply = ask(
                [
                    {"role": "system", "content": STAGE_SYSTEM if script else SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                key=key,
            )
            spent += reply.cost_usd
            candidate = fenced_python(reply.text)

            outcome = render_script(
                candidate,
                step_dir,
                blender=blender,
                width=width,
                height=height,
                engine=engine,
                samples=samples,
            )
            blocking = [d for d in outcome.defects if not d.startswith("engine ")]
            if outcome.ok and not blocking:
                # Structurally sound. Now ask whether it looks like what was asked for, which is
                # the question the probe cannot reach: it counted six meshes, all in frame, no
                # defects, on a render where every surface came out white against a brief that
                # said matte dark grey.
                judgement, critic_reply = critique(
                    instruction, outcome, model=critic_model, key=key
                )
                spent += critic_reply.cost_usd
                raw = judgement.get("score")
                stage.score = int(raw) if isinstance(raw, (int, float)) else None
                stage.verdict = str(judgement.get("verdict", ""))
                stage.defects = _strings(judgement.get("defects"))

                good_enough = stage.score is None or stage.score >= look_bar
                if good_enough or attempt > retries:
                    script = candidate
                    stage.ok = True
                    stage.image = str(outcome.image)
                    stage.probe_defects = outcome.defects
                    meshes = outcome.report.get("meshes")
                    stage.meshes = int(meshes) if isinstance(meshes, int) else 0
                    break

                actions = _strings(judgement.get("next_actions"))
                last_error = (
                    f"It rendered, but a reviewer scored it {stage.score}/100: {stage.verdict}\n"
                    f"Defects: {json.dumps(stage.defects, indent=1)}\n"
                    f"Do this: {json.dumps(actions, indent=1)}"
                )
                stage.stderr = last_error
                continue
            # A render that ran is not a render that shows anything. Blocking defects carry the
            # structural failures an image cannot report and, since the framing check landed, the
            # one an image reports loudest: a camera pointed at nothing.
            if outcome.ok and blocking:
                last_error = "The script ran and rendered, but: " + "; ".join(blocking)
            else:
                last_error = outcome.stderr or "; ".join(outcome.defects)
            stage.stderr = last_error
            stage.probe_defects = outcome.defects

        stage.cost_usd = spent
        record.append(stage)
        (step_dir / "scene.py").write_text(script or "", encoding="utf-8")
        (step_dir / "stage.json").write_text(json.dumps(asdict(stage), indent=2), encoding="utf-8")

        if not stage.ok:
            break

    if script:
        (out_dir / "scene.py").write_text(script, encoding="utf-8")
    (out_dir / "stages.json").write_text(
        json.dumps([asdict(s) for s in record], indent=2), encoding="utf-8"
    )
    return script, record


#: The workcell, decomposed. Each entry is one body, in the order that makes the render legible
#: as it grows: the room, then the surface, then the things on it, then the thing that moves.
WORKCELL_BASE = """Build a Blender 5.2 scene of an empty laboratory bench, ready for instruments.

- a matte dark-grey bench top 1.8 m wide, 0.8 m deep, 40 mm thick, its top surface at 0.9 m
- four square steel legs at the corners, 50 mm section
- a large floor plane in light neutral grey
- a camera at three-quarter view from the front-left, about 1.6 m high and 3.2 m from the bench
  centre, framing the whole bench with headroom, and set it as the scene camera
- a soft area key light from the front-left about 3 m up, a cooler dimmer area fill from the right,
  and a weak world ambient so shadows are not black

Use metres. Give the bench a slightly rough dark material and the floor a matte light one."""

WORKCELL_STAGES: list[tuple[str, str]] = [
    (
        "plate-reader",
        "Add a plate reader on the left third of the bench top: a matte dark polymer box "
        "0.45 m wide, 0.35 m deep, 0.25 m tall, with a shallow horizontal slot across the front "
        "for a loading drawer and a slightly recessed darker front panel. No text or logos.",
    ),
    (
        "shaker",
        "Add an orbital shaker on the right third of the bench top: a low matte dark base "
        "0.30 x 0.30 x 0.09 m, with a light grey platform on top and four small corner clamps. "
        "Place one microplate on the platform, 127.76 x 85.48 x 14 mm, light grey, with a shallow "
        "recessed grid of 96 wells in 8 rows and 12 columns on its upper face.",
    ),
    (
        "hotels",
        "Add two plate hotels, one at each rear corner of the bench top: an open vertical rack of "
        "thin steel uprights 0.5 m tall holding eight microplates in a stack with about 20 mm "
        "clearance between them. Reuse the microplate geometry already in the script.",
    ),
    (
        "arm",
        "Add a six-axis robot arm at the centre-rear of the bench top, roughly 0.7 m reach, in "
        "brushed aluminium. Build it as a real kinematic chain: a cylindrical base, a shoulder "
        "yoke, an upper arm, a forearm, a wrist, and a two-finger parallel gripper. Pose it "
        "mid-transfer, leaning forward and to the left, with the gripper closed on a microplate "
        "held level about 0.25 m above the bench. The plate must sit between the fingers with the "
        "fingers touching its short edges.",
    ),
]
