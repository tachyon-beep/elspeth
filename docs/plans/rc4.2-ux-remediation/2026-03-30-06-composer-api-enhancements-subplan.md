# RC4.2 UX Remediation — Composer API Enhancements Subplan

Date: 2026-03-30 (expanded 2026-03-31)
Status: Ready
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## 1. Scope

This subplan groups the assistant/composer authoring API improvements that make
iterative pipeline editing cheaper and more expressive.

Included requirements:

- `REQ-API-03` — patch operations (patch_source_options, patch_node_options,
  patch_output_options)
- `REQ-API-04` — atomic full pipeline replacement (set_pipeline)

Primary surfaces:

- `CompositionState` mutation methods
- composer tool definitions and dispatch registry
- `ToolResult` serialization (unchanged — reuses existing shape)

Not included (moved to Wave 4 sub-plan 08):

- `REQ-API-05` (clear_source), `REQ-API-08` (explain validation errors),
  `REQ-API-09` (list models) — these are P3 and have no dependencies within
  Wave 3.

---

## 2. Goals

- Reduce token waste when the LLM needs to change one field in a source/node/
  sink config — patch instead of full rewrite.
- Support atomic first-pass pipeline creation in a single tool call, avoiding
  invalid intermediate states from sequential set_source + upsert_node +
  upsert_edge + set_output.
- Maintain existing validation-after-mutation contract: every mutation tool
  returns `ToolResult` with a `ValidationSummary`.

Non-goals:

- No changes to discovery tools.
- No changes to the composition budget model.
- No frontend changes — these are assistant-facing tools only.

---

## 3. Architecture Decisions

### AD-1: JSON merge-patch (RFC 7396) for all patch operations

Patch tools apply RFC 7396 semantics at the `options` dict level:

- Keys present in the patch overwrite the corresponding keys in the target.
- Keys set to `null` in the patch delete the corresponding key from the target.
- Keys absent from the patch are left unchanged.

This is a **shallow merge** on `options` only. To change a nested key inside
options, the caller must supply the full nested structure for that key. This
matches the requirement spec and is simple to implement and explain.

Implementation: `{**current_options, **patch}` with explicit `None`-key
deletion. No library dependency needed.

### AD-2: Patch tools reuse existing state mutation methods

Patch tools do NOT require new methods on `CompositionState`. The flow is:

1. Read the current spec from state (e.g. `state.source`)
2. Apply the merge-patch to `spec.options`
3. Construct a new spec with the patched options
4. Call the existing state method (`state.with_source()`, `state.with_node()`,
   `state.with_output()`)

This keeps the state dataclass simple and avoids duplicating mutation logic.

### AD-3: `set_pipeline` constructs a fresh state, not a delta

`set_pipeline` is a full replacement, not a merge. The tool receives the
complete pipeline structure (source, nodes, edges, outputs, metadata) and
constructs a new `CompositionState` from scratch using the existing spec
constructors.

It does NOT use `CompositionState.from_dict()` directly because `from_dict()`
expects the internal serialization format (with version numbers etc.). Instead,
the tool:

1. Constructs `SourceSpec`, `NodeSpec`, `EdgeSpec`, `OutputSpec`,
   `PipelineMetadata` from the tool arguments
2. Creates a new `CompositionState` with `version = current_version + 1`
3. Runs `validate()` on the result
4. Returns the standard `ToolResult`

This reuses the same validation and construction logic as the individual tools,
applied atomically.

### AD-4: `set_pipeline` validates plugin names via catalog

Each source/node/sink plugin name in the `set_pipeline` payload is validated
against the catalog, using the same logic as `set_source`, `upsert_node`, and
`set_output`. This prevents the LLM from inventing plugin names in an atomic
call that would bypass the per-tool validation.

### AD-5: `set_pipeline` counts as a single composition budget charge

Even though it replaces the entire state, `set_pipeline` is a single mutation
tool call and charges one composition turn. This is the primary benefit: the
LLM can build a full pipeline in one turn instead of N sequential mutations.

---

## 4. Detailed Changes

### Phase 6A: Patch Operations (3 new tools)

#### 6A.1: `patch_source_options` tool

**Tool definition** (add to `get_tool_definitions()` in `tools.py`):

