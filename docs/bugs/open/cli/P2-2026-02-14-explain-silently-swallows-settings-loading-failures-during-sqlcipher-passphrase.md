## Summary

`explain` silently swallows settings-loading failures during SQLCipher passphrase resolution, causing misleading DB errors and hiding config problems.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/cli.py`
- Line(s): 660-667, 669-688
- Function/Method: `explain`

## Evidence

`explain` does catch-all suppression:

```python
if landscape_settings is None and settings_path is not None and settings_path.exists():
    try:
        settings_for_passphrase = load_settings(settings_path)
        landscape_settings = settings_for_passphrase.landscape
    except Exception:
        pass  # No settings available — passphrase will be None
```

Then it proceeds with passphrase resolution/open:

- `resolve_audit_passphrase(None)` intentionally returns `None` (`src/elspeth/cli_helpers.py:207-211`).
- DB open then fails with generic connection error (`src/elspeth/cli.py:682-688`), masking original settings/config failure.

Also, the dedicated helper for secret-aware loading exists (`_load_settings_with_secrets`, `src/elspeth/cli.py:309-356`) but isn’t used here.

## Root Cause Hypothesis

A broad `except Exception: pass` was used to make `--settings` optional for explain, but it suppresses actionable failures at the encryption/config boundary.

## Suggested Fix

Replace catch-all suppression with explicit handling:

1. If `--settings` was provided and loading fails, return a clear config error.
2. Use `_load_settings_with_secrets(...)` for this path so Key Vault-backed passphrase env injection behaves consistently with other commands.

## Impact

- Hidden configuration errors.
- Misleading “database connection failed” output when the real fault is settings/secret resolution.
- Friction and false diagnosis for encrypted audit DB explain workflows.

## Triage

- Status: open
- Source report: `docs/bugs/generated/cli.py.md`
- Finding index in source report: 3
- Beads: pending
