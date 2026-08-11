# Writing conventions

## Register

OpenSDL's prose is written for a working scientist or engineer evaluating whether to build a
laboratory on this framework, and for the agents that will operate one. It states what the software
does and what it does not, in specific terms, and it declines to sell. Claims carry the evidence
that supports them or say plainly that the evidence is missing.

## Audience

- Someone arriving at the repository cold, deciding in a few minutes whether it is real.
- A laboratory owner deciding what to depend on, who needs the limits stated before the features.
- An agent operating a laboratory, which needs instructions it can follow without inferring intent.

## Conventions already recorded elsewhere

`AGENTS.md` governs repository structure, architecture rules, and the definition of a complete
change. `.agents/skills/` holds the recurring procedures. Neither is restated here.

---

## Lead the README with the image

**Rule:** The root README carries one hero image immediately after the title and badges, above the
first prose section. A reader should not have to scroll to see what the framework produces. Images
that illustrate a specific section stay in that section; the hero is separate from them and is not
a duplicate of one.
**Scope:** `README.md` at the repository root, and the README of any example that ships a rendered
artifact.
**Origin:** 2026-08-11 — the repository's only image sat at line 113 of 173, below five sections of
prose, and had to be scrolled to.

## Show the run, not the machine

**Rule:** When a published image can show the framework doing something, prefer it to a portrait of
the equipment. A still of a cell says a scene was modelled; a frame of a campaign mid-search says
the loop closes. State in the caption that the image was generated from a recorded run, when it was.
**Scope:** Hero and section images in `README.md` and example READMEs.
**Origin:** 2026-08-11 — the front door led with a static render of the reference cell while a frame
of an actual campaign existed.

## Size an image for where it is read

**Rule:** Deliver a rendered artifact at the width it is displayed at, not at the largest width it
can be produced at. An oversized file is resampled by whatever displays it, and that resampling is
what makes type look soft. Supersample during generation, then resample down to the delivery size.
**Scope:** Any rendered image committed to the repository or published from it.
**Origin:** 2026-08-11 — a 3840px frame read as blurry everywhere it was viewed; the same frame
resampled to 1920px read sharp.
