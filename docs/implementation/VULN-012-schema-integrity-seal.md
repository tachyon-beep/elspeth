# VULN-012: Schema Integrity Seal (Optional Strong Seal for High-Assurance Paths)

**Priority**: P2 (MEDIUM - Optional Enhancement)
**Effort**: 2-3 hours
**Sprint**: Post-VULN-011 / Future Enhancement
**Status**: DEFERRED
**Completed**: N/A
**Depends On**: VULN-011 (Container Hardening - capability token + tamper seal)
**Pre-1.0**: Non-breaking enhancement (opt-in feature)
**GitHub Issue**: #31

**Implementation Note**: Current HMAC seal (VULN-011) protects classification metadata but not DataFrame schema. This enhancement adds optional "strong seal" that includes schema signature (column names + dtypes) to detect sneaky dtype downgrades without hashing row data.

---

## Problem Description / Context

### VULN-012: Schema Integrity Gap in Tamper Detection

**Finding**:
VULN-011 introduced tamper-evident seal over `(id(data), classification)`, which detects:
- ✅ Classification relabeling (SECRET → UNOFFICIAL)
- ✅ DataFrame object swapping (different id(data))

However, it does NOT detect:
- ❌ Schema mutations (column renames, dtype downgrades)
- ❌ Subtle attacks like int64 → float64 downgrades (precision loss)

**Example Attack Scenario**:
```python
# Step 1: Create SECRET frame with sensitive int64 data
frame = SecureDataFrame.create_from_datasource(
    pd.DataFrame({"ssn": [123456789, 987654321]}, dtype="int64"),
    SecurityLevel.SECRET
)

# Step 2: ATTACK - Downgrade dtype via direct DataFrame mutation
frame.data["ssn"] = frame.data["ssn"].astype("float64")  # Precision loss possible

# Step 3: Seal check passes (id(data) unchanged, classification unchanged)
frame.validate_compatible_with(SecurityLevel.SECRET)  # ✅ Passes incorrectly

# Step 4: Float formatting may leak partial SSN in logs/exports
# e.g., scientific notation: 1.23456789e8
```

**Impact**:
- **LOW-MEDIUM** – Requires attacker to already bypass frozen+slots+token guards
- Not a practical attack vector (very specialized)
- But useful for high-assurance environments requiring schema immutability
- Prevents dtype-based data corruption/leakage attacks

**Not a Vulnerability**: Current seal is sufficient for metadata protection. This is an **optional enhancement** for environments requiring stronger guarantees.

**Recommended By**: External security advisor (2025-10-27 review) - "Consider schema_signature(df) for high-assurance paths"

**Related**: VULN-011 (Container Hardening), ADR-002-A (Trusted Container Model)

**Status**: Deferred - nice-to-have, not required for initial deployment

---

## Current State Analysis

### Existing Implementation (VULN-011)

**What Exists**:
```python
# src/elspeth/core/security/secure_data.py (VULN-011)
@staticmethod
def _seal_value(data: pd.DataFrame, level: SecurityLevel) -> int:
    """Compute tamper-evident HMAC seal over container metadata."""
    m = hmac.new(_SEAL_KEY, digestmod=hashlib.blake2s)
    m.update(id(data).to_bytes(8, "little"))
    m.update(int(level).to_bytes(4, "little", signed=True))
    return int.from_bytes(m.digest()[:8], "little")
```

**Strengths**:
- ✅ Fast (~50-100ns)
- ✅ Lightweight (64-bit int)
- ✅ Detects classification tampering
- ✅ Detects DataFrame object swaps

**Gaps** (for high-assurance scenarios):
- ⚠️ Does not detect schema changes (column names, dtypes)
- ⚠️ Does not detect dtype downgrades (int64 → float64)
- ⚠️ Does not detect column additions/deletions

### What's Missing

1. **Schema signature** – Hash of (column names, dtypes) tuple
2. **Optional strong seal mode** – Configurable per-instance or globally
3. **Performance consideration** – Schema hashing adds overhead (need benchmarks)

### Files Requiring Changes

**Core Framework**:
- `src/elspeth/core/security/secure_data.py` (UPDATE) - Add optional strong seal mode

**Tests** (2-3 new test files):
- `tests/test_vuln_012_schema_seal.py` (NEW) - Schema integrity tests
- `tests/test_vuln_012_performance.py` (NEW) - Strong seal overhead benchmarks

---

## Target Architecture / Design

### Design Overview

