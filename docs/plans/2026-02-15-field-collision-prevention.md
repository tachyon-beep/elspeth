# Phase 3: Field Collision Prevention — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent silent data loss when transforms add fields that collide with existing input row fields.

**Architecture:** Shared `detect_field_collisions()` utility in `plugins/transforms/field_collision.py` called by all field-enriching transforms before writing. On collision, `TransformResult.error()` quarantines the row with structured collision details.

**Tech Stack:** Python, pytest, PipelineRow, TransformResult, SchemaContract

**Design doc:** `docs/plans/2026-02-15-field-collision-prevention-design.md`

---

### Task 1: Shared Utility — `detect_field_collisions()`

**Files:**
- Create: `src/elspeth/plugins/transforms/field_collision.py`
- Test: `tests/unit/plugins/transforms/test_field_collision.py`

**Step 1: Write the failing tests**

Create `tests/unit/plugins/transforms/test_field_collision.py`:

```python
"""Tests for field collision detection utility."""

from elspeth.plugins.transforms.field_collision import detect_field_collisions


class TestDetectFieldCollisions:
    """Unit tests for detect_field_collisions()."""

    def test_no_collision_returns_none(self) -> None:
        existing = {"id", "name", "amount"}
        new = ["llm_response", "llm_response_usage"]
        assert detect_field_collisions(existing, new) is None

    def test_single_collision_returns_sorted_list(self) -> None:
        existing = {"id", "name", "llm_response"}
        new = ["llm_response", "llm_response_usage"]
        assert detect_field_collisions(existing, new) == ["llm_response"]

    def test_multiple_collisions_returns_sorted_list(self) -> None:
        existing = {"id", "fetch_status", "content", "fetch_url_final"}
        new = ["content", "fingerprint", "fetch_status", "fetch_url_final"]
        assert detect_field_collisions(existing, new) == [
            "content",
            "fetch_status",
            "fetch_url_final",
        ]

    def test_empty_new_fields_returns_none(self) -> None:
        existing = {"id", "name"}
        assert detect_field_collisions(existing, []) is None

    def test_empty_existing_fields_returns_none(self) -> None:
        assert detect_field_collisions(set(), ["a", "b"]) is None
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_field_collision.py -v`
Expected: FAIL (ImportError — module does not exist yet)

**Step 3: Write minimal implementation**

Create `src/elspeth/plugins/transforms/field_collision.py`:

```python
"""Field collision detection for transforms.

Transforms that enrich rows with new fields must check for collisions
with existing input fields before writing. Silent overwrites are data loss.
"""

from __future__ import annotations

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

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_field_collision.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/field_collision.py tests/unit/plugins/transforms/test_field_collision.py
git commit -m "feat: add detect_field_collisions() shared utility for Phase 3"
```

---

### Task 2: Bug 1 — LLM single-query response_field collision

**Files:**
- Modify: `src/elspeth/plugins/llm/base.py:351` (insert collision check before field writes)
- Test: `tests/unit/plugins/llm/test_base.py` (add test to existing file)

**Step 1: Write the failing test**

Add to `tests/unit/plugins/llm/test_base.py`, inside a new test class at the end of the file:

