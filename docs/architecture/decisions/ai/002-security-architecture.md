# ADR 002 – Multi-Level Security Enforcement (LITE)

## Status

Accepted (2025-10-23)

## Context

Elspeth handles classified data (PSPF UNOFFICIAL→SECRET, HIPAA, PCI-DSS). Traditional access control checks clearance at consumption time - too late if data is already in memory. Need fail-fast mechanism.

**Attack Without Fail-Fast**: SECRET datasource + UNOFFICIAL sink → data retrieved into memory → clearance check fails at write time → SECRET data leaked via memory dumps/logs.

**With Fail-Fast**: `operating_level = MIN(SECRET, UNOFFICIAL) = UNOFFICIAL` → datasource validates "Can I operate at UNOFFICIAL?" → NO (insufficient clearance) → **aborts BEFORE data retrieval**.

## Decision: Two-Layer MLS Model

### Layer 1: Plugin Clearance (Bell-LaPadula "No Read Up")

1. **Declarations**: All plugins declare `security_level` (UNOFFICIAL|OFFICIAL|OFFICIAL:SENSITIVE|PROTECTED|SECRET)
2. **Operating Level**: `operating_level = MIN(all component clearances)` computed at pipeline construction
3. **Insufficient Clearance Prevention**: Components with clearance LOWER than operating_level refuse to run
4. **Trusted Downgrade**: Components with clearance HIGHER than operating_level CAN operate (trusted to filter/downgrade)
5. **Fail-Fast**: Abort before data retrieval if any component has insufficient clearance

### Layer 2: Data Classification (Bell-LaPadula "No Write Down")

- **Enforcement**: `SecureDataFrame` immutability (frozen dataclass) - see ADR-002-A
- **Rule**: Data tagged SECRET CANNOT be downgraded to UNOFFICIAL
- **Mechanism**: No downgrade API exists, only `with_uplifted_security_level()`

### Architectural Split (CRITICAL CONCEPT)

**"No Write Down" (Data)** - ADR-002-A:

- Controls: `SecureDataFrame` objects
- Enforcement: Immutable classification (no downgrade API)
- Violation: SECRET data → UNOFFICIAL sink = TypeError

**"No Read Up" (Plugin)** - ADR-002/004:

- Controls: Plugin operations
- Enforcement: `BasePlugin.validate_can_operate_at_level()`
- Violation: UNOFFICIAL plugin at SECRET level = `SecurityValidationError`

**"Trusted Downgrade" (Plugin Flexibility)** - ADR-002/005:

- Enables: SECRET plugin CAN operate at UNOFFICIAL (if `allow_downgrade=True`)
- Trust: Certified plugins filter data appropriately
- Enforcement: Certification + audit, NOT runtime validation

### Why SECRET Datasource → UNOFFICIAL Sink is Valid

**Pipeline**: SECRET datasource, UNOFFICIAL sink

1. Compute: `operating_level = MIN(SECRET, UNOFFICIAL) = UNOFFICIAL`
2. Datasource validates: "Can I operate at UNOFFICIAL?" → YES (trusted downgrade)
3. Datasource operates at UNOFFICIAL → produces `SecureDataFrame(..., UNOFFICIAL)`
4. UNOFFICIAL sink receives UNOFFICIAL data → ✅ Valid

**Key**: SECRET datasource does NOT produce SECRET data at UNOFFICIAL operating level. Filtering responsibility validated through certification.

### Asymmetry Summary

```
Data Classification (Layer 1):
  UNOFFICIAL → OFFICIAL → SECRET  (can only increase)
  
Plugin Operation (Layer 2):
  SECRET → OFFICIAL → UNOFFICIAL  (can decrease if allow_downgrade=True)
```

**Forbidden**:

- ❌ UNOFFICIAL plugin at SECRET level (insufficient clearance)
- ❌ SECRET SecureDataFrame downgraded to UNOFFICIAL (no API)

## API: get_effective_level()

**Purpose**: Return pipeline operating level (≤ plugin's security_level)

**Implementation**:

```python
@final
def get_effective_level(self) -> SecurityLevel:
    if self.plugin_context.operating_level is None:
        raise RuntimeError(
            f"{self.plugin_context.plugin_name}: operating_level not set. "
            "This is a programming error - validate_can_operate_at_level() "
            "must be called before get_effective_level()."
        )
    return self.plugin_context.operating_level
```

**Fail-Loud**:

- Raises `RuntimeError` if `operating_level` is `None`
- NO fallback to `security_level` (forbidden graceful degradation)
- Catches programming errors early (using before validation)

### Valid Use Cases

✅ **Datasource filtering** (SECRET Azure filters to UNOFFICIAL blobs at UNOFFICIAL level)
✅ **Audit logging** (record effective level for compliance)
✅ **Performance optimization** (reduce encryption at lower levels)

### Invalid Use Cases (FORBIDDEN)

❌ **Data classification** (use content-based classification, not operating level)
❌ **Skipping validation** (all data must validate regardless of level)
❌ **Security decisions** (use `security_level`, not `get_effective_level()`)

## Certification Requirements

Plugins using `get_effective_level()` must demonstrate:

1. **Filtering Correctness**: Filters out higher-classified data when operating below declared level
2. **Classification Accuracy**: Tags data at correct level based on content, not operating level
3. **Audit Trail**: Logs effective level

**Test Pattern**:

```python
def test_datasource_filters_at_lower_level():
    datasource = SecretAzureDatasource(
        security_level=SecurityLevel.SECRET,
        allow_downgrade=True,
    )
    datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
    context = PluginContext(..., operating_level=SecurityLevel.UNOFFICIAL)
    datasource.plugin_context = context
    
    result = datasource.load_data()
    
    assert result.classification == SecurityLevel.UNOFFICIAL
    assert datasource.get_effective_level() == SecurityLevel.UNOFFICIAL
```

## Implementation Details

- `operating_level` defaults to `None` (pre-validation)
- `PluginContext` is frozen (immutable)
- `get_effective_level()` is `@final` (no override)
- Operating level ≤ declared security level (guaranteed)

## Related

ADR-001 (Philosophy), ADR-002-A (SecureDataFrame), ADR-004 (BasePlugin), ADR-005 (Plugin registry)

---
**Last Updated**: 2025-10-26
