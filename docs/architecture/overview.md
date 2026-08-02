# Architecture overview

The reference system is a modular monolith by default: one process composes the registry, policy engine, runtime, repositories, artifact store, and operator gateway. This is intentionally easier to understand and deploy than an initial microservice architecture.

Components can be separated when scale or equipment-network boundaries justify it. Public contracts and adapters remain stable as deployment topology changes.

See the repository-root
[ARCHITECTURE.md](https://github.com/fl-sean03/OpenSDL/blob/main/ARCHITECTURE.md)
for the full package graph.
