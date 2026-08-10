# Pull request reviewer

`.github/workflows/reviewer.yml` runs Claude Code headlessly against a pull request and posts one
comment. It reviews against the rules in `AGENTS.md` and against this repository's own record of
checks that reported green while constraining nothing.

It is **off** until somebody adds the repository secret `ANTHROPIC_API_KEY`, and it stays advisory
after that. It is not a gate and it is not on the path to `main`.

## Why it exists, and why it does not duplicate CI

The gates already answer every question that can be answered mechanically: `ci.yml` runs the
workspace suite and `make lint` on three interpreters, `conformance.yml` runs the adapter suite and
the complete example, `docs.yml` builds the documentation strictly, and `scene.yml` rebuilds the
reference scene in headless Blender and compares bytes. Those are unusually real, and they are what
makes agent-authored change safe to accept here.

What they cannot see is whether a check *means* anything. This repository has shipped a
reproducibility test that skipped in CI for months, a policy module at 100% coverage with one
assertion, a conformance harness that grades an adapter against the adapter's own schemas, a
boundary checker that silently passed any package missing from its map, and a state machine with no
callers that had been wrong since it was written. [The audit](audit-2026-08-05.md) catalogues them
under "D. Checks that certify nothing".

So the reviewer's prompt does two things. It states the architecture rules — `core` imports no
internal package, vendor behaviour belongs in adapters, public models are exported as versioned
schemas, every operational adapter needs simulation and conformance coverage, database access goes
through repository interfaces, applications compose packages, and a change is complete only when
code, tests, schemas, examples and documentation agree. And it demands, for every check the change
adds or edits, one concrete sentence naming what that check would have to see in order to fail —
**with an explicit instruction to say so when the answer is nothing.**

It is told not to report anything the gates already enforce. Style, formatting, typing and import
ordering are Ruff's and Pyright's job, and a reviewer that repeats them is a reviewer nobody reads.

## What it cannot do

The list is short on purpose, and most of it is structural rather than a promise:

- **It cannot push, commit, branch, tag, or open a pull request.** The job holds `contents: read`,
  and — this is the part that actually decides it — the workflow passes `github_token:` to the
  action, so that read-only token is the one the model holds. Omit that input and the action mints
  its own GitHub App token carrying Contents, Issues and Pull Requests *write*, which ignores the
  job's `permissions:` block entirely. The workflow also withholds `id-token: write` so the
  exchange cannot succeed, and `scripts/validate-repository.py` fails `make lint` if either
  property is ever lost.
- **It cannot merge or approve.** It posts a normal comment with `gh pr comment`. It has no
  `gh pr review` and no `gh pr merge`, so it can neither approve nor dismiss a review.
- **It cannot block a merge.** It adds no required status check, and nothing consumes its output. A
  failed or skipped reviewer run leaves the real gates exactly as they were. (`main` currently
  carries no protection rule at all — audit finding D8 — so nothing here should be read as a gate.)
- **It cannot run the tests, the linter, or the scene rebuild**, and the prompt tells it not to
  write as though it had. Where a judgement needs evidence it cannot obtain, it is told to name the
  command that would settle it.
- **It never has the pull request's code on disk.** The workspace is the base branch; the change
  reaches the model only as `gh pr diff` output. It therefore sees changed lines with diff context,
  not whole files at head.
- **It does not run on pull requests from forks.** GitHub withholds secrets from fork runs, the
  preflight job detects that, and the review is skipped with an explanation in the run summary.
  `workflow_dispatch` does not inherit that protection — it runs on the base repository with
  secrets live and accepts any number — so the preflight job additionally refuses a dispatch whose
  pull request is cross-repository. Without that check the invariant would hold only on the
  automatic path while the documentation claimed it outright.
- **It does not review drafts**, and it does not re-run on every push — see the triggers below.
- **It cannot be triggered by a bot or by a comment.** `allowed_bots` is left at its empty default
  and there is no `issue_comment` trigger, so no `@claude` mention and no Dependabot pull request
  reaches it.

## The safety model

### It sits behind the gates, not beside them

Nothing about the reviewer is load-bearing. Delete the workflow and every claim this repository
makes about correctness is unchanged. That is the intended relationship: the model's output is a
comment a human reads, and the machinery that decides whether a change is safe is the machinery that
already existed.

