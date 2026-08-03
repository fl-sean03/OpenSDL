---
name: author-skill
description: Create, revise, split, or remove an OpenSDL repository skill. Use when a recurring agent procedure needs portable triggers, instructions, resources, validation, and fresh-session tests.
---

# Author a repository skill

## Inputs

- recurring job and intended users
- three positive trigger requests
- two nearby requests that should select a different skill or no skill
- supported commands, inputs, outputs, evidence, and stop conditions

## Procedure

1. Read `docs/development/agent-skills.md` and the nearest `.agents/AGENTS.md`.
2. Place durable global rules in `AGENTS.md`, concepts in documentation, exact behavior in typed
   tooling, and equipment procedures in a reviewed lab runbook.
3. Create or revise one canonical directory under `.agents/skills/`.
4. Keep `SKILL.md` focused on one job. Add only the supporting references, scripts, or assets that
   the procedure needs.
5. Use portable `name` and `description` frontmatter. State what the skill does and when it applies.
6. Reference every supporting file and every command that the procedure depends on.
7. Add or update the matching `.claude/skills/` symlink.
8. Run `uv run --locked python scripts/validate-repository.py` and the procedure's own tests.
9. Forward-test positive selection, negative selection, representative execution, and continuing
   work in a dirty worktree.

## Completion

The canonical skill validates, both supported harnesses discover it, its commands exist, and fresh
tests show correct selection and completion behavior.

## Stop conditions

Stop if the proposed procedure depends on a planned command, duplicates operational authority, or
would store credentials, conversation transcripts, or mutable runtime state in Git.
