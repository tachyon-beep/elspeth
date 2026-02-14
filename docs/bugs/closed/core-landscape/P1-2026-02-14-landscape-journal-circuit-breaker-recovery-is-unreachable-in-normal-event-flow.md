## Summary

`LandscapeJournal`'s circuit-breaker recovery is unreachable in normal event flow, so once the journal is disabled after repeated write failures, it can remain disabled indefinitely and stop producing backup records.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/journal.py`
- Line(s): 96-97, 119-120, 141-153, 176-183
- Function/Method: `_after_cursor_execute`, `_after_commit`, `_append_records`

## Evidence

`_append_records()` contains the intended disabled-mode recovery logic:

```python
# journal.py
if self._disabled:
    self._total_dropped += len(records)
    if self._total_dropped % 100 == 0:
        ...  # attempt recovery
        self._disabled = False
    else:
        return
```

But event handlers short-circuit before `_append_records()` can run when disabled:

```python
# journal.py
def _after_cursor_execute(...):
    if self._disabled:
        return

def _after_commit(...):
    if self._disabled:
        return
```

So after `_append_records()` sets `self._disabled = True` at failure threshold (lines 176-183), subsequent writes do not buffer and commits do not call `_append_records()`. Recovery path is effectively dead in production flow.

Additional corroboration: unit test `tests/unit/core/landscape/test_journal.py:422-434` validates recovery by calling `_append_records()` directly, which bypasses the real event path and masks this integration defect.

This behavior also conflicts with documented expectations that journal includes database commits (`docs/reference/configuration.md:579`).

## Root Cause Hypothesis

Circuit-breaker state management is split across methods, but disabled checks in event hooks prevent the recovery state machine in `_append_records()` from receiving any further traffic. The intended "retry every 100 dropped records" logic exists but is not reachable from actual SQLAlchemy hook execution once disabled.

## Suggested Fix

Make `_append_records()` the single gatekeeper for disabled behavior:

- Remove/relax `if self._disabled: return` in `_after_cursor_execute` and `_after_commit`.
- Continue buffering write records and always route commit buffers into `_append_records()`, which can drop, count, and periodically retry as designed.
- Ensure commit path clears per-connection buffer even while disabled to avoid stale buffered data.
- Add an integration-style test through hooks (not direct private call) that:
  1. forces 5 write failures,
  2. verifies disabled state,
  3. restores writable path,
  4. verifies automatic recovery and resumed journaling.

## Impact

- Emergency JSONL backup stream can silently stop after transient filesystem issues.
- Subsequent commits (including call records and optional payload inlining) are absent from journal indefinitely.
- Operational/audit fallback guarantees are weakened: investigation relying on journal may miss large spans of activity despite DB commits succeeding.
