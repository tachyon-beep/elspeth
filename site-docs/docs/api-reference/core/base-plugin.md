# BasePlugin

Abstract base class for all Elspeth plugins with security enforcement.

!!! info "ADR-004: Mandatory BasePlugin Inheritance"
    All plugins **must** explicitly inherit from `BasePlugin`. This is not a Protocol (structural typing) but an ABC (nominal typing) to prevent security bypass attacks.

---

## Overview

`BasePlugin` provides **security bones** - concrete, non-overridable methods that implement security-critical invariants. Plugins inherit security enforcement without implementing it.

**Key Design Principle**: Security methods are `@final` and cannot be overridden by subclasses. This ensures consistent security enforcement across all plugins.

---

## Class Documentation

::: elspeth.core.base.plugin.BasePlugin
    options:
      members:
        - __init__
        - __init_subclass__
        - get_security_level
        - validate_can_operate_at_level
        - security_level
        - allow_downgrade
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

---

## Usage Examples

### Basic Plugin

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel

class MyDatasource(BasePlugin):
    """Simple datasource plugin."""

    def __init__(self, *, security_level: SecurityLevel, path: str):
        super().__init__(security_level=security_level)
        self.path = path

    def load_data(self):
        """Load data from path."""
        # Implementation...
        pass

# Usage
ds = MyDatasource(security_level=SecurityLevel.OFFICIAL, path="data.csv")
print(ds.get_security_level())  # SecurityLevel.OFFICIAL
```

### Frozen Plugin (ADR-005)

```python
class FrozenSecretDatasource(BasePlugin):
    """Datasource that refuses to operate below SECRET level."""

    def __init__(self, *, database_url: str):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False  # ← Frozen at SECRET only
        )
        self.database_url = database_url

# Usage
frozen = FrozenSecretDatasource(database_url="postgresql://...")
print(frozen.allow_downgrade)  # False

# Can operate at SECRET level (exact match)
frozen.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK

# Cannot operate at lower levels (frozen)
frozen.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ❌ Raises SecurityValidationError
```

### Validation Example

```python
# Create plugin with SECRET clearance
plugin = MyDatasource(security_level=SecurityLevel.SECRET, path="data.csv")

# Validate operating levels
plugin.validate_can_operate_at_level(SecurityLevel.SECRET)      # ✅ OK (exact match)
plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)    # ✅ OK (trusted downgrade)
plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # ✅ OK (trusted downgrade)

# Create plugin with UNOFFICIAL clearance
plugin_low = MyDatasource(security_level=SecurityLevel.UNOFFICIAL, path="public.csv")

# Cannot operate above clearance
plugin_low.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # ✅ OK (exact)
plugin_low.validate_can_operate_at_level(SecurityLevel.SECRET)      # ❌ Raises (insufficient clearance)
```

---

## Security Enforcement

### "Security Bones" Design

BasePlugin provides concrete (not abstract) security methods:

| Method | Purpose | Overridable? |
|--------|---------|--------------|
| `get_security_level()` | Returns plugin's clearance | ❌ No (@final) |
| `validate_can_operate_at_level()` | Validates operating level | ❌ No (@final) |

**Why concrete methods?**

1. **Consistency**: All plugins use identical security logic
2. **Security**: Can't accidentally break enforcement
3. **Simplicity**: Plugins inherit security for free
4. **Maintainability**: Security logic in one place
5. **Trust Boundary**: Security enforcement isolated from plugin code

### Runtime Enforcement

`__init_subclass__` hook prevents subclass override attempts:

```python
class BadPlugin(BasePlugin):
    def get_security_level(self):  # ❌ Attempt to override
        return SecurityLevel.SECRET  # (Always return SECRET - bypass!)

# Raises TypeError at class definition time:
# TypeError: Subclass BadPlugin cannot override final method 'get_security_level'
```

---

## Constructor Contract

### Required Parameters

```python
def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool = True):
    """Initialize BasePlugin.

    Args:
        security_level: Plugin's security clearance (keyword-only, required)
        allow_downgrade: Whether plugin can operate at lower levels (default: True)
    """
```

**Rules:**

- ✅ `security_level` is **keyword-only** (must use `security_level=...`)
- ✅ `security_level` is **required** (no default value)
- ✅ Must call `super().__init__(security_level=...)`
- ✅ `allow_downgrade` is optional (defaults to `True`)

### Invalid Constructors

```python
# ❌ Missing security_level
class BadPlugin1(BasePlugin):
    def __init__(self):
        super().__init__()  # TypeError: missing required argument

# ❌ Positional argument
class BadPlugin2(BasePlugin):
    def __init__(self, level: SecurityLevel):
        super().__init__(level)  # TypeError: takes keyword-only arguments

# ✅ Correct
class GoodPlugin(BasePlugin):
    def __init__(self, *, security_level: SecurityLevel):
        super().__init__(security_level=security_level)
```

---

## Properties

### `security_level`

Read-only property returning the plugin's security clearance.

```python
plugin = MyDatasource(security_level=SecurityLevel.OFFICIAL, path="data.csv")
print(plugin.security_level)  # SecurityLevel.OFFICIAL

# Read-only (cannot modify)
plugin.security_level = SecurityLevel.SECRET  # ❌ AttributeError
```

### `allow_downgrade`

Read-only property indicating whether plugin can operate at lower levels.

```python
# Standard plugin (can downgrade)
plugin = MyDatasource(security_level=SecurityLevel.SECRET, path="data.csv")
print(plugin.allow_downgrade)  # True

# Frozen plugin (cannot downgrade)
frozen = FrozenSecretDatasource(database_url="...")
print(frozen.allow_downgrade)  # False
```

---

## Related Documentation

- **[ClassifiedDataFrame](classified-dataframe.md)** - Data container with classification
- **[SecurityLevel](security-level.md)** - Security clearance enumeration
- **[Security Model](../../user-guide/security-model.md)** - Bell-LaPadula MLS explanation
- **[Plugin Development](../../plugins/overview.md)** - Creating custom plugins

---

## ADR Cross-References

- **ADR-002**: Multi-Level Security Enforcement - Requires `isinstance(plugin, BasePlugin)` checks
- **ADR-004**: Mandatory BasePlugin Inheritance - This ABC enables ADR-002 validation
- **ADR-005**: Frozen Plugin Protection - `allow_downgrade=False` use cases
