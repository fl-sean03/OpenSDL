---
name: create-lab
description: Create a simulator-first organization laboratory scaffold with policy and validation. Use when bootstrapping a separate lab repository from OpenSDL.
---

# Create an organization laboratory

## Inputs

- empty destination path
- laboratory name
- owner identifier

## Procedure

1. Run `.agents/skills/create-lab/run.sh PATH [NAME] [OWNER]`.
2. Inspect the generated manifest, workflows, policy, tests, and local skills.
3. Configure a package source for the OpenSDL alpha distributions.
4. For a local smoke test before registry publication, run
   `uv build --all-packages --wheel --out-dir dist` in the framework checkout. Then run
   `uv sync --find-links /path/to/OpenSDL/dist` in the lab.
5. Run `./scripts/check.sh` and the first simulator workflow.
6. Prepare an organization-owned baseline. Commit it when requested and only treat `uv.lock` as
   portable when it resolves from a stable registry or committed artifact source. A local
   wheelhouse path can be recorded in the lock and is local bootstrap state.
7. Set the CI repository variable `OPENSDL_PACKAGES_AVAILABLE=true` only after that stable source is
   available. Until then, CI validates agent files and visibly skips the full dependency-backed job.
8. Replace simulated capabilities incrementally and retain their conformance fixtures.

## Completion

With an OpenSDL package source configured, the separate repository resolves its dependencies and
passes its generated simulator checks. A stable package source is required before claiming that the
lockfile and generated CI are portable across clones.

## Stop conditions

Stop if the destination contains files or package resolution is unavailable. Report the exact
state and preserve the destination.
