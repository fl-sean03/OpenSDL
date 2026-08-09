---
name: release
description: Prepare OpenSDL release candidates by versioning, validating, and building every workspace distribution. Use when cutting or rehearsing a coordinated project release.
---

# Prepare a release

## Inputs

- target version
- reviewed release scope and notes

## Procedure

1. Start from a clean worktree and an absent or empty `dist/`. Review changes since the previous
   release.
2. Run `.agents/skills/release/run.sh VERSION`.
3. Review synchronized workspace versions, installed CLI and API version reporting, citation
   metadata, generated dependency floors, public API changes, schemas, and migration guidance.
4. Do not recreate the import-evidence files at the repository root. They describe the imported
   snapshot and live at the import commit; `IMPORT_PROVENANCE.md` records where and why.
5. Inspect every wheel and source archive under `dist/`.
6. Record the exact validation evidence and unresolved release work.

## Completion

All workspace distributions build from the reviewed revision, and the test, lint, type, schema,
boundary, example, and conformance checks pass.

## Stop conditions

Stop on a dirty worktree, a nonempty `dist/`, a failing check, an unexpected public API change, or
an unexpected artifact.

The helper builds distribution candidates. It does not publish packages, sign artifacts, generate an
SBOM, or create a tag.
