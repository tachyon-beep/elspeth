# Output Schema Contract Enforcement

**Date:** 2026-03-20
**Status:** Draft
**Scope:** BaseTransform, DAG builder, all field-adding transforms

## Problem Statement

ELSPETH's DAG builder validates edges between transforms by checking that a producer's `guaranteed_fields` satisfy a consumer's `required_input_fields`. This validation depends on transforms setting `_output_schema_config` — a `SchemaConfig` instance that declares which fields the transform guarantees in its output.

This contract is currently **optional and unenforced**. The DAG builder reads it via `getattr(transform, "_output_schema_config", None)` and silently skips validation when the attribute is absent. Six transforms declare output fields via `declared_output_fields` but never set `_output_schema_config`, creating a gap where DAG validation cannot verify their output contracts.

### Affected Transforms

| Transform | Has `declared_output_fields` | Has `_output_schema_config` | Gap |
|-----------|------------------------------|----------------------------|-----|
| `rag/transform.py` | Yes (4 fields) | Yes (manual) | Fixed in prior commit, but manual — should use helper |
| `web_scrape.py` | Yes (8 fields) | No | DAG invisible |
| `json_explode.py` | Yes (config-driven) | No | DAG invisible |
| `batch_replicate.py` | Yes (conditional `copy_index`) | No | DAG invisible |
| `field_mapper.py` | **No** (empty default) | No | DAG invisible AND undeclared |
| `batch_stats.py` | **No** (empty default) | No | DAG invisible AND undeclared |

Transforms that are **not affected** (already correct):
- `llm/transform.py` — manually builds `_output_schema_config` with complex multi-query logic
- `llm/openrouter_batch.py` — same
- `llm/azure_batch.py` — same

### Consequences

1. Downstream transforms cannot use `required_input_fields` to declare dependencies on fields produced by these transforms — the DAG builder rejects the edge as "missing field."
2. Pipeline authors must use `required_input_fields: []` (opt-out) to bypass validation, defeating the purpose of static field checking.
3. The gap is silent — no error, no warning. Authors discover it only when a downstream transform fails at runtime or when DAG validation rejects a valid pipeline.

### Root Cause: Shifting the Burden

The `_create_schemas` helper handles runtime Pydantic schemas but not build-time DAG contracts. Authors call `_create_schemas(..., adds_fields=True)` and feel done — the helper's name and behavior signal "schema setup is complete." The actual contract (`_output_schema_config`) requires a separate, non-obvious manual step. Five transforms have already settled into the incomplete pattern.

## Design

### Invariants This Design Enforces

1. **If a transform declares output fields, it MUST provide a DAG contract.** A transform with non-empty `declared_output_fields` and `_output_schema_config is None` is a `FrameworkBugError` at graph-build time. No silent skip.

2. **`_output_schema_config.guaranteed_fields` MUST be a superset of `declared_output_fields`.** The helper method enforces this by construction — it merges `declared_output_fields` into `guaranteed_fields`. Transforms that build `_output_schema_config` manually (LLM transforms) are responsible for maintaining this invariant themselves. A comment in the LLM transform code should reference this spec and the invariant.

3. **Every transform that uses `adds_fields=True` MUST set `declared_output_fields` before calling `_build_output_schema_config`.** The method reads `self.declared_output_fields` — if it's the default empty `frozenset()`, the resulting `guaranteed_fields` contains no transform-specific fields. The DAG builder check (invariant 1) catches this if the transform later sets `declared_output_fields` but forgot the helper call. **Residual gap:** if a developer calls `_build_output_schema_config` *before* populating `declared_output_fields`, the result is a valid but empty contract — the enforcement check does not catch "helper called too early." This is addressable only by code review.

4. **`_create_schemas` remains a pure schema factory.** It does not set `_output_schema_config`. The two concerns (runtime Pydantic schemas and build-time DAG contracts) are handled by separate methods with no hidden coupling.

### Part 1: Base Class Changes (`BaseTransform`)

#### Declare `_output_schema_config` as a class attribute

```python
class BaseTransform:
    _output_schema_config: SchemaConfig | None = None
```

This eliminates the `getattr` pattern in the DAG builder. Direct attribute access with `None` check. Add `SchemaConfig` to the existing `if TYPE_CHECKING:` import block in `base.py` (alongside the existing `LifecycleContext`, `TransformContext`, etc. imports).

#### Add `_build_output_schema_config` helper method

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

Design decisions:
- **Returns** the `SchemaConfig` — does not set it. The caller assigns explicitly: `self._output_schema_config = self._build_output_schema_config(cfg)`. No hidden side effects.
- **`_create_schemas` stays `@staticmethod`, unchanged.** Runtime Pydantic schemas and build-time DAG contracts are separate concerns handled by separate methods.
- **LLM transforms are unaffected.** They don't use `_create_schemas` or `_build_output_schema_config` — their multi-query field logic requires manual construction, which is correct for their complexity level.