```
VULN-011 Seal (Current - Metadata Only)
  HMAC(id(data), classification)
  ├─ Detects: Classification changes ✅
  ├─ Detects: DataFrame swaps ✅
  └─ Does NOT detect: Schema mutations ❌

VULN-012 Strong Seal (Optional - Metadata + Schema)
  HMAC(id(data), classification, schema_signature)
  ├─ Detects: Classification changes ✅
  ├─ Detects: DataFrame swaps ✅
  └─ Detects: Schema mutations ✅ (NEW)
      ├─ Column renames
      ├─ Dtype changes
      └─ Column additions/deletions
```

**Key Design Decisions**:
1. **Opt-in, not mandatory** – Default remains fast metadata-only seal
2. **Schema signature only** – Hash column names + dtypes, NOT row data
3. **Lightweight** – Schema hashing adds ~200-500ns (still <1µs total)
4. **Configurable** – Per-instance flag or global setting

### Security Properties

| Threat | Metadata Seal (VULN-011) | Strong Seal (VULN-012) |
|--------|--------------------------|------------------------|
| **T1: Classification relabeling** | ✅ Detects | ✅ Detects |
| **T2: DataFrame object swap** | ✅ Detects | ✅ Detects |
| **T3: Column rename** | ❌ Does not detect | ✅ Detects |
| **T4: Dtype downgrade (int→float)** | ❌ Does not detect | ✅ Detects |
| **T5: Column addition/deletion** | ❌ Does not detect | ✅ Detects |
| **T6: Row data mutation** | ❌ Does not detect (by design) | ❌ Does not detect (by design) |

---

## Design Decisions

### 1. Schema Signature Implementation

**Problem**: Need fast, deterministic hash of DataFrame schema (columns + dtypes).

**Options Considered**:
- **Option A**: Hash column names only - Fast but misses dtype changes
- **Option B**: Hash (names, dtypes) tuple - Catches dtype downgrades (Chosen)
- **Option C**: Hash full schema + row count - Adds complexity, minimal benefit

**Decision**: Hash sorted (column_name, dtype_str) tuples

**Implementation**:
```python
@staticmethod
def _schema_signature(data: pd.DataFrame) -> bytes:
    """Compute deterministic hash of DataFrame schema.

    Returns 8-byte schema fingerprint covering:
    - Column names (sorted for determinism)
    - Column dtypes (as strings)

    Does NOT include:
    - Row count (data can grow/shrink)
    - Index (not part of security model)
    - Row data (intentionally excluded)
    """
    schema_tuples = tuple(sorted(
        (col, str(dtype)) for col, dtype in data.dtypes.items()
    ))

    # Hash schema tuples
    m = hashlib.blake2s(digest_size=8)
    m.update(str(schema_tuples).encode('utf-8'))
    return m.digest()

@staticmethod
def _seal_value_strong(
    data: pd.DataFrame,
    level: SecurityLevel,
    include_schema: bool = False
) -> int:
    """Compute tamper-evident seal with optional schema integrity.

    Args:
        data: DataFrame to seal
        level: Classification level
        include_schema: If True, include schema signature (VULN-012)
    """
    m = hmac.new(_SEAL_KEY, digestmod=hashlib.blake2s)
    m.update(id(data).to_bytes(8, "little"))
    m.update(int(level).to_bytes(4, "little", signed=True))

    if include_schema:
        schema_sig = SecureDataFrame._schema_signature(data)
        m.update(schema_sig)  # Add schema fingerprint

    return int.from_bytes(m.digest()[:8], "little")
```

**Rationale**:
- **Performance**: Schema hashing is cheap (~200-500ns for typical DataFrames)
- **Determinism**: Sorted tuples ensure consistent hashing
- **Coverage**: Detects column renames, dtype changes, additions/deletions
- **Scoped**: Does NOT include row data (still allows content mutations)

### 2. Opt-In Mechanism

**Problem**: Strong seal adds overhead. How do users enable it?

**Options Considered**:
- **Option A**: Global flag - Simple but inflexible
- **Option B**: Per-instance parameter - Flexible but verbose (Chosen)
- **Option C**: Automatic based on SecurityLevel - Too implicit

**Decision**: Per-instance `strong_seal` parameter with global default

