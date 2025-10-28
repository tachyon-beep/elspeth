# SecurityLevel

Enumeration of security clearance levels implementing Australian Government PSPF classifications.

---

## Overview

`SecurityLevel` defines five hierarchical security clearances from lowest (UNOFFICIAL) to highest (SECRET):

```
UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET
    (0)         (1)            (2)              (3)        (4)
```

**Ordering**: Security levels support comparison operations (`<`, `>`, `<=`, `>=`) based on integer values.

---

## Class Documentation

::: elspeth.core.base.types.SecurityLevel
    options:
      members: true
      show_root_heading: true
      show_root_full_path: false
      heading_level: 2

---

## Security Levels

### UNOFFICIAL (Level 0)

**Description**: Public information, no sensitivity

**Example Use Cases**:
- Marketing copy
- Public datasets
- Open-source documentation
- Test data for development

**YAML Configuration**:
```yaml
datasource:
  security_level: UNOFFICIAL
```

---

### OFFICIAL (Level 1)

**Description**: Routine business data, limited distribution

**Example Use Cases**:
- Customer names
- Product lists
- Internal reports (non-sensitive)
- Business correspondence

**YAML Configuration**:
```yaml
datasource:
  security_level: OFFICIAL
```

---

### OFFICIAL_SENSITIVE (Level 2)

**Description**: Sensitive business data, controlled access

**Example Use Cases**:
- Customer emails and phone numbers
- Internal financial reports
- Employee performance data
- Project roadmaps

**YAML Configuration**:
```yaml
datasource:
  security_level: OFFICIAL_SENSITIVE
```

---

### PROTECTED (Level 3)

**Description**: Highly sensitive data, strict access controls

**Example Use Cases**:
- Detailed financial records
- HR personnel files
- Contracts and legal documents
- Customer payment information

**YAML Configuration**:
```yaml
datasource:
  security_level: PROTECTED
```

---

### SECRET (Level 4)

**Description**: Classified information, maximum protection

**Example Use Cases**:
- Government classified data
- Regulated healthcare data (HIPAA)
- National security information
- Trade secrets

**YAML Configuration**:
```yaml
datasource:
  security_level: SECRET
```

---

## Usage Examples

### Comparison Operations

Security levels support rich comparisons:

```python
from elspeth.core.base.types import SecurityLevel

# Inequality comparisons
print(SecurityLevel.UNOFFICIAL < SecurityLevel.OFFICIAL)  # True
print(SecurityLevel.SECRET > SecurityLevel.PROTECTED)     # True

# Equality
print(SecurityLevel.OFFICIAL == SecurityLevel.OFFICIAL)   # True
print(SecurityLevel.UNOFFICIAL == SecurityLevel.SECRET)   # False

# Ordering
levels = [
    SecurityLevel.SECRET,
    SecurityLevel.UNOFFICIAL,
    SecurityLevel.PROTECTED
]
sorted_levels = sorted(levels)
# [SecurityLevel.UNOFFICIAL, SecurityLevel.PROTECTED, SecurityLevel.SECRET]
```

### min() and max() Operations

Computing operating levels and uplifting:

```python
# Operating level = MIN of all component levels
datasource_level = SecurityLevel.SECRET
llm_level = SecurityLevel.OFFICIAL
sink_level = SecurityLevel.PROTECTED

operating_level = min(datasource_level, llm_level, sink_level)
print(operating_level)  # SecurityLevel.OFFICIAL (lowest)

# Classification uplifting = MAX operation
current_classification = SecurityLevel.OFFICIAL
plugin_level = SecurityLevel.PROTECTED

uplifted = max(current_classification, plugin_level)
print(uplifted)  # SecurityLevel.PROTECTED
```

### Validation Logic

