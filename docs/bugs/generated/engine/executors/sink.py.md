## Summary

`SinkExecutor.write()` never validates `SinkWriteResult.diversions`, so a sink that returns an out-of-range or duplicate `row_index` can silently produce the wrong terminal audit record for a token.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/sink.py
- Line(s): 245-247, 354, 410-411, 583-585, 615-632
- Function/Method: `SinkExecutor.write`

## Evidence

`RowDiversion` only enforces `row_index >= 0`; it does not enforce `row_index < batch_size` or uniqueness:

```python
# /home/john/elspeth/src/elspeth/contracts/diversion.py:34-40
row_index: int

def __post_init__(self) -> None:
    require_int(self.row_index, "row_index", min_value=0)
```

`SinkExecutor.write()` then immediately collapses diversion indices through a `set` and a `dict`:

```python
# /home/john/elspeth/src/elspeth/engine/executors/sink.py:245-247
diverted_indices = {d.row_index for d in diversions}
primary_tokens = [(token, i) for i, token in enumerate(tokens) if i not in diverted_indices]
diverted_tokens = [(token, i) for i, token in enumerate(tokens) if i in diverted_indices]

# /home/john/elspeth/src/elspeth/engine/executors/sink.py:354
diversion_by_index = {d.row_index: d for d in diversions}
```

What this does:
- Duplicate diversion entries for the same `row_index` are silently deduplicated.
- An out-of-range diversion index is silently ignored during partitioning.
- Later logic uses `diversion_by_index[idx]`, so the last duplicate wins and earlier reasons disappear.

What it should do:
- Crash immediately on invalid diversion metadata from a system-owned sink plugin.
- Reject duplicate indices and indices outside `0..len(tokens)-1` before recording any token outcomes.

Why this is a real audit bug:
- If a sink incorrectly returns `RowDiversion(row_index=99, ...)` for a 2-row batch, `diverted_tokens` is empty, both real tokens go down the primary-success path, and `record_token_outcome(... outcome=pending_outcome.outcome ...)` records them as completed/quarantined even though the sink reported a diversion.
- If a sink returns the same `row_index` twice with different reasons, one diversion reason is silently discarded and the surviving reason is arbitrary by list order.

This violates the executor’s own responsibility to keep token terminal states accurate and complete in the audit trail.

## Root Cause Hypothesis

The executor trusts `SinkWriteResult.diversions` as already well-formed and uses container deduplication as an implementation convenience. That turns a plugin contract violation into silent audit corruption instead of an immediate crash.

## Suggested Fix

Validate `diversions` immediately after `sink.write()` returns and before any partitioning or outcome recording.

Suggested checks:
- Every `row_index` must satisfy `0 <= row_index < len(tokens)`.
- No duplicate `row_index` values.
- Optionally, sort or preserve original order only after validation.

Example shape:

```python
seen: set[int] = set()
for diversion in diversions:
    idx = diversion.row_index
    if idx >= len(tokens):
        raise PluginContractViolation(
            f"Sink '{sink.name}' returned diversion row_index={idx} for batch size {len(tokens)}."
        )
    if idx in seen:
        raise PluginContractViolation(
            f"Sink '{sink.name}' returned duplicate diversion for row_index={idx}."
        )
    seen.add(idx)
```

## Impact

A sink plugin bug can currently cause:
- silent data loss in diversion accounting,
- incorrect `COMPLETED` or other terminal outcomes for rows that were not actually written,
- overwritten diversion reasons,
- broken explainability for affected tokens.

That is an audit-trail integrity failure in the target file.
---
## Summary

The failsink branch bypasses `SinkExecutor`’s centralized sink input validation and required-field enforcement, so failsink writes can ignore `validate_input` and `declared_required_fields` entirely.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/sink.py
- Line(s): 206-225, 423-426
- Function/Method: `SinkExecutor.write`

## Evidence

The sink protocol explicitly says both required-field enforcement and input validation are centralized in `SinkExecutor`:

```python
# /home/john/elspeth/src/elspeth/contracts/plugin_protocols.py:440-448
# Required-field enforcement (centralized in SinkExecutor).
declared_required_fields: frozenset[str]

# Input validation (centralized in SinkExecutor).
validate_input: bool
```

The primary sink path honors that contract:

```python
# /home/john/elspeth/src/elspeth/engine/executors/sink.py:206-225
if sink.validate_input:
    ...
    sink.input_schema.model_validate(row)

if sink.declared_required_fields:
    ...
    raise PluginContractViolation(...)
```

But the failsink path skips the same checks and calls the plugin directly:

```python
# /home/john/elspeth/src/elspeth/engine/executors/sink.py:423-426
failsink._reset_diversion_log()
try:
    failsink_write_result = failsink.write(enriched_rows, ctx)
    failsink.flush()
```

The allowed failsink implementations rely on executor-centralized enforcement too:

```python
# /home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:233-255
self.declared_required_fields = self._schema_config.get_effective_required_fields()
...
# ValidationError: If validate_input=True and a row fails validation.
```

```python
# /home/john/elspeth/src/elspeth/plugins/sinks/json_sink.py:240-259
self.declared_required_fields = self._schema_config.get_effective_required_fields()
...
# ValidationError: If validate_input=True and a row fails validation.
```

What the code does:
- Primary sink rows are schema-checked before `write()`.
- Failsink rows are not schema-checked at all.

What it should do:
- Apply the same centralized validation/required-field checks to `failsink` before `failsink.write()`.

## Root Cause Hypothesis

The failsink path was added as a special-case branch and reused the raw plugin call without reusing the executor’s pre-write validation block. That left the primary sink compliant with the protocol while the secondary sink path quietly diverged from it.

## Suggested Fix

Before `failsink.write(enriched_rows, ctx)`, run the same validation logic currently used for `sink`:
- `failsink.input_schema.model_validate(row)` when `failsink.validate_input` is true.
- required-field presence checks against `failsink.declared_required_fields`.

It would be safest to extract the existing pre-write checks into a small helper used by both the primary and failsink paths.

## Impact

A configured failsink can currently receive rows that violate its declared schema without the executor noticing. That can lead to:
- skipped contract enforcement,
- silent missing required fields in failsink output,
- less actionable downstream exceptions,
- audit records claiming a diverted row was successfully written to the failsink even though the executor skipped the contract checks it promises to enforce.
