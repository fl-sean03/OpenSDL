# Add an adapter

Generate a package:

```bash
uv run --locked opensdl adapter create networked-balance \
  --capability-id instrument.measure_mass \
  --destination adapters
```

Implement semantic capability definitions and execution. Add health, reconnect, timeout, retry, cancellation, abort, and cleanup behavior appropriate to the target. Include a simulator or mock and conformance cases. Physical qualification remains deployment-specific.
