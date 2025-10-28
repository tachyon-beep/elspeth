# ADR 002-A – Trusted Container Model for SecureDataFrame (LITE)

## Status

**Accepted & IMPLEMENTED** (2025-10-25, impl 2025-10-27) - Extends ADR-002

## Context

ADR-002 Phase 1 introduced `SecureDataFrame` with immutable classification and `with_uplifted_security_level()`. However, **classification laundering vulnerability exists**: nothing prevents plugins from calling `SecureDataFrame(data, lower_level)` directly, bypassing uplifting.

**Attack Scenario**:

```python
def process(self, input_data: SecureDataFrame) -> SecureDataFrame:
    # Input: SECRET data
    result = transform(input_data.data)
    # ❌ ATTACK: Create "fresh" frame claiming OFFICIAL
    return SecureDataFrame(result, SecurityLevel.OFFICIAL)
```

Plugin truthfully reports clearance (passes start-time validation) but lies about output data lineage (SECRET → mislabeled as OFFICIAL). Current defense relies on certification reviewing every transformation (high burden).

## Decision: Trusted Container Model

Separates classification metadata (immutable, trusted) from data content (mutable, transformed).

**Bell-LaPadula Note**: This ADR covers **data classification** (can only INCREASE via uplift). For **plugin operation** (can DECREASE via trusted downgrade), see ADR-002/ADR-005. Data and plugin operations move in OPPOSITE directions.

### Implementation

1. **Datasource-only creation**: Only datasources can create instances via `create_from_datasource()` factory. Direct construction raises `SecurityValidationError`.

2. **Container immutability**: Classification metadata frozen (existing).

3. **Content mutability**: Data content (`.data`) is explicitly mutable for in-place transforms.

4. **Uplifting-only modification**: `with_uplifted_security_level()` enforces upward-only via `max()`.

### Constructor Protection (Fail-Closed)

`__post_init__` validates caller identity via stack inspection:

```python
def __post_init__(self) -> None:
    # Allow datasource factory
    if object.__getattribute__(self, '_created_by_datasource'):
        return
    
    # SECURITY: Fail-closed when stack inspection unavailable
    frame = inspect.currentframe()
    if frame is None:
        raise SecurityValidationError(
            "Cannot verify caller identity - stack inspection unavailable. "
            "SecureDataFrame creation blocked."
        )
    
    # Walk stack to find trusted methods (with_uplifted_security_level, with_new_data)
    # Verify caller's 'self' is SecureDataFrame instance (prevents spoofing)
    # Block all other attempts
```

### Factory Methods

**Datasource creation**:

```python
@classmethod
def create_from_datasource(cls, data: pd.DataFrame, 
                          classification: SecurityLevel) -> "SecureDataFrame":
    """Create initial classified frame (datasources only)."""
    # Bypass __post_init__ validation
```

**Plugin new data generation**:

```python
def with_new_data(self, new_data: pd.DataFrame) -> "SecureDataFrame":
    """Create frame with different data, preserving classification."""
    # Used when plugin generates entirely new DataFrame
```

### Supported Plugin Patterns

✅ **Pattern 1: In-place mutation** (recommended)

```python
def process(self, frame: SecureDataFrame) -> SecureDataFrame:
    frame.data['processed'] = transform(frame.data['input'])
    return frame.with_uplifted_security_level(self.get_security_level())
```

✅ **Pattern 2: New data generation**

```python
def process(self, frame: SecureDataFrame) -> SecureDataFrame:
    new_df = self.llm.generate(...)
    return frame.with_new_data(new_df).with_uplifted_security_level(
        self.get_security_level()
    )
```

❌ **Anti-pattern: Direct creation** (blocked)

```python
return SecureDataFrame(new_data, SecurityLevel.OFFICIAL)  # SecurityValidationError
```

## Interaction with Frozen Plugins (ADR-002/005)

**Two Independent Layers**:

1. **Clearance validation** (ADR-002): Can plugin participate? (frozen = must operate at exact level)
2. **Classification management** (ADR-002A): How track data classification? (container model applies to ALL)

Frozen plugins MUST use factory method:

```python
def load_data(self, context: PluginContext) -> SecureDataFrame:
    # ✅ CORRECT
    return SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)
    
    # ❌ WRONG: Blocked by container model
    # return SecureDataFrame(data, SecurityLevel.SECRET)
```

**Key**: Freezing affects WHEN plugins run (pipeline construction), not HOW they manage classification (runtime).

## Consequences

### Benefits

- **Classification laundering prevented**: Technical enforcement (not certification-dependent)
- **Reduced certification burden**: ~70% reduction - only verify `get_security_level()` honesty, not every transformation
- **Explicit mutability**: `.data` mutation is intended behavior
- **Stronger defense-in-depth**: 4 layers (start-time, constructor, runtime, certification)

### Limitations

- **Shared references**: Multiple frames may share same DataFrame (mutations visible across all)
- **Stack inspection overhead**: ~1-5μs per creation (negligible)
- **Datasource migration**: ~5-10 datasources need one-line change to factory method
- **Does not prevent T2**: Malicious plugins can still lie about `get_security_level()` (certification continues)

## Implementation Impact

- Core: `secure_data.py` updated with `__post_init__`, factories
- Datasources: ~5-10 files updated to factory method
- Tests: 5 new security tests
- Docs: Plugin guide updated with lifecycle patterns
- Threat model: T4 updated to technical enforcement

## Related

ADR-002 (MLS), ADR-005 (Plugin registry), `ADR002_IMPLEMENTATION/THREAT_MODEL.md`

---
**Last Updated**: 2025-10-25
