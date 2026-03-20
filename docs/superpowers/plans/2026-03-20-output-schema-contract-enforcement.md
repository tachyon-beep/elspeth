# Output Schema Contract Enforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that every transform declaring output fields also provides a DAG contract (`_output_schema_config`), closing a gap where 6 transforms silently skip build-time field validation.

**Architecture:** Add `_build_output_schema_config` helper to `BaseTransform` and an offensive check in the DAG builder. Fix all 6 affected transforms atomically. `_create_schemas` stays unchanged.

**Tech Stack:** Python dataclasses (`SchemaConfig`), pluggy transform system, pytest, `FrameworkBugError` offensive checks.

**Spec:** `docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md`

**IMPORTANT — Task Ordering and Atomicity:**
Tasks 1-9 MUST all be committed before running the full test suite against integration tests that build real pipelines. Task 2 adds the enforcement check (`FrameworkBugError`); Tasks 3-8 fix the transforms that would fail that check. If the test suite runs between Task 2 and Task 8, unfixed transforms will crash at graph-build time. Either: (a) execute Tasks 1-9 sequentially without CI between them, or (b) squash Tasks 2-8 into a single commit.

---

### Task 1: Base Class — Add `_output_schema_config` Class Attribute and `_build_output_schema_config` Helper

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/base.py`
- Create: `tests/unit/plugins/infrastructure/test_build_output_schema_config.py`

- [ ] **Step 1: Write the failing tests for `_build_output_schema_config`**

Create `tests/unit/plugins/infrastructure/test_build_output_schema_config.py`:

```python
"""Tests for BaseTransform._build_output_schema_config helper."""

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.plugins.transforms.keyword_filter import KeywordFilter


def _make_minimal_transform(declared_fields: frozenset[str] | None = None):
    """Create a minimal transform to test the base class helper.

    Uses KeywordFilter as a concrete BaseTransform subclass
    (simplest available — no external deps, no adds_fields).
    """
    transform = KeywordFilter(
        {
            "fields": "text",
            "blocked_patterns": ["test"],
            "schema": {"mode": "observed"},
        }
    )
    if declared_fields is not None:
        transform.declared_output_fields = declared_fields
    return transform


