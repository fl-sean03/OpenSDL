# Domain proposals

A candidate technology domain for the flagship facility is proposed as one Markdown file in this
directory. The proposal exists so the screen in
[decision D12](../buildout.md#d12-screen-the-cost-share-before-spending-research-on-a-domain) runs
before research money does.

Three candidates were each researched to completion and each died on the same question, asked at the
end: what fraction of the paying customer's cost does the discoverable property actually control?
The answers were 1.3%, 2.4-4.1%, and a figure that fell fourfold under recomputation. Each was
estimable in an afternoon from public cost structure.

Start from [the template](_template.md), which carries every required heading and the reason each
one is there.

## What a proposal must contain

`tests/test_domain_proposal.py` fails the build if any of these headings is absent, and fails it
again if the controlled cost share is stated without a percentage or falls below 15%.

| Section | The question it answers | Decision |
|---|---|---|
| Controlled cost share | What percentage of the payer's cost does the discoverable property govern? Show the arithmetic. | D12 |
| Process maturity | Does a mature incumbent process already exist that this would merely improve? | D6 |
| Annual tonnage | World annual tonnage of the addressable output, with a source. | D6 |
| Attribution distance | How many transformation layers sit between the advance and the payer? | D6 |
| Computational regime | SOLVED, PARTIAL or BLIND. Only PARTIAL qualifies. | D6 |
| Measurement identity | Is the number the literature reports the number that sets cost? | D12 |
| Fast screen predicts slow truth | Does the cheap measurement genuinely predict the expensive one? | D6 |
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
