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

2. **`_output_schema_config.guaranteed_fields` MUST be a superset of `declared_output_fields`.** The helper method enforces this by construction — it merges `declared_output_fields` into `guaranteed_fields`. Transforms that build `_output_schema_config` manually (LLM transforms) are responsible for maintaining this invariant themselves.

3. **Every transform that uses `adds_fields=True` MUST set `declared_output_fields` before calling `_build_output_schema_config`.** The method reads `self.declared_output_fields` — if it's the default empty `frozenset()`, the resulting `guaranteed_fields` contains no transform-specific fields. The DAG builder check (invariant 1) catches this if the transform later sets `declared_output_fields` but forgot the helper call.

4. **`_create_schemas` remains a pure schema factory.** It does not set `_output_schema_config`. The two concerns (runtime Pydantic schemas and build-time DAG contracts) are handled by separate methods with no hidden coupling.

### Part 1: Base Class Changes (`BaseTransform`)

#### Declare `_output_schema_config` as a class attribute

```python
class BaseTransform:
    _output_schema_config: SchemaConfig | None = None
```

This eliminates the `getattr` pattern in the DAG builder. Direct attribute access with `None` check. Uses `TYPE_CHECKING` import for `SchemaConfig` to avoid circular dependency.

#### Add `_build_output_schema_config` helper method

```python
def _build_output_schema_config(self, schema_config: SchemaConfig) -> SchemaConfig:
    """Build output schema config for DAG contract propagation.

    Merges the transform's declared_output_fields into guaranteed_fields
    so the DAG builder can validate downstream field requirements.

    Args:
        schema_config: The transform's input schema config (base fields).

    Returns:
        SchemaConfig with guaranteed_fields including declared output fields.
    """
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

Change `schema_config: Any` to `schema_config: SchemaConfig` under `TYPE_CHECKING`. This is a pre-existing type annotation gap.

### Part 2: DAG Builder Validation (`dag/builder.py`)

At both `getattr` sites (line 223 for transforms, line 251 for aggregations), replace `getattr` with direct attribute access and add the offensive check:

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

#### Transforms that already have `declared_output_fields` (add helper call only)

**`rag/transform.py`**: Remove the manual `_output_schema_config` construction (lines 89–99). Replace with:
```python
self._output_schema_config = self._build_output_schema_config(self._rag_config.schema_config)
```

**`web_scrape.py`**: Add after `declared_output_fields` is set:
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```
Note: `web_scrape` doesn't use `_create_schemas` — it builds schemas manually. The helper call is independent.

**`json_explode.py`**: Add after `declared_output_fields` is set:
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

**`batch_replicate.py`**: Add after `declared_output_fields` is set:
```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

#### Transforms that need `declared_output_fields` populated first

**`field_mapper.py`**: The mapping target names are the output fields. Before `_create_schemas`:
```python
# Mapping targets are the fields this transform adds to the output
self.declared_output_fields = frozenset(cfg.mapping.values())
```
Then add the helper call after `_create_schemas`.

**`batch_stats.py`**: The output fields are computed from config. Before `_create_schemas`:
```python
stat_fields = {"count", "sum", "batch_size"}
if cfg.compute_mean:
    stat_fields.add("mean")
self.declared_output_fields = frozenset(stat_fields)
```
Then add the helper call after `_create_schemas`.

Note: `batch_stats` also emits the `group_by` field value if configured, but that field's name comes from the data, not from config — it's a passthrough of an existing field, not a new declared output.

### Part 4: Testing Strategy

#### Unit tests: `_build_output_schema_config` helper

| Test | Assertion |
|------|-----------|
| Merges base guaranteed + declared output fields | `guaranteed_fields` is the union |
| Empty `declared_output_fields` | Returns base guaranteed only |
| Empty base `guaranteed_fields` | Returns declared output fields only |
| Preserves other config fields | `mode`, `fields`, `audit_fields`, `required_fields` pass through |

#### Unit tests: DAG builder validation

| Test | Assertion |
|------|-----------|
| Non-empty `declared_output_fields`, no `_output_schema_config` | Raises `FrameworkBugError` |
| Non-empty `declared_output_fields`, valid `_output_schema_config` | Passes |
| Empty `declared_output_fields`, no `_output_schema_config` | Passes (shape-preserving transform) |

#### Per-transform unit tests (pin `guaranteed_fields` content)

Each affected transform gets a test that constructs an instance with a representative config and asserts `_output_schema_config.guaranteed_fields` contains the expected field names:

| Transform | Expected guaranteed fields |
|-----------|--------------------------|
| `rag` | `{prefix}__rag_context`, `{prefix}__rag_score`, `{prefix}__rag_count`, `{prefix}__rag_sources` |
| `web_scrape` | `content_field`, `fingerprint_field`, `fetch_status`, `fetch_url_final`, etc. |
| `json_explode` | Config-driven field names + conditional `item_index` |
| `batch_replicate` | `copy_index` when `include_copy_index=True`; empty when False |
| `field_mapper` | Mapping target names from config |
| `batch_stats` | `count`, `sum`, `batch_size`, conditional `mean` |

#### Integration test: RAG → LLM with DAG field validation

Build a pipeline with `from_plugin_instances` where:
- RAG transform outputs `sci__rag_context` (via `guaranteed_fields`)
- LLM transform declares `required_input_fields: [sci__rag_context]`
- Assert: graph builds successfully without `required_input_fields: []` opt-out

### Relationship to Existing Systems

| System | When | Purpose | Changed? |
|--------|------|---------|----------|
| `_output_schema_config` / `guaranteed_fields` | Graph build | DAG edge validation — "does this field exist?" | **Yes** — enforced, helper added |
| `_create_schemas` / `adds_fields` | Plugin init | Output Pydantic schema — "accept any fields at runtime?" | **No** — unchanged |
| `propagate_contract` / `transform_adds_fields` | Row processing | Contract propagation — "infer types for new fields?" | **No** — unchanged |
| `declared_output_fields` | Plugin init + executor | Collision detection in TransformExecutor | **Extended** — also feeds `_build_output_schema_config` |

### Files Changed

| File | Change |
|------|--------|
| `src/elspeth/plugins/infrastructure/base.py` | Add `_output_schema_config` class attr, add `_build_output_schema_config` method, fix `_create_schemas` type annotation |
| `src/elspeth/core/dag/builder.py` | Replace `getattr` with direct access + offensive check (2 sites) |
| `src/elspeth/plugins/transforms/rag/transform.py` | Replace manual construction with helper call |
| `src/elspeth/plugins/transforms/web_scrape.py` | Add helper call |
| `src/elspeth/plugins/transforms/json_explode.py` | Add helper call |
| `src/elspeth/plugins/transforms/batch_replicate.py` | Add helper call |
| `src/elspeth/plugins/transforms/field_mapper.py` | Populate `declared_output_fields`, add helper call |
| `src/elspeth/plugins/transforms/batch_stats.py` | Populate `declared_output_fields`, add helper call |
| `config/cicd/enforce_tier_model/plugins.yaml` | Update allowlist fingerprints if any defensive patterns change |
| Tests (new/modified) | Unit tests for helper, DAG check, per-transform pinning, integration test |