#### Fix type annotation on `_create_schemas`

Change `schema_config: Any` to `schema_config: SchemaConfig` under `TYPE_CHECKING`. The `SchemaConfig` import added to the `TYPE_CHECKING` block (above) serves both the class attribute annotation and this parameter annotation.

### Part 2: DAG Builder Validation (`dag/builder.py`)

At both `getattr` sites (line 223 for transforms, line 251 for aggregations), replace `getattr` with direct attribute access and add the offensive check. Remove the now-stale `getattr` justification comments.

```python
output_schema_config = transform._output_schema_config

if transform.declared_output_fields and output_schema_config is None:
    raise FrameworkBugError(
        f"Transform {transform.name!r} declares output fields "
        f"{sorted(transform.declared_output_fields)} but provides no "
        f"_output_schema_config for DAG contract validation. "
        f"Call self._output_schema_config = self._build_output_schema_config(schema_config) "
        f"in __init__ after setting declared_output_fields."
    )
```

The error message includes the fix instruction — offensive programming with actionable diagnostics.

### Part 3: Fix All Affected Transforms

All transforms call `_build_output_schema_config` **unconditionally** after setting `declared_output_fields`. When `declared_output_fields` is empty (e.g. `batch_replicate` with `include_copy_index=False`), the helper returns base `guaranteed_fields` only — still useful for DAG propagation.

#### Transforms that already have `declared_output_fields` (add helper call only)

**`rag/transform.py`**: Remove the manual `_output_schema_config` construction (lines 89–99). Replace with:
```python
self._output_schema_config = self._build_output_schema_config(self._rag_config.schema_config)
```
Note: `declared_output_fields` is set at lines 73–79 with prefix-interpolated names (e.g. `{prefix}__rag_context`), before `_create_schemas` at line 82. The ordering is already correct — the helper call goes after both.

**`web_scrape.py`**: Add after `declared_output_fields` is set:
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```
Note: `web_scrape` doesn't use `_create_schemas` — it builds schemas manually. The helper call is independent.

**`json_explode.py`**: Add after `declared_output_fields` is set:
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

**`batch_replicate.py`**: Add after `declared_output_fields` is set (unconditionally — see note above):
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

#### Transforms that need `declared_output_fields` populated first

**`field_mapper.py`**: The mapping target names are the output fields. Before `_create_schemas`:
```python
# Mapping targets are the fields this transform adds/renames to in the output.
# Note: for rename-only mappings where the target already exists in the input,
# TransformExecutor collision detection may need review — but declared_output_fields
# is correct for DAG contract purposes (these fields are guaranteed in output).
self.declared_output_fields = frozenset(cfg.mapping.values())
```
Then add the helper call after `_create_schemas`.

**Implementation note:** `field_mapper` with `select_only=False` and rename-only mappings may have the target field already present in the input row. Verify that `TransformExecutor` collision detection handles this case correctly (collision check is against *other transforms'* declared fields, not input row keys). If collision detection checks against input keys, the rename case needs a carve-out. Document findings during implementation.

**`batch_stats.py`**: The output fields are computed from config. Before `_create_schemas`:
```python
stat_fields: set[str] = {"count", "sum", "batch_size"}
if cfg.compute_mean:
    stat_fields.add("mean")
if cfg.group_by is not None:
    stat_fields.add(cfg.group_by)
