# API reference

The FastAPI application serves OpenAPI documentation at `/docs`.

## The API is unauthenticated

**The HTTP API has no authentication and no authorization. Do not expose it to an untrusted
network.**

No route declares a security scheme, no dependency checks a credential, and no middleware
intercepts a request. Every endpoint below is reachable by anyone who can open a socket to the
process, including the two that execute laboratory capabilities:

- `POST /runs` executes a workflow through the durable runtime.
- `POST /capabilities/{capability_id}/execute` executes a single capability.

The `operator_id` field on both request bodies is a caller-supplied string with a default. It is not
a credential. It is the subject the policy engine matches against a rule's `operators` patterns and
the actor recorded on every event, so a caller chooses both the identity policy evaluates and the
identity provenance records. Policy still applies, and a `deny` decision still blocks execution, but
no operator-scoped rule constrains anyone who can reach the port.

The shipped `Dockerfile` binds `0.0.0.0:8000`. Run the API bound to a loopback address, behind an
authenticating reverse proxy, or on a segmented network reachable only by trusted callers. Error
responses no longer echo exception text — every detail string is chosen in the route, because an
adapter's own message can carry an endpoint or a credential. Workflow inputs are still recorded
verbatim in the permanent event log, so treat those as readable by anyone who can read a run.

Authentication and scoped service identities are v0.4 work on the
[roadmap](https://github.com/fl-sean03/OpenSDL/blob/main/ROADMAP.md).

## Endpoints

Implemented endpoints:

- `GET /health`
- `GET /context`
- `GET /tools`
- `POST /tools/{tool_name}`
- `GET /capabilities`
- `POST /capabilities/{capability_id}/execute`
- `GET /resources`
- `GET /runs`
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /events` — `run_id`, `campaign_id`, and a bounded `limit`
- `GET /campaigns`
- `GET /campaigns/{campaign_id}`
- `GET /twin`
- `GET /twin/scene.glb`
- `GET /twin/runs/{run_id}`
- `GET /viewer`
- `GET /viewer/{asset_path}`

The twin and viewer endpoints are read-only and return 404 when the laboratory manifest declares no
digital twin.
