# Discovering colors

![One round of the campaign: the reference cell's plate shot from above, each well carrying the
color its own run measured, beside the search that produced it](renders/discovering-colors.png)

A closed loop that recovers a dye recipe from its color. The laboratory is given one measured
color and has to find the mixture of cyan, magenta and yellow that reproduces it. It is told
nothing about how the dyes behave, so it has to search.

The frame above is round 2 of the run recorded in `plates.json`, photographed in the reference cell
from `examples/digital-twin-surrogate`. Both halves are generated from that record by the two
scripts below, so it is a picture of a run rather than an illustration of one.

Each round fills a 96-well plate with 96 recipes, reads every well on a simulated colorimeter, and
scores each reading against the target. The optimizer then draws the next round from a region that
has contracted around whatever came closest. Six rounds, 576 wells.

Everything here runs in simulation. No hardware, no network, no model API.

## Run it

```bash
uv run --locked python examples/discovering-colors/run_campaign.py
```

Takes about 80 seconds and prints the recovered recipe with a convergence table:

```
round   region   best ΔRGB   median ΔRGB
    1    1.000       14.02         95.22
    2    0.620       14.15         72.48
    3    0.384       10.37         42.66
    4    0.238        8.35         25.19
    5    0.148        4.52         22.35
    6    0.092        0.50         12.59
```

The target was mixed from `cyan 0.46, magenta 0.09, yellow 0.30`. The campaign gets back
`0.4612, 0.0858, 0.2989` without ever seeing those numbers.

Writes `plates.json`: every recipe, every colorimeter reading, and every score, grouped into the
plates they ran as. Runs, tasks, events and policy decisions land in `.opensdl/opensdl.db`.

## The showcase frame

Two more scripts turn a recorded round into the published image.

```bash
uv run --locked python examples/discovering-colors/render_plate.py  --round 2
uv run --locked python examples/discovering-colors/compose_frame.py --round 2
```

`render_plate.py` photographs the plate from above inside the reference cell from
`examples/digital-twin-surrogate`, giving each well the color its own run measured. It needs
Blender at the version recorded in that scene's node inventory, and it builds in a temporary
directory so the committed scene artifacts stay untouched.

`compose_frame.py` puts that render beside the campaign that produced it: the target against the
closest sample so far, the search space with the region the optimizer is currently drawing from,
error per round, and the tail of the laboratory's event stream. It lays the page out in HTML and
photographs it with headless Chrome. Both write into `renders/`.

Round 2 is the one worth showing. By round 4 the plate has converged to near-uniform teal, which
is the right answer and a dull picture.

The panel only reads rounds up to the one being rendered. A frame of round 2 has no access to
round 3, because when that plate came off the reader, round 3 had not happened.

## What is simulated, and how honestly

The mixing model is Beer-Lambert absorbance over three dye stocks, with the off-diagonal terms
real dyes have: cyan absorbs some green, magenta absorbs some blue. That is what makes the inverse
problem worth searching rather than solving in closed form. Absorbance scales with fill depth, so
the same recipe in a fuller well reads darker.

The colorimeter carries 1.5 counts of Gaussian noise, which is where the error trace flattens. A
noiseless instrument would let the search drive the residual to zero — and prove nothing about
experiments.

Scoring is Euclidean distance in sRGB. A colorimetry laboratory would use ΔE in CIELAB, which is
perceptually uniform; sRGB distance is a stand-in that keeps the example to one existing compute
capability.

## What it exercises

| Piece | Where |
|---|---|
| `sim.mix_dyes` | `adapters/simulated-lab` |
| `ContractingSearch` | `adapters/contracting-search` |
| Candidate constraints | the three dyes cannot exceed the well volume |
| Batch campaigns | 96 candidates per round, one plate |
| Policy, leases, events | `.opensdl/opensdl.db` |

The constraint is doing real work. A recipe asking for more dye than the well holds is refused
before anything is leased or dispensed, and the refused corner is visible in the search-space
chart as the empty triangle above the diagonal.
