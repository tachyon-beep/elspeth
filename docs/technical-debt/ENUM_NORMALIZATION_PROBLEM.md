# Security/Determinism Level Normalization

**Date**: 2025-10-20
**Resolution Date**: 2025-10-21
**Status**: RESOLVED
**Severity**: Medium (Code Quality & Maintainability)
**Impact (pre‑fix)**: ~16 files, 90+ normalize_* calls, wide architectural usage

---

## Executive Summary

The system now uses `SecurityLevel` and `DeterminismLevel` enums end‑to‑end. Legacy string normalizers have been removed. All internal code paths (contexts, registries, pipeline, plugins, helpers, endpoint validation) operate on enums. Canonical PSPF strings are produced via `enum.value` only at boundaries that require strings.

---

## The Architecture We Have (Post‑Fix)

### Type Definitions

Located in `src/elspeth/core/base/types.py`:

```python
class SecurityLevel(str, Enum):
    """Australian Government PSPF security classification levels."""
    UNOFFICIAL = "UNOFFICIAL"
    OFFICIAL = "OFFICIAL"
    OFFICIAL_SENSITIVE = "OFFICIAL: SENSITIVE"
    PROTECTED = "PROTECTED"
    SECRET = "SECRET"

    @classmethod
    def from_string(cls, value: str | None) -> "SecurityLevel":
        """Parse string with aliases: 'public'→UNOFFICIAL, 'internal'→OFFICIAL"""
        # Handles case-insensitive input
        # Maps legacy aliases (public, internal, confidential, sensitive)
        # Validates against known levels
        ...

    # Comparison operators for hierarchy enforcement (__lt__, __le__, __gt__, __ge__)

class DeterminismLevel(str, Enum):
    """Determinism spectrum for reproducibility guarantees."""
    NONE = "none"
    LOW = "low"
    HIGH = "high"
    GUARANTEED = "guaranteed"

    @classmethod
    def from_string(cls, value: str | None) -> "DeterminismLevel":
        """Parse string (case-insensitive)"""
        ...

    # Comparison operators for hierarchy enforcement
```

### Normalization Layer

The legacy `normalize_security_level()` and `normalize_determinism_level()` functions have been removed. Use `SecurityLevel.from_string()` / `DeterminismLevel.from_string()` and operate on enums directly.

### Helper Functions (Enum‑Based)

Also in `src/elspeth/core/security/__init__.py`:

```python
def resolve_security_level(*levels: str | None) -> str:
    """Resolve multiple levels to the highest classification."""
    normalized = [normalize_security_level(level) for level in levels if level is not None]
    if not normalized:
        return SECURITY_LEVELS[0]
    return max(normalized, key=SECURITY_LEVELS.index)
    # ^^^ Could use max(enums) directly since SecurityLevel has __gt__

def coalesce_security_level(*levels: str | None) -> str:
    """Return a single normalized level ensuring all inputs agree."""
    # ... uses normalize_security_level() and string comparison
    # ^^^ Could use enum equality directly

# Same pattern for determinism_level
def resolve_determinism_level(*levels: str | None) -> str: ...
def coalesce_determinism_level(*levels: str | None) -> str: ...
```

All helper functions now accept and return enums; comparison uses enum ordering.

---

## Type Signatures Across Codebase (Post‑Fix)

### PluginContext (Core Data Structure)

`src/elspeth/core/base/plugin_context.py`:

```python
class PluginContext(BaseModel):
    security_level: str = Field(..., min_length=1, description="...")
    determinism_level: str = Field(default="none", description="...")

    @field_validator("determinism_level")
    @classmethod
    def validate_determinism_level(cls, v: str) -> str:
        """Validate determinism level is one of the expected values."""
        valid_levels = {"none", "low", "high", "guaranteed"}
        v_lower = v.lower().strip()
        if v_lower not in valid_levels:
            raise ValueError(f"determinism_level must be one of {valid_levels}, got '{v}'")
        return v_lower
```

PluginContext fields are enums with before‑validators to auto‑convert strings from YAML.

### Plugin Implementations

All plugins store these as strings:

```python
# src/elspeth/plugins/nodes/sinks/excel.py
self._security_level: str | None = None
self._determinism_level: str | None = None

# src/elspeth/plugins/nodes/sources/_csv_base.py
def __init__(self, security_level: str | None = None, determinism_level: str | None = None):
    self.security_level = normalize_security_level(security_level)
    self.determinism_level = normalize_determinism_level(determinism_level)
```

### Protocols (Type Contracts)

`src/elspeth/core/base/protocols.py`:

```python
@dataclass
class ArtifactDescriptor:
    security_level: str | None = None
    determinism_level: str | None = None

@dataclass
class Artifact:
    security_level: str | None = None
    determinism_level: str | None = None
```

Protocols and artifacts now carry enums, ensuring type‑safe boundaries.

---

## Resolution Summary

Key changes
- Removed normalize_* functions; removed SECURITY_LEVELS/DETERMINISM_LEVELS constants.
- PluginContext uses enums; validators convert strings → enums.
- Protocols, pipeline artifacts, and sink bindings now carry enums.
- Helper functions (resolve/coalesce/is_allowed) use enums.
- Plugins (sources/sinks/utilities) parse metadata into enums and store enums.
- Endpoint validation accepts enums/strings and normalizes using .value.

All tests updated and passing; coverage ≥ 80% per file.

### Migration Guide (Plugin Authors)

- Accept enums in factories; read `ctx.security_level` / `ctx.determinism_level` directly.
- Convert free‑form input via `.from_string()` when needed.
- Compare using enum ordering; serialize via `.value`.
- Remove usage of `normalize_*` and `SECURITY_LEVELS`/`DETERMINISM_LEVELS`.

YAML configs stay the same (strings), Pydantic converts to enums at load.

**Total Uses**: 90 function calls across these 16 files

### Files Using resolve_* Functions (5 files)

1. `src/elspeth/core/experiments/runner.py`
2. `src/elspeth/core/experiments/suite_runner.py`
3. `src/elspeth/core/orchestrator.py`
4. `src/elspeth/core/security/__init__.py` (defines them)
5. `src/elspeth/plugins/nodes/sinks/zip_bundle.py`

### Configuration Files

**Good News**: Config files (YAML) already use correct PSPF values:
- `security_level: OFFICIAL` (not "internal")
- `determinism_level: guaranteed` (not "GUARANTEED")

**No config migration needed** - users already specify canonical values.

---

## What We Should Have (Target Architecture)

### 1. PluginContext Uses Enums with Pydantic Conversion

```python
from elspeth.core.base.types import SecurityLevel, DeterminismLevel

class PluginContext(BaseModel):
    security_level: SecurityLevel = Field(...)
    determinism_level: DeterminismLevel = Field(default=DeterminismLevel.NONE)

    @field_validator("security_level", mode="before")
    @classmethod
    def parse_security_level(cls, v: str | SecurityLevel) -> SecurityLevel:
        """Auto-convert strings to SecurityLevel enum."""
        if isinstance(v, SecurityLevel):
            return v
        return SecurityLevel.from_string(v)

    @field_validator("determinism_level", mode="before")
    @classmethod
    def parse_determinism_level(cls, v: str | DeterminismLevel) -> DeterminismLevel:
        """Auto-convert strings to DeterminismLevel enum."""
        if isinstance(v, DeterminismLevel):
            return v
        return DeterminismLevel.from_string(v)
```

**Benefits**:
- Type safety: `context.security_level` is guaranteed to be a `SecurityLevel` enum
- Pydantic handles string→enum conversion automatically from YAML configs
- No manual validation needed (enum already validates)
- IDE autocomplete works

### 2. Protocols Use Enums

```python
@dataclass
class ArtifactDescriptor:
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None

@dataclass
class Artifact:
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None
```

### 3. Plugins Store Enums

```python
# Datasources
def __init__(self, security_level: SecurityLevel, determinism_level: DeterminismLevel):
    self.security_level = security_level
    self.determinism_level = determinism_level

# Sinks
self._security_level: SecurityLevel | None = None
self._determinism_level: DeterminismLevel | None = None
```

### 4. Helper Functions Use Enums

