# Issue responder

`.github/workflows/issue-responder.yml` reads a newly opened issue, classifies it, answers what the
repository can actually answer, and posts one comment. It is off until someone sets a secret, and it
is advisory: nothing downstream reads its output, and no gate waits for it.

It is deliberately not a triager. It does not label, assign, close, or prioritise anything. The
comment is the entire product.

## What it does

| Kind of issue | What the reply contains |
|---|---|
| Question | The answer, with the committed file that already contained it quoted and linked — plus a sentence naming the page that should have surfaced it |
| Bug report | A reproduction attempt against the current tree: the exact command, its real output, and which of *reproduced*, *not reproduced*, or *could not attempt* happened |
| Feature request | Whether the repository supports it **today** — yes with the code that does it, partly with the half that exists, or no — and whether the backlog or roadmap already tracks it |

The second half of the question row is the point of the whole thing. A question whose answer was
already written down is a discoverability defect, not a support request, and the reply is the only
place that observation gets recorded. Reading those replies is how the documentation gets fixed.

### Accuracy over helpfulness

The prompt names [the audit register](audit-2026-08-05.md) and [the validation
report](validation.md) as the honest inventory and tells the model they outrank every other document
— including the README — when they disagree. The "Asserted, not verified" section is the specific
target: PostgreSQL, plugin trust, secret handling, retry-safety enforcement, authentication and
packaging are all implemented-but-unverified, and a reply that promises any of them as a working
feature is a worse outcome than no reply.

This reduces the failure rate. It does not eliminate it. A comment from this workflow is a starting
point for a maintainer, not an answer from the project.

## What it cannot do

The safety argument is not that the model behaves. It is that the job's token forecloses the
outcomes that matter. Everything below is a property of `permissions:` plus the `github_token:`
input, not a request made of the model.

| | Why |
|---|---|
| Push to `main`, or to any branch | The responder job holds `contents: read`, and the workflow passes `github_token:` so that is the token the model holds. Without that input the action mints its own App token with Contents write and the `permissions:` block stops meaning anything; `make lint` fails if it is ever dropped |
| Open a pull request | Same. It is asked to *describe* a change instead, and told it cannot offer a branch |
| Touch a workflow, a tag, or a release | No permission grants it |
| Read a secret other than the one it was handed | Only `ANTHROPIC_API_KEY` and the job's `GITHUB_TOKEN` are in scope, and the token expires with the job |
| Reply twice to one issue | An issue already carrying a reply from the Actions bot is skipped |

### What it *can* do, which the table above should not be read as excluding

`issues: write` is scoped to the **repository**, not to the issue being answered. It authorises
editing any issue's title and body, deleting anybody's comment, and closing, locking, labelling or
assigning — across the whole tracker. The prompt asks the model not to do any of that, and
`--allowedTools` omits the tools for it, but the allowlist includes `Bash(uv run --locked python
/tmp/:*)` and `Write(/tmp/**)`, which is arbitrary code by construction and can call `gh` directly.
So treat "it does not label, assign or close" as a request the model is asked to honour, not as
something the token prevents. The worst case is not one visible bad comment; it is quiet edits
anywhere in the issue tracker, and a deleted comment does not come back.

Two further limits are commonly assumed and are not true. The runner has unrestricted network
egress, so "cannot read another repository" is wrong — any public repository is `git clone`-able
regardless of token scope; what the token prevents is *writing* to one. And `ANTHROPIC_API_KEY` is
the durable asset in the job: `allowed_non_write_users` turns on the action's subprocess secret
scrub, which helps, but the session can comment, so use a key dedicated to this workflow that can
be revoked on its own.

What stays true and is the point: nothing here reaches `main`, the code, or a release.

It also cannot answer well when the answer is not in the repository. It has no access to the
issue tracker's history, no memory between runs, and no way to ask a follow-up question.

## The prompt-injection surface

Issue text is written by strangers and this workflow feeds it to a model that runs commands. Four
things constrain that, and they are worth ranking, because only the first two hold regardless of how
the model behaves.

1. **The permissions block.** Described above. This is the real containment.
2. **No untrusted text enters the workflow.** The only value interpolated into `issue-responder.yml`
   is the issue *number*, and `preflight` refuses it unless it is digits. Title, body and comments
   reach the model only as the output of `gh issue view` — visibly a tool result, never part of the
   instructions, and never a shell word. The GitHub Actions script-injection class does not apply.
3. **`--allowedTools`.** The session can read the tree, run the committed test suite and CLI, write
   under `/tmp`, and comment. This is a reduction, not a proof: a prefix-matched command allowlist
   is not a sandbox, and a reproduction script under `/tmp` is arbitrary code by construction. It
   raises the cost of misusing the session; item 1 is what bounds the damage.
