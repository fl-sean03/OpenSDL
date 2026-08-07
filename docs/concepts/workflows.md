# Workflows and campaigns

A workflow is a DAG of capability calls. Steps declare dependencies and inputs. Values can reference workflow inputs and predecessor outputs:

```yaml
sample_id: ${inputs.sample_id}
rgb: ${steps.measure.output.rgb}
```

Independent steps in the same topological layer may execute concurrently. Every task has durable state, attempts, inputs, outputs, errors, and events.

## A run's workflow of record

Submitting a workflow creates a run whose `RunCreated` event embeds the whole definition and the
canonical digest of that embedded document. That is the run's workflow of record, and it is what the
run is evidence about.

Resubmitting under an existing run identifier is a resume, so it must present the same definition.
A different one is refused, because running new steps under an existing identifier would leave the
run's own record describing work it did not do while its events named the operator who submitted the
original. A repaired workflow is a new execution: submit it with `supersedes` naming the run it
replaces, and the link is recorded on both.

A run is also claimed once. Moving it to `running` is a single conditional write at the store, so
two callers cannot both start the same run, and a run already recorded `running` is reconciled
before it can be resumed.

A campaign repeatedly selects workflow inputs, executes the workflow, evaluates an output, records a decision, and updates its optimizer. The reference grid optimizer is intentionally simple; organizations can install domain-specific optimization packages.
