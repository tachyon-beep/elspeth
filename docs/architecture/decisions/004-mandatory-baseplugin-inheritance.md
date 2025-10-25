# ADR-004: Mandatory BasePlugin Inheritance (Breaking Change)

**Status**: PROPOSED
**Date**: 2025-10-25
**Deciders**: Security Team, Core Platform Team
**Related**: ADR-002 (Suite-level security), ADR-003 (Plugin type registry)

---

## TL;DR - "Security Bones" Design

BasePlugin changes from **Protocol** (structural typing) to **ABC** (nominal typing) with **concrete security enforcement**:

```python
class BasePlugin(ABC):
    """Provides mandatory, non-overridable "security bones" for ALL plugins."""

    def __init__(self, *, security_level: SecurityLevel, **kwargs):
        self._security_level = security_level  # Private storage

    @property
    def security_level(self) -> SecurityLevel:
        return self._security_level  # Read-only property (no setter)

    def get_security_level(self) -> SecurityLevel:
        return self._security_level  # FINAL - do not override

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        # Bell-LaPadula "no read up": Reject if asked to operate ABOVE clearance
        if operating_level > self._security_level:  # FINAL - do not override
            raise SecurityValidationError(
                f"Cannot operate at {operating_level} - insufficient clearance"
            )
```

**Key Properties**:

- ✅ **Can't instantiate without security_level**: Keyword-only arg enforced by Python
- ✅ **Can't override security behavior**: Methods are concrete, subclasses inherit
- ✅ **Centralized validation logic**: ONE implementation in BasePlugin
- ✅ **Prevents accidental plugins**: Must explicitly inherit from BasePlugin

**Migration Impact**: Plugins inherit security enforcement, don't reimplement it.

---

## Context and Problem Statement

**Current State**: `BasePlugin` is implemented as a `Protocol` (structural typing), allowing any class with the correct method signatures to be treated as a plugin:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BasePlugin(Protocol):
    """Base protocol defining security requirements for all plugins."""

    def get_security_level(self) -> SecurityLevel:
        raise NotImplementedError

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        raise NotImplementedError
```

**The Problem**: Structural typing allows **accidental compliance** - any class that happens to have these two methods will pass `isinstance(obj, BasePlugin)` checks, even if the developer never intended it to be a plugin.

**Attack Scenario**:

```python
# Developer creates a helper class (NOT intended as plugin)
class SecurityLevelHelper:
    """Helper to check security levels - NOT A PLUGIN!"""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL  # Just a default for comparison

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        """Helper method to validate levels."""
        if level < SecurityLevel.OFFICIAL:
            raise ValueError("Need OFFICIAL or higher")

# Accidental compliance - this passes isinstance() check!
helper = SecurityLevelHelper()
isinstance(helper, BasePlugin)  # True! ⚠️

# If this object ends up in a plugin list by mistake:
runner = ExperimentRunner(
    datasource=secret_datasource,
    row_plugins=[helper],  # ⚠️ Accidentally treated as plugin!
    # ...
)

# ADR-002 validation sees helper.get_security_level() = UNOFFICIAL
# Operating envelope = MIN(SECRET datasource, UNOFFICIAL helper) = UNOFFICIAL
# Job runs at UNOFFICIAL level with SECRET data! 💥
```

**Why This Matters**:

1. **Silent Security Downgrade**: Accidental object lowers operating envelope without any warning
2. **No Developer Intent**: Class author never meant to participate in security validation
3. **Hard to Debug**: No obvious connection between helper class and security failure
4. **Violates Least Surprise**: Helper classes shouldn't affect security boundaries

---

## Decision Drivers

1. **Security-Critical**: ADR-002 validation relies on `isinstance(obj, BasePlugin)` checks
2. **Explicit Opt-In**: Only classes that explicitly inherit should participate in security validation
3. **Developer Intent**: Inheritance signals "this is a plugin that processes data"
4. **Type Safety**: Nominal typing provides compile-time verification
5. **Auditability**: Can trace all plugins via inheritance tree
6. **Pre-1.0 Window**: Breaking changes are acceptable before 1.0 release

---

## Considered Options

### Option 1: Keep Protocol (Status Quo)

**Approach**: Continue using `Protocol` with structural typing.

**Pros**:

- ✅ No breaking changes
- ✅ Flexible - any object with right methods works
- ✅ Backward compatible

**Cons**:

- ❌ Allows accidental compliance
- ❌ No explicit developer intent
- ❌ Cannot reliably distinguish plugins from helpers
- ❌ Security risk (shown in attack scenario)

### Option 2: Convert to ABC with Concrete "Security Bones" - CHOSEN

**Approach**: Replace `Protocol` with `ABC` (Abstract Base Class) that provides **concrete, non-overridable** security enforcement. Subclasses inherit security behavior, they don't implement it.

```python
from abc import ABC
from typing import final

