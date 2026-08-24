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

**Two worked reference designs.** The domain search produced two facility architectures that are
worth keeping even though both ventures were falsified. They are the concrete form of the list above,
researched to real instruments, real costs and real wall-clock.

*Elastocaloric alloys.* Nine steps from melt to regenerator assembly. Differential scanning
calorimetry answers in **15 minutes at $10 a sample**; functional fatigue to 10⁸ cycles takes
**58 days at $15,000-30,000**. That is a **fast/slow ratio of about 5,500**. The contended instruments
are servo-hydraulic and resonant frames, which every fatigue campaign queues on, plus electron
backscatter diffraction, transmission electron microscopy, and a single regenerator rig. Custody runs
melt → work → heat treat → machine → coupon test → tube form → assembly, with a specific ingot heat
traceable through six operations.

*CO2 electrolysis.* **Five decades of timescale in one workflow**: cyclic voltammetry in 10-60
minutes under $5; Faradaic efficiency on a small electrode in 2-6 hours; a 25 cm² membrane assembly
for 100 hours over 4-7 days; 1,000-hour durability at 100 cm² holding a stand for six weeks; then an
8,760-hour qualification occupying one stand for a year. The throughput bottleneck is the gas
chromatography and mass spectrometry product line, which every cell needs continuously.

Both are kept as reference designs for facility shape. Neither is a domain recommendation.

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

**Open. Seven candidates across two shapes have been modelled and falsified.** Each failed on
arithmetic. The negative results are recorded because rediscovering them would cost months, and
because a single mechanism accounts for all seven.

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

**Generation 1's diagnosis.** All three were *a better material for a mature industrial process*. In
a mature process the material axis is the cheapest axis to optimise, so incumbents harvested it
first, over decades, and what remains there is the saturated tail. The shape was changed to require
that **the process does not yet exist**, so that material and process are designed together.

**Generation 2 followed that instruction and produced four more falsifications.**

| Candidate | Materials axis at its physical ceiling | The architecture that beat it, with no discovery |
|---|---|---|
| Elastocaloric cooling | +25-45% device COP; closes 4-13% of the gap to vapour compression | R-290 propane at $2/kg, +3% COP, full regulatory compliance |
| CO2 or CO to ethylene | thermodynamic floor of 13,183 kWh/t | the BASF/SABIC/Linde electric cracker, running since April 2024 at 1,875-4,286 kWh/t |
| On-site hydrogen peroxide | $40-99/t | Solvay deleting one distillation column, worth $500-1,000/t |
| Direct propylene epoxidation | 11.6% cost share on the proponents' own arithmetic | Sumitomo's process, already cheaper on those same prices |

The elastocaloric case is the sharpest. Take the material to *both* of its physical ceilings — zero
hysteresis and transformation stress at the superelastic floor — and device coefficient of
performance improves 25-45%. Parity with vapour compression requires **355-614%**. Between 58 and
73% of the loss is pumps, friction, regenerator and heat leak. It is a mechanical engineering
programme with a materials input.

**The unified diagnosis, which is the actual result of five months of this.**

> In all seven candidates, a process-architecture change on the same cost line beat the materials
> discovery — including in the two where the process genuinely did not yet exist.

The mechanism is structural. **Value that takes the form of reducing a loss is bounded below by zero
loss, so it always saturates.** The incumbent has owned that cost line for decades and can move
architecture far more cheaply than materials, so the cheap part is already gone. Four of the seven
show the value function explicitly as `1 - x_ref/x`; a fifth shows it as the algebraically identical
reciprocal sum `1/V = Σ 1/v_i`.

Generation 2's instruction was necessary and insufficient, because it named the wrong noun. **A new
process delivering an old product inherits the old product's saturated cost line intact.** Every one
of the four obeyed the instruction and every one still chose a domain where the *product* already
exists at industrial scale: cooling at 135 million units a year, ethylene at 200 Mt/y, hydrogen
peroxide at 6.11 Mt/y, propylene oxide at 10 Mt/y.

**The shape for generation 3:**

> The discoverable property must gate whether a product or capability **exists at all**, and not how
> efficiently an existing one is delivered.

Two admissible criteria remain. **(a)** The product cannot currently be made at all, meaning there is
no incumbent article to price against — a product that is merely expensive or dirty does not qualify.
**(d)** A named buyer with a named budget and a named deadline needs something for which no supply
route exists; if the buyer cannot be named, it is not criterion (d). Two criteria are retired: "the
incumbent route is indirect" admits loss-reduction plays by construction and produced three of
generation 2's four failures, and "a capability recently became cheap" describes the search rather
than the value.

