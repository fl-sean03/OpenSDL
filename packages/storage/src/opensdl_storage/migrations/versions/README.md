# Migration revisions

Revisions are a global sequence, and `tests/integration/test_migrations.py` pins specific
identifiers in five assertions. Two engineers adding a migration on separate branches will collide
unless the next numbers are claimed in advance, and the collision surfaces as a failing pin rather
than as a merge conflict.

## Landed

| Revision | What |
|---|---|
| `0001_initial` | The initial schema |
| `0002_declared_indexes` | Declared indexes |

## Claimed, from the facility buildout plan

| Revision | Owner | What |
|---|---|---|
| `0003` | long-latency capabilities | the awaited-result columns and the overdue sweep |
| `0004` | long-duration leases | lease renewal and reconciliation state |

If those two land in the other order, both numbers move and so do the pins in
`tests/integration/test_migrations.py`. Claim a number here before writing the file.

## Rules that the tests enforce

A migration containing an opaque call — `op.execute` and anything else the checker cannot read — has
to declare itself `destructive`, and `upgrade_to_head` then refuses to run it on open. That is
deliberate: a laboratory that a user can express in fifteen manifest lines must not need a migration
step between writing the manifest and running work. See
[decision D4](../../../../../../docs/development/buildout.md#d4-scale-invariance-the-small-case-stays-first-class).
