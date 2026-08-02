---
name: release
description: Prepare a reproducible OpenSDL release by versioning, validating, and building every workspace distribution. Use when cutting or rehearsing a coordinated project release.
---

# Prepare a release

1. Synchronize package versions with `uv run --locked python scripts/release.py VERSION`.
2. Run tests, lint, type checking, boundary checks, schema checks, and migrations.
3. Run the complete simulator campaign and adapter conformance suite.
4. Build every workspace distribution.
5. Review public API changes and migration guidance.
6. Generate the SBOM and check license files in every distribution.
7. Create signed release notes and tag only after the artifacts are reproducible.

The helper builds distribution candidates. It does not publish packages, sign artifacts, generate an
SBOM, or create a tag.
