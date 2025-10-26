# ADR 005 – Frozen Plugin Capability (Strict Level Enforcement) (LITE)

## Status

**Accepted** (2025-10-26) - **Implemented** (2025-10-26)

## Context

ADR-002 establishes **trusted downgrade as default**: plugins with HIGHER clearance can operate at LOWER levels (e.g., SECRET datasource operating at OFFICIAL by filtering).

However, some scenarios require **strict level enforcement** where plugins refuse ALL operations below their declared level:

1. **Dedicated Classification Domains**: Infrastructure physically/logically separated by level (SECRET-only enclaves)
2. **Regulatory Mandates**: Explicit per-level certification without cross-level operation
3. **High-Assurance Systems**: Environments where filtering trust insufficient (air-gapped networks)
4. **Organizational Policy**: SECRET datasources NEVER participate in non-SECRET pipelines

Currently, `validate_can_operate_at_level()` is sealed (`@final` + `__init_subclass__`) and CANNOT be overridden, making strict enforcement impossible without framework changes.

## Decision: Configuration-Driven Frozen Capability

Add **mandatory `allow_downgrade: bool` parameter** to `BasePlugin.__init__()`:

- Maintains sealed method security (no override attack surface)
- Provides explicit, auditable configuration
- **Requires explicit security choice** (no default - security decisions must be intentional)
- ⚠️ **Breaking change**: All plugins MUST declare `allow_downgrade=True` or `False`

### Bell-LaPadula Directionality: Data vs Plugin (CRITICAL)

**Data and plugin operations move in OPPOSITE directions**:

**Data Classifications (Can Only INCREASE)**:

- UNOFFICIAL → OFFICIAL → SECRET (via `with_uplifted_security_level()`)
- SECRET **CANNOT** downgrade to OFFICIAL/UNOFFICIAL (Bell-LaPadula "no write down")
- Classification increases are EXPLICIT and AUDITED (never implicit)

**Plugin Operations (Can Only DECREASE - if allow_downgrade=True)**:

- SECRET plugin **CAN** operate at OFFICIAL/UNOFFICIAL (trusted downgrade if allow_downgrade=True)
- UNOFFICIAL plugin **CANNOT** operate at SECRET (insufficient clearance - "no read up")
- Operation decreases require `allow_downgrade=True` (frozen plugins reject ALL downgrade)

**Asymmetry**:

```
Data:    UNOFFICIAL → OFFICIAL → SECRET  (can only increase)
Plugin:  SECRET → OFFICIAL → UNOFFICIAL  (can only decrease)
```

**Forbidden**:

- ❌ UNOFFICIAL plugin at SECRET level (insufficient clearance)
- ❌ SECRET data downgrading to UNOFFICIAL (no write down)
- ❌ Frozen plugin (allow_downgrade=False) operating below clearance

**Allowed**:

- ✅ SECRET plugin at UNOFFICIAL level (if allow_downgrade=True) - trusted to filter
- ✅ UNOFFICIAL data uplifted to SECRET (explicit via uplift method)
- ✅ Frozen plugin at EXACT declared level only

## Implementation

```python
class BasePlugin(ABC):
    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,  # MANDATORY - no default
        **kwargs: object
    ) -> None:
        """Initialize with mandatory security level and downgrade policy.
        
        Args:
            security_level: Plugin's clearance (MANDATORY keyword-only).
            allow_downgrade: Whether plugin can operate at lower levels (MANDATORY - no default).
                - True: Trusted downgrade - plugin can filter to lower levels
                - False: Frozen plugin - must operate at exact declared level
        
        Raises:
            ValueError: If security_level is None.
            TypeError: If allow_downgrade not provided (explicit choice required).
        """
        if security_level is None:
            raise ValueError(f"{type(self).__name__}: security_level cannot be None")
        
        self._security_level = security_level
        self._allow_downgrade = allow_downgrade
        super().__init__(**kwargs)
    
    @property
    def allow_downgrade(self) -> bool:
        """Read-only property for downgrade permission."""
        return self._allow_downgrade
    
    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate plugin can operate at pipeline level (SEALED).
        
        Validation Logic:
            1. Check insufficient clearance: operating_level > security_level → REJECT (always)
            2. Check frozen downgrade: operating_level < security_level AND not allow_downgrade → REJECT
            3. Otherwise: ALLOW (exact match or trusted downgrade)
        """
        # Check 1: Insufficient clearance (Bell-LaPadula "no read up")
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name}. Insufficient clearance."
            )
        
        # Check 2: Frozen plugin downgrade rejection
        if operating_level < self._security_level and not self._allow_downgrade:
            raise SecurityValidationError(
                f"{type(self).__name__} is frozen at {self._security_level.name} "
                f"(allow_downgrade=False). Cannot operate at {operating_level.name}."
            )
        
        # Check 3: Valid (exact match or trusted downgrade)
```

