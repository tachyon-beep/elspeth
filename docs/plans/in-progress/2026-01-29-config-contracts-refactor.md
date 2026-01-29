# Config Contracts Refactor: Fix the Settings→Runtime Mapping Problem

> **Priority:** P2 (Architectural debt, not blocking RC-1 but creates ongoing bug risk)
> **Effort:** Medium (2-3 sessions)
> **Risk:** Low (additive changes, comprehensive test coverage exists)

## Problem Statement

The contracts model was designed to own all cross-boundary types, but **Settings→Runtime config mappings were never properly contracted**. This caused P2-2026-01-21 (`exponential_base` silently ignored) and audit revealed 10+ orphaned config fields across the codebase.

### The Architectural Gap

**What the original plan (2026-01-16) specified:**
```
contracts/
├── config.py        # ResolvedConfig, PipelineSettings
```

**What actually shipped:**
```python
# contracts/config.py
# "These are re-exports from core/config.py for import consistency.
# The actual definitions stay in core/config.py..."
```

**The consequence:**
- `RetrySettings` lives in `core/config.py` (Pydantic, user-facing)
- `RetryConfig` lives in `engine/retry.py` (dataclass, runtime)
- `RetryPolicy` lives in `contracts/engine.py` (TypedDict, plugin config)
- The `from_settings()` mapping is ad-hoc with no contract enforcement
- Fields can be added to Settings and silently orphaned

### Trust Boundary Violation

Per the Data Manifesto, Settings→Runtime is a **trust boundary crossing**:
- **Tier 3 (Settings):** User-provided YAML config, needs validation
- **Tier 2 (Runtime):** Validated runtime state, trusted within engine

The `from_settings()` factory IS the boundary conversion, but it was implemented as an ad-hoc method in consuming modules instead of a proper contract.

---

## Current State (from Alignment Test Audit)

### Orphaned Fields by Subsystem

| Settings Class | Orphaned Fields | Impact |
|----------------|-----------------|--------|
| **ConcurrencySettings** | `max_workers` | Thread pool size never configured |
| **RateLimitSettings** | ALL 5 fields | Registry never instantiated |
| **CheckpointSettings** | `aggregation_boundaries` | Never checked |
| **CheckpointSettings** | ALL fields in normal run | Only used during resume |
| **LandscapeSettings** | `enabled`, `backend` | Not validated at runtime |

### Existing Alignment Tests

The following tests now exist as a band-aid (added 2026-01-29):
- `tests/core/test_config_alignment.py` - Documents field categorization
- `tests/engine/test_retry_policy.py::TestRetrySchemaAlignment` - Retry-specific alignment

These tests use `xfail` markers to document known gaps but don't fix the architecture.

---

## Target Architecture

### Package Structure

```
src/elspeth/contracts/
├── __init__.py           # Re-exports everything
├── enums.py              # (existing) Status codes, modes
├── config/
│   ├── __init__.py       # Re-exports
│   ├── settings.py       # Re-exports from core/config.py (user-facing Pydantic)
│   ├── runtime.py        # NEW: Runtime config dataclasses
│   └── protocols.py      # NEW: Mapping protocols
├── ...
```

### Runtime Config Pattern

```python
# contracts/config/runtime.py
"""Runtime configuration contracts.

These dataclasses represent validated runtime state consumed by engine
components. They are constructed from user-facing Settings via from_settings()
factory methods.

The separation enforces:
1. Settings (Pydantic) handle validation of user input (Tier 3)
2. Runtime (dataclass) holds validated state (Tier 2)
3. from_settings() is the trust boundary conversion
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.core.config import RetrySettings

@dataclass(frozen=True)
class RuntimeRetryConfig:
    """Runtime retry configuration.

    Constructed from RetrySettings via from_settings().
    All fields MUST be mapped - alignment tests enforce this.
    """
    max_attempts: int
    base_delay: float
    max_delay: float
    jitter: float
    exponential_base: float

    @classmethod
    def from_settings(cls, settings: "RetrySettings") -> "RuntimeRetryConfig":
        """Convert user-facing Settings to runtime config.

        This is the Tier 3 → Tier 2 trust boundary conversion.
        """
        return cls(
            max_attempts=settings.max_attempts,
            base_delay=settings.initial_delay_seconds,
            max_delay=settings.max_delay_seconds,
            jitter=1.0,  # Internal default, documented in class docstring
            exponential_base=settings.exponential_base,
        )
```

