# Propagation graphs

A propagation graph makes implementation dependencies explicit. Nodes represent areas such as core contracts, generated schemas, storage, adapters, examples, interfaces, documentation, and deployment. Edges state why one area must be reviewed when another changes.

```bash
uv run opensdl propagate packages/core/src/opensdl_core/models.py
```

The result is a review plan, not permission to blindly rewrite every matched file. Tests and generated artifacts should automate deterministic propagation; humans or coding systems review semantic changes.
