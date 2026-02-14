## Summary

`OpenRouterLLMTransform._process_row()` reparses external JSON with permissive `response.json()` and does not validate `usage`/numeric finiteness, allowing malformed Tier-3 data (e.g., `NaN`) to enter success output and later crash canonical hashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter.py`
- Line(s): `592-593`, `633-635`, `652`, `659`
- Function/Method: `_process_row`

## Evidence

`openrouter.py` reparses HTTP body using permissive JSON parsing:

```python
# src/elspeth/plugins/llm/openrouter.py:592-593
data = response.json()
```

Then it accepts and forwards `usage` without structure/finiteness validation:

```python
# src/elspeth/plugins/llm/openrouter.py:635
usage = data.get("usage") or {}
# src/elspeth/plugins/llm/openrouter.py:652
output[f"{self._response_field}_usage"] = usage
```

Executor hashes successful output and converts canonicalization failures into hard plugin-contract crashes:

```python
# src/elspeth/engine/executors/transform.py:290-302
result.output_hash = stable_hash(result.row)
...
raise PluginContractViolation(...)
```

Canonical layer explicitly rejects non-finite floats:

```python
# src/elspeth/core/canonical.py:60-63
if math.isnan(obj) or math.isinf(obj):
    raise ValueError(...)
```

I also verified locally that Python JSON accepts `NaN` while canonical hashing rejects it:
- `json.loads('{"usage":{"prompt_tokens":NaN}}')` -> `nan`
- `stable_hash({"usage":{"prompt_tokens": float("nan")}})` -> `ValueError`

So malformed external response data can be treated as transform success, then fail as an internal plugin-contract crash.

## Root Cause Hypothesis

The transform validates only JSON syntax/shape partially, but not numeric finiteness or `usage` schema before promoting external response fields into Tier-2 output. It also bypasses the stricter non-finite handling logic already present in the audited HTTP client path.

## Suggested Fix

In `openrouter.py` boundary handling, add strict response validation before building output:
1. Parse from `response.text` with non-finite rejection (or equivalent strict check).
2. Enforce `data` is `dict`.
3. Validate `usage` is either `None` or `dict[str, int]` with finite integer values.
4. Validate `model` is `str` when present.
5. Return `TransformResult.error(..., retryable=False)` for malformed boundary data instead of letting it reach hashing.

## Impact

Malformed provider payloads can crash the pipeline as `PluginContractViolation` instead of producing attributable transform error results for external-data faults. This violates the Tier-3 boundary rule ("validate immediately") and can turn recoverable row-level external-data issues into run-level failures.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter.py.md`
- Finding index in source report: 1
- Beads: pending
