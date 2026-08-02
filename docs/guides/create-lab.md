# Create a laboratory repository

```bash
uv run opensdl init ../my-lab --name my-lab --owner my-organization
cd ../my-lab
uv sync
uv run opensdl validate opensdl.yaml --workflow workflows/first-run.yaml
```

Begin in simulation. Replace one capability at a time with an organization adapter while keeping the simulator and the same public workflow.
