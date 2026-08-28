"""The iterate-until-it-looks-right loop.

One pass is: write a Blender script, render it headlessly, look at the render, say what is wrong,
rewrite. The loop ends when the critic scores the image at or above the bar, or when the attempts
run out.

Two things make this more than a chat transcript.

The critic sees the render **and** the structured probe report from the same attempt. Those two
channels fail differently and neither subsumes the other: an image cannot show a mesh with no faces
or a non-finite transform, and a report cannot show that the camera is pointing at the back of the
instrument. `examples/digital-twin-surrogate/scene/check_scene.py` records the same finding from the
other direction, which is why both are always in the prompt.

And every attempt is kept — script, render, critique, cost. The run directory is the artifact. A
loop whose intermediate states are thrown away cannot be debugged, and cannot show anybody how the
scene got where it got.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .client import CRITIC_MODEL, GENERATOR_MODEL, Reply, ask, fenced_python, image_part
from .render import RenderOutcome, render_script

SYSTEM = """You author Blender 5.2 Python scripts that build a scene from nothing.

Rules that are not negotiable:
- Emit ONE fenced ```python block and nothing else. No commentary outside it.
- Start from `bpy.ops.wm.read_factory_settings(use_empty=True)`. The scene begins empty.
- Build geometry procedurally. You have no asset library, no external files, no network.
- Create a camera, set `bpy.context.scene.camera`, and light the scene. A render with no camera or
  no light is a black rectangle and scores zero.
- Do NOT set `scene.render.filepath`, resolution, engine, or call `bpy.ops.render.render`. The
  harness appends all of that. Setting it yourself will be overwritten.
- Blender 5.2's render engines are BLENDER_EEVEE, BLENDER_WORKBENCH and CYCLES. BLENDER_EEVEE_NEXT
  does not exist here.
- Prefer real dimensions in metres. A bench is about 0.9 m tall, a microplate is 127.76 x 85.48 mm.

You are judged on what the render looks like, so composition, materials and lighting are part of the
job, not decoration.

These helpers are ALREADY DEFINED above your script. Use them. Do not redefine them, and do not
import bpy primitives to do what they do — each exists because hand-rolling it has failed before.

    new_scene()                                  empty scene WITH a world, returns the scene
    ambient(strength=0.1, color=(r,g,b))         world light; keep strength 0.05-0.2
    material(name, color, roughness, metallic)   Principled material
    palette()                                    dict of measured preset materials, keyed:
                                                 bench 0.090  polymer 0.055  steel 0.420 metallic
                                                 aluminium 0.560 metallic   floor 0.300
                                                 labware 0.620   glass 0.800
    lab_lighting(target, cam)                    three-point rig placed off the CAMERA axis
    box(name, (x,y,z), location, material_)      box of that size in metres, centred on location
    cylinder(name, radius, depth, location, m)   upright cylinder
    plane(name, size, location, material_)       flat square, for floors
    bench(name, width, depth, top_z=0.90,        a whole bench: top placed by its SURFACE height,
          top_material=, leg_material=)          legs reaching up into it. Use this, do not build
                                                 a bench out of boxes
    on_surface(name, (x,y,z), (cx,cy), surf_z,   a body standing ON a surface, sunk 2 mm so it
               material_)                        does not z-fight. USE THIS for anything on the
                                                 bench: it computes the height for you
    aim(obj, target)                             point an object's -Z at a point
    camera(location, target, lens=42.0)          camera looking at target, set as scene camera
    frame_all(cam)                               pull the camera back until everything fits
    area_light(name, location, target, energy,   area light aimed at a point
               size, color)

Start with `scene = new_scene()`. Build bodies with `box`, `cylinder` and `plane`. Frame with
`cam = camera(...)` then `frame_all(cam)` as the last thing before lighting: it measures what you
actually built and pulls back until none of it is cropped. Never write rotation_euler by hand.
Then `lab_lighting(target, cam)` LAST, after framing, passing the camera it returned. The rig
places itself relative to the view axis so the light always models the form; lighting chosen in
world space lands frontally as often as not and the render comes out flat.

**A detail placed inside a solid body is invisible.** A slot modelled as its own box, positioned
within the housing, renders as nothing and the instrument comes out a featureless block. To show a
recess, either stand the detail 1-2 mm PROUD of the face in a darker material, or build the housing
as panels around the opening. Never bury a mesh inside another.

Where two bodies meet, **sink one a few millimetres into the other**. Surfaces that end at exactly
the same height and overlap in plan will z-fight into flickering dark squares. A bench leg should
reach up *into* the bench top, and every instrument on the bench goes through `on_surface`, which
handles this and computes the height so you never write `surface_z + height/2` by hand.

**Use the presets. They are measured, and guessed values keep coming out wrong.**

    p = palette()          bench, polymer, steel, aluminium, floor, labware, glass
    lab_lighting(target)   the whole three-point rig, exposed correctly

A swatch ramp was rendered to calibrate these. The finding worth knowing: the FLOOR dominates. At
0.55 albedo it bounces so much light that even a 0.03 surface reads mid-grey and nothing can look
dark. `p['floor']` is 0.30 for that reason. Do not brighten it.

**Take the material from `p`, do not write your own for a surface it already covers.** The albedos
above are what those words mean in this rig. A bench top written as 0.15 because it sounds like
dark grey renders as mid grey and gets marked down for it — that has happened, twice. If you need
something the palette lacks, keep it in the same range: matte dark polymer lives near 0.05, painted
metal near 0.35, anything meant to read white near 0.65.

**Lighting numbers, if you override the rig.** The harness renders with the Standard
view transform, so there is no filmic roll-off to hide an overexposed scene. A measured failure: an
800 W key at 2.8 m over 0.2-albedo surfaces put 48% of the frame at pure white.

    key   area_light(..., energy=80-150,  size=1.0-1.5)
    fill  area_light(..., energy=20-40,   size=1.0, cooler colour, opposite side)
    world ambient(strength=0.05-0.2)

Aim for real blacks, real whites, and most of the image between them.

Group each assembly into its own function so the script stays readable as it grows.
"""

CRITIC_SYSTEM = """You judge a rendered Blender scene against a brief, and you are hard to please.

Reply with ONE fenced ```json block:
{"score": 0-100, "verdict": "...", "defects": ["..."], "next_actions": ["..."]}