```python
{
    "name": "patch_source_options",
    "description": "Apply a JSON merge-patch to the current source options. "
        "Keys in the patch overwrite existing keys. "
        "Keys set to null are deleted. Missing keys are unchanged.",
    "parameters": {
        "type": "object",
        "properties": {
            "patch": {
                "type": "object",
                "description": "Merge-patch to apply to source options.",
            },
        },
        "required": ["patch"],
    },
}
```

**Handler** (`_execute_patch_source_options`):

```python
def _execute_patch_source_options(
    state: CompositionState,
    args: dict[str, Any],
    catalog: CatalogServiceProtocol,
) -> ToolResult:
    if state.source is None:
        return _failure_result(state, "No source configured to patch.")
    patch = args.get("patch", {})
    new_options = _apply_merge_patch(state.source.options, patch)
    new_source = SourceSpec(
        plugin=state.source.plugin,
        options=new_options,
        on_success=state.source.on_success,
        on_validation_failure=state.source.on_validation_failure,
    )
    new_state = state.with_source(new_source)
    return ToolResult(
        success=True,
        updated_state=new_state,
        validation=new_state.validate(),
        affected_nodes=("source",),
    )
```

#### 6A.2: `patch_node_options` tool

Same pattern. Looks up node by `node_id`, applies merge-patch to `node.options`,
constructs new `NodeSpec` preserving all other fields, calls `state.with_node()`.

**Extra parameter:** `node_id: str` (required).

Fail if node not found: `"Node '{node_id}' not found."`

#### 6A.3: `patch_output_options` tool

Same pattern. Looks up output by `sink_name`, applies merge-patch to
`output.options`, constructs new `OutputSpec`, calls `state.with_output()`.

**Extra parameter:** `sink_name: str` (required).

Fail if output not found: `"Output '{sink_name}' not found."`

#### 6A.4: Shared merge-patch helper

Add a module-level helper:

```python
def _apply_merge_patch(
    target: Mapping[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """RFC 7396 JSON merge-patch at one level."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result
```

This is deliberately one-level-deep, matching AD-1.

#### 6A.5: Register in dispatch

Add all three to `_MUTATION_TOOLS` registry dict (around line 1040):

```python
_MUTATION_TOOLS: dict[str, MutationHandler] = {
    # ... existing entries ...
    "patch_source_options": _execute_patch_source_options,
    "patch_node_options": _execute_patch_node_options,
    "patch_output_options": _execute_patch_output_options,
}
```

The overlap assertions at line 1074 will catch any name collision
automatically.

---

### Phase 6B: `set_pipeline` Tool

#### 6B.1: Tool definition

```python
{
    "name": "set_pipeline",
    "description": "Atomically replace the entire pipeline. Provide the "
        "complete source, nodes, edges, outputs, and metadata in one call. "
        "This is more efficient than calling set_source + upsert_node + "
        "upsert_edge + set_output sequentially.",
    "parameters": {
        "type": "object",
        "properties": {
            "source": {
                "type": "object",
                "description": "Source configuration: {plugin, options, on_success, on_validation_failure?}",
            },
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Array of node specs: [{id, input, plugin?, node_type, options?, condition?, routes?, branches?, policy?}]",
            },
            "edges": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Array of edge specs: [{id, from_node, to_node, edge_type}]",
            },
            "outputs": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Array of output specs: [{name, plugin, options, on_write_failure?}]",
            },
            "metadata": {
                "type": "object",
                "description": "Pipeline metadata: {name?, description?}",
            },
        },
        "required": ["source", "nodes", "edges", "outputs"],
    },
}
```

#### 6B.2: Handler (`_execute_set_pipeline`)

Flow:

1. **Validate source plugin** against catalog (same check as `set_source`).
2. **Validate each node's plugin** against catalog where `plugin` is present
   (same check as `upsert_node`).
3. **Validate each output's plugin** against catalog (same check as
   `set_output`).
4. **Construct specs** from raw dicts using `SourceSpec(...)`,
   `NodeSpec(...)`, `EdgeSpec(...)`, `OutputSpec(...)`,
   `PipelineMetadata(...)`. Use the same field extraction and defaults as the
   individual tool handlers.
