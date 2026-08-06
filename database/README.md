# Database migrations

The reference runtime uses the SQLAlchemy models in `opensdl-storage`. Alembic owns the schema:
it is how a store comes into existence and the only way it moves forward.

**The migration environment is not in this directory.** It lives in the distribution that declares
the models, at `packages/storage/src/opensdl_storage/migrations/`, so it ships in the
`opensdl-storage` wheel. A generated laboratory installs that wheel, has no checkout of this
repository, and can still migrate its store. `alembic.ini` here points at the packaged environment
through `script_location = opensdl_storage:migrations`.

## Upgrading a laboratory

```bash
opensdl migrate --manifest opensdl.yaml --check   # report pending revisions, write nothing
opensdl migrate --manifest opensdl.yaml           # apply them
```

That command wraps `opensdl_controller.migrate.plan` and `opensdl_controller.migrate.upgrade`. Until
it lands in `packages/cli`, call those two functions or use `alembic -c database/alembic.ini` below;
neither the upgrade nor the adoption depends on the CLI.

`Database.initialize()` applies the same upgrade when a laboratory is opened for writing, so a
store reaches the current schema whether or not anyone runs the command. Read-only commands never
migrate. Back up before upgrading OpenSDL: there is no rollback path for a laboratory's data.

A store created before Alembic owned the schema carries the declared tables and no
`alembic_version`. It is adopted — stamped at `ADOPTION_REVISION` and upgraded from there — rather
than rejected. Nothing is dropped and nothing is recreated.

## Authoring a revision

```bash
uv run --locked alembic -c database/alembic.ini revision --autogenerate -m "describe change"
```

Set `OPENSDL_DATABASE_URL` to autogenerate against a database other than the default SQLite path.

Append revisions; never edit a shipped one. A revision that has to serve both a store built by
Alembic and one adopted from the pre-Alembic path must check before it acts — revision `0002`
creates each index only if it is absent, because a `create_all()` store already had all 23.

`tests/integration/test_migrations.py` compares the schema Alembic produces against the schema the
models declare. A model change without a matching revision fails there.
