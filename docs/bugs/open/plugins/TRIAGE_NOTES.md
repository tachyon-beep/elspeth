# Plugins Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | Non-finite values bypass source boundary validation for explicit schemas | schema_factory.py | P1 | P1 | Confirmed |
| 2 | PluginManager.register leaves pluggy polluted on duplicate name | manager.py | P1 | P2 | Downgraded |
| 3 | SinkPathConfig header mapping collision causes silent field overwrite | config_base.py | P1 | P1 | Confirmed |
| 4 | MISSING sentinel is not enforced as singleton | sentinels.py | P2 | P3 | Downgraded |

**Result:** 2 confirmed (both P1), 2 downgraded.

## Detailed Assessments

### Bug 1: Non-finite values bypass source boundary validation for explicit schemas (P1 confirmed)

Genuine P1. The code path is clear: `_create_explicit_schema` (line 170) uses `PluginSchema` as its base, which has no non-finite validator. `_create_dynamic_schema` (line 128) uses `_ObservedPluginSchema` which does. The TYPE_MAP maps `"any"` to `Any` (line 38), so an explicit schema with `any`-typed fields will accept `inf`/`nan` values. The `FiniteFloat` annotation at line 29 only applies to `float`-typed fields, not `any`.

The downstream crash is confirmed: `canonical.py:59-63` raises `ValueError` on non-finite float, and this is called during non-quarantined row hashing at `_token_recording.py:95`. The JSON overflow path (`json.loads('{"value": 1e309}')` producing `inf`) is a real Tier 3 input scenario that bypasses `parse_constant` because it is a valid JSON number that overflows to infinity, not a literal `NaN`/`Infinity` token.

This violates the Three-Tier Trust Model: external data passes source validation but crashes during audit hashing instead of being quarantined at the boundary.

### Bug 2: PluginManager.register leaves pluggy polluted on duplicate name (P1 -> P2)

The bug is real: `_refresh_caches()` at line 86 is called after `self._pm.register(plugin)` at line 79, and its `ValueError` at lines 104/111/118 is not caught by the `except pluggy.PluginValidationError` handler at line 82. The failed plugin remains registered in `self._pm`.

However, this is downgraded to P2 because:
1. **Single call site at startup:** `register_builtin_plugins()` (lines 52-71) is the production registration path. It calls `register()` three times with pre-discovered plugins. Duplicate detection between these sets is effectively impossible because source, transform, and sink discovery scan separate base classes.
2. **Re-registration of same plugin set not possible:** Each `create_dynamic_hookimpl` call packages all discovered plugins of a type into a single hookimpl. You would need two separate discovery rounds returning overlapping plugin names to trigger this.
3. **No hot-reload path:** There is no runtime re-registration or dynamic plugin loading. Registration happens once at startup.

The fix is still correct (wrap `_refresh_caches()` in the same unregister/re-raise pattern), and this would be important if plugin hot-reload were ever added.

### Bug 3: SinkPathConfig header mapping collision causes silent field overwrite (P1 confirmed)

Genuine P1. The validation gap is clear: `_validate_headers` at lines 226-244 checks that `headers` is a dict, string, or None, but never validates uniqueness of mapping values. A config like `headers: {"a": "X", "b": "X"}` passes validation, and the downstream dict comprehension at `json_sink.py:549` (`{display_map.get(k, k): v for k, v in row.items()}`) silently overwrites field `a` with field `b` (dict key collision).

This is a config-time validation gap that causes silent data loss at runtime. The fix belongs in `SinkPathConfig` (reject duplicate mapping values) and is independent of the related `plugins-sinks/P1-header-display-mapping-collisions` bug, which concerns the runtime dict comprehension itself in `json_sink.py`.

**Cross-reference:** Related to `plugins-sinks/P1-header-display-mapping-collisions` but different root causes. This bug is about config validation (accepting invalid mappings). The other is about runtime collision in the dict comprehension when ORIGINAL mode reverse-maps to colliding originals. Both should remain open -- fixing this one prevents CUSTOM mode collisions but not ORIGINAL mode collisions.

### Bug 4: MISSING sentinel is not enforced as singleton (P2 -> P3)

The bug is technically real: `MissingSentinel` at line 31-42 has no singleton enforcement. `copy.deepcopy()`, `pickle.loads()`, and direct `MissingSentinel()` all create new instances that fail `is MISSING` checks.

Downgraded to P3 because:
1. **No production code path copies or pickles MISSING:** The sentinel is used in two places -- `utils.py:get_nested_field` (returns it as a default) and `field_mapper.py:119-121` (checks `is MISSING`). Neither path involves deepcopy, pickle, or serialization of the sentinel value itself.
2. **`deepcopy` in field_mapper operates on row data:** The `copy.deepcopy(row_data)` at `field_mapper.py:109` operates on `row.to_dict()` output, which never contains `MISSING` (it is a local sentinel for "field not found", never stored in rows).
3. **Direct construction would require a code bug in ELSPETH:** Since `MISSING` is only used internally as a "not found" marker, and we own all the code, a second `MissingSentinel()` call would require a bug in our system code -- which per CLAUDE.md should crash, not be defensively handled.

This is a defense-in-depth hardening that would prevent hypothetical future misuse but has zero current production risk.

## Cross-Cutting Observations

### 1. Non-finite validation gap affects the schema factory boundary

Bug 1 reveals that the non-finite validator was only applied to observed schemas, likely because observed schemas were seen as the highest-risk path (accepting any field). But explicit schemas with `any`-typed fields have the same gap. The fix should apply the non-finite validator to all schema modes used at the source boundary (when `allow_coercion=True`), creating a single enforcement point regardless of schema mode.

### 2. Config validation depth for sink header mappings

Bug 3 shows that structural type validation alone is insufficient for sink header configs. Semantic validation (value uniqueness, collision with unmapped fields) is needed at the config layer to prevent runtime data loss. This pattern may apply to other config-level mappings in the codebase.