One tension has to be resolved explicitly, because leaving it open is what produced the elastocaloric
scissors — 92,148 t/y of demand in a market closed by propane, against 9-230 t/y in the market that
is open. **If the product does not exist there is no world tonnage**, so the tonnage gate applies to a
named substitution or new-demand pool with a named buyer, never to current sales.

**The honest case against this whole approach, which is on the record because it may be right.** A
screen that rejects everything is indistinguishable from a broken screen. These gates are calibrated
on chemicals and energy, where incumbents have had fifty to a hundred years on every cost line that
exists; applied to any mature industrial cost line they will reject everything, because that is what
mature industrial cost lines look like. The screen may be correctly reporting that **no materials
venture of any shape is fundable against a mature industrial cost line** — in which case the search
space has to change, and a fourth shape would not help. Three further objections stand unanswered: seven of seven
were killed by a prosecution with no symmetric defence, and asymmetric adversarial processes converge
on rejection regardless of merit; every kill is a median-case kill, and a screen computing expected
value on medians rejects every venture ever funded; and the exclusion of biology, in force for all
seven, may have removed the answer from the search space before the search began, since a large share
of genuine "cannot be made at all" opportunities now sit at the materials and biology interface.

Generation 3 therefore adds a defence agent arguing each candidate as forcefully as the prosecution
attacks it, with an adjudication between them.

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

*Enforced by:* `tests/test_domain_proposal.py`, which requires a domain proposal to carry a capital
intensity section stating the two numbers above. Whether the numbers are honest is still intent;
whether they were computed at all is now checked. Three modelled ventures exist as comparables.

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

**Four more tests, added after generation 2, in ascending order of cost.** Run them in this order and
stop at the first failure. All seven falsified candidates would have died in under a day, and five of
them in under an hour.

**Test 0 — the value function. Free.** Can the customer buy an article today that performs the same
function, in any form, at any price? If so the value is loss reduction, it saturates, and the
candidate is rejected. Write the value function down. The form `V = C - K/x`, or a reciprocal sum
`1/V = Σ 1/v_i`, is a rejection. The property must enter as a **threshold** — the article exists above
the line and does not exist below it — or **multiplicatively into a quantity nobody currently sells**.

**Test 1 — floor-limited cost. One hour.** When the dominant cost line is a purchased commodity whose
coefficient has a thermodynamic floor, compute floor × price against product price before anything
else. This alone kills a route that is underwater at its own physics limit, and it would have ended
the ethylene candidate before any literature review.

**Test 2 — physics-limit sufficiency. R ≥ 3.** Take the property to its physical ceiling and divide
the improvement it delivers by the improvement required for parity with the **best architecture
available to the incumbent**. Current practice is the wrong benchmark, because the incumbent will
upgrade. The threshold is 3, because every prior candidate near or below 1 lost to an architecture
change, and the margin has to absorb the pioneer-plant penalty: 51% of pioneer process plants never reach 85% of
design capacity, and class-2 estimates come in 1.28× over.

**Test 3 — architecture ratio. A < 0.3.** Divide the value of the best zero-discovery flowsheet change
by the value of the materials axis at its ceiling. **This test has caught seven of seven**, which makes
it the highest-yield screen in the set for the time it takes. Search the flowsheet literature:
debottlenecking, modular plants, electrified heat, an eliminated unit operation, and the licensor
patent record.

**Test 4 — capital benchmarked from outside the field. Half a day.** Never price capital from a
field's own techno-economic analyses, because every field's analyses carry its own aspirations. Price
against the nearest mature technology's demonstrated installed cost. One candidate's literature
assumed $68/kW against a roughly $2,000/kW demonstrated baseline for a strictly harder device — a
factor of thirty, hiding inside peer review.

The related trap, which the para-xylene work names precisely: **the number the literature reports is
often not the number that sets cost.** The field reports gravimetric equilibrium selectivity on powder
against a binary feed. Plant cost is set by volumetric working capacity and mass-transfer rate on a
formed bead in four-component feed with a desorbent present. One material bought 5x selectivity and
paid 39% of its capacity; a nine-formulation dataset spans 55.3 to 88.5 wt% selectivity with a 2.45x
throughput spread that tracks macropore volume, and the most selective sample is not the fastest.
Confirm that the reported measurement is the one that governs cost before treating a literature
record as a prize. Check the **sign** of the correlation between the cheap assay and the expensive
truth in the variable that must change at scale. A correlation that merely exists is insufficient.
One generation-2 candidate had a screen that was worse than useless: selectivity fell with the pressure
the commercial plant would require, so the bench result pointed the wrong way.

