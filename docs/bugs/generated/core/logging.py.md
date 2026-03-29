## Summary

`configure_logging()` unconditionally replaces `root.handlers`, which drops any pre-existing handlers such as pytest `caplog` capture handlers and other integrations that were already attached to the root logger.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/core/logging.py`
- Line(s): 130-133
- Function/Method: `configure_logging`

## Evidence

`configure_logging()` clears the root logger by assignment and installs only its own `StreamHandler`:

```python
root = logging.getLogger()
root.handlers = []
root.addHandler(handler)
root.setLevel(log_level)
```

Evidence that this is not just theoretical:

- `/home/john/elspeth/src/elspeth/core/logging.py:130-133` removes all existing handlers.
- Direct reproduction in this repo showed the loss of an existing pytest capture handler:
  - Before `configure_logging()`: `['LogCaptureHandler']`
  - After `configure_logging()`: `['StreamHandler']`
  - `cap_present False`
- Multiple tests already contain workarounds that accept either stdout or `caplog`, which is consistent with handler eviction breaking standard log capture:
  - `/home/john/elspeth/tests/unit/engine/orchestrator/test_graceful_shutdown.py:217-220`
  - `/home/john/elspeth/tests/unit/plugins/llm/test_provider_protocol.py:131-135`
- By contrast, tests that rely purely on `caplog` and do not call `configure_logging()` still expect normal capture behavior:
  - `/home/john/elspeth/tests/unit/plugins/llm/test_llm_config.py:434-466`

What the code does:
- Deletes every handler already attached to the root logger.

What it should do:
- Install ELSPETH formatting without silently breaking existing handler-based integrations, or at minimum replace only ELSPETH-owned handlers.

## Root Cause Hypothesis

The module treats logging configuration as exclusive ownership of the root logger. That works for the CLI happy path, but it violates integration expectations in shared runtimes and tests where another system has already attached handlers. The implementation has no notion of “our handler” vs. “someone else’s handler”, so reconfiguration becomes destructive.

## Suggested Fix

Stop blanket-replacing `root.handlers`. Instead:

- Remove only ELSPETH-owned handlers.
- Preserve unrelated handlers already attached to root.
- Optionally mark the installed handler with a private attribute so it can be replaced safely on reconfiguration.

Example shape:

```python
handler = logging.StreamHandler(sys.stdout)
handler._elspeth_handler = True  # type: ignore[attr-defined]

root = logging.getLogger()
root.handlers = [h for h in root.handlers if not getattr(h, "_elspeth_handler", False)]
root.addHandler(handler)
root.setLevel(log_level)
```

If exclusive-root ownership is truly required, this function should at least fail loudly or document that constraint, but preserving non-ELSPETH handlers is the safer fix.

## Impact

This breaks observability integrations that depend on existing root handlers:

- pytest `caplog` can stop seeing records after logging is configured.
- Any pre-attached log shipping, capture, or diagnostics handler is silently detached.
- Tests become flaky and have to check stdout as a fallback instead of relying on normal logging capture.
- Operational visibility is reduced because logs still appear on stdout, but secondary consumers stop receiving them.