self.declared_output_fields = frozenset(stat_fields)
```
Then add the helper call after `_create_schemas`.

**Design notes on `batch_stats` fields:**
- `group_by` is included in `declared_output_fields` when configured — the transform guarantees it in output when the config specifies it.
- `skipped_non_finite` and `skipped_non_finite_indices` are intentionally **not** declared — they are data-dependent (only emitted when non-finite values are encountered), not config-guaranteed.

### Part 4: Testing Strategy

#### Unit tests: `_build_output_schema_config` helper

| Test | Assertion |
|------|-----------|
| Merges base guaranteed + declared output fields | `guaranteed_fields` is the union (exact `frozenset` equality) |
| Empty `declared_output_fields` | Returns base guaranteed only |
| Empty base `guaranteed_fields` | Returns declared output fields only |
| Preserves other config fields | `mode`, `fields`, `audit_fields`, `required_fields` pass through unchanged |
| Non-`None` `audit_fields` passes through | Regression guard if helper is later modified |

#### Unit tests: DAG builder validation

Use a minimal hand-crafted stub implementing `TransformProtocol` with configurable `declared_output_fields` and `_output_schema_config`. Call the builder entry point directly. Do not use a real transform that already has a valid `_output_schema_config`.

| Test | Assertion |
|------|-----------|
| Non-empty `declared_output_fields`, `_output_schema_config = None` | Raises `FrameworkBugError` |
| Non-empty `declared_output_fields`, valid `_output_schema_config` | Passes |
| Empty `declared_output_fields`, `_output_schema_config = None` | Passes (shape-preserving transform) |

#### Per-transform unit tests (pin `guaranteed_fields` content)

Each affected transform gets a test that constructs an instance with a representative config and asserts `_output_schema_config.guaranteed_fields` contains the expected field names. Use **exact `frozenset` equality** (not `issubset`) to catch both missing and spurious fields. These are separate from the existing `test_declared_output_fields` tests — they test different attributes (`declared_output_fields` for collision detection vs `guaranteed_fields` for DAG contracts).

| Transform | Config | Expected `guaranteed_fields` (exact) |
|-----------|--------|--------------------------------------|
| `rag` | `output_prefix="sci"`, `schema: {mode: observed}` | `{"sci__rag_context", "sci__rag_score", "sci__rag_count", "sci__rag_sources"}` |
| `web_scrape` | `content_field="page_content"`, `fingerprint_field="page_hash"` | `{"page_content", "page_hash", "fetch_status", "fetch_url_final", "fetch_url_final_ip", "fetch_request_hash", "fetch_response_raw_hash", "fetch_response_processed_hash"}` |
| `json_explode` | `array_field="items"`, `output_field="item"`, `include_index=True` | `{"item", "item_index"}` |
| `json_explode` | `array_field="items"`, `output_field="item"`, `include_index=False` | `{"item"}` |
| `batch_replicate` | `include_copy_index=True` | `{"copy_index"}` |
| `batch_replicate` | `include_copy_index=False` | `frozenset()` (empty — verify against source that field is truly conditional) |
| `field_mapper` | `mapping={"old_name": "new_name", "source": "target"}` | `{"new_name", "target"}` |
| `batch_stats` | `value_field="amount"`, `compute_mean=True`, `group_by="category"` | `{"count", "sum", "batch_size", "mean", "category"}` |
| `batch_stats` | `value_field="amount"`, `compute_mean=False`, `group_by=None` | `{"count", "sum", "batch_size"}` |

#### Integration test: RAG → LLM with DAG field validation

This test MUST use `ExecutionGraph.from_plugin_instances()` (the production code path), not raw `graph.add_node()`/`graph.add_edge()` construction. Use a CSV source stub or existing test fixtures.

| Scenario | Assertion |
|----------|-----------|
| RAG outputs `sci__rag_context`, LLM declares `required_input_fields: [sci__rag_context]` | Graph builds successfully |
| RAG outputs `sci__rag_context`, LLM declares `required_input_fields: [nonexistent_field]` | Graph rejects edge with missing field error |

### Relationship to Existing Systems

| System | When | Purpose | Changed? |
|--------|------|---------|----------|
| `_output_schema_config` / `guaranteed_fields` | Graph build | DAG edge validation — "does this field exist?" | **Yes** — enforced, helper added |
| `_create_schemas` / `adds_fields` | Plugin init | Output Pydantic schema — "accept any fields at runtime?" | **No** — unchanged |
| `propagate_contract` / `transform_adds_fields` | Row processing | Contract propagation — "infer types for new fields?" | **No** — unchanged |
| `declared_output_fields` | Plugin init + executor | Collision detection in TransformExecutor | **Extended** — also feeds `_build_output_schema_config` |

**Layer dependency:** `SchemaConfig` lives at L0 (`contracts/schema.py`). `BaseTransform` lives at L3 (`plugins/infrastructure/base.py`). L3 importing L0 is a valid downward dependency. The `TYPE_CHECKING` import follows the existing pattern in `base.py`.

### Files Changed

| File | Change |
|------|--------|
| `src/elspeth/plugins/infrastructure/base.py` | Add `_output_schema_config` class attr, add `_build_output_schema_config` method, fix `_create_schemas` type annotation, add `SchemaConfig` to `TYPE_CHECKING` imports |
| `src/elspeth/core/dag/builder.py` | Replace `getattr` with direct access + offensive check (2 sites), remove stale `getattr` justification comments |
| `src/elspeth/plugins/transforms/rag/transform.py` | Replace manual construction with helper call, remove `SchemaConfig` import (now in base) |
| `src/elspeth/plugins/transforms/web_scrape.py` | Add helper call |
| `src/elspeth/plugins/transforms/json_explode.py` | Add helper call |
| `src/elspeth/plugins/transforms/batch_replicate.py` | Add helper call |
| `src/elspeth/plugins/transforms/field_mapper.py` | Populate `declared_output_fields`, add helper call, verify collision detection compatibility |
| `src/elspeth/plugins/transforms/batch_stats.py` | Populate `declared_output_fields` (including conditional `group_by`), add helper call |
| `src/elspeth/plugins/transforms/llm/transform.py` | Add comment referencing this spec and Invariant 2 (manual `_output_schema_config` responsibility) |
| `config/cicd/enforce_tier_model/plugins.yaml` | Update allowlist fingerprints if any defensive patterns change |
| Tests (new/modified) | Unit tests for helper, DAG check, per-transform pinning, integration test |