```python
class TestBaseLLMTransformFieldCollision:
    """Tests for field collision detection in LLM transforms."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        return PluginContext(run_id="test-run", config={})

    def test_response_field_collision_returns_error(self, ctx: PluginContext) -> None:
        """LLM transform returns error when response_field collides with input row field."""
        mock_client = Mock(spec=AuditedLLMClient)
        mock_client.chat_completion.return_value = LLMResponse(
            content="test", model="gpt-4", usage={"total_tokens": 10}
        )

        TransformClass = create_test_transform_class(mock_client=mock_client)
        transform = TransformClass(
            {
                "template": "Classify: {{ text }}",
                "response_field": "llm_response",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        # Row already has "llm_response" — collision!
        row = wrap_in_pipeline_row({"text": "hello", "llm_response": "pre-existing"})
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "field_collision"
        assert "llm_response" in result.reason["collisions"]

    def test_suffixed_field_collision_returns_error(self, ctx: PluginContext) -> None:
        """LLM transform detects collision on suffixed metadata fields too."""
        mock_client = Mock(spec=AuditedLLMClient)
        mock_client.chat_completion.return_value = LLMResponse(
            content="test", model="gpt-4", usage={"total_tokens": 10}
        )

        TransformClass = create_test_transform_class(mock_client=mock_client)
        transform = TransformClass(
            {
                "template": "Classify: {{ text }}",
                "response_field": "llm_response",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        # Row has a suffixed field that collides with LLM metadata
        row = wrap_in_pipeline_row({"text": "hello", "llm_response_usage": {"old": True}})
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "field_collision"
        assert "llm_response_usage" in result.reason["collisions"]

    def test_no_collision_succeeds(self, ctx: PluginContext) -> None:
        """LLM transform succeeds when no field collision exists."""
        mock_client = Mock(spec=AuditedLLMClient)
        mock_client.chat_completion.return_value = LLMResponse(
            content="classified", model="gpt-4", usage={"total_tokens": 10}
        )

        TransformClass = create_test_transform_class(mock_client=mock_client)
        transform = TransformClass(
            {
                "template": "Classify: {{ text }}",
                "response_field": "llm_response",
                "schema": DYNAMIC_SCHEMA,
            }
        )

        row = wrap_in_pipeline_row({"text": "hello"})
        result = transform.process(row, ctx)

        assert result.status == "success"
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_base.py::TestBaseLLMTransformFieldCollision -v`
Expected: 2 FAIL (collision tests expect error but get success), 1 PASS (no-collision test)

**Step 3: Implement the fix**

In `src/elspeth/plugins/llm/base.py`:

1. Add import at top (after existing imports):
```python
from elspeth.plugins.llm import get_llm_audit_fields, get_llm_guaranteed_fields
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

Note: `get_llm_guaranteed_fields` and `get_llm_audit_fields` are already imported on line 25. Just add the `detect_field_collisions` import.

2. Insert collision check before line 352 (`output = row_data.copy()`). The new code goes between the LLM call error handling (line 349) and the output building (line 351):

```python
        # 4.5 Check for field collisions before writing output
        added_fields = [
            *get_llm_guaranteed_fields(self._response_field),
            *get_llm_audit_fields(self._response_field),
        ]
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

        # 5. Build output row (OUR CODE - let exceptions crash)
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_base.py -v`
Expected: ALL PASS (including all existing tests)

**Step 5: Commit**

```bash
git add src/elspeth/plugins/llm/base.py tests/unit/plugins/llm/test_base.py
git commit -m "fix: detect field collisions in LLM single-query transform (Bug 1)"
```

---

### Task 3: Bug 3 — Multi-query merge output vs input collision

**Files:**
- Modify: `src/elspeth/plugins/llm/base_multi_query.py:348-352` (add collision check in merge loop)
- Test: `tests/unit/plugins/llm/test_multi_query.py` (add test to existing file)

**Step 1: Write the failing test**

Add to `tests/unit/plugins/llm/test_multi_query.py`, inside a new test class at the end:

```python
class TestMultiQueryFieldCollision:
    """Tests for field collision detection in multi-query merge."""

    # (Implementation note: This test requires a working multi-query transform
    #  with mock LLM responses. Look at existing tests in this file for the
    #  fixture patterns — typically uses conftest.py fixtures for mock clients.
    #  The key assertion: when a query result contains a field that already
    #  exists in the input row, the transform returns TransformResult.error()
    #  with reason="field_collision".)
    pass
```

The actual test structure depends on the existing fixtures in `tests/unit/plugins/llm/test_multi_query.py` and `conftest.py`. The implementing engineer should:

1. Read the existing test patterns in `test_multi_query.py` (especially tests that exercise `_process_single_row_internal`)
2. Create a row with a field like `casestudy1_diagnosis_score` that matches a multi-query output field
3. Assert the transform returns `TransformResult.error()` with `reason="field_collision"`

**Step 2: Implement the fix**

In `src/elspeth/plugins/llm/base_multi_query.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. Replace lines 348-352 (the merge loop) with collision-checked version:

```python
        # Merge all results into output row
        output = row_data.copy()
        input_field_names = set(row_data.keys())
        for result in results:
            if result.row is not None:
                collisions = detect_field_collisions(input_field_names, result.row.keys())
                if collisions is not None:
                    return TransformResult.error(
                        {
                            "reason": "field_collision",
                            "collisions": collisions,
                            "message": (
                                f"Multi-query output fields {collisions} already exist in input row. "
                                "This would silently overwrite source data."
                            ),
                        },
                        retryable=False,
                        context_after=pool_context,
                    )
                output.update(result.row)
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_multi_query.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/elspeth/plugins/llm/base_multi_query.py tests/unit/plugins/llm/test_multi_query.py
git commit -m "fix: detect field collisions in multi-query merge (Bug 3)"
```

---

### Task 4: Bug 2 — Batch LLM response_field collision (OpenRouter + Azure)

**Files:**
- Modify: `src/elspeth/plugins/llm/openrouter_batch.py:749-760` (add collision check)
- Modify: `src/elspeth/plugins/llm/azure_batch.py:1209-1226` (add collision check)
- Test: `tests/unit/plugins/llm/test_openrouter_batch.py` (add collision test)
- Test: `tests/unit/plugins/llm/test_azure_batch.py` (add collision test)

**OpenRouter Batch Fix:**

In `src/elspeth/plugins/llm/openrouter_batch.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. In `_process_single_row()`, before line 750 (`output = row.to_dict()`), add collision check. The method returns a `dict` on success or `dict` with "error" key on failure. On collision, return an error dict:

```python
        # 6.5 Check for field collisions before writing output
        from elspeth.plugins.llm import get_llm_audit_fields, get_llm_guaranteed_fields

        added_fields = [
            *get_llm_guaranteed_fields(self._response_field),
            *get_llm_audit_fields(self._response_field),
        ]
        collisions = detect_field_collisions(set(row.to_dict().keys()), added_fields)
        if collisions is not None:
            return {
                "error": {
                    "reason": "field_collision",
                    "collisions": collisions,
                    "message": (
                        f"Transform output fields {collisions} already exist in input row. "
                        "This would silently overwrite source data."
                    ),
                }
            }

        # 7. Build output row (OUR CODE - let exceptions crash)
```

**Azure Batch Fix:**

In `src/elspeth/plugins/llm/azure_batch.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. In the result assembly loop (around line 1209), before writing fields to `output_row`, add collision check. The Azure batch result assembly is in `_assemble_results()`. On collision, treat the row as an error row:

```python
                # 6.5 Check for field collisions before writing output
                from elspeth.plugins.llm import get_llm_audit_fields, get_llm_guaranteed_fields

                added_fields = [
                    *get_llm_guaranteed_fields(self._response_field),
                    *get_llm_audit_fields(self._response_field),
                ]
                collisions = detect_field_collisions(set(row.to_dict().keys()), added_fields)
                if collisions is not None:
                    output_row = row.to_dict()
                    output_row[self._response_field] = None
                    output_row[f"{self._response_field}_error"] = {
                        "reason": "field_collision",
                        "collisions": collisions,
                    }
                    output_rows.append(output_row)
                    row_errors.append({"row_index": idx, "reason": "field_collision"})
                    continue

                output_row = row.to_dict()
```

**Testing:** Add collision test to each batch test file. The test creates a row with `self._response_field` already present and verifies the collision is detected.

