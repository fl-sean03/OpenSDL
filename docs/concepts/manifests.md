# Laboratory manifests

`opensdl.yaml` is the machine-readable entry point for one laboratory environment. It declares metadata, storage, runtime settings, adapters, capability bindings, resources, policy, domain packs, and extension data.

A repository may contain separate manifests for simulation, hardware-in-the-loop, staging, and live operation. Credentials are named rather than written: a manifest value may contain `${env:NAME}`, which `load_manifest` resolves from the process environment before validation.

```yaml
spec:
  adapters:
    - name: networked-balance
      plugin: networked-balance
      config:
        token: ${env:BALANCE_TOKEN}
```

`env:` is the only implemented provider. The `${provider:name}` form leaves room for a secret
provider later, and any other prefix is refused by name rather than passed through. A reference
that does not resolve is an error naming the variable and the field: nothing substitutes an empty
string and nothing leaves the literal text in place, so a missing credential fails at the loader
instead of at an instrument. References are refused in mapping keys, because the environment must
not choose which field is configured, and anywhere under `spec.policy`, because resolving an
authorization decision from an environment variable would make `EFFECT=allow` a supported
configuration. A resolved value is written back as its reference when a manifest is dumped and in
the operator context pack. See [configuration](../reference/configuration.md).

Validate a manifest:

```bash
uv run --locked opensdl validate opensdl.yaml
```
