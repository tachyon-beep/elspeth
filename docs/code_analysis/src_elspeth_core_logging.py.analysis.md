# Analysis: src/elspeth/core/logging.py

**Lines:** 154
**Role:** Structured logging configuration using structlog. Configures both structlog and stdlib logging to emit consistent output (JSON or human-readable console format). Routes stdlib log records through structlog's processor chain via ProcessorFormatter.
**Key dependencies:** `structlog`, `structlog.stdlib.ProcessorFormatter`, stdlib `logging`. Imported by `src/elspeth/cli.py`, `src/elspeth/core/__init__.py`. Used indirectly by every module that calls `logging.getLogger(__name__)`.
**Analysis depth:** FULL

## Summary

The logging configuration is well-structured and handles the dual structlog/stdlib integration correctly. The `_remove_internal_fields` processor appropriately uses `del` (crash on missing) rather than `.pop()` (defensive) per project philosophy. There is one warning-level finding regarding `getattr(logging, level.upper())` which could accept invalid levels silently, and one observation about reconfiguration safety.

## Warnings

### [83] getattr(logging, level.upper()) accepts invalid log levels silently

**What:** The `level` parameter is converted to a logging constant via `getattr(logging, level.upper())`. If an invalid level string is passed (e.g., `"VERBOSE"`, `"TRACE"`, `""`), `getattr` returns `None` (since `logging.VERBOSE` doesn't exist as a standard level) rather than raising an error. `root.setLevel(None)` would then silently set the level to the `NOTSET` value (0), causing ALL log messages to be emitted.
**Why it matters:** An operator who misconfigures the log level in YAML (e.g., `level: TRACE` thinking of a different framework) would get every DEBUG message flooding their output with no indication the configured value was invalid. In an emergency dispatch context, log noise could obscure critical alerts.
**Evidence:**
```python
log_level = getattr(logging, level.upper())
# If level="TRACE", getattr(logging, "TRACE") returns the module attribute if it exists,
# or raises AttributeError (no default given).
```
**Correction to analysis:** Actually, `getattr` without a default WILL raise `AttributeError` if the attribute doesn't exist. So `getattr(logging, "TRACE")` raises. This is actually correct behavior -- crash on invalid input. However, the function signature accepts `str` with no validation comment, and certain edge cases could be confusing:
- `getattr(logging, "WARNING")` returns `30` (correct)
- `getattr(logging, "WARN")` returns `30` (works, but deprecated alias)
- `getattr(logging, "StreamHandler")` returns `<class 'StreamHandler'>` (not an int, `setLevel` accepts it silently and converts via `logging._checkLevel`)

The last case is a contrived but real path where a non-level attribute name could be passed. Per the project's standards, this is a minor gap -- input validation on `level` should reject non-level strings rather than relying on `getattr` over a module namespace.

### [131-135] Root logger handler replacement is not idempotent-safe

**What:** The code replaces all root logger handlers with `root.handlers = []` followed by `root.addHandler(handler)`. If `configure_logging()` is called multiple times (e.g., in test fixtures), a new `StreamHandler(sys.stdout)` is created each time.
**Why it matters:** In test scenarios, repeated calls leak `StreamHandler` objects (they are replaced, not closed). The old handlers are not explicitly closed, so their file descriptors remain open until garbage collection. In practice, since `sys.stdout` is the target, this is harmless (stdout doesn't need closing). But if the handler target were ever changed to a file, this would leak file handles.
**Evidence:**
```python
handler = logging.StreamHandler(sys.stdout)
# ...
root = logging.getLogger()
root.handlers = []          # Orphans previous handlers without close()
root.addHandler(handler)
```
**Mitigating factor:** The `cache_logger_on_first_use=False` flag in structlog configuration (line 116) suggests this function IS expected to be called multiple times in tests, so this pattern is intentional. The orphaned handlers targeting stdout are not harmful.

## Observations

### [48-65] _remove_internal_fields uses del correctly per project philosophy

**What:** Uses `del event_dict["_record"]` and `del event_dict["_from_structlog"]` instead of `.pop()` with defaults. The comment explains that these fields are guaranteed present by ProcessorFormatter's contract.
**Why it matters:** This is the correct approach per CLAUDE.md -- crash on missing fields in system code rather than silently handling the absence. If structlog changes its internal contract, this will fail loudly.

### [26-45] Noisy logger silencing list is comprehensive

**What:** The `_NOISY_LOGGERS` tuple covers Azure SDK, urllib3, OpenTelemetry, httpx, and httpcore. These are silenced to WARNING even when ELSPETH runs in DEBUG mode.
**Why it matters:** This is well-considered. Azure SDK in particular emits full HTTP request/response bodies at DEBUG level, which could leak sensitive data into logs. The explicit listing (rather than a wildcard) ensures new libraries aren't silently suppressed.

### [109-117] structlog configuration routes through stdlib

**What:** structlog is configured to use `stdlib.LoggerFactory()` and `ProcessorFormatter.wrap_for_formatter`, meaning all structlog output flows through the standard logging infrastructure. The `foreign_pre_chain` parameter ensures stdlib-only records get the same shared processors.
**Why it matters:** This is the recommended structlog integration pattern. It ensures a single output stream regardless of whether code uses `structlog.get_logger()` or `logging.getLogger()`.

### [144-154] get_logger type annotation

**What:** The return type is annotated as `structlog.stdlib.BoundLogger` with an explicit type assignment on line 153. This is needed because `structlog.get_logger()` returns `FilteringBoundLogger | Any` depending on configuration.
**Why it matters:** This provides correct type information to downstream code. The explicit annotation is necessary for mypy to understand the return type.

## Verdict

**Status:** SOUND
**Recommended action:** Consider adding validation of the `level` parameter to reject non-standard log level strings. The handler replacement pattern is acceptable for the current use case but should be revisited if handler targets change from stdout.
**Confidence:** HIGH -- The file is well-structured, the structlog integration follows documented best practices, and the dual-routing pattern (structlog + stdlib) is correctly implemented.