*Enforced by:* `tests/test_domain_proposal.py`. A domain proposal is one Markdown file in
[`docs/development/domains/`](domains/index.md), and the suite fails if it omits any screen section,
states the controlled cost share without a percentage, or reports a share below 15%. The para-xylene
candidate at 4.1% would have been rejected by the second check.

A convention-based check has an obvious hole: write the proposal somewhere else and the screen never
runs. That hole is closed at the one place it matters. A third check reads D6 itself, and if this
entry stops reading as open it must link to a proposal file that exists — so a domain choice cannot
be recorded in the decision log without a document the screen has already been applied to.

### D13 — The facility's first deliverable is the predictive bridge

**Decided. It came from the two facility architectures; neither venture survived to contribute it.**

Both domains examined in enough depth to answer the question gave the same answer, and it was the
answer that disqualifies a naive facility:

> **The fast screen does not predict the slow truth, and no validated accelerated protocol exists.**

For elastocaloric alloys, differential scanning calorimetry genuinely predicts adiabatic temperature
change, and an infrared self-heating method genuinely predicts *structural* fatigue to 10⁷ cycles.
Neither predicts *functional* fatigue, which is what actually kills a regenerator, and single-cycle
adiabatic temperature change **overstates the stabilised value by 1.5 to 6 times** (23-38.5 K
measured against 6.6-15.9 K after fatigue). The field's fastest screen also measures the wrong
object: the celebrated 10⁷-cycle result is a sputtered 20 µm film, and **eleven years later no bulk
material reproduces that fatigue life at that temperature change.**

For CO2 electrolysis, a one-hour flow-cell efficiency of 75.9% does not predict a 1,020-hour
membrane-assembly efficiency of 68% at one sixth the current density. Every degradation mode — salt
precipitation, flooding, copper reconstruction, ionomer and membrane decay — is slow and invisible in
an hour. The published literature on accelerated testing for this device is one position paper from
2020 and nothing standardised since.

**A facility that scales the fast screen without the bridge is a machine for generating confident
error at speed.** D6 already lists this as a disqualifying risk for a domain. D13 states the
consequence for the build: **the bridge is the facility's first deliverable, before any discovery
campaign runs.**

Three things follow.

1. **The bridge is measurement science.** It is bounded, schedulable and estimable in a way discovery
   is not. The elastocaloric version is a bulk-coupon assay under 10⁴ cycles calibrated against
   10⁷-cycle behaviour on a formed article; at 20 Hz a 10⁷-cycle point takes 5.8 days, so a 40-point
   calibration set is about eight months on four frames or two months on twenty.
2. **The bridge is a saleable asset on its own.** It is transferable, it serves every participant in
   the field including competitors, and it needs no plant, no offtake and no first-of-a-kind
   financing. D7's qualification-dossier hypothesis is the same idea seen from the commercial side.
3. **It changes what the facility is claimed to do.** The claim "we search faster" is weaker and
   easier to attack than the claim "we built the measurement that makes searching mean anything,"
   and only the second is defensible when the field's own fast screen points the wrong way.

**One uncomfortable finding to keep with it.** Model contribution is largest where it is least needed.
On cheap axes — transformation temperature, latent heat, hysteresis — models do well. On the
expensive axis that decides the outcome, fatigue life scatters by an order of magnitude at fixed
nominal condition, which sits at the bad end of the 2.3-3.5x noise penalty, and each point costs 6 to
58 days. So the realistic acceleration is near the bottom of the published 1.25-6x band **on the axis
that matters**. State that to an investor plainly, because it is the first thing a good one will find.

*Enforced by:* intent, and by D6's existing requirement that a domain answer the
fast-screen-predicts-slow-truth question before adoption. `tests/test_domain_proposal.py` requires
the answer to be present and to state the sign of the correlation.

### D7 — Business model

**Shape decided. The specifics wait on D6, and only the specifics.** The three falsified candidates
were modelled far enough to answer the structural question, and the answer held across all of them,
so it is recorded now.

The four paths, costed side by side on the third candidate:

| Path | Company capital | Expected MOIC | Base-case IRR | Downside |
|---|---|---|---|---|
| Sell the consumable | $80-155M | 2.03x | 5.6% | 0.26x |
| Consumable under instrumented performance contracts | $200-250M | 2.64x | 7.6% | 0.05x |
| Build and own plants | $500-620M | 2.12x | 10.2% | **zero, at 50% probability** |
| **Staged hybrid** | **~$126M** | **4.32x** | **15.1%** | **1.08x** |

Owning plants and selling the consumable have the same expected multiple, and owning demands four
times the capital, six more points of dilution, two more years to revenue, and a downside of zero.
The hybrid wins by roughly 2x on expected value, and it wins in the **bear**
case. Its bull case is only 1.5x the plant-owner's bull case; its failure costs $15M at month 18
where the plant-owner's costs $620M at year 10, and the $15M comes back and is redeployable.

Four rules follow, and none of them depends on which domain D6 lands on:

1. **Keep the consumable.** Licence-only is a weak position and the evidence is specific: GTC
   Technology — a genuine aromatics licensor, its process in more than sixty units, thirty years of
   development, around two hundred staff, roughly $50M of revenue — sold to Sulzer in May 2019 at a
   **$39M enterprise value**. The recurring physical product is where the margin lives.
2. **Buy the reference plant with intellectual property.** A first commercial reference is
   the artefact that cannot be bought and without which nothing else is financeable. Contribute
   licence and materials for carried equity in exactly one unit built on someone else's balance
   sheet. Model the **dilution** the entry percentage will suffer: LanzaTech contributed IP for 30% of the
   Shougang joint venture in 2011 and was diluted to 8.38% as others funded the build.
3. **Prove inside a host's existing facility first.** A capacity revamp borrows the host's feedstock,
   utilities, operators, tankage and offtake, and so has no minimum-scale problem — which is the trap
   that otherwise binds, because the scale at which a first plant is financeable sits below the scale
   at which it works standalone.
4. **Write the hard stop into the financing documents before the work starts.** Pre-commit the
   numeric gates and the decision to stop if they fail. Sunk-cost pressure at the point of committing
   engineering capital is what actually kills these companies, and a gate agreed afterwards is not a
   gate.

Retained from the earlier draft, still untested: tamper-evident provenance produces a **qualification
dossier as a byproduct**, which in a regulatory-replacement market is itself a priced deliverable.
That reframes the offer from "we found a material" to "we found it and can prove how, in a form a
qualifying authority accepts." The second half is the defensible half.

*Enforced by:* intent for the four rules, and by `tests/test_domain_proposal.py` for the inputs they
consume. D11's ownership test decides any proposal to own capital; D12's cost-share screen runs
before it.

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
5. **Partial observations that arrive before the measurement finishes.** A capability must be able
   to emit a predicted result with a stated uncertainty from incomplete data, and then revise it
   when the measurement completes. The optimizer must know it received a prediction, act on it, and
   accept the correction without invalidating the campaign. *At one bench this is reading a trend
   after one night of a three-night run.*

**Correction, and it reorders the list.** Items 1, 2 and 4 all treat a slow measurement as a fixed
duration to schedule around. That is the smaller win. Attia et al. (*Nature* 578, 397-402, 2020)
closed a loop on fast-charging protocols by *shortening the measurement itself*: a model predicting
cycle life from the first 100 cycles replaced cycling to failure, and the combined early-prediction
and closed-loop system evaluated 224 protocols in 16 days against roughly 500 days for the exhaustive
alternative. Pipelining around a three-week measurement recovers throughput. Truncating a three-week
measurement to three days recovers an order of magnitude more, and it compounds with the pipelining.

So item 5 outranks items 1, 2 and 4, and it changes what the facility is for. The triage policy in
item 3 and the truncation model in item 5 are the same asset viewed twice: both decide how much
measurement a sample deserves, and both are the part a competitor cannot buy. The framework
obligation is that a capability can report progressively, and that provenance records which
observations were predictions and which were truth, because a campaign built on predictions that were
never corrected is a campaign that cannot be audited.

*Enforced by:* intent, until the work is scheduled. When it is, each addition ships with simulation
and conformance coverage per the architecture rules and demonstrates its one-bench benefit in an
example. The requirement item 5 places on the design: progressive results carry an explicit
`predicted` flag through the evidence store, and attestation reports every prediction as either
resolved to a measurement or unresolved.

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
