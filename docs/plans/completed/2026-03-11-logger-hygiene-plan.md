# Logger Hygiene — Remove Redundant Logs and Close Audit Gaps

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove logging that duplicates Landscape audit data, and enrich LLM transform `success_reason` so classification decisions survive payload purge.

**Architecture:** Two workstreams — (1) delete redundant log statements that echo data already in `node_states` or `context_after_json`, and (2) enrich `TransformSuccessReason` metadata in LLM transforms so the *interpretation* of an LLM response is captured in the audit trail, not just the generic action label.

**Tech Stack:** structlog, SQLAlchemy Core, pytest, Landscape audit trail

**Prerequisites:**
- Development environment set up (`uv pip install -e ".[dev]"`)
- Familiarity with `TransformResult.success()` API and `TransformSuccessReason` TypedDict
- Understanding of the Landscape audit trail (`node_states.success_reason_json`, `context_after_json`)

**Important: Line numbers in this plan were verified against `main` as of 2026-03-11.** If you are working on a feature branch (e.g., `RC4-user-interface`), line numbers may have shifted by a few lines. Always locate the code by searching for the **content** shown in the BEFORE blocks, not the line numbers. Every task includes the exact code to find/replace.

**Plan Review (2026-03-12):** APPROVED_WITH_WARNINGS. Four-reviewer pass (reality, architecture, quality, systems). Changes applied:
- W1: Added parallel-path test fixture and `TestMultiQuerySuccessReasonParallel` class to Task 6
- W2: Made MCP collision query Filigree task mandatory in Task 3 Step 0 (was deferred prose)
- W3: Added atomic delivery pairs note for Tasks 4-5 and 6-7
- W5: Replaced manual token field conditionals with `TokenUsage.to_dict()` in Task 5; fixed `response_tokens` → `completion_tokens` naming to match `calls` table
- W7: Fixed contradictory conftest.py/inline-fixtures prose in Task 4
- W8: Corrected `QuerySpec.input_fields` type to `MappingProxyType` in Task 6
- Pre-execution review (2026-03-13): Fixed Task 5 step numbering gap (Steps 0,1,2,4,5 → 0,1,2,3,4); added remediation guidance to Task 9 Step 5 for `.get()` on evolved JSON shapes
- Full review: `docs/plans/2026-03-11-logger-hygiene-plan.review.json`

**Corrected Findings from Audit Report:**

The original audit report (`docs/plans/2026-03-11-logger-audit-report.md`) incorrectly identified G3 (coalesce union merge collisions) as an audit gap. Investigation shows `CoalesceMetadata.with_collisions()` already records collision data in `context_after_json`. The warning log is redundant, not gap-filling. G3 is reclassified as R3 (remove redundant log).

---

### Task 1: Remove `pipeline_row_created` Debug Log

**Files:**
- Modify: `src/elspeth/engine/executors/transform.py:418-423`
- Test: `tests/unit/engine/test_executors.py` (verify no tests depend on the log)

**Step 1: Verify no tests assert on this log**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py -v -k "pipeline_row" --no-header 2>&1 | head -20`

Expected: No tests match — this log is untested because it's debug noise.

**Step 2: Remove the debug log**

In `src/elspeth/engine/executors/transform.py`, delete lines 418-423:

```python
# DELETE this block:
            slog.debug(
                "pipeline_row_created",
                token_id=token.token_id,
                transform=transform.name,
                contract_mode=result.row.contract.mode,
            )
```

The code before (contract evolution, line ~412) flows directly into the code after (token update, line ~425). No other logic depends on this log.

**Step 3: Remove dead `slog`, `logger`, and their imports**

The `slog.debug` at line 418 is the **only** structlog call in this file, and `logger` is **already unused** (declared at line 31 but never called anywhere). After deleting the debug log, remove all four dead lines:

- Line 3: `import logging`
- Line 7: `import structlog`
- Line 31: `logger = logging.getLogger(__name__)`
- Line 32: `slog = structlog.get_logger(__name__)`

Verify with a quick grep that no other `slog.` or `logger.` calls exist in the file (there are none as of 2026-03-11).

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_executors.py -x -q`

Expected: All tests pass — this was a pure diagnostic with no side effects.

