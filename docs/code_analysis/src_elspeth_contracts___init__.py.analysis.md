# Analysis: src/elspeth/contracts/__init__.py

**Lines:** 373
**Role:** Main contracts package entry point. Re-exports all cross-boundary types (dataclasses, enums, TypedDicts, NamedTuples) from submodules for convenient import. Serves as the public API surface of the contracts package.
**Key dependencies:** Imports from ~20 submodules within `elspeth.contracts.*`. Imported by virtually every module in the engine, plugins, CLI, telemetry, and tests.
**Analysis depth:** FULL

## Summary

This file is a pure re-export module with no logic of its own. It is well-organized with clear section comments and a complete `__all__` list. AST analysis confirms perfect synchronization between imported names and `__all__` entries (no orphans in either direction). The main architectural concern is that this file loads every contracts submodule at import time, which means importing *any* contract symbol eagerly loads all of them. This is a design tradeoff, not a bug. No critical findings.

## Critical Findings

None.

## Warnings

### [Lines 60-77] Contracts imports from `contracts.config` subpackage may pull heavier dependencies

**What:** The imports from `elspeth.contracts.config` bring in `FIELD_MAPPINGS`, `SETTINGS_TO_RUNTIME`, `EXEMPT_SETTINGS`, `POLICY_DEFAULTS`, and `INTERNAL_DEFAULTS`. These are alignment/documentation data structures. While the module docstring (lines 7-9) explicitly states "This package is a LEAF MODULE with no outbound dependencies to core/engine", the `contracts.config` subpackage must itself be leaf-safe.

**Why it matters:** If any `contracts.config` submodule accidentally imports from `elspeth.core`, it would silently violate the leaf module boundary and pull in pandas/numpy/sqlalchemy at import time. The docstring comment references fix `P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary`, suggesting this was a real incident.

**Evidence:** Lines 51-59 contain an explicit warning about Settings classes NOT being re-exported. This is correct. The risk is regression -- future developers adding a new runtime config type might accidentally import a core dependency.

### [Lines 80-87] Schema contract phase comments may mislead about import order

**What:** Comments label imports as "Phase 2: Source Integration", "Phase 3: Pipeline Integration", "Phase 4: Audit Trail Integration" which suggests a build/initialization order. However, all imports happen eagerly at module load time regardless of phase.

**Why it matters:** A developer might assume these phases imply lazy or conditional loading, leading to incorrect dependency assumptions.

**Evidence:**
```python
# Schema contracts (Phase 2: Source Integration)
from elspeth.contracts.contract_builder import ContractBuilder

# Schema contracts (Phase 3: Pipeline Integration)
from elspeth.contracts.contract_propagation import (
```

## Observations

### [Lines 207-373] `__all__` is comprehensive and well-organized

The `__all__` list is grouped by category with comments. AST analysis confirms every imported symbol appears in `__all__` and vice versa. This is good practice for a re-export module.

### Module serves as a convenient import facade

The pattern `from elspeth.contracts import X` instead of `from elspeth.contracts.some_submodule import X` reduces import verbosity across the codebase. The tradeoff is that any import pulls in all submodules.

### No re-export of `AuditIntegrityError` or `OrchestrationInvariantError`

The `errors.py` module defines `AuditIntegrityError` and `OrchestrationInvariantError` which are not re-exported through `__init__.py`. Consumers must import them directly from `elspeth.contracts.errors`. This appears intentional (these are used only in engine internals), but creates an inconsistency with how other error types like `BatchPendingError` and `PluginContractViolation` are exported.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. Consider adding a comment explaining why `AuditIntegrityError` and `OrchestrationInvariantError` are excluded from re-export for future maintainers.
**Confidence:** HIGH -- AST analysis confirms import/export synchronization; no logic to contain bugs.
