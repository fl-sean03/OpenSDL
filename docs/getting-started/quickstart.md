# Quick start

```bash
uv sync --all-packages --group dev
uv run opensdl validate examples/simulated-color-mixing/opensdl.yaml \
  --workflow examples/simulated-color-mixing/workflow.yaml
uv run python examples/simulated-color-mixing/run_campaign.py
```

The example writes local state under `examples/simulated-color-mixing/.opensdl/`. Delete that directory to reset the laboratory.

Inspect capabilities:

```bash
uv run opensdl capability list \
  --manifest examples/simulated-color-mixing/opensdl.yaml
```

Serve the API:

```bash
uv run opensdl serve-api \
  --manifest examples/simulated-color-mixing/opensdl.yaml
```