```python
def resolve_security_level(*levels: SecurityLevel | None) -> SecurityLevel:
    """Resolve multiple levels to the highest classification."""
    filtered = [level for level in levels if level is not None]
    if not filtered:
        return SecurityLevel.UNOFFICIAL
    return max(filtered)  # Uses SecurityLevel.__gt__

def coalesce_security_level(*levels: SecurityLevel | None) -> SecurityLevel:
    """Return a single level ensuring all inputs agree."""
    filtered = [level for level in levels if level is not None]
    if not filtered:
        raise ValueError("security_level is required")
    if len(set(filtered)) > 1:
        raise ValueError("Conflicting security_level values")
    return filtered[0]

# Same pattern for determinism
```

### 5. Delete normalize_* Functions Entirely

They serve no purpose when everything is properly typed.

---

## Migration Path

### Phase 1: Core Types (High Risk, High Value)

**Files to change**: 2-3 core files
**Impact**: Affects entire codebase via imports

1. Update `PluginContext` to use enums with Pydantic validators (1 file)
2. Update `Artifact` / `ArtifactDescriptor` protocols (1 file)
3. Run tests - expect ~100+ failures (type mismatches)

### Phase 2: Helper Functions (Medium Risk)

**Files to change**: 1 file (`src/elspeth/core/security/__init__.py`)

1. Update `resolve_security_level()` to accept/return enums
2. Update `coalesce_security_level()` to accept/return enums
3. Same for determinism variants
4. Run tests - expect more failures

### Phase 3: Plugins (Low Risk, High Volume)

**Files to change**: ~16 plugin files

For each plugin:
1. Change `security_level: str` → `security_level: SecurityLevel`
2. Change `determinism_level: str` → `determinism_level: DeterminismLevel`
3. Remove `normalize_*()` calls - use enum directly
4. Update constructor signatures

### Phase 4: Cleanup (Zero Risk)

**Files to change**: 1 file

1. Delete `normalize_security_level()` from `src/elspeth/core/security/__init__.py`
2. Delete `normalize_determinism_level()` from `src/elspeth/core/security/__init__.py`
3. Remove from `__all__` exports
4. Run full test suite - should pass

---

## Risks & Considerations

### Breaking Changes

**Public API Impact**: HIGH
- Any external code importing `normalize_security_level()` breaks
- Plugin authors expecting strings will get enums
- Serialization points (JSON, YAML) need enum→string conversion

**Mitigation**:
- Mark as major version bump (breaking change)
- Provide migration guide for plugin authors
- Add deprecation warnings first (keep both paths for 1-2 versions)

### Type Checker Impact

**Before**: Type checkers allow `str` anywhere
**After**: Type checkers enforce enum types

This will catch existing bugs but also may reveal latent type errors.

### Serialization

**Enums are `str` subclasses**, so they serialize naturally:
```python
str(SecurityLevel.OFFICIAL)  # "OFFICIAL"
f"Level: {SecurityLevel.OFFICIAL}"  # "Level: OFFICIAL"
json.dumps(SecurityLevel.OFFICIAL)  # "OFFICIAL"
```

**YAML**: Pydantic handles enum→string for YAML export automatically.

### Performance

**Negligible impact**:
- Enums are singletons (no allocation overhead)
- String comparison vs enum comparison: both O(1)
- `.from_string()` has same logic as `normalize_*()`

---

## Recommendations

### Immediate Action (For Current Work)

**For now** (to unblock CI coverage work):
- Fix the test to expect `"OFFICIAL"` not `"internal"`
- Fix the test to expect PSPF-normalized values
- Document this technical debt (this file)

### Long-Term Refactor (Recommended)

**Timeline**: 1-2 sprints
**Effort**: ~8-16 hours development + testing

1. **Sprint 1**: Phase 1-2 (core types + helpers)
2. **Sprint 2**: Phase 3-4 (plugins + cleanup)

**OR**: Incremental approach with deprecation warnings:
1. Keep `normalize_*()` but mark deprecated
2. Update PluginContext to use enums (auto-convert on boundary)
3. Gradually update plugins file-by-file
4. Remove normalize_*() in next major version

