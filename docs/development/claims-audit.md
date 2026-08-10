# Claims auditor

A scheduled agent that re-reads the documentation against the code once a week and opens an issue
when the two disagree. It is defined in
`.github/workflows/claims-audit.yml` and is dormant until someone sets an API key.

## Why it exists

Every gate this repository owns checks the code against itself. None of them can check the code
against a sentence. That gap is where this project's failures have actually happened: figures in the
[validation report](validation.md) drifted three separate times, the scene rebuild sat in the
"enforced" column for the project's entire life while its test skipped on every hosted run, and a
specification nothing consulted was wrong in four places while the whole suite passed.

None of those are expressible as a test. They are agreements between prose and code, and the only
way to check one is to read both again. The auditor does that on a schedule so it happens whether or
not anyone remembers to.

## What it checks

Four categories, all of them derived rather than assumed:

- **Figures.** Every number in the documentation that describes this repository — test counts,
  schema counts, skill counts, workspace members, viewer tests, scene nodes and motion checks — is
  recomputed by collecting, counting, or reading what a tool prints.
- **The enforced-versus-asserted split.** For each row of the validation report's *Enforced on every
  change* table, it opens the workflow named in that row and confirms a step really runs the check
  and that the check fails rather than skips when its subject is missing. It reads the *Asserted, not
  verified* list the other way round, because a claim that has quietly become enforced is drift too.
- **Skips.** It runs the suite with skip reasons shown. A test that skips is a green light that
  checked nothing, and documentation calling it verified is a finding.
- **Capability and "what works now" claims, and commands.** Stated shapes are checked against the
  models and the generated schemas rather than against another description; `make` targets are
  checked against the `Makefile`, `opensdl` subcommands and flags against the CLI, and script paths
  against `scripts/`.

The rule the prompt spends most of its words on is the method: a claim counts as checked only when
it has been re-derived from source that was read or a command that was run, and never by finding a
second document that repeats it. The `WebFetch` and `WebSearch` tools are removed for the same
reason: an auditor that can search the internet can "confirm" a claim without ever opening the code.

That is a methodological preference, not a containment property, and the distinction is exactly the
kind this page exists to police. `Bash` is deliberately unrestricted — the auditor's whole job is to
re-run the repository's own commands — so `curl`, `uv` and `gh` all still reach the network. The
runner has egress. Nothing here is a sandbox.

## What it cannot do

- **It cannot write to this repository.** The job that runs the model holds `contents: read` and
  nothing else. It pushes no branch, opens no pull request, edits no file, and cannot merge
  anything. That is a property of the token, not an instruction in the prompt.
- **It cannot escalate.** The workflow passes `github_token:` to the action explicitly. Omitting
  that input would make the action trade the workflow's OIDC token for a GitHub App token carrying
  Contents, Issues and Pull Requests *write*. The job also withholds `id-token: write`, so that
  exchange fails rather than succeeding quietly if the input is ever dropped.
- **It cannot open an issue itself.** The model writes a file. A second job with no model in it
  holds `issues: write`, takes that file as its only input, and makes one API call.
- **It is not a gate.** Nothing about it blocks a pull request or a merge, and it does not replace
  `make lint`. It produces a claim for a human to check, and every finding it reports is required to
  name the command or file that establishes it — so verify before acting on one.
- **It cannot run the Blender rebuild.** `make scene` needs a Blender install this runner does not
  have. The auditor is told that is expected rather than a finding.

One entry that belongs on a different list: the prompt tells the auditor to report rather than
repair, and `Edit` is removed from its tools. With unrestricted `Bash`, `sed -i` and `python` are
still available, so "it edits no file" is a request the model is asked to honour rather than
something the token prevents. It is stated here rather than above because everything above is
enforced by the token and this is not.

## Prompt injection

The model runs shell commands, so anything it reads is a potential instruction.

No stranger's text reaches it. The triggers are `schedule` and `workflow_dispatch` only; the
workflow never runs on `issues`, `issue_comment`, `pull_request`, or `pull_request_target`, so no
issue body, pull-request description, or comment written by anyone is ever part of the prompt. Both
triggers require write access to reach — GitHub enforces that for a dispatch, and a schedule has no
external actor. What the auditor does read is a checkout of the default branch, which already passed
review to get there.