class TestBuildOutputSchemaConfig:
    def test_merges_base_guaranteed_and_declared_output_fields(self):
        transform = _make_minimal_transform(frozenset({"new_field_a", "new_field_b"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            guaranteed_fields=("existing_field",),
        )
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset(
            {"existing_field", "new_field_a", "new_field_b"}
        )

    def test_empty_declared_output_fields_returns_base_only(self):
        transform = _make_minimal_transform(frozenset())
        base = SchemaConfig(
            mode="observed",
            fields=None,
            guaranteed_fields=("base_field",),
        )
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset({"base_field"})

    def test_none_base_guaranteed_fields_returns_declared_only(self):
        transform = _make_minimal_transform(frozenset({"output_x"}))
        base = SchemaConfig(mode="observed", fields=None, guaranteed_fields=None)
        result = transform._build_output_schema_config(base)
        assert frozenset(result.guaranteed_fields) == frozenset({"output_x"})

    def test_preserves_mode_and_fields(self):
        fields = (
            FieldDefinition(name="id", field_type="int", required=True),
        )
        transform = _make_minimal_transform(frozenset({"extra"}))
        base = SchemaConfig(mode="fixed", fields=fields, guaranteed_fields=None)
        result = transform._build_output_schema_config(base)
        assert result.mode == "fixed"
        assert result.fields == fields

    def test_preserves_audit_fields(self):
        transform = _make_minimal_transform(frozenset({"x"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            audit_fields=("audit_a", "audit_b"),
        )
        result = transform._build_output_schema_config(base)
        assert result.audit_fields == ("audit_a", "audit_b")

    def test_preserves_required_fields(self):
        transform = _make_minimal_transform(frozenset({"x"}))
        base = SchemaConfig(
            mode="observed",
            fields=None,
            required_fields=("req_field",),
        )
        result = transform._build_output_schema_config(base)
        assert result.required_fields == ("req_field",)

    def test_class_attribute_defaults_to_none(self):
        transform = _make_minimal_transform()
        assert transform._output_schema_config is None
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_build_output_schema_config.py -v`
Expected: FAIL — `_build_output_schema_config` does not exist yet, `_output_schema_config` attribute not found.

- [ ] **Step 3: Implement the base class changes**

In `src/elspeth/plugins/infrastructure/base.py`:

**a)** Add `SchemaConfig` to the `TYPE_CHECKING` block (~line 43):

```python
if TYPE_CHECKING:
    from elspeth.contracts.contexts import LifecycleContext, SinkContext, SourceContext, TransformContext
    from elspeth.contracts.header_modes import HeaderMode
    from elspeth.contracts.schema import SchemaConfig
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.contracts.sink import OutputValidationResult
```

**b)** Add class attribute to `BaseTransform` (after `on_success` at ~line 174, before `__init__`):

```python
    # DAG contract for output field validation (centralized in DAG builder).
    # Transforms that add fields must set this via _build_output_schema_config()
    # so the DAG builder can validate downstream required_input_fields.
    # None = no output contract provided (acceptable for shape-preserving transforms).
    _output_schema_config: SchemaConfig | None = None
```

**c)** Fix `_create_schemas` type annotation (~line 190):

Change `schema_config: Any,` to `schema_config: SchemaConfig,`

**d)** Add `_build_output_schema_config` method after `_create_schemas` (after line 226):

```python
    def _build_output_schema_config(self, schema_config: SchemaConfig) -> SchemaConfig:
        """Build output schema config for DAG contract propagation.

        Merges the transform's declared_output_fields into guaranteed_fields
        so the DAG builder can validate downstream field requirements.

        The returned SchemaConfig is for DAG contract propagation only. For
        fixed/flexible input schemas, guaranteed_fields may reference field
        names not present in the schema's fields tuple — this is intentional
        and correct for propagation purposes (the output adds fields beyond
        the input schema's declared set).

        Args:
            schema_config: The transform's input schema config (base fields).

        Returns:
            SchemaConfig with guaranteed_fields including declared output fields.
        """
        from elspeth.contracts.schema import SchemaConfig

        base_guaranteed = schema_config.guaranteed_fields or ()
        return SchemaConfig(
            mode=schema_config.mode,
            fields=schema_config.fields,
            guaranteed_fields=tuple(set(base_guaranteed) | self.declared_output_fields),
            audit_fields=schema_config.audit_fields,
            required_fields=schema_config.required_fields,
        )
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/infrastructure/test_build_output_schema_config.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Run existing transform tests — verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/ -x -q`
Expected: All pass (the class attribute defaults to `None` — no behavioral change).

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/plugins/infrastructure/base.py tests/unit/plugins/infrastructure/test_build_output_schema_config.py
git commit -m "feat: add _build_output_schema_config helper and _output_schema_config class attr to BaseTransform"
```

---

### Task 2: Fix All Transforms — Add `declared_output_fields` and Helper Calls

**IMPORTANT:** This task fixes ALL 6 transforms BEFORE adding the enforcement check (Task 3). This prevents any window where the enforcement check fires against unfixed transforms. Each transform's fix is a substep within this task.

**Files:**
- Modify: `src/elspeth/plugins/transforms/rag/transform.py`
- Modify: `src/elspeth/plugins/transforms/json_explode.py`
- Modify: `src/elspeth/plugins/transforms/batch_replicate.py`
- Modify: `src/elspeth/plugins/transforms/field_mapper.py`
- Modify: `src/elspeth/plugins/transforms/batch_stats.py`
- Modify: `src/elspeth/plugins/transforms/web_scrape.py`
- Modify: `tests/unit/plugins/transforms/rag/test_transform.py`
- Modify: `tests/unit/plugins/transforms/test_json_explode.py`
- Modify: `tests/unit/plugins/transforms/test_batch_replicate.py`
- Modify: `tests/unit/plugins/transforms/test_field_mapper.py`
- Modify: `tests/unit/plugins/transforms/test_batch_stats.py`
- Modify: `tests/unit/plugins/transforms/test_web_scrape.py`

#### 2a: RAG Transform — Replace Manual Construction with Helper

- [ ] **Step 1: Write the regression pinning test**

Add to `tests/unit/plugins/transforms/rag/test_transform.py` in `TestTransformLifecycle`:

```python
    def test_output_schema_config_guaranteed_fields(self):
        transform = _make_transform()
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {
                "policy__rag_context",
                "policy__rag_score",
                "policy__rag_count",
                "policy__rag_sources",
            }
        )
```

- [ ] **Step 2: Verify pinning test passes against existing manual construction**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py::TestTransformLifecycle::test_output_schema_config_guaranteed_fields -v`
Expected: PASS — this is a regression pin, not TDD. The manual construction at lines 89-99 already produces the correct result. This test ensures the refactor to the helper doesn't change behavior.

- [ ] **Step 3: Replace manual construction with helper call**

In `src/elspeth/plugins/transforms/rag/transform.py`, replace lines 89-99 (the manual `SchemaConfig` construction) with:

```python
        # Output schema config for DAG contract propagation.
        self._output_schema_config = self._build_output_schema_config(
            self._rag_config.schema_config
        )
```

Also remove the `SchemaConfig` import from the top of the file (line 23: `from elspeth.contracts.schema import SchemaConfig`) — it is no longer needed since the helper uses a local import. Check if any other code in the file uses `SchemaConfig` first — if not, remove it.

- [ ] **Step 4: Run all RAG tests — verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/ -v`
Expected: All pass, including the pinning test.

#### 2b: json_explode — Add Helper Call

- [ ] **Step 5: Write pinning tests for json_explode**

Add to `tests/unit/plugins/transforms/test_json_explode.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields_with_index(self):
        transform = JSONExplode(
            {
                "array_field": "items",
                "output_field": "item",
                "include_index": True,
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"item", "item_index"}
        )

    def test_guaranteed_fields_without_index(self):
        transform = JSONExplode(
            {
                "array_field": "items",
                "output_field": "item",
                "include_index": False,
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"item"}
        )
```

- [ ] **Step 6: Verify tests fail, add helper call, verify tests pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_json_explode.py::TestOutputSchemaConfig -v`
Expected: FAIL — `_output_schema_config` is `None`.

In `src/elspeth/plugins/transforms/json_explode.py`, add after the `_create_schemas` call (~line 134):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

Run again. Expected: PASS.

#### 2c: batch_replicate — Add Helper Call

- [ ] **Step 7: Write pinning tests for batch_replicate**

Add to `tests/unit/plugins/transforms/test_batch_replicate.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields_with_copy_index(self):
        transform = BatchReplicate(
            {
                "include_copy_index": True,
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"copy_index"}
        )

    def test_guaranteed_fields_without_copy_index(self):
        transform = BatchReplicate(
            {
                "include_copy_index": False,
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset()
```

- [ ] **Step 8: Verify tests fail, add helper call, verify tests pass**

In `src/elspeth/plugins/transforms/batch_replicate.py`, add after the `_create_schemas` call (~line 120):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

#### 2d: field_mapper — Populate `declared_output_fields` and Add Helper Call

- [ ] **Step 9: Write pinning tests for field_mapper**

Add to `tests/unit/plugins/transforms/test_field_mapper.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields_from_mapping_targets(self):
        transform = FieldMapper(
            {
                "mapping": {"old_name": "new_name", "source": "target"},
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"new_name", "target"}
        )

    def test_guaranteed_fields_empty_mapping(self):
        transform = FieldMapper(
            {
                "mapping": {},
                "schema": {"mode": "observed"},
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset()

    def test_declared_output_fields_set_from_mapping(self):
        transform = FieldMapper(
            {
                "mapping": {"a": "b", "c": "d"},
                "schema": {"mode": "observed"},
            }
        )
        assert transform.declared_output_fields == frozenset({"b", "d"})
```

- [ ] **Step 10: Verify tests fail, add declared_output_fields + helper, verify tests pass**

In `src/elspeth/plugins/transforms/field_mapper.py`, in `__init__` (~line 91, after `self.validate_input = cfg.validate_input`):

```python
        # Mapping targets are the fields this transform guarantees in output.
        self.declared_output_fields = frozenset(cfg.mapping.values())
```

Then after the `_create_schemas` call (~line 99):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

**IMPORTANT — Collision detection check:** After this step, verify that `TransformExecutor` collision detection (at `src/elspeth/engine/executors/transform.py:211-223`) does not produce false positives for `field_mapper`. The collision check calls `detect_field_collisions(set(input_dict.keys()), transform.declared_output_fields)`, which checks if any `declared_output_fields` already exist in the input row. For rename-only mappings where the target name coincidentally exists in the input, this would raise `PluginContractViolation`. Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_field_mapper.py -v` and check for collision-related failures. If collisions are detected in existing tests, the `declared_output_fields` computation needs refinement (e.g., exclude targets that also appear as sources: `frozenset(cfg.mapping.values()) - frozenset(cfg.mapping.keys())`).

#### 2e: batch_stats — Populate `declared_output_fields` and Add Helper Call

- [ ] **Step 11: Write pinning tests for batch_stats**

Add to `tests/unit/plugins/transforms/test_batch_stats.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields_with_mean_and_group_by(self):
        """group_by is a passthrough field (already in input) — NOT in declared_output_fields.
        Only the new stat fields appear in guaranteed_fields."""
        transform = BatchStats(
            {
                "schema": {"mode": "observed"},
                "value_field": "amount",
                "compute_mean": True,
                "group_by": "category",
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"count", "sum", "batch_size", "mean"}
        )

    def test_guaranteed_fields_minimal(self):
        transform = BatchStats(
            {
                "schema": {"mode": "observed"},
                "value_field": "amount",
                "compute_mean": False,
            }
        )
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"count", "sum", "batch_size"}
        )

    def test_declared_output_fields_excludes_group_by(self):
        """group_by is a passthrough from input — not a new field added by the transform.
        Including it in declared_output_fields would trigger false collision detection
        (TransformExecutor checks declared fields against input keys)."""
        transform = BatchStats(
            {
                "schema": {"mode": "observed"},
                "value_field": "amount",
                "group_by": "region",
            }
        )
        assert transform.declared_output_fields == frozenset(
            {"count", "sum", "batch_size", "mean"}
        )
        assert "region" not in transform.declared_output_fields
```

- [ ] **Step 12: Verify tests fail, add declared_output_fields + helper, verify tests pass**

In `src/elspeth/plugins/transforms/batch_stats.py`, in `__init__` (~line 84, after `self._compute_mean = cfg.compute_mean`):

```python
        # Declare output fields for DAG contract validation.
        # - group_by is intentionally NOT declared — it is a passthrough from
        #   input (already in the row), not a new field. Including it would
        #   trigger false collision detection in TransformExecutor.
        # - skipped_non_finite/skipped_non_finite_indices are intentionally NOT
        #   declared — they are data-dependent (only emitted when non-finite
        #   values are encountered), not config-guaranteed.
        stat_fields: set[str] = {"count", "sum", "batch_size"}
        if cfg.compute_mean:
            stat_fields.add("mean")
        self.declared_output_fields = frozenset(stat_fields)
```

Then after the `_create_schemas` call (~line 92):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

#### 2f: web_scrape — Add Helper Call

- [ ] **Step 13: Write pinning test for web_scrape**

Add to `tests/unit/plugins/transforms/test_web_scrape.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields(self):
        transform = WebScrapeTransform(
            {
                "schema": {"mode": "observed"},
                "url_field": "url",
                "content_field": "page_content",
                "fingerprint_field": "page_hash",
                "http": {
                    "abuse_contact": "test@example.com",
                    "scraping_reason": "Unit testing output schema config",
                },
            }
        )
        expected = frozenset({
            "page_content",
            "page_hash",
            "fetch_status",
            "fetch_url_final",
            "fetch_url_final_ip",
            "fetch_request_hash",
            "fetch_response_raw_hash",
            "fetch_response_processed_hash",
        })
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == expected
```

- [ ] **Step 14: Verify test fails, add helper call, verify test passes**

In `src/elspeth/plugins/transforms/web_scrape.py`, after the schema construction (~line 249, after `self.output_schema = schema`), add:

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

Note: `web_scrape` does NOT use `_create_schemas` — it builds schemas manually. The helper call is independent.

#### 2g: Run all transform tests and commit

- [ ] **Step 15: Run all transform tests — verify everything passes**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/ -x -q`
Expected: All pass.

- [ ] **Step 16: Commit all transform fixes together**

```bash
git add src/elspeth/plugins/transforms/rag/transform.py \
       src/elspeth/plugins/transforms/json_explode.py \
       src/elspeth/plugins/transforms/batch_replicate.py \
       src/elspeth/plugins/transforms/field_mapper.py \
       src/elspeth/plugins/transforms/batch_stats.py \
       src/elspeth/plugins/transforms/web_scrape.py \
       tests/unit/plugins/transforms/
git commit -m "feat: add _output_schema_config to all field-adding transforms

Populate declared_output_fields for field_mapper and batch_stats.
Add _build_output_schema_config helper call to all 6 transforms.
Replace RAG transform manual construction with helper.
Pin guaranteed_fields content in per-transform unit tests."
```

---

### Task 3: DAG Builder — Offensive Check for Missing Output Schema Config

**PREREQUISITE:** Task 2 must be complete — all transforms must have `_output_schema_config` set before this enforcement check is added.

**Files:**
- Modify: `src/elspeth/core/dag/builder.py`
- Modify: `tests/unit/core/test_dag_schema_propagation.py` (fix existing test mocks)
- Create: `tests/unit/core/dag/test_output_schema_enforcement.py`

- [ ] **Step 1: Fix existing test mocks that lack `declared_output_fields`**

In `tests/unit/core/test_dag_schema_propagation.py`, add `declared_output_fields` to ALL THREE mock classes that don't inherit `BaseTransform`:

At `MockTransformWithSchemaConfig` (~line 34), add after the class attributes:
```python
    declared_output_fields: frozenset[str] = frozenset()
```

At `MockTransformWithoutSchemaConfig` (~line 54), add after the class attributes:
```python
    declared_output_fields: frozenset[str] = frozenset()
```

At `MockAggregationTransform` (~line 347), add after the class attributes:
```python
    declared_output_fields: frozenset[str] = frozenset()
```

These mocks don't inherit `BaseTransform`, so they don't get the class attribute automatically. Without this fix, `_validate_output_schema_contract` will `AttributeError` on `transform.declared_output_fields`. `MockTransformWithSchemaConfig` is used in 4 tests — missing it would break those tests.

- [ ] **Step 2: Write the failing tests for the enforcement check**

Create `tests/unit/core/dag/test_output_schema_enforcement.py`:

```python
"""Tests for DAG builder enforcement of _output_schema_config.

Verifies that transforms declaring output fields without providing
an _output_schema_config raise FrameworkBugError at graph-build time.
"""

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.contracts.schema import SchemaConfig


class _StubTransform:
    """Minimal stub implementing enough of TransformProtocol for the builder check."""

    name = "stub_transform"
    config = {"schema": {"mode": "observed"}}
    input_schema = None
    output_schema = None
    declared_output_fields: frozenset[str] = frozenset()
    _output_schema_config: SchemaConfig | None = None


class TestOutputSchemaEnforcement:
    def test_nonempty_declared_fields_without_config_raises(self):
        """Transform declares output fields but no _output_schema_config -> FrameworkBugError."""
        stub = _StubTransform()
        stub.declared_output_fields = frozenset({"field_a", "field_b"})
        stub._output_schema_config = None

        from elspeth.core.dag.builder import _validate_output_schema_contract

        with pytest.raises(FrameworkBugError, match="declares output fields"):
            _validate_output_schema_contract(stub)

    def test_nonempty_declared_fields_with_valid_config_passes(self):
        stub = _StubTransform()
        stub.declared_output_fields = frozenset({"field_a"})
        stub._output_schema_config = SchemaConfig(
            mode="observed", fields=None, guaranteed_fields=("field_a",)
        )

        from elspeth.core.dag.builder import _validate_output_schema_contract

        _validate_output_schema_contract(stub)  # Should not raise

    def test_empty_declared_fields_without_config_passes(self):
        """Shape-preserving transforms (no declared fields) don't need _output_schema_config."""
        stub = _StubTransform()
        stub.declared_output_fields = frozenset()
        stub._output_schema_config = None

        from elspeth.core.dag.builder import _validate_output_schema_contract

        _validate_output_schema_contract(stub)  # Should not raise
```

- [ ] **Step 3: Run tests — verify enforcement tests fail**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/test_output_schema_enforcement.py -v`
Expected: FAIL — `_validate_output_schema_contract` does not exist.

- [ ] **Step 4: Implement the DAG builder changes**

In `src/elspeth/core/dag/builder.py`:

**a)** Add import at the top (after the existing `from elspeth.contracts` imports):

```python
from elspeth.contracts.errors import FrameworkBugError
```

**b)** Add the validation function (before `build_execution_graph`):

```python
def _validate_output_schema_contract(transform: Any) -> None:
    """Validate that transforms declaring output fields provide a DAG contract.

    Raises FrameworkBugError if declared_output_fields is non-empty but
    _output_schema_config is None. This prevents silent DAG validation gaps.
    """
    if transform.declared_output_fields and transform._output_schema_config is None:
        raise FrameworkBugError(
            f"Transform {transform.name!r} declares output fields "
            f"{sorted(transform.declared_output_fields)} but provides no "
            f"_output_schema_config for DAG contract validation. "
            f"Call self._output_schema_config = self._build_output_schema_config(schema_config) "
            f"in __init__ after setting declared_output_fields."
        )
```

**c)** Replace the transform `getattr` site (~line 218-223). Remove the multi-line `getattr` justification comment and the `getattr` call, replace with:

```python
        # Validate output schema contract — crash if transform declares output
        # fields but provides no DAG contract.
        _validate_output_schema_contract(transform)
        output_schema_config = transform._output_schema_config
```

**d)** Replace the aggregation `getattr` site (~line 250-251). Remove the comment and `getattr` call, replace with:

```python
        # Same validation for aggregation transforms.
        _validate_output_schema_contract(transform)
        agg_output_schema_config = transform._output_schema_config
```

- [ ] **Step 5: Run all new and existing tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/ tests/unit/core/test_dag_schema_propagation.py -x -q`
Expected: All pass (mocks fixed in Step 1, enforcement tests pass from Step 4).

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/core/dag/builder.py tests/unit/core/dag/test_output_schema_enforcement.py tests/unit/core/test_dag_schema_propagation.py
git commit -m "feat: add FrameworkBugError check for missing _output_schema_config in DAG builder

Also fixes MockTransformWithoutSchemaConfig and MockAggregationTransform
in test_dag_schema_propagation.py to include declared_output_fields."
```

---

### Task 4: Add LLM Transform Comment and Verify Tier Model

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py`
- Modify: `config/cicd/enforce_tier_model/plugins.yaml` (if needed)

- [ ] **Step 1: Add invariant comment to LLM transform**

In `src/elspeth/plugins/transforms/llm/transform.py`, find the multi-query `_output_schema_config` construction (search for `self._output_schema_config = SchemaConfig(` — there are two sites). Add a comment before each:

```python
            # Output schema config with prefixed fields for DAG contract propagation.
            # INVARIANT: guaranteed_fields must be a superset of declared_output_fields.
            # This transform builds _output_schema_config manually (not via
            # _build_output_schema_config) because multi-query field computation
            # requires prefix interpolation beyond the generic helper's scope.
            # See: docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md
```

- [ ] **Step 2: Run the tier model enforcer and full verification**

```bash
.venv/bin/python -m pytest tests/unit/plugins/transforms/ -x -q
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
.venv/bin/python -m mypy src/elspeth/plugins/infrastructure/base.py src/elspeth/core/dag/builder.py src/elspeth/plugins/transforms/llm/transform.py
.venv/bin/python -m ruff check src/elspeth/
```

If tier model enforcer reports stale fingerprints, update `config/cicd/enforce_tier_model/plugins.yaml`.

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add src/elspeth/plugins/transforms/llm/transform.py
git commit -m "docs: add output schema contract invariant comments to LLM transform"
```

If allowlist updated:
```bash
git add config/cicd/enforce_tier_model/plugins.yaml
git commit -m "chore: update tier model allowlist fingerprints for output schema contract changes"
```

---

### Task 5: Integration Test — Contract Enforcement End-to-End

**Files:**
- Create: `tests/integration/plugins/transforms/test_output_schema_contract.py`

- [ ] **Step 1: Write the integration test**

This test verifies the full contract chain: transform construction → `_output_schema_config` populated → `_validate_output_schema_contract` passes → `guaranteed_fields` contains declared fields. It uses real transform instances (not stubs) and the production validation function from the DAG builder.

Note: `ExecutionGraph.from_plugin_instances()` requires `SourceProtocol`, `WiredTransform`, `SinkProtocol`, and `GateSettings` — heavy machinery that no existing test exercises. Instead, we test the contract invariants that the builder relies on, using real transform instances and the builder's validation function. This covers the contract surface area without requiring full pipeline orchestration.

Create `tests/integration/plugins/transforms/test_output_schema_contract.py`:

```python
"""Integration test for output schema contract enforcement.

Tests the full contract chain using real transform instances:
1. Transform construction populates _output_schema_config via helper
2. _validate_output_schema_contract passes for correctly-configured transforms
3. _validate_output_schema_contract raises FrameworkBugError when contract missing
4. Invariant 2: guaranteed_fields is superset of declared_output_fields

Uses real transforms (not stubs) to verify the end-to-end path
from plugin construction through DAG builder validation.
"""

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.core.dag.builder import _validate_output_schema_contract
from elspeth.plugins.transforms.batch_replicate import BatchReplicate
from elspeth.plugins.transforms.batch_stats import BatchStats
from elspeth.plugins.transforms.field_mapper import FieldMapper
from elspeth.plugins.transforms.json_explode import JSONExplode
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform
from elspeth.plugins.transforms.web_scrape import WebScrapeTransform


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch):
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key")


class TestContractInvariantsAcrossAllTransforms:
    """Verify Invariant 2 (guaranteed_fields superset of declared_output_fields)
    holds for every field-adding transform with real instances."""

    @pytest.mark.parametrize(
        "transform_factory",
        [
            pytest.param(
                lambda: RAGRetrievalTransform(
                    {"output_prefix": "sci", "query_field": "q", "provider": "chroma",
                     "provider_config": {"collection": "test-col", "mode": "ephemeral"},
                     "schema": {"mode": "observed"}}
                ),
                id="rag",
            ),
            pytest.param(
                lambda: JSONExplode(
                    {"array_field": "items", "output_field": "item",
                     "include_index": True, "schema": {"mode": "observed"}}
                ),
                id="json_explode",
            ),
            pytest.param(
                lambda: BatchReplicate(
                    {"include_copy_index": True, "schema": {"mode": "observed"}}
                ),
                id="batch_replicate",
            ),
            pytest.param(
                lambda: FieldMapper(
                    {"mapping": {"a": "b"}, "schema": {"mode": "observed"}}
                ),
                id="field_mapper",
            ),
            pytest.param(
                lambda: BatchStats(
                    {"value_field": "amount", "schema": {"mode": "observed"}}
                ),
                id="batch_stats",
            ),
            pytest.param(
                lambda: WebScrapeTransform(
                    {"url_field": "url", "content_field": "page_content",
                     "fingerprint_field": "page_hash",
                     "http": {"abuse_contact": "test@example.com",
                              "scraping_reason": "Integration test"},
                     "schema": {"mode": "observed"}}
                ),
                id="web_scrape",
            ),
        ],
    )
    def test_invariant2_guaranteed_superset_of_declared(self, transform_factory):
        """Every field-adding transform's guaranteed_fields contains all declared_output_fields."""
        transform = transform_factory()
        assert transform._output_schema_config is not None, (
            f"{transform.name}: _output_schema_config is None"
        )
        guaranteed = frozenset(transform._output_schema_config.guaranteed_fields)
        assert transform.declared_output_fields.issubset(guaranteed), (
            f"{transform.name}: declared_output_fields {transform.declared_output_fields} "
            f"not a subset of guaranteed_fields {guaranteed}"
        )

    @pytest.mark.parametrize(
        "transform_factory",
        [
            pytest.param(
                lambda: RAGRetrievalTransform(
                    {"output_prefix": "sci", "query_field": "q", "provider": "chroma",
                     "provider_config": {"collection": "test-col", "mode": "ephemeral"},
                     "schema": {"mode": "observed"}}
                ),
                id="rag",
            ),
            pytest.param(
                lambda: JSONExplode(
                    {"array_field": "items", "output_field": "item",
                     "schema": {"mode": "observed"}}
                ),
                id="json_explode",
            ),
            pytest.param(
                lambda: FieldMapper(
                    {"mapping": {"a": "b"}, "schema": {"mode": "observed"}}
                ),
                id="field_mapper",
            ),
        ],
    )
    def test_enforcement_passes_for_valid_transforms(self, transform_factory):
        """Transforms with declared_output_fields AND _output_schema_config pass validation."""
        transform = transform_factory()
        _validate_output_schema_contract(transform)  # Should not raise

    def test_enforcement_fires_on_missing_contract(self):
        """A real transform with cleared _output_schema_config triggers FrameworkBugError."""
        transform = RAGRetrievalTransform(
            {"output_prefix": "sci", "query_field": "q", "provider": "chroma",
             "provider_config": {"collection": "test-col", "mode": "ephemeral"},
             "schema": {"mode": "observed"}}
        )
        transform._output_schema_config = None

        with pytest.raises(FrameworkBugError, match="declares output fields"):
            _validate_output_schema_contract(transform)

    def test_rag_guaranteed_fields_exact(self):
        """RAG transform's guaranteed_fields contains exactly the 4 declared output fields."""
        transform = RAGRetrievalTransform(
            {"output_prefix": "sci", "query_field": "q", "provider": "chroma",
             "provider_config": {"collection": "test-col", "mode": "ephemeral"},
             "schema": {"mode": "observed"}}
        )
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {"sci__rag_context", "sci__rag_score", "sci__rag_count", "sci__rag_sources"}
        )
```

- [ ] **Step 2: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/plugins/transforms/test_output_schema_contract.py -v`
Expected: All pass.

- [ ] **Step 3: Run the example pipelines**

```bash
./examples/chroma_rag/run.sh
./examples/chroma_rag_qa/run.sh
```

Expected: Both complete successfully (8/8 rows, 0 quarantined).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/plugins/transforms/test_output_schema_contract.py
git commit -m "test: add integration test for output schema contract enforcement"
```

---

### Task 6: Final Verification and Cleanup

- [ ] **Step 1: Run the full test suite for all affected areas**

```bash
.venv/bin/python -m pytest tests/unit/plugins/transforms/ tests/unit/plugins/infrastructure/ tests/unit/core/dag/ tests/unit/core/test_dag_schema_propagation.py tests/integration/plugins/transforms/ -x -q
```

Expected: All pass.

- [ ] **Step 2: Run mypy on all changed files**

```bash
.venv/bin/python -m mypy src/elspeth/plugins/infrastructure/base.py src/elspeth/core/dag/builder.py src/elspeth/plugins/transforms/rag/transform.py src/elspeth/plugins/transforms/web_scrape.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/batch_replicate.py src/elspeth/plugins/transforms/field_mapper.py src/elspeth/plugins/transforms/batch_stats.py src/elspeth/plugins/transforms/llm/transform.py
```

Expected: `Success: no issues found`.

- [ ] **Step 3: Run ruff**

```bash
.venv/bin/python -m ruff check src/elspeth/
```

Expected: `All checks passed!`

- [ ] **Step 4: Verify tier model enforcer**

```bash
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
```

Expected: `No bug-hiding patterns detected. Check passed.`

- [ ] **Step 5: Run example pipelines**

```bash
./examples/chroma_rag/run.sh
./examples/chroma_rag_qa/run.sh
```

Expected: Both complete successfully (8/8 rows, 0 quarantined).

- [ ] **Step 6: Update spec status**

Change the spec status from `Draft` to `Implemented` in `docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md`.

- [ ] **Step 7: Final commit**

```bash
git add docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md
git commit -m "docs: mark output schema contract enforcement spec as implemented"
```