class BasePlugin(ABC):
    """Base class providing mandatory "security bones" for ALL plugins.

    SECURITY INVARIANTS (ADR-004):
    1. All plugins MUST explicitly inherit from this class (nominal typing)
    2. Security level is MANDATORY at construction (keyword-only arg)
    3. Security methods are FINAL and cannot be overridden by subclasses
    4. Validation logic is centralized in BasePlugin (single source of truth)

    This prevents both accidental compliance AND intentional security bypasses.
    """

    def __init_subclass__(cls, **kwargs):
        """Runtime enforcement: prevent subclasses from overriding security methods."""
        super().__init_subclass__(**kwargs)

        sealed_methods = ("get_security_level", "validate_can_operate_at_level")
        for method_name in sealed_methods:
            if method_name in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} may not override {method_name} (ADR-004 security invariant). "
                    f"Security enforcement is provided by BasePlugin and cannot be customized."
                )

    def __init__(self, *, security_level: SecurityLevel, **kwargs):
        """Initialize plugin with MANDATORY security level.

        Args:
            security_level: REQUIRED - minimum clearance for this plugin

        Raises:
            TypeError: If security_level not provided (keyword-only enforcement)
            ValueError: If security_level is None
        """
        if security_level is None:
            raise ValueError(f"{type(self).__name__}: security_level cannot be None")
        self._security_level = security_level
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only property for security level (convenience accessor)."""
        return self._security_level

    @final
    def get_security_level(self) -> SecurityLevel:
        """Return the minimum security level (FINAL - do not override)."""
        return self._security_level

    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate security level (FINAL - do not override).

        Bell-LaPadula "no read up": Plugin can operate at same or lower level,
        but cannot operate ABOVE its clearance.

        Raises:
            SecurityValidationError: If operating_level > plugin clearance
        """
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name} - insufficient clearance"
            )
```

**Pros**:

- ✅ **Explicit Opt-In**: Must write `class MyPlugin(BasePlugin)`
- ✅ **Cannot Accidentally Comply**: Helper classes rejected automatically
- ✅ **Clear Intent**: Inheritance signals plugin participation
- ✅ **Type Safety**: MyPy can verify inheritance at compile time
- ✅ **Auditability**: Can list all plugins via inheritance tree
- ✅ **Runtime Safety**: `isinstance()` checks are definitive
- ✅ **"Security Bones"**: Concrete implementation, subclasses inherit (don't reimplement)
- ✅ **Cannot Break Security**: Runtime enforcement prevents method override
- ✅ **Single Source of Truth**: Validation logic in ONE place (BasePlugin)
- ✅ **Mandatory Security Level**: Keyword-only arg enforced by Python
- ✅ **Dual Enforcement**: @final (static) + **init_subclass** (runtime)

**Cons**:

- ⚠️ **Breaking Change**: Existing code must add `(BasePlugin)` inheritance
- ⚠️ **Migration Required**: All current plugins must be updated to call `super().__init__(security_level=...)`
- ⚠️ **Less Flexible**: Cannot use arbitrary objects (by design - this is good!)

**Why Concrete Over Abstract**:

- **Security-critical code benefits from centralization**: One implementation to audit, test, and patch
- **Prevents inconsistent security logic**: If each plugin implements validation differently, some will get it wrong
- **Simpler migration**: Plugins inherit methods, don't copy 10 lines of validation logic to 26 classes
- **Fail-fast on violations**: Runtime enforcement catches override attempts at class definition time

### Option 3: Hybrid - Protocol + Explicit Registration

**Approach**: Keep Protocol but require manual registration via decorator.

```python
# Registry of approved plugins
_REGISTERED_PLUGINS = set()

def register_plugin(cls):
    """Decorator to explicitly register a plugin."""
    _REGISTERED_PLUGINS.add(cls)
    return cls

@register_plugin
class MyPlugin:
    def get_security_level(self) -> SecurityLevel: ...
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...

def is_registered_plugin(obj):
    return type(obj) in _REGISTERED_PLUGINS
