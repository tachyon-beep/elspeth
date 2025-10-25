# ADR-002-A: Trusted Container Model for ClassifiedDataFrame

**Status**: Proposed
**Date**: 2025-10-25
**Augments**: ADR-002 (Orchestrator Security Model)
**Delta Document**: `adr-002-classified-dataframe-hardening-delta.md`
**Security Impact**: HIGH - Prevents classification laundering attack

---

## Context

ADR-002 established a two-layer security model for the orchestration framework:

1. **Start-time validation**: Orchestrator computes minimum clearance envelope, rejects misconfigured plugins before data access
2. **Runtime validation**: `ClassifiedDataFrame` carries classification metadata, validates access at every hand-off

Phase 1 implementation (commit d83d7fd) introduced:
- `ClassifiedDataFrame` wrapper with immutable classification
- `with_uplifted_classification()` method preventing downgrades via `max()` operation
- `validate_access_by()` runtime failsafe

However, **code review identified a security gap**: Nothing prevents plugins from calling `ClassifiedDataFrame(data, lower_level)` directly, bypassing uplifting logic entirely.

### The Attack Scenario

```python
class SubtlyMaliciousPlugin(TransformNode):
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # Truthful - can handle SECRET

    def process(self, input_data: ClassifiedDataFrame) -> ClassifiedDataFrame:
        # Input: SECRET data (validated at start-time)
        result = transform(input_data.data)

        # ❌ ATTACK: Create "fresh" frame claiming OFFICIAL classification
        # Bypasses with_uplifted_classification() entirely
        return ClassifiedDataFrame(result, SecurityLevel.OFFICIAL)
```

This **classification laundering attack** is more subtle than T2 (malicious plugins lying about capabilities) because:
- Plugin truthfully reports `get_security_level()` (passes start-time validation)
- Plugin lies about **output data lineage** (claims transformed SECRET data is "fresh" OFFICIAL)
- Requires reviewing every data transformation to detect

**Current ADR-002 defense**: Certification must verify all plugins use `with_uplifted_classification()` (human review of every transformation).

---

## Problem Statement

**T4 (Classification Mislabeling)** from ADR-002 THREAT_MODEL states:
> "Primary (Automatic Uplifting): Every component MUST uplift...NOT optional, NOT manual. Enforced by inherited BasePlugin behavior."

**Reality**: Uplifting is NOT enforced technically - it's enforced by certification reviewing plugin code.

**Issue**: This increases certification burden and creates risk that reviewers miss malicious/buggy transformations that skip uplifting.

**Desired State**: Move classification uplifting enforcement from **certification** (human review) to **technical control** (framework enforcement).

---

## Decision

We adopt a **Trusted Container Model** for `ClassifiedDataFrame`:

1. **Only datasources can create ClassifiedDataFrame instances** (trusted source)
2. **Classification metadata is immutable** (existing - frozen dataclass)
3. **Data content (.data) is mutable** (explicit - plugins transform in-place)
4. **Only `with_uplifted_classification()` can change classification** (upward only)

### Key Changes

#### 1. Constructor Protection

Add `__post_init__` validation that blocks direct `ClassifiedDataFrame()` calls from plugins:

```python
@dataclass(frozen=True)
class ClassifiedDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = False

    def __post_init__(self):
        """Enforce datasource-only creation."""
        import inspect
        caller = inspect.currentframe().f_back

        # Allow internal methods (with_uplifted_classification, with_new_data)
        if caller.f_code.co_name in ('with_uplifted_classification', 'with_new_data'):
            return

        # Allow datasource factory
        if object.__getattribute__(self, '_created_by_datasource'):
            return

        # Block all other attempts
        raise SecurityValidationError(
            "ClassifiedDataFrame can only be created by datasources. "
            "Plugins must use with_uplifted_classification() or mutate .data directly."
        )
```

#### 2. Datasource Factory Method

```python
@classmethod
def create_from_datasource(
    cls,
    data: pd.DataFrame,
    classification: SecurityLevel
) -> "ClassifiedDataFrame":
    """Create initial classified frame (datasources only).

    This is the ONLY way to create a ClassifiedDataFrame from scratch.
    """
    instance = cls.__new__(cls)
    object.__setattr__(instance, 'data', data)
    object.__setattr__(instance, 'classification', classification)
    object.__setattr__(instance, '_created_by_datasource', True)
    return instance
```

#### 3. with_new_data() Method

For plugins that generate entirely new data (LLMs, aggregations):

```python
def with_new_data(self, new_data: pd.DataFrame) -> "ClassifiedDataFrame":
    """Create frame with different data, preserving current classification.

    Must still call with_uplifted_classification() afterwards.
    """
    instance = ClassifiedDataFrame.__new__(ClassifiedDataFrame)
    object.__setattr__(instance, 'data', new_data)
    object.__setattr__(instance, 'classification', self.classification)
    object.__setattr__(instance, '_created_by_datasource', False)
    return instance
```

