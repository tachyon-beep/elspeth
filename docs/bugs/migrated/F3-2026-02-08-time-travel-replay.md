## Summary

Leverage ELSPETH's complete audit trail to replay historical runs with modified logic. Answer: "What would have happened if we changed the threshold / swapped the model / updated the rules?"

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.5

## Why This Is Unique to ELSPETH

ELSPETH already captures everything needed for deterministic replay:
- Every source row with content hash (rows table)
- Every transform input/output with hashes (node_states table)
- Every external call request AND response (calls table + payload store)
- Every routing decision with reason (routing_events table)
- Full config snapshot per run (runs.settings_json)
- Reproducibility grading per node

## Core Capability

```bash
# Replay with different gate threshold
elspeth replay abc123 --override 'gates[0].condition=row["score"] >= 0.6'

# Replay with recorded LLM responses (deterministic, no API calls)
elspeth replay abc123 --use-recorded-calls

# Replay with live LLM calls (new prompt template)
elspeth replay abc123 --live-calls --override 'transforms[0].options.prompt_template=new_prompt.j2'
```

## Diff Engine

- Compare original vs replay: which rows changed outcome?
- Per-row diff with reasons
- Aggregate diff: "847 unchanged, 23 rerouted, 4 newly quarantined"

## Use Cases

- Regulatory impact analysis
- Model comparison (same data through model A vs B)
- Threshold tuning
- Incident investigation
- Audit defense (prove same inputs + config = same outputs)

## Dependencies

- Parent: `w2q7` — ELSPETH-NEXT epic
