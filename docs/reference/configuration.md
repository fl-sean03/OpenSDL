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

Environment overrides:

- `OPENSDL_MANIFEST`
- `OPENSDL_DATABASE_URL`
- `OPENSDL_ARTIFACT_ROOT`
- `OPENSDL_HOST`
- `OPENSDL_PORT`