### Mapping Protocol

```python
# contracts/config/protocols.py
"""Protocols for Settings → Runtime mappings."""

from typing import Protocol, Self, TypeVar

from pydantic import BaseModel

S = TypeVar("S", bound=BaseModel)

class RuntimeConfigProtocol(Protocol):
    """Protocol for runtime config types that map from Settings.

    All runtime config dataclasses MUST implement this protocol.
    The alignment tests verify field coverage.
    """

    @classmethod
    def from_settings(cls, settings: S) -> Self:
        """Convert Settings to runtime config.

        Implementers MUST map all non-internal Settings fields.
        """
        ...
```

---

## Implementation Tasks

### Phase 1: Create Infrastructure (Non-Breaking)

**Task 1.1: Create contracts/config/ subpackage**
- Create `contracts/config/__init__.py`
- Create `contracts/config/settings.py` (move re-exports from `contracts/config.py`)
- Create `contracts/config/runtime.py` (empty, add docstring)
- Create `contracts/config/protocols.py` (define `RuntimeConfigProtocol`)
- Update `contracts/__init__.py` to re-export from new location
- **Tests:** Verify all existing imports still work

**Task 1.2: Create RuntimeRetryConfig in contracts**
- Define `RuntimeRetryConfig` dataclass in `contracts/config/runtime.py`
- Include ALL fields from current `RetryConfig` in `engine/retry.py`
- Add `from_settings()` class method
- **Do NOT delete `engine/retry.py` RetryConfig yet** - deprecate in next phase
- **Tests:** Add test verifying `RuntimeRetryConfig` matches `RetryConfig` fields

**Task 1.3: Create RuntimeRateLimitConfig in contracts**
- Define `RuntimeRateLimitConfig` dataclass
- Map from `RateLimitSettings` (all 5 fields)
- Include `from_settings()` factory
- **Tests:** Alignment test with sentinel values

**Task 1.4: Create RuntimeConcurrencyConfig in contracts**
- Define `RuntimeConcurrencyConfig` dataclass
- Map `max_workers` from `ConcurrencySettings`
- **Tests:** Alignment test

**Task 1.5: Create RuntimeCheckpointConfig in contracts**
- Define `RuntimeCheckpointConfig` dataclass
- Map ALL fields including `aggregation_boundaries`
- **Tests:** Alignment test

### Phase 2: Wire Runtime Configs to Engine (Breaking)

**Task 2.1: Replace RetryConfig with RuntimeRetryConfig**
- Update `engine/retry.py` to use `RuntimeRetryConfig` from contracts
- Delete the local `RetryConfig` dataclass
- Update `RetryManager` to accept `RuntimeRetryConfig`
- Update `Orchestrator` to use `RuntimeRetryConfig.from_settings()`
- **Tests:** All retry tests must pass

**Task 2.2: Wire RuntimeRateLimitConfig to CLI**
- Instantiate `RateLimitRegistry` from `RuntimeRateLimitConfig` in CLI
- Pass registry to Orchestrator
- Remove xfail marker from alignment test
- **Tests:** Integration test for rate limiting

**Task 2.3: Wire RuntimeConcurrencyConfig to Orchestrator**
- Pass `max_workers` to ThreadPoolExecutor creation
- Remove xfail marker from alignment test
- **Tests:** Concurrency integration test

