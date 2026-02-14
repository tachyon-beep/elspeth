## Summary

`KeywordFilterConfig` allows empty regex entries (`""`) in `blocked_patterns`; empty regex matches every string, so benign rows are all blocked.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — failure mode is fail-closed (blocks all rows), not fail-open; operationally noisy, not a security risk

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/keyword_filter.py`
- Line(s): 69-80, 124, 166-177
- Function/Method: `KeywordFilterConfig.validate_patterns_not_empty()`, `KeywordFilter.process()`

## Evidence

The validator only checks list length:

```python
if not v:
    raise ValueError("blocked_patterns cannot be empty")
```

It does not reject empty pattern elements. `""` compiles and `re.Pattern.search("")` semantics mean zero-length match at position 0 for any string, so line 166 always matches and line 168 always returns `TransformResult.error(...)`.

I verified behavior at runtime:

- `KeywordFilter({"blocked_patterns": [""], ...})` constructs successfully.
- Processing `{"content": "benign text"}` returns error with `matched_pattern: ""`, `match_position: 0`, `match_length: 0`.

Test gap corroboration: `tests/unit/plugins/transforms/test_keyword_filter.py:90-102` only checks empty list, not empty elements.

## Root Cause Hypothesis

Validation is applied at container level (`list` non-empty) but not at element level, allowing a syntactically valid yet semantically unsafe regex.

## Suggested Fix

Strengthen `blocked_patterns` validation to reject empty entries (and optionally whitespace-only entries):

```python
@field_validator("blocked_patterns")
@classmethod
def validate_patterns_not_empty(cls, v: list[str]) -> list[str]:
    if not v:
        raise ValueError("blocked_patterns cannot be empty")
    for i, pattern in enumerate(v):
        if pattern == "":
            raise ValueError(f"blocked_patterns[{i}] cannot be empty")
    return v
```

## Impact

A single misconfigured pattern can force every row into error routing/quarantine, creating systemic false positives, operational disruption, and misleading audit records (`blocked_content` for benign rows).
