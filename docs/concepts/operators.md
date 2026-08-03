# Operators and context

Human users, scripts, workflow services, optimization systems, and AI assistants can use the same typed interfaces.

The context builder provides current laboratory metadata, environment, capabilities, resources, active runs, recent events, and policy version. The operator gateway exposes inspect and execute operations without coupling the runtime to one interface or agent harness.

Interfaces return this context when a user or tool asks for it. OpenSDL does not require a custom
conversation layout or persistent status display.

`AGENTS.md` files document repository-local development commands and constraints. Reusable procedures live in `.agents/skills/`. The laboratory manifest and deployment policy define operational authority. Repository instruction files do not.