**Task 2.4: Wire RuntimeCheckpointConfig to normal run**
- Pass checkpoint config to Orchestrator in normal run (not just resume)
- Implement `aggregation_boundaries` check
- Remove xfail markers from alignment tests
- **Tests:** Checkpoint integration tests

### Phase 3: Extend AST Checker

**Task 3.1: Add Settings→Runtime alignment check**
- Extend `config/cicd/check_contracts.py`
- Verify every `*Settings` class has corresponding `Runtime*Config` in contracts
- Verify field counts match (accounting for INTERNAL_ONLY fields)
- **Tests:** AST checker tests

**Task 3.2: Add from_settings() coverage check**
- Verify `from_settings()` references all Settings fields
- Flag unused Settings fields as errors
- **Tests:** AST checker tests

### Phase 4: Cleanup

**Task 4.1: Remove band-aid alignment tests**
- The alignment tests in `test_config_alignment.py` become redundant
- Replace with AST checker enforcement
- Keep as documentation or remove entirely

**Task 4.2: Update CLAUDE.md**
- Document the Settings→Runtime pattern
- Add to "Core Architecture" section
- Reference the trust boundary model

---

## Migration Strategy

### Import Compatibility

During Phase 1-2, maintain backwards compatibility:

```python
# engine/retry.py - during transition
from elspeth.contracts.config.runtime import RuntimeRetryConfig

# Temporary alias for existing code
RetryConfig = RuntimeRetryConfig
```

### Test-Driven Migration

Each task follows TDD:
1. Write failing test for new contract
2. Implement contract
3. Wire to runtime
4. Remove xfail markers
5. Verify all tests pass

---

## Success Criteria

### Immediate (Phase 1-2 Complete)

- [ ] All runtime config dataclasses live in `contracts/config/runtime.py`
- [ ] All `from_settings()` methods are in contracts, not scattered in engine
- [ ] Zero orphaned fields (all alignment tests pass without xfail)
- [ ] `RateLimitSettings` actually controls rate limiting
- [ ] `ConcurrencySettings.max_workers` actually controls thread pool
- [ ] `CheckpointSettings` works for normal runs, not just resume

### Long-term (Phase 3-4 Complete)

- [ ] AST checker prevents future field orphaning at CI time
- [ ] Adding a field to Settings without updating Runtime fails CI
- [ ] CLAUDE.md documents the pattern for future contributors

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing imports | Medium | Medium | Maintain aliases during transition |
| RateLimitRegistry integration is complex | Medium | Low | It's already implemented, just not wired |
| AST checker false positives | Low | Low | Use whitelist for intentional exceptions |
| Performance impact of new dataclasses | Very Low | Very Low | Dataclasses are lightweight |

---

## Dependencies

- **None** - This is foundational infrastructure cleanup
- **Blocked by:** Nothing
- **Blocks:** No features, but reduces ongoing bug risk

---

## Verification

After each phase:

```bash
# Run alignment tests
.venv/bin/python -m pytest tests/core/test_config_alignment.py -v

# Run all retry tests
.venv/bin/python -m pytest tests/engine/test_retry*.py tests/integration/test_retry*.py -v

# Type check contracts
.venv/bin/python -m mypy src/elspeth/contracts/

# Lint
.venv/bin/python -m ruff check src/elspeth/contracts/
```

---

## References

- **Original contracts plan:** `docs/plans/completed/2026-01-16-contracts-subsystem.md`
- **Bug that exposed this:** `docs/bugs/closed/engine-retry/P2-2026-01-21-retry-exponential-base-ignored.md`
- **Quality audit findings:** `docs/quality-audit/INTEGRATION_SEAM_ANALYSIS_REPORT.md` (Finding #8)
- **Alignment tests:** `tests/core/test_config_alignment.py`
- **Data Manifesto:** `CLAUDE.md` (Three-Tier Trust Model section)
