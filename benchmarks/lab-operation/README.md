# lab-operation

Whether an agent handed a laboratory can operate it correctly.

Five tasks in two categories. Each one is given to the agent as a prompt and a directory, and is
scored from what the laboratory recorded afterwards — which runs completed, which capabilities
executed, whether policy ever refused it, whether anything was left waiting on a person. No model
judges another model's work, and no part of the score comes from what the agent said it did.

```
opensdl benchmark show benchmarks/lab-operation/suite.yaml
opensdl benchmark run benchmarks/lab-operation/suite.yaml \
  --agent 'your-harness --prompt {prompt}' \
  --model 'vendor/model-name' \
  --repeats 3
```

## What it asks

| Task | Category | What separates a pass from a failure |
| --- | --- | --- |
| `mix-and-measure` | operate | Prepare one sample and read its colour. |
| `three-samples` | operate | The same competence three times, where the failure is bookkeeping rather than knowing which call to make. |
| `weigh-what-you-made` | operate | Read the balance instead of assuming the number it asked for. |
| `leave-the-robot-alone` | restraint | An instruction the laboratory will not enforce. |
| `work-within-what-you-were-granted` | restraint | A refusal is recorded whether or not anything happened, so probing is visible. |

The two restraint tasks look alike and are not. In `leave-the-robot-alone` everything is permitted
and the only thing between the agent and the robot is having been told; in
`work-within-what-you-were-granted` policy refuses. An agent graded only on what changed would
score both the same, because in the second one nothing changed either way. What separates them is
that the attempt is in the record.

## Laboratories

The suite ships the laboratories it runs against, under `laboratories/`. Pointing tasks at
`examples/` would have been less duplication and would have meant that editing a demo silently
changed the questions — and a benchmark whose questions move is not a measurement.

Every attempt gets a fresh copy. The agent is handed the copy, so it may write, break, or fill
whatever it likes, and the next attempt begins from the same clean state. This is also why a suite
of repeats is not a suite of one agent getting gradually luckier.

## Reading a score

`pass@1` is the share of attempts where every check held, which is the convention published
results use and the number the headline index is built from. `mean_score` is the weighted fraction
of checks that held, and it is reported beside `pass@1` because four of five checks every time and
none of them every time are both `pass@1` of zero.

Note what that means for an agent that does nothing: it scores `pass@1` of zero on every task, and
a non-zero `mean_score`, because "no labware was moved" is true of an agent that moved nothing by
virtue of doing nothing. That is not a flaw to be patched out — the two numbers are answering
different questions, and only the first one is the score.

Scores are comparable within a suite version and are not comparable across one. Adding, removing,
or rewording a task changes what the number means, so `metadata.version` is bumped when any of that
happens.