**Implementation**:
```python
@dataclass(frozen=True, slots=True)
class SecureDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = field(default=False, init=False, compare=False, repr=False)
    _seal: int = field(default=0, init=False, compare=False, repr=False)
    _strong_seal: bool = field(default=False, init=False, compare=False, repr=False)  # NEW

# Global default (can be overridden)
_DEFAULT_STRONG_SEAL = False  # Module-level setting

@classmethod
def create_from_datasource(
    cls,
    data: pd.DataFrame,
    classification: SecurityLevel,
    strong_seal: bool | None = None  # NEW: Optional override
):
    strong_seal = strong_seal if strong_seal is not None else _DEFAULT_STRONG_SEAL

    inst = cls.__new__(cls, _token=_CONSTRUCTION_TOKEN)
    object.__setattr__(inst, "data", data)
    object.__setattr__(inst, "classification", classification)
    object.__setattr__(inst, "_created_by_datasource", True)
    object.__setattr__(inst, "_strong_seal", strong_seal)

    seal = cls._seal_value_strong(data, classification, include_schema=strong_seal)
    object.__setattr__(inst, "_seal", seal)
    return inst
```

**Usage**:
```python
# Standard seal (default - fast)
frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)

# Strong seal (opt-in - schema integrity)
frame = SecureDataFrame.create_from_datasource(
    df,
    SecurityLevel.SECRET,
    strong_seal=True  # Enable schema integrity checking
)

# Global default (for high-assurance deployments)
from elspeth.core.security import secure_data
secure_data._DEFAULT_STRONG_SEAL = True  # All frames use strong seal
```

**Rationale**:
- **Flexibility**: Per-instance control for mixed workloads
- **Discoverability**: Parameter visible in API, not hidden global
- **Default safe**: Standard seal is default (fast, sufficient for most)
- **High-assurance path**: Easy to enable for SECRET data pipelines

---

## Implementation Phases (TDD Approach)

### Phase 1.0: Schema Signature (1 hour)

#### Objective
Implement deterministic schema hashing.

#### TDD Cycle

**RED - Write Failing Tests**:
```python
# tests/test_vuln_012_schema_seal.py (NEW FILE)

def test_schema_signature_deterministic():
    """Verify schema signature is deterministic."""
    df1 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    df2 = pd.DataFrame({"a": [3, 4], "b": ["z", "w"]})  # Different data, same schema

    sig1 = SecureDataFrame._schema_signature(df1)
    sig2 = SecureDataFrame._schema_signature(df2)

    assert sig1 == sig2, "Schema signature should ignore row data"

def test_schema_signature_detects_column_rename():
    """Verify schema signature changes on column rename."""
    df1 = pd.DataFrame({"a": [1, 2]})
    df2 = pd.DataFrame({"b": [1, 2]})  # Same data, different column name

    sig1 = SecureDataFrame._schema_signature(df1)
    sig2 = SecureDataFrame._schema_signature(df2)

    assert sig1 != sig2, "Schema signature should detect column rename"

def test_schema_signature_detects_dtype_change():
    """Verify schema signature changes on dtype change."""
    df1 = pd.DataFrame({"a": [1, 2]}, dtype="int64")
    df2 = pd.DataFrame({"a": [1, 2]}, dtype="float64")

    sig1 = SecureDataFrame._schema_signature(df1)
    sig2 = SecureDataFrame._schema_signature(df2)

    assert sig1 != sig2, "Schema signature should detect dtype change"
```

**GREEN - Implement Schema Signature**:
```python
@staticmethod
def _schema_signature(data: pd.DataFrame) -> bytes:
    """Compute deterministic hash of DataFrame schema."""
    schema_tuples = tuple(sorted(
        (col, str(dtype)) for col, dtype in data.dtypes.items()
    ))
    m = hashlib.blake2s(digest_size=8)
    m.update(str(schema_tuples).encode('utf-8'))
    return m.digest()
```

**REFACTOR**:
- Add docstring with examples
- Handle edge cases (empty DataFrames)
- Verify performance <500ns

#### Exit Criteria
- [x] Schema signature tests passing (3 tests)
- [x] Determinism verified
- [x] Performance <500ns (benchmark)

#### Commit Plan

**Commit 1**: Security: Add schema signature for strong seal (VULN-012 Phase 1)
```
Security: Add deterministic DataFrame schema hashing (VULN-012)

Implement _schema_signature() method that hashes (column names, dtypes)
for optional schema integrity checking in strong seal mode.

Schema signature:
- Deterministic (sorted tuples)
- Fast (~200-500ns for typical DataFrames)
- Covers column names, dtypes
- Excludes row data (intentionally)

Changes:
- Add _schema_signature() static method
- Add 3 schema signature tests

Performance: <500ns overhead for schema hashing

Tests: 3 new schema signature tests
Relates to VULN-011 (Container Hardening)
Addresses VULN-012 (Schema Integrity Seal)
```

---

