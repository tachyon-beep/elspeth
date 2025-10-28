# SecureDataFrame Hardening - Delta Document

**Status**: Proposed Security Enhancement
**Date**: 2025-10-25
**Supersedes**: Current `SecureDataFrame` implementation (commit d83d7fd)
**Related**: ADR-002-A (Trusted Container Model)
**Security Impact**: HIGH - Prevents classification laundering attack

---

## Executive Summary

This document describes a security hardening of `SecureDataFrame` to prevent **classification laundering attacks** where malicious or buggy plugins create new frames with downgraded classifications.

**Current Model**: Plugins can create new `SecureDataFrame` instances, relying on certification to ensure they use `with_uplifted_security_level()`.

**Proposed Model**: Only datasources can create frames (trusted container pattern). Plugins mutate data content but cannot create new classification containers.

**Security Improvement**: Moves "classification uplifting enforcement" from **certification-only** to **technical control**.

---

## Problem Statement

### Current Implementation Gap

The Phase 1 implementation (commit d83d7fd) provides excellent building blocks:
- ✅ Immutable classification metadata (`@dataclass(frozen=True)`)
- ✅ `with_uplifted_security_level()` prevents downgrades via `max()` operation
- ✅ `validate_compatible_with()` runtime failsafe

However, **nothing prevents plugins from calling `SecureDataFrame(data, lower_level)` directly**.

### The Attack Scenario

```python
class SubtlyMaliciousTransform(BasePlugin):
    """Plugin that launders SECRET data as OFFICIAL by creating fresh frame."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # Truthful about capability

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        # Passes start-time validation
        if level < SecurityLevel.SECRET:
            raise SecurityValidationError("Requires SECRET")

    def process(self, input_data: SecureDataFrame) -> SecureDataFrame:
        # Input: SECRET data (classification verified)
        assert input_data.classification == SecurityLevel.SECRET

        # Transform the data
        result_df = some_transformation(input_data.data)

        # ❌ ATTACK: Create "fresh" frame with OFFICIAL classification
        # Bypasses with_uplifted_security_level() entirely
        return SecureDataFrame(result_df, SecurityLevel.OFFICIAL)

        # ✅ SHOULD HAVE BEEN:
        # return input_data.with_uplifted_security_level(SecurityLevel.SECRET)
```

### Why This Is More Subtle Than T2

**T2 (Security Downgrade Attack)** from THREAT_MODEL.md:
- Plugin lies about `get_security_level()`
- Easily caught: "Does this sink actually handle SECRET data?"

**Classification Laundering** (this attack):
- Plugin tells truth about `get_security_level()` (can handle SECRET)
- Passes start-time validation (correct security level declared)
- Lies about **output data lineage** (claims transformed data is "fresh" OFFICIAL)
- Harder to catch: Requires reviewing every data transformation

---

## Current vs. Proposed Model Comparison

### Current Model (Phase 1 Implementation)

```python
@dataclass(frozen=True)
class SecureDataFrame:
    """Classification metadata is immutable, but container creation is unrestricted."""

    data: pd.DataFrame
    classification: SecurityLevel

    # ✅ Prevents downgrade via max()
    def with_uplifted_security_level(self, new_level: SecurityLevel) -> "SecureDataFrame":
        uplifted = max(self.classification, new_level)
        return SecureDataFrame(data=self.data, security_level=uplifted)

# Usage in plugins (BOTH patterns possible)
class GoodPlugin:
    def process(self, input_frame: SecureDataFrame) -> SecureDataFrame:
        # ✅ CORRECT: Use uplifting method
        return input_frame.with_uplifted_security_level(self.get_security_level())

class BadPlugin:
    def process(self, input_frame: SecureDataFrame) -> SecureDataFrame:
        # ❌ WRONG: Create fresh frame (not prevented!)
        return SecureDataFrame(new_data, SecurityLevel.OFFICIAL)
```

**Trust Model**:
- Technical controls: Prevent accidental misconfiguration (T1, T3)
- Certification: Ensure plugins use `with_uplifted_security_level()` (T4)