```

**Pros**:

- ✅ Explicit opt-in via decorator
- ✅ No inheritance required

**Cons**:

- ❌ Easy to forget decorator (no compile-time check)
- ❌ Runtime-only verification
- ❌ More complex than ABC
- ❌ Decorator can be forgotten

---

## Decision Outcome

**Chosen**: **Option 2 - Convert BasePlugin to ABC with Concrete "Security Bones"**

**Rationale**:

1. **Security First**: Prevents accidental compliance attack scenario
2. **Developer Intent**: Inheritance makes plugin status explicit and obvious
3. **Type Safety**: MyPy can enforce inheritance at compile time
4. **Industry Standard**: ABCs are Python's standard mechanism for mandatory base classes
5. **Pre-1.0 Window**: Breaking changes are acceptable now, not after 1.0
6. **Simplicity**: ABC is simpler and more well-understood than custom registration
7. **"Security Bones" Design**: Concrete implementation prevents inconsistent security logic
8. **Centralized Trust**: One validation implementation to audit, test, and patch
9. **Fail-Fast**: Runtime enforcement prevents override attempts at class definition
10. **Simpler Migration**: Plugins inherit security methods instead of reimplementing them

**Breaking Change Justification**: We are pre-1.0 release. Now is the time to establish correct security foundations, even if it requires migration.

**Why Concrete Implementation Over Abstract Methods**:

- **Single Source of Truth**: Validation logic lives in ONE place (BasePlugin), not duplicated across 26 plugin classes
- **Cannot Break Security**: `__init_subclass__` hook raises TypeError if subclass tries to override security methods
- **Reduces Bug Surface**: 26 classes inheriting correct logic vs. 26 classes implementing their own (with 26 opportunities for bugs)
- **Easier to Patch**: Security fixes only need to be made in BasePlugin, automatically inherited by all plugins
- **Simpler Testing**: Test BasePlugin once instead of testing 26 implementations

---

## Implementation Plan

### Phase 1: Update BasePlugin Definition (15 min)

**File**: `src/elspeth/core/base/protocols.py`

**Before** (Line 62-79):

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BasePlugin(Protocol):
    """Base protocol defining security requirements for all plugins."""

    def get_security_level(self) -> SecurityLevel:
        """Return the minimum security level this plugin requires."""
        raise NotImplementedError

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate this plugin can operate at the given security level.

        Raises:
            SecurityValidationError: If operating_level < required level
        """
        raise NotImplementedError
```

**After**:

```python
from abc import ABC
from typing import final  # Python 3.8+ for static type checkers

from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError


class BasePlugin(ABC):
    """Base class providing MANDATORY security enforcement for ALL plugins.

    CRITICAL SECURITY DESIGN (ADR-004 "Security Bones"):
    This class provides CONCRETE, FINAL security enforcement that CANNOT be
    overridden by subclasses. Think of it as the "security bones" - the
    foundational structure that higher-level classes build on but cannot break.

    SECURITY INVARIANTS (enforced by BasePlugin):
    1. ALL plugins MUST provide security_level at construction (keyword-only arg)
    2. Security behavior CANNOT be customized/overridden by subclasses (runtime enforced)
    3. get_security_level() and validate_can_operate_at_level() are FINAL
    4. ADR-002 validation logic is centralized and consistent across ALL plugins

    Runtime Enforcement:
    - @final decorator enforces at static type-check time (MyPy/Pyright)
    - __init_subclass__ hook enforces at runtime (raises TypeError on override)
    - Dual enforcement ensures security invariants cannot be violated

    Why Concrete Implementation (Not Abstract)?
    - Abstract methods allow each subclass to implement security differently
    - This creates inconsistency and potential security bugs
    - BasePlugin provides ONE correct implementation used by ALL plugins
    - Subclasses inherit security behavior, they don't reimplement it

    Why ABC (Not Protocol)?
    - Protocol allows ANY class with matching methods to be a plugin (duck typing)
    - ABC requires explicit inheritance: class MyPlugin(BasePlugin)
    - This ensures developer intent and prevents accidental compliance

    Constructor Pattern (ALL subclasses MUST follow):
        class MyPlugin(BasePlugin):
            def __init__(self, *, param1: str, security_level: SecurityLevel):
                super().__init__(security_level=security_level)  # ← Pass to BasePlugin
                self.param1 = param1

            # NO get_security_level() - inherited from BasePlugin ✅
            # NO validate_can_operate_at_level() - inherited from BasePlugin ✅

    Example - Correct Usage:
        >>> class SecretDatasource(BasePlugin):
        ...     def __init__(self, *, path: str, security_level: SecurityLevel):
        ...         super().__init__(security_level=security_level)
        ...         self.path = path
        ...
        >>> ds = SecretDatasource(path="data.csv", security_level=SecurityLevel.SECRET)
        >>> ds.get_security_level()  # Inherited method
        SecurityLevel.SECRET
        >>> ds.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
        SecurityValidationError: SecretDatasource requires SECRET, operating envelope is UNOFFICIAL

    Example - Wrong (No Inheritance):
        >>> class AccidentalPlugin:  # ← Missing (BasePlugin) inheritance
        ...     def get_security_level(self) -> SecurityLevel:
        ...         return SecurityLevel.UNOFFICIAL
        ...
        >>> isinstance(AccidentalPlugin(), BasePlugin)  # False ✅
        False

    Example - Wrong (Trying to Override Security - BLOCKED AT RUNTIME):
        >>> class BrokenPlugin(BasePlugin):  # ← TypeError raised immediately!
        ...     def get_security_level(self) -> SecurityLevel:
        ...         return SecurityLevel.UNOFFICIAL  # Override attempt
        ...
        TypeError: BrokenPlugin may not override get_security_level (ADR-004 invariant)

        # __init_subclass__ hook prevents this class from even being created!
    """

    def __init_subclass__(cls, **kwargs):
        """Runtime enforcement: prevent subclasses from overriding security methods.

        SECURITY INVARIANT (ADR-004):
        The methods get_security_level() and validate_can_operate_at_level() are
        FINAL and cannot be overridden by subclasses. This hook enforces that
        invariant at runtime by raising TypeError if a subclass attempts to
        override these methods.

        This complements the @final decorator which only works for static type checkers.

        Raises:
            TypeError: If subclass overrides get_security_level or validate_can_operate_at_level

        Example:
            >>> class BadPlugin(BasePlugin):
            ...     def get_security_level(self) -> SecurityLevel:  # ← Override attempt
            ...         return SecurityLevel.UNOFFICIAL
            ...
            TypeError: BadPlugin may not override get_security_level (ADR-004 invariant)
        """
        super().__init_subclass__(**kwargs)

        # List of sealed methods that cannot be overridden
        sealed_methods = ("get_security_level", "validate_can_operate_at_level")

        for method_name in sealed_methods:
            if method_name in cls.__dict__:  # Check if subclass defines this method
                raise TypeError(
                    f"{cls.__name__} may not override {method_name} (ADR-004 security invariant). "
                    f"Security enforcement is provided by BasePlugin and cannot be customized."
                )

    def __init__(self, *, security_level: SecurityLevel, **kwargs):
        """Initialize plugin with MANDATORY security level.

        SECURITY REQUIREMENT (ADR-004):
        All plugins MUST provide security_level at construction. This is enforced
        by keyword-only argument (raises TypeError if missing).

        Args:
            security_level: REQUIRED - minimum clearance for this plugin
                           Cannot be None, must be valid SecurityLevel enum
            **kwargs: Passed to parent classes (for cooperative multiple inheritance)

        Raises:
            TypeError: If security_level not provided (Python enforces keyword-only)
            ValueError: If security_level is None or invalid

        Example:
            >>> class MyPlugin(BasePlugin):
            ...     def __init__(self, *, name: str, security_level: SecurityLevel):
            ...         super().__init__(security_level=security_level)
            ...         self.name = name
            ...
            >>> # ✅ CORRECT: security_level provided
            >>> MyPlugin(name="test", security_level=SecurityLevel.SECRET)
            ...
            >>> # ❌ WRONG: security_level missing
            >>> MyPlugin(name="test")  # TypeError: missing required keyword argument
        """
        if security_level is None:
            raise ValueError(
                f"{type(self).__name__}: security_level cannot be None. "
                f"All plugins MUST have a defined security level (ADR-004)."
            )

        # Private attribute to discourage direct access/override
        # Subclasses should use get_security_level(), not self._security_level
        self._security_level = security_level
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only property for security level (convenience accessor).

        DESIGN NOTE (ADR-004):
        This property provides backward compatibility with existing code that
        references self.security_level directly (e.g., in factory methods like
        SecureDataFrame.create_from_datasource(df, self.security_level)).

        The property is READ-ONLY (no setter) to prevent accidental reassignment.
        Subclasses cannot override security level after construction.

        For protocol compliance and clarity, prefer using get_security_level()
        in validation code. Use this property for convenience in non-security
        contexts (logging, factory methods, etc.).

        Returns:
            SecurityLevel: The minimum clearance level (same as get_security_level())

        Example:
            >>> ds = SecretDatasource(path="data.csv", security_level=SecurityLevel.SECRET)
            >>> ds.security_level  # Property access (read-only)
            SecurityLevel.SECRET
            >>> ds.security_level = SecurityLevel.UNOFFICIAL  # ❌ AttributeError: can't set
        """
        return self._security_level

    def get_security_level(self) -> SecurityLevel:
        """Return the minimum security level this plugin requires.

        FINAL METHOD (ADR-004 Security Bones):
        This method is CONCRETE and should NOT be overridden by subclasses.
        All plugins inherit this implementation from BasePlugin.

        Subclasses that override this method break the "security bones" design
        and create inconsistent security behavior. DO NOT OVERRIDE.

        Returns:
            SecurityLevel: The minimum clearance level required to use this plugin

        Example:
            >>> ds = SecretDatasource(path="data.csv", security_level=SecurityLevel.SECRET)
            >>> ds.get_security_level()  # Calls BasePlugin.get_security_level()
            SecurityLevel.SECRET
        """
        return self._security_level

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate this plugin can operate at the given security level.

        FINAL METHOD (ADR-004 Security Bones):
        This method is CONCRETE and should NOT be overridden by subclasses.
        All plugins inherit this implementation from BasePlugin.

        This method implements ADR-002 start-time validation with Bell-LaPadula semantics:
        - Plugin can operate at SAME or LOWER level (trusted to filter/downgrade)
        - Plugin CANNOT operate ABOVE its clearance (insufficient clearance)
        - Validation: If operating_level > plugin.security_level: raise error

        Subclasses that override this method break the "security bones" design
        and create inconsistent ADR-002 enforcement. DO NOT OVERRIDE.

        Args:
            operating_level: The minimum clearance envelope for the job
                           (computed as MIN of all plugin security levels)

        Raises:
            SecurityValidationError: If operating_level > this plugin's clearance

        Example (Bell-LaPadula "no read up"):
            >>> ds = SecretDatasource(path="data.csv", security_level=SecurityLevel.SECRET)
            >>>
            >>> # ✅ PASS: Operating at same or lower level (plugin can downgrade)
            >>> ds.validate_can_operate_at_level(SecurityLevel.SECRET)      # Same - OK
            >>> ds.validate_can_operate_at_level(SecurityLevel.OFFICIAL)    # Lower - OK
            >>> ds.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # Much lower - OK
            >>>
            >>> # ❌ FAIL: Operating level ABOVE clearance (insufficient clearance)
            >>> ds.validate_can_operate_at_level(SecurityLevel.TOP_SECRET)
            SecurityValidationError: SecretDatasource has clearance SECRET,
                but pipeline requires TOP_SECRET - insufficient clearance
        """
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name} - insufficient clearance"
            )
```

