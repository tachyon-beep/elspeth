# Security Model

Understand Elspeth's **Bell-LaPadula Multi-Level Security (MLS)** enforcement.

!!! info "Why This Matters"
    Elspeth enforces **fail-fast security validation** to prevent sensitive data from flowing into untrusted components. Understanding this model is critical for configuring experiments correctly.

---

## Overview

Elspeth implements **Multi-Level Security (MLS)** based on the Bell-LaPadula model, originally designed for military and government systems. This ensures:

- ✅ **Fail-fast validation** - Misconfigured pipelines abort before data is retrieved
- ✅ **No unauthorized access** - Components can't access data above their clearance
- ✅ **Trusted downgrade** - High-clearance components can safely filter data for lower levels
- ✅ **Audit trail** - All security decisions logged

---

## Security Level Hierarchy

Elspeth uses five security levels (based on Australian Government PSPF classifications):

```
UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET
(lowest)                                                  (highest)
```

### Level Descriptions

| Level | Description | Example Use Cases |
|-------|-------------|-------------------|
| **UNOFFICIAL** | Public information, no sensitivity | Marketing copy, public datasets |
| **OFFICIAL** | Routine business data, limited distribution | Customer names, product lists |
| **OFFICIAL_SENSITIVE** | Sensitive business data, controlled access | Customer emails, internal reports |
| **PROTECTED** | Highly sensitive data, strict access controls | Financial records, HR data |
| **SECRET** | Classified information, maximum protection | Government secrets, regulated healthcare data |

!!! tip "Start with UNOFFICIAL"
    For testing and development, use `UNOFFICIAL` for all components. Increase levels only when handling actual sensitive data.

---

## Key Concepts

### Security Level (Clearance)

**What it is**: The maximum classification level a component is **cleared to handle**.

**Where it's declared**: In plugin configuration:

```yaml
datasource:
  type: csv_local
  path: data/customer_data.csv
  security_level: OFFICIAL  # ← Cleared for OFFICIAL data
```

**Analogy**: Like a security badge. If you have a SECRET badge, you can access SECRET, PROTECTED, OFFICIAL, and UNOFFICIAL areas.

---

### Operating Level

**What it is**: The actual classification level the **pipeline is running at**.

**How it's computed**: **Minimum** security level across ALL components:

```python
operating_level = min(
    datasource.security_level,
    llm.security_level,
    sink1.security_level,
    sink2.security_level,
    # ... all components
)
```

**Analogy**: The whole pipeline operates at the "lowest common clearance" - the weakest link in the chain.

---

### Bell-LaPadula "No Read Up" Rule

**The Core Principle**: Components can only access data **at or below** their security level.

```
❌ UNOFFICIAL component accessing SECRET data → FORBIDDEN (insufficient clearance)
✅ SECRET component accessing UNOFFICIAL data → ALLOWED (trusted to filter)
```

**Directionality**:
- **Data classification**: Can only INCREASE (UNOFFICIAL → SECRET via explicit uplift)
- **Plugin operations**: Can only DECREASE (SECRET → UNOFFICIAL via trusted downgrade)

These move in **opposite directions** - this is intentional!

---

## How It Works: Step-by-Step

### Example 1: Successful Pipeline

**Configuration**:
```yaml
datasource:
  security_level: OFFICIAL

llm:
  security_level: SECRET

sinks:
  - type: csv
    security_level: OFFICIAL
```

**Computation**:
```python
operating_level = min(OFFICIAL, SECRET, OFFICIAL)
                = OFFICIAL  # Lowest clearance wins
```

**Validation**:
- Datasource: `OFFICIAL` clearance, operating at `OFFICIAL` → ✅ **PASS** (exact match)
- LLM: `SECRET` clearance, operating at `OFFICIAL` → ✅ **PASS** (can downgrade, trusted to filter)
- Sink: `OFFICIAL` clearance, operating at `OFFICIAL` → ✅ **PASS** (exact match)

**Result**: Pipeline runs successfully at `OFFICIAL` level.

---

### Example 2: Failed Pipeline (Insufficient Clearance)