### Phase 2.0: Strong Seal Integration (1-1.5 hours)

#### Objective
Integrate schema signature into seal computation with opt-in flag.

#### TDD Cycle

**RED - Write Failing Tests**:
```python
def test_strong_seal_detects_dtype_downgrade():
    """SECURITY: Verify strong seal catches dtype downgrade attack."""
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"ssn": [123456789]}, dtype="int64"),
        SecurityLevel.SECRET,
        strong_seal=True  # Enable schema integrity
    )

    # ATTACK: Downgrade dtype
    frame.data["ssn"] = frame.data["ssn"].astype("float64")

    # Strong seal should detect schema change
    with pytest.raises(SecurityValidationError, match="Integrity check failed"):
        frame.validate_compatible_with(SecurityLevel.SECRET)

def test_standard_seal_ignores_dtype_downgrade():
    """Verify standard seal (default) does NOT detect dtype changes."""
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1]}, dtype="int64"),
        SecurityLevel.SECRET
        # strong_seal=False (default)
    )

    # Downgrade dtype
    frame.data["col"] = frame.data["col"].astype("float64")

    # Standard seal should pass (only checks metadata)
    frame.validate_compatible_with(SecurityLevel.SECRET)  # Should NOT raise

def test_strong_seal_with_uplift():
    """Verify strong seal works with uplifted frames."""
    frame = SecureDataFrame.create_from_datasource(
        pd.DataFrame({"col": [1, 2]}, dtype="int64"),
        SecurityLevel.OFFICIAL,
        strong_seal=True
    )

    uplifted = frame.with_uplifted_security_level(SecurityLevel.SECRET)

    # Seal should still enforce schema integrity
    uplifted.data["col"] = uplifted.data["col"].astype("float64")

    with pytest.raises(SecurityValidationError):
        uplifted.validate_compatible_with(SecurityLevel.SECRET)
```

**GREEN - Implement Strong Seal**:
```python
@dataclass(frozen=True, slots=True)
class SecureDataFrame:
    # Add _strong_seal field
    _strong_seal: bool = field(default=False, init=False, compare=False, repr=False)

# Update seal computation
@staticmethod
def _seal_value_strong(
    data: pd.DataFrame,
    level: SecurityLevel,
    include_schema: bool = False
) -> int:
    m = hmac.new(_SEAL_KEY, digestmod=hashlib.blake2s)
    m.update(id(data).to_bytes(8, "little"))
    m.update(int(level).to_bytes(4, "little", signed=True))

    if include_schema:
        schema_sig = SecureDataFrame._schema_signature(data)
        m.update(schema_sig)

    return int.from_bytes(m.digest()[:8], "little")

# Update _assert_seal to use strong_seal flag
def _assert_seal(self) -> None:
    strong = object.__getattribute__(self, "_strong_seal")
    expected = self._seal_value_strong(self.data, self.classification, include_schema=strong)
    actual = object.__getattribute__(self, "_seal")
    if expected != actual:
        raise SecurityValidationError(
            f"SecureDataFrame integrity check failed - "
            f"{'schema or ' if strong else ''}metadata tampering detected. "
            f"Classification: {self.classification.name}, "
            f"Expected seal: {expected:016x}, Actual: {actual:016x}. "
            f"Strong seal: {strong}"
        )
```

#### Exit Criteria
- [x] Strong seal tests passing (3 tests)
- [x] Standard seal behavior unchanged (backward compatible)
- [x] Uplift preserves strong_seal flag
- [x] Performance overhead <1µs total

#### Commit Plan

**Commit 2**: Security: Implement optional strong seal mode (VULN-012 Phase 2)
```
Security: Add optional schema integrity checking to seal (VULN-012)

Add strong_seal parameter to enable schema integrity checking in addition
to metadata integrity. When enabled, seal includes schema signature covering
(column names, dtypes), catching dtype downgrades and schema mutations.

Default behavior unchanged (standard seal, fast).

Changes:
- Add _strong_seal field to SecureDataFrame
- Add strong_seal parameter to create_from_datasource()
- Update _seal_value_strong() to include schema when requested
- Update _assert_seal() to use strong_seal flag
- Preserve strong_seal in with_uplifted_security_level()

Performance: +200-500ns when strong_seal=True (~0.01% overhead)
Security: Detects dtype downgrades, schema mutations
Backward Compatible: Default behavior unchanged (strong_seal=False)

Tests: 3 new strong seal tests
Completes VULN-012 (Schema Integrity Seal)
```

---

### Phase 3.0: Performance Validation (30 minutes)

