# Phase 3: Field Collision Prevention — Silent Data Loss

**Date:** 2026-02-15
**Status:** Approved
**Branch:** RC3.1-bug-hunt

## Problem

Transforms that enrich rows with new fields silently overwrite existing input fields when names collide. This is silent data loss — the audit trail records the overwritten value as if it were the original, destroying traceability.

**Example:** A source row has field `llm_response` (from a previous pipeline stage or source data). An LLM transform configured with `response_field: llm_response` silently overwrites it. The audit trail shows the LLM output — the original value is gone with no record it ever existed.

## Scope

Six bugs across the transform plugin layer. The engine layer (coalesce, schema contracts, gates, fork/join) and source layer already have collision detection.

| # | Bug | Files | Risk |
|---|-----|-------|------|
| 1 | LLM single-query `response_field` overwrites input row fields | `plugins/llm/base.py` | P1 |
| 2 | LLM batch transforms same collision | `plugins/llm/azure_batch.py`, `plugins/llm/openrouter_batch.py` | P1 |
| 3 | Multi-query merge overwrites input row fields | `plugins/llm/base_multi_query.py` | P1 |
| 4 | Web scrape hardcoded fields overwrite row fields | `plugins/transforms/web_scrape.py` | P1 |
| 5 | JSON explode `output_field` + hardcoded `item_index` overwrite | `plugins/transforms/json_explode.py` | P1 |
| 6 | Batch replicate hardcoded `copy_index` overwrite | `plugins/transforms/batch_replicate.py` | P1 |

## Design Decisions

1. **On collision: fail the row.** Return `TransformResult.error()` with collision details. The row gets quarantined with a clear audit trail. Rationale: silent overwrite violates the auditability standard — "if it's not recorded, it didn't happen."

2. **Shared utility function.** A single `detect_field_collisions()` helper that all transforms call. DRY, consistent error messages, easy to test.

3. **Location: `plugins/transforms/field_collision.py`.** Lives near consumers (all affected code is in `plugins/`). Clean namespace, dedicated module.

## Shared Utility

```python
# plugins/transforms/field_collision.py

from collections.abc import Iterable


def detect_field_collisions(
    existing_fields: set[str],
    new_fields: Iterable[str],
) -> list[str] | None:
    """Detect field name collisions between existing row fields and new fields.

    Args:
        existing_fields: Field names already present in the row.
        new_fields: Field names the transform intends to add.

    Returns:
        Sorted list of colliding field names, or None if no collisions.
    """
    collisions = sorted(f for f in new_fields if f in existing_fields)
    return collisions or None
```

All transforms call this before writing fields. On collision:

```python
collisions = detect_field_collisions(set(row_data.keys()), added_fields)
if collisions is not None:
    return TransformResult.error(
        {
            "reason": "field_collision",
            "collisions": collisions,
            "message": (
                f"Transform output fields {collisions} already exist in input row. "
                "This would silently overwrite source data."
            ),
        },
        retryable=False,
    )
```

## Per-Bug Fix

### Bug 1: LLM single-query (base.py)

**Location:** `plugins/llm/base.py`, before line 352.

Build list of all field names the transform will write:
- `self._response_field`
- `f"{self._response_field}_model"`
- `f"{self._response_field}_usage"`
- `f"{self._response_field}_template_hash"`
- `f"{self._response_field}_variables_hash"`
- `f"{self._response_field}_template_source"`
- `f"{self._response_field}_lookup_hash"`
- `f"{self._response_field}_lookup_source"`
- `f"{self._response_field}_system_prompt_source"`

Call `detect_field_collisions()` against `row_data.keys()`.

### Bug 2: LLM batch (azure_batch.py, openrouter_batch.py)

Same pattern as Bug 1. Each batch transform has a result-building section that adds response_field + metadata fields to each output row. Add collision check before the first field write in each row's processing.

For batch transforms, the check happens per-row in the result assembly loop. On collision, the individual row gets an error result (not the entire batch).

### Bug 3: Multi-query merge (base_multi_query.py)

**Location:** `plugins/llm/base_multi_query.py`, line 349-352.

Check each `result.row` against the **original input row fields** before `output.update()`:

```python
input_field_names = set(row_data.keys())
for result in results:
    if result.row is not None:
        collisions = detect_field_collisions(input_field_names, result.row.keys())
        if collisions is not None:
            return TransformResult.error(...)
        output.update(result.row)
```

Note: inter-query output collisions are already prevented by config-time `validate_multi_query_key_collisions()`.

### Bug 4: Web scrape (web_scrape.py)

**Location:** `plugins/transforms/web_scrape.py`, before line 242.

Check both configurable and hardcoded fields:
- `self._content_field` (configurable)
- `self._fingerprint_field` (configurable)
- `"fetch_status"`, `"fetch_url_final"`, `"fetch_request_hash"`, `"fetch_response_raw_hash"`, `"fetch_response_processed_hash"` (hardcoded)

### Bug 5: JSON explode (json_explode.py)

**Location:** `plugins/transforms/json_explode.py`, before line 177.

Check against `base` dict (row minus the array field):
- `self._output_field` (configurable)
- `"item_index"` (hardcoded, only when `self._include_index` is True)

### Bug 6: Batch replicate (batch_replicate.py)

**Location:** `plugins/transforms/batch_replicate.py`, before line 181.

Check against row dict:
- `"copy_index"` (hardcoded, only when `self._include_copy_index` is True)

For batch replicate, the check happens once per row in the replication loop. Since `copy_index` is the same for all copies of the same row, checking the first row's fields is sufficient.

## Testing Strategy

### Unit test for shared utility
- `tests/unit/plugins/transforms/test_field_collision.py`
- Test: no collision returns None
- Test: single collision returns sorted list
- Test: multiple collisions returns sorted list
- Test: empty new_fields returns None

### Regression tests per bug (1-2 tests each)
Each test constructs a PipelineRow with a field matching the collision name, calls the transform, and asserts:
- `TransformResult.error()` is returned (not success)
- Error reason is `"field_collision"`
- Collision details include the specific field names

**Test files:**
- `tests/unit/plugins/llm/test_base_field_collision.py` (Bugs 1, 3)
- `tests/unit/plugins/llm/test_batch_field_collision.py` (Bug 2)
- `tests/unit/plugins/transforms/test_web_scrape_field_collision.py` (Bug 4)
- `tests/unit/plugins/transforms/test_json_explode_field_collision.py` (Bug 5)
- `tests/unit/plugins/transforms/test_batch_replicate_field_collision.py` (Bug 6)

Estimated: ~15 tests total.

## Out of Scope

- **Coalesce union merge** — already records collisions in audit metadata (bug vzrr, fixed).
- **Field mapper target collisions** — explicit mapping is intentional behavior.
- **Config-time validation** — checking response_field against source schema at config load would require schema to be known before pipeline runs. Runtime detection is sufficient.
- **Engine-level collision detection** — engine layer is already protected.
