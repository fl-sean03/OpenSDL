# Closed-loop campaign

The reference campaign combines the simulated-lab adapter, local-compute adapter, workflow runtime, and grid optimizer.

```bash
uv run --locked python examples/simulated-color-mixing/run_campaign.py
```

A production campaign should record the objective, candidate, workflow and adapter versions, score, uncertainty, evidence run, stopping criterion, and decision rationale.
