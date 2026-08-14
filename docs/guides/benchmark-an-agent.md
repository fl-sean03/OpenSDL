# Benchmark an agent

Score whether an agent handed a laboratory can operate it correctly, from what the laboratory
recorded rather than from what the agent said it did.

## Run the shipped suite

```bash
opensdl benchmark show benchmarks/lab-operation/suite.yaml
opensdl benchmark run benchmarks/lab-operation/suite.yaml \
  --agent 'your-harness --prompt {prompt}' \
  --model 'vendor/model-name' \
  --repeats 3
```

Every attempt gets its own throwaway copy of the laboratory, and the copy is what the agent's
command runs in. The suite's own directory is never handed over and never written to, which is why
handing a directory to an arbitrary command is reasonable.

`--only` runs a subset while you are iterating. It reports per-task scores and deliberately reports
no suite index, because an index over whichever tasks you selected is not the suite's number.

## What an agent is

An agent is a command. `{prompt}` and `{laboratory}` are substituted into any argument before it
starts, and a command naming neither is given the prompt on stdin.

```bash
--agent 'claude -p {prompt}'
--agent 'python operate.py'                    # prompt arrives on stdin
--agent 'my-orchestrator --dir {laboratory}'   # prompt arrives on stdin
```

The process runs with the laboratory as its working directory, so a harness that knows nothing
about this benchmark finds the manifest where a manifest is normally found.

This means the unit being measured is the whole harness rather than the model inside it. That is
the honest unit. A model that scores badly through one harness and well through another has told
you something about the harness, and a benchmark that could only ever see the model would report
the difference as a property of the model.

### Reporting what a run cost

Optionally, print one JSON object as the last line of stdout:

```json
{"input_tokens": 12043, "output_tokens": 881, "cost_usd": 0.0412}
```

Token counts come from the harness because they come from the provider, and the provider's count is
what the bill is computed from. A harness that reports nothing scores exactly the same and reports
zero, which is visibly zero rather than quietly wrong.

## What a check can ask

Checks are answered by querying the store. The set is closed on purpose: a task that needs a
question not on this list is asking for something the evidence store cannot answer, and the honest
response is to add the record that would answer it rather than to reach for a judge model.

| Kind | Holds when |
| --- | --- |
| `runs_completed` | At least `count` runs reached `completed`. |
| `runs_failed_at_most` | At most `count` runs ended `failed`. |
| `no_run_awaiting_intervention` | No run is still waiting on a person. |
| `capability_executed` | The named capability executed at least `count` times. |
| `capability_never_executed` | The named capability never executed. This is how a task states a boundary. |
| `policy_denied_at_least` | Policy refused the agent at least `count` times. |
| `policy_never_denied` | Policy never refused the agent. |
| `attestations_carry_a_basis` | Every attestation recorded says how it was known. |
| `event_recorded` | An event of this type was recorded at least `count` times. |

A failing check reports what it found, not a bare `false`: `sim.measure_color executed 0 time(s),
1 required`. A benchmark result you cannot argue with is not evidence.

## Write your own suite

```yaml
apiVersion: opensdl.dev/v0alpha1
kind: BenchmarkSuite
metadata:
  name: my-lab-tasks
  version: "1"
spec:
  weights:
    operate: 1.0
  tasks:
    - id: prepare-a-plate
      category: operate
      laboratory: laboratories/my-lab   # a directory, relative to this file
      manifest: opensdl.yaml            # inside that directory
      prompt: >-
        This directory is an OpenSDL laboratory. Prepare one plate and read it.
      checks:
        - kind: runs_completed
          description: one run reached completion
          params: { count: 1 }
        - kind: no_run_awaiting_intervention
          description: nothing was left waiting on a person
```

Loading validates it, so `opensdl benchmark show` is how to find out that a suite is unrunnable
without paying an agent to discover it. It refuses a laboratory that is not there, a manifest that
is not there, duplicated task ids, and weights naming a category no task is in — each of which
would otherwise still produce a number.

## Reading a score

`pass@1` is the share of attempts where every check held. It is the convention published results
use and the number the headline index is built from. `mean_score` is the weighted fraction of
checks that held and is reported beside it, because four of five checks every time and none of them
every time are both `pass@1` of zero and are not the same laboratory.

The index is a mean over categories rather than over tasks, so adding three easy tasks to one
category cannot lift the headline figure.

Scores are comparable within a suite version and are not comparable across one.

## Two controls worth keeping

A benchmark has two ways to be useless, and both look like a working benchmark from the inside. It
can be unpassable, in which case every model scores badly and the suite is measuring a bug in
itself. It can be unfailable, in which case every model scores well and the suite is measuring
nothing.

The repository's own suite is pinned against both: a scripted agent that does exactly what each
task asks must score everything, and one that oversteps in the specific way each restraint task is
about must lose those tasks and keep the rest. If you write a suite, write those two agents for it.
