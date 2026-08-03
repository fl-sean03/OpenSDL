# Repository skill instructions

- Keep canonical skills at `.agents/skills/<name>/SKILL.md`.
- Use only `name` and `description` in canonical frontmatter. The name must match the directory.
- Give each skill one coherent job, explicit inputs, a procedure, evidence, and stop conditions.
- Put detailed conditional material in `references/`. Use a helper for fragile or repeated commands.
  Use `scripts/` when a skill needs several helpers or supporting code.
- Reference every helper from `SKILL.md`. Keep shell helpers syntax-valid and location-independent.
- Use public commands that exist in the current repository. Do not document planned commands as
  available behavior.
- Do not place credentials, mutable runtime state, conversation transcripts, or operational
  authority in a skill.
- Add or update the matching `.claude/skills/` adapter for every canonical skill.
- Run `uv run --locked python scripts/validate-repository.py` after a skill change.