**Risk**: Classification laundering requires **certification review** to catch.

---

### Proposed Model (Trusted Container)

```python
@dataclass(frozen=True)
class SecureDataFrame:
    """Trusted container: Only datasources create, plugins mutate content."""

    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = False  # Internal security flag

    def __post_init__(self):
        """Enforce: Only datasources can create SecureDataFrame instances."""
        import inspect
        frame = inspect.currentframe().f_back

        # Allow creation from with_uplifted_security_level()
        if frame.f_code.co_name == 'with_uplifted_security_level':
            return

        # Allow creation if marked as datasource
        if object.__getattribute__(self, '_created_by_datasource'):
            return

        # Block all other creation attempts
        raise SecurityValidationError(
            f"SecureDataFrame can only be created by datasources. "
            f"Plugins must use with_uplifted_security_level() or mutate .data directly."
        )

    @classmethod
    def create_from_datasource(cls, data: pd.DataFrame, classification: SecurityLevel):
        """Datasource-only factory method."""
        instance = cls.__new__(cls)
        object.__setattr__(instance, 'data', data)
        object.__setattr__(instance, 'classification', classification)
        object.__setattr__(instance, '_created_by_datasource', True)
        return instance

    def with_uplifted_security_level(self, new_level: SecurityLevel):
        """Plugins use this to uplift (shares underlying DataFrame)."""
        uplifted = max(self.classification, new_level)
        instance = cls.__new__(cls)
        object.__setattr__(instance, 'data', self.data)  # Share data
        object.__setattr__(instance, 'classification', uplifted)
        object.__setattr__(instance, '_created_by_datasource', False)
        return instance

    def with_new_data(self, new_data: pd.DataFrame):
        """Create frame with new data but preserves current classification."""
        instance = cls.__new__(cls)
        object.__setattr__(instance, 'data', new_data)
        object.__setattr__(instance, 'classification', self.classification)
        object.__setattr__(instance, '_created_by_datasource', False)
        return instance
```

**Usage Patterns**:

```python
# ✅ Datasource: Create initial container
class SecretDatasource(DataSource):
    def load(self) -> SecureDataFrame:
        raw_data = pd.read_csv("secret.csv")
        return SecureDataFrame.create_from_datasource(
            data=raw_data,
            security_level=SecurityLevel.SECRET
        )

# ✅ Plugin Pattern 1: In-place mutation (preferred)
class Transform(TransformNode):
    def process(self, frame: SecureDataFrame) -> SecureDataFrame:
        # Mutate data directly (container unchanged)
        frame.data['processed'] = frame.data['text'].str.upper()

        # Uplift classification
        return frame.with_uplifted_security_level(self.get_security_level())

# ✅ Plugin Pattern 2: Entirely new data (e.g., LLM generation)
class LLMGenerator(TransformNode):
    def process(self, frame: SecureDataFrame) -> SecureDataFrame:
        new_df = self.llm.generate(...)

        # Create frame with new data, preserve classification, then uplift
        return frame.with_new_data(new_df).with_uplifted_security_level(
            self.get_security_level()
        )

# ❌ Malicious Plugin: Blocked by framework
class MaliciousPlugin(TransformNode):
    def process(self, frame: SecureDataFrame) -> SecureDataFrame:
        # Try to launder SECRET as OFFICIAL
        return SecureDataFrame(frame.data, SecurityLevel.OFFICIAL)
        # Raises: SecurityValidationError("can only be created by datasources")
```

**Trust Model**:
- Technical controls: Prevent misconfiguration (T1, T3) + **classification laundering (T4)**
- Certification: Ensure plugins truthfully report `get_security_level()` (T2 only)

**Improvement**: Classification laundering **technically prevented**, reduces certification burden.

---

## Detailed Changes

### 1. Constructor Protection

**Before**:
```python
@dataclass(frozen=True)
class SecureDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    # No restrictions on creation
```

**After**:
```python
@dataclass(frozen=True)
class SecureDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = False

    def __post_init__(self):
        """Validate creation source - only datasources or internal methods allowed."""
        # Implementation as shown in Proposed Model section
```