**Step: Run all batch tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_openrouter_batch.py tests/unit/plugins/llm/test_azure_batch.py -v`
Expected: ALL PASS

**Commit:**

```bash
git add src/elspeth/plugins/llm/openrouter_batch.py src/elspeth/plugins/llm/azure_batch.py tests/unit/plugins/llm/test_openrouter_batch.py tests/unit/plugins/llm/test_azure_batch.py
git commit -m "fix: detect field collisions in batch LLM transforms (Bug 2)"
```

---

### Task 5: Bug 4 — Web scrape field collision

**Files:**
- Modify: `src/elspeth/plugins/transforms/web_scrape.py:240-249` (add collision check)
- Test: `tests/unit/plugins/transforms/test_web_scrape.py` (add test to existing file)

**Step 1: Write the failing test**

Add to `tests/unit/plugins/transforms/test_web_scrape.py`. The test creates a row with a field matching a hardcoded web scrape output field (e.g., `"fetch_status"`) and verifies the collision is detected.

The implementing engineer should:
1. Read existing test patterns in `test_web_scrape.py` for fixture setup (mock HTTP responses, SSRF config)
2. Create a row with `{"url": "https://example.com", "fetch_status": "pre-existing"}`
3. Assert `TransformResult.error()` with `reason="field_collision"` and `"fetch_status"` in collisions

**Step 2: Implement the fix**

In `src/elspeth/plugins/transforms/web_scrape.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. Insert before line 242 (`output = row.to_dict()`):

```python
        # Check for field collisions before writing output
        added_fields = [
            self._content_field,
            self._fingerprint_field,
            "fetch_status",
            "fetch_url_final",
            "fetch_request_hash",
            "fetch_response_raw_hash",
            "fetch_response_processed_hash",
        ]
        collisions = detect_field_collisions(set(row.to_dict().keys()), added_fields)
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

        # Enrich row with scraped data
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py -v`
Expected: ALL PASS

**Commit:**

```bash
git add src/elspeth/plugins/transforms/web_scrape.py tests/unit/plugins/transforms/test_web_scrape.py
git commit -m "fix: detect field collisions in web scrape transform (Bug 4)"
```

---

### Task 6: Bug 5 — JSON explode field collision

**Files:**
- Modify: `src/elspeth/plugins/transforms/json_explode.py:174-180` (add collision check)
- Test: `tests/unit/plugins/transforms/test_json_explode.py` (add test to existing file)

**Step 1: Write the failing test**

Add to `tests/unit/plugins/transforms/test_json_explode.py`:

```python
class TestJSONExplodeFieldCollision:
    """Tests for field collision detection in JSONExplode."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        return PluginContext(run_id="test-run", config={})

    def test_output_field_collision_returns_error(self, ctx: PluginContext) -> None:
        """JSONExplode returns error when output_field collides with existing field."""
        from elspeth.plugins.transforms.json_explode import JSONExplode

        transform = JSONExplode(
            {
                "schema": DYNAMIC_SCHEMA,
                "array_field": "items",
                "output_field": "name",  # Will collide!
            }
        )

        # Row has "name" which collides with output_field
        row = make_pipeline_row(
            {"id": 1, "name": "existing", "items": [{"a": 1}]}
        )
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "field_collision"
        assert "name" in result.reason["collisions"]

    def test_item_index_collision_returns_error(self, ctx: PluginContext) -> None:
        """JSONExplode returns error when item_index collides with existing field."""
        from elspeth.plugins.transforms.json_explode import JSONExplode

        transform = JSONExplode(
            {
                "schema": DYNAMIC_SCHEMA,
                "array_field": "items",
                "include_index": True,
            }
        )

        # Row has "item_index" which collides with hardcoded field
        row = make_pipeline_row(
            {"id": 1, "item_index": 99, "items": [{"a": 1}]}
        )
        result = transform.process(row, ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "field_collision"
        assert "item_index" in result.reason["collisions"]
```

**Step 2: Implement the fix**