## Usage Examples

**Trusted Downgrade (Most Common)**:

```python
class AzureDataSource(BasePlugin, DataSource):
    def __init__(self, **kwargs):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True  # ← Explicit
        )
    
    def load_data(self, context: PluginContext) -> SecureDataFrame:
        effective = self.get_effective_level()
        # Filter blobs based on effective level
        if effective == SecurityLevel.OFFICIAL:
            blobs = [b for b in blobs if b.classification <= SecurityLevel.OFFICIAL]
        return SecureDataFrame.create_from_datasource(data, effective)
```

**Frozen Plugin (Strict Enforcement)**:

```python
class DedicatedSecretDataSource(BasePlugin, DataSource):
    def __init__(self, **kwargs):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False  # ← Frozen
        )
    
    def load_data(self, context: PluginContext) -> SecureDataFrame:
        # Only participates in SECRET pipelines
        # No filtering needed - all data is SECRET
        return SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)
```

## Behavior Matrix

| Plugin | Operating Level | allow_downgrade | Result |
|--------|----------------|-----------------|--------|
| SECRET | SECRET | True/False | ✅ ALLOW (exact match) |
| SECRET | OFFICIAL | True | ✅ ALLOW (trusted downgrade) |
| SECRET | OFFICIAL | False | ❌ REJECT (frozen, no downgrade) |
| SECRET | PROTECTED | True/False | ❌ REJECT (insufficient clearance) |
| OFFICIAL | UNOFFICIAL | True | ✅ ALLOW (trusted downgrade) |
| OFFICIAL | UNOFFICIAL | False | ❌ REJECT (frozen, no downgrade) |

## Test Coverage

**Unit Tests** (`test_baseplugin_frozen.py`):

```python
def test_frozen_exact_match():
    """Frozen plugin accepts exact level match."""
    plugin = MockPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
    plugin.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK

def test_frozen_downgrade_rejected():
    """Frozen plugin rejects lower level."""
    plugin = MockPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
    with pytest.raises(SecurityValidationError) as exc:
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)
    assert "frozen at SECRET" in str(exc.value)
```

**Integration Tests** (additions to `test_adr002_suite_integration.py`):

```python
def test_frozen_datasource_rejects_lower_sink():
    """Frozen datasource aborts when sink has lower clearance."""
    datasource = create_frozen_datasource(SecurityLevel.SECRET)
    sink = create_sink(SecurityLevel.OFFICIAL)
    
    suite = ExperimentSuite(datasource=datasource, sinks=[sink])
    
    # operating_level = min(SECRET frozen, OFFICIAL) = OFFICIAL
    # Frozen datasource: OFFICIAL < SECRET and not allow_downgrade → REJECT
    with pytest.raises(SecurityValidationError):
        suite.run()
```

## Implementation Timeline

**Phase 1: Core** (1-2 hours)

- Update `BasePlugin.__init__()` with `allow_downgrade`
- Add property and validation logic

**Phase 2: Tests** (2-3 hours)

- Unit tests for frozen behavior
- Integration tests
- 100% coverage on frozen paths

**Phase 3: Docs** (1-2 hours)

- Update ADR-002, ADR-004
- Plugin authoring guide

**Phase 4: Verification** (30 min)

- Full test suite, type checking

**Total: 5-8 hours**

## Consequences

**Positive**:

- ✅ Strict enforcement for dedicated environments
- ✅ Explicit security choices (no implicit defaults)
- ✅ Maintains sealed method security
- ✅ Auditable configuration

**Negative**:

- ⚠️ Breaking change: All plugins must declare `allow_downgrade`
- ⚠️ More verbose plugin construction

## Related

ADR-002 (MLS trusted downgrade), ADR-004 (BasePlugin sealed methods)

---
**Last Updated**: 2025-10-26
**Effort**: 5-8 hours
