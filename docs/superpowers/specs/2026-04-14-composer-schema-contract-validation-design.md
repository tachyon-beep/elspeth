# Composer Schema Contract Validation

**Date:** 2026-04-14
**Status:** Draft
**Triggered by:** False-positive pipeline completion — assistant reported a pipeline as complete when the runtime validator later rejected it due to unsatisfied schema contracts.

## Problem

The composer's `preview_pipeline` reports `is_valid: true` for pipelines that fail at runtime with `GraphValidationError: Schema contract violation`. The gap: `CompositionState.validate()` checks topology and structural completeness but never checks schema contracts (producer guaranteed fields vs consumer required fields).

A simple text source + value_transform pipeline demonstrated the failure: the transform declared `required_input_fields: ["text"]`, the source used `observed` schema with no guaranteed fields, the composer said "valid", and the runtime rejected it.

The bug has two halves:
1. **Tooling**: The composer doesn't validate schema contracts.
2. **Skill**: The assistant has no rule requiring field-contract verification before declaring completion.

## Scope

### In scope
- Schema contract validation in `CompositionState.validate()`
- Edge contract data exposed in `preview_pipeline` response
- Text source auto-guarantee heuristic for deterministic output
- Skill patch for `pipeline_composer.md`

### Out of scope
- Type compatibility checking (requires Pydantic schema instantiation — stays in runtime)
- Transform output field tracking (composer doesn't know what fields a transform adds)
- Full DAG construction in the composer (heavyweight, breaks the pure-function design)

## Design

### 1. Schema Contract Validation in `state.validate()`

**File:** `src/elspeth/web/composer/state.py`

Add validation pass 9 (error-level) to `CompositionState.validate()`.

#### Connection chain resolution

Build a producer map from the connection-field chain:

```
source.on_success = "step_a"  →  producer_map["step_a"] = (source, source.options)
node(input="step_a").on_success = "step_b"  →  producer_map["step_b"] = (node, node.options)
```

For each consumer node, look up the producer for `node.input`. Gates with routes produce data for multiple downstream connection points — each route target gets the same guaranteed fields as the gate's producer (gates are schema-preserving, they don't add or remove fields).

#### Contract check per edge

For each producer→consumer pair:

1. **Producer guaranteed fields**: Parse `producer.options["schema"]` via `SchemaConfig.from_dict()` (imported from `elspeth.contracts.schema`). Call `.get_effective_guaranteed_fields()`. If no schema config exists, guaranteed = empty frozenset.

2. **Consumer required fields**: Read `consumer.options.get("required_input_fields")`. If absent/empty, skip.

3. **Compare**: `missing = required - guaranteed`. If non-empty, emit error.

#### Guarantee propagation through transforms

A transform node's guaranteed fields are derived from its own `options["schema"]` if present. If a transform has no schema config, it makes no guarantee — downstream consumers see an empty guarantee set for that producer. This is conservative: the composer doesn't know what fields a transform adds or removes, so it only trusts explicit declarations.

In practice this means the contract check is most valuable for the source→first-consumer edge, where the source's schema is the authoritative declaration. For deeper edges, the runtime validator fills the gap.

#### Text source heuristic (closed list — text only)

When producer is a source with `plugin: "text"` and `options["column"]` is set, and the schema is `observed` with no explicit `guaranteed_fields`, infer `{column}` as a guaranteed field for contract comparison. If `guaranteed_fields` is already set explicitly, use the explicit value — the heuristic does not override or supplement explicit declarations.

Rationale: The text source always yields `{column: value}` (text_source.py:110). The output is fully deterministic — one field, always present.

**Enforcement link:** Add a comment in `text_source.py` near line 110 referencing the composer heuristic (`# Composer heuristic depends on this: web/composer/state.py infers {column} as guaranteed field`). This ensures a developer changing the text source's output key discovers the dependency. A cross-module test (test case 20) verifies both sides agree.

**This heuristic list is intentionally closed.** Only `text` qualifies because its output shape is fully determined by config (`column`). Other sources (csv, json, dataverse) have variable schemas depending on input data and do not qualify for heuristic inference. If a new source has fully deterministic output, the decision to add it here requires explicit design review, not incremental expansion. This constraint prevents the composer from gradually rebuilding the runtime validator via accumulated heuristics (the "Shifting the Burden" archetype).

