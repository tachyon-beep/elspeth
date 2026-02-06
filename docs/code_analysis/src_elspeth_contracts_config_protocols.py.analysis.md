# Analysis: src/elspeth/contracts/config/protocols.py

**Lines:** 184
**Role:** Protocol definitions for runtime config. Defines the structural typing interfaces that engine components expect from configuration -- mypy verifies that Runtime*Config classes satisfy these protocols. Each protocol corresponds to a specific engine subsystem (RetryManager, RateLimitRegistry, ThreadPoolExecutor, checkpoint system, TelemetryManager).
**Key dependencies:**
- Imports (TYPE_CHECKING only): `contracts.config.runtime` (ExporterConfig), `contracts.enums` (BackpressureMode, TelemetryGranularity)
- Imported by: `contracts.config.__init__`, `engine.retry` (RuntimeRetryProtocol)
**Analysis depth:** FULL

## Summary

This file is clean, well-documented, and fulfills its narrow purpose precisely. The protocols are `@runtime_checkable`, properly typed, and correctly mirror the fields in the corresponding Runtime*Config dataclasses. The separation of concerns is exemplary -- protocols define expectations, dataclasses implement them, and mypy verifies compliance. No critical issues found. Two minor observations about protocol coverage and a potential protocol drift risk.

## Warnings

### [80-101] RuntimeRateLimitProtocol is incomplete relative to RuntimeRateLimitConfig

**What:** `RuntimeRateLimitProtocol` only requires `enabled` and `default_requests_per_minute`. However, `RuntimeRateLimitConfig` also has `persistence_path`, `services`, and the method `get_service_config()`. The docstring (lines 88-89) acknowledges this: "services and persistence_path are handled separately." However, the `RateLimitRegistry` constructor at `core/rate_limit/registry.py:77` accepts `RuntimeRateLimitConfig` directly (not `RuntimeRateLimitProtocol`), and the `get_service_config()` method is called there.

**Why it matters:** The protocol's stated purpose is "What RateLimitRegistry expects from rate limit configuration," but it does not actually capture what the registry expects. The registry needs `get_service_config()`, `persistence_path`, and `services` -- none of which are in the protocol. This means the protocol is not serving its verification purpose for this subsystem. If someone created a test double implementing only the protocol, it would fail at runtime when `get_service_config()` is called.

**Evidence:**
```python
# protocols.py - only two properties
class RuntimeRateLimitProtocol(Protocol):
    @property
    def enabled(self) -> bool: ...
    @property
    def default_requests_per_minute(self) -> int: ...

# But RateLimitRegistry actually needs:
#   config.enabled
#   config.get_service_config(service_name)
#   config.persistence_path (potentially)
```

### [116-143] RuntimeCheckpointProtocol omits checkpoint_interval

**What:** The protocol includes `enabled`, `frequency`, and `aggregation_boundaries`, but omits `checkpoint_interval`. The docstring explains (line 125-126): "checkpoint_interval is conditional on frequency='every_n' and handled during construction, not as a protocol field."

**Why it matters:** This is correctly reasoned -- `checkpoint_interval` is consumed during `from_settings()` to compute `frequency` and is preserved only for reference. However, if any consumer ever needs the raw interval value (for logging, debugging, or audit), the protocol would need updating. This is a minor concern since the field is documented as "preserved for full Settings fidelity."

## Observations

### All protocols are @runtime_checkable -- correct for this use case

The `@runtime_checkable` decorator allows `isinstance()` checks at runtime. While this adds a small overhead, it enables runtime verification in addition to static mypy checking. For a configuration layer where objects are created once at startup, this is the right trade-off.

### Protocol properties use `@property` for read-only semantics

All protocol members are defined as `@property` rather than plain attributes. For frozen dataclasses (which expose attributes as read-only), this is the correct protocol pattern -- mypy treats dataclass fields as satisfying `@property` protocol requirements.

### TYPE_CHECKING imports prevent circular dependencies

The `ExporterConfig`, `BackpressureMode`, and `TelemetryGranularity` imports are under `TYPE_CHECKING` to avoid creating import-time circular dependencies with `runtime.py` and `enums.py`. This is clean and necessary.

### Documentation is thorough and consistent

Each protocol documents which Settings fields map to its properties, including internal-only fields (jitter) and transformation notes (frequency Literal to int). This is well-maintained and consistent with the alignment.py documentation.

### No protocol for ExporterConfig

`ExporterConfig` is a simple dataclass (name + options) used in `RuntimeTelemetryProtocol.exporter_configs`. There is no separate protocol for it, which is correct -- it has no engine consumer that needs to be decoupled from the concrete type.

## Verdict

**Status:** SOUND
**Recommended action:** Consider expanding `RuntimeRateLimitProtocol` to include `get_service_config()` method signature, as the current protocol does not capture the actual requirements of `RateLimitRegistry`. This is a minor structural issue, not a bug, since the registry currently accepts the concrete type. Low priority.
**Confidence:** HIGH -- The file is small, self-contained, and its contracts are verifiable by cross-referencing with the runtime.py dataclasses and engine consumers.
