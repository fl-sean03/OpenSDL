# Security policy

## Supported versions

No OpenSDL version is currently supported for production operation. The project is an executable alpha.

## Reporting

Do not disclose vulnerabilities publicly when they could expose credentials, enable unauthorized
physical action, bypass policy, corrupt provenance, or reveal facility information. Submit those
reports through [GitHub private vulnerability reporting](https://github.com/fl-sean03/OpenSDL/security/advisories/new).
If that form is unavailable, email the maintainers at
[florezsean0822@gmail.com](mailto:florezsean0822@gmail.com) with `OpenSDL security` in the subject.
Do not include exploit details in a public issue.

A useful report includes the affected version, component, prerequisites, simulator-based reproduction when possible, impact, and mitigation.

## Threat model

The framework assumes that:

- model output and external artifacts are untrusted input;
- adapters and plugins may be compromised;
- laboratory state may be stale or contradictory;
- equipment networks require segmentation;
- safety controls are independent;
- service identities and secret providers are available;
- extension packages require supply-chain review.

## High-priority vulnerability classes

- authorization or policy bypass;
- arbitrary command execution on equipment networks;
- duplicate or replayed physical action;
- resource lease bypass;
- event or artifact tampering;
- cross-lab data access;
- credential disclosure;
- malicious plugin or generated procedure promotion;
- denial of cancellation or safe-state commands;
- incorrect digital-physical reconciliation.

## Secure defaults

These are the defaults the project holds itself to. The alpha implements some of them and does not
yet implement others. The status of each is stated so that a deployment can tell which controls it
must supply itself. A requirement is no weaker for being unimplemented — an unimplemented
requirement is one the operator carries.

| Default | Status in the alpha |
|---|---|
| Deny by default for live environments | **Implemented.** The policy engine's default effect is configurable and the generated manifest sets `deny`, with an allow rule scoped to the `simulation` environment. |
| Typed validation at every trust boundary | **Implemented.** Manifests, workflows, capability inputs, and capability outputs are validated against typed models and JSON Schema. Caller-supplied JSON Schema is compiled without a size or complexity bound. |
| Durable request identifiers and receipts | **Partly implemented.** Every execution carries a durable request identifier and every run, task, and event is persisted. `AuthorizationReceipt` is defined but never written, and `ExecutionRequest.authorization_id` is never populated, so a dispatch record has no link to an authorization. |
| Human review for safety-sensitive changes | **Partly implemented.** Pull-request review applies to every change, and `propagation.yaml` describes the blast radius of a change to a contract. No check invokes it and no gate identifies a change as safety-sensitive. |
| No credentials in Git | **Not implemented.** There is no secret mechanism: no `${ENV}` interpolation in the manifest loader, no secret-provider interface, no `SecretStr`, and no secret scanning in `make lint` or CI. Adapter configuration travels verbatim from the manifest to the adapter, and the manifest is a committed file. The generated laboratory's `.gitignore` covers `.env` but not `.env.*`. |
| Scoped, short-lived identities | **Not implemented.** There is no authentication or authorization anywhere. `operator_id` is a caller-supplied string on every interface, and it is both the policy subject and the recorded actor. |
| Immutable event and artifact records | **Implemented for artifacts, not for events.** Artifact bytes are content-addressed and the digest is recomputed and compared on every read. Event rows carry no hash chain and no append-only constraint, so nothing detects an edited or deleted event, and `policy_version` on a recorded decision is a free-form manifest string bound to no rule content. |
| Restricted network egress | **Not implemented.** Nothing in the framework constrains what an adapter, plugin, or domain pack connects to. Egress control belongs entirely to the deployment. |
| Dependency pinning, SBOMs, and signed releases for production | **Partly implemented.** The framework pins its own dependencies through a committed `uv.lock` and CI runs with `--locked`. There is no SBOM, no release signing, no SAST, no secret scanning, and no dependency audit in CI. Dependabot covers `uv` and `github-actions` only; the viewer's npm dependencies and the Docker base images are unmonitored. The generated laboratory's CI template uses floating action tags and `uv sync` without `--locked`. |

Two consequences are worth stating directly:

- **The HTTP API is unauthenticated.** No route requires a credential, and two of them execute
  capabilities. See the [API reference](docs/reference/api.md).
- **Loading a manifest is a code-execution boundary.** A manifest's `adapters[].plugin` names an
  installed entry point that the controller imports and calls. A validator for reference plugin
  provenance exists but is not called on the loading path.

Compatibility, deprecation, and upgrade guarantees are stated in
[compatibility and versioning](docs/reference/compatibility.md).
