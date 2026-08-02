# Storage package instructions

- All metadata access goes through `Repositories` or a future narrow protocol.
- Model changes require Alembic migration and round-trip tests.
- Artifact bytes are immutable and hash-verified.
- Test SQLite locally and PostgreSQL in CI for dialect-specific behavior.
