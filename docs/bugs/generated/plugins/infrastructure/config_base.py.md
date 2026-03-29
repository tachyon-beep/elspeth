## Summary

`validate_headers_value()` accepts `headers: {}` as valid custom-header config, even though the downstream header contract requires a non-empty custom mapping; the result is either a late runtime failure or a silent fallback to normalized headers instead of the user-requested custom output.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py
- Line(s): 198-215
- Function/Method: `validate_headers_value`

## Evidence

[`config_base.py` lines 203-215](/home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L203) treat any `dict` as valid `headers` config and only check for duplicate target values:

```python
if isinstance(v, dict):
    targets = list(v.values())
    duplicates = [t for t in targets if targets.count(t) > 1]
    if duplicates:
        raise ValueError(...)
    return v
```

That means `headers: {}` is accepted.

But the canonical header resolver rejects empty custom mappings outright. [`header_modes.py` lines 90-92](/home/john/elspeth/src/elspeth/contracts/header_modes.py#L90) state:

```python
if mode == HeaderMode.CUSTOM and not custom_mapping:
    raise ValueError("CUSTOM header mode requires a non-empty custom_mapping...")
```

The sink display-header path can also silently degrade instead of failing. [`display_headers.py` lines 85-86](/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L85) return the empty dict directly for `CUSTOM` mode, and [`display_headers.py` lines 219-236](/home/john/elspeth/src/elspeth/plugins/infrastructure/display_headers.py#L219) then leave every field name unchanged because unmapped fields fall back to the original key. So `headers: {}` behaves like normalized output, not custom output.

The repository’s own tests show the contract mismatch:
- [`test_header_modes.py` lines 173-180](/home/john/elspeth/tests/unit/contracts/test_header_modes.py#L173) expect empty custom mappings to raise.
- [`test_sink_header_config.py` lines 102-113](/home/john/elspeth/tests/unit/plugins/test_sink_header_config.py#L102) currently assert that `headers: {}` is valid and produces `HeaderMode.CUSTOM`.

What the code does: accepts an impossible/meaningless CUSTOM config.
What it should do: reject empty custom mappings during config validation in `config_base.py`, before sinks are instantiated.

## Root Cause Hypothesis

`validate_headers_value()` validates only duplicate targets, but it does not enforce the full contract for `HeaderMode.CUSTOM`. The file was updated to support unified `headers` parsing, but the validator was left looser than the downstream resolver and sink behavior, creating an internal config contract split.

## Suggested Fix

Reject empty dicts in `validate_headers_value()`:

```python
if isinstance(v, dict):
    if not v:
        raise ValueError("headers custom mapping must not be empty")
    ...
```

Then update the sink-header config test to expect rejection, aligning it with the resolver contract in `header_modes.py`.

## Impact

Sinks can accept a config that does not represent a valid custom-header policy. In practice this can:
- write normalized column names when the operator explicitly requested custom output names,
- fail later during header resolution instead of at config-validation time,
- produce incorrect external handoff files, which is especially risky because the project explicitly treats silent header fallback as potential data corruption.
