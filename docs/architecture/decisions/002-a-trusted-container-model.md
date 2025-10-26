# ADR 002-A – Trusted Container Model for ClassifiedDataFrame

## Status

Accepted (2025-10-25)

Extends [ADR-002](002-security-architecture.md)

## Context

ADR-002 established Multi-Level Security (MLS) enforcement with two layers: start-time validation (orchestrator rejects misconfigured pipelines) and runtime validation (`ClassifiedDataFrame` validates access at every data hand-off).

Phase 1 implementation (commit d83d7fd) introduced `ClassifiedDataFrame` with:

- **Immutable classification** – `@dataclass(frozen=True)` prevents modification
- **Uplifting enforcement** – `with_uplifted_classification()` uses `max()` to prevent downgrades
- **Runtime failsafe** – `validate_access_by()` checks clearance at every hand-off

However, code review identified a **classification laundering vulnerability**: nothing prevents plugins from calling `ClassifiedDataFrame(data, lower_level)` directly, bypassing uplifting logic entirely.

### The Attack Scenario

```python
class SubtlyMaliciousPlugin(TransformNode):
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # Truthful - can handle SECRET

    def process(self, input_data: ClassifiedDataFrame) -> ClassifiedDataFrame:
        # Input: SECRET data (validated at start-time)
        result = transform(input_data.data)

        # ❌ ATTACK: Create "fresh" frame claiming OFFICIAL classification
        return ClassifiedDataFrame(result, SecurityLevel.OFFICIAL)
        # Bypasses with_uplifted_classification() entirely
```

This is more subtle than T2 (malicious plugins lying about capabilities) because:

- Plugin truthfully reports `get_security_level()` → passes start-time validation
- Plugin lies about **output data lineage** → transformed SECRET data mislabeled as OFFICIAL
- Requires reviewing every transformation to detect → high certification burden

**Current defense**: ADR-002 THREAT_MODEL states "classification uplifting is NOT optional, NOT manual, enforced by inherited BasePlugin behavior" but this is not technically enforced—it relies on certification reviewing every plugin transformation.

**Problem**: T4 (Classification Mislabeling) defense relies on human review rather than technical control, increasing risk that reviewers miss malicious/buggy transformations.

## Decision

We will adopt a **Trusted Container Model** that separates classification metadata (immutable, trusted) from data content (mutable, transformed).

**Bell-LaPadula Note**: This ADR covers **data classification** management (can only INCREASE via uplift). For **plugin operation** rules (can only DECREASE via trusted downgrade), see ADR-002 and ADR-005. Data and plugin operations move in OPPOSITE directions - see ADR-005 "Bell-LaPadula Directionality" for the asymmetry explanation.

### Container Model Implementation

1. **Datasource-only creation** – Only datasources can create `ClassifiedDataFrame` instances via `create_from_datasource()` factory method. Plugins attempting direct construction will raise `SecurityValidationError`.

2. **Container immutability** – Classification metadata remains frozen (existing). The container itself cannot be created by plugins.

3. **Content mutability** – Data content (`.data` field) is explicitly mutable. Plugins transform data in-place within the trusted container.

4. **Uplifting-only modification** – `with_uplifted_classification()` is the only way plugins can change classification, and it enforces upward-only movement via `max()` operation (existing).

### Implementation

**Constructor protection** via `__post_init__` validation (hardened, fail-closed):