Its output cannot become a command either. The report leaves the job as a file, and the publishing
job builds the API request with `jq --rawfile`, so the report is a JSON string value rather than
text spliced into a shell script or expanded by a workflow expression.

The residual risk is worth stating accurately, because it is larger than a wasted afternoon.
Someone who gets adversarial text merged into a docstring could steer the audit's conclusions — and
because `Bash` is unrestricted and `ANTHROPIC_API_KEY` sits in the environment of the step that runs
the model, a subverted session could also write the key into `report.md`. This workflow publishes
that file to a **public issue** and to the run summary. Actions secret masking does not apply to an
API request body, and any encoding would defeat it regardless.

They still cannot reach the repository, because the token cannot write. What they can do is burn the
credential. Use an Anthropic key dedicated to this workflow so it can be revoked on its own, and
treat an audit whose findings read strangely as a reason to rotate it.

The checkout is pinned to the default branch rather than left to the event. A `workflow_dispatch`
otherwise runs against whichever ref the dispatcher chose, which would let a collaborator run
unreviewed code with the key in scope — and would quietly falsify the paragraph above about the
trust boundary being "already passed review to get there".

## Failure behaviour

The auditor fails closed, on the same principle as the scene workflow's `pytest_no_skip`: a check
that did not run must never read as one that passed.

| Situation | What happens |
|---|---|
| No `ANTHROPIC_API_KEY` secret, scheduled run | The audit job is **skipped**, the run summary says the auditor is dormant, and the run carries a warning annotation. Be precise: the run itself still *concludes* green, because a skipped job is not a failed one. What does not happen is a green `audit` job for an audit that never ran. Failing the schedule instead would make an unconfigured optional feature into a permanently red weekly build — D8 inverted. |
| No `ANTHROPIC_API_KEY` secret, manual run | The run **fails**. Somebody asked for an audit deliberately, so silence would be a lie. |
| The model produces no verdict or no report | The run **fails**. An audit that produced nothing did not happen. |
| The verdict is not exactly `clean` or `findings` | The run **fails**. |
| Turn limit reached | The prompt requires `report.md` to be written first and `verdict.txt` last, and a step checks that the verdict is no older than the report. A session that recorded a verdict early and then ran out of turns fails there. Without that ordering check, "no verdict is written" would depend on the model's own sequencing — the one thing this design is otherwise careful never to rely on. |
| `timeout-minutes` reached | The run is **cancelled**, which is not the same as failed. It is visible in the Actions tab but does not send a failure notification. |
| The report exceeds the issue-body limit | It is cut at 60000 bytes, trimmed to the last complete line **when there is one**, and the run fails if the cut leaves an empty body. A report with no newline in its first 60000 bytes previously became a 30-byte issue containing only the truncation notice. |
| Verdict is `clean` | No issue. The report goes to the run summary, so a clean audit still leaves evidence it ran. |
| Verdict is `findings` | An issue is opened, and the full report is attached to the run as an artifact for 30 days. |

Findings issues are opened one per run and are not coalesced. An audit nobody has dealt with should
stay visible rather than being quietly folded into an older thread. The tension is real and worth
watching: an unaddressed drift opens a fresh issue every Monday, and a weekly recurring issue trains
the same reflex as an empty one. If that starts happening, the fix is to deal with the finding or
turn the schedule off, not to widen the auditor's tolerance.

## Turning it on

1. Add a repository secret named `ANTHROPIC_API_KEY` (**Settings → Secrets and variables → Actions**).
   Until it exists, the workflow is inert — every scheduled run skips the audit and says so.
2. Exercise it deliberately before trusting it. Run **Actions → Claims audit → Run workflow** with
   **dry run** ticked. The audit runs in full and writes its report to the run summary, but opens no
   issue. That is the intended way to read what it would have said.
3. Run it once more without **dry run** when the report looks sound, and let the Monday schedule take
   over.

The API calls are billed to the key's account. `--max-turns` in the workflow bounds the work in a
single run; the schedule bounds how often that happens.

To turn it off again, delete the secret — the workflow goes dormant on its own — or remove the
`schedule:` trigger to keep it available for manual runs only.
