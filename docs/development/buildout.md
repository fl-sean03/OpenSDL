# Facility buildout

The canonical plan for the facility-scale program: what has been decided, why, how each decision is
kept from decaying, and what remains open.

## What belongs here

This page is the one to read before doing facility work, and the one to update when a decision
changes. It holds **decisions and their reasoning**, which nothing else in the repository does.

- [The roadmap](roadmap.md) tracks releases. It says what ships.
- [The backlog](backlog.md) tracks framework work items. It says what remains.
- This page tracks the program. It says **what was decided and why**, so a decision survives the
  conversation that produced it.

The distinction matters because of a demonstrated failure here. The
[2026-08-05 audit](audit-2026-08-05.md) is 945 lines of correct analysis whose own header records
that nothing in it has been acted on. A document disconnected from work decays into archaeology.
Every decision below therefore names the mechanism that enforces it, and a decision enforced only
by intention is marked as such, because that is the honest description of its durability.

## Decision log

Each entry carries a status and the thing that would catch its violation. `Enforced by: intent`
means nothing would catch it, which is a standing invitation to find a better mechanism.

### D1 — Facility scale

**Decided.** The next showcase is a laboratory facility. A single cell has already been shown.

A single cell has already been demonstrated and a second one proves nothing new. The interesting
claim is not more throughput; it is that a facility is a *different machine* — see D2.

*Enforced by:* the showcase itself.

### D2 — A facility is not N cells

**Decided.** Facility scale is a qualitative change, and the design must reflect all of it:

- heterogeneous stations, each doing a different thing
- physical samples moving between stations, with custody and genealogy
- contention for shared characterization instruments
- **multiple timescales in one loop** — minutes to weeks — so work has to pipeline
- graceful degradation when one station fails with dozens of experiments in flight
- multi-fidelity triage: screen many, validate some, qualify few
- human technicians as first-class stations for steps that cannot be automated

Every one of these maps onto a primitive the framework already has and has never stressed: capability
contracts, resource leases, lifecycle states and attestation, provenance, and the human-task
adapter. That is the reason to build it.

*Enforced by:* intent, and by D9's framework work failing without it.

### D3 — The 10x claim is decisions per unit time

**Decided.** The capability claim is **experiments that reach a decision** — throughput × yield ×
the fraction producing an attributable, trustworthy measurement. Samples per day is the wrong unit.

Anyone can buy more liquid handlers, so samples per day measures a purchase. Real facilities lose
most of their nominal throughput to samples that are made and never characterized, or characterized
and never correctly attributed. That loss is what provenance actually fixes.

*Enforced by:* the metric must appear in the showcase with a stated baseline. A claim without a
denominator does not ship.

### D4 — Scale invariance: the small case stays first-class

**Decided, and load-bearing.** Facility work must not tax the one-bench case.

The test for any new feature: **does it make the one-bench case better, or merely leave it unharmed?** A
feature that only helps at scale is usually an accident of deployment promoted into the domain
model. All four planned additions in D9 pass this test; anything that
fails it should be redesigned. Gating it behind a flag hides the problem.

The hard constraint: **tier 1 must never require anything from tier 4.**

| Tier | Storage | Process | Manifest |
|---|---|---|---|
| Laptop | SQLite | in-process | ~15 lines, `default_effect: allow` |
| Bench | SQLite | in-process | adapters, real policy, campaigns |
| Cell | SQLite | in-process | resources, twin, viewer |
| Facility | PostgreSQL | multi-process | stations, long-latency work, human stations |

*Enforced by:* `tests/test_minimal_laboratory.py`, which pins the size of the smallest working
manifest and fails when the minimum grows. Growth in the minimum is the observable form of this
decision being violated, and a new required field is a diff anyone can see.

### D5 — The showcase proves the chain

**Decided.** The previous showcase proved a loop closes. That is no longer interesting. This one
proves the chain from discovery to a sellable asset, in three visible beats:

1. the loop finds something a grid search or a human would not have, with the search trace visible
2. the evidence store becomes a qualification package automatically — **including the failed runs**,
   because "what else did you try" is exactly the question provenance answers