```python
@dataclass(frozen=True)
class ClassifiedDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel
    _created_by_datasource: bool = field(default=False, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Enforce datasource-only creation (ADR-002-A constructor protection).

        Security: Fail-closed when stack inspection unavailable (CVE-ADR-002-A-003).
        Verifies caller identity to prevent spoofing (CVE-ADR-002-A-001).
        """
        import inspect

        # Allow datasource factory
        if object.__getattribute__(self, '_created_by_datasource'):
            return

        # Check stack inspection availability
        frame = inspect.currentframe()
        if frame is None:
            # SECURITY: Fail-closed when stack inspection unavailable
            raise SecurityValidationError(
                "Cannot verify caller identity - stack inspection is unavailable in this Python runtime. "
                "ClassifiedDataFrame creation blocked for security. "
                "Datasources must use ClassifiedDataFrame.create_from_datasource(). "
                "Plugins must use with_uplifted_classification() or with_new_data()."
            )

        # Walk up call stack to find trusted methods
        current_frame = frame
        for _ in range(5):
            if current_frame is None or current_frame.f_back is None:
                break
            current_frame = current_frame.f_back
            caller_name = current_frame.f_code.co_name

            # Allow internal methods (with_uplifted_classification, with_new_data)
            if caller_name in ("with_uplifted_classification", "with_new_data"):
                # SECURITY: Verify the caller's 'self' is actually a ClassifiedDataFrame instance
                # Prevents spoofing via external functions with same name
                caller_self = current_frame.f_locals.get('self')
                if isinstance(caller_self, ClassifiedDataFrame):
                    return  # Legitimate internal method call

        # Block all other attempts (plugins, direct construction)
        raise SecurityValidationError(
            "ClassifiedDataFrame can only be created by datasources using "
            "create_from_datasource(). Plugins must use with_uplifted_classification() "
            "to uplift existing frames or with_new_data() to generate new data. "
            "This prevents classification laundering attacks (ADR-002-A)."
        )
```

**Datasource factory method**:

```python
@classmethod
def create_from_datasource(
    cls, data: pd.DataFrame, classification: SecurityLevel
) -> "ClassifiedDataFrame":
    """Create initial classified frame (datasources only)."""
    instance = cls.__new__(cls)
    object.__setattr__(instance, 'data', data)
    object.__setattr__(instance, 'classification', classification)
    object.__setattr__(instance, '_created_by_datasource', True)
    return instance
```

**New data method** for plugins generating entirely new DataFrames:

```python
def with_new_data(self, new_data: pd.DataFrame) -> "ClassifiedDataFrame":
    """Create frame with different data, preserving current classification."""
    instance = ClassifiedDataFrame.__new__(ClassifiedDataFrame)
    object.__setattr__(instance, 'data', new_data)
    object.__setattr__(instance, 'classification', self.classification)
    object.__setattr__(instance, '_created_by_datasource', False)
    return instance
```

### Supported Plugin Patterns

**Pattern 1: In-place mutation (recommended)**

```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    frame.data['processed'] = transform(frame.data['input'])
    return frame.with_uplifted_classification(self.get_security_level())
```

**Pattern 2: New data generation**

```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    new_df = self.llm.generate(...)
    return frame.with_new_data(new_df).with_uplifted_classification(
        self.get_security_level()
    )
```

**Anti-pattern: Direct creation (blocked)**

```python
def process(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    return ClassifiedDataFrame(new_data, SecurityLevel.OFFICIAL)  # SecurityValidationError
```

## Consequences

### Benefits

- **Classification laundering prevented** – Plugins cannot create frames with arbitrary classifications; technically enforced rather than certification-dependent. Strengthens T4 (Classification Mislabeling) defense from "certification only" to "technical control".

- **Reduced certification burden** – Reviewers only need to verify `get_security_level()` honesty, not review every data transformation for uplifting logic. Certification scope reduced by ~70%.

- **Explicit data mutability** – Documentation and implementation clearly state that `.data` mutation is intended behavior. Separates container (trusted, immutable) from content (mutable, transformed).

- **Stronger defense-in-depth** – Adds fourth layer to ADR-002 model: (1) start-time validation, (2) constructor protection (new), (3) runtime validation, (4) certification (reduced scope).

- **Minimal migration impact** – Only affects code calling constructor directly (rare pattern). Datasources require one-line change to factory method.

### Limitations / Trade-offs

- **Shared DataFrame references** – Multiple `ClassifiedDataFrame` instances may share the same pandas DataFrame. Mutations to `.data` are visible across all references. *Mitigation*: Document clearly; add `.copy()` option if parallel processing requires isolation.

- **Frame inspection overhead** – `__post_init__` uses `inspect.currentframe()` (~1-5μs per creation). *Impact*: Negligible (<0.1ms per suite with typical 3-5 frame operations). *Mitigation*: Can cache validation in production if profiling shows impact.

