# Storage package instructions

- All metadata access goes through `Repositories` or a future narrow protocol.
- Model changes require Alembic migration and round-trip tests.
- Artifact bytes are immutable and hash-verified.
- Test against SQLite. No PostgreSQL runs anywhere in CI, so dialect-specific behavior — the
  rowcount of a conditional `UPDATE`, savepoints, conflict handling — is unverified on the other
  supported backend. Prefer portable constructs and say in the change where one is relied on.
  Adding that CI job is tracked in the development backlog.