### `pull_request`, never `pull_request_target`

`pull_request_target` runs with the base repository's secrets while the pull request supplies the
content — which is the standard way this class of workflow is compromised. This workflow uses
`pull_request`, so a fork pull request runs with no secrets and a read-only token and simply cannot
reach the key. The cost is that fork pull requests are never reviewed. That is the correct trade:
the untrusted case is the one you least want to hand a credential to.

### The working tree is the base branch

The checkout pins `github.event.pull_request.base.sha`. Nothing the contributor wrote is ever
executed, and no PR-authored `Makefile`, lockfile, hook or formatter config can run.

This matters specifically here. The action restores a fixed list of Claude configuration paths from
the base branch — `.claude/`, `.mcp.json`, `CLAUDE.md`, `.husky/` and a few others — but **not**
`AGENTS.md`. This repository's `CLAUDE.md` is a one-line `@AGENTS.md` import, so that import
resolves against the working tree. Checking out the pull request would therefore let it rewrite the
reviewer's own instructions, in a file the vendor's protection does not cover. Checking out the base
branch closes that, and closes the same hole for `.agents/skills/` and for the audit the prompt
tells the model to read.

### No untrusted text is interpolated into the workflow

The only `${{ }}` values that reach the prompt are `github.repository` and a pull request number the
preflight job has already checked is digits. Title, body, comments and diff reach the model only as
tool output — never through workflow-level string interpolation, so they cannot break out into YAML
or into a shell command. The dispatch input is checked rather than trusted because it is
caller-supplied text that ends up in both the prompt and a `gh` argument.

The prompt itself states that the pull request is material under review rather than instruction, and
that an attempt to redirect the reviewer should be reported as the first finding. That instruction
is the weakest layer, not the strongest — it is there so an injection attempt is *visible*, not so
that it is prevented. Prevention is the three structural layers above.

### The blast radius is one comment, plus the key

Job permissions are `contents: read` and `pull-requests: write`; the top-level default is
`permissions: {}`. The vendor's own review example also requests `id-token: write` for workload
identity federation, which this workflow does not use and therefore does not request — and
withholding it is a second layer under `github_token:`, not a substitute for it. The tool
allowlist is `Read`, `Glob`, `Grep`, `Write`, and three narrow `gh` prefixes — `gh pr view`,
`gh pr diff`, and `gh pr comment`. `WebFetch` and `WebSearch` are explicitly denied, because a diff
that contains a URL is otherwise an amplifier. `Write` is allowed only because a multi-line comment
body has to be written to a file before `--body-file` can post it; the runner's filesystem is
discarded when the job ends and nothing is pushed from it.

So a completely successful injection cannot touch `main`, cannot merge, and cannot approve. Its
visible output is a wrong or hostile comment: deletable, and attached to a pull request nobody is
obliged to believe.

That is not the whole blast radius, and the difference matters. `ANTHROPIC_API_KEY` is present in
the environment of the step that runs the model, and the action's subprocess secret scrub is gated
on `allowed_non_write_users`, which this workflow does not set. `gh pr comment` is an allowed
write, and a shell expands `$ANTHROPIC_API_KEY` without the model ever needing to know its value.
So a session that has been fully subverted could publish the key. The same reasoning reaches the
short-lived `GITHUB_TOKEN`, which is `contents: read` and expires with the job.

The honest mitigation is a dedicated Anthropic key used by nothing else, revoked and reissued if a
run ever looks wrong — not a claim that one comment is the ceiling. Treat the key as the asset at
risk here, because it is the only durable thing in the job.

One layer is the vendor's rather than ours and should be named as such: the action refuses to run
for an actor without write access on pull request and comment events. That is real, and it is not
what this workflow relies on. Note that `workflow_dispatch` is an automation event, so that vendor
check does not apply on the dispatch path at all.

### Silence is a failure

The action exits 0 for a session that produced nothing — one that ends with the review as a chat
message instead of calling `gh pr comment`, or one that exhausts `--max-turns`. Posting is the
deliverable, so the job counts comments carrying the reviewer's marker before the session and
again after it, and fails unless the count went **up**. Counting only afterwards would certify
nothing on a re-review by dispatch, where the pull request already carries a review.

