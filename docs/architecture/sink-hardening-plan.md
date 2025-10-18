# Sink Hardening & Observability Plan

Objective: Enforce write-path allowlists and symlink containment across local sinks (CSV, Excel, local_bundle, zip_bundle), and extend observability with structured PluginLogger events.

## Principles
- Deny-by-default outside an allowed base directory.
- Validate all path components; do not follow symlinks.
- Prefer atomic writes (temp + `os.replace`).
- Use `O_NOFOLLOW` when available (POSIX); fallback to `lstat()` checks.
- Consistent JSONL logging across sinks.

## Scope
- CSV: `src/elspeth/plugins/nodes/sinks/csv_file.py`
- Excel: `src/elspeth/plugins/nodes/sinks/excel.py`
- Local bundle: `src/elspeth/plugins/nodes/sinks/local_bundle.py`
- Zip bundle: `src/elspeth/plugins/nodes/sinks/zip_bundle.py`
- Helpers: `src/elspeth/core/utils/path_guard.py`
- Tests: new focused tests under `tests/`

## Path Containment
Add optional `allowed_base_path` to sinks (default `outputs/`).
Shared helpers in `path_guard.py`:
- `resolve_under_base(target, base)`: resolve path under base or raise.
- `ensure_no_symlinks_in_ancestors(path)`: reject symlinked ancestors.
- `ensure_destination_is_not_symlink(path)`: reject symlink target.
- `check_and_prepare_dir(path)`: prepare directories after checks.
- `safe_atomic_write(path, writer)`: write to temp in same dir, fsync, `os.replace`.

Apply per sink:
- CSV/Excel: guard target path, atomic write, reject symlinks.
- Local bundle: guard base dir and all produced files; atomic writes.
- Zip bundle: guard archive path, atomic creation; validate member names.

## Observability
Emit PluginLogger events:
- `sink_write_attempt`, `sink_write`, `sink_finalize`, and `error` with `metrics` and `metadata` (path, rows, bytes, experiment, sanitization flags).

## Tests
- `tests/test_path_guard.py`: under-base, traversal rejection, symlink ancestor rejection, atomicity.
- `tests/test_csv_sink_path_guard.py`: allowed/blocked paths, symlink destination and parent.
- Similar tests for Excel/local_bundle/zip_bundle in later slices.

## Milestones (estimates)
1. Helpers + tests (S–M, 2–3d)
2. CSV hardening + tests (S, 1–2d)
3. Excel hardening + tests (M, 2–3d)
4. Local bundle hardening + tests (M, 3–4d)
5. Zip bundle hardening + tests (M, 3–4d)
6. Security tests unskip + additions (S, 1d)
7. Docs & CI updates (S, 1d)

## Acceptance Criteria
- Sinks only write under `allowed_base_path`.
- No symlinked ancestors or targets; atomic writes.
- PluginLogger events present for attempt/success/finalize/error.
- Tests validate happy and adversarial cases; security symlink test no longer skipped.

