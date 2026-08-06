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

Two things a production campaign still cannot do. There is no resume: an optimizer's state is
recorded when the campaign stops and nothing reads it back, so a fitted surrogate does not survive a
restart. And the runner does not schedule around resource leases, so two candidates needing the same
exclusive instrument are dispatched together and one fails as busy — which is why parallelism
defaults to one and why raising it requires knowing the laboratory can support it.