5. **Build new state:**
   ```python
   new_state = CompositionState(
       source=source_spec,
       nodes=tuple(node_specs),
       edges=tuple(edge_specs),
       outputs=tuple(output_specs),
       metadata=metadata_spec,
       version=state.version + 1,
   )
   ```
6. **Validate** and return `ToolResult`.

Error handling:

- If any plugin name is not in the catalog, fail with a clear message
  identifying which component has the unknown plugin.
- If spec construction raises (e.g. missing required field), catch
  `KeyError`/`TypeError` and return `_failure_result` with the field name.

#### 6B.3: Register in dispatch

Add to `_MUTATION_TOOLS`:

```python
"set_pipeline": _execute_set_pipeline,
```

#### 6B.4: Extract shared plugin validation

The catalog validation logic is currently inline in `_execute_set_source`
(line ~635), `_execute_upsert_node` (line ~665), and `_execute_set_output`
(line ~785). `set_pipeline` needs the same checks for all three plugin types.

Extract a shared helper:

```python
def _validate_plugin_name(
    catalog: CatalogServiceProtocol,
    plugin_type: str,
    name: str,
) -> str | None:
    """Return an error message if the plugin name is not in the catalog,
    or None if valid."""
    # ... lookup logic from existing handlers ...
```

Refactor the three existing handlers to use this helper, then use it in
`set_pipeline`. This is a refactor, not a behaviour change.

---

### Phase 6C: Tests

#### 6C.1: Patch tool unit tests

File: `tests/unit/web/composer/test_tools.py` (create or extend)

| Test | Setup | Expected |
|------|-------|----------|
| `test_patch_source_options_updates_key` | Source with `{path: "/a"}`, patch `{path: "/b"}` | Source options now `{path: "/b"}` |
| `test_patch_source_options_adds_key` | Source with `{path: "/a"}`, patch `{encoding: "utf-8"}` | Options now `{path: "/a", encoding: "utf-8"}` |
| `test_patch_source_options_deletes_key` | Source with `{path: "/a", encoding: "utf-8"}`, patch `{encoding: null}` | Options now `{path: "/a"}` |
| `test_patch_source_options_no_source_fails` | No source configured | `success=False`, error message |
| `test_patch_node_options_updates_key` | Node with options, patch one key | Options updated, other fields preserved |
| `test_patch_node_options_unknown_node_fails` | Nonexistent node_id | `success=False`, error message |
| `test_patch_output_options_updates_key` | Output with options, patch one key | Options updated |
| `test_patch_output_options_unknown_sink_fails` | Nonexistent sink_name | `success=False`, error message |

#### 6C.2: Merge-patch helper unit tests

| Test | Setup | Expected |
|------|-------|----------|
| `test_merge_patch_overwrites` | `{a: 1}` + `{a: 2}` | `{a: 2}` |
| `test_merge_patch_adds` | `{a: 1}` + `{b: 2}` | `{a: 1, b: 2}` |
| `test_merge_patch_deletes_null` | `{a: 1, b: 2}` + `{b: null}` | `{a: 1}` |
| `test_merge_patch_preserves_unmentioned` | `{a: 1, b: 2}` + `{a: 3}` | `{a: 3, b: 2}` |
| `test_merge_patch_empty_patch` | `{a: 1}` + `{}` | `{a: 1}` |
| `test_merge_patch_does_not_mutate_target` | MappingProxyType input | Original unchanged |

#### 6C.3: `set_pipeline` unit tests

| Test | Setup | Expected |
|------|-------|----------|
| `test_set_pipeline_creates_valid_state` | Full valid pipeline spec | `success=True`, `is_valid=True`, version incremented |
| `test_set_pipeline_unknown_source_plugin_fails` | Source with `plugin: "nonexistent"` | `success=False`, error names the source plugin |
| `test_set_pipeline_unknown_node_plugin_fails` | Node with unknown plugin | `success=False`, error names the node |
| `test_set_pipeline_unknown_sink_plugin_fails` | Output with unknown plugin | `success=False`, error names the output |
| `test_set_pipeline_missing_required_field_fails` | Source missing `on_success` | `success=False`, error indicates the field |
| `test_set_pipeline_replaces_entire_state` | Existing state with 3 nodes, set_pipeline with 1 node | New state has exactly 1 node |
| `test_set_pipeline_version_increments` | Current version N | New version is N+1 |
| `test_set_pipeline_validation_runs` | Pipeline with disconnected node | Validation errors in result |

