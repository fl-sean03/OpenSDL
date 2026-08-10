# Create a lab project

Run this from a checkout of the framework repository. No OpenSDL distribution is published to a
package index, so the new project installs from a wheelhouse you build here
(`uv build --all-packages --wheel --out-dir dist`).

```bash
uv run --locked opensdl init ../my-lab --name my-lab --owner my-organization
cd ../my-lab
uv sync --find-links /path/to/OpenSDL/dist
uv run --locked opensdl validate opensdl.yaml --workflow workflows/first-run.yaml
```

`opensdl init` scaffolds an independent lab project, intended to live in its own Git repository. It
does not copy the OpenSDL source history or create a GitHub fork. The new project consumes versioned
OpenSDL packages and can upgrade them explicitly. Fork the framework repository only to develop
OpenSDL itself.

Then start a normal agent conversation in the new repository and ask it to “start here,” describe
the existing or planned lab, or name the first workflow to build. The generated `start-here` skill
updates four shared working files:

```text
docs/lab/
├── context.md
├── inventory.md
├── setup-plan.md
└── decisions.md
```

These files let a fresh agent resume from confirmed shared context without copying private chat
history into Git. They do not replace `opensdl.yaml`, runtime evidence, or a secrets store.

The local wheelhouse is a smoke-test bootstrap. Because its location can be recorded in `uv.lock`,
configure a stable registry or committed artifact source before treating the lockfile and generated
CI as portable across clones. The generated workflow always validates agent files; set the
repository variable `OPENSDL_PACKAGES_AVAILABLE=true` to enable its full job after the stable source
is configured.

The generated `pyproject.toml` declares OpenSDL dependency floors with no upper bound, and no OpenSDL
contract is stable between releases. See
[compatibility and versioning](../reference/compatibility.md) for what to pin before the first real
run.

Begin in simulation. Replace one capability at a time with an organization adapter while keeping
the simulator and the same public workflow. [Add an adapter](add-adapter.md) covers generating,
installing, declaring, and running one. Build any 3D scene on demand inside this lab repository;
the framework intentionally provides no equipment-model catalog.
