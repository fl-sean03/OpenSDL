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
[roadmap](https://github.com/fl-sean03/OpenSDL/blob/main/ROADMAP.md).

## Environment overrides

- `OPENSDL_MANIFEST`
- `OPENSDL_DATABASE_URL`
- `OPENSDL_ARTIFACT_ROOT`
- `OPENSDL_HOST`
- `OPENSDL_PORT`
