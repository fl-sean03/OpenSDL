# Repository skills

`.agents/skills/` is the canonical OpenSDL skill tree. Each skill follows the
[Agent Skills specification](https://agentskills.io/specification) and contains one recurring
procedure. Codex discovers this tree directly. Claude Code discovers the same directories through
the symlinks in `.claude/skills/`.

`AGENTS.md` contains small, always-loaded project rules. Skills contain task procedures. Detailed
architecture stays in `docs/`, and exact behavior stays in typed code, commands, tests, manifests,
and policy.

See [`docs/development/agent-skills.md`](../docs/development/agent-skills.md) before adding or
changing a skill.
