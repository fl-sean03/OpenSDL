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

- deny by default for live environments;
- no credentials in Git;
- scoped, short-lived identities;
- typed validation at every trust boundary;
- durable request identifiers and receipts;
- immutable event and artifact records;
- restricted network egress;
- dependency pinning, SBOMs, and signed releases for production;
- human review for safety-sensitive changes.
