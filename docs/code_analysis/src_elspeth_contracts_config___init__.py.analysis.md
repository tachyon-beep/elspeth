# Analysis: src/elspeth/contracts/config/__init__.py

**Lines:** 114
**Role:** Module exports and convenience imports for the config contracts package. Re-exports all public symbols from alignment.py, defaults.py, protocols.py, and runtime.py. Provides a single import point: `from elspeth.contracts.config import X`.
**Key dependencies:**
- Imports: `contracts.config.alignment` (all public symbols), `contracts.config.defaults` (all public symbols), `contracts.config.protocols` (all protocol classes), `contracts.config.runtime` (all config dataclasses)
- Imported by: `engine.retry`, `engine.orchestrator.core`, `engine.__init__`, `cli.py`, `core.rate_limit.registry`, `telemetry.factory`, `tests/core/test_config_alignment.py`, many test files
**Analysis depth:** FULL

## Summary

This is a well-organized package init file that serves as the public API surface for the config contracts subpackage. It correctly re-exports all public symbols, maintains a complete `__all__` list, and includes clear documentation about what should NOT be imported from this package (Settings classes). The boundary enforcement comment referencing P2-2026-01-20 is helpful context. No issues found.

## Observations

### __all__ is complete and alphabetically sorted

The `__all__` list on lines 92-114 includes all 15 re-exported symbols, alphabetically sorted. Cross-referencing against the import statements:

From alignment.py (6 symbols):
- EXEMPT_SETTINGS, FIELD_MAPPINGS, SETTINGS_TO_RUNTIME -- present
- get_runtime_field_name, get_settings_field_name, is_exempt_settings -- present

From defaults.py (4 symbols):
- INTERNAL_DEFAULTS, POLICY_DEFAULTS -- present
- get_internal_default, get_policy_default -- present

From protocols.py (5 symbols):
- RuntimeCheckpointProtocol, RuntimeConcurrencyProtocol, RuntimeRateLimitProtocol, RuntimeRetryProtocol, RuntimeTelemetryProtocol -- present

From runtime.py (6 symbols):
- ExporterConfig, RuntimeCheckpointConfig, RuntimeConcurrencyConfig, RuntimeRateLimitConfig, RuntimeRetryConfig, RuntimeTelemetryConfig -- present

Total: 21 imported, 15 in __all__. Wait -- let me recount.

Imports: 6 + 4 + 5 + 6 = 21 symbols imported.
__all__: 15 entries listed.

Missing from __all__: SETTINGS_TO_RUNTIME is imported (line 37) but IS in __all__ (line 97). Let me recount the __all__ entries: EXEMPT_SETTINGS, FIELD_MAPPINGS, INTERNAL_DEFAULTS, POLICY_DEFAULTS, SETTINGS_TO_RUNTIME, ExporterConfig, RuntimeCheckpointConfig, RuntimeCheckpointProtocol, RuntimeConcurrencyConfig, RuntimeConcurrencyProtocol, RuntimeRateLimitConfig, RuntimeRateLimitProtocol, RuntimeRetryConfig, RuntimeRetryProtocol, RuntimeTelemetryConfig, RuntimeTelemetryProtocol, get_internal_default, get_policy_default, get_runtime_field_name, get_settings_field_name, is_exempt_settings = 21 entries. Correct, all accounted for.

### RUNTIME_TO_SUBSYSTEM is imported but not in __all__

Wait, re-reading: line 37 imports `SETTINGS_TO_RUNTIME` from alignment. The `RUNTIME_TO_SUBSYSTEM` constant from alignment.py is NOT imported here. It is only used internally by `scripts/check_contracts.py` which imports it directly from `alignment.py`. This is intentional -- `RUNTIME_TO_SUBSYSTEM` is an implementation detail of the AST checker, not part of the public API.

This is a reasonable design decision. The `__init__.py` re-exports the consumer-facing symbols; tooling-only symbols stay in their submodules.

### Leaf boundary documentation is clear

Lines 81-90 explicitly document that Settings classes are NOT re-exported, with a reference to the P2-2026-01-20 fix. This prevents future developers from accidentally importing Settings classes from the wrong module. The comment `# FIX: P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary` links to the specific issue.

### Import ordering follows the logical grouping

The imports are grouped by submodule with section headers:
1. Field alignment documentation (alignment.py)
2. Default registries (defaults.py)
3. Runtime protocols (protocols.py)
4. Runtime configuration dataclasses (runtime.py)

Each group has a comment explaining what the imports provide. This is clean and easy to navigate.

### No circular import risk

The import chain is: `__init__.py` -> `alignment.py` (no elspeth imports), `defaults.py` (no elspeth imports), `protocols.py` (TYPE_CHECKING only imports), `runtime.py` (imports from defaults.py and contracts.enums). None of these create circular dependencies. The lazy imports in `runtime.py`'s `from_settings()` methods avoid the `core.config` -> `contracts.config` -> `core.config` cycle.

## Verdict

**Status:** SOUND
**Recommended action:** None. This file is well-structured and complete. The only potential improvement would be adding `RUNTIME_TO_SUBSYSTEM` to the re-exports if it becomes needed by consumers beyond the AST checker, but its current placement is appropriate.
**Confidence:** HIGH -- Simple re-export module, fully verified against source submodules.