**Configuration**:
```yaml
datasource:
  security_level: UNOFFICIAL  # ← Low clearance

llm:
  security_level: SECRET

sinks:
  - type: csv
    security_level: SECRET  # ← High clearance
```

**Computation**:
```python
operating_level = min(UNOFFICIAL, SECRET, SECRET)
                = UNOFFICIAL  # Datasource is the bottleneck
```

**Validation**:
- Datasource: `UNOFFICIAL` clearance, operating at `UNOFFICIAL` → ✅ **PASS**
- LLM: `SECRET` clearance, operating at `UNOFFICIAL` → ✅ **PASS** (trusted downgrade)
- Sink: `SECRET` clearance, operating at `UNOFFICIAL` → ✅ **PASS** (trusted downgrade)

**Result**: Pipeline runs successfully at `UNOFFICIAL` level.

**Wait, why didn't it fail?**

Because the operating level is automatically computed as the MINIMUM. The `SECRET` sink can safely operate at `UNOFFICIAL` level (it's cleared for higher, so it can handle lower).

---

### Example 3: When Validation DOES Fail

Validation failures occur when you **manually force** a higher operating level:

**Configuration** (with manual override):
```yaml
# Force pipeline to operate at SECRET level
operating_level_override: SECRET  # Manual forcing

datasource:
  security_level: UNOFFICIAL  # ← Insufficient!

sink:
  security_level: SECRET
```

**Error**:
```
SecurityValidationError: Datasource has insufficient clearance.
Component clearance: UNOFFICIAL
Required operating level: SECRET
Cannot access SECRET data with UNOFFICIAL clearance (Bell-LaPadula "no read up" violation)
```

**Why it fails**: You're forcing the datasource to access `SECRET` data, but it only has `UNOFFICIAL` clearance.

!!! warning "Manual Overrides Rare"
    In normal operation, you won't manually set operating levels. The automatic minimum computation prevents insufficient-clearance errors. This scenario only occurs with explicit configuration overrides.

---

## Common Scenarios

### Scenario 1: Public Data → Public Output ✅

```yaml
datasource:
  security_level: UNOFFICIAL

llm:
  security_level: UNOFFICIAL

sinks:
  - type: csv
    security_level: UNOFFICIAL
```

**Operating Level**: `UNOFFICIAL` (minimum)

**Result**: ✅ **PASS** - All components match, pipeline runs at `UNOFFICIAL`

---

### Scenario 2: Secret Data → Secret Output ✅

```yaml
datasource:
  security_level: SECRET

llm:
  security_level: SECRET

sinks:
  - type: csv
    security_level: SECRET
```

**Operating Level**: `SECRET` (minimum)

**Result**: ✅ **PASS** - All components match, pipeline runs at `SECRET`

---

### Scenario 3: Secret Datasource → Public Output ✅

```yaml
datasource:
  security_level: SECRET  # Can access SECRET data

llm:
  security_level: SECRET

sinks:
  - type: csv
    security_level: UNOFFICIAL  # ← Lower clearance
```

**Operating Level**: `UNOFFICIAL` (minimum - the sink)

**Result**: ✅ **PASS** - Datasource is **trusted to filter** SECRET data down to UNOFFICIAL

**How it works**: The `SECRET` datasource operates at `UNOFFICIAL` level by:
1. Retrieving all data (has clearance)
2. **Filtering out SECRET-tagged rows** (trusted responsibility)
3. Passing only UNOFFICIAL data to pipeline

This is called **trusted downgrade** - high-clearance components can safely operate at lower levels.

---

### Scenario 4: Public Datasource → Secret Output ✅

```yaml
datasource:
  security_level: UNOFFICIAL  # ← Lowest clearance

llm:
  security_level: SECRET

sinks:
  - type: csv
    security_level: SECRET  # Can write SECRET data
```

**Operating Level**: `UNOFFICIAL` (minimum - the datasource)

**Result**: ✅ **PASS** - Pipeline operates at `UNOFFICIAL`, sink accepts lower-classified data

**Note**: The sink has `SECRET` clearance, so it can handle `UNOFFICIAL` data (higher clearance accepts lower data).

---

## Data Classification vs Plugin Operations

**CRITICAL DISTINCTION**: Data and plugins move in **opposite directions**:

### Data Classification (Can Only INCREASE)

```
UNOFFICIAL data → Explicit uplift → OFFICIAL data
OFFICIAL data   → Explicit uplift → SECRET data
```

✅ **Allowed**: Uplifting UNOFFICIAL to SECRET (via explicit API call)
❌ **Forbidden**: Downgrading SECRET to UNOFFICIAL (violates "no write down")

**Example**:
```python
df = ClassifiedDataFrame.create_from_datasource(
    raw_df,
    source_classification=SecurityLevel.UNOFFICIAL
)

# Explicit uplift (audited)
df_secret = df.with_uplifted_classification(SecurityLevel.SECRET)
```

---

### Plugin Operations (Can Only DECREASE)

```
SECRET plugin    → Trusted downgrade → Operates at OFFICIAL
OFFICIAL plugin  → Trusted downgrade → Operates at UNOFFICIAL
```

✅ **Allowed**: SECRET plugin operating at UNOFFICIAL (trusted to filter)
❌ **Forbidden**: UNOFFICIAL plugin operating at SECRET (insufficient clearance)

**Example**:
```python
# SECRET datasource can operate at UNOFFICIAL level
datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # ✅ PASS

# UNOFFICIAL datasource CANNOT operate at SECRET level
datasource.validate_can_operate_at_level(SecurityLevel.SECRET)      # ❌ FAIL
```

---

## Frozen Plugins (Advanced)

Some plugins are **frozen** - they refuse to operate below their declared level.

**Use case**: Dedicated SECRET infrastructure that should NEVER serve lower-classified pipelines.

**Configuration**:
```python
class FrozenSecretDataSource(BasePlugin, DataSource):
    def __init__(self, ...):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False  # ← Frozen at SECRET only
        )
```

**Behavior**:
- ✅ Can operate at `SECRET` level (exact match)
- ❌ Cannot operate at `OFFICIAL` or `UNOFFICIAL` (rejects downgrade)

**Error**:
```
SecurityValidationError: Frozen plugin cannot operate below declared level.
Declared level: SECRET
Requested level: OFFICIAL
This plugin has allow_downgrade=False
```

See [ADR-005](../../architecture/decisions/005-frozen-plugin-protection.md) for details.

---

## Troubleshooting

### Error: "Insufficient clearance"

**Full error**:
```
SecurityValidationError: Component has insufficient clearance.
Component clearance: UNOFFICIAL
Required operating level: SECRET
```

**Cause**: You've manually forced a pipeline to operate at a level higher than a component's clearance.

**Solution**: Either:
1. **Remove manual override** (let automatic minimum computation handle it)
2. **Increase component clearance**:
   ```yaml
   datasource:
     security_level: SECRET  # Raise to match required level
   ```

---

### Error: "Frozen plugin cannot operate below declared level"

**Full error**:
```
SecurityValidationError: Frozen plugin cannot operate below declared level.
Declared level: SECRET
Requested level: OFFICIAL
```

**Cause**: A frozen plugin (allow_downgrade=False) is being asked to operate at a lower level.

**Solution**: Either:
1. **Raise all components to match frozen plugin's level**:
   ```yaml
   datasource:
     security_level: SECRET  # Match frozen plugin

   sinks:
     - security_level: SECRET  # Match frozen plugin
   ```
2. **Use non-frozen plugin** (default allow_downgrade=True)

---

### Warning: "Operating at lower level than capable"

**Message**:
```
WARNING: SECRET datasource operating at UNOFFICIAL level.
Ensure datasource properly filters SECRET data.
```

**Cause**: A high-clearance component is operating at a lower level (trusted downgrade).

**Action**: This is expected behavior. Verify the component:
- Properly filters data at the operating level
- Doesn't leak higher-classified information
- Is certified for trusted downgrade use

---

## Audit Logging

All security decisions are logged to `logs/run_*.jsonl`:

```json
{
  "event": "security_validation",
  "timestamp": "2025-10-26T14:30:00Z",
  "component": "datasource",
  "clearance": "SECRET",
  "operating_level": "OFFICIAL",
  "result": "PASS",
  "reason": "Trusted downgrade"
}
```

**Review audit logs** to:
- Verify security enforcement
- Troubleshoot validation failures
- Provide evidence for compliance audits

---

## Best Practices

### 1. Start with UNOFFICIAL

For development and testing:
```yaml
# Set everything to UNOFFICIAL during development
datasource:
  security_level: UNOFFICIAL

llm:
  security_level: UNOFFICIAL

sinks:
  - security_level: UNOFFICIAL
```

Raise levels only when handling actual sensitive data.

---

### 2. Match Levels for Simplicity

Simplest configuration - all components at same level:
```yaml
datasource:
  security_level: OFFICIAL

llm:
  security_level: OFFICIAL

sinks:
  - security_level: OFFICIAL
```

Pipeline operates at `OFFICIAL`, no downgrade needed.

---

### 3. Use Trusted Downgrade Intentionally

Only use high-clearance components operating at lower levels when:
- ✅ Component is certified to filter appropriately
- ✅ Organizational policy allows trusted downgrade
- ✅ Audit logging is enabled
- ✅ Regular security reviews are conducted

---

### 4. Never Manually Override Operating Level

Avoid forcing operating levels unless absolutely necessary:
```yaml
# ❌ Avoid this
operating_level_override: SECRET

# ✅ Prefer this (automatic minimum)
# (no override - let system compute)
```

---

### 5. Document Security Decisions

In experiment configs, explain security choices:
```yaml
datasource:
  security_level: SECRET
  # JUSTIFICATION: Accessing classified government datasets
  # CERTIFICATION: Approved by security team (ticket #1234)
  # FILTER BEHAVIOR: Removes all SECRET-tagged rows when operating below SECRET

llm:
  security_level: OFFICIAL
  # JUSTIFICATION: LLM endpoint not cleared for SECRET data
  # CONSEQUENCE: Pipeline forced to OFFICIAL level (minimum)
```

---

## Visual Summary

### Pipeline Security Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ SECURITY LEVEL ENFORCEMENT                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Components declare security levels (clearances)             │
│     ↓                                                           │
│  2. System computes operating level = MIN(all clearances)       │
│     ↓                                                           │
│  3. Each component validates: Can I operate at this level?      │
│     ↓                                                           │
│  4. HIGH clearance ≥ operating level → ✅ PASS (trusted)        │
│     LOW clearance < operating level → ❌ FAIL (insufficient)    │
│     ↓                                                           │
│  5. Pipeline runs (or aborts if validation failed)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Security Level Hierarchy

```
┌─────────────┐
│   SECRET    │  ← Highest classification
├─────────────┤
│  PROTECTED  │
├─────────────┤
│  OFFICIAL   │
│ :SENSITIVE  │
├─────────────┤
│  OFFICIAL   │
├─────────────┤
│ UNOFFICIAL  │  ← Lowest classification (public)
└─────────────┘

Allowed Operations:
  ✅ SECRET component → Can operate at OFFICIAL (trusted downgrade)
  ❌ OFFICIAL component → Cannot operate at SECRET (insufficient clearance)
```

---

## Further Reading

- **[ADR-002: Multi-Level Security Enforcement](../../architecture/decisions/002-security-architecture.md)** - Full specification
- **[ADR-002a: ClassifiedDataFrame Constructor](../../architecture/decisions/002a-classified-dataframe-constructor.md)** - Data classification model
- **[ADR-005: Frozen Plugin Protection](../../architecture/decisions/005-frozen-plugin-protection.md)** - Strict level enforcement
- **[Security Controls](../../compliance/security-controls.md)** - Compliance documentation

---

!!! success "Key Takeaways"
    - **Operating level** = MIN of all component clearances
    - **"No read up"** = Components can't access data above their clearance
    - **Trusted downgrade** = High-clearance components can safely operate at lower levels
    - **Fail-fast** = Validation happens before data retrieval
    - **Start with UNOFFICIAL** for development, raise levels only when needed

    Security is enforced **automatically** - just declare levels correctly and the system handles the rest!