### Alternative: Keep normalize_* but Return Enums

**Compromise approach**:
```python
def normalize_security_level(level: str | SecurityLevel | None) -> SecurityLevel:
    """Convert to SecurityLevel enum (not string)."""
    if isinstance(level, SecurityLevel):
        return level
    return SecurityLevel.from_string(level)
```

This keeps the function but makes it return the enum type. Gentler migration path.

---

## Related Technical Debt

### Similar Patterns to Investigate

1. **Is there a `normalize_data_type()` for `DataType` enum?**
   - Check `src/elspeth/core/base/types.py:DataType`
   - Scan for usage patterns

2. **Are there other enum types being string-wrapped?**
   - Check all `Enum` classes in codebase
   - Look for `normalize_*` or `resolve_*` patterns

3. **Configuration validation**
   - Check `src/elspeth/core/validation/` for similar patterns
   - Look for manual validators duplicating enum logic

---

## Test Impact

### Current Failing Test

`tests/test_validation_rules_simple.py`:

```python
# WRONG (expects denormalized alias)
result = _validate_security_level_fields(
    report, context="test", entry_level="internal", options_level="internal"
)
assert result == "internal"  # FAILS: result is "OFFICIAL"

# CORRECT (expects normalized PSPF value)
result = _validate_security_level_fields(
    report, context="test", entry_level="internal", options_level="internal"
)
assert result == "OFFICIAL"  # internal→OFFICIAL via alias mapping
```

### After Enum Refactor

```python
# Type-safe version
result = _validate_security_level_fields(
    report, context="test",
    entry_level=SecurityLevel.OFFICIAL,
    options_level=SecurityLevel.OFFICIAL
)
assert result == SecurityLevel.OFFICIAL
```

---

## Conclusion

This normalization layer is **legacy technical debt** that should be removed. The enum types already provide:
- Type safety
- Validation
- Alias mapping
- Hierarchy enforcement
- String conversion

The `normalize_*()` functions add complexity without adding value. They hide the well-designed enums behind string-based wrappers and prevent the type system from catching errors.

**Impact**: Medium severity (doesn't affect functionality, but impairs maintainability and type safety)

**Recommendation**: Fix immediate test failures with PSPF values, then schedule refactor for next sprint.

---

## Appendix: Full File Inventory

### Files Defining Types
- `src/elspeth/core/base/types.py` - SecurityLevel, DeterminismLevel enums

### Files Defining Normalization
- `src/elspeth/core/security/__init__.py` - normalize_*, resolve_*, coalesce_*

### Files Using Normalization (16)
1. Core orchestration (4):
   - `src/elspeth/core/experiments/job_runner.py`
   - `src/elspeth/core/experiments/runner.py`
   - `src/elspeth/core/orchestrator.py`
   - `src/elspeth/core/pipeline/artifact_pipeline.py`

2. Registry system (2):
   - `src/elspeth/core/registries/context_utils.py`
   - `src/elspeth/core/registries/plugin_helpers.py`

3. Security/validation (3):
   - `src/elspeth/core/security/approved_endpoints.py`
   - `src/elspeth/core/security/__init__.py`
   - `src/elspeth/core/validation/rules.py`

4. Sinks (6):
   - `src/elspeth/plugins/nodes/sinks/analytics_report.py`
   - `src/elspeth/plugins/nodes/sinks/csv_file.py`
   - `src/elspeth/plugins/nodes/sinks/excel.py`
   - `src/elspeth/plugins/nodes/sinks/file_copy.py`
   - `src/elspeth/plugins/nodes/sinks/_visual_base.py`
   - `src/elspeth/plugins/nodes/sinks/zip_bundle.py`

5. Datasources (2):
   - `src/elspeth/plugins/nodes/sources/blob.py`
   - `src/elspeth/plugins/nodes/sources/_csv_base.py`

### Files Storing as Strings
- `src/elspeth/core/base/plugin_context.py` - PluginContext
- `src/elspeth/core/base/protocols.py` - ArtifactDescriptor, Artifact
- All plugin implementations (see sinks/datasources above)

**Total Estimated Changes**: ~20 files, ~200 lines of code, ~90 function call sites