#### 6C.4: Integration tests

File: `tests/integration/web/test_composer_tools.py` (create or extend)

| Test | Setup | Expected |
|------|-------|----------|
| `test_patch_source_via_message` | Send message that triggers `patch_source_options` | Response state reflects patched options |
| `test_set_pipeline_via_message` | Send message that triggers `set_pipeline` | Response state matches the full pipeline |

These can be difficult to trigger deterministically via the LLM. If the
composer test harness supports direct tool execution, test via that path
instead.

---

## 5. Implementation Order

```
Phase 6A (patch tools) ─────────────────────────────────┐
  6A.4  Shared merge-patch helper                        │
  6A.1  patch_source_options tool + handler              │
  6A.2  patch_node_options tool + handler                │
  6A.3  patch_output_options tool + handler              │
  6A.5  Register in dispatch                             │
                                                         │
Phase 6B (set_pipeline) ── can parallel with 6A ────────┤
  6B.4  Extract shared plugin validation helper          │
  6B.1  Tool definition                                  │
  6B.2  Handler                                          │
  6B.3  Register in dispatch                             │
                                                         │
Phase 6C (tests) ── after 6A + 6B ──────────────────────┘
  6C.1  Patch tool unit tests
  6C.2  Merge-patch helper tests
  6C.3  set_pipeline unit tests
  6C.4  Integration tests (if feasible)
```

**Parallelism:** Phases 6A and 6B are independent of each other (different
tools, different handlers). Both must complete before 6C.

**Dependencies:** Sub-plan 05 (validation enhancements) should land first so
the new tools return `warnings` and `suggestions` in their validation results
automatically. However, this is not a hard blocker — the tools will work
correctly without it, they'll just return the pre-enhancement
`ValidationSummary` shape.

**Estimated scope:** ~200 lines new tool handlers, ~50 lines shared helpers,
~200 lines tests. No database changes. No frontend changes. No new files
except test files.

---

## 6. Files Affected

### Modified

| File | Changes |
|------|---------|
| `src/elspeth/web/composer/tools.py` | 4 new tool definitions, 4 new handlers, 1 merge-patch helper, 1 plugin validation helper, registry additions |

### Possibly modified

| File | Condition |
|------|-----------|
| `src/elspeth/web/composer/state.py` | Only if `without_source()` is added here (moved to Wave 4) |

### New (tests only)

| File | Purpose |
|------|---------|
| `tests/unit/web/composer/test_tools.py` | Patch + set_pipeline unit tests |

---

## 7. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM uses patch tools incorrectly (wrong key names, wrong nesting level) | Low | Tool descriptions are explicit about shallow merge. Validation runs after every mutation — the LLM sees errors immediately. |
| `set_pipeline` with invalid plugin names produces confusing multi-error output | Low | Validate each component type separately and report the first failure with a clear component identifier. |
| Plugin validation extraction changes existing tool behaviour | Low | The refactor is mechanical — extract existing inline checks to a shared function. Existing tests cover the behaviour. |
| Merge-patch on frozen `MappingProxyType` options | None | `_apply_merge_patch` accepts `Mapping` and returns a plain `dict`. The spec constructor + `freeze_fields` handles re-freezing. |

---

## 8. Acceptance Criteria

- [ ] `patch_source_options`, `patch_node_options`, `patch_output_options`
      tools exist and appear in LLM tool definitions.
- [ ] Patch tools apply RFC 7396 merge-patch: overwrite, add, delete-on-null,
      preserve-absent.
- [ ] Patch tools fail gracefully when target doesn't exist (no source, unknown
      node, unknown output).
- [ ] `set_pipeline` tool exists and creates a complete state in one call.
- [ ] `set_pipeline` validates all plugin names against the catalog.
- [ ] `set_pipeline` increments version by 1.
- [ ] `set_pipeline` charges one composition budget turn.
- [ ] All new tools return `ToolResult` with `ValidationSummary`.
- [ ] All unit tests pass.
