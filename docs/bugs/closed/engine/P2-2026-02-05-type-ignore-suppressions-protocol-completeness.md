# P2-2026-02-05: Type: Ignore Suppressions - Protocol Completeness and Runtime Guarantees

**Priority:** P2 (Medium)
**Status:** Closed (Resolved)
**Component:** Engine, Protocols
**Detected:** 2026-02-05 (systematic type safety audit)
**Resolved:** 2026-02-05
**Affects:** Type checking, IDE autocomplete, maintainability

## Summary

Systematic analysis of `type: ignore` suppressions revealed 8 legitimate opportunities to improve type safety and code clarity. These fall into 4 categories, ordered by priority:

1. **EventBusProtocol default parameter mismatch** (HIGH)
2. **Missing `config` attribute in plugin protocols** (HIGH)
3. **Runtime guarantees without assertions** (MEDIUM)
4. **node_id optionality ambiguity** (LOW)

None of these hide bugs, but fixing them improves type safety, eliminates suppressions, and makes code intent clearer.

---

## Issue 1: EventBusProtocol Default Parameter Mismatch (HIGH PRIORITY)

### Location
`src/elspeth/engine/orchestrator/core.py:129`

### Current Code
```python
def __init__(
    self,
    # ... other params
    event_bus: EventBusProtocol = None,  # type: ignore[assignment]
    # ... more params
) -> None:
```

### Problem
Type annotation says `EventBusProtocol` (non-optional), but default value is `None`. This is a direct type annotation mismatch.

### Impact
- ❌ 1 `type: ignore[assignment]` suppression
- ❌ Misleading type hint (callers might think event_bus is required)
- ❌ mypy cannot verify None handling is correct

### Root Cause
Parameter should be typed as `EventBusProtocol | None` to match the default.

### Proposed Fix
```python
def __init__(
    self,
    # ... other params
    event_bus: EventBusProtocol | None = None,
    # ... more params
) -> None:
```

### Files Affected
- `src/elspeth/engine/orchestrator/core.py` (1 line change)

### Testing
- mypy should pass without suppression
- Existing tests should pass (no behavior change)

### Complexity
**Trivial** - One line change, zero behavioral impact

---

## Issue 2: Missing `config` Attribute in Plugin Protocols (HIGH PRIORITY)

### Locations
Multiple files accessing `.config` on plugin instances:
- `src/elspeth/core/dag.py:403` (SourceProtocol)
- `src/elspeth/core/dag.py:416` (SinkProtocol)
- `src/elspeth/core/dag.py:437` (TransformProtocol)
- `src/elspeth/core/dag.py:512` (TransformProtocol)
- `src/elspeth/engine/orchestrator/export.py:91` (SinkProtocol)
- `src/elspeth/engine/orchestrator/export.py:93` (SinkProtocol)

### Current Code (example from dag.py:403)
```python
source_config = source.config  # type: ignore[attr-defined]
```

### Problem
`SourceProtocol`, `TransformProtocol`, `SinkProtocol`, and `GateProtocol` don't declare a `config` attribute, but all concrete implementations set `self.config = config` in `__init__`.

**Protocol definitions lack the attribute:**
```python
@runtime_checkable
class SourceProtocol(Protocol):
    name: str
    output_schema: type["PluginSchema"]
    node_id: str | None
    # ... other attributes
    # MISSING: config: dict[str, Any]
```

**All implementations have it:**
```python
class BaseSource(ABC):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config  # Stored but not in protocol
```

### Impact
- ❌ 6 `type: ignore[attr-defined]` suppressions
- ❌ IDE autocomplete doesn't show `.config` on plugin instances
- ❌ Type checker can't verify config access patterns

### Root Cause
Protocols define the interface but forgot to include the `config` attribute that all plugins provide.

### Proposed Fix
Add `config: dict[str, Any]` to each plugin protocol:

```python
@runtime_checkable
class SourceProtocol(Protocol):
    name: str
    output_schema: type["PluginSchema"]
    node_id: str | None
    config: dict[str, Any]  # Add this line
    # ... rest of protocol
```

Repeat for:
- `TransformProtocol`
- `GateProtocol`
- `SinkProtocol`
- `CoalesceProtocol` (if applicable)

### Files Affected
- `src/elspeth/plugins/protocols.py` (4-5 protocols to update)
- `src/elspeth/core/dag.py` (4 suppressions removed)
- `src/elspeth/engine/orchestrator/export.py` (2 suppressions removed)

### Testing
- mypy should pass without suppressions
- Existing tests should pass (no behavior change)
- IDE autocomplete should show `.config` on plugin instances

### Complexity
**Low** - Add 1 line to each protocol, remove 6 suppressions

---

## Issue 3: Runtime Guarantees Without Assertions (MEDIUM PRIORITY)

### Locations
Multiple locations where Pydantic validation or business logic guarantees invariants that mypy can't track:

#### 3a. Pydantic fork_to Validation
**Location:** `src/elspeth/engine/executors.py:882`