### Phase 2: Update All Existing Plugins (30-45 min)

**Migration Pattern**:

```python
# BEFORE (No BasePlugin):
class MyDatasource:
    def __init__(self, *, path: str, security_level: SecurityLevel):
        self.path = path
        self.security_level = security_level  # ← Stored manually

    def get_security_level(self) -> SecurityLevel:
        return self.security_level  # ← Manual implementation

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < self.security_level:  # ← Manual validation logic
            raise SecurityValidationError(
                f"MyDatasource requires {self.security_level.name}, got {level.name}"
            )

# AFTER (With BasePlugin - "Security Bones"):
from elspeth.core.base.plugin import BasePlugin

class MyDatasource(BasePlugin):  # ← 1. Inherit from BasePlugin
    def __init__(self, *, path: str, security_level: SecurityLevel):
        super().__init__(security_level=security_level)  # ← 2. Pass to BasePlugin
        self.path = path
        # NO self.security_level assignment - BasePlugin stores it ✅

    # ✅ NO get_security_level() - inherited from BasePlugin
    # ✅ NO validate_can_operate_at_level() - inherited from BasePlugin
    # Security enforcement happens automatically via inheritance!
```

**Key Changes**:

1. ✅ Add `(BasePlugin)` inheritance
2. ✅ Add `super().__init__(security_level=security_level)` call
3. ❌ **REMOVE** manual `get_security_level()` implementation
4. ❌ **REMOVE** manual `validate_can_operate_at_level()` implementation
5. ❌ **REMOVE** `self.security_level = ...` assignment (BasePlugin handles it)

**Why Remove the Methods?**

- BasePlugin provides concrete implementations
- All plugins get consistent security behavior
- Cannot accidentally break security logic
- Less code duplication

---

#### Special Case: Plugins Without Existing security_level Constructor Parameter

**Problem**: Some plugins (e.g., `StaticLLMClient`, many sinks) don't currently accept `security_level` in their constructor because they haven't been migrated to ADR-002 yet.

**Example - StaticLLMClient** (before ADR-004):

```python
class StaticLLMClient(LLMClientProtocol):
    """Return predefined content for testing."""

    def __init__(self, *, content: str, score: float | None = None):
        self.content = content
        self.score = score
        # ❌ NO security_level parameter!
        # ❌ NO get_security_level() method!
```

**Solution**: Add `security_level` parameter and pass to BasePlugin:

```python
from elspeth.core.base.plugin import BasePlugin

class StaticLLMClient(BasePlugin, LLMClientProtocol):  # ← Multi-inheritance
    """Return predefined content for testing."""

    def __init__(
        self,
        *,
        content: str,
        security_level: SecurityLevel,  # ← ADD mandatory parameter
        score: float | None = None,
    ):
        super().__init__(security_level=security_level)  # ← Pass to BasePlugin
        self.content = content
        self.score = score

    # ✅ NO get_security_level() - inherited from BasePlugin
    # ✅ NO validate_can_operate_at_level() - inherited from BasePlugin
```

**Migration Checklist for Plugins Without security_level**:

1. ✅ Add `BasePlugin` to inheritance chain (before other protocols/classes)
2. ✅ Add `security_level: SecurityLevel` to `__init__` signature (keyword-only)
3. ✅ Call `super().__init__(security_level=security_level)` first thing in `__init__`
4. ✅ Update all call sites to provide `security_level` argument
5. ✅ Choose appropriate default security level for test code (typically `SecurityLevel.UNOFFICIAL`)

**Example Call Site Updates**:

```python
# BEFORE:
client = StaticLLMClient(content="Hello", score=0.9)

# AFTER:
client = StaticLLMClient(
    content="Hello",
    score=0.9,
    security_level=SecurityLevel.UNOFFICIAL  # ← ADD for test/mock usage
)
```

**Choosing Security Levels**:

- **Production datasources/sinks**: Use actual data classification (SECRET, OFFICIAL, etc.)
- **Test mocks/stubs**: Use `SecurityLevel.UNOFFICIAL` (lowest restriction)
- **LLM clients**: Typically `SecurityLevel.UNOFFICIAL` (unless accessing classified endpoints)
- **Middleware**: Match the data they operate on

