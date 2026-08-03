# Agent instructions and skills

OpenSDL uses small repository instructions and task-complete skills. The files support normal Codex,
Claude Code, and other Agent Skills clients. They do not create a separate agent runtime.

## File roles

| File or directory | Purpose |
|---|---|
| `AGENTS.md` | Durable facts and rules that apply to nearly every task in its directory tree |
| `CLAUDE.md` | Thin Claude Code entrypoint that imports the adjacent `AGENTS.md` |
| `.agents/skills/<name>/SKILL.md` | Canonical procedure for one recurring job |
| `.claude/skills/<name>` | Symlink that exposes the canonical skill to Claude Code |
| `references/` | Detailed material that the skill loads only when needed |
| `scripts/` | Deterministic helpers that the skill can run without loading their source |
| `assets/` | Templates, fixtures, or other files used to produce an output |

The [Agent Skills specification](https://agentskills.io/specification) defines the skill format. It
does not define a universal discovery path. [Codex discovers project skills](https://learn.chatgpt.com/docs/build-skills)
under `.agents/skills/`. [Claude Code discovers project skills](https://code.claude.com/docs/en/skills)
under `.claude/skills/` and supports symlinked skill directories.

OpenSDL keeps one canonical copy under `.agents/skills/`. Per-skill symlinks provide Claude Code
compatibility without duplicate instructions. The lab generator creates a validated mirror when
the host cannot create a directory symlink. Generated development and validation scripts currently
require Bash, including Git Bash or an equivalent environment on Windows.

`AGENTS.md` is also the canonical source for shared repository instructions. The adjacent
`CLAUDE.md` is a regular text file whose `@AGENTS.md` line imports that source when Claude Code loads
the session. The import does not synchronize two editable documents. Change shared instructions in
`AGENTS.md`. Add text to `CLAUDE.md` only when a rule genuinely applies to Claude Code alone.

A `CLAUDE.md` symlink would make both paths refer to the same file, but OpenSDL uses imports. Imports
work without Windows symlink privileges and leave room for a small harness-specific addition. Do
not copy shared rules into both files.

## Keep always-loaded context small

Put a rule in `AGENTS.md` when it applies to most work in that scope. Examples include build
commands, package boundaries, test requirements, and durable safety constraints. Add a nested file
only when a subtree has different rules.

Put a recurring sequence in a skill. A skill can cover development, simulation, diagnosis,
operation, audit, or maintenance. Its name describes a procedure, not an agent persona.

Put exact inputs, state transitions, side effects, and authorization in typed code. Use CI and tests
for mechanical enforcement. Put equipment-specific physical procedures in reviewed lab runbooks.

## Skill shape

Use a flat discovery tree:

```text
.agents/skills/
└── skill-name/
    ├── SKILL.md
    ├── scripts/       # optional
    ├── references/    # optional
    └── assets/        # optional
```

Do not add category directories between `skills/` and the skill name. Use names and descriptions to
express the lifecycle area.

Each `SKILL.md` starts with portable frontmatter:

```yaml
---
name: skill-name
description: Do one job. Use when a concrete trigger or task applies.
---
```

Apply these rules:

- Use lowercase letters, digits, and single hyphens in the name.
- Match the directory name and keep the name at 64 characters or fewer.
- Keep the description between 1 and 1,024 characters.
- State what the skill does and when it applies. Put trigger terms early.
- Keep canonical frontmatter to `name` and `description` for portability.
- Avoid `allowed-tools`, hooks, and other harness extensions in canonical skills.

## Skill length and progressive disclosure

A skill should be long enough to complete one job. Most OpenSDL skills should use tens to low
hundreds of lines. Keep `SKILL.md` below 500 lines and about 5,000 tokens.

Move conditional domain detail, large examples, and reference tables into focused files under
`references/`. Keep references one level below the skill and link each one from `SKILL.md`. State
when the agent should read it.

Use a script when a command is fragile, repeated, or needs deterministic output. Keep simple
judgment work in the procedure. Avoid a large skill that acts as a handbook. Avoid small skills that
must all load to complete one ordinary task.

## Procedure contract

Every OpenSDL skill contains these elements:

1. List required inputs and useful defaults.
2. Inspect current repository and runtime evidence before mutation.
3. Use commands that exist in the current release.
4. Preserve unrelated work and mutable runtime state.
5. Produce tests, run records, exports, or another named form of evidence.
6. State the completion condition.
7. Stop when authority, physical state, or a required typed operation is unclear.

Skills guide an agent through work. They do not grant filesystem, network, source-control, or
laboratory authority. The active harness enforces local permissions. OpenSDL policy and runtime
contracts govern configured laboratory actions.

## Authoring workflow

Use the `author-skill` repository skill for additions and revisions.

1. Collect three realistic trigger requests and two nearby requests that should not select the
   skill.
2. Decide whether the content belongs in `AGENTS.md`, a skill, documentation, a typed command, or a
   lab runbook.
3. Create or update the canonical skill under `.agents/skills/`.
4. Add only the supporting files required by the procedure.
5. Add or update the `.claude/skills/` symlink.
6. Run repository validation and the tests named by the procedure.
7. Test selection and execution from a fresh conversation.
8. Test a continuing conversation against a dirty worktree and current runtime evidence.

The fresh tests must cover a positive trigger, a negative trigger, and a representative task. A
parser check proves that a skill can load. It does not prove that an agent selects the right skill
or follows it correctly.

## Evolution policy

Add a skill when users repeat a coherent job and the underlying interfaces support it. Extend a
skill when new cases share the same inputs, evidence, and completion condition. Split it when the
triggers or stop conditions become distinct.

Delete or revise a skill when its command contract changes. Do not publish procedures for planned
commands. The agent-native operation plan records future lifecycle skills beside the typed platform
work that must exist first.
