# Runtime package instructions

- Preserve durable run, task, event, lease, and retry semantics.
- Never treat a database rollback as reversal of a physical action.
- Add integration tests for recovery, concurrency, or policy changes.
- Runtime code depends on interfaces; vendor behavior belongs in adapters.