```python
def validate_clearance(
    component_level: SecurityLevel,
    required_level: SecurityLevel
) -> bool:
    """Check if component has sufficient clearance.

    Component must be >= required level (higher or equal).
    """
    return component_level >= required_level

# Examples
print(validate_clearance(
    SecurityLevel.SECRET,
    SecurityLevel.OFFICIAL
))  # True (SECRET >= OFFICIAL)

print(validate_clearance(
    SecurityLevel.UNOFFICIAL,
    SecurityLevel.SECRET
))  # False (UNOFFICIAL < SECRET)
```

---

## String Representation

Security levels have string representations matching YAML configuration:

```python
level = SecurityLevel.OFFICIAL
print(str(level))   # "SecurityLevel.OFFICIAL"
print(level.name)   # "OFFICIAL"
print(level.value)  # 1
```

### Parsing from Strings

```python
# From name
level = SecurityLevel['OFFICIAL']
print(level)  # SecurityLevel.OFFICIAL

# From value
level = SecurityLevel(1)
print(level)  # SecurityLevel.OFFICIAL
```

---

## Integer Values

Each level has an integer value for ordering:

| Level | Value | Comparison |
|-------|-------|------------|
| UNOFFICIAL | 0 | Lowest |
| OFFICIAL | 1 | Low |
| OFFICIAL_SENSITIVE | 2 | Medium |
| PROTECTED | 3 | High |
| SECRET | 4 | Highest |

```python
print(SecurityLevel.UNOFFICIAL.value)  # 0
print(SecurityLevel.SECRET.value)      # 4

# Comparisons use integer values
print(SecurityLevel.SECRET.value > SecurityLevel.OFFICIAL.value)  # True
```

---

## Common Patterns

### Operating Level Computation

Pipeline operating level is the **minimum** across all components:

```python
def compute_operating_level(*components) -> SecurityLevel:
    """Compute pipeline operating level.

    Returns minimum security level across all components.
    This is the "weakest link" in the security chain.
    """
    return min(c.get_security_level() for c in components)

# Usage
operating_level = compute_operating_level(
    datasource,  # SECRET
    llm,         # OFFICIAL
    sink1,       # PROTECTED
    sink2        # OFFICIAL
)
print(operating_level)  # OFFICIAL (minimum)
```

### Classification Uplifting

Data classification can only increase (max operation):

```python
def uplift_classification(
    current: SecurityLevel,
    plugin_level: SecurityLevel
) -> SecurityLevel:
    """Uplift classification to plugin level.

    Returns max(current, plugin_level) to prevent downgrading.
    """
    return max(current, plugin_level)

# Examples
print(uplift_classification(
    SecurityLevel.OFFICIAL,
    SecurityLevel.PROTECTED
))  # PROTECTED (uplifted)

print(uplift_classification(
    SecurityLevel.SECRET,
    SecurityLevel.OFFICIAL
))  # SECRET (no downgrade)
```

### Validation with Bell-LaPadula "No Read Up"

```python
def can_access(
    component_clearance: SecurityLevel,
    data_classification: SecurityLevel
) -> bool:
    """Check if component can access data (Bell-LaPadula "no read up").

    Component must have clearance >= data classification.
    """
    return component_clearance >= data_classification

# Examples
print(can_access(
    SecurityLevel.SECRET,      # Component clearance
    SecurityLevel.OFFICIAL     # Data classification
))  # True (SECRET >= OFFICIAL)

print(can_access(
    SecurityLevel.UNOFFICIAL,  # Component clearance
    SecurityLevel.SECRET       # Data classification
))  # False (UNOFFICIAL < SECRET, insufficient clearance)
```

---

## Related Documentation

- **[BasePlugin](base-plugin.md)** - Plugin base class using SecurityLevel
- **[ClassifiedDataFrame](classified-dataframe.md)** - Data container with SecurityLevel
- **[Security Model](../../user-guide/security-model.md)** - Complete MLS explanation

---

## ADR Cross-References

- **ADR-002**: Multi-Level Security Enforcement - SecurityLevel enumeration defines classification hierarchy
- **ADR-001**: Design Philosophy - Security-first priority hierarchy
