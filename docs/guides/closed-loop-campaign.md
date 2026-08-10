# Closed-loop campaign

The reference campaign combines the simulated-lab adapter, local-compute adapter, workflow runtime, and grid optimizer.

```bash
uv run --locked python examples/simulated-color-mixing/run_campaign.py
```

A campaign declares what it is searching — the objectives with their direction, target and measured
uncertainty, the search space, and the feasibility constraints on both candidates and outcomes — so a
candidate outside it is refused before a run is created, a policy decision is taken, or a resource is
leased. Every decision is recorded before the run it causes, naming the runs it rested on, the
acquisition value and function, and the model that produced it. A campaign records why it stopped.

A constraint on an outcome takes one of two forms, and a campaign declares whichever the criterion
actually is. `lower` and `upper` bound a measurement. `equals` states an exact value for a criterion
that is not a measurement at all — a solver reporting whether it converged, or an instrument
reporting whether it trusts the datum it just produced. A bound and an exact value cannot both be
declared on the same constraint, an inverted interval is refused at load rather than failing every
run in silence, and an exact value keeps its type: a criterion declaring `true` is not met by a run
reporting `1`.

Violating an outcome constraint is not a failure. The run happened, the numbers are real, and they
are recorded and handed to the optimizer as evidence about a candidate that does not satisfy the
criterion. What the observation loses is its claim on the result: it is excluded from the best and
cannot reach a target.

An optimizer that proposes several candidates at once declares a batch size; a laboratory that can
execute several at once declares its parallelism, which defaults to one, because how many candidates
a method proposes and how many instruments a laboratory has are different questions.

A campaign resumes. `opensdl campaign start --resume --campaign-id ...` continues the campaign
already recorded under that identifier: history is reconstructed from its own events and the runs
they name, iteration numbering continues, and a candidate whose run already completed is never
dispatched again — including when the controller died between the run finishing and the campaign
recording it, where the run record settles the iteration. An optimizer that implements `load_state`
is handed back what it recorded; one that does not, such as the grid, has the observations replayed
into it instead. Running the same identifier twice without `--resume` is refused.

A resume stops rather than continuing when any iteration names a run whose physical outcome the
record does not establish — an `intervention_required` run above all. The run layer refuses to
re-dispatch such a run, and a campaign that carried on past it would be granting itself an
acknowledgement OpenSDL does not offer. There is deliberately no override. A person establishes what
the equipment did, and until an operation exists for recording that, the remaining search is
submitted as a new campaign.

## What a plugin exchanges is a published document

An optimizer is configured with a `CampaignProblem`, returns a `Suggestion`, and is given back a
`CampaignObservation`. All three are typed models in `opensdl-core` with generated schemas under
`packages/schemas/jsonschema/`, and each is written into the campaign's durable event stream as its
own serialisation rather than as a mapping hand-written beside it. So the document a plugin author
reads the schema for is the document the store holds.

Write them in Python with the field names — `acquisition_function=`, `run_id=` — and read the
recorded form in the stream's camelCase. Both validate.

## What is still open

The runner does not schedule around resource leases, so two candidates needing the same exclusive
instrument are dispatched together and one fails as busy. That is why parallelism defaults to one,
and why raising it means knowing the laboratory can carry it.