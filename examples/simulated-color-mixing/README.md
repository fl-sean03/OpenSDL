# Simulated color-mixing laboratory

This is the v0.1 proof that the repository works without hardware, cloud services, or model APIs.

```bash
uv run python examples/simulated-color-mixing/run_campaign.py
```

The campaign creates virtual samples, measures color and mass, scores every experiment, records decisions, persists runs/tasks/events, and identifies the closest recipe to the target purple.
