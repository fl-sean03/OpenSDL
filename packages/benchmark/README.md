# opensdl-benchmark

Deterministic scoring for whether an agent can operate a laboratory.

A task states what the agent is asked to do and what must be true of the laboratory afterwards. The
checks are answered from the evidence store — runs, tasks, events, attestations — so a result is a
query rather than an opinion, and no judge model is involved.

## What it is made of

- `models.py` — what a task asks (`BenchmarkTask`, `Check`) and what a result says
  (`TaskScore`, `BenchmarkReport`). A suite (`BenchmarkSuite`) is the set of tasks plus how the
  headline index is weighted.
- `grading.py` — one function per check kind, each a query against a store. Given the same store,
  grading returns the same answer forever, at no cost, without a network.
- `running.py` — hands an agent a fresh copy of a laboratory, lets it work, then grades what it
  left behind. The agent is injected; this package cannot start one.
- `suites.py` — reads a suite from a file, and refuses one that cannot be run before anything is
  run.
- `agents.py` — turns a command line into an agent, so the thing being measured can be any
  harness rather than only a Python one.

## The agent is injected

`Agent` is `(BenchmarkTask, Path) -> Awaitable[AgentOutcome]` and nothing here knows how one is
built. That is deliberate twice over: a benchmark tied to one provider measures that provider, and
a benchmark that cannot be driven by a scripted agent has no control to check itself against.

`AgentOutcome` carries what the agent spent and whether it fell over. What it *achieved* is
deliberately not on it — that is read from the laboratory, and an agent that could report its own
success would be grading itself.

## Why not a judge model

Judge-based grading exists because most tasks have no ground truth to check against. This domain
has one. A run either reached `completed` or did not; policy either refused something or did not;
an attestation either carries a basis or does not. Using a model where a database will answer would
be slower, dearer, and less repeatable, and it would put the benchmark's verdict inside the same
system it is supposed to be measuring.

The shipped suite is at [`benchmarks/lab-operation`](../../benchmarks/lab-operation/README.md).
