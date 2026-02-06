# Analysis: src/elspeth/tui/widgets/node_detail.py

**Lines:** 234
**Role:** Detail panel widget showing information about a selected node in the lineage tree. Renders node identity, status/timing, data hashes, error details (with discriminated error type detection), and artifact information. Includes validation functions for error and artifact display types.
**Key dependencies:** Imports `json`, `structlog`, `elspeth.tui.types` (ArtifactDisplay, ExecutionErrorDisplay, NodeStateInfo, TransformErrorDisplay). Imported by `elspeth.tui.screens.explain_screen` and `elspeth.tui.widgets.__init__`.
**Analysis depth:** FULL

## Summary

This is the most audit-critical file in the TUI layer. The error discrimination logic (ExecutionError vs TransformErrorReason) is correctly implemented with proper Tier 1 crash-on-corruption semantics. The validation functions are well-structured. The main concern is that the `json.loads` call on `error_json` trusts the string came from our audit database but does not handle all edge cases of JSON parsing. Overall this is the strongest file in the TUI module.

## Warnings

### [146-154] error_json string content is not size-bounded before json.loads

**What:** The `error_json` field from `NodeStateInfo` is passed directly to `json.loads()` without any size check. While this data comes from the Landscape audit database (Tier 1 -- our data), the `error_json` field stores serialized error information that could be arbitrarily large if a transform recorded a very long exception traceback or error message.

**Why it matters:** For a TUI display, parsing a multi-megabyte JSON string would cause the UI to freeze. The `json.loads` call itself is O(n) in the size of the string. In normal operation, error JSON is small (a few KB at most), so this is a theoretical concern rather than a practical one. However, if the audit database is shared or modified externally, a maliciously large `error_json` value could denial-of-service the TUI.

**Evidence:**
```python
error_json = self._state.get("error_json")
if error_json:
    # No size check
    error = json.loads(error_json)  # Could be arbitrarily large
```

### [163-186] Error variant discrimination relies on key presence, not explicit discriminator

**What:** The error JSON is discriminated by checking for key combinations: `"type" in error and "exception" in error` for `ExecutionError`, `"reason" in error` for `TransformErrorReason`. If a future error type has both `"type"` and `"reason"` fields, the `ExecutionError` branch would match first, potentially misclassifying it.

**Why it matters:** The discrimination order matters. The current approach works because the two error types (`ExecutionError` and `TransformErrorReason`) have non-overlapping required key sets. However, this is a fragile implicit contract. If a third error type is added to `elspeth.contracts.errors`, this discrimination logic must be updated manually. There is no compile-time or test-time check that would catch a new error variant being silently misclassified.

**Evidence:**
```python
if "type" in error and "exception" in error:
    # ExecutionError variant
    ...
elif "reason" in error:
    # TransformErrorReason variant
    ...
else:
    raise ValueError(...)  # Unknown format - correctly crashes
```

The `else` branch correctly crashes on unknown formats, which provides a safety net. But if a new variant matches one of the existing conditions, it would be silently misclassified rather than caught.

### [180-186] Unknown error format crash includes raw error keys in exception message

**What:** When an unknown error format is detected, the `ValueError` message includes `list(error.keys())`. If the error JSON contains sensitive field names or values (unlikely but possible in error contexts), these would appear in the exception traceback.

**Why it matters:** This is a very minor concern. Error keys are metadata (field names), not values, so sensitive data leakage is minimal. The crash is correct behavior per Tier 1 semantics. However, in a TUI context, this exception may be caught by Textual's error handler and displayed to the user.

## Observations

### [18-68] Validation functions correctly implement Tier 1 crash semantics

**What:** `_validate_execution_error`, `_validate_transform_error`, and `_validate_artifact` all use direct dictionary access (`data["exception"]`, `data["reason"]`, etc.) for required fields. Missing required fields will raise `KeyError`, which is correct per the Tier 1 trust model -- this is our audit data and corruption should crash immediately.

The functions also correctly handle `NotRequired` fields using `"field" in data` checks rather than `.get()` with defaults. This is the correct pattern: check for presence, then access directly.

### [96-103] render_content handles None state cleanly

**What:** When `self._state is None`, the method immediately returns a helpful message: "No node selected. Select a node from the tree to view details." This is a clean null-state rendering.

### [107-117] Required vs optional field access is clearly separated

**What:** Required fields (`plugin_name`, `node_type`, `node_id`) use direct access (`self._state["plugin_name"]`). Optional fields (`state_id`, `token_id`, `status`, etc.) use `.get()` with display fallbacks (`or 'N/A'`). This separation is clearly commented and follows the documented contract.

The `.get()` usage here is legitimate per the CLAUDE.md prohibition rules -- `NodeStateInfo` has `total=False`, so these fields genuinely may not be present. The `.get()` is not hiding a bug; it's handling the documented optional nature of post-execution fields.

### [210-226] _format_size is a clean utility function

**What:** The byte-size formatting function uses standard binary prefixes (1024-based) and produces clean output. The progression B -> KB -> MB -> GB covers all practical sizes. There is no TB branch, but artifact sizes in the TB range are unrealistic for this use case.

### [228-234] update_state is a simple state replacement

**What:** The `update_state` method replaces `self._state` with the new value. This is intentionally simple -- there is no re-rendering triggered because the TUI currently uses static text rendering. When the TUI moves to interactive Textual widgets, this method would need to trigger a re-render.

### [149-158] TypeError checks on error_json and artifact enforce Tier 1 integrity

**What:** Before parsing `error_json`, the code verifies it's a string with `isinstance(error_json, str)`. After parsing, it verifies the result is a dict with `isinstance(error, dict)`. These checks raise `TypeError` with detailed audit integrity violation messages including the `state_id`. Similarly, `artifact` is verified to be a dict before validation. This is correct Tier 1 enforcement -- our data must be pristine.

## Verdict

**Status:** SOUND
**Recommended action:** (1) Consider adding an explicit discriminator field to error JSON in the contracts layer rather than relying on key-presence heuristics. (2) Minor: the error format discrimination order should be documented with a comment explaining why `ExecutionError` is checked first. No urgent changes needed.
**Confidence:** HIGH -- the error handling and validation logic is well-structured, follows the project's trust model correctly, and the edge cases are properly handled with crash semantics.
