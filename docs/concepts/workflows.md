# Workflows and campaigns

A workflow is a DAG of capability calls. Steps declare dependencies and inputs. Values can reference workflow inputs and predecessor outputs:

```yaml
sample_id: ${inputs.sample_id}
rgb: ${steps.measure.output.rgb}
```

Independent steps in the same topological layer may execute concurrently. Every task has durable state, attempts, inputs, outputs, errors, and events.

A campaign repeatedly selects workflow inputs, executes the workflow, evaluates an output, records a decision, and updates its optimizer. The reference grid optimizer is intentionally simple; organizations can install domain-specific optimization packages.
