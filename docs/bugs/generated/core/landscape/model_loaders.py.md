## Summary

`TokenOutcomeLoader` accepts structurally impossible `token_outcomes` rows, so corrupted audit data can be read back as valid lineage instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/core/landscape/model_loaders.py`
- Line(s): 468-514
- Function/Method: `TokenOutcomeLoader.load`

## Evidence

`TokenOutcomeLoader.load()` validates only `is_terminal` and the enum conversion:

```python
outcome = RowOutcome(row.outcome)
is_terminal = row.is_terminal == 1
if is_terminal != outcome.is_terminal:
    raise AuditIntegrityError(...)
return TokenOutcome(
    ...
    sink_name=row.sink_name,
    batch_id=row.batch_id,
    fork_group_id=row.fork_group_id,
    join_group_id=row.join_group_id,
    expand_group_id=row.expand_group_id,
    error_hash=row.error_hash,
    context_json=row.context_json,
    expected_branches_json=row.expected_branches_json,
)
```

Source: [model_loaders.py](/home/john/elspeth/src/elspeth/core/landscape/model_loaders.py#L468)

But the write path treats these fields as mandatory parts of the token-outcome contract:

- `COMPLETED` and `ROUTED` require `sink_name`
- `FORKED` requires `fork_group_id`
- `FAILED` and `QUARANTINED` require `error_hash`
- `CONSUMED_IN_BATCH` and `BUFFERED` require `batch_id`
- `COALESCED` requires `join_group_id`
- `EXPANDED` requires `expand_group_id`

Source: [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L190)

```python
if outcome == RowOutcome.COMPLETED:
    if sink_name is None:
        raise ValueError("COMPLETED outcome requires sink_name ...")
elif outcome == RowOutcome.ROUTED:
    if sink_name is None:
        raise ValueError("ROUTED outcome requires sink_name ...")
...
elif outcome == RowOutcome.CONSUMED_IN_BATCH:
    if batch_id is None:
        raise ValueError("CONSUMED_IN_BATCH outcome requires batch_id ...")
```

The property tests enforce the same contract on writes:

Source: [test_landscape_recording_properties.py](/home/john/elspeth/tests/property/core/test_landscape_recording_properties.py#L224), [test_landscape_recording_properties.py](/home/john/elspeth/tests/property/core/test_landscape_recording_properties.py#L240), [test_landscape_recording_properties.py](/home/john/elspeth/tests/property/core/test_landscape_recording_properties.py#L268)

So if a bad row is inserted by corruption, manual SQL, or a future buggy migration, reads will not fail fast. For example, a row with `outcome='routed'`, `is_terminal=1`, and `sink_name=NULL` will deserialize successfully even though the repository explicitly defines that state as impossible.

## Root Cause Hypothesis

The loader implemented only the generic invariant (`outcome` must agree with `is_terminal`) and omitted the outcome-specific invariants already defined in the write path. That creates an asymmetry: writes reject impossible token outcomes, but reads do not, violating the Tier 1 rule that our audit DB must crash on anomalies.

## Suggested Fix

Mirror the token-outcome contract inside `TokenOutcomeLoader.load()` and raise `AuditIntegrityError` when required fields are missing.

A straightforward fix in the target file is a `match`/`if` block after `outcome` is parsed:

```python
if outcome in {RowOutcome.COMPLETED, RowOutcome.ROUTED} and row.sink_name is None:
    raise AuditIntegrityError(...)
if outcome == RowOutcome.FORKED and row.fork_group_id is None:
    raise AuditIntegrityError(...)
if outcome in {RowOutcome.FAILED, RowOutcome.QUARANTINED} and row.error_hash is None:
    raise AuditIntegrityError(...)
if outcome in {RowOutcome.CONSUMED_IN_BATCH, RowOutcome.BUFFERED} and row.batch_id is None:
    raise AuditIntegrityError(...)
if outcome == RowOutcome.COALESCED and row.join_group_id is None:
    raise AuditIntegrityError(...)
if outcome == RowOutcome.EXPANDED and row.expand_group_id is None:
    raise AuditIntegrityError(...)
```

If `expected_branches_json` is considered audit-critical for `FORKED`/`EXPANDED`, validate that here too, because the specialized write paths populate it in [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L516) and [data_flow_repository.py](/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L728).

## Impact

Bad `token_outcomes` rows can survive deserialization and appear as legitimate audit facts during `explain`, export, recovery analysis, or any query path using this loader. That weakens the audit trail’s “crash on our-data anomalies” guarantee and can silently hide lineage corruption instead of surfacing it immediately.
