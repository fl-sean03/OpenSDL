# Testing

Run everything:

```bash
uv run pytest
```

Markers:

- `integration`: crosses package or process boundaries;
- `e2e`: runs a complete scientific loop;
- `conformance`: verifies an extension contract.

Virtual equipment and fault injection make the main suite deterministic. Hardware tests should live in controlled organization repositories or explicit hardware test environments.