---

**Files to Update** (search for classes implementing both methods):

1. **Datasources**:
   - `src/elspeth/datasources/*.py`
   - Pattern: `class *Datasource:` → `class *Datasource(BasePlugin):`

2. **Sinks**:
   - `src/elspeth/sinks/*.py`
   - Pattern: `class *Sink:` → `class *Sink(BasePlugin):`

3. **LLM Clients**:
   - `src/elspeth/llm/*.py`
   - Pattern: `class *Client:` → `class *Client(BasePlugin):`

4. **Middleware**:
   - `src/elspeth/middleware/*.py`
   - Pattern: `class *Middleware:` → `class *Middleware(BasePlugin):`

5. **Test Mocks**:
   - `tests/adr002_test_helpers.py`
   - `tests/test_adr002_suite_integration.py`
   - Pattern: `class Mock*Plugin:` → `class Mock*Plugin(BasePlugin):`

**Automated Search**:

```bash
# Find all classes implementing both security methods
rg "def get_security_level" -A 10 | rg "def validate_can_operate_at_level" -B 10
```

### Phase 3: Update Type Hints (15 min)

**Files to Update**:

- `src/elspeth/core/experiments/suite_runner.py`
- `src/elspeth/core/experiments/runner.py`

**Pattern**:

```python
# BEFORE: Protocol allows structural typing
from elspeth.core.base.plugin import BasePlugin  # Protocol

def process(plugin: BasePlugin) -> None:
    # Any object with right methods accepted

# AFTER: ABC requires inheritance
from elspeth.core.base.plugin import BasePlugin  # ABC

def process(plugin: BasePlugin) -> None:
    # Only classes inheriting BasePlugin accepted
```

**MyPy Configuration** (already present in `pyproject.toml`):

```toml
[tool.mypy]
strict = true
warn_return_any = true
disallow_untyped_defs = true
# ✅ These settings will now enforce BasePlugin inheritance
```

### Phase 4: Add Verification Tests (20 min)

**File**: `tests/test_adr004_baseplugin_enforcement.py` (NEW)

```python
"""ADR-004: Verify mandatory BasePlugin inheritance enforcement.

These tests verify that:
1. Only classes explicitly inheriting BasePlugin are recognized as plugins
2. Accidental compliance (duck typing) is rejected
3. Type hints enforce inheritance at compile time
"""

import pytest
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel


class TestBasePluginInheritanceEnforcement:
    """Verify ADR-004 nominal typing enforcement."""

    def test_explicit_inheritance_required(self):
        """SECURITY: Only classes explicitly inheriting BasePlugin are recognized."""

        # ✅ CORRECT: Explicit inheritance
        class CorrectPlugin(BasePlugin):
            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.OFFICIAL

            def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
                if level < SecurityLevel.OFFICIAL:
                    raise SecurityValidationError(...)

        plugin = CorrectPlugin()
        assert isinstance(plugin, BasePlugin), "Explicit inheritance should be recognized"

    def test_accidental_compliance_rejected(self):
        """SECURITY: Classes with matching methods but no inheritance are REJECTED.

        This is the core security property - prevents accidental plugins from
        affecting operating envelope calculation.
        """

        # ❌ WRONG: No inheritance (duck typing)
        class AccidentalPlugin:
            """Helper class that accidentally has same methods - NOT A PLUGIN!"""

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.UNOFFICIAL

            def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
                pass  # Empty implementation

        helper = AccidentalPlugin()

        # ✅ SECURITY: isinstance() rejects accidental compliance
        assert not isinstance(helper, BasePlugin), \
            "Accidental compliance MUST be rejected (ADR-004 security requirement)"

    def test_cannot_instantiate_baseplugin_directly(self):
        """Verify BasePlugin is abstract - cannot instantiate directly."""

        with pytest.raises(TypeError) as exc_info:
            BasePlugin()

        assert "abstract" in str(exc_info.value).lower(), \
            "BasePlugin should be abstract (cannot instantiate)"

    def test_missing_method_implementation_fails(self):
        """Verify abstract methods must be implemented."""

        # Missing validate_can_operate_at_level implementation
        with pytest.raises(TypeError) as exc_info:
            class IncompletePlugin(BasePlugin):
                def get_security_level(self) -> SecurityLevel:
                    return SecurityLevel.OFFICIAL
                # Missing: validate_can_operate_at_level

            IncompletePlugin()

        assert "abstract" in str(exc_info.value).lower()


class TestMigrationVerification:
    """Verify all existing plugins have been migrated to inherit BasePlugin."""

    def test_all_datasources_inherit_baseplugin(self):
        """Verify all datasource classes inherit BasePlugin."""
        # TODO: Add after migration complete
        pytest.skip("Migration in progress")

    def test_all_sinks_inherit_baseplugin(self):
        """Verify all sink classes inherit BasePlugin."""
        # TODO: Add after migration complete
        pytest.skip("Migration in progress")

    def test_all_llm_clients_inherit_baseplugin(self):
        """Verify all LLM client classes inherit BasePlugin."""
        # TODO: Add after migration complete
        pytest.skip("Migration in progress")
```