3. the customer receives that package, and the material comes with it

Beats 2 and 3 are the differentiation. Nobody is showing them.

*Enforced by:* intent.

### D6 — Target technology domain

**Open. Three candidates have been modelled to completion against adversarial review and
falsified.** Each failed on arithmetic. The negative results are recorded because rediscovering them
would cost months, and because the third one finally explains the first two.

**Falsified: a heavy-rare-earth-free permanent magnet venture.** The thesis was that grain-boundary
engineering could reach high-temperature coercivity without dysprosium or terbium, removing the
largest cost in a Western magnet. The physics is sound — Nd2Fe14B allows about 7.6 T and commercial
magnets deliver 1-2 T, so 70-85% of the bound is unrealised and the deficit is microstructural. The
economics are not. Eliminating heavy rare earth is worth **$9.50/kg on a thin part and $31.92/kg on
a thick one**. The first pass assumed $40-75/kg because it priced bulk alloying; grain-boundary
diffusion already uses a fraction of the terbium. Nobody has ever published the cost of *being*
heavy-rare-earth-free, and at a $10/kg process premium the thin-part case goes negative. Probability
weighted, a Series A returns **2.24x at 10.6% IRR**; even the upside case returns 10.1x, which clears
a growth fund's bar and fails a seed fund's.

**Falsified: a recycling-fed rare-earth separation venture built on a superior extractant.** The
thesis was that separation factor sets stage count, stage count sets plant capital, and so a better
extractant buys a cheaper plant. The first link holds and was validated against a patent running
identical duty on two extractants, agreeing within 10%. The second link does not. Solvent extraction
is 18-30% of plant capital and only part of that scales with stage count; **86% of per-stage volume
is settler, and coalescence sizes it.** The whole capital value of raising the
separation factor from 1.5 to 5 is about **$3/kg of oxide, 1.3% of revenue** — against feedstock
payable moving the same model by $52.6M and the export-control premium by $43.0M. Three further
errors compounded it: the stage-count curve is concave and the target sat on its flat part; the
binding split for magnet feedstock is non-adjacent and already runs at high selectivity; and cheaper
levers exist on the same cost line with no chemistry risk, one patent cutting a cascade 37% using the
same extractant by moving the reflux point. Returns **1.16-1.50x at 2.1-6.0% IRR**.

**Falsified: a step-change adsorbent for para-xylene separation.** The thesis was that an adsorbent
with selectivity near 70, against an incumbent barium-exchanged faujasite at 2-3, would simplify or
replace simulated-moving-bed separation across the ~54 Mt/a of world capacity that runs it. Twelve
agents across two independent passes attacked it from the cost side and the physics side. It fails
four separate ways, and any one of them is sufficient.

*The value saturates, and the saturation is algebraic.* The separation unit is 11.4% of an aromatics
complex, and chambers plus adsorbent charge — everything selectivity can touch — are 42% of that
unit. The remainder is desorbent-recovery distillation, whose size is floored by the back-off from
the equilibrium-theory vertex and is independent of selectivity. The fraction of the total available
prize captured at any selectivity reduces to **1 − α_ref/α**, in which every calibration constant
cancels. At selectivity 10 that is 75%; at 70 it is 96.4%. The whole 2.5 → 70 step is worth **2.4-4.1%
of project capital and $21-26 per tonne of product**. The elasticity of capital cost with respect to
selectivity at 70 is **−0.009**.

*The binding pair is physically inaccessible to the mechanism.* Ethylbenzene, at 14-17% of feed, is
the hard rejection, and para-xylene and ethylbenzene have minimum cross-sections of **6.51 and
6.53 Å**. Every steric or kinetic sieving mechanism capable of producing high selectivity is blind to
that difference. The 2025 record material measures **EB/PX = 2.79 on a real four-component feed — it
prefers ethylbenzene.** Ethylbenzene boils at 136.2 °C against para-xylene at 138.35 °C, so
distillation cannot remove it downstream.