**Step 5: Commit**

```bash
git add src/elspeth/engine/executors/transform.py
git commit -m "remove redundant pipeline_row_created debug log — data already in node_states"
```

**Definition of Done:**
- [ ] Debug log removed
- [ ] No test regressions
- [ ] Dead imports removed: `logging`, `structlog`, `logger`, `slog` (all four are unused after this deletion)
- [ ] Committed

---

### Task 2: Remove `Call response payload purged` Debug Log

**Files:**
- Modify: `src/elspeth/core/landscape/execution_repository.py:1010`

**Step 1: Remove the debug log**

In `src/elspeth/core/landscape/execution_repository.py`, delete line 1010:

```python
# DELETE this line:
            logger.debug("Call response payload purged", content_hash=exc.content_hash, call_id=call_id)
```

The `except PayloadNotFoundError` handler at ~line 1009 should flow directly to `return CallDataResult(state=CallDataState.PURGED, data=None)` at ~line 1011.

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/core/ -x -q`

Expected: All tests pass.

**Step 3: Commit**

```bash
git add src/elspeth/core/landscape/execution_repository.py
git commit -m "remove redundant payload-purged debug log — CallDataState.PURGED already signals the state"
```

**Definition of Done:**
- [ ] Debug log removed
- [ ] No test regressions
- [ ] Committed

---

### Task 3: Remove `union_merge_field_collisions` Warning Log

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py:832-837`

**Context:** The collision data is already recorded in the Landscape audit trail via `CoalesceMetadata.with_collisions()` at lines 758-759, which flows through `context_after` → `context_after_json`. The warning log duplicates this.

**Step 0: Verify collision data round-trips through `context_after_json`**

**This step is mandatory before proceeding.** Removing this warning converts push observability (log-based alerting that operators may have dashboards/alerts for) to pull-only (Landscape query). You must confirm the pull path actually captures the data.

1. Run collision-related tests:
   ```
   .venv/bin/python -m pytest tests/unit/engine/test_coalesce_executor.py -v -k "collision" --no-header
   ```

2. **Verify the audit trail content, not just test pass/fail.** Look for a test that asserts on `context_after_json` containing `union_field_collisions` with field names and contributing branches. If no such assertion exists, add one before removing the log:
   ```python
   # The CoalesceMetadata.with_collisions() path at coalesce_executor.py:758-759
   # should produce context_after_json like:
   # {"policy": "require_all", "merge_strategy": "union", ...,
   #  "union_field_collisions": {"field_name": ["branch_a", "branch_b"]}}
   ```
   Confirm the `union_field_collisions` key appears with the correct structure. A test that passes without checking this field proves nothing about the audit path.

3. **File MCP collision query task (mandatory).** No MCP analyzer currently surfaces collision data from `context_after_json`. Before removing this warning log, file a Filigree task for adding a collision query tool to `src/elspeth/mcp/analyzers/`. This creates a trackable commitment for the push-to-pull observability migration rather than leaving it as a prose note. Include the new task ID in the Task 3 commit message.

4. **Operational check:** If your deployment has log-based alerting (Datadog, Grafana, etc.) that watches for the `union_merge_field_collisions` event name, note that those alerts will go silent after this change. The data moves from logs to `context_after_json` in the Landscape database — operators will need to query it there instead.

**Step 1: Remove the warning log**

In `src/elspeth/engine/coalesce_executor.py`, delete lines 832-837 (the entire `if collisions:` block including the guard):

```python
# DELETE this block:
            if collisions:
                slog.warning(
                    "union_merge_field_collisions",
                    collisions=dict(collisions),
                    winner_branch={f: branches_list[-1] for f, branches_list in collisions.items()},
                )
```

The `_execute_merge` helper method returns `merged, collisions` — the collision dict is consumed by the caller at lines 758-759 (`CoalesceMetadata.with_collisions()`). The log was observational only.

