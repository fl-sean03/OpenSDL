# Storage and provenance

OpenSDL stores structured metadata in a relational database and large data in an artifact store.

The event stream records what occurred. Run and task rows provide efficient current-state queries. Artifact records point to immutable bytes identified by SHA-256.

The reference exporter packages run metadata, tasks, events, and artifacts into a ZIP with RO-Crate metadata. Research graphs are projections built from those durable records.
