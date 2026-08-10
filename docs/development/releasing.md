# Releasing and publishing

## Where the pipeline stops today

OpenSDL has never been released. No Git tag exists, no GitHub Release exists, and no distribution
has been uploaded to any package index. The version in every `pyproject.toml` is `0.1.0a0`, and the
only way to obtain the packages is to build them from a checkout.

Two things exist, and both stop at a built artifact:

| | What it does | What it does not do |
|---|---|---|
| `.agents/skills/release/run.sh VERSION` | Synchronizes the version across the 22 workspace distributions, the generated dependency floors and `CITATION.cff`; relocks; runs `make test lint example`; builds every wheel and sdist into `dist/` | Nothing leaves the machine. No commit, tag, signature, SBOM or upload. |
| `.github/workflows/release.yml` ("Build distribution candidates", manual trigger only) | Runs the same gate on a clean runner and uploads `dist/` as a GitHub Actions artifact | The artifact expires with the run and is visible only to people who can see the repository. No tag, release, signature, SBOM or upload. |

That boundary is deliberate: a package-index name is claimed by its first upload, and this is an
alpha whose contracts are not stable. Building candidates is reversible; publishing is not.

## What publishing would require

None of this is configured. Each step below is something the repository owner has to do
deliberately, in this order.

### 1. Decide the naming surface, and understand what it costs

Publishing means claiming **22 project names** on the index, all under the `opensdl-` prefix:

```text
opensdl-adapter-grid-optimizer   opensdl-domain-materials   opensdl-runtime
opensdl-adapter-human-task       opensdl-domain-physics     opensdl-schemas
opensdl-adapter-local-compute    opensdl-operators          opensdl-sdk
opensdl-adapter-simulated-lab    opensdl-policy             opensdl-simulation
opensdl-api                      opensdl-provenance         opensdl-storage
opensdl-capabilities             opensdl-cli                opensdl-twin
opensdl-controller               opensdl-core               opensdl-workflows
opensdl-domain-chemistry
```

As of 2026-08-10 all 22 are unregistered on PyPI, and so is the bare name `opensdl` — which is
*not* a distribution here but *is* the top-level import package that `opensdl-sdk` installs. Anyone
may register it.

What is irreversible, and what is not:

- **A name is claimed by the first upload.** Nothing reserves it beforehand except a pending
  trusted publisher (step 3), which reserves it only for that one GitHub workflow.
- **A version and its filenames can never be re-uploaded**, even after the release or the whole
  project is deleted. A wrong `0.1.0a1` is corrected by publishing `0.1.0a2`, never by fixing
  `0.1.0a1` in place. Plan the first version number as if it cannot be taken back, because it
  cannot.
- **Yanking is the reversible half.** A yanked release stays installable by exact pin and stops
  being selected by resolvers. Use it for a bad release; deletion is not the tool.
- **Reclaiming a name someone else holds is a discretionary process** ([PEP 541]), measured in
  months and not guaranteed. Releasing a name you hold, by deleting the project, exposes it to that
  process from the other side.
- Uploading to TestPyPI claims nothing on PyPI. It is a separate index with separate accounts, and
  it is the right place to rehearse the mechanics.

Publishing fewer distributions is a legitimate answer, and the dependency graph already suggests
where the line falls. `opensdl-cli` and `opensdl-sdk` reach 14 of the 22 as required dependencies,
so those 14 have to be published together or not at all. The other eight — the four reference
adapters, the three domain packs, and `opensdl-simulation` — are reached only through a manifest at
runtime, so they can be held back. Publishing them anyway claims their names, which is a reason to
publish them and a reason not to.

### 2. Meet the preconditions the current repository does not meet

- `CHANGELOG.md` carries a `## 0.1.0a0 — 2026-08-02` heading for a version that was never tagged or
  published, and everything since sits under `## Unreleased`. A release needs a heading that names
  something someone can install.
- No release notes or migration guidance exist, and
  [compatibility and versioning](../reference/compatibility.md) states that no contract is stable
  between releases. Publishing makes that statement load-bearing for strangers.
- No SBOM is generated and no artifact is signed by any current process.
- `CITATION.cff` carries `version: 0.1.0a0` and `date-released: 2026-08-02`. `scripts/release.py`
  rewrites both; check the result rather than assuming it.

### 3. Configure a trusted publisher on the index — before the project exists

PyPI accepts a *pending* publisher for a project that has not been created yet, which is what makes
the first upload possible without an API token. In the PyPI account settings, under publishing, add
a pending publisher for each project name with:

- owner `fl-sean03`, repository `OpenSDL`;
- workflow filename `release.yml` (or whatever file holds the job in step 5);
- environment name `pypi`.

This is 22 entries. It reserves each name for that workflow alone and grants nothing else.

### 4. Create the GitHub environment

Create an environment named `pypi` in the repository settings with required reviewers, so that a
dispatch of the workflow pauses for a human approval before any upload. Without the environment the
job in step 5 fails closed, which is the desired failure.

### 5. Add the publish job

Adding this job **is** the act of enabling publishing. It lives here rather than in
`.github/workflows/` so that it cannot run by accident. Append it to
`.github/workflows/release.yml`, pin the action to a digest the same way every other action in this
repository is pinned, and read what you are pinning:

```yaml
  publish:
    # Manual dispatch only, gated on the `pypi` environment's reviewers.
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/project/opensdl-core/
    permissions:
      id-token: write   # mints the OIDC token the trusted publisher verifies
    steps:
      - uses: actions/download-artifact@<pin-a-digest>  # v7.0.1
        with:
          name: python-distributions
          path: dist/
      - uses: pypa/gh-action-pypi-publish@<pin-a-digest>
        # No password: the trusted publisher configured in step 3 authenticates this run.
        # Recent versions attach PEP 740 attestations to trusted-publisher uploads; confirm that
        # for the version you pin rather than assuming it.
```

Rehearse it against TestPyPI first by adding `repository-url: https://test.pypi.org/legacy/` and a
pending publisher on that index. A rehearsal there proves the OIDC exchange and the metadata; it
proves nothing about the name on PyPI.

### 6. Tag

Nothing in this repository creates a tag, and no step above needs one. If a release should be
citable, create it after a successful build and before publishing:

```bash
git tag -s v0.1.0a1 -m "OpenSDL 0.1.0a1"
git push origin v0.1.0a1
```

A tag is the one reversible step here — it can be moved or deleted while nobody has fetched it. The
upload in step 5 cannot. Tag first, verify, then publish.

## Release checklist

Once the above exists, a release is:

1. `.agents/skills/release/run.sh VERSION` on a clean worktree with an empty `dist/`;
2. review the version, lockfile and citation diff, and the contents of every wheel and sdist;
3. write the `CHANGELOG.md` heading, release notes, and migration guidance;
4. commit, tag, push;
5. dispatch **Build distribution candidates** against the tag and approve the `pypi` environment.

[PEP 541]: https://peps.python.org/pep-0541/