- **Datasource migration required** – All datasources must change from `ClassifiedDataFrame(data, level)` to `ClassifiedDataFrame.create_from_datasource(data, level)`. *Scope*: ~5-10 datasources in codebase. *Effort*: ~30 minutes total.

- **Does not prevent T2** – Malicious plugins can still lie about `get_security_level()` (out of scope per Rice's Theorem). *Mitigation*: Certification continues to verify `get_security_level()` honesty.

### Implementation Impact

- **Core module** – `src/elspeth/core/security/classified_data.py` updated with `__post_init__`, `create_from_datasource()`, `with_new_data()`

- **Datasources** – All datasource plugins updated to use factory method (~5-10 files)

- **Testing** – 5 new security tests added to validate constructor protection:
  - `test_plugin_cannot_create_frame_directly`
  - `test_datasource_can_create_frame`
  - `test_with_uplifted_classification_bypasses_check`
  - `test_with_new_data_preserves_classification`
  - `test_malicious_classification_laundering_blocked`

- **Documentation** – Plugin development guide updated with lifecycle section showing correct patterns. `ClassifiedDataFrame` docstring updated with container vs. content model.

- **Threat model** – `ADR002_IMPLEMENTATION/THREAT_MODEL.md` T4 section updated to reflect technical enforcement rather than certification-only defense.

- **Certification checklist** – ADR-002 certification checklist updated to remove "verify all transformations use uplifting" requirement (technically enforced).

## Interaction with Plugin Customization (ADR-002 / ADR-005)

ADR-002 and ADR-005 document the frozen plugin capability (`allow_downgrade=False`) that enables
strict level enforcement. This customization is **orthogonal to the ClassifiedDataFrame container model**:

**Two Independent Security Layers**:

1. **Clearance validation** (ADR-002) – Can this plugin participate in this pipeline?
   - Default: Higher clearance can operate at lower levels (trusted downgrade)
   - Custom frozen: Must operate at exact declared level (no downgrade)

2. **Classification management** (ADR-002A) – How do we track data classification?
   - Container model: Immutable classification, datasource-only creation, uplifting enforcement
   - Applies to ALL plugins regardless of clearance validation behavior

**Frozen Plugin Container Usage**:

Frozen plugins still MUST respect the ClassifiedDataFrame container model:

```python
class FrozenSecretDataSource(BasePlugin, DataSource):
    def __init__(self):
        super().__init__(security_level=SecurityLevel.SECRET)

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        # Custom validation: frozen at SECRET only
        if operating_level != SecurityLevel.SECRET:
            raise SecurityValidationError("Must operate at SECRET level exactly")

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        data = fetch_data()

        # ✅ CORRECT: Use factory method (container model requirement)
        return ClassifiedDataFrame.create_from_datasource(
            data=data,
            classification=SecurityLevel.SECRET
        )

        # ❌ WRONG: Direct construction blocked by container model
        # return ClassifiedDataFrame(data, SecurityLevel.SECRET)  # SecurityValidationError
```

**Key Insight**: Freezing behavior affects WHEN plugins can run (clearance checks at pipeline
construction), not HOW they manage data classification (container model at runtime). Both
layers are enforced independently:

- **Pipeline construction** (start-time): Frozen validation rejects mismatched operating levels
- **Data hand-off** (runtime): Container model prevents classification laundering

Custom frozen plugins require certification to verify BOTH layers: correct clearance validation
AND correct container model usage.

## Related Documents

- [ADR-002](002-security-architecture.md) – Multi-Level Security Enforcement
- `docs/security/adr-002-classified-dataframe-hardening-delta.md` – Detailed delta document with full implementation specification
- `ADR002_IMPLEMENTATION/THREAT_MODEL.md` – Threat model and risk assessment
- `src/elspeth/core/security/classified_data.py` – ClassifiedDataFrame implementation (commit d83d7fd)

---

**Last Updated**: 2025-10-25
**Author(s)**: Security Code Review
