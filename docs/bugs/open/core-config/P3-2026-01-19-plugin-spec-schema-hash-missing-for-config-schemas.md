# Bug Report: PluginSpec computes schema hashes from plugin classes, but built-in schemas are instance/config-driven (hashes become `None`)

## Summary

- `PluginSpec.from_plugin(...)` accepts a *plugin class* and computes `input_schema_hash`/`output_schema_hash` via `getattr(plugin_cls, "input_schema", None)` / `getattr(plugin_cls, "output_schema", None)`.
- Built-in plugins (sources/transforms/sinks) set `input_schema`/`output_schema` on the *instance* during `__init__` based on config (`create_schema_from_config(...)`), so the class typically has no schema attributes.
- If/when PluginSpec is used for audit metadata, schema hashes will be `None` (or incomplete), defeating compatibility/change detection.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: codex
- Date: 2026-01-19
- Related run/issue ID: N/A (static analysis)

## Environment

- Commit/branch: `main` @ `8cfebea78be241825dd7487fed3773d89f2d7079`
- OS: Linux (Ubuntu kernel 6.8.0-90-generic)
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: deep dive into subsystem 6 (plugins), identify bugs, create tickets
- Model/version: GPT-5.2 (Codex CLI)
- Tooling and permissions (sandbox/approvals): workspace-write, network restricted, approvals on-request
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code inspection (no runtime execution)

## Steps To Reproduce

1. Instantiate a built-in transform (e.g., `FieldMapper`) with a config-driven schema.
2. Observe that `transform.input_schema` exists on the instance, but `FieldMapper.input_schema` is typically not a concrete class attribute.
3. Call `PluginSpec.from_plugin(FieldMapper, node_type=...)` and observe schema hashes are `None` (because `getattr` returns `None`).

## Expected Behavior

- Schema hashes should reflect the actual schemas used by a plugin instance in a specific run/configuration.

## Actual Behavior

- Schema hashes are computed from class-level attributes and can be missing for config-driven schemas.

## Evidence

- PluginSpec reads schemas from the plugin class via `getattr(...)`: `src/elspeth/plugins/manager.py:77-107`
- Built-in plugins set schema attributes per instance during `__init__`:
  - `CSVSource`: `self.output_schema = self._schema_class`: `src/elspeth/plugins/sources/csv_source.py:71-82`
  - `FieldMapper`: `self.input_schema = schema; self.output_schema = schema`: `src/elspeth/plugins/transforms/field_mapper.py:64-73`
  - `CSVSink`: `self.input_schema = self._schema_class`: `src/elspeth/plugins/sinks/csv_sink.py:69-82`

## Impact

- User-facing impact: low today (PluginManager appears unused), but schema hashes are critical for future audit/compatibility features.
- Data integrity / security impact: missing schema hashes reduce ability to verify compatibility changes and reproduce runs.
- Performance or cost impact: potential future debugging/repro cost.

## Root Cause Hypothesis

- PluginSpec was designed around static class-level schemas, but the system has moved to config-driven schema generation at instance construction time.

## Proposed Fix

- Code changes (modules/files):
  - Change `PluginSpec.from_plugin` to accept a plugin *instance* (or accept schemas directly) so it can hash the real schema classes.
  - Alternatively, compute schema hashes from `schema_config` deterministically (and store `schema_config` hash) rather than introspecting Pydantic models.
- Config or schema changes: none.
- Tests to add/update:
  - Add a unit test that `PluginSpec` schema hashes are non-None when using config-driven schemas.
- Risks or migration steps:
  - Changing API signature is breaking; consider adding a new method `from_instance(...)` and deprecating `from_plugin(...)`.

## Architectural Deviations

- Spec or doc reference: `docs/arch-analysis-2026-01-20-0105/02-subsystem-catalog.md` (PluginSpec intended for Landscape node metadata)
- Observed divergence: schema hashing path doesn’t align with config-driven schemas.
- Reason (if known): refactor from static schemas to config-driven generation.
- Alignment plan or decision needed: decide canonical representation for schema identity (Pydantic introspection vs schema_config hash).

## Acceptance Criteria

- Schema hashes (or a replacement) exist and are stable/deterministic for config-driven plugin instances.

## Tests

- Suggested tests to run: `pytest tests/`
- New tests required: yes

## Notes / Links

- Related ticket: `docs/bugs/open/2026-01-19-plugin-registries-drift-and-unused-plugin-manager.md`

---

## VERIFICATION: 2026-01-25

**Status:** STILL VALID

**Verified By:** Claude Code P3 verification wave 2

**Current Code Analysis:**

The bug is **100% reproducible** and remains unresolved. Testing confirms:

```python
# FieldMapper (Transform)
getattr(FieldMapper, "input_schema", None)  # → None
getattr(FieldMapper, "output_schema", None)  # → None
PluginSpec.from_plugin(FieldMapper, NodeType.TRANSFORM)
  # → input_schema_hash: None, output_schema_hash: None

# CSVSource (Source)
getattr(CSVSource, "output_schema", None)  # → None
PluginSpec.from_plugin(CSVSource, NodeType.SOURCE)
  # → output_schema_hash: None
```

**Code inspection confirms the architectural mismatch:**

1. **PluginSpec.from_plugin() (manager.py:76-103)** uses `getattr(plugin_cls, "input_schema", None)` and `getattr(plugin_cls, "output_schema", None)` to extract schemas from the **class**.

2. **All built-in plugins** set schemas as **instance attributes** during `__init__`:
   - `CSVSource.__init__` (csv_source.py:71-78): `self.output_schema = self._schema_class`
   - `FieldMapper.__init__` (field_mapper.py:67-78): `self.input_schema = ...` and `self.output_schema = ...`
   - `CSVSink.__init__` (csv_sink.py:82-89): `self.input_schema = self._schema_class`

3. **Schema generation is config-driven**: All plugins call `create_schema_from_config()` with the `schema_config` from their configuration, meaning schemas are dynamically created per-instance, not statically defined on the class.

**Git History:**

No commits have addressed this issue since the bug was reported on 2026-01-19. Recent schema-related work focused on:
- Schema validation at construction time (commits 0a339fd, 0e2f6da, 7ee7c51)
- Schema validation protocol changes (commits 430307d, df43269)
- Node ID determinism for checkpoints (commit 04d5605)

None of these touched `PluginSpec` or the schema hashing mechanism.

**Usage Analysis:**

`PluginSpec` is currently **NOT used in production code**:
- Exported in `src/elspeth/plugins/__init__.py` (line 58, 113)
- Only referenced in tests: `test_manager.py`, `test_manager_validation.py`
- **Not imported by engine, landscape, or any runtime code**

The existing tests use **mock plugins with class-level schemas** (test_manager.py:217-227), which do not exercise the config-driven schema path and therefore pass despite the bug.

**Root Cause Confirmed:**

Yes, 100% confirmed. The bug report's hypothesis is accurate:

> "PluginSpec was designed around static class-level schemas, but the system has moved to config-driven schema generation at instance construction time."

This is a **design-level incompatibility** between `PluginSpec`'s API (class-based) and the plugin system's implementation (instance-based config-driven schemas).

**Recommendation:**

**Keep open** with the following qualifications:

1. **Impact is currently zero** since `PluginSpec` is unused in production code. The bug manifests only if/when the engine or landscape start using `PluginSpec.from_plugin()` for audit metadata.

2. **The bug report's proposed fixes are sound:**
   - Option A: Add `PluginSpec.from_instance(plugin_instance)` method that reads `instance.input_schema` and `instance.output_schema`
   - Option B: Hash the `schema_config` dict instead of the generated Pydantic class (more stable for audit trail)

3. **Priority remains P3** - this is a latent bug that will become critical if the planned "Phase 3 Landscape node metadata" feature (mentioned in the architectural docs) starts using `PluginSpec`.

4. **Test coverage gap:** The existing `test_manager.py::TestPluginSpecSchemaHashes` tests use mock plugins with class-level schemas and thus don't catch this bug. A test using an actual config-driven plugin (e.g., `CSVSource`, `FieldMapper`) would immediately fail and document the issue.

**Suggested next steps (when prioritized):**
- Add failing test case using real config-driven plugin
- Implement `PluginSpec.from_instance()` or switch to hashing `schema_config`
- Update engine/landscape to use the new API if schema hashing is needed