### Supported Plugin Patterns

**Pattern 1: In-Place Mutation (Recommended)**
```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    # Mutate data in existing container
    frame.data['processed'] = transform(frame.data['input'])

    # Uplift classification
    return frame.with_uplifted_classification(self.get_security_level())
```

**Pattern 2: New Data Generation**
```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    # Generate entirely new DataFrame
    new_df = self.llm.generate(...)

    # Preserve classification, then uplift
    return frame.with_new_data(new_df).with_uplifted_classification(
        self.get_security_level()
    )
```

**Anti-Pattern: Direct Creation (Blocked)**
```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    # ❌ BLOCKED - SecurityValidationError
    return ClassifiedDataFrame(new_data, SecurityLevel.OFFICIAL)
```

---

## Consequences

### Positive

✅ **Prevents classification laundering attacks** - Technically enforced, not certification-dependent

✅ **Reduces certification burden** - Only need to verify `get_security_level()` honesty, not every transformation

✅ **Clarifies data mutability** - Explicit that `.data` mutation is intended (container vs. content separation)

✅ **Stronger threat defense** - T4 (Classification Mislabeling) moves from "certification only" to "technical control"

✅ **Minimal breaking changes** - Only affects code directly calling constructor (should be rare)

### Negative

⚠️ **Shared DataFrame references** - Multiple `ClassifiedDataFrame` instances may share same pandas DataFrame (mutations visible across references)
- **Mitigation**: Document clearly, add `.copy()` option if needed for parallel processing

⚠️ **Frame inspection overhead** - `__post_init__` uses `inspect.currentframe()` (~1-5μs per creation)
- **Impact**: Negligible (<0.1ms per suite with 3-5 frame operations)
- **Mitigation**: Can cache validation in production if profiling shows impact

⚠️ **Datasource migration required** - All datasources must change from `ClassifiedDataFrame(data, level)` to `ClassifiedDataFrame.create_from_datasource(data, level)`
- **Scope**: ~5-10 datasources in codebase
- **Effort**: ~30 minutes total

### Neutral

