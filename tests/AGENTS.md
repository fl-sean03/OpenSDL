# Cross-package test instructions

## Where an end-to-end test lives

An end-to-end test of an example lives in `tests/end_to_end/` and reads the example's YAML by path.

`pyproject.toml` sets `testpaths = ["packages", "apps", "adapters", "domain-packs", "tests"]`, so a
test placed under `examples/` **does not run** unless it also has a Makefile target and a CI job of
its own. Two exist and both are deliberate: `make surrogate` runs the digital-twin overlay, and
`make scene` runs the headless Blender rebuild behind its own workflow because it needs a pinned
Blender and several minutes.

Adding a third by accident is the failure this rule prevents. A test that never runs is worse than a
missing one, because the coverage looks present.

## What belongs here rather than in a package

- Behaviour that crosses package boundaries, where no single package owns the assertion.
- Guards on decisions in `docs/development/buildout.md`. These read the repository as data and fail
  when a decision quietly stops being true — `test_minimal_laboratory.py` for D4,
  `test_domain_proposal.py` for D6, D11 and D12, `test_twin_is_read_only.py` for D14.
- Anything asserting a property of the repository itself: structure, versions, skills.

A test about one package's internals belongs in that package.

## Guards that read the repository

A guard is only worth its line count if it fails when the thing it protects breaks. Verify both
directions before committing one: introduce the violation, watch the named assertion fire, restore.
A guard that has only ever been observed passing has not been tested, it has been written.

State the decision it enforces in the module docstring, so the next reader learns why the constraint
exists without opening the decision log.