*The headline number has no provenance.* Three independent search passes found **no peer-reviewed
liquid-phase para/meta selectivity near 70**. The best documented values are 4.99, ~17, 27.5 by
vapour-phase IAST, and ~30. Everything above that is para/*ortho* — the easy pair — or a binary
measurement. A selectivity of 70 measured at 298 K and driven by adsorption enthalpy decays to **~17
at the 180 °C operating temperature**. And the incumbent's own equilibrium selectivity was **3.35 in
1972 and 3.26 in 2021**: fifty years in which every gain came from capacity, mass transfer, particle
size, binder elimination and architecture.

*The flowsheet the thesis implies was already built, at the incumbent selectivity.* UOP
commercialised HySorb XP in 1998 — single chamber, light desorbent, single-stage crystallisation —
and published that it "does not provide any cost or performance advantages relative to the Parex
process." Sinopec took **~20% off investment cost** in 2022 with a 16-bed single column, and
commercialised temperature-swing SMB in 2019, both at conventional selectivity. The two largest
capital reductions ever booked in this unit were won by people who own the architecture.

*And a thermodynamic ceiling sits above all of it.* A perfect adsorbent — infinite selectivity, 100%
recovery — shrinks circulation to the separator from 4.368 to 4.237 tonnes per tonne of product, a
**3.0% reduction**, because equilibrated C8 aromatics are ~23% para and that is a property of the
molecule. The isomerisation recycle loop is mandatory at every selectivity.

Returns, probability-weighted over ten years: **2.03x selling adsorbent, 2.12x owning plants, 4.32x
for a staged hybrid**. Base-case IRRs are 5.6%, 10.2% and 15.1%. Owning plants carries the same
expected multiple as selling beds, at four times the capital and a 50% probability of total loss.

**What the three failures have in common, which is the useful result.** Every candidate was *a better
material for a mature industrial process*. In a mature process the material axis is the cheapest axis
to optimise, so incumbents harvested it first, over decades. What remains on that axis is the
saturated tail — and the arithmetic keeps finding exactly that, because it is what is there. This is
a structural property of the search. A fourth candidate of the same shape would produce a fourth
version of the same answer.

The consequence for D6: the domain must be one where **the process does not yet exist**, so the
material and the process are designed together and the material carries the whole value. That is also
where an autonomous laboratory is differentiated. A facility is poor at extracting the last few
percent from a fifty-year optimisation and strong at searching a space nobody has searched, because
the measurement was too expensive to run at scale.

The filter is fixed even though the answer is not:

1. combinatorial **and** not already solved by simulation or ML on existing data
2. loop-closable — real cost and wall-clock numbers per experiment
3. characterization automatable, by a named instrument
4. a named customer with a deadline
5. a survivable qualification timeline
6. legible — a non-expert can see success

Added by D2: the domain must have **genuine multi-step heterogeneity and a fast/slow split**. A
domain where one instrument does everything is now a worse fit, because it would not exercise
facility-scale capability.

The disqualifying risk to check before committing: **does the fast screen actually predict the slow
truth?** A fast proxy that does not predict the real property makes an autonomous lab a machine for
generating confident error at speed. If the answer is no, the domain is rejected however good the
science.

### D11 — Capital intensity caps venture returns

**Decided. It constrains D6 and D7; it does not follow from them.**

Two independently modelled full-stack materials ventures returned 2.24x and 1.16-1.50x. The pattern
is structural: owning the plant means owning the capex, and capex compresses the
multiple. A materials manufacturer can be right about the science, execute well, and still hand the
investor who took the technical risk an outcome that suits a growth fund and misses a seed fund's
bar entirely.

The consequence for this programme is uncomfortable and should not be smoothed: **the instinct toward
vertical integration and the requirement for venture-scale returns pull in opposite directions.**
Integration is the right answer for value *capture* and the wrong answer for *multiple*. Anything
proposed under D6 must be tested against this before the science is evaluated, because a domain that
fails here fails regardless of how good the chemistry is.

**Amended after the para-xylene work, which supplied the missing test.** The earlier form of this
decision said only that capital intensity compresses the multiple. That is too blunt, because owning
capital the discovery makes uniquely cheap is the entire point of a discovery. The test is a
comparison of two numbers on the same denominator:

> **Own the plant when the discovery's value per unit of output exceeds the capital charge per unit
> of output.**

For para-xylene the discovery is worth $21-26 per tonne at its theoretical maximum, and the capital
charge on the tonne that captures it is $82 per tonne. It fails by a factor of three to four, and the
industry it would be bought into runs a four-year mean margin of $304.81/t against a $332/t full-cost
breakeven, with sector ROIC of 3.72% against a 6.22% cost of capital.

The compression is also priced, and the price is public. Chemical (Specialty) trades at **13.36x** and
Chemical (Basic) at **8.57x** (Damodaran, January 2026). Forward integration therefore costs **36% of
enterprise value per dollar of EBITDA and 6.20 points of economic profit**, before any operating
result. That is the cost of the relabelling alone.

*Enforced by:* any future domain proposal carries a returns model with a stated capital intensity
before it is adopted, and states the two numbers above. Three exist now as comparables.

### D12 — Screen the cost share before spending research on a domain

**Decided, and it is the cheapest thing in this document.**

Three deep-research programmes each ran to completion and each died on the same question, asked at
the end when it could have been asked at the start: **what fraction of the paying customer's cost
does the discoverable property actually control?**

| Candidate | The discoverable property | What it controls |
|---|---|---|
| Permanent magnets | heavy-rare-earth-free coercivity | $9.50-31.92/kg of a magnet |
| Rare-earth separation | extractant separation factor | $3/kg of oxide, 1.3% of revenue |
| Para-xylene adsorbents | adsorbent selectivity | 2.4-4.1% of project capital, $21-26/t |

Each number is estimable to an order of magnitude in a few hours from public cost structure, well
before any physics is evaluated. Each would have stopped the programme.

The screen: **compute the controlled cost share first, and reject below roughly 15%.** A property
that governs under a sixth of the payer's cost cannot carry a venture outcome, however good the
science is and however large the market. Market size does not rescue it, because the share is
multiplicative with the market and the arithmetic is the same at every scale.

The related trap, which the para-xylene work names precisely: **the number the literature reports is
often not the number that sets cost.** The field reports gravimetric equilibrium selectivity on powder
against a binary feed. Plant cost is set by volumetric working capacity and mass-transfer rate on a
formed bead in four-component feed with a desorbent present. One material bought 5x selectivity and
paid 39% of its capacity; a nine-formulation dataset spans 55.3 to 88.5 wt% selectivity with a 2.45x
throughput spread that tracks macropore volume, and the most selective sample is not the fastest.
Confirm that the reported measurement is the one that governs cost before treating a literature
record as a prize.

*Enforced by:* a domain proposal states the controlled cost share, with arithmetic, on its first page,
and states which measurement sets cost and whether the cited record is that measurement.

### D7 — Business model

**Open. Owner decision.** The candidates, with the known trade:

- **joint development with an incumbent** — they hold the plant, customers and qualification muscle;
  we hold search speed. Avoids the scale-up wall, caps the upside, makes us a supplier.
- **discover and manufacture** — highest ceiling, and the wall Zymergen hit: a ~$3B valuation and
  world-class automation, killed by a product with no qualified customer that could not scale.
- **discover and license** — low capital, weak position; formulation IP is trade secret more than
  patent.
- **platform** — already what OpenSDL is, and it is open source.

The hypothesis worth testing separately: tamper-evident provenance produces a **qualification
dossier as a byproduct**, which in a regulatory-replacement market is itself a priced deliverable.
That reframes the offer from "we found a molecule" to "we found it and can prove how, in a form a
regulator accepts" — the second half being the defensible half.

### D8 — Scheduler architecture

**Open, and the sharpest tension in D4.** Facility scale wants a persistent process routing work
across stations. The laptop case wants `opensdl run workflow.yaml` with no daemon, no broker, and
nothing running in the background.

Intended resolution: scheduling becomes a strategy behind an interface with an in-process
immediate-dispatch default, in the same shape as the storage layer, where repository interfaces
make PostgreSQL a swap. Named here because "we will just add a small daemon"
is exactly how the small case dies.

### D9 — Framework work the facility requires

**Decided in shape, unscheduled.** Four additions, each of which must satisfy D4:

1. **Long-latency capabilities.** A chamber that legitimately answers in three weeks is not a hung
   instrument. Today a timeout on a non-repeatable capability lands in `intervention_required`,
   which is right for a hung mixer and wrong for a chamber doing its job. "No answer yet" needs to
   be a declared, normal state. *At one bench this fixes the overnight anneal.*
2. **Late-arriving observations.** An observation must be foldable into a campaign whose run
   finished long ago and which has since issued hundreds of proposals. *At one bench this is a
   sample mailed out for external analysis.*
3. **Multi-fidelity as a first-class concept.** A fast screen and a slow truth are different
   measurements of one property, with different cost and trust, and the optimizer must know which
   it received. The triage policy — which sample earns the expensive measurement — is where the
   intellectual value sits and is the part a competitor cannot buy. *At one bench this is a cheap
   check before an expensive one.*
4. **Leases across long durations.** A chamber slot held for weeks stresses lease TTL,
   reconciliation, and controller restart mid-hold.

*Enforced by:* each ships with simulation and conformance coverage, per the architecture rules, and
each must demonstrate its one-bench benefit in an example.

### D10 — Dogfooding does not become facility-only

**Decided.** Building the facility creates pressure for every default, example and document to
assume one. The countermeasure is that the small examples stay alive and exercised.

*Enforced by:* `make showcase` re-derives the `discovering-colors` campaign in CI, so the small
reference cannot silently rot while attention is on the facility. The benchmark suite keeps both a
small laboratory and a facility laboratory, so a change that makes small labs harder to operate
appears as a score drop.

## Standing rules

Durable constraints on all facility work. These are quoted in `AGENTS.md` so a fresh session
inherits them.

1. A laboratory with one instrument stays expressible in about fifteen manifest lines, runnable in
   one process against SQLite, with no scheduler, no broker and no optional service.
2. Facility features are opt-in by configuration, never by requirement.
3. A change that lengthens the minimum manifest needs justifying.
4. Heavy dependencies live behind an extra. `pip install opensdl` stays small.
5. Documentation leads with the small case. The quick start never mentions a station.

An accepted consequence: a feature that would be simple given PostgreSQL and a daemon will take
longer built this way. That is the correct trade while the small case is the adoption path.

## Sequence

Phase boundaries carry the sequence. Each phase ends with something an outsider can check.

**Phase 0 — settle the domain.** Close D6 and D7. Ends with a domain, a named customer, a
loop with real cost and wall-clock numbers, and a written answer to the fast-screen-predicts-slow-
truth question.

**Phase 1 — framework work.** D9 items 1 and 2, each with a one-bench example. Ends with a campaign
that keeps proposing while a three-week measurement is outstanding, demonstrated in simulation.

**Phase 2 — the facility in simulation.** Stations, sample custody, contention, triage — as a
manifest and a simulated laboratory, before any hardware. Ends with a facility that runs end to end
with no physical equipment, which is also the honest way to size the real one.

**Phase 3 — the twin.** The Blender scene of the facility, showing work in progress at every stage
simultaneously. The multi-timescale story is legible at a glance in a way one plate cannot be.

**Phase 4 — the chain.** D5 beats 2 and 3: the evidence store emitting a qualification package,
failed runs included.

**Phase 5 — real hardware.** Per the hardware access research: the first physical instrument, in
whatever domain, closing one real loop.

## Open questions

| # | Question | Blocks | Owner |
|---|---|---|---|
| D6 | Which technology domain | Everything | research, then owner |
| D7 | Business model | The plan's shape | owner |
| D8 | Scheduler architecture | Phase 2 | design |
| — | Does the fast screen predict the slow truth | D6 | research |
| — | Facility capital and staffing | Phase 2 sizing | research |