**Step 2: Run coalesce tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_coalesce_executor.py -x -q`

Expected: All tests pass.

**Step 3: Commit**

```bash
git add src/elspeth/engine/coalesce_executor.py
git commit -m "remove redundant union_merge_field_collisions warning — already in context_after_json via CoalesceMetadata"
```

**Definition of Done:**
- [ ] Verified collision data round-trips through `context_after_json` (Step 0) — assertion added if missing
- [ ] Filigree task filed for MCP collision query analyzer (Step 0.3)
- [ ] Warning log removed (entire `if collisions:` block, lines 832-837)
- [ ] Collision data still flows through CoalesceMetadata (no functional change)
- [ ] No test regressions
- [ ] Committed (commit message includes MCP task ID)

---

**⚠ Atomic Delivery Pairs:** Tasks 4-5 and Tasks 6-7 are TDD pairs that must be treated as atomic delivery units. Do not merge a branch with only one pair completed — this would leave the codebase with inconsistent `success_reason` shapes between single-query and multi-query LLM transforms, and (for the test-only commits) failing tests on the shared branch.

### Task 4: Enrich Single-Query LLM `success_reason` — Write Failing Test

**Files:**
- Create: `tests/unit/plugins/llm/test_llm_success_reason.py`
- Reference: `src/elspeth/contracts/errors.py:144-200` (TransformSuccessReason TypedDict)
- Reference: `src/elspeth/plugins/transforms/llm/transform.py:331-334` (current success call)

**Step 1: Write the failing test**

Create `tests/unit/plugins/llm/test_llm_success_reason.py`:

```python
"""Tests for LLM transform success_reason audit metadata.

Validates that success_reason captures enough semantic context for
an auditor to understand what the transform decided, even after
payload purge deletes the output row data.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.results import TransformResult


class TestSingleQuerySuccessReason:
    """SingleQueryStrategy must capture response field and model in success_reason."""

    def test_success_reason_includes_model(
        self,
        single_query_result: TransformResult,
    ) -> None:
        """success_reason must include which model produced the result."""
        assert single_query_result.success_reason is not None
        assert "model" in single_query_result.success_reason.get("metadata", {}), (
            "success_reason.metadata must include 'model' so the audit trail "
            "records which model produced the classification"
        )

    def test_success_reason_includes_completion_tokens(
        self,
        single_query_result: TransformResult,
    ) -> None:
        """success_reason must include completion token count for cost attribution."""
        assert single_query_result.success_reason is not None
        metadata = single_query_result.success_reason.get("metadata", {})
        assert "completion_tokens" in metadata, (
            "success_reason.metadata must include 'completion_tokens' "
            "for cost attribution in the audit trail"
        )

    def test_success_reason_includes_fields_added(
        self,
        single_query_result: TransformResult,
    ) -> None:
        """success_reason must include which fields were added."""
        assert single_query_result.success_reason is not None
        assert "fields_added" in single_query_result.success_reason
        assert isinstance(single_query_result.success_reason["fields_added"], list)
        assert len(single_query_result.success_reason["fields_added"]) > 0
```

**Why this test:** After payload purge, `success_reason_json` in `node_states` is the only surviving record of what the transform decided. The generic `"enriched"` label tells an auditor nothing about which model or how many tokens were consumed. These fields are already available from the LLM call — they just need to flow into `success_reason`.

**Fixture implementation:** Add inline fixtures in the test file, following the `_make_ctx()` pattern from `tests/unit/plugins/llm/test_transform.py:43-50`:

```python
# Add these fixtures at module level in the test file

from unittest.mock import Mock

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.transforms.llm.provider import FinishReason, LLMQueryResult
from elspeth.plugins.transforms.llm.templates import PromptTemplate
from elspeth.plugins.transforms.llm.transform import SingleQueryStrategy
from elspeth.testing import make_pipeline_row


def _make_ctx() -> Mock:
    """Minimal mock TransformContext — matches test_transform.py pattern."""
    ctx = Mock()
    ctx.state_id = "state-123"
    ctx.run_id = "run-123"
    ctx.token = Mock()
    ctx.token.token_id = "token-1"
    return ctx


@pytest.fixture()
def single_query_result() -> TransformResult:
    """Execute SingleQueryStrategy with mocked provider, return the result."""
    strategy = SingleQueryStrategy(
        template=PromptTemplate("Classify: {{ row.text }}"),
        system_prompt=None,
        system_prompt_source=None,
        model="gpt-4o",
        temperature=0.7,
        max_tokens=None,
        response_field="llm_response",
    )

    mock_provider = Mock()
    mock_provider.execute_query.return_value = LLMQueryResult(
        content="The analysis is positive.",
        usage=TokenUsage.known(prompt_tokens=10, completion_tokens=5),
        model="gpt-4o",
        finish_reason=FinishReason.STOP,
    )

    mock_tracer = Mock()

    row = make_pipeline_row({"text": "hello"})
    ctx = _make_ctx()

    return strategy.execute(row, ctx, provider=mock_provider, tracer=mock_tracer)
```

**Key points:**
- `PromptTemplate("Classify: {{ row.text }}")` — constructor takes a string directly, NOT `from_string()`
- `_make_ctx()` follows `test_transform.py:43-50` — Mock with `state_id`, `run_id`, and `token.token_id` set
- `LangfuseTracer` is mocked as a plain `Mock()` — the strategy calls `tracer.record_success()` / `record_error()` which the mock absorbs
- The fixture calls `strategy.execute()` directly rather than going through `LLMTransform.accept()`, which is appropriate for unit-testing the success_reason shape

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_llm_success_reason.py -v --no-header 2>&1 | head -30`

Expected: Tests fail because current `success_reason` is `{"action": "enriched", "fields_added": ["llm_response"]}` with no `metadata` key.

**Step 3: Commit the failing test**

```bash
git add tests/unit/plugins/llm/test_llm_success_reason.py
git commit -m "test: add failing tests for LLM single-query success_reason audit metadata"
```

**Definition of Done:**
- [ ] Test file created with fixtures following existing LLM test patterns
- [ ] Tests fail for the right reason (missing metadata, not import errors)
- [ ] Committed

---

### Task 5: Implement Single-Query `success_reason` Enrichment

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py:331-334`
- Test: `tests/unit/plugins/llm/test_llm_success_reason.py`
- Reference: `src/elspeth/contracts/errors.py:144-200` (TransformSuccessReason has `metadata: NotRequired[dict[str, Any]]`)

**Step 0: Verify `LLMQueryResult` type guarantees on your working branch**

Before implementing, confirm two assumptions this task relies on:

1. `LLMQueryResult.model` is a non-optional `str` validated in `__post_init__`. Check `src/elspeth/plugins/transforms/llm/provider.py` around line 93-117 — look for the `__post_init__` guard that rejects empty/whitespace model strings. If this guard exists, `result.model` can be used directly with no fallback.

2. `LLMQueryResult.usage` is always a `TokenUsage` instance (never `None`). Check the same class — `usage` field should have type `TokenUsage` (no `| None`). The individual fields `usage.completion_tokens` and `usage.prompt_tokens` ARE `int | None` — that's why we conditionally include them.

If either guarantee has changed on your branch, adjust the implementation accordingly. The code below assumes both hold.

**Step 1: Identify available metadata at the success site**

At line 331-334 of `transform.py`, the `SingleQueryStrategy.execute()` method has these variables in scope:
- `self.response_field` — the output field name (already in success_reason)
- `result` — the `LLMQueryResult` object (has `.model: str`, `.usage: TokenUsage`)
- `content` — the raw response text
- `start_time` — for latency calculation

**Important variable names:** The LLM response is stored in `result` (assigned at line ~238 via `result = provider.execute_query(...)`), NOT `response`. The `result.model` field is a non-optional `str` (validated in `LLMQueryResult.__post_init__`). The `result.usage` field is always a `TokenUsage` instance (never `None`), but `result.usage.completion_tokens` and `result.usage.prompt_tokens` are `int | None`.

The call audit (calls table) already records model, tokens, and latency via the `_recorder.record_call()` earlier in the method. The enrichment should add a **summary** to success_reason, not duplicate the full call record.

**Step 2: Enrich the success_reason**

In `src/elspeth/plugins/transforms/llm/transform.py`, replace lines 331-334:

```python
# BEFORE:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={"action": "enriched", "fields_added": [self.response_field]},
        )

# AFTER:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "enriched",
                "fields_added": [self.response_field],
                "metadata": {"model": result.model, **result.usage.to_dict()},
            },
        )
```

**Why this approach:**
- `result.model` is used directly (no fallback guard) — it's a non-optional `str` validated by `LLMQueryResult.__post_init__`. Defensive coercion to `"unknown"` is forbidden on Tier 2 data per CLAUDE.md offensive programming standard
- Token counts use `result.usage.to_dict()` — `TokenUsage.to_dict()` (at `contracts/token_usage.py:82-93`) already handles conditional omission of `None` fields with the standard key names (`prompt_tokens`, `completion_tokens`). This avoids hand-coding the same logic and keeps field names consistent with the `calls` table
- `model` and token counts are the minimum an auditor needs to understand cost and provenance
- The full response content is NOT included (may contain PII, subject to purge)
- The call-level audit in the calls table has the detailed record; this is a queryable summary
- Uses the existing `metadata: NotRequired[dict[str, Any]]` field in `TransformSuccessReason`

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_llm_success_reason.py -v --no-header`

Expected: All tests in `TestSingleQuerySuccessReason` pass.

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/ -x -q`

Expected: No regressions in existing LLM tests.

**Step 4: Commit**

```bash
git add src/elspeth/plugins/transforms/llm/transform.py
git commit -m "enrich single-query LLM success_reason with model and token metadata

success_reason now includes model name and token counts in the metadata
field, so the audit trail captures which model produced each classification
even after payload purge deletes the output row data."
```

**Definition of Done:**
- [ ] success_reason includes `result.model` directly (no defensive fallback)
- [ ] Token counts via `result.usage.to_dict()` — standard field names (`prompt_tokens`, `completion_tokens`)
- [ ] Uses variable `result` (not `response`) for LLMQueryResult access
- [ ] New tests pass
- [ ] Existing LLM tests unbroken
- [ ] Committed

---

### Task 6: Enrich Multi-Query LLM `success_reason` — Write Failing Test

**Files:**
- Modify: `tests/unit/plugins/llm/test_llm_success_reason.py`
- Reference: `src/elspeth/plugins/transforms/llm/transform.py:727-733,835-841` (sequential and parallel success sites)

**Step 1: Add failing tests for multi-query success_reason**

Append to `tests/unit/plugins/llm/test_llm_success_reason.py`:

```python
class TestMultiQuerySuccessReason:
    """MultiQueryStrategy must capture model and field info in success_reason."""

    def test_success_reason_includes_queries_completed(
        self,
        multi_query_result: TransformResult,
    ) -> None:
        """success_reason must include total query count (existing field)."""
        assert multi_query_result.success_reason is not None
        assert "queries_completed" in multi_query_result.success_reason

    def test_success_reason_includes_model_for_multi_query(
        self,
        multi_query_result: TransformResult,
    ) -> None:
        """success_reason must include model name even for multi-query."""
        assert multi_query_result.success_reason is not None
        metadata = multi_query_result.success_reason.get("metadata", {})
        assert "model" in metadata

    def test_success_reason_includes_fields_added(
        self,
        multi_query_result: TransformResult,
    ) -> None:
        """success_reason must include which fields were added by the queries."""
        assert multi_query_result.success_reason is not None
        assert "fields_added" in multi_query_result.success_reason
        assert isinstance(multi_query_result.success_reason["fields_added"], list)
        assert len(multi_query_result.success_reason["fields_added"]) > 0
```

**Why this test:** Multi-query transforms run N independent LLM calls. The audit trail should record which model ran the queries and which fields were added, so an auditor can understand provenance even after payload purge. (Note: `query_outcomes` was considered but dropped — at the success return site, all queries necessarily succeeded since errors return early, making an all-success dict redundant with `queries_completed`.)

**Fixture implementation:** Two fixtures are needed — one for the sequential path and one for the parallel path. Task 7 modifies both `_execute_sequential()` (~line 727) and `_execute_parallel()` (~line 835), so both paths must be tested. Based on the patterns in `tests/unit/plugins/llm/test_azure_multi_query.py:108-160` and `405-444`:

1. Construct a `MultiQueryStrategy` (frozen dataclass at `transform.py:338-375`):
   - `query_specs`: A sequence of `QuerySpec` objects (defined at `multi_query.py:83-131`). Each needs `name: str` and `input_fields: MappingProxyType[str, str]` at minimum (a plain `dict` is accepted and coerced in `__post_init__`). For structured output, add `output_fields: tuple[OutputFieldConfig, ...]`.
   - `model`: `"gpt-4o"` — this is the field the new tests assert on
   - Other fields: `template`, `system_prompt`, `system_prompt_source`, `temperature`, `max_tokens`, `response_field`

2. Mock the provider using the pattern from `test_azure_multi_query.py:108-160`:
   ```python
   def _make_mock_provider(responses: list[dict]) -> Mock:
       cycle = itertools.cycle(responses)
       mock_provider = Mock()
       def execute_from_list(messages, *, model, temperature, max_tokens,
                             state_id, token_id, response_format=None):
           return LLMQueryResult(
               content=json.dumps(next(cycle)),
               usage=TokenUsage.known(10, 5),
               model="gpt-4o",
               finish_reason=FinishReason.STOP,
           )
       mock_provider.execute_query.side_effect = execute_from_list
       return mock_provider
   ```

3. Create two fixtures:
   - `multi_query_result` — calls `_execute_sequential()` directly for the sequential path
   - `parallel_multi_query_result` — calls `_execute_parallel()` for the parallel path

4. Add a `TestMultiQuerySuccessReasonParallel` class that mirrors `TestMultiQuerySuccessReason` but uses the `parallel_multi_query_result` fixture. This ensures the parallel `accumulated_outputs` population (which uses `result.row.to_dict()` rather than `result.fields`) produces the correct `fields_added` list.

Reference: `tests/unit/plugins/llm/test_azure_multi_query.py` for complete working examples.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_llm_success_reason.py::TestMultiQuerySuccessReason -v --no-header 2>&1 | head -20`

Expected: Tests fail because current multi-query `success_reason` has no `metadata` key.

**Step 3: Commit**

```bash
git add tests/unit/plugins/llm/test_llm_success_reason.py
git commit -m "test: add failing tests for multi-query LLM success_reason audit metadata"
```

**Definition of Done:**
- [ ] Multi-query sequential tests added (`TestMultiQuerySuccessReason` with `multi_query_result` fixture)
- [ ] Multi-query parallel tests added (`TestMultiQuerySuccessReasonParallel` with `parallel_multi_query_result` fixture)
- [ ] Tests fail for the right reason (missing metadata, not import errors)
- [ ] Committed

---

### Task 7: Implement Multi-Query `success_reason` Enrichment

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py:727-733` (sequential path)
- Modify: `src/elspeth/plugins/transforms/llm/transform.py:835-841` (parallel path)
- Test: `tests/unit/plugins/llm/test_llm_success_reason.py`

**Step 1: Enrich sequential success path**

In `src/elspeth/plugins/transforms/llm/transform.py`, replace lines 727-733:

**Important:** `MultiQueryStrategy` is a frozen dataclass with field `model: str` at line 356 — use `self.model`, NOT `self._model` (which exists only on `LLMTransform`, not on the strategy dataclass).

```python
# BEFORE:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
            },
        )

# AFTER:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model},
            },
        )
```

**Notes:**
- `accumulated_outputs` is the dict of field-name → value pairs built during the query loop (available at this return site, used on line 720). Its keys are the exact fields added to the output row — for structured queries these are `{spec.name}_{field.suffix}`, for raw queries just `spec.name`. Using `accumulated_outputs.keys()` is more accurate than trying to derive field names from `QuerySpec` (which has no `response_field` attribute).
- The original plan included a `query_outcomes` dict mapping each query name to `"success"`. This was dropped because the sequential path only reaches this code if ALL queries succeeded (errors return early at lines 691-714), making the dict always `{name: "success" for all specs}` — identical information to `queries_completed`. The `model` field is the genuinely new information an auditor needs.
- **Why no token counts in multi-query metadata:** Unlike single-query (one call = one token count), multi-query makes N calls with potentially different token counts each. A sum would be misleading (masks individual outliers), and a per-query breakdown would duplicate the calls table which already records per-call token usage with `token_id` correlation. The `model` field is the same across all queries (set on the strategy, not per-query), so it's unambiguous. An auditor needing per-query token data should join `node_states` → `calls` on `token_id`.

**Step 2: Enrich parallel success path**

Replace lines 835-841 with the same pattern:

```python
# BEFORE:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
            },
        )

# AFTER:
        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
                "fields_added": list(accumulated_outputs.keys()),
                "metadata": {"model": self.model},
            },
        )
```

**Same rationale:** The parallel path also only reaches the success return if no errors exist (checked at lines 806-819). Use `self.model` (dataclass field), not `self._model`. The `accumulated_outputs` dict is available here too (built at line 821-827).

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_llm_success_reason.py -v --no-header`

Expected: All tests pass.

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/ -x -q`

Expected: No regressions.

**Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/llm/transform.py
git commit -m "enrich multi-query LLM success_reason with model and fields_added

Multi-query success_reason now records which model ran the queries and
which fields were added, so the audit trail captures provenance even
after payload purge deletes the output row data."
```

**Definition of Done:**
- [ ] Sequential path enriched with `model` and `fields_added` (from `accumulated_outputs.keys()`)
- [ ] Parallel path enriched with `model` and `fields_added` (from `accumulated_outputs.keys()`)
- [ ] Uses `self.model` (dataclass field), not `self._model`
- [ ] Both sequential and parallel tests pass (`TestMultiQuerySuccessReason` and `TestMultiQuerySuccessReasonParallel`)
- [ ] Existing LLM tests unbroken
- [ ] Committed

---

### Task 8: Update Audit Report with Corrected Findings

**Files:**
- Modify: `docs/plans/2026-03-11-logger-audit-report.md`

**Step 1: Update the report**

In the audit report, correct these items:

1. **G3 (coalesce collision metadata):** Reclassify from "audit gap" to "redundant logging." Add note that `CoalesceMetadata.with_collisions()` already records this in `context_after_json`.

2. **A2 section:** Update to note that collision metadata IS in `context_after_json` via `CoalesceMetadata.union_field_collisions`. The warning log is the redundant item, not the audit gap.

3. **Phase 2 work items:** Remove G3 from "Close Audit Gaps" and add R3 to "Remove Redundant Logging."

4. **Add reference** to this implementation plan.

**Step 2: Commit**

```bash
git add docs/plans/2026-03-11-logger-audit-report.md
git commit -m "docs: correct audit report — coalesce collisions already in context_after_json"
```

**Definition of Done:**
- [ ] G3 reclassified as R3
- [ ] Report accurately reflects implementation findings
- [ ] Committed

---

### Task 9: Verify Full Test Suite and Type Check

**Files:** None (verification only)

**Step 1: Run full unit and LLM integration tests**

Run: `.venv/bin/python -m pytest tests/unit/ -x -q`

Expected: All unit tests pass.

Run: `.venv/bin/python -m pytest tests/integration/plugins/llm/ -x -q` (if this directory exists)

Expected: All LLM integration tests pass. The success_reason enrichment should not break any integration test since it only adds new metadata fields to an existing dict.

**Step 2: Run type checker**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/llm/transform.py src/elspeth/engine/executors/transform.py src/elspeth/engine/coalesce_executor.py src/elspeth/core/landscape/execution_repository.py`

Expected: No new type errors. The `metadata` field in `TransformSuccessReason` is `NotRequired[dict[str, Any]]`, so adding it should not cause type issues.

**Step 3: Run tier model enforcer**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

Expected: No new violations (we're removing logs, not adding imports).

**Step 4: Run lint**

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/transforms/llm/transform.py src/elspeth/engine/executors/transform.py src/elspeth/engine/coalesce_executor.py src/elspeth/core/landscape/execution_repository.py`

Expected: No new warnings.

**Step 5: Verify schema evolution compatibility**

After this work, `success_reason_json` in `node_states` will have two shapes coexisting in the same database:

- **Old runs** (pre-change): `{"action": "enriched", "fields_added": ["llm_response"]}` — no `metadata` key
- **New runs** (post-change): `{"action": "enriched", "fields_added": ["llm_response"], "metadata": {"model": "gpt-4o", ...}}` — with `metadata`

No schema migration is needed (the column is JSON), but any tooling that queries `success_reason_json` must handle both shapes. Verify that:

1. The MCP analysis server (`src/elspeth/mcp/analyzers/`) doesn't assume `metadata` exists when reading success_reason. Grep for `success_reason` in the analyzers directory and check for hard key access.
2. The TUI explain screens (`src/elspeth/tui/`) don't crash on the new shape. Grep for `success_reason` in `tui/`.
3. The CLI formatters (`src/elspeth/cli_formatters.py`) handle both shapes.

If any of these access `success_reason["metadata"]` directly (without `.get()`), they'll crash on old runs. This is acceptable for *new code you're adding*, but existing code that reads old data must be tolerant of the missing key.

**If you find a hard access:** These are JSON-parsed dicts from the database (Tier 1 data, but the *shape* has evolved additively). Using `.get("metadata", {})` on a parsed JSON dict is not defensive programming — it's handling a legitimate schema evolution where old rows lack the key. Change the access to `.get()` and move on. This is distinct from the CLAUDE.md prohibition on `.get()` for typed dataclass fields.

**Step 6: Spot-check integration round-trip (optional but recommended)**

The unit tests verify the `TransformResult.success_reason` dict shape. They do NOT verify the metadata survives through the recorder into `node_states.success_reason_json` in the database. If you want full confidence:

1. Check `tests/integration/plugins/llm/` for an existing test that asserts on `node_states` content after a full pipeline run
2. If one exists, verify it still passes and optionally add an assertion on `success_reason_json` containing `metadata`
3. If none exists, this is a known gap — the audit report (`docs/plans/2026-03-11-logger-audit-report.md`) documents it as a follow-up item

The recorder serializes `success_reason` via `json.dumps()` in `execution_repository.py`. Since we're only adding standard JSON-serializable types (strings, ints, dicts), the round-trip should work. But "should work" is not "verified."

**Definition of Done:**
- [ ] Full unit tests pass
- [ ] LLM integration tests pass (if directory exists)
- [ ] mypy clean
- [ ] Tier model enforcer clean
- [ ] Ruff clean
- [ ] Schema evolution: verified no existing code crashes on new `metadata` key or on old runs without it

---

## Deferred Items (Not in Scope)

### G4: Hash Method Tracking in node_states

**Status:** Needs design decision. Currently when quarantined input data is not canonically hashable, `execution_repository.py:160` uses `repr_hash()` as a fallback. The `node_states` table stores the hash but not *which method* produced it.

**Decision needed:** Is it worth adding a `hash_method` column to `node_states`? This would require a schema migration (Alembic) and touches the core audit schema. The current warning log adequately signals the degradation for operational purposes. Deferring to a future schema review.

### I1: Checkpoint Size as Landscape Metric

**Status:** Not actionable. Large checkpoint size warnings (`coalesce_executor.py:232`) are operational observations about memory pressure, not row-affecting decisions. Logging is the correct channel.

### I2: LRU Eviction Auditability

**Status:** Not actionable. Completed-key eviction (`coalesce_executor.py:312`) is a memory management detail. If a duplicate token arrives after eviction, the dedup check fails — but this would be caught by the `complete_node_state()` call failing with a constraint violation. The existing invariants are sufficient.

### MCP Collision Query Support

**Status:** Filigree task must be filed as part of Task 3 (Step 0.3). Removing the `union_merge_field_collisions` warning log (Task 3) moves collision observability from push (log-based alerting) to pull-only (Landscape query via `context_after_json`). No MCP analyzer currently surfaces this data. The follow-up task to add a collision query tool to `src/elspeth/mcp/analyzers/` is filed during Task 3 implementation to create a trackable commitment, not left as prose.

### Batch LLM Transform success_reason Consistency

**Status:** Out of scope. `azure_batch.py` and `openrouter_batch.py` have their own `TransformResult.success()` calls with generic success_reason. After this work, single-query and multi-query transforms will have enriched metadata while batch transforms will not. A follow-up task should align batch transform success_reason with the pattern established here. The batch transforms have different execution models (async batch jobs with polling), so the available metadata differs — they may need a batch-specific metadata shape.

### Logger Variable Name Inconsistency

**Status:** Cosmetic. The codebase uses `logger`, `slog`, `_logger`, and `log` inconsistently. Not worth a rename sweep — the naming is locally consistent within each module and doesn't affect functionality.
