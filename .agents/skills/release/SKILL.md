---
name: release
description: Build and validate OpenSDL release candidates by synchronizing versions and producing every workspace distribution locally. Use when cutting or rehearsing a coordinated project release. It does not publish, sign, or tag.
---

# Build a release candidate

This procedure ends at built artifacts in `dist/`. It does not upload to a package index, sign an
artifact, generate an SBOM, create a Git tag, or create a GitHub Release, and neither does
`.github/workflows/release.yml`, which runs the same gate on a clean runner and uploads the
distributions as an expiring Actions artifact. Nothing has ever been published or tagged. What
publishing would additionally require, and what it costs irreversibly, is written down in
[releasing and publishing](../../../docs/development/releasing.md); do not improvise it here.

## Inputs

- target version
- reviewed release scope and notes

## Procedure

1. Start from a clean worktree and an absent or empty `dist/`. Review changes since the previous
   release — there is not yet a first one, so the scope is the whole history until there is.
2. Run `.agents/skills/release/run.sh VERSION`.
3. Review synchronized workspace versions, installed CLI and API version reporting, citation
   metadata, generated dependency floors, public API changes, schemas, and migration guidance.
4. Do not recreate the import-evidence files at the repository root. They describe the imported
   snapshot and live at the import commit; `docs/development/import-provenance.md` records where
   and why.
5. Inspect every wheel and source archive under `dist/`.
6. Record the exact validation evidence and unresolved release work.

## Completion

All workspace distributions build from the reviewed revision, and the test, lint, type, schema,
boundary, example, and conformance checks pass. The artifacts are local and unpublished.

## Stop conditions

Stop on a dirty worktree, a nonempty `dist/`, a failing check, an unexpected public API change, or
an unexpected artifact.

Stop and hand back to the repository owner before any step that leaves the machine: registering a
project name, configuring a trusted publisher, uploading a distribution, or pushing a tag. Claiming
a name on a package index cannot be undone, and an uploaded version can never be re-uploaded.
