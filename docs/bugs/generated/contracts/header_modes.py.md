## Summary

`header_modes.py` defines two incompatible meanings for `HeaderMode.CUSTOM`: `parse_header_mode()` accepts any dict, including `{}`, while `resolve_headers()` rejects empty or partial mappings as invalid.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/header_modes.py`
- Line(s): 29-59, 62-121
- Function/Method: `parse_header_mode`, `resolve_headers`

## Evidence

`parse_header_mode()` classifies every dict as `HeaderMode.CUSTOM` with no emptiness or completeness check:

```python
if isinstance(config, dict):
    return HeaderMode.CUSTOM
```

Source: `/home/john/elspeth/src/elspeth/contracts/header_modes.py:50-51`

But `resolve_headers()` treats the same mode as requiring a non-empty, total mapping:

```python
if mode == HeaderMode.CUSTOM and not custom_mapping:
    raise ValueError(...)
...
if name not in custom_mapping:
    raise ValueError(...)
```

Source: `/home/john/elspeth/src/elspeth/contracts/header_modes.py:91-92`, `/home/john/elspeth/src/elspeth/contracts/header_modes.py:112-118`

The rest of the codebase already relies on the looser interpretation that partial or empty mappings are allowed:

- `/home/john/elspeth/tests/unit/plugins/test_sink_header_config.py:102-113` explicitly asserts `{}` is valid and still means `CUSTOM`.
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:85-86` returns the custom mapping directly instead of routing CUSTOM through `resolve_headers()`.
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py:223-229` leaves unmapped fields unchanged.
- `/home/john/elspeth/tests/unit/plugins/sinks/test_sink_display_headers.py:64-85` verifies partial custom mappings keep unmapped fields as normalized names.

So the target file’s own helper pair disagrees about what a valid CUSTOM configuration is, and downstream code has worked around that disagreement by bypassing `resolve_headers()` for CUSTOM mode.

## Root Cause Hypothesis

`header_modes.py` appears to mix two different designs that were never reconciled:

- “CUSTOM is any override dict, possibly partial”
- “CUSTOM is a full explicit handover contract”

`parse_header_mode()` implements the first design, while `resolve_headers()` implements the second. That split forces other modules to special-case CUSTOM mode instead of relying on a single authoritative contract helper.

## Suggested Fix

Make `parse_header_mode()` and `resolve_headers()` enforce the same CUSTOM contract.

If CUSTOM is supposed to be total and explicit, the primary fix belongs here:
- Reject `{}` in `parse_header_mode()`
- Document that partial mappings are invalid
- Update downstream tests/config validation to fail early

If CUSTOM is supposed to allow partial overrides, then:
- Relax `resolve_headers()` so unmapped fields fall back to normalized names
- Remove the “all fields must be explicitly mapped” error path
- Update the module docstrings/tests to match actual sink behavior

Either way, `header_modes.py` should become the single source of truth instead of requiring `display_headers.py` to bypass it.

## Impact

This is an integration-contract bug: code can accept a sink config as valid CUSTOM mode and later hit a runtime `ValueError` if any caller uses the target file’s central resolver for the same config. It also makes header handling non-uniform across sinks and validation paths, which is risky for external handoff behavior because the meaning of `headers: {...}` depends on which helper a caller happened to use.
