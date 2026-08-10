# Quick start

Prerequisites: Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).

The commands on this page and throughout these guides run from a checkout of the framework
repository, and their paths are relative to its root. No OpenSDL distribution is published to a
package index yet, so a clone is currently the only way to get one.

```bash
git clone https://github.com/fl-sean03/OpenSDL.git opensdl
cd opensdl
```

Then install the workspace and run the reference campaign:

```bash
uv sync --locked --all-packages --group dev
uv run --locked opensdl validate examples/simulated-color-mixing/opensdl.yaml \
  --workflow examples/simulated-color-mixing/workflow.yaml
uv run --locked python examples/simulated-color-mixing/run_campaign.py
```

It needs no hardware, cloud account, model API, or message broker.

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

An organization's own laboratory belongs in its own repository rather than in this checkout. See
[create a lab project](../guides/create-lab.md).