🔄 **Does not prevent T2** - Malicious plugins can still lie about `get_security_level()` (out of scope per Rice's Theorem)

🔄 **Maintains existing security properties** - All Phase 1 guarantees preserved (immutability, max() uplifting, runtime validation)

---

## Threat Model Updates

### T4: Classification Mislabeling - DEFENSE STRENGTHENED

**Before** (ADR-002 THREAT_MODEL.md):
```
Defense Layers:
- Primary (Automatic Uplifting): ClassifiedDataFrame.with_uplifted_classification()
  - Every component MUST uplift
  - NOT optional, NOT manual
  - Enforced by inherited BasePlugin behavior  ❌ NOT ENFORCED
- Certification: Code review verifies all transforms use uplifting
```

**After** (ADR-002-A):
```
Defense Layers:
- Primary (Constructor Protection): ClassifiedDataFrame.__post_init__()
  - Only datasources can create frames
  - Plugins MUST use with_uplifted_classification() (no alternative)
  - Enforced by constructor validation ✅ TECHNICAL CONTROL
- Certification: Reduced scope - verify get_security_level() honesty only
```

**Impact**: T4 defense moves from certification-dependent to framework-enforced.

---

### T2: Security Downgrade Attack - PARTIALLY MITIGATED

**Additional Coverage**:
- Framework NOW prevents: Malicious plugins creating downgraded frames
- Framework STILL cannot prevent: Malicious plugins lying about `get_security_level()`

**Certification Scope Reduction**:
- Before: Verify `get_security_level()` honesty + review every transformation
- After: Verify `get_security_level()` honesty only

---

## Implementation Plan

### Phase 1: Core Implementation (3-4 hours)

1. ✅ Update `ClassifiedDataFrame` with `__post_init__` validation
2. ✅ Add `create_from_datasource()` class method
3. ✅ Add `with_new_data()` instance method
4. ✅ Update `with_uplifted_classification()` to bypass checks

### Phase 2: Testing (2 hours)

5. ✅ `test_plugin_cannot_create_frame_directly`
6. ✅ `test_datasource_can_create_frame`
7. ✅ `test_with_uplifted_classification_bypasses_check`
8. ✅ `test_with_new_data_preserves_classification`
9. ✅ `test_malicious_classification_laundering_blocked`

### Phase 3: Migration (1 hour)

10. ✅ Update all datasources to use `create_from_datasource()`
11. ✅ Verify existing plugin patterns still work
12. ✅ Run full test suite

### Phase 4: Documentation (1 hour)

13. ✅ Update `ClassifiedDataFrame` docstring with lifecycle
14. ✅ Add plugin development guide section
15. ✅ Update THREAT_MODEL.md T4 section
16. ✅ Update ADR-002 certification checklist

**Total Estimated Effort**: 7-8 hours

---

## Rollout Strategy

### Option A: Immediate Enforcement (Recommended for greenfield)

Enable enforcement immediately - breaking change for any code calling constructor directly.

**Risk**: Low (should be rare in current codebase)

### Option B: Feature Flag Rollout (Recommended for production)

```python
ENFORCE_DATASOURCE_ONLY_CREATION = os.getenv('ADR_002A_ENFORCE', 'false').lower() == 'true'
```

**Steps**:
1. Deploy with enforcement disabled
2. Update datasources to use factory method
3. Enable enforcement in staging
4. Monitor for violations
5. Enable enforcement in production
6. Remove feature flag after 1 sprint

**Risk**: Very low (gradual rollout with monitoring)

---

## Success Criteria

### Must-Have (MVP)

- [ ] `__post_init__` blocks direct plugin creation
- [ ] `create_from_datasource()` allows datasource creation
- [ ] All 5 security tests pass
- [ ] All existing tests still pass
- [ ] All datasources migrated

### Should-Have (Quality)

- [ ] Plugin development guide updated
- [ ] THREAT_MODEL.md updated
- [ ] Performance validation (<0.1ms overhead)
- [ ] Documentation examples added

### Nice-to-Have (Future)

- [ ] Metrics/logging for constructor violations (monitoring)
- [ ] Type hints clarified (`-> ClassifiedDataFrame` in plugins)
- [ ] Integration tests covering classification laundering scenarios

---

## Alternatives Considered

### Alternative 1: Documentation + Certification Only (Rejected)

**Description**: Keep current implementation, document that plugins must use `with_uplifted_classification()`, rely on certification.

**Pros**: No code changes, no migration effort

**Cons**: Relies on human review catching every missed uplifting call, increases certification burden

**Rejection Reason**: Security controls should be technical when possible (fail-safe design)

---

### Alternative 2: Sealed/Abstract Base Class (Rejected)

**Description**: Make `ClassifiedDataFrame` abstract, require datasources to subclass.

**Pros**: More "Pythonic" inheritance model

**Cons**:
- Increases complexity (subclass per datasource)
- Doesn't prevent plugins from creating their own subclass
- Less explicit than factory method

**Rejection Reason**: Factory method is simpler and more explicit

---

### Alternative 3: Lineage Tracking (Deferred)

**Description**: Add `parent_classification` field tracking data provenance explicitly.

**Pros**: Enables audit trail of classification changes

**Cons**: Increases complexity, overkill for current threat model

**Decision**: Defer to future ADR if provenance auditing becomes requirement

---

## Security Review

### Attack Surface Changes

**Before**: Plugins can create arbitrary `ClassifiedDataFrame` instances

**After**: Only datasources can create instances, plugins limited to uplifting existing frames

**Net Change**: ✅ Reduced attack surface

### Defense in Depth

This ADR adds an additional layer to ADR-002's defense model:

1. **Start-time validation** (existing): Orchestrator rejects misconfigured pipelines
2. **Constructor protection** (new): Plugins cannot create downgraded frames
3. **Runtime validation** (existing): `validate_access_by()` catches bypassed checks
4. **Certification** (reduced scope): Verify `get_security_level()` honesty only

**Assessment**: Strengthens existing controls without introducing new vulnerabilities

---

## References

- **ADR-002**: Orchestrator Security Model - `docs/security/adr-002-orchestrator-security-model.md`
- **Delta Document**: Classification Hardening Details - `docs/security/adr-002-classified-dataframe-hardening-delta.md`
- **Threat Model**: `ADR002_IMPLEMENTATION/THREAT_MODEL.md`
- **Phase 1 Implementation**: Commit d83d7fd (Core security primitives)
- **Related Pattern**: Unix file descriptor model (container vs. content separation)

---

## Approval

**Proposed By**: Security code review (2025-10-25)
**Reviewed By**: [To be filled]
**Approved By**: [To be filled]
**Implementation PR**: [To be created]

---

## Appendix: Security Properties Table

| Property | Before ADR-002-A | After ADR-002-A | Enforcement |
|----------|------------------|-----------------|-------------|
| Classification immutability | ✅ Frozen dataclass | ✅ Frozen dataclass | Technical |
| Prevent downgrade | ✅ max() operation | ✅ max() operation | Technical |
| Runtime access validation | ✅ validate_access_by | ✅ validate_access_by | Technical |
| **Prevent forgotten uplifting** | ⚠️ Documentation | **✅ No constructor** | **Technical** |
| **Prevent classification laundering** | **❌ Certification** | **✅ Constructor blocked** | **Technical** |
| Prevent malicious get_security_level() | ❌ Certification | ❌ Certification | Certification |
| Data mutation clarity | ⚠️ Ambiguous | ✅ Explicit | Documentation |

**Key**: ❌ Not protected | ⚠️ Weak protection | ✅ Strong protection
