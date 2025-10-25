# ClassifiedDataFrame

DataFrame wrapper with immutable classification metadata implementing ADR-002 security enforcement.

!!! warning "Security-Critical Component"
    `ClassifiedDataFrame` enforces **immutable classification** and **automatic uplifting**. Classification can only increase (UNOFFICIAL → SECRET), never decrease. This prevents data laundering attacks.

---

## Overview

`ClassifiedDataFrame` wraps Pandas DataFrames with a security classification that:

- ✅ **Cannot be downgraded** (classification only increases)
- ✅ **Is immutable** (frozen dataclass)
- ✅ **Created only by datasources** (constructor protection)
- ✅ **Uplifted automatically** (max operation on classifications)

**Security Model**: ADR-002 Trusted Container with constructor protection against classification laundering.

---

## Class Documentation

::: elspeth.core.security.classified_data.ClassifiedDataFrame
    options:
      members:
        - create_from_datasource
        - with_uplifted_classification
        - with_new_data
        - validate_access_by
        - data
        - classification
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

---

## Usage Patterns

### Pattern 1: Datasource Creation (Trusted Source)

Only datasources can create `ClassifiedDataFrame` instances from scratch:

```python
from elspeth.core.security.classified_data import ClassifiedDataFrame
from elspeth.core.base.types import SecurityLevel
import pandas as pd

# Datasource creates classified frame
raw_data = pd.DataFrame({'text': ['Hello', 'World'], 'score': [0.9, 0.8]})
frame = ClassifiedDataFrame.create_from_datasource(
    raw_data, SecurityLevel.OFFICIAL
)

print(frame.classification)  # SecurityLevel.OFFICIAL
print(len(frame.data))       # 2
```

### Pattern 2: Plugin Transformation (In-Place Mutation)

Plugins can mutate the underlying DataFrame, then uplift classification:

```python
# Plugin modifies data in-place
frame.data['processed'] = frame.data['text'].str.upper()

# Uplift classification to plugin's level
plugin_level = SecurityLevel.PROTECTED
result = frame.with_uplifted_classification(plugin_level)

print(result.classification)  # SecurityLevel.PROTECTED (uplifted)
print('processed' in result.data.columns)  # True
```

### Pattern 3: Plugin Data Generation (LLMs, Aggregations)

Plugins can generate new data and attach it with uplifted classification:

```python
# LLM generates new dataframe
llm_output = pd.DataFrame({
    'input': ['Hello', 'World'],
    'llm_response': ['Processed: Hello', 'Processed: World']
})

# Attach new data with uplifted classification
result = frame.with_new_data(llm_output).with_uplifted_classification(
    plugin.get_security_level()
)

print(result.data.columns)    # ['input', 'llm_response']
print(result.classification)  # Uplifted to plugin level
```

### Anti-Pattern: Direct Construction (BLOCKED)

Direct construction is prohibited to prevent classification laundering:

```python
import pandas as pd
from elspeth.core.security.classified_data import ClassifiedDataFrame
from elspeth.core.base.types import SecurityLevel

# ❌ Direct construction raises SecurityValidationError
df = pd.DataFrame({'data': [1, 2, 3]})
frame = ClassifiedDataFrame(df, SecurityLevel.OFFICIAL)
# Raises: SecurityValidationError: ClassifiedDataFrame must be created via create_from_datasource
```

---

## Security Guarantees

### Immutability

Classification cannot be modified after creation (frozen dataclass):

```python
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)

# ❌ Cannot modify classification
frame.classification = SecurityLevel.SECRET  # AttributeError (frozen)
```

### Classification Uplifting Only

Classification can only increase, never decrease:

```python
# Start with OFFICIAL data
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)

# ✅ Can uplift to PROTECTED
uplifted = frame.with_uplifted_classification(SecurityLevel.PROTECTED)
print(uplifted.classification)  # SecurityLevel.PROTECTED

# ✅ Can uplift again to SECRET
secret = uplifted.with_uplifted_classification(SecurityLevel.SECRET)
print(secret.classification)  # SecurityLevel.SECRET

# ✅ "Downgrade" attempt is actually a no-op (max operation)
attempt_downgrade = secret.with_uplifted_classification(SecurityLevel.OFFICIAL)
print(attempt_downgrade.classification)  # Still SecurityLevel.SECRET
```

