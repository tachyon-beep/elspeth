## Summary

`resolve_database_url()` rejects valid `~`-prefixed `settings_path` values because it checks `Path.exists()` before expanding the user home path.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/cli_helpers.py`
- Line(s): 121-126
- Function/Method: `resolve_database_url`

## Evidence

`resolve_database_url()` normalizes `database` with `expanduser().resolve()` but does not do the same for `settings_path`:

```python
if settings_path is not None:
    if not settings_path.exists():
        raise ValueError(f"Settings file not found: {settings_path}")
    config = load_settings(settings_path)
```

In contrast, other CLI paths intentionally expand `~` first (e.g. `run` and `validate`):
- `src/elspeth/cli.py:399`
- `src/elspeth/cli.py:1025`

Repro from this workspace:

- `Path('~/elspeth-rapid/CLAUDE.md').exists()` → `False`
- `Path('~/elspeth-rapid/CLAUDE.md').expanduser().exists()` → `True`
- Calling `resolve_database_url(database=None, settings_path=Path('~/elspeth-rapid/examples/threshold_gate/settings.yaml'))` raises:
  - `ValueError: Settings file not found: ~/elspeth-rapid/examples/threshold_gate/settings.yaml`

So the helper reports a false missing-file error for a real file when `~` is used.

## Root Cause Hypothesis

Path normalization was applied for `database` but omitted for `settings_path`, creating inconsistent path semantics across CLI helper entry points.

## Suggested Fix

Normalize `settings_path` before existence checks and load:

```python
if settings_path is not None:
    normalized_settings = settings_path.expanduser().resolve()
    if not normalized_settings.exists():
        raise ValueError(f"Settings file not found: {normalized_settings}")
    config = load_settings(normalized_settings)
    return config.landscape.url, config
```

Also add a regression test in `tests/unit/cli/test_cli_helpers_db.py` for `~` expansion on `settings_path`.

## Impact

Users (or internal callers/tests) passing `~` for settings get a false “file not found” failure. This can block settings-based DB URL resolution and any downstream behavior that depends on loading `landscape` settings from that path.

## Triage

- Status: open
- Source report: `docs/bugs/generated/cli_helpers.py.md`
- Finding index in source report: 1
- Beads: pending