## Turning it on

1. Create an Anthropic API key.
2. Add it as the repository secret `ANTHROPIC_API_KEY` (Settings → Secrets and variables → Actions).
3. Open a pull request, or dispatch the workflow against an existing one.

Until step 2, the workflow is inert. It does not half-run: the preflight job reads whether the
secret is non-empty — a boolean, never the key — and the review job is gated on that.

The two absent-secret paths deliberately differ:

| Trigger | No secret | Reasoning |
|---|---|---|
| `pull_request` | Review skipped, explanation written to the run summary, run reports success | Failing every pull request in a repository that has not opted in would turn an unconfigured optional feature into a permanently red build, which is the D8 pathology inverted |
| `workflow_dispatch` | Run **fails** with the same explanation | Somebody asked for a review. Reporting success without one is exactly the "green and constraining nothing" failure this reviewer exists to catch |

## Exercising it before trusting it

`workflow_dispatch` takes a pull request number and runs the **same job** the automatic trigger
runs — same checkout, same prompt, same tools, same permissions. That is the point of it: a rehearsal
that ran a different mode would prove nothing about the path that runs unattended. The one
deliberate difference is that a dispatch refuses a fork pull request, because a dispatch runs with
secrets and the automatic fork path does not.

Run it against a merged pull request first. Read the comment and ask the question the prompt asks:
for each finding, is there a file, a line, and a case that goes wrong — or is it advice? A reviewer
that produces plausible prose and no re-verifiable findings is itself a check that constrains
nothing, and should be turned off rather than tuned.

Be clear about how little of this is mechanically checked, because the gap is the same shape as the
one the reviewer exists to find. `make lint` parses every YAML file in the tree and its propagation
check requires every tracked file to match a node — `.github/workflows/**` under `deployment`,
`docs/**` under `documentation`. Parsing is not validation: a wrong permission, a nonexistent
action input, an `if:` referencing a missing output, or a step that certifies nothing are all
well-formed YAML and pass every gate. No `actionlint` or `yamllint` runs in CI or in any `make`
target.

The one workflow property this repository does enforce is the one whose failure is invisible:
`scripts/validate-repository.py` requires every `anthropics/claude-code-action` step to pass
`github_token:`, to be pinned to a full commit SHA, and to sit in a job that does not grant
`id-token: write`. GitHub ignores unknown `with:` keys with only a warning, so a typo in that input
name reads exactly like the correct spelling while silently restoring a write-scoped token. That is
the single most fragile line in these three workflows, and it now has a test. Everything else about
them rests on review.

## Knobs, and what changing them costs

| Where | Now | If you change it |
|---|---|---|
| `on.pull_request.types` | `opened`, `reopened`, `ready_for_review` | Adding `synchronize` reviews every push. It multiplies cost and produces a comment per push, which is how a reviewer stops being read. Re-review is a dispatch instead |
| `claude_args: --model` | `claude-opus-5` | Pinned so the review's behaviour does not change under you. Every action in `.github/workflows/` is pinned by commit SHA for the same reason; an unpinned model is the same hazard in a different place |
| `claude_args: --max-turns` | `30` | Bounds a runaway session. Paired with `timeout-minutes: 20` on the job |
| `claude_args: --allowedTools` | read-only plus `gh pr comment` | Adding `mcp__github_inline_comment__create_inline_comment` gives inline annotations. Left off deliberately: one structured comment is easier to read and gives the model one write surface instead of two |
| `permissions` | `contents: read`, `pull-requests: write` | `pull-requests: write` is the minimum that can post a comment. Nothing here needs more |
| `github_token` | the job's `GITHUB_TOKEN` | Do not remove it and do not add `id-token: write`. Together they are what make the `permissions` row above describe the token the model actually holds; `make lint` fails if either changes |
| `concurrency` | per pull request, `cancel-in-progress: true` | Prevents duplicate comments and superseded spend |

The prompt is the part most worth editing. It is a block scalar in the workflow rather than a
separate file so that a change to what the reviewer is asked shows up in the workflow's own diff.
When editing it, keep the rule that got it here: **do not put a count in it.** Test totals, file
counts and check counts go stale silently, which is audit finding G1, and a prompt is not covered by
the propagation graph edge that was built to catch that.