#### Schema parse failure handling

If `SchemaConfig.from_dict()` raises `ValueError` on a producer or consumer's schema dict, emit an **error** (not warning) and set `is_valid` to `false`. Schema config is Tier 2 data (pipeline configuration we control). A malformed schema dict is a plugin configuration bug — the project's plugin ownership model requires these to crash, not degrade gracefully. Treating parse failures as warnings would allow `is_valid: true` for pipelines that will fail at runtime, which is the exact bug this spec fixes.

The error message should identify which node's schema failed to parse and include the `ValueError` message for debuggability.

#### Import placement

`SchemaConfig` is imported via deferred import inside the schema-validation pass function, following the existing pattern established by `_validate_gate_expression()` (which defers `from elspeth.core.expression_parser import ...`). This preserves `state.py`'s module-level import constraint ("Imports from L0 contracts.freeze only") while still using the real `SchemaConfig` at call time.

#### Error message format

```
Schema contract violation: 'source' -> 'add_world'.
  Consumer (value_transform) requires fields: ['text']
  Producer (text) guarantees: (none - observed schema)
  Missing fields: ['text']
  Fix: Add missing fields to the source schema (use mode 'fixed' or 'flexible'),
  set explicit guaranteed_fields, or remove from required_input_fields if optional.
```

### 2. Edge Contract Data in Preview Response

**Files:** `src/elspeth/web/composer/state.py`, `src/elspeth/web/composer/tools.py`

#### New dataclass

```python
@dataclass(frozen=True, slots=True)
class EdgeContract:
    """Schema contract check result for a single producer->consumer edge."""
    from_id: str
    to_id: str
    producer_guarantees: tuple[str, ...]
    consumer_requires: tuple[str, ...]
    satisfied: bool
```

#### ValidationSummary extension

```python
@dataclass(frozen=True, slots=True)
class ValidationSummary:
    is_valid: bool
    errors: tuple[ValidationEntry, ...]
    warnings: tuple[ValidationEntry, ...] = ()
    suggestions: tuple[ValidationEntry, ...] = ()
    edge_contracts: tuple[EdgeContract, ...] = ()  # NEW
```

#### Preview response

`_execute_preview_pipeline()` serializes `edge_contracts` into the response:

```json
{
  "edge_contracts": [
    {
      "from": "source",
      "to": "add_world",
      "producer_guarantees": ["text"],
      "consumer_requires": ["text"],
      "missing_fields": [],
      "satisfied": true
    }
  ]
}
```

The `edge_contracts` field appears even when all contracts are satisfied, providing positive confirmation of correct wiring.

### 3. Skill Patch for `pipeline_composer.md`

**File:** `src/elspeth/web/composer/skills/pipeline_composer.md`

Three targeted additions:

#### 3a. Completion Criteria — field contract gate

Add item 4 to the existing completion criteria list:

> 4. **All edge contracts are satisfied** — every downstream step's `required_input_fields` must be guaranteed by its upstream producer. Check `edge_contracts` in the preview response. If any edge shows `"satisfied": false`, the pipeline is not complete.

#### 3b. Text Source Safety Rule

Add to the text source gotchas in the Source Semantics Guide:

> **Schema rule for text sources:** When downstream steps reference the text column by name (via `required_input_fields` or expressions like `row['text']`), always configure the source with a `fixed` schema declaring that field:
> ```json
> {"column": "text", "schema": {"mode": "fixed", "fields": ["text: str"]}}
> ```
> Do not rely on `observed` schema when downstream steps have field requirements. The `observed` mode guarantees no fields to downstream consumers.

#### 3c. Schema Contract Fix Flow (worked example)

New subsection under Validation, replacing vague "disagreement handling" with a concrete action sequence:

> #### Fixing Schema Contract Violations
>
> When `preview_pipeline` returns an unsatisfied edge contract, follow this sequence:
>
> 1. **Read the violation** — identify which edge failed, what fields are missing, and which node is the producer.
> 2. **Patch the producer schema** — typically `patch_source_options` to change from `observed` to `fixed` with the required fields declared:
>    ```json
>    patch_source_options({
>      "patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}
>    })
>    ```
> 3. **Re-preview** — call `preview_pipeline` and verify the edge now shows `"satisfied": true`.
> 4. **Only then report success.**
>
> **Example — text source + value_transform:**
> - `preview_pipeline` returns: `edge_contracts: [{"from": "source", "to": "add_world", "satisfied": false, "consumer_requires": ["text"], "producer_guarantees": []}]`
> - Fix: `patch_source_options({"patch": {"schema": {"mode": "fixed", "fields": ["text: str"]}}})`
> - Re-preview confirms: `"satisfied": true`
>
> If `get_pipeline_state` and `preview_pipeline` disagree (e.g., state shows a field but preview shows an unsatisfied contract), treat this as unresolved. Do not report success. Re-run both tools, fix the discrepancy, and confirm before responding.

## What This Doesn't Catch

| Gap | Why | Mitigation |
|-----|-----|------------|
| Transform output fields | Composer doesn't instantiate plugins, can't know what fields a transform adds | Runtime DAG validator catches this |
| Type mismatches | Requires Pydantic schema construction | Runtime type validation catches this |
| Dynamic schemas with no declarations | If neither side declares contracts, nothing to check | S3 suggestion already flags missing schemas |
| Plugin-computed guaranteed fields | Some plugins compute guarantees at init time | Runtime validator is authoritative |

The composer's contract check is a fast, early-feedback mechanism. The runtime validator remains the final authority.

## Test Strategy

### Unit tests for `state.validate()`

**Positive cases:**
1. Source with `fixed` schema guaranteeing `text`, consumer with `required_input_fields: ["text"]` — no error.
2. Text source heuristic: `plugin: "text"`, `column: "text"`, `observed` schema, no explicit `guaranteed_fields`, consumer requiring `text` — no error (heuristic infers guarantee).
3. Text source with explicit `guaranteed_fields: ["text"]` and `column: "text"` — heuristic does not interfere, explicit value used.
4. Consumer with no `required_input_fields` — contract check skipped, no error regardless of producer schema.
5. Consumer with `required_input_fields: []` (empty list) — treated as no requirements, skipped.

**Negative cases:**
6. Source with `observed` schema (no guarantees), consumer requiring `text` — error emitted, `is_valid: false`.
7. Partial match: producer guarantees `["text"]`, consumer requires `["text", "score"]` — error for missing `score`.
8. Optional field trap: producer declares `text: str?` (optional), consumer requires `text` — error (optional fields are not guaranteed).
9. No schema config at all on source — guaranteed = empty, consumer requirements flagged.
10. Malformed schema dict (e.g., `{"mode": "invalid"}`) — error emitted, `is_valid: false`.

**Topology cases:**
11. Gate-only pipeline: source → gate → sinks. Gate route targets inherit source's guaranteed fields. Consumer on route target with requirements satisfied by source — no error.
12. Fork topology: source → fork gate → path_a, path_b. Consumer on path_a requires `text`, source guarantees `text` — no error on both paths.
13. Multi-hop: source → transform A (no requirements, no schema) → transform B (requires `text`). Transform A guarantees nothing — error for transform B.
14. Multi-sink with gate routing: source → gate → sink_a, sink_b. Contract check applies per route, not globally.

**Data integrity:**
15. `ValidationSummary.edge_contracts` contains correct `EdgeContract` entries with proper `from_id`, `to_id`, `producer_guarantees`, `consumer_requires`, `satisfied` for all edges.
16. `EdgeContract.to_dict()` serializes `from_id` as `"from"` key (Python keyword avoidance).

### Integration test for preview response

17. Build a pipeline via composer tools, call `preview_pipeline`, verify `edge_contracts` appears in response with correct fields and is consistent with `errors`.

### Regression test for the original bug

18. Build: text source (column=text, observed schema) + value_transform (required_input_fields=["text"]) + csv output. Assert `is_valid` is `false` and error mentions schema contract violation.

### Composer/runtime agreement test

19. Build a pipeline that the composer validates (both pass and fail cases). Generate YAML, instantiate plugins, build `ExecutionGraph`, call `validate_edge_compatibility()`. Assert both validators agree on pass/fail for the same pipeline configuration. This prevents the two validators from silently diverging.

### Heuristic enforcement test

20. Import `TextSource`, construct with `column: "text"` and minimal valid config, call `load()` on a one-line temp file, verify the yielded row contains key `"text"`. This ties the composer's heuristic assumption to the plugin's actual behavior — if either side changes, this test fails.
