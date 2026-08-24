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

## Show the run where the run is the subject

**Rule:** An image of the framework doing something belongs beside the text that describes that
thing, and should say in its caption that it came from a recorded run. It does not displace the
header. The root README's header image is the reference cell, because the first thing a reader needs
is what a laboratory built on this looks like; a campaign frame is evidence for a particular claim
and sits with that claim.
**Scope:** Hero and section images in `README.md` and example READMEs.
**Origin:** 2026-08-11 — the front door led with a static render of the reference cell while a frame
of an actual campaign existed.
**Superseded:** 2026-08-11 — the original rule read "show the run, not the machine" and moved the
campaign frame to the header. Sean reversed it: the cell is the header, and the campaign frame comes
later as an example. The narrower rule above is what survives — prefer the run *where the run is the
subject*. Everywhere was too broad.

## Size an image for where it is read

**Rule:** Deliver a rendered artifact at the width it is displayed at. The largest width it
can be produced at. An oversized file is resampled by whatever displays it, and that resampling is
what makes type look soft. Supersample during generation, then resample down to the delivery size.
**Scope:** Any rendered image committed to the repository or published from it.
**Origin:** 2026-08-11 — a 3840px frame read as blurry everywhere it was viewed; the same frame
resampled to 1920px read sharp.

## Never manufacture emphasis with a contrast

**Rule:** Do not use the formulaic contrast: `X, not Y` · `not X but Y` · `X rather than Y` ·
`X instead of Y` · `less X, more Y` · `it is not X; it is Y`. State the claim and stop. Where the
contrast carries real information, give it its own sentence and say what is actually true of the
rejected option.

The last variant hides from a search for the others, and it survived two passes over the buildout
page. A comparison of two real quantities is fine — moving process architecture genuinely does cost
less than moving materials. The rule is about inventing a foil in order to sound emphatic.

**Why:** The construction invents a strawman to knock down, which reads as emphasis without adding
information. It is one of the most reliable signals of generated prose, and it accumulates: the
first buildout draft carried it in eight decision headings.

**How to fix:** Delete the negated half. `Facility scale, not another cell` becomes `Facility
scale`, and the body explains what was rejected. Where the rejected option genuinely needs stating,
write a second sentence about it.

**Scope:** All prose. Headings especially, where the construction is most tempting and least
informative.
