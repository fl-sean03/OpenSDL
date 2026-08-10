# Configuration reference

Top-level manifest fields:

- `apiVersion`: currently `opensdl.dev/v0alpha1`;
- `kind`: `Laboratory`;
- `metadata`: name, owner, description, tags;
- `spec.environment`: deployment environment;
- `spec.storage`: database URL and artifact root;
- `spec.runtime`: concurrency, default timeout, lease TTL;
- `spec.adapters`: plugin packages and configuration;
- `spec.capabilities`: optional explicit bindings;
- `spec.resources`: laboratory resources;
- `spec.policy`: default effect and ordered rules;
- `spec.domain_packs`: scientific extension packages.

## Secret references

`opensdl.yaml` is a committed file. A credential written into it is a credential in Git, so a
manifest **names** its credentials instead of carrying them:

```yaml
spec:
  storage:
    database:
      url: postgresql://opensdl:${env:OPENSDL_DB_PASSWORD}@db:5432/lab
  adapters:
    - name: networked-balance
      plugin: networked-balance
      config:
        host: balance.lab.example
        token: ${env:BALANCE_TOKEN}
```

The form is `${provider:name}`. `load_manifest` resolves references before validation, so every
consumer — adapters, the runtime, the API — receives ordinary values and nothing has to know a value
was named rather than written.

**`env:` is the only implemented provider.** It reads a process environment variable. The prefix
exists so a real secret provider can be added later without changing a manifest that already works;
a reference naming any other provider is refused rather than ignored.

### Resolution fails closed

A reference that does not resolve is an error naming the variable and the field it appeared in.
Nothing substitutes an empty string and nothing leaves the literal `${env:BALANCE_TOKEN}` in place:
either would send garbage to an instrument and surface as an authentication failure in a laboratory,
which is a far worse place to discover a misspelled variable name than the loader.

A variable that is **set but empty** is also an error, for the same reason.

Two positions refuse a reference outright:

- **A mapping key.** `${env:FIELD}: value` would let the environment decide which field is being
  configured, which is a different and larger power than supplying its contents.
- **Anywhere under `spec.policy`.** Policy decides whether a capability may execute. Allowing
  `default_effect: ${env:EFFECT}` would make `EFFECT=allow` a supported configuration for a live
  laboratory, and authorization bypass is the first vulnerability class in
  [`SECURITY.md`](https://github.com/fl-sean03/OpenSDL/blob/main/SECURITY.md). Write policy in the
  manifest, where review can see it.

A `${...}` that names no provider is not a secret reference and is left exactly as written, so
workflow references such as `${inputs.sample_id}` pass through untouched. There is no escape
sequence: a literal `${env:NAME}` cannot be expressed in a manifest.

### A resolved value is not printed back

`dump_manifest` and `redacted_manifest_document` write the reference back, not what it resolved to,
so a load-then-write round trip reproduces the file instead of committing the credential. The
context pack that `GET /context`, the `describe_lab` tool, and the SDK serve carries the reference
for `spec.domain_packs[].config`. `opensdl doctor` and `GET /health` print the database URL with
userinfo and credential-bearing query parameters replaced.

What this does **not** cover, and what a deployment still carries:

- an adapter receives the resolved credential, as it must, and anything that adapter chooses to put
  in `health()`, in an exception message, or in a capability's `metadata` is printed by
  `opensdl doctor` or served by the API unfiltered;
- there is no secret scanning in `make lint` or CI, so a credential typed directly into a manifest
  is still committed without complaint;
- the generated laboratory's `.gitignore` covers `.env` but not `.env.*`.

## Policy rules

`spec.policy.default_effect` is `allow` or `deny` and applies when no rule matches. It defaults to
`deny`, and the generated laboratory sets it explicitly. `spec.policy.version` is a free-form string
recorded on every policy decision.

`spec.policy.rules` is an ordered list. Rules are sorted by ascending `priority` and the first match
wins. Each rule declares:

- `id`: rule identifier, recorded on the decision;
- `effect`: `allow` or `deny`;
- `capability`: glob matched against the capability identifier;
- `environments`: globs matched against `spec.environment`;
- `operators`: globs matched against the operator identifier;
- `risk_classes`: exact risk-class values, or `*`;
- `reason`: text recorded on the decision;
- `priority`: evaluation order, lowest first.

### `operators` does not identify anyone

The operator identifier a rule matches against is a caller-supplied string. The CLI, the SDK, the
HTTP API, and the controller each take it as an ordinary parameter with a default and pass it
straight to the policy engine, and no authentication exists anywhere that could establish it. Any
caller can present any operator identifier.

**A rule scoped to `operators` therefore provides no assurance.** A rule that denies one operator
constrains nobody, because the caller it names sends a different string instead. Use `capability`,
`environments`, and `risk_classes` to bound what a laboratory can do. Treat `operators` as a label on
a decision record rather than as access control, and treat the actor recorded on every event as
self-declared. Authentication and scoped service identities are v0.4 work on the
[roadmap](../development/roadmap.md).

## Environment overrides

- `OPENSDL_MANIFEST`
- `OPENSDL_DATABASE_URL`
- `OPENSDL_ARTIFACT_ROOT`
- `OPENSDL_HOST`
- `OPENSDL_PORT`

These replace a manifest value outright. They are not secret references and are not resolved: a
credential in `OPENSDL_DATABASE_URL` reaches the store as written. Prefer `${env:NAME}` inside the
manifest, which keeps the connection string under review and the credential out of it.

## Database schema

`spec.storage.database.url` names a store whose schema Alembic owns. Opening a laboratory for
writing brings its store to the current schema; a store created before Alembic owned the schema is
adopted rather than rejected. `opensdl migrate --check` reports what is pending without applying it,
and wraps `opensdl_controller.migrate.plan` — which is what exists until that command lands in
`packages/cli`. See
[compatibility and versioning](compatibility.md#the-database-schema-upgrades-through-alembic).
