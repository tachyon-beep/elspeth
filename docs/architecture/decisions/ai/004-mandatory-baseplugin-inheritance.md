# ADR 004 – Mandatory BasePlugin Inheritance (LITE)

## Status

**IMPLEMENTED** (2025-10-27) - Sprints 1-2

## TL;DR - "Security Bones" Design

BasePlugin changes from **Protocol** (structural typing) to **ABC** (nominal typing) with **concrete security enforcement**:

```python
class BasePlugin(ABC):
    """Provides mandatory, non-overridable "security bones" for ALL plugins."""
    
    def __init_subclass__(cls, **kwargs):
        """Prevent subclasses from overriding security methods."""
        super().__init_subclass__(**kwargs)
        sealed_methods = ("get_security_level", "validate_can_operate_at_level")
        for method_name in sealed_methods:
            if method_name in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} may not override {method_name} (ADR-004). "
                    "Security enforcement is provided by BasePlugin."
                )
    
    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool, **kwargs):
        self._security_level = security_level
        self._allow_downgrade = allow_downgrade
        super().__init__(**kwargs)
    
    @property
    def security_level(self) -> SecurityLevel:
        return self._security_level  # Read-only (no setter)
    
    @property
    def allow_downgrade(self) -> bool:
        return self._allow_downgrade  # Read-only (no setter)
    
    @final
    def get_security_level(self) -> SecurityLevel:
        return self._security_level  # FINAL - cannot override
    
    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        # Bell-LaPadula "no read up"
        if operating_level > self._security_level:
            raise SecurityValidationError("Insufficient clearance")
        # Frozen plugin (ADR-005)
        if operating_level < self._security_level and not self._allow_downgrade:
            raise SecurityValidationError("Frozen plugin - cannot downgrade")
```

**Key Properties**:

- ✅ Can't instantiate without security_level and allow_downgrade (keyword-only, no defaults)
- ✅ Can't override security behavior (concrete + @final + **init_subclass**)
- ✅ Centralized validation (ONE implementation)
- ✅ Prevents accidental plugins (must explicitly inherit)

## Context

**Current State**: `BasePlugin` is a `Protocol` (structural typing) - any class with matching methods passes `isinstance()`.

**Attack Scenario**:

```python
# Helper class (NOT intended as plugin)
class SecurityLevelHelper:
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL
    
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.OFFICIAL:
            raise ValueError("Need OFFICIAL")

# ⚠️ PROBLEM: Accidental compliance
helper = SecurityLevelHelper()
isinstance(helper, BasePlugin)  # True! (Protocol accepts duck typing)

# If helper ends up in plugin list by mistake:
runner = ExperimentRunner(
    datasource=secret_datasource,  # SECRET
    row_plugins=[helper],  # UNOFFICIAL (accident!)
)

# Operating envelope = MIN(SECRET, UNOFFICIAL) = UNOFFICIAL 💥
# Secret data processed at UNOFFICIAL level!
```

**Why This Matters**:

1. Silent security downgrade (no warning)
2. No developer intent (author never meant plugin participation)
3. Hard to debug
4. Violates least surprise

## Decision: Convert to ABC with Concrete Security Enforcement

**Chosen Solution**: Replace `Protocol` with `ABC` that provides **concrete, non-overridable** security enforcement. Subclasses **inherit** security behavior, they don't implement it.

**Three Enforcement Layers**:

1. **Keyword-only args** (Python): Can't instantiate without security_level, allow_downgrade
2. **@final decorator** (MyPy): Static check prevents method override
3. ****init_subclass**** (Runtime): Dynamic check prevents method override

### Why "Security Bones" Pattern

**Traditional ABC** (plugins implement security):

```python
class BasePlugin(ABC):
    @abstractmethod
    def get_security_level(self) -> SecurityLevel: ...
    # ❌ Every plugin reimplements security logic
```

**Security Bones** (BasePlugin implements security):

```python
class BasePlugin(ABC):
    def __init__(self, *, security_level: SecurityLevel, ...):
        self._security_level = security_level
    
    @final
    def get_security_level(self) -> SecurityLevel:
        return self._security_level
    # ✅ ONE implementation, all plugins inherit
```

**Benefits**:

- Plugins can't accidentally implement wrong security logic
- Centralized enforcement (single source of truth)
- Can't bypass security by overriding methods

## Migration Impact

**Before (Protocol)**:

```python
class SecretDatasource:  # No inheritance
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET
```

**After (ABC with Security Bones)**:

```python
class SecretDatasource(BasePlugin):  # ← Add inheritance
    def __init__(self, **kwargs):
        super().__init__(
            security_level=SecurityLevel.SECRET,  # ← Declare security
            allow_downgrade=True,                  # ← Declare policy
            **kwargs
        )
    # ✅ get_security_level() inherited from BasePlugin
    # ✅ validate_can_operate_at_level() inherited from BasePlugin
```

**Key Change**: Plugins declare security in `__init__()`, inherit enforcement from BasePlugin.

## Implementation Plan

**Phase 1: BasePlugin Conversion (30 min)**

- Convert `BasePlugin` Protocol → ABC with security bones
- Add `__init__()` with keyword-only args
- Add `@final` methods and `__init_subclass__` check

**Phase 2: Plugin Migration (15 min)**

- Update all plugins to inherit `BasePlugin`
- Move security declarations to `__init__()`
- Remove custom security method implementations

**Phase 3: Verification (10 min)**

- Run test suite
- Verify MyPy passes with `--strict`

**Total: ~1 hour**

## Consequences

**Positive**:

- ✅ Security: Prevents accidental compliance
- ✅ Clarity: Inheritance makes plugin status explicit
- ✅ Type Safety: MyPy enforces at compile time
- ✅ Auditability: Can enumerate via inheritance tree
- ✅ Centralized: ONE security implementation

**Negative**:

- ⚠️ Breaking Change: Existing code must add `(BasePlugin)`
- ⚠️ Migration: All plugins must update (acceptable pre-1.0)

## Examples

**Before (Accidental Compliance Allowed)**:

```python
helper = SecurityHelper()
isinstance(helper, BasePlugin)  # True! (Protocol)
# Helper accidentally lowers security envelope
```

**After (Explicit Required)**:

```python
helper = SecurityHelper()
isinstance(helper, BasePlugin)  # False! (ABC requires inheritance)
# Helper ignored by validation - security preserved
```

## Defense in Depth (with ADR-003)

| Layer | Mechanism | Prevents |
|-------|-----------|----------|
| **Layer 1: ADR-004** | Nominal typing (ABC) | Accidental compliance |
| **Layer 2: ADR-003** | Plugin registry | Forgetting plugin types |
| **Layer 3: ADR-003** | Test enforcement | Registry out of sync |

**Combined Effect**: Cannot accidentally be plugin + cannot forget to validate

## Related

ADR-002 (MLS), ADR-003 (Registry), ADR-005 (allow_downgrade semantics)

---
**Last Updated**: 2025-10-25
**Status**: PROPOSED
**Effort**: ~1 hour
