# Laboratory manifests

`opensdl.yaml` is the machine-readable entry point for one laboratory environment. It declares metadata, storage, runtime settings, adapters, capability bindings, resources, policy, domain packs, and extension data.

A repository may contain separate manifests for simulation, hardware-in-the-loop, staging, and live operation. Credentials are supplied through environment variables or a secret provider, not committed manifests.

Validate a manifest:

```bash
uv run opensdl validate opensdl.yaml
```