```python
# GateSettings.fork_to is list[str] | None, but Pydantic validator ensures
# fork_to is not None when routes include "fork"
fork_branches: list[str] = gate_config.fork_to  # type: ignore[assignment]
```

**Fix:**
```python
# Pydantic validator guarantees fork_to is not None when routes include "fork"
assert gate_config.fork_to is not None, "Pydantic validation should guarantee fork_to"
fork_branches: list[str] = gate_config.fork_to
```

#### 3b. Coalesce Name Guarantees
**Locations:**
- `src/elspeth/engine/orchestrator/core.py:1429`
- `src/elspeth/engine/orchestrator/core.py:2177`

```python
# outcome.coalesce_name is guaranteed non-None when merged_token is not None
coalesce_name = CoalesceName(outcome.coalesce_name)  # type: ignore[arg-type]
```

**Fix:**
```python
# Business logic: coalesce_name is guaranteed non-None when merged_token is not None
assert outcome.coalesce_name is not None, "Coalesce outcome must have coalesce_name"
coalesce_name = CoalesceName(outcome.coalesce_name)
```

#### 3c. TransformResult.rows Contract Guarantee
**Location:** `src/elspeth/engine/processor.py:1834`

```python
# transform_result.contract is not None, so rows must be multi-row (non-None)
expanded_rows=transform_result.rows,  # type: ignore[arg-type]
```

**Fix:**
```python
# Contract exists, so rows must be non-None (multi-row transform result)
assert transform_result.rows is not None, "Contract presence guarantees rows"
expanded_rows = transform_result.rows
```

#### 3d. MyPy Control Flow Narrowing
**Location:** `src/elspeth/engine/executors.py:385`

```python
# has_output_data guarantees rows is not None, but mypy can't track through property
output_data_with_pipe = result.rows  # type: ignore[assignment]
```

**Fix:**
```python
# has_output_data property guarantees rows is not None
assert result.rows is not None, "has_output_data guarantees rows"
output_data_with_pipe = result.rows
```

#### 3e. Secret Loading Config
**Location:** `src/elspeth/core/security/config_secrets.py:91`

```python
# Function only called when config.source == "keyvault", which guarantees vault_url is not None
loader = KeyVaultSecretLoader(vault_url=config.vault_url)  # type: ignore[arg-type]
```

**Fix:**
```python
# load_secrets_from_config() only called when config.source == "keyvault"
assert config.vault_url is not None, "vault_url required when source=keyvault"
loader = KeyVaultSecretLoader(vault_url=config.vault_url)
```

### Impact
- ✅ Eliminates 5 `type: ignore` suppressions
- ✅ Documents invariants in code (helps future maintainers)
- ✅ Provides runtime verification in DEBUG builds
- ✅ Makes implicit contracts explicit

### Root Cause
Python's type system cannot express Pydantic validation constraints or business logic invariants. Assertions bridge this gap.

### Proposed Fix
Add assertions with explanatory comments at each location (5 total).

### Files Affected
- `src/elspeth/engine/executors.py` (2 locations)
- `src/elspeth/engine/orchestrator/core.py` (2 locations)
- `src/elspeth/engine/processor.py` (1 location)
- `src/elspeth/core/security/config_secrets.py` (1 location)

### Testing
- Assertions should pass in all existing tests (invariants are already true)
- mypy should pass without suppressions

### Complexity
**Low** - Add 1-2 lines per location (assertion + optional comment)

---

## Issue 4: node_id Optionality Ambiguity (LOW PRIORITY - INVESTIGATION NEEDED)

### Locations
- `src/elspeth/engine/processor.py:231`
- `src/elspeth/engine/processor.py:1650`

### Current Code (processor.py:231)
```python
self._event_bus.emit(
    TransformCompleted(
        run_id=ctx.run_id,
        node_id=transform.node_id,  # type: ignore[arg-type]
        # ... other fields
    )
)
```

### Problem
- `TransformProtocol.node_id` is typed as `str | None` (optional)
- `TransformCompleted.node_id` field expects `str` (non-optional)
- Suppressions at emission sites hide this mismatch

### Impact
- ❌ 2 `type: ignore[arg-type]` suppressions
- ❌ Type system doesn't guarantee node_id is set before telemetry emission
- ⚠️ Could emit telemetry with `None` node_id if orchestrator flow changes

### Root Cause (Two Possibilities)

**Hypothesis A: node_id is ALWAYS assigned before execution**
- Orchestrator calls `plugin.node_id = "..."` during registration
- By the time transforms execute, `node_id` is guaranteed non-None
- Protocol should declare `node_id: str` (not optional)

**Hypothesis B: node_id is genuinely optional in some cases**
- Some plugin execution paths don't assign node_id
- Telemetry events should accept `str | None`
- Current suppression is hiding a valid optionality

### Investigation Needed
1. Trace orchestrator initialization flow:
   - Does `orchestrator.register_plugin()` always set `node_id`?
   - Can plugins be executed outside orchestrator (tests, CLI tools)?
2. Check telemetry event consumers:
   - Can they handle `None` node_id gracefully?
   - Are there queries that filter by node_id?

### Proposed Investigation Plan