In `src/elspeth/plugins/transforms/json_explode.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. Insert after line 161 (`base = {k: v for k, v in row_data.items() if k != normalized_array_field}`), before the empty array check:

```python
        # Check for field collisions before writing output
        added_fields = [self._output_field]
        if self._include_index:
            added_fields.append("item_index")
        collisions = detect_field_collisions(set(base.keys()), added_fields)
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

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_json_explode.py -v`
Expected: ALL PASS

**Commit:**

```bash
git add src/elspeth/plugins/transforms/json_explode.py tests/unit/plugins/transforms/test_json_explode.py
git commit -m "fix: detect field collisions in JSON explode transform (Bug 5)"
```

---

### Task 7: Bug 6 — Batch replicate copy_index collision

**Files:**
- Modify: `src/elspeth/plugins/transforms/batch_replicate.py:176-183` (add collision check)
- Test: `tests/unit/plugins/transforms/test_batch_replicate.py` (add test to existing file)

**Step 1: Write the failing test**

Add to `tests/unit/plugins/transforms/test_batch_replicate.py`:

```python
class TestBatchReplicateFieldCollision:
    """Tests for field collision detection in BatchReplicate."""

    # Test: Create a row batch where the first row has a "copy_index" field.
    # Configure include_copy_index=True.
    # Assert the transform returns error with reason="field_collision".
    #
    # Implementation note: BatchReplicate is a batch transform (process_batch).
    # Look at existing test patterns in this file for fixture setup.
    # The key assertion: when a row already has "copy_index" and
    # include_copy_index=True, the transform returns TransformResult.error().
    pass
```

The implementing engineer should read `test_batch_replicate.py` for existing patterns.

**Step 2: Implement the fix**

In `src/elspeth/plugins/transforms/batch_replicate.py`:

1. Add import:
```python
from elspeth.plugins.transforms.field_collision import detect_field_collisions
```

2. Insert before the replication loop (before line 177 `for copy_idx in range(copies):`):

```python
            # Check for field collisions before writing output
            if self._include_copy_index:
                collisions = detect_field_collisions(set(row.to_dict().keys()), ["copy_index"])
                if collisions is not None:
                    quarantined.append(
                        {
                            "reason": "field_collision",
                            "collisions": collisions,
                            "row_data": row.to_dict(),
                        }
                    )
                    continue
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_batch_replicate.py -v`
Expected: ALL PASS

**Commit:**

```bash
git add src/elspeth/plugins/transforms/batch_replicate.py tests/unit/plugins/transforms/test_batch_replicate.py
git commit -m "fix: detect field collisions in batch replicate transform (Bug 6)"
```

---

### Task 8: Full test suite + lint + type check

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=60`
Expected: ALL PASS (no regressions)

**Step 2: Run linter**

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/transforms/field_collision.py src/elspeth/plugins/llm/base.py src/elspeth/plugins/llm/base_multi_query.py src/elspeth/plugins/llm/openrouter_batch.py src/elspeth/plugins/llm/azure_batch.py src/elspeth/plugins/transforms/web_scrape.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/batch_replicate.py`
Expected: No errors

**Step 3: Run type checker**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/field_collision.py src/elspeth/plugins/llm/base.py src/elspeth/plugins/llm/base_multi_query.py`
Expected: No errors

**Step 4: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: No new violations (detect_field_collisions is not a defensive pattern — it's an explicit validation)

**Step 5: Create beads issues and close them**

Create one beads issue per bug (6 total), immediately close them with the commit hashes.

---

### Task 9: Final squash commit (optional)

If the individual commits are clean, skip this. Otherwise, create a summary commit message:

```
fix: Phase 3 — field collision prevention for 6 silent data loss bugs

Add detect_field_collisions() utility and integrate into all
field-enriching transforms. On collision, rows are quarantined with
structured error details instead of silently overwriting source data.

Bugs fixed:
- LLM single-query response_field collision (base.py)
- LLM batch response_field collision (azure_batch.py, openrouter_batch.py)
- Multi-query merge output vs input collision (base_multi_query.py)
- Web scrape hardcoded field collision (web_scrape.py)
- JSON explode output_field/item_index collision (json_explode.py)
- Batch replicate copy_index collision (batch_replicate.py)
```
