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

One thing a production campaign still cannot do: the runner does not schedule around resource
leases, so two candidates needing the same exclusive instrument are dispatched together and one
fails as busy. That is why parallelism defaults to one, and why raising it means knowing the
laboratory can carry it.