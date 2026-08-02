# Quick start

```bash
uv sync --locked --all-packages --group dev
uv run --locked opensdl validate examples/simulated-color-mixing/opensdl.yaml \
  --workflow examples/simulated-color-mixing/workflow.yaml
uv run --locked python examples/simulated-color-mixing/run_campaign.py
```

The example writes local state under `examples/simulated-color-mixing/.opensdl/`. Delete that directory to reset the laboratory.

Inspect capabilities:

```bash
uv run --locked opensdl capability list \
  --manifest examples/simulated-color-mixing/opensdl.yaml
```

Serve the API:

```bash
uv run --locked opensdl serve-api \
  --manifest examples/simulated-color-mixing/opensdl.yaml
```