`score` is how well the render satisfies the brief: 0 is unusable, 60 is recognisable but crude, 80
is a credible technical illustration, 95 is publishable.
`defects` names what is actually wrong, each one specific enough to fix. "improve the lighting" is
useless. "the key light is behind the camera so every surface is flat and the form reads as a
silhouette" is useful.
`next_actions` are concrete script-level changes, in priority order, at most five.

You will be given the render AND a structured report of the scene graph. Use both. If the report
shows a defect the image cannot reveal, say so. If the image shows a problem the report cannot see,
say that too."""


@dataclass
class Attempt:
    """One pass through the loop, kept whole so the run can be replayed and shown."""

    index: int
    script: str
    ok: bool
    score: int | None = None
    verdict: str = ""
    defects: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    probe_defects: list[str] = field(default_factory=list)
    stderr: str = ""
    image: str | None = None
    cost_usd: float = 0.0


def _json_block(text: str) -> dict[str, object]:
    """The first JSON object in a reply, fenced or bare."""

    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    body = fenced.group(1) if fenced else text
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strings(value: object) -> list[str]:
    """A model may return a string, a list, or nothing where a list was asked for."""

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _report_digest(outcome: RenderOutcome) -> str:
    """The probe report, trimmed to what a critic can act on."""

    report = dict(outcome.report)
    objects = report.get("objects")
    if isinstance(objects, list) and len(objects) > 40:
        report["objects"] = objects[:40]
        report["objects_truncated"] = f"{len(objects) - 40} more not shown"
    return json.dumps(report, indent=1)[:6000]


def generate(
    brief: str, *, model: str = GENERATOR_MODEL, key: str | None = None
) -> tuple[str, Reply]:
    """First attempt, from the brief alone."""

    reply = ask(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Build this scene.\n\n{brief}"},
        ],
        model=model,
        key=key,
    )
    return fenced_python(reply.text), reply


def critique(
    brief: str, outcome: RenderOutcome, *, model: str = CRITIC_MODEL, key: str | None = None
) -> tuple[dict[str, object], Reply]:
    """Judge one render, with the image and the scene report both in the prompt."""

    content: list[dict[str, object]] = [
        {
            "type": "text",
            "text": (
                f"BRIEF\n{brief}\n\nSCENE REPORT\n{_report_digest(outcome)}\n\n"
                "Judge the attached render against the brief."
            ),
        }
    ]
    if outcome.image is not None:
        content.append(image_part(outcome.image))
    else:
        content[0]["text"] = str(content[0]["text"]) + (
            f"\n\nNOTHING RENDERED. Blender said:\n{outcome.stderr[:2000]}\n"
            "Score this 0 and make next_actions the fix."
        )

    reply = ask(
        [
            {"role": "system", "content": CRITIC_SYSTEM},
            {"role": "user", "content": content},
        ],
        model=model,
        key=key,
    )
    return _json_block(reply.text), reply


def refine(
    brief: str,
    script: str,
    judgement: dict[str, object],
    outcome: RenderOutcome,
    *,
    model: str,
    key: str | None,
) -> tuple[str, Reply]:
    """Rewrite the script to answer the critique. The whole script comes back, never a patch."""

    defects = _strings(judgement.get("defects"))
    actions = _strings(judgement.get("next_actions"))
    instruction = (
        f"BRIEF\n{brief}\n\n"
        f"YOUR PREVIOUS SCRIPT\n```python\n{script}\n```\n\n"
        f"WHAT IS WRONG\n{json.dumps(defects, indent=1)}\n\n"
        f"WHAT TO DO\n{json.dumps(actions, indent=1)}\n\n"
        f"SCENE REPORT FROM THAT ATTEMPT\n{_report_digest(outcome)}\n\n"
        "Return the COMPLETE corrected script in one fenced python block. Keep what worked."
    )
    if outcome.stderr:
        instruction += f"\n\nBLENDER STDERR\n{outcome.stderr[:1500]}"

    reply = ask(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": instruction}],
        model=model,
        key=key,
    )
    return fenced_python(reply.text), reply


def run(
    brief: str,
    out_dir: Path,
    *,
    iterations: int = 6,
    target_score: int = 85,
    model: str = GENERATOR_MODEL,
    critic_model: str = CRITIC_MODEL,
    key: str | None = None,
    blender: str | None = None,
    width: int = 1280,
    height: int = 720,
    engine: str = "CYCLES",
    samples: int = 256,
    on_step: object = None,
) -> list[Attempt]:
    """Drive the loop and leave every attempt on disk. Returns the attempts in order."""

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief.md").write_text(brief, encoding="utf-8")

    attempts: list[Attempt] = []
    script, reply = generate(brief, model=model, key=key)
    spent = reply.cost_usd

    for index in range(1, iterations + 1):
        step_dir = out_dir / f"{index:02d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        (step_dir / "scene.py").write_text(script, encoding="utf-8")

        outcome = render_script(
            script,
            step_dir,
            blender=blender,
            width=width,
            height=height,
            engine=engine,
            samples=samples,
        )
        judgement, critic_reply = critique(brief, outcome, model=critic_model, key=key)
        spent += critic_reply.cost_usd

        raw_score = judgement.get("score")
        attempt = Attempt(
            index=index,
            script=script,
            ok=outcome.ok,
            score=int(raw_score) if isinstance(raw_score, (int, float)) else None,
            verdict=str(judgement.get("verdict", "")),
            defects=_strings(judgement.get("defects")),
            next_actions=_strings(judgement.get("next_actions")),
            probe_defects=outcome.defects,
            stderr=outcome.stderr,
            image=str(outcome.image) if outcome.image else None,
            cost_usd=spent,
        )
        attempts.append(attempt)
        (step_dir / "critique.json").write_text(
            json.dumps(asdict(attempt) | {"script": "see scene.py"}, indent=2), encoding="utf-8"
        )
        if callable(on_step):
            on_step(attempt)

        if attempt.score is not None and attempt.score >= target_score:
            break
        if index == iterations:
            break

        script, refine_reply = refine(brief, script, judgement, outcome, model=model, key=key)
        spent += refine_reply.cost_usd

    (out_dir / "run.json").write_text(
        json.dumps([asdict(a) | {"script": f"{a.index:02d}/scene.py"} for a in attempts], indent=2),
        encoding="utf-8",
    )
    return attempts