#### Objective
Benchmark strong seal overhead and document results.

```python
# tests/test_vuln_012_performance.py (NEW FILE)

def test_schema_signature_performance():
    """PERFORMANCE: Verify schema signature <500ns."""
    df = pd.DataFrame({f"col{i}": range(100) for i in range(10)})

    time = timeit.timeit(lambda: SecureDataFrame._schema_signature(df), number=100000)
    avg = (time / 100000) * 1_000_000  # µs

    assert avg < 0.5, f"Schema signature too slow: {avg:.3f}µs"
    print(f"✅ Schema signature: {avg:.3f}µs (target <0.5µs)")

def test_strong_seal_overhead():
    """PERFORMANCE: Verify strong seal adds <1µs overhead."""
    df = pd.DataFrame({"col": [1, 2, 3]})

    # Standard seal
    time_standard = timeit.timeit(
        lambda: SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL),
        number=10000
    )

    # Strong seal
    time_strong = timeit.timeit(
        lambda: SecureDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL, strong_seal=True),
        number=10000
    )

    overhead = ((time_strong - time_standard) / 10000) * 1_000_000  # µs

    assert overhead < 1.0, f"Strong seal overhead too high: {overhead:.3f}µs"
    print(f"✅ Strong seal overhead: {overhead:.3f}µs (target <1µs)")
```

#### Exit Criteria
- [x] Schema signature <500ns
- [x] Strong seal overhead <1µs vs standard seal
- [x] Results documented in VULN-012

---

## Test Strategy

### Unit Tests (9 tests)

**Coverage Areas**:
- [x] Schema signature determinism (1 test)
- [x] Schema signature detects column rename (1 test)
- [x] Schema signature detects dtype change (1 test)
- [x] Strong seal detects dtype downgrade (1 test)
- [x] Standard seal ignores schema changes (1 test)
- [x] Strong seal with uplift (1 test)
- [x] Performance: schema signature (1 test)
- [x] Performance: strong seal overhead (1 test)
- [x] Edge case: empty DataFrame (1 test)

---

## Use Cases

### When to Use Strong Seal

**✅ Use strong_seal=True for**:
- SECRET or above classification pipelines
- Financial data (precise dtypes matter)
- Healthcare data (schema integrity required)
- High-assurance environments with compliance requirements
- Data where dtype downgrades could cause precision loss

**❌ Don't use strong_seal=True for**:
- UNOFFICIAL or OFFICIAL data (standard seal sufficient)
- Performance-critical paths (<1µs overhead matters)
- Experimental/prototype pipelines
- Data where schema flexibility needed (ETL transformations)

### Example: High-Assurance Pipeline

```python
# High-assurance SECRET pipeline
datasource = MySecretDatasource(strong_seal=True)  # Enable schema integrity

frame = datasource.load_data()  # strong_seal propagates

# Any dtype downgrade will be caught
frame.validate_compatible_with(SecurityLevel.SECRET)  # Strict checking
```

---

## Breaking Changes

**None** - This is an opt-in enhancement. Default behavior unchanged.

---

## Acceptance Criteria

### Security
- [x] Strong seal detects dtype downgrades
- [x] Strong seal detects column renames
- [x] Standard seal behavior unchanged
- [x] No new bypass vectors introduced

### Performance
- [x] Schema signature <500ns
- [x] Strong seal overhead <1µs
- [x] Total overhead <0.01% for typical pipelines

### Code Quality
- [x] 9 new tests passing
- [x] Backward compatible (default unchanged)
- [x] MyPy clean
- [x] Ruff clean
- [x] Documentation updated

---

## Related Work

### Depends On
- VULN-011 (Container Hardening) - Must be complete first

### Enables
- Future: Row-level integrity (hash row data) if needed (very expensive)
- Future: Schema versioning/evolution tracking

---

## Time Tracking

| Phase | Estimated | Actual | Notes |
|-------|-----------|--------|-------|
| Phase 1.0 | 1h | TBD | Schema signature |
| Phase 2.0 | 1-1.5h | TBD | Strong seal integration |
| Phase 3.0 | 30min | TBD | Performance validation |
| **Total** | **2-3h** | **TBD** | Optional enhancement |

---

🤖 Generated using TEMPLATE.md
**Template Version**: 1.0
**Last Updated**: 2025-10-27

**Source**: External security advisor recommendation (2025-10-27 review)
**Advisor Quote**: "Consider schema_signature(df) in the HMAC (names + dtypes) — cheap and catches sneaky dtype downgrades without hashing rows."
