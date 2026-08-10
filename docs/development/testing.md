# Testing

Run the suites:

```bash
make test
```

`make test` runs the workspace suite and the digital-twin surrogate overlay. A bare
`uv run --locked pytest` is not the whole suite: `testpaths` in `pyproject.toml` excludes
`examples/`, so the surrogate tests are reachable only through `make test` or `make surrogate`.
`make test` and `make lint` together are what CI enforces on a pull request; `make viewer`,
`make docs`, and `make example` cover the rest of it, and `make scene` covers the Blender rebuild
that runs separately.

Markers:

- `integration`: crosses package or process boundaries;
- `e2e`: runs a complete scientific loop;
- `conformance`: verifies an extension contract.

Virtual equipment and fault injection make the main suite deterministic. Hardware tests should live in controlled organization repositories or explicit hardware test environments.