#### Step 1: Verify Orchestrator Guarantees
```bash
# Search for node_id assignment patterns
grep -n "\.node_id\s*=" src/elspeth/engine/orchestrator/

# Check plugin registration flow
grep -A 10 "def register_plugin" src/elspeth/engine/orchestrator/
```

#### Step 2: Check Test Execution Paths
```bash
# Look for plugins instantiated in tests without orchestrator
grep -n "BaseTransform\|BaseSource\|BaseSink" tests/ | grep -v "orchestrator"
```

#### Step 3: Analyze Telemetry Event Usage
```bash
# Check if telemetry consumers expect non-None node_id
grep -n "node_id" src/elspeth/engine/orchestrator/telemetry.py
grep -n "TransformCompleted" src/
```

### Possible Fixes (Pending Investigation)

**Option A: Make node_id Required (if always assigned)**
```python
@runtime_checkable
class TransformProtocol(Protocol):
    name: str
    node_id: str  # Changed from str | None
    # ... rest of protocol
```

**Option B: Make Telemetry Events Accept Optional (if genuinely optional)**
```python
@dataclass
class TransformCompleted:
    run_id: str
    node_id: str | None  # Changed from str
    # ... other fields
```

**Option C: Add Type Narrowing Assertions (if guaranteed at call sites)**
```python
assert transform.node_id is not None, "node_id must be set by orchestrator before execution"
self._event_bus.emit(
    TransformCompleted(
        run_id=ctx.run_id,
        node_id=transform.node_id,
        # ... other fields
    )
)
```

### Files Affected (Pending Investigation)
- `src/elspeth/plugins/protocols.py` (if changing protocol)
- `src/elspeth/engine/orchestrator/telemetry.py` (if changing events)
- `src/elspeth/engine/processor.py` (2 suppressions to remove)

### Testing
- All existing tests should pass
- Add test verifying node_id is set before telemetry emission

### Complexity
**Medium** - Requires orchestrator flow analysis to determine correct fix

---

## Exclusions (Legitimate Suppressions)

The following suppressions are **intentional and should NOT be fixed**:

### Batch Transform Protocol (6 suppressions)
**Locations:** `src/elspeth/engine/executors.py:170, 178, 179, 181, 286, 337`

**Reason:** Batch transforms dynamically add `_executor_batch_adapter`, `accept()`, `connect_output()`, `evict_submission()` at runtime. This is the `BatchTransformProtocol` architectural pattern introduced in commit `fb63cc3b`.

**Justification:** Type system cannot express "protocol attributes added at runtime based on is_batch_aware flag". Suppressions are well-documented and expected.

### Third-Party Library Type Stubs (3 suppressions)
**Locations:**
- `src/elspeth/core/config.py:1542` (dynaconf)
- `src/elspeth/core/rate_limit/limiter.py:11` (pyrate_limiter)
- `src/elspeth/core/landscape/database.py:126` (SQLAlchemy event handlers)
- `src/elspeth/core/security/secret_loader.py:191` (Azure SDK conditional import)

**Reason:** External libraries with incomplete type stubs or dynamic typing.

**Justification:** Cannot fix without upstream changes. Expected and unavoidable.

---

## Summary of Fixes

| Issue | Priority | Suppressions Removed | Complexity | Impact |
|-------|----------|---------------------|-----------|--------|
| EventBusProtocol default | HIGH | 1 | Trivial | Type safety |
| Missing protocol.config | HIGH | 6 | Low | IDE autocomplete, type safety |
| Runtime guarantees | MEDIUM | 5 | Low | Code clarity, documentation |
| node_id optionality | LOW | 2 | Medium | Requires investigation |
| **TOTAL** | | **14** | | |

---

## Implementation Plan

### Phase 1: Quick Wins (HIGH Priority)
1. Fix `EventBusProtocol` default parameter (1 line change)
2. Add `config: dict[str, Any]` to plugin protocols (4 lines added)
3. Remove 7 suppressions

**Effort:** 30 minutes
**Impact:** 7 suppressions eliminated, improved type safety

### Phase 2: Clarity Improvements (MEDIUM Priority)
1. Add assertions for runtime guarantees (5 locations)
2. Remove 5 suppressions

**Effort:** 1 hour
**Impact:** 5 suppressions eliminated, better code documentation

### Phase 3: Investigation (LOW Priority)
1. Investigate node_id optionality (orchestrator flow analysis)
2. Implement appropriate fix (protocol change, event change, or assertions)
3. Remove 2 suppressions

**Effort:** 2-3 hours (investigation + fix)
**Impact:** 2 suppressions eliminated, clearer orchestrator contracts

---

## Related Issues
- None (new issue from systematic audit)

## Detection Method
Systematic `type: ignore` suppression audit using explore agents after `BatchTransformProtocol` refactoring (commit `fb63cc3b`).

---

## Notes
- All suppressions analyzed are documented in agent reports (see conversation 2026-02-05)
- No defensive patterns or bugs were found - these are protocol completeness issues
- Fixing these improves type safety without changing runtime behavior
- Original audit revealed 15 suppressions; 1 unavoidable (third-party), 14 addressable
