# Add an adapter

An adapter binds a capability identifier to something that can execute it: an instrument, a robot, a
compute service, a human, or a simulator. This guide takes one from generation to a workflow that
runs it.

Generation alone is not enough. `opensdl adapter create` writes an installable package, and nothing
installs it. Until the laboratory depends on that package, the manifest fails at composition with
`LookupError: unknown adapter plugin`, and `opensdl validate` reports success anyway. The steps below
are the whole path.

The examples use a laboratory created by `opensdl init` whose environment is already synced, so that
`uv run opensdl` resolves inside it, and an adapter named `networked-balance` bound to
`instrument.measure_mass`. See [create a laboratory](create-lab.md) for that starting point.

## Where an adapter belongs

Put the generated package at `adapters/<name>/` in the laboratory repository. That is the default
destination of `opensdl adapter create`, and it is the right one: the generator emits a complete
distribution with its own `pyproject.toml`, entry point, tests, and instructions. A distribution
cannot live inside another distribution's import package, so it does not belong under
`src/<package>/`.

The generated `AGENTS.md` also names `src/<package>/adapters/`. That directory is for adapter classes
written by hand into the laboratory's own package, with the entry point declared in the laboratory's
`pyproject.toml`. It is a module, not a package, and it is not where `opensdl adapter create` writes.
Use `adapters/<name>/` whenever the generator produced the code.

## 1. Generate the package

Run from the laboratory repository:

```bash
uv run opensdl adapter create networked-balance \
  --capability-id instrument.measure_mass \
  --destination adapters
```

This writes `adapters/networked-balance/` containing `pyproject.toml`, the adapter class under
`src/opensdl_adapter_networked_balance/`, a test, and instruction files. The `pyproject.toml` already
declares the entry point that makes the adapter discoverable:

```toml
[project.entry-points."opensdl.adapters"]
networked-balance = "opensdl_adapter_networked_balance.adapter:NetworkedBalanceAdapter"
```

The entry-point name on the left is the value a manifest puts in `plugin:`.

## 2. Install it into the laboratory

Discovery reads installed distributions, so the entry point is invisible until the laboratory
depends on the package. Add it to the laboratory's `pyproject.toml` as a dependency and resolve that
dependency from the local path:

```toml
[project]
dependencies = [
  "opensdl-cli>=0.1.0a0",
  "opensdl-adapter-simulated-lab>=0.1.0a0",
  "opensdl-adapter-local-compute>=0.1.0a0",
  "opensdl-adapter-human-task>=0.1.0a0",
  "opensdl-adapter-networked-balance",
]

[tool.uv.sources]
opensdl-adapter-networked-balance = { path = "adapters/networked-balance", editable = true }
```

Both parts are required. The `dependencies` entry is what makes the package part of the environment;
the `[tool.uv.sources]` entry is what tells `uv` to resolve it from the working tree rather than from
an index, where it does not exist.

`editable = true` is what makes the adapter workable. Without it `uv` builds and installs a wheel, so
every source edit needs another `uv sync` before it takes effect — a change to the adapter silently
does nothing until you remember to re-sync.

Then sync:

```bash
uv sync
```

If the OpenSDL distributions are not in your configured index, add the wheelhouse built from the
framework checkout, as described in the laboratory's `README.md`:

```bash
uv sync --find-links ../opensdl/dist
```

`uv sync` reports the adapter as installed from its path:

```text
+ opensdl-adapter-networked-balance==0.1.0 (from file:///.../my-lab/adapters/networked-balance)
```

## 3. Declare it in the manifest

Add the adapter and bind the capability to it in `opensdl.yaml`:

```yaml
spec:
  adapters:
    - name: networked-balance
      plugin: networked-balance
  capabilities:
    - capability: instrument.measure_mass
      adapter: networked-balance
```

`plugin` is the entry-point name from step 1. `name` is how the manifest refers to this adapter
instance.

## 4. Confirm it loads

`opensdl validate` does not load plugins, so it reports `Manifest valid` whether or not the adapter is
installed. Use `doctor`, which composes the system and reports each adapter's health:

```bash
uv run opensdl doctor --manifest opensdl.yaml
```

A missing installation fails here, and the message names what is available:

```text
LookupError: unknown adapter plugin 'networked-balance'; available: human-task, local-compute, simulated-lab
```

If you see that after step 2, the dependency, the `[tool.uv.sources]` entry, or the `uv sync` is
missing.

## 5. Run it

Write a workflow that calls the capability, as `workflows/balance-check.yaml`:

```yaml
id: balance-check
name: Networked balance check
input_schema:
  type: object
  required: [sample_id]
  properties:
    sample_id: {type: string}
  additionalProperties: false
steps:
  - id: weigh
    capability: instrument.measure_mass
    inputs:
      sample_id: ${inputs.sample_id}
outputs:
  simulated: ${steps.weigh.output.simulated}
```

Then run it:

```bash
uv run opensdl validate opensdl.yaml --workflow workflows/balance-check.yaml
uv run opensdl run workflows/balance-check.yaml \
  --manifest opensdl.yaml \
  --inputs '{"sample_id": "demo-001"}'
```

The generated adapter echoes its inputs and reports `"simulated": true`, so a successful run proves
the wiring rather than the instrument. Policy applies as usual: the generated capability is `R0` and
the generated laboratory's rule allows `R0` and `R1` in the `simulation` environment.

## 6. Update the laboratory's own test

The generated `tests/test_configuration.py` asserts the exact set of adapter plugins in the manifest,
so `uv run pytest` fails once you add one:

```text
AssertionError: Extra items in the left set: 'networked-balance'
```

Add the new plugin name to that assertion. Keeping the assertion exact is deliberate: it makes an
undeclared or removed adapter a test failure rather than a runtime surprise.

## 7. Implement the capability

The generated adapter is a placeholder that returns its inputs. Replacing it is the real work:

- **Semantic definitions.** Give the capability real `input_schema` and `output_schema` values,
  a truthful `executor_type` and `risk_class`, a `timeout_seconds`, and `max_retries`. The runtime
  validates outputs against the declared schema.
- **Transport and typed failures.** Own the vendor protocol inside the adapter and raise typed
  errors. Error strings reach unauthenticated API responses and the permanent event log, so keep
  credentials and endpoints out of them.
- **Health and reconnect.** `health()` is what `doctor` reports. Make it reflect the connection.
- **Lifecycle.** `start()` and `close()` are called by the registry around the process lifetime.
- **A simulator.** Keep a simulated path so the workflow runs without the instrument. Every
  operational adapter needs one.
- **Conformance cases.** `conformance_cases()` should exercise the real input shape, not the
  generated placeholder.

`abort()` is declared on `CapabilityAdapter`, but the runtime has no cancellation path, so nothing
calls it. Implementing it today produces code that will not run. See
[capabilities](../concepts/capabilities.md).

Physical qualification stays deployment-specific. An adapter that returns a success is not evidence
that a physical action occurred — see
[SAFETY.md](https://github.com/fl-sean03/OpenSDL/blob/main/SAFETY.md) for the records a physical
operation must preserve and the controls that remain independent of this framework.