4. **The prompt.** It tells the model that issue text is the subject of its work rather than
   instruction to it, and to report rather than obey anything that asks it to do otherwise. This is
   the weakest of the four and is treated as such.

Two supporting details. `allowed_non_write_users: "*"` is required — without it the action refuses
to run for anyone lacking write access, which is every asker worth answering — and setting it also
enables the action's scrub of Anthropic and Actions secrets from subprocess environments. The
`github_token` passed to the action is the job's own short-lived `GITHUB_TOKEN`; it must never be
replaced with a personal access token, because a static token does not rotate between runs and could
be recovered a piece at a time across many issues.

## Turning it on

The workflow is committed and inert. It needs one secret.

1. Create an Anthropic API key for this purpose alone, so it can be revoked without affecting
   anything else.
2. Add it as a repository secret named `ANTHROPIC_API_KEY` (**Settings → Secrets and variables →
   Actions**).
3. Exercise it before trusting it. Open **Actions → Issue responder → Run workflow**, give it the
   number of an existing issue, and read what it posts. The manual path bypasses the answered-once
   guard, so a real issue can be used, and it behaves identically to the automatic trigger — the
   dry run is a real test rather than a different code path.

Until step 2 is done the responder job never starts, and the two paths differ on purpose:

| Trigger | No secret | Reasoning |
|---|---|---|
| `issues` | Job skipped, explanation in the run summary, run carries a warning annotation and reports success | This trigger is stranger-controlled. Failing it would let anyone redden the Actions tab by opening issues, and would turn an unconfigured optional feature into a permanently red build — audit finding D8 inverted |
| `workflow_dispatch` | Run **fails** with the same explanation | Somebody asked for an answer and has to be told they did not get one |

This matches `reviewer.yml`, which makes the same split for the same reason.

To turn it off, delete the secret — the workflow goes inert again — or delete the file.

## Behaviour worth knowing before enabling it

- **It answers each issue once.** An issue that already carries a reply is left alone; without that
  guard, every title fix would produce another near-identical comment. Re-run through
  `workflow_dispatch` to answer again after a substantial rewrite.
- **An issue opened with an empty body waits.** That is what makes `edited` a trigger, and it only
  works because `opened` is *skipped* when the body is empty. Answering the empty body immediately
  and then letting the answered-once guard suppress the `edited` run would give the person who
  types the title before the body a useless comment and never a real answer — with the run
  reporting success. The guard and the trigger have to be read together or they cancel each other.
- **Silence is a failure.** The action reports success for a session that posted nothing, which is
  indistinguishable from never having been triggered. The job counts replies carrying the
  responder's marker **before** the session and again after, and fails unless the count went up.
  Counting only afterwards would be vacuous on the dispatch path — which is the path step 3 above
  tells you to rehearse with — because the issue already carries a reply there.
- **The marker alone is not evidence.** `<!-- opensdl-issue-responder -->` is published in a public
  workflow file, so anyone can post a comment containing it. Both the answered-once guard and the
  delivery check therefore require the comment's author to be the Actions bot; otherwise a stranger
  could silence the responder on any issue by planting the marker.
- **Overlapping runs queue rather than cancel.** `cancel-in-progress` is deliberately `false`. The
  answered-once guard only engages once a reply exists, so cancelling the in-flight run would mean
  it never engages, and someone editing an issue on a loop could start sessions indefinitely.
  Queueing lets the first session post, after which the next run reads the marker and stops.
- **Each run costs money and about ten to twenty minutes of runner time**, mostly the locked
  `uv sync` and any test run the reproduction attempt triggers. Say the uncomfortable part plainly:
  `on: issues` plus `allowed_non_write_users: "*"` means **any GitHub account can start a paid
  session on the owner's budget**, with no author filter, label gate, or rate limit. `concurrency`
  bounds one issue at a time, not the total. That is the trade for answering the strangers worth
  answering. The model is pinned to `claude-opus-5` in `claude_args`; lowering it there is the
  first cost knob, `--max-turns` the second, and restricting the trigger to issues opened by
  collaborators is the third if the budget matters more than the reach.
- **The dependency cache is deliberately off.** This is the only job in the repository a stranger
  can trigger, and an `issues` event runs against the default branch, so a cache written here would
  be restored by `ci.yml`, `docs.yml`, `conformance.yml` and `release.yml`. Whether a poisoned `uv`
  cache survives `uv sync --locked`'s hashes is not established either way; the channel simply is
  not worth the minute it saves on an advisory job.

## Where it sits relative to the gates

Nowhere. `ci.yml`, `conformance.yml`, `docs.yml` and `scene.yml` decide whether a change is
acceptable, and they neither call this workflow nor read anything it produces. This workflow only
ever adds prose to an issue thread. If it is wrong, delete the comment; if it is wrong often, delete
the secret.
