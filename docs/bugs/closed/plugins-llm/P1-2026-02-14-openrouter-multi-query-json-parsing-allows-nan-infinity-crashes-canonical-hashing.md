## Summary

LLM JSON content parsing allows `NaN`/`Infinity`, which can pass field validation and later crash canonical hashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_multi_query.py`
- Line(s): 350-372, 388-401
- Function/Method: `_process_single_query`

## Evidence

The transform parses LLM content with plain `json.loads`:

```python
parsed = json.loads(content_str)
```

(`src/elspeth/plugins/llm/openrouter_multi_query.py:350`)

Python JSON accepts non-finite literals (`NaN`, `Infinity`). For `OutputFieldType.NUMBER`, float values are accepted (`src/elspeth/plugins/llm/base_multi_query.py:521-526`), so non-finite floats can enter output row.

Repro (executed locally):
- Content: `{"score": NaN, "rationale":"ok"}`
- With `score` typed as `number`, `_process_single_query` returns `success`
- Later `stable_hash(output_row)` raises `ValueError: Cannot canonicalize non-finite float: nan`

Engine behavior confirms this becomes a hard failure:
- Canonicalization enforced in executor (`src/elspeth/engine/executors/transform.py:286-302`)

## Root Cause Hypothesis

The target transform validates JSON structure/type but does not enforce canonical-number constraints at the external boundary before producing pipeline data.

## Suggested Fix

After parsing LLM content JSON, explicitly reject non-finite floats recursively (for both mapped fields and metadata copied from external response). Return `TransformResult.error(reason="invalid_json_response", ...)` (or equivalent structured reason) rather than emitting non-canonical data.

## Impact

Violates canonical JSON safety requirements and can convert malformed external responses into runtime crashes during hashing, rather than deterministic, auditable transform errors.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter_multi_query.py.md`
- Finding index in source report: 2
- Beads: pending
