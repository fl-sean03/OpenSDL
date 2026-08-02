# Prepare a release

1. Synchronize package versions with `uv run python scripts/release.py VERSION`.
2. Run tests, lint, type checking, boundary checks, schema checks, and migrations.
3. Run the complete simulator campaign and adapter conformance suite.
4. Build every workspace distribution.
5. Review public API changes and migration guidance.
6. Create signed release notes and tag only after artifacts are reproducible.