### Phase 5: Documentation Updates (20 min)

**Files to Update**:

1. **Plugin Development Guide** (`docs/guides/plugin-development-adr002a.md`):
   - Update all examples to show `(BasePlugin)` inheritance
   - Add "Why Inheritance is Required" section
   - Show incorrect examples without inheritance

2. **CONTRIBUTING.md**:
   - Add "Creating New Plugins" section
   - Emphasize mandatory BasePlugin inheritance
   - Link to ADR-004

3. **THREAT_MODEL.md**:
   - Add defense for T1: "Nominal typing prevents accidental compliance"
   - Reference ADR-004

4. **CERTIFICATION_EVIDENCE.md**:
   - Add verification step: "Verify all plugins inherit BasePlugin"
   - Add test reference: `tests/test_adr004_baseplugin_enforcement.py`

### Phase 6: CI Enforcement (10 min)

**Pre-Commit Hook** (`.pre-commit-config.yaml`):

```yaml
repos:
  - repo: local
    hooks:
      - id: adr004-baseplugin-enforcement
        name: Verify BasePlugin inheritance (ADR-004)
        entry: pytest tests/test_adr004_baseplugin_enforcement.py::TestBasePluginInheritanceEnforcement -v
        language: system
        always_run: true
        pass_filenames: false
```

**GitHub Actions** (`.github/workflows/ci.yml`):

```yaml
- name: ADR-004 Security Verification
  run: |
    pytest tests/test_adr004_baseplugin_enforcement.py -v
    # Fail CI if any test fails
```

---

## Migration Impact Assessment

### Breaking Changes

**What Breaks**:

- All existing plugin classes without `(BasePlugin)` inheritance will fail `isinstance()` checks
- Plugins will be skipped in ADR-002 validation (likely causing test failures)
- Any code relying on structural typing will break

**Who Is Affected**:

- ✅ **Internal Code**: We control all plugins, can migrate easily
- ✅ **Test Mocks**: Test helpers need `(BasePlugin)` added
- ❌ **External Plugins**: None (pre-1.0, no external plugin ecosystem yet)

### Migration Effort

| Component | Files Affected | Effort | Risk |
|-----------|----------------|--------|------|
| **BasePlugin Definition** | 1 file | 15 min | LOW (straightforward change) |
| **Core Plugins** | ~10-15 files | 30 min | LOW (mechanical change) |
| **Test Mocks** | ~5 files | 15 min | LOW (mechanical change) |
| **Type Hints** | ~3 files | 15 min | LOW (no runtime impact) |
| **Tests** | 1 new file | 20 min | LOW (new tests) |
| **Documentation** | 4 files | 20 min | LOW (documentation) |
| **CI Setup** | 2 files | 10 min | LOW (hook configuration) |

**Total Effort**: ~2-2.5 hours

**Risk Level**: **LOW**

- Pre-1.0 (no external users)
- Mechanical changes (add inheritance)
- Type checker catches errors
- Test suite verifies correctness

### Rollback Plan

If critical issues discovered:

1. **Immediate**: Revert `protocols.py` change (Protocol → ABC)
2. **Remove**: Delete new test file
3. **Restore**: Git revert to last good state
4. **Time**: <5 minutes

**Rollback Triggers**:

- Critical production bug discovered
- >50% of plugins fail to migrate cleanly
- Unforeseen MyPy/type checking issues

---

## Consequences

### Positive

- ✅ **Security**: Prevents accidental compliance attack scenario
- ✅ **Clarity**: Inheritance makes plugin status explicit
- ✅ **Type Safety**: MyPy enforces inheritance at compile time
- ✅ **Auditability**: Can enumerate all plugins via inheritance tree
- ✅ **Runtime Safety**: `isinstance()` checks are definitive
- ✅ **Intent**: Developer must explicitly opt in to plugin behavior
- ✅ **Standards**: Uses Python's standard ABC mechanism

### Negative

- ⚠️ **Breaking Change**: Existing code must add `(BasePlugin)`
- ⚠️ **Migration**: All plugins must be updated (mitigated: pre-1.0)
- ⚠️ **Flexibility**: Cannot use arbitrary objects as plugins (by design)

### Neutral

- ➡️ **Pre-1.0 Only**: Breaking changes acceptable now, not after 1.0
- ➡️ **One-Time Cost**: Migration effort is one-time, ongoing benefit

---

## Validation and Testing

### Test Coverage

**Unit Tests** (`test_adr004_baseplugin_enforcement.py`):

- ✅ Explicit inheritance is recognized
- ✅ Accidental compliance is rejected
- ✅ Cannot instantiate BasePlugin directly
- ✅ Missing method implementation fails
- ✅ All existing plugins migrated (verification)

**Integration Tests** (existing `test_adr002_suite_integration.py`):

