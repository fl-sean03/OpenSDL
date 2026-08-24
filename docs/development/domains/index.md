# Domain proposals

A candidate technology domain for the flagship facility is proposed as one Markdown file in this
directory. The proposal exists so the screen in
[decision D12](../buildout.md#d12-screen-the-cost-share-before-spending-research-on-a-domain) runs
before research money does.

Seven candidates were each researched to completion and each died of the same thing: **a process
architecture change on the same cost line beat the materials discovery**, including in the two cases
where the process genuinely did not yet exist. Value that reduces a loss is bounded below by zero
loss, so it saturates, and the incumbent has owned that cost line for decades.

Every one of the seven was killable in under a day, and five of them in under an hour.

Start from [the template](_template.md), which carries every required heading and the reason each
one is there.

## What a proposal must contain

`tests/test_domain_proposal.py` fails the build if any of these headings is absent, and fails it
again if the controlled cost share is stated without a percentage or falls below 15%.

| Section | The question it answers | Decision |
|---|---|---|
| Value function | Can the customer buy an article today that does the same job? If so the value saturates. State the form: threshold, or multiplicative into an unsold quantity. | D12, test 0 |
| Physics-limit sufficiency | The property at its ceiling, divided by what parity with the incumbent's best available architecture requires. R ≥ 3. | D12, test 2 |
| Architecture ratio | The best zero-discovery flowsheet change, divided by the materials axis at its ceiling. A < 0.3. This check has caught seven of seven. | D12, test 3 |
| Controlled cost share | What percentage of the payer's cost does the discoverable property govern? Show the arithmetic. | D12 |
| Process maturity | Does a mature incumbent process already exist that this would merely improve? | D6 |
| Annual tonnage | World annual tonnage of the addressable output, with a source. | D6 |
| Attribution distance | How many transformation layers sit between the advance and the payer? | D6 |
| Computational regime | SOLVED, PARTIAL or BLIND. Only PARTIAL qualifies. | D6 |
| Measurement identity | Is the number the literature reports the number that sets cost? | D12 |
| Fast screen predicts slow truth | Does the cheap measurement genuinely predict the expensive one, and **with which sign** in the variable that must change at scale? | D6, D13 |
| Capital intensity | Discovery value per unit of output against capital charge per unit of output. | D11 |

## The check that closes the convention's hole

A rule of the form "put it in this directory" is escapable by writing it in a different directory.
So a third check reads [decision D6](../buildout.md#d6-target-technology-domain) directly: once that
entry stops reading as open, it must link to a proposal file that exists here. A domain choice cannot
enter the decision log without a document the screen has already been applied to.

## Why the floor is 15%

A property governing under roughly a sixth of the payer's cost cannot carry a venture outcome,
however good the science is and however large the market. Market size does not rescue it: the share
is multiplicative with the market, so the arithmetic is the same at every scale.

The floor is a screen rather than a verdict. A proposal that fails it is not necessarily wrong about
the physics — it is wrong about who would pay for the physics, which is the cheaper thing to
discover first.