**Why max() operation?**

Uplifting uses `max(current, requested)`:
- If requested > current → uplift to requested
- If requested < current → no-op (stay at current)
- This prevents accidental downgrading

### Constructor Protection

Only datasources can create instances:

```python
# ✅ Datasource context (trusted)
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)

# ❌ Plugin context (untrusted)
frame = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
# Raises: SecurityValidationError
```

**Why this restriction?**

Prevents plugins from creating "fresh" frames with lower classifications, bypassing uplifting logic:

```python
# Attack scenario (prevented):
# 1. Plugin receives SECRET data
# 2. Plugin creates new frame with UNOFFICIAL classification
# 3. SECRET data now appears as UNOFFICIAL (laundering attack)
# → BLOCKED by constructor protection
```

---

## Access Validation

### validate_access_by()

Runtime failsafe ensuring component has sufficient clearance:

```python
from elspeth.core.base.plugin import BasePlugin

# Create PROTECTED data
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.PROTECTED
)

# Plugin with PROTECTED clearance
plugin_protected = MyPlugin(security_level=SecurityLevel.PROTECTED)
frame.validate_access_by(plugin_protected)  # ✅ OK

# Plugin with UNOFFICIAL clearance
plugin_low = MyPlugin(security_level=SecurityLevel.UNOFFICIAL)
frame.validate_access_by(plugin_low)  # ❌ Raises SecurityValidationError
```

**When to use:**
- Runtime checks in sinks before writing data
- Validation before passing data to external systems
- Defensive programming for security-critical paths

---

## Common Operations

### Accessing Underlying DataFrame

```python
frame = ClassifiedDataFrame.create_from_datasource(
    data, SecurityLevel.OFFICIAL
)

# Access underlying DataFrame
df = frame.data
print(type(df))  # pandas.DataFrame

# Modify DataFrame in-place
frame.data['new_column'] = frame.data['old_column'] * 2

# Uplift after modifications
result = frame.with_uplifted_classification(plugin.get_security_level())
```

### Replacing DataFrame

```python
# Generate new DataFrame
new_df = pd.DataFrame({'result': [1, 2, 3]})

# Replace data and uplift
result = frame.with_new_data(new_df).with_uplifted_classification(
    SecurityLevel.PROTECTED
)

print(result.data.columns)    # ['result']
print(result.classification)  # SecurityLevel.PROTECTED
```

### Chaining Operations

```python
result = (
    frame
    .with_new_data(llm_output)
    .with_uplifted_classification(SecurityLevel.PROTECTED)
    .with_uplifted_classification(SecurityLevel.SECRET)  # Chain uplifts
)

print(result.classification)  # SecurityLevel.SECRET
```

---

## Error Handling

### SecurityValidationError

Raised when security constraints are violated:

```python
from elspeth.core.validation.base import SecurityValidationError

try:
    # Direct construction (blocked)
    frame = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
except SecurityValidationError as e:
    print(f"Security violation: {e}")

try:
    # Insufficient clearance
    frame = ClassifiedDataFrame.create_from_datasource(
        data, SecurityLevel.SECRET
    )
    plugin = MyPlugin(security_level=SecurityLevel.UNOFFICIAL)
    frame.validate_access_by(plugin)
except SecurityValidationError as e:
    print(f"Access denied: {e}")
```

---

## ADR Threat Prevention

ClassifiedDataFrame prevents ADR-002 threat scenarios:

| Threat | Prevention Mechanism |
|--------|----------------------|
| **T3: Runtime Bypass** | `validate_access_by()` catches start-time validation bypass |
| **T4: Classification Mislabeling** | Constructor protection prevents laundering attacks |
| **Downgrade Attacks** | Immutability + max() operation prevents classification reduction |

---

## Related Documentation

- **[BasePlugin](base-plugin.md)** - Plugin base class with security enforcement
- **[SecurityLevel](security-level.md)** - Security clearance enumeration
- **[Security Model](../../user-guide/security-model.md)** - Bell-LaPadula MLS explanation

---

## ADR Cross-References

- **ADR-002**: Multi-Level Security Enforcement - ClassifiedDataFrame implements trusted container
- **ADR-002a**: ClassifiedDataFrame Constructor - Constructor protection design