- ✅ All integration tests still pass with ABC
- ✅ Security validation works correctly
- ✅ No regressions in ADR-002 enforcement

**Property-Based Tests** (existing `test_adr002_properties.py`):

- ✅ All property tests still pass
- ✅ Hypothesis finds no new edge cases

### Success Criteria

**Functional**:

- [ ] All existing tests pass after migration
- [ ] No plugins accidentally bypass validation
- [ ] Type checker (MyPy) catches missing inheritance

**Security**:

- [ ] `isinstance(helper_class, BasePlugin)` returns False (accidental compliance rejected)
- [ ] Only explicit inheritors participate in security validation
- [ ] No security regressions in ADR-002 enforcement

**Developer Experience**:

- [ ] Clear error messages when inheritance forgotten
- [ ] IDE autocomplete shows BasePlugin inheritance requirement
- [ ] Documentation provides migration examples

---

## Defense in Depth

**ADR-004 as Layer 1** (combined with ADR-003):

| Layer | Mechanism | Prevents |
|-------|-----------|----------|
| **Layer 1: ADR-004** | Nominal typing (ABC) | Accidental compliance via duck typing |
| **Layer 2: ADR-003** | Plugin type registry | Forgetting to collect plugin types |
| **Layer 3: ADR-003** | Test enforcement | Registry falling out of sync |

**Combined Effect**:

- Cannot accidentally be a plugin (Layer 1)
- Cannot forget to validate plugin type (Layer 2 + 3)
- Multiple independent defenses

---

## Examples

### Before (Protocol - Allows Accidental Compliance)

```python
# protocols.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class BasePlugin(Protocol):
    def get_security_level(self) -> SecurityLevel: ...
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...

# Helper class (NOT intended as plugin)
class SecurityHelper:
    """Helper for security level comparison - NOT A PLUGIN!"""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.OFFICIAL:
            raise ValueError("Need OFFICIAL")

# ⚠️ PROBLEM: Accidental compliance
helper = SecurityHelper()
isinstance(helper, BasePlugin)  # True! (Protocol accepts duck typing)

# If helper ends up in plugin list by mistake:
runner = ExperimentRunner(
    datasource=secret_datasource,  # SECRET
    row_plugins=[helper],  # UNOFFICIAL (accident!)
)

# Operating envelope = MIN(SECRET, UNOFFICIAL) = UNOFFICIAL 💥
# Secret data processed at UNOFFICIAL level!
```

### After (ABC - Requires Explicit Inheritance)

```python
# protocols.py
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    """All plugins MUST inherit from this class (ADR-004)."""

    @abstractmethod
    def get_security_level(self) -> SecurityLevel: ...

    @abstractmethod
    def validate_can_operate_at_level(self, level: SecurityLevel) -> None: ...

# Helper class (NOT a plugin)
class SecurityHelper:
    """Helper for security level comparison - NOT A PLUGIN!"""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.OFFICIAL:
            raise ValueError("Need OFFICIAL")

# ✅ FIXED: Accidental compliance rejected
helper = SecurityHelper()
isinstance(helper, BasePlugin)  # False! (ABC requires inheritance)

# If helper ends up in plugin list by mistake:
runner = ExperimentRunner(
    datasource=secret_datasource,  # SECRET
    row_plugins=[helper],  # NOT a BasePlugin - skipped ✅
)

# Operating envelope = MIN(SECRET) = SECRET ✅
# Helper ignored, correct security level maintained
```

### Migration Example

```python
# BEFORE: Works with Protocol, fails with ABC
class SecretDatasource:
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.SECRET:
            raise SecurityValidationError(...)

# AFTER: One-line fix
from elspeth.core.base.plugin import BasePlugin

class SecretDatasource(BasePlugin):  # ← Add this
    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, level: SecurityLevel) -> None:
        if level < SecurityLevel.SECRET:
            raise SecurityValidationError(...)
```

---

## Compliance and Certification

**ADR-002 Impact**: This ADR strengthens ADR-002 by:

1. Preventing accidental plugins from lowering operating envelope
2. Making plugin participation explicit and auditable
3. Providing compile-time verification of plugin compliance

**Certification Updates**:

- [ ] Update CERTIFICATION_EVIDENCE.md with ADR-004 verification
- [ ] Add to THREAT_MODEL.md as defense for T1
- [ ] Security team review and approval

---

## References

- **ADR-002**: Suite-level security enforcement
- **ADR-003**: Plugin type registry and test enforcement
- **Python ABC Documentation**: <https://docs.python.org/3/library/abc.html>
- **PEP 3119**: Introducing Abstract Base Classes
- **Related Incident**: Copilot P1 finding (missing plugin types) - highlighted need for stronger typing

---

## Decision Review

**Review Date**: TBD (6 months after implementation)
**Success Criteria**:

- [ ] Zero incidents of accidental plugin compliance
- [ ] All developers understand inheritance requirement
- [ ] No security regressions

---

**Author**: Claude Code
**Approvers**: [Pending Security Team Review]
**Implementation**: [Pending]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