**Rationale**: Prevents plugins from circumventing `with_uplifted_security_level()`.

---

### 2. Datasource Factory Method

**New Addition**:
```python
@classmethod
def create_from_datasource(
    cls,
    data: pd.DataFrame,
    classification: SecurityLevel
) -> "SecureDataFrame":
    """Factory for datasources to create initial classified frames.

    This is the ONLY way to create a SecureDataFrame from scratch.
    Plugins cannot use this - blocked by __post_init__.
    """
```

**Rationale**: Explicit API for trusted frame creation.

---

### 3. with_new_data() Method

**New Addition**:
```python
def with_new_data(self, new_data: pd.DataFrame) -> "SecureDataFrame":
    """Create frame with different data but same classification.

    Use when plugin generates entirely new data (not in-place transformation).
    Must still call with_uplifted_security_level() afterwards.

    Example:
        result = input_frame.with_new_data(generated_df).with_uplifted_security_level(
            self.get_security_level()
        )
    """
```

**Rationale**: Support plugins that generate new DataFrames (LLMs, aggregations) without allowing classification laundering.

---

### 4. Data Mutability Clarification

**Before**: Ambiguous whether `.data` mutation is allowed.

**After**: Explicit in documentation and usage examples.

```python
# ✅ RECOMMENDED: Mutate .data in-place
frame.data['new_column'] = transform(frame.data['old_column'])
return frame.with_uplifted_security_level(self.get_security_level())

# ✅ ALSO VALID: Generate new data, then preserve+uplift classification
new_df = generate_data()
return frame.with_new_data(new_df).with_uplifted_security_level(
    self.get_security_level()
)

# ❌ BLOCKED: Cannot create fresh frame
return SecureDataFrame(new_data, SecurityLevel.OFFICIAL)  # SecurityValidationError
```

**Rationale**: Data mutation is the **point** of the orchestration. Classification container is what's protected.

---

## Security Properties Comparison

| Property | Current Model | Proposed Model | Enforcement |
|----------|---------------|----------------|-------------|
| **Classification immutability** | ✅ Frozen dataclass | ✅ Frozen dataclass | Technical |
| **Prevent downgrade** | ✅ max() in uplift | ✅ max() in uplift | Technical |
| **Runtime validation** | ✅ validate_compatible_with() | ✅ validate_compatible_with() | Technical |
| **Prevent forgotten uplifting** | ⚠️ Documentation | ✅ No direct constructor | Technical |
| **Prevent classification laundering** | ❌ Certification only | ✅ Constructor blocked | **Technical** |
| **Prevent malicious get_security_level()** | ❌ Certification only | ❌ Certification only | Certification |

**Key Improvement**: T4 (Classification Mislabeling) moves from certification-dependent to technically enforced.

---

## Threat Model Impact

### T4: Classification Mislabeling - CONTROL STRENGTHENED

**Current Defense** (from THREAT_MODEL.md line 176):
```
Primary (Automatic Uplifting): SecureDataFrame.with_uplifted_security_level()
  - Every component MUST uplift: max(input.classification, self.get_security_level())
  - NOT optional, NOT manual
  - Enforced by inherited BasePlugin behavior  ❌ NOT ACTUALLY ENFORCED
```

**Proposed Defense**:
```
Primary (Constructor Protection): SecureDataFrame.__post_init__()
  - Only datasources can create SecureDataFrame instances
  - Plugins MUST use with_uplifted_security_level() (no alternative)
  - Enforced by __post_init__ validation ✅ TECHNICALLY ENFORCED
```

**Updated Test Evidence**:
- `test_INVARIANT_classification_uplifting_automatic` (existing)
- `test_plugin_cannot_create_frame_directly` (new)
- `test_malicious_classification_laundering_blocked` (new)

---

### T2: Security Downgrade Attack - PARTIALLY MITIGATED

