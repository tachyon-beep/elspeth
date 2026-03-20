# Output Schema Contract Enforcement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that every transform declaring output fields also provides a DAG contract (`_output_schema_config`), closing a gap where 6 transforms silently skip build-time field validation.

**Architecture:** Add `_build_output_schema_config` helper to `BaseTransform` and an offensive check in the DAG builder. Fix all 6 affected transforms atomically. `_create_schemas` stays unchanged.

**Tech Stack:** Python dataclasses (`SchemaConfig`), pluggy transform system, pytest, `FrameworkBugError` offensive checks.

**Spec:** `docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md`

---

### Task 1: Base Class — Add `_output_schema_config` Class Attribute and `_build_output_schema_config` Helper

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/base.py`
- Create: `tests/unit/plugins/infrastructure/test_build_output_schema_config.py`

- [ ] **Step 1: Write the failing tests for `_build_output_schema_config`**

Create `tests/unit/plugins/infrastructure/test_build_output_schema_config.py`:

```python
"""Tests for BaseTransform._build_output_schema_config helper."""

from elspeth.contracts.schema import SchemaConfig
from elspeth.plugins.transforms.keyword_filter import KeywordFilterTransform


def _make_minimal_transform(declared_fields: frozenset[str] | None = None):
    """Create a minimal transform to test the base class helper.

    Uses KeywordFilterTransform as a concrete BaseTransform subclass
    (simplest available — no external deps, no adds_fields).
    """
    transform = KeywordFilterTransform(
        {
            "field": "text",
            "keywords": ["test"],
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
        from elspeth.contracts.schema import FieldDefinition

        fields = (
            FieldDefinition(name="id", type=int, original_name="id", required=True, source="config"),
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

### Task 2: DAG Builder — Offensive Check for Missing Output Schema Config

**Files:**
- Modify: `src/elspeth/core/dag/builder.py`
- Create: `tests/unit/core/dag/test_output_schema_enforcement.py`

- [ ] **Step 1: Write the failing tests**

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

        # Import the check function we'll extract, or inline the logic
        # The actual check lives in builder.py — we test via the builder entry point
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

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/test_output_schema_enforcement.py -v`
Expected: FAIL — `_validate_output_schema_contract` does not exist.

- [ ] **Step 3: Implement the DAG builder changes**

In `src/elspeth/core/dag/builder.py`:

**a)** Add import at the top (after existing imports, ~line 31):

```python
from elspeth.contracts.errors import FrameworkBugError
```

**b)** Add the validation function (before `build_execution_graph`, around line 50):

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

**c)** Replace the transform `getattr` site (~line 218-223). Remove the multi-line comment and `getattr` call, replace with:

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

- [ ] **Step 4: Run new tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/test_output_schema_enforcement.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run existing DAG tests — verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/core/dag/ -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/elspeth/core/dag/builder.py tests/unit/core/dag/test_output_schema_enforcement.py
git commit -m "feat: add FrameworkBugError check for missing _output_schema_config in DAG builder"
```

---

### Task 3: Fix RAG Transform — Replace Manual Construction with Helper

**Files:**
- Modify: `src/elspeth/plugins/transforms/rag/transform.py`
- Modify: `tests/unit/plugins/transforms/rag/test_transform.py`

- [ ] **Step 1: Write the pinning test**

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

- [ ] **Step 2: Run test — verify it passes (manual construction still works)**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/test_transform.py::TestTransformLifecycle::test_output_schema_config_guaranteed_fields -v`
Expected: PASS (the manual construction at lines 89-99 is still in place).

- [ ] **Step 3: Replace manual construction with helper call**

In `src/elspeth/plugins/transforms/rag/transform.py`, replace lines 89-99:

```python
        # Output schema config with guaranteed_fields for DAG contract propagation.
        # Input fields pass through, and RAG adds its declared output fields.
        schema_config = self._rag_config.schema_config
        base_guaranteed = schema_config.guaranteed_fields or ()
        self._output_schema_config = SchemaConfig(
            mode=schema_config.mode,
            fields=schema_config.fields,
            guaranteed_fields=tuple(set(base_guaranteed) | self.declared_output_fields),
            audit_fields=schema_config.audit_fields,
            required_fields=schema_config.required_fields,
        )
```

With:

```python
        # Output schema config for DAG contract propagation.
        self._output_schema_config = self._build_output_schema_config(
            self._rag_config.schema_config
        )
```

Also remove the `SchemaConfig` import from the top of the file (line 23: `from elspeth.contracts.schema import SchemaConfig`) — it is no longer needed since the helper uses a local import. Check if any other code in the file uses `SchemaConfig` first — if not, remove it.

- [ ] **Step 4: Run all RAG tests — verify no regressions**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/rag/ -v`
Expected: All pass, including the new pinning test.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/rag/transform.py tests/unit/plugins/transforms/rag/test_transform.py
git commit -m "refactor: replace manual _output_schema_config in RAG transform with helper"
```

---

### Task 4: Fix json_explode — Add Helper Call and Pinning Tests

**Files:**
- Modify: `src/elspeth/plugins/transforms/json_explode.py`
- Modify: `tests/unit/plugins/transforms/test_json_explode.py`

- [ ] **Step 1: Write the pinning tests**

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

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_json_explode.py::TestOutputSchemaConfig -v`
Expected: FAIL — `_output_schema_config` is `None`.

- [ ] **Step 3: Add helper call to json_explode**

In `src/elspeth/plugins/transforms/json_explode.py`, add after the `_create_schemas` call (~line 134):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_json_explode.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/json_explode.py tests/unit/plugins/transforms/test_json_explode.py
git commit -m "feat: add _output_schema_config to json_explode transform"
```

---

### Task 5: Fix batch_replicate — Add Helper Call and Pinning Tests

**Files:**
- Modify: `src/elspeth/plugins/transforms/batch_replicate.py`
- Modify: `tests/unit/plugins/transforms/test_batch_replicate.py`

- [ ] **Step 1: Write the pinning tests**

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
        # Empty declared_output_fields -> guaranteed_fields has no transform-specific fields
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset()
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_batch_replicate.py::TestOutputSchemaConfig -v`
Expected: FAIL — `_output_schema_config` is `None`.

- [ ] **Step 3: Add helper call to batch_replicate**

In `src/elspeth/plugins/transforms/batch_replicate.py`, add after the `_create_schemas` call (~line 120):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_batch_replicate.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/batch_replicate.py tests/unit/plugins/transforms/test_batch_replicate.py
git commit -m "feat: add _output_schema_config to batch_replicate transform"
```

---

### Task 6: Fix field_mapper — Populate `declared_output_fields` and Add Helper Call

**Files:**
- Modify: `src/elspeth/plugins/transforms/field_mapper.py`
- Modify: `tests/unit/plugins/transforms/test_field_mapper.py`

- [ ] **Step 1: Write the pinning test**

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
        # Empty mapping = no declared output fields = no guaranteed fields
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

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_field_mapper.py::TestOutputSchemaConfig -v`
Expected: FAIL — `declared_output_fields` is empty, `_output_schema_config` is `None`.

- [ ] **Step 3: Add `declared_output_fields` and helper call to field_mapper**

In `src/elspeth/plugins/transforms/field_mapper.py`, in `__init__` (~line 91, after `self.validate_input = cfg.validate_input`):

```python
        # Mapping targets are the fields this transform adds/renames to in the output.
        self.declared_output_fields = frozenset(cfg.mapping.values())
```

Then after the `_create_schemas` call (~line 99):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_field_mapper.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/field_mapper.py tests/unit/plugins/transforms/test_field_mapper.py
git commit -m "feat: populate declared_output_fields and add _output_schema_config to field_mapper"
```

---

### Task 7: Fix batch_stats — Populate `declared_output_fields` and Add Helper Call

**Files:**
- Modify: `src/elspeth/plugins/transforms/batch_stats.py`
- Modify: `tests/unit/plugins/transforms/test_batch_stats.py`

- [ ] **Step 1: Write the pinning tests**

Add to `tests/unit/plugins/transforms/test_batch_stats.py`:

```python
class TestOutputSchemaConfig:
    def test_guaranteed_fields_with_mean_and_group_by(self):
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
            {"count", "sum", "batch_size", "mean", "category"}
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

    def test_declared_output_fields_set_from_config(self):
        transform = BatchStats(
            {
                "schema": {"mode": "observed"},
                "value_field": "amount",
                "group_by": "region",
            }
        )
        assert "region" in transform.declared_output_fields
        assert "count" in transform.declared_output_fields
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_batch_stats.py::TestOutputSchemaConfig -v`
Expected: FAIL — `declared_output_fields` is empty, `_output_schema_config` is `None`.

- [ ] **Step 3: Add `declared_output_fields` and helper call to batch_stats**

In `src/elspeth/plugins/transforms/batch_stats.py`, in `__init__` (~line 84, after `self._compute_mean = cfg.compute_mean`):

```python
        # Declare output fields for DAG contract validation.
        # skipped_non_finite/skipped_non_finite_indices are intentionally NOT
        # declared — they are data-dependent (only emitted when non-finite
        # values are encountered), not config-guaranteed.
        stat_fields: set[str] = {"count", "sum", "batch_size"}
        if cfg.compute_mean:
            stat_fields.add("mean")
        if cfg.group_by is not None:
            stat_fields.add(cfg.group_by)
        self.declared_output_fields = frozenset(stat_fields)
```

Then after the `_create_schemas` call (~line 92):

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_batch_stats.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/batch_stats.py tests/unit/plugins/transforms/test_batch_stats.py
git commit -m "feat: populate declared_output_fields and add _output_schema_config to batch_stats"
```

---

### Task 8: Fix web_scrape — Add Helper Call and Pinning Test

**Files:**
- Modify: `src/elspeth/plugins/transforms/web_scrape.py`
- Modify: `tests/unit/plugins/transforms/test_web_scrape.py`

- [ ] **Step 1: Write the pinning test**

Add to `tests/unit/plugins/transforms/test_web_scrape.py`. Note: `web_scrape` requires specific config. Find the existing test helper or constructor pattern in the file and adapt. The test needs:

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

- [ ] **Step 2: Run test — verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py::TestOutputSchemaConfig -v`
Expected: FAIL — `_output_schema_config` is `None`.

- [ ] **Step 3: Add helper call to web_scrape**

In `src/elspeth/plugins/transforms/web_scrape.py`, after `declared_output_fields` is set (~line 211) and after the schema construction (~line 249), add:

```python
        self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

Note: `web_scrape` does NOT use `_create_schemas` — it builds schemas manually. The helper call is independent of schema creation. Place it after line 249 (`self.output_schema = schema`).

- [ ] **Step 4: Run tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/test_web_scrape.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/elspeth/plugins/transforms/web_scrape.py tests/unit/plugins/transforms/test_web_scrape.py
git commit -m "feat: add _output_schema_config to web_scrape transform"
```

---

### Task 9: Add LLM Transform Comment and Verify Tier Model

**Files:**
- Modify: `src/elspeth/plugins/transforms/llm/transform.py`
- Modify: `config/cicd/enforce_tier_model/plugins.yaml` (if needed)

- [ ] **Step 1: Add invariant comment to LLM transform**

In `src/elspeth/plugins/transforms/llm/transform.py`, add a comment before the multi-query `_output_schema_config` construction (~line 978):

```python
            # Output schema config with prefixed fields for DAG contract propagation.
            # INVARIANT: guaranteed_fields must be a superset of declared_output_fields.
            # This transform builds _output_schema_config manually (not via
            # _build_output_schema_config) because multi-query field computation
            # requires prefix interpolation beyond the generic helper's scope.
            # See: docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md
```

Add the same comment before the single-query construction (~line 1018).

- [ ] **Step 2: Run the tier model enforcer**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

If any new violations are reported (fingerprint changes from modified files), update the allowlist in `config/cicd/enforce_tier_model/plugins.yaml` with the new fingerprints. The changes in this spec should not introduce new defensive patterns, but line number shifts may invalidate existing fingerprints.

- [ ] **Step 3: Run full verification suite**

Run all five verification commands from the spec:

```bash
.venv/bin/python -m pytest tests/unit/plugins/transforms/ -x -q
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
.venv/bin/python -m mypy src/elspeth/plugins/infrastructure/base.py src/elspeth/core/dag/builder.py
.venv/bin/python -m ruff check src/elspeth/
```

Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/elspeth/plugins/transforms/llm/transform.py
git commit -m "docs: add output schema contract invariant comments to LLM transform"
```

If allowlist was updated:

```bash
git add config/cicd/enforce_tier_model/plugins.yaml
git commit -m "chore: update tier model allowlist fingerprints for output schema contract changes"
```

---

### Task 10: Integration Test — RAG → LLM Pipeline with Field Validation

**Files:**
- Create: `tests/integration/plugins/transforms/test_output_schema_contract.py`

- [ ] **Step 1: Write the integration test**

This test MUST use `ExecutionGraph.from_plugin_instances()` — the production code path. It verifies that the RAG transform's `guaranteed_fields` are visible to downstream transforms' `required_input_fields` validation.

Create `tests/integration/plugins/transforms/test_output_schema_contract.py`:

```python
"""Integration test for output schema contract enforcement.

Verifies that RAG transform's guaranteed_fields propagate through
the DAG builder so downstream transforms can declare required_input_fields
without using the [] opt-out.

Uses ExecutionGraph.from_plugin_instances() — the production code path.
"""

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch):
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key")


def _make_rag_transform():
    """Create a RAG transform with known output prefix."""
    return RAGRetrievalTransform(
        {
            "output_prefix": "sci",
            "query_field": "question",
            "provider": "chroma",
            "provider_config": {
                "collection": "test-collection",
                "mode": "ephemeral",
            },
            "schema": {"mode": "observed"},
        }
    )


class TestOutputSchemaContractIntegration:
    def test_rag_guaranteed_fields_visible_to_dag(self):
        """RAG transform's declared output fields appear in _output_schema_config."""
        transform = _make_rag_transform()
        assert transform._output_schema_config is not None
        guaranteed = frozenset(transform._output_schema_config.guaranteed_fields)
        assert "sci__rag_context" in guaranteed
        assert "sci__rag_score" in guaranteed
        assert "sci__rag_count" in guaranteed
        assert "sci__rag_sources" in guaranteed

    def test_transform_without_contract_raises_at_build_time(self):
        """A transform with declared fields but no contract crashes the builder."""
        transform = _make_rag_transform()
        # Simulate the bug: clear _output_schema_config after construction
        transform._output_schema_config = None

        from elspeth.core.dag.builder import _validate_output_schema_contract

        with pytest.raises(FrameworkBugError, match="declares output fields"):
            _validate_output_schema_contract(transform)
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

### Task 11: Final Verification and Cleanup

- [ ] **Step 1: Run the full test suite for all affected areas**

```bash
.venv/bin/python -m pytest tests/unit/plugins/transforms/ tests/unit/plugins/infrastructure/ tests/unit/core/dag/ tests/integration/plugins/transforms/ -x -q
```

Expected: All pass.

- [ ] **Step 2: Run mypy on all changed files**

```bash
.venv/bin/python -m mypy src/elspeth/plugins/infrastructure/base.py src/elspeth/core/dag/builder.py src/elspeth/plugins/transforms/rag/transform.py src/elspeth/plugins/transforms/web_scrape.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/batch_replicate.py src/elspeth/plugins/transforms/field_mapper.py src/elspeth/plugins/transforms/batch_stats.py
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

- [ ] **Step 5: Update spec status**

Change the spec status from `Draft` to `Implemented` in `docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md`.

- [ ] **Step 6: Final commit**

```bash
git add docs/superpowers/specs/2026-03-20-output-schema-contract-enforcement-design.md
git commit -m "docs: mark output schema contract enforcement spec as implemented"
```
