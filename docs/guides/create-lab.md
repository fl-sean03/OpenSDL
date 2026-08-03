# Create a laboratory repository

```bash
uv run --locked opensdl init ../my-lab --name my-lab --owner my-organization
cd ../my-lab
uv sync --find-links /path/to/OpenSDL/dist
uv run --locked opensdl validate opensdl.yaml --workflow workflows/first-run.yaml
```

The local wheelhouse is a smoke-test bootstrap. Because its location can be recorded in `uv.lock`,
configure a stable registry or committed artifact source before treating the lockfile and generated
CI as portable across clones. The generated workflow always validates agent files; set the
repository variable `OPENSDL_PACKAGES_AVAILABLE=true` to enable its full job after the stable source
is configured.

Begin in simulation. Replace one capability at a time with an organization adapter while keeping the simulator and the same public workflow.