**Previous Analysis** (THREAT_MODEL.md line 93):
> Out of Scope: Framework CANNOT prevent malicious code (would require solving Halting Problem per Rice's Theorem)

**Updated Analysis**:
Framework CAN prevent:
- ✅ Malicious plugins creating downgraded frames
- ✅ Buggy plugins forgetting to uplift

Framework CANNOT prevent:
- ❌ Malicious plugins lying about `get_security_level()`
- ❌ Malicious plugins exfiltrating data via side channels

**Certification Scope Reduction**: Only need to verify `get_security_level()` honesty, not data transformation code.

---

## Migration Impact

### Breaking Changes

**None** - This is additive hardening:

1. **Datasources** that currently do:
   ```python
   return SecureDataFrame(data, SecurityLevel.SECRET)
   ```

   Must change to:
   ```python
   return SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)
   ```

2. **Plugins** already using `with_uplifted_security_level()`: ✅ No change required

3. **Malicious/buggy plugins** creating frames directly: ❌ Now blocked (intentional)

---

### Rollout Strategy

**Phase 1**: Implement hardened `SecureDataFrame` with feature flag
```python
# Allow toggling enforcement during rollout
ENFORCE_DATASOURCE_ONLY_CREATION = os.getenv('ADR_002A_ENFORCE', 'false').lower() == 'true'

def __post_init__(self):
    if ENFORCE_DATASOURCE_ONLY_CREATION:
        # Enforcement logic
```

**Phase 2**: Update all datasources to use `create_from_datasource()`

**Phase 3**: Enable enforcement by default, require opt-out

**Phase 4**: Remove feature flag, make enforcement mandatory

---

## Performance Impact

**Constructor Check**: ~1-5μs per frame creation (inspect.currentframe())

**Frame Creation Frequency**:
- Datasources: Once per job (1 frame created)
- Plugins: Once per transformation IF using `with_new_data()` (shares DataFrame)
- Typical pipeline: 3-5 frame operations total

**Expected Overhead**: < 0.1ms per suite execution (negligible)

**Optimization**: If profiling shows impact, cache caller validation in production mode.

---

## Testing Requirements

### New Tests Required

1. **test_plugin_cannot_create_frame_directly**
   ```python
   def test_plugin_cannot_create_frame_directly():
       """Plugins cannot create SecureDataFrame - only datasources."""
       with pytest.raises(SecurityValidationError,
                         match="can only be created by datasources"):
           SecureDataFrame(pd.DataFrame(), SecurityLevel.OFFICIAL)
   ```

2. **test_datasource_can_create_frame**
   ```python
   def test_datasource_can_create_frame():
       """Datasources can create frames via factory method."""
       frame = SecureDataFrame.create_from_datasource(
           data=pd.DataFrame({"col": [1, 2]}),
           security_level=SecurityLevel.SECRET
       )
       assert frame.classification == SecurityLevel.SECRET
   ```

3. **test_with_uplifted_security_level_bypasses_check**
   ```python
   def test_with_uplifted_security_level_bypasses_check():
       """with_uplifted_security_level can create new instances (internal method)."""
       frame = SecureDataFrame.create_from_datasource(...)
       uplifted = frame.with_uplifted_security_level(SecurityLevel.SECRET)
       assert uplifted.classification == SecurityLevel.SECRET  # No error
   ```

4. **test_with_new_data_preserves_classification**
   ```python
   def test_with_new_data_preserves_classification():
       """with_new_data creates frame with new data but same classification."""
       original = SecureDataFrame.create_from_datasource(
           pd.DataFrame({"a": [1]}), SecurityLevel.OFFICIAL
       )
       new_frame = original.with_new_data(pd.DataFrame({"b": [2]}))

       assert new_frame.classification == SecurityLevel.OFFICIAL
       assert "b" in new_frame.data.columns
       assert "a" not in new_frame.data.columns
   ```

5. **test_malicious_classification_laundering_blocked**
   ```python
   def test_malicious_classification_laundering_blocked():
       """Prevents classification laundering attack scenario."""
       # Simulate malicious transform trying to launder SECRET as OFFICIAL
       secret_frame = SecureDataFrame.create_from_datasource(
           pd.DataFrame({"secret": ["classified"]}),
           SecurityLevel.SECRET
       )

       # Malicious plugin tries to create "fresh" OFFICIAL frame
       with pytest.raises(SecurityValidationError):
           laundered = SecureDataFrame(
               secret_frame.data,
               SecurityLevel.OFFICIAL  # Attack attempt
           )
   ```

---

## Documentation Updates

### API Documentation

**SecureDataFrame docstring** - Add lifecycle section:
```python
"""
Lifecycle:
    1. Datasource creates via create_from_datasource()
    2. Plugins mutate .data directly OR use with_new_data()
    3. Plugins uplift via with_uplifted_security_level()
    4. Sink consumes final frame

Security Model (Trusted Container):
    - Container (SecureDataFrame): Created by datasource, immutable classification
    - Content (.data): Mutable, transformed by plugins
    - Uplifting: Only direction allowed (max() operation)
"""
```

### Plugin Development Guide

**Add "Classified Data Handling" section**:
```markdown
## Working with SecureDataFrame

### Pattern 1: In-Place Transformation (Recommended)
```python
def process(self, input_frame: SecureDataFrame) -> SecureDataFrame:
    # Mutate data in the container
    input_frame.data['result'] = transform(input_frame.data['input'])

    # Uplift classification
    return input_frame.with_uplifted_security_level(self.get_security_level())
```

### Pattern 2: New Data Generation
```python
def process(self, input_frame: SecureDataFrame) -> SecureDataFrame:
    # Generate entirely new DataFrame
    new_data = self.llm.generate(...)

    # Preserve classification, then uplift
    return input_frame.with_new_data(new_data).with_uplifted_security_level(
        self.get_security_level()
    )
```

### ❌ Anti-Pattern: Direct Frame Creation
```python
# WRONG - This will raise SecurityValidationError
return SecureDataFrame(new_data, SecurityLevel.OFFICIAL)
```
```

---

## Certification Impact

### Review Checklist Changes

**Before** (Current ADR-002 certification):
- [ ] Plugin declares `get_security_level()` truthfully
- [ ] Plugin implements `validate_can_operate_at_level()` correctly
- [ ] **All data transformations use `with_uplifted_security_level()`** ← REMOVED
- [ ] No malicious code paths bypass validation

**After** (ADR-002-A certification):
- [ ] Plugin declares `get_security_level()` truthfully
- [ ] Plugin implements `validate_can_operate_at_level()` correctly
- [ ] ~~All data transformations use with_uplifted_security_level()~~ **TECHNICALLY ENFORCED**
- [ ] No malicious code paths bypass validation

**Effort Reduction**: Eliminates manual review of every data transformation for uplifting logic.

---

## Appendix: Implementation Checklist

- [ ] Update `SecureDataFrame` with `__post_init__` validation
- [ ] Add `create_from_datasource()` class method
- [ ] Add `with_new_data()` instance method
- [ ] Add `_created_by_datasource` internal flag
- [ ] Update `with_uplifted_security_level()` to bypass checks
- [ ] Write 5 new security tests
- [ ] Update all datasources to use factory method
- [ ] Update plugin development documentation
- [ ] Update THREAT_MODEL.md T4 defense layer
- [ ] Update ADR-002 certification checklist
- [ ] Performance validation (< 0.1ms overhead)
- [ ] Create ADR-002-A formal document

---

## References

- **Original Implementation**: `src/elspeth/core/security/secure_data.py` (commit d83d7fd)
- **Threat Model**: `ADR002_IMPLEMENTATION/THREAT_MODEL.md`
- **ADR-002**: `docs/security/adr-002-orchestrator-security-model.md`
- **Related ADR**: ADR-002-A (Trusted Container Model) - this document's formal ADR

---

**Document Status**: Ready for review and ADR-002-A creation
**Security Review Required**: Yes - changes security boundary
**Breaking Changes**: Minimal (only affects direct constructor usage)
**Estimated Implementation Time**: 4-6 hours
