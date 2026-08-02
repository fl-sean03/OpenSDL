# Database migrations

The reference runtime uses SQLAlchemy models from `opensdl-storage`. Alembic provides release migrations.

```bash
OPENSDL_DATABASE_URL=sqlite:///./.opensdl/opensdl.db \
  uv run --locked alembic -c database/alembic.ini upgrade head
```

`Database.initialize()` creates the same tables for local development and tests. Production deployments should use Alembic migrations and maintain backup/restore procedures.
