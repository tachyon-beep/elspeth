# Analysis: src/elspeth/telemetry/protocols.py

**Lines:** 97
**Role:** Protocol definition for telemetry exporters (`ExporterProtocol`). Defines the contract that all exporters must satisfy: `name` property, `configure()`, `export()`, `flush()`, and `close()` methods.
**Key dependencies:** Imports `TelemetryEvent` from `contracts/events` (TYPE_CHECKING only). Imported by `telemetry/manager.py`, `telemetry/factory.py`, `telemetry/hookspecs.py`, `telemetry/__init__.py`.
**Analysis depth:** FULL

## Summary

Clean protocol definition with thorough documentation of the exporter lifecycle, error handling expectations, and thread safety constraints. The `@runtime_checkable` decorator enables isinstance checks at registration time. The protocol is well-designed and correctly used across the codebase. One documentation inconsistency regarding the export() contract vs. actual TelemetryManager behavior. Confidence is HIGH.

## Warnings

### [62-81] Protocol says export() MUST NOT raise, but TelemetryManager catches and counts exceptions from export()

**What:** The `export()` docstring on line 65 states: "This method MUST NOT raise exceptions." However, `TelemetryManager._dispatch_to_exporters` (manager.py line 170-180) wraps each `exporter.export(event)` call in a try/except block that catches `Exception` and counts failures. The ConsoleExporter correctly follows the protocol (wraps its own errors internally), but the manager's defensive catching suggests the protocol contract is not trusted.

**Why it matters:** This is a contract documentation inconsistency, not a runtime bug. If export() truly MUST NOT raise, the try/except in the manager is dead code. If exporters may raise (which the manager's code path assumes), the protocol documentation is wrong. The actual behavior is that the manager tolerates raising exporters (counting failures), which is the robust choice. The protocol docstring should be updated to match reality: "Implementations SHOULD NOT raise exceptions, but the TelemetryManager will isolate and count failures if they do."

**Evidence:**
```python
# Protocol (line 65):
# "This method MUST NOT raise exceptions"

# Manager (line 170-180):
try:
    exporter.export(event)
except Exception as e:
    failures += 1
    # ... counted and logged
```

### [27-31] Lifecycle documentation says "export() called for each event (must not raise)" but configure() can raise

**What:** The lifecycle documentation describes a 5-step process where step 3 (Configuration) explicitly allows `TelemetryExporterError` but step 4 (Operation) says "must not raise." This is consistent within the protocol, but the error type specificity is asymmetric: `configure()` raises a specific typed exception (`TelemetryExporterError`), while `export()` prohibits all exceptions. If an exporter encounters a configuration-level error during export (e.g., authentication token expired mid-run), there is no defined mechanism to escalate.

**Why it matters:** In long-running pipelines, credentials or endpoints can become invalid after initial configuration. The protocol provides no mechanism for an exporter to signal "I am no longer functional" during operation. The TelemetryManager handles this indirectly through consecutive failure counting, but the protocol itself doesn't define this escalation path.

## Observations

### [14] @runtime_checkable is correctly used

**What:** The `@runtime_checkable` decorator on `ExporterProtocol` enables `isinstance()` checks, which is appropriate for plugin registration where structural typing verification at runtime is valuable.

**Why it matters:** Positive finding -- matches the project's use of runtime_checkable protocols in `contracts/config/protocols.py`.

### [73-76] Thread safety documentation is thorough

**What:** The `export()` docstring explicitly documents that export() runs on the telemetry export thread and warns about thread-local state from configure(). This is correct -- `configure()` runs on the main thread during factory setup, while `export()` runs on the background thread.

**Why it matters:** Positive finding -- important for exporter implementors to know, especially for exporters that use connection pools or clients initialized during configure().

### No `__init__` in protocol

**What:** The protocol does not define `__init__`, meaning exporters can have any constructor signature. The factory (`telemetry/factory.py`) assumes zero-argument construction: `exporter_class()` on line 77 of factory.py.

**Why it matters:** This is a coupling between the factory and exporter implementations that is not captured in the protocol. If a third-party exporter requires constructor arguments, the factory would fail. Since ELSPETH does not support user-provided plugins, this is acceptable but could be documented.

### `flush()` and `close()` don't specify error handling

**What:** Unlike `export()` (which says "MUST NOT raise") and `configure()` (which says "MUST raise TelemetryExporterError"), the `flush()` and `close()` methods have no explicit error handling guidance.

**Why it matters:** The TelemetryManager wraps both `flush()` and `close()` in try/except blocks (manager.py lines 352-359 and 420-427), so runtime behavior is safe regardless. But the protocol documentation gap could lead to inconsistent implementations.

## Verdict

**Status:** SOUND
**Recommended action:** Update the `export()` docstring to reflect reality: the method SHOULD NOT raise, but TelemetryManager will isolate failures if it does. Consider documenting error handling expectations for `flush()` and `close()` for consistency.
**Confidence:** HIGH -- Protocol definitions are simple and well-documented. No structural issues.
