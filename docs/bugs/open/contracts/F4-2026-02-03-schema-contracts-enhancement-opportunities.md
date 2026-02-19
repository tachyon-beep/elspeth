## Summary

Enhancement opportunities identified during expert review of schema contracts.

## Severity

- Severity: minimal
- Priority: P4
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-ande

## Enhancement List

**Code Clarity:**
- [ ] Add ANY_TYPE constant instead of using bare 'object' (schema_contract.py)
- [ ] Rename `get_field()` to `get_field_or_none()` to make optional return explicit

**API Completeness:**
- [ ] Add `__iter__` to PipelineRow for dict-like iteration
- [ ] Add `__setitem__` and `__delitem__` that raise TypeError (explicit immutability)

**Richer Return Types:**
- [ ] Consider ValidationResult dataclass instead of bare list
  - Distinguishes 'passed' vs 'nothing to check'
  - Includes fields_checked count

**Documentation:**
- [ ] Document merge behavior when original_names differ (currently uses first contract's)

**Found by:** Type Design Analyzer, Coverage Gap Analyst agents

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `contracts/schema_contract.py`
- `contracts/pipeline_row.py`
