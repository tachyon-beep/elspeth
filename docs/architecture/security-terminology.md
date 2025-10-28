# Security Terminology Glossary

**Last Updated**: 2025-10-26
**Purpose**: Canonical definitions for security-related terms used throughout Elspeth architecture and ADRs

---

## Core Security Concepts

### security_level

**Definition**: A plugin's **clearance** - the maximum security level of data it is authorized to handle

**Type**: `SecurityLevel` enum (UNOFFICIAL, OFFICIAL, OFFICIAL_SENSITIVE, PROTECTED, SECRET)

**Usage**: Plugin property, declared at registration time

**Example**:
```python
class SecretClearedSink(BasePlugin, ResultSink):
    def __init__(self, *, allow_downgrade: bool):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=allow_downgrade  # REQUIRED: No default
        )
        # This sink is cleared to handle data up to SECRET classification
        # allow_downgrade choice determines if it can operate at lower levels
```

**Synonyms to Avoid**: "clearance" (ambiguous - use `security_level` instead)

**Related**: ADR-002 (Multi-Level Security), ADR-004 (BasePlugin)

---

### classification

**Definition**: Data's **classification label** - the security level required to access this data

**Type**: `SecurityLevel` enum (same values as security_level)

**Usage**: Data property, tracked by `SecureDataFrame` (ADR-002-A)

**Example**:
```python
# Note: Direct construction is blocked; only datasources can create frames
classified_df = SecureDataFrame.create_from_datasource(
    data=df,
    security_level=SecurityLevel.PROTECTED
)
# This data requires PROTECTED clearance to access
```

**Key Distinction**:
- `security_level` = what a component **CAN handle** (capability)
- `classification` = what data **REQUIRES** (constraint)

**Related**: ADR-002-A (Trusted Container Model), ADR-002 (MLS)

---

### operating_level

**Definition**: The pipeline's **security envelope** - the minimum security level across all components in the pipeline

**Type**: `SecurityLevel` enum

**Computation**: `operating_level = min(datasource.security_level, llm.security_level, sink.security_level, ...)`

**Usage**: Computed at pipeline construction, used for fail-fast validation

**Example**:
```python
# Pipeline components
datasource.security_level = SecurityLevel.OFFICIAL      # Lowest clearance
llm.security_level = SecurityLevel.SECRET
sink.security_level = SecurityLevel.SECRET

# Computed operating level
operating_level = SecurityLevel.OFFICIAL  # Minimum of all components

# All components must validate they can operate at this level
```

**Purpose**: Fail-fast abort if any component cannot operate at the required security level

**Important Note**: With automatic computation (default behavior), `operating_level` equals the LOWEST component clearance. This means insufficient clearance errors **cannot occur** under normal operation—every component can always operate at or above the minimum level. Insufficient clearance errors ONLY occur in two scenarios:
1. **Manual override**: Operators force a higher operating level via configuration
2. **Frozen plugins** (ADR-005): Plugins with **explicitly set** `allow_downgrade=False` refuse to operate below their declared level, even if the automatic minimum is lower. This is useful for dedicated classification domains (e.g., SECRET-only infrastructure).

**Note**: `allow_downgrade` has **no default value** - developers must explicitly choose `True` (trusted downgrade) or `False` (frozen plugin) when creating plugins. This explicit choice enforces security-first thinking (ADR-001).

**Related**: ADR-002 (Pipeline-wide minimum evaluation, lines 47-48, 68-77)

---

## Access Control Rules (Bell-LaPadula Model)

### "No Read Up" Rule

**Definition**: A component with LOWER clearance CANNOT access data with HIGHER classification

**Formula**: `if data.classification > component.security_level: raise SecurityValidationError`

**Example (VIOLATION)**:
```python
# Component clearance
sink.security_level = SecurityLevel.UNOFFICIAL

# Data classification
data.classification = SecurityLevel.SECRET

# Result: ABORT (sink lacks clearance for SECRET data)
if data.classification > sink.security_level:
    raise SecurityValidationError(
        f"Sink lacks clearance for {data.classification} data"
    )
```

**Rationale**: Prevents low-clearance components from accessing high-classification data (information leakage)

**Related**: ADR-002 (Bell-LaPadula enforcement)

---

### "Trusted Downgrade" Rule

**Definition**: A component with HIGHER clearance CAN operate at LOWER security levels (trusted to filter/downgrade appropriately) **when explicitly permitted**

**Formula**: `component.security_level >= operating_level AND component.allow_downgrade == True` (OK to operate)

**Explicit Choice Required**: Developers must set `allow_downgrade=True` to enable trusted downgrade (no default - ADR-001 security-first principle)

**Example (ALLOWED)**:
```python
# Datasource with trusted downgrade (EXPLICIT)
datasource = MyDatasource(
    security_level=SecurityLevel.SECRET,
    allow_downgrade=True  # ← REQUIRED: Explicit choice to enable downgrade
)

# Pipeline operating level
operating_level = SecurityLevel.OFFICIAL  # Lower than datasource

# Validation check
if datasource.security_level >= operating_level and datasource.allow_downgrade:
    # ✅ OK: datasource can operate at lower level, trusted to filter SECRET data
    datasource.load_data()
```

**Responsibility**: When operating at lower level, high-clearance component MUST filter out higher-classified data

**Certification**: Proper filtering is validated through security certification, not runtime checks

**Related**: ADR-002 (Source responsibility)

---

## Security Level Hierarchy

### SecurityLevel Enum

**Values** (ordered from lowest to highest):
1. **UNOFFICIAL** - Public, unclassified data
2. **OFFICIAL** - Internal use, not for public release
3. **OFFICIAL_SENSITIVE** - Internal sensitive, requires protection (displayed as "OFFICIAL: SENSITIVE")
4. **PROTECTED** - Higher protection, limited access
5. **SECRET** - Highest classification, strict access controls

**Comparison**:
```python
# Ordering
SecurityLevel.SECRET > SecurityLevel.PROTECTED
SecurityLevel.PROTECTED > SecurityLevel.OFFICIAL_SENSITIVE
SecurityLevel.OFFICIAL_SENSITIVE > SecurityLevel.OFFICIAL
SecurityLevel.OFFICIAL > SecurityLevel.UNOFFICIAL

# Access control check
if data.classification > plugin.security_level:
    # Violation: Plugin lacks clearance
    raise SecurityValidationError(...)
```

**Note**: Australian PSPF classification scheme used as reference (adaptable to other schemes)

**Related**: ADR-002 (MLS model)

---

## Component Security Concepts

### security bones

**Definition**: Concrete security enforcement methods in `BasePlugin` abstract base class that **cannot be overridden** by subclasses

**Pattern**: ADR-004 "Security Bones" pattern

**Implementation**: `@final` decorator on critical security methods

**Example**:
```python
class BasePlugin(ABC):
    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool):
        """Initialize plugin with explicit downgrade policy (NO DEFAULT).

        Args:
            allow_downgrade: MANDATORY - must explicitly choose:
                - True: Trusted downgrade (can operate at lower levels)
                - False: Frozen plugin (exact level match only - ADR-005)
        """
        self._security_level = security_level
        self._allow_downgrade = allow_downgrade

    @final
    def validate_can_operate_at_level(self, required_level: SecurityLevel) -> None:
        """Validate clearance (CANNOT be overridden by subclasses)."""
        # Frozen plugin (allow_downgrade=False): Exact match only
        if not self._allow_downgrade and required_level != self._security_level:
            raise SecurityValidationError("Frozen plugin requires exact level match")
        # All plugins: Cannot operate above clearance
        if required_level > self._security_level:
            raise SecurityValidationError(
                f"Insufficient clearance: required {required_level}, "
                f"have {self._security_level}"
            )
```

**Purpose**: Prevent subclasses from bypassing security checks

**Methods with "Security Bones"** (sealed with `@final` + `__init_subclass__` enforcement):
- `get_security_level()` - Returns plugin's declared security clearance
- `validate_can_operate_at_level()` - Validates operating level (supports `allow_downgrade` parameter)

**Related**: ADR-004 (Mandatory BasePlugin Inheritance)

---

### fail-closed

**Definition**: Deny the operation when security **cannot be validated** (conservative, secure default)

**Opposite**: fail-open (allow operation when validation fails - INSECURE, FORBIDDEN)

**Policy**: ADR-001 mandates fail-closed for ALL security controls

**Example (CORRECT - fail-closed)**:
```python
# Stack inspection unavailable (cannot validate caller)
if not can_inspect_stack():
    raise SecurityValidationError(
        "Stack inspection unavailable, cannot validate caller"
    )
    # ✅ Operation denied (fail-closed)
```

**Example (INCORRECT - fail-open)**:
```python
# FORBIDDEN pattern
if not can_inspect_stack():
    logger.warning("Stack inspection unavailable, allowing operation")
    return  # ❌ Operation allowed (fail-open) - SECURITY VIOLATION
```

**Rationale**: Adversaries can trigger control failures to bypass security (fail-open creates attack surface)

**Related**: ADR-001 (Fail-Closed Principle), ADR-006 (Security exceptions - proposed)

---

### fail-fast

**Definition**: Abort pipeline execution **early** (before data retrieval) if security validation fails

**Purpose**: Prevent low-clearance components from accessing high-classification data

**Example**:
```python
# Fail-fast: Validate clearances BEFORE datasource.load_data()
operating_level = compute_pipeline_minimum(datasource, llm, sink)

for component in [datasource, llm, sink]:
    component.validate_can_operate_at_level(operating_level)
    # ✅ If validation fails, abort BEFORE loading data

# Only execute if all validations pass
datasource.load_data()
```

**Contrast with "fail-later"**: Validate clearances during execution (too late - data already in memory)

**Important Note**: With automatic `operating_level` computation (the default), validation failures only occur in two scenarios:
1. **Manual override**: Operators force a higher operating level via configuration
2. **Frozen plugins** (ADR-005): Plugins with **explicitly set** `allow_downgrade=False` refuse to operate below their declared level

Under normal operation, `operating_level = min(all clearances)`, so all components can always pass validation. This design ensures fail-fast catches **configuration errors** and **frozen plugin violations** rather than blocking normal pipeline composition.

**Developer Requirement**: Every plugin must explicitly set `allow_downgrade` (no default) - choose `True` for trusted downgrade or `False` for frozen enforcement.

**Related**: ADR-002 (Pipeline-wide minimum evaluation)

---

## Data Security Concepts

### SecureDataFrame

**Definition**: Immutable container for classified data that tracks security level and enforces access controls

**Pattern**: ADR-002-A "Trusted Container Model"

**Key Properties**:
- **Immutability**: Classification cannot be changed after creation
- **High water mark**: Classification can only increase (never decrease)
- **Stack inspection**: Validates caller identity before DataFrame access

**Example**:
```python
# Datasource creates classified frame (factory method required)
classified_df = SecureDataFrame.create_from_datasource(
    data=df,
    security_level=SecurityLevel.PROTECTED
)

# Data access is tracked but not validated at retrieval
# Validation occurs at hand-off to next component
df = classified_df.data  # Access underlying DataFrame
```

**Related**: ADR-002-A (Trusted Container Model)

---

### high water mark

**Definition**: Once data is classified at a certain level, it can only be **upgraded** (never downgraded)

**Rule**: `new_classification >= current_classification`

**Example (ALLOWED)**:
```python
# Datasource creates frame
df = SecureDataFrame.create_from_datasource(data, security_level=SecurityLevel.OFFICIAL)
# Upgrade allowed (enforced by max() operation)
df_upgraded = df.with_uplifted_security_level(SecurityLevel.SECRET)  # ✅ OK
```

**Example (FORBIDDEN)**:
```python
# Attempting to downgrade is prevented by with_uplifted_security_level() using max()
df = SecureDataFrame.create_from_datasource(data, security_level=SecurityLevel.SECRET)
# Attempting "downgrade" - max(SECRET, OFFICIAL) = SECRET (no downgrade occurs)
df_attempted_downgrade = df.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# Result: df_attempted_downgrade.classification == SECRET (not OFFICIAL)
```

**Rationale**: Prevents accidental declassification (data sensitivity never decreases)

**Related**: ADR-002-A (High water mark enforcement)

---

## Exception Taxonomy

### SecurityCriticalError

**Definition**: Exception for **security invariant violations** - conditions that should NEVER occur

**Policy**: ADR-006 "Fail-loud" policy (escalate, audit, alert) - proposed

**When to Use**:
- Invariant violations (impossible state reached)
- Bypassed security controls
- Tampered security metadata

**Example**:
```python
if classified_df.classification is None:
    raise SecurityCriticalError(
        "Classification is None - security invariant violated"
    )
    # This should NEVER happen (fail-loud)
```

**Handling**: Log, audit, escalate, ABORT immediately

**Related**: ADR-006 (Security-Critical Exception Policy - proposed)

---

### SecurityValidationError

**Definition**: Exception for **expected security checks** that fail during normal operation

**Policy**: ADR-006 "Fail-graceful" policy (audit, deny operation, continue if safe) - proposed

**When to Use**:
- Clearance check failures
- Access control denials
- Authentication failures

**Example**:
```python
if data.classification > plugin.security_level:
    raise SecurityValidationError(
        f"Insufficient clearance: required {data.classification}"
    )
    # Expected failure (user lacks clearance)
```

**Handling**: Audit log, deny operation, emit user-friendly error

**Related**: ADR-006 (Security-Critical Exception Policy - proposed)

---

## Audit & Compliance Concepts

### audit trail

**Definition**: Comprehensive, tamper-evident log of all security-relevant events

**Purpose**: Compliance (PSPF, HIPAA, PCI-DSS), incident response, forensics

**Required Events** (ADR-013 - draft):
- Authentication attempts
- Access denials (clearance violations)
- Data access (datasource loads)
- Classification changes
- Security validation failures

**Format**: JSONL (JSON Lines) for structured logging

**Retention**: 90 days minimum (compliance requirement)

**Related**: ADR-013 (Global Observability Policy - draft)

---

### correlation_id

**Definition**: UUIDv4 identifier that propagates through entire pipeline execution for request tracing

**Purpose**: Trace requests across components for debugging

**Format**: `550e8400-e29b-41d4-a716-446655440000` (UUIDv4)

**Propagation**: Via `PluginContext` object

**Example**:
```python
# Generated at entry
run_id = str(uuid.uuid4())
context = PluginContext(run_id=run_id, ...)

# Propagated to all plugins
def datasource_load(self, context: PluginContext):
    self.audit_logger.log_event(
        "datasource_load",
        correlation_id=context.run_id,  # ✅ Propagate
        ...
    )
```

**Related**: ADR-013 (Correlation ID propagation - draft)

---

## Architecture Pattern Concepts

### plugin context

**Definition**: Immutable object that propagates cross-cutting concerns (security, audit, correlation) through plugin stack

**Fields**:
- `security_level: SecurityLevel` - Operating security level
- `run_id: str` - Correlation ID
- `audit_logger: AuditLogger` - Audit logging interface
- `experiment_id: str | None` - Experiment correlation ID (optional)

**Immutability**: Plugins CANNOT modify context (read-only)

**Propagation**: Passed to all plugins via constructor or method arguments

**Example**:
```python
class PluginContext:
    security_level: SecurityLevel
    run_id: str
    audit_logger: AuditLogger
    # Immutable - no setters

# Usage
def write(self, results: dict, *, context: PluginContext):
    # Access context fields (read-only)
    context.audit_logger.log_event("write", correlation_id=context.run_id)
```

**Related**: ADR-004 (Plugin architecture)

---

## Common Misconceptions

### ❌ Misconception 1: "security_level" and "classification" are interchangeable

**Correction**:
- `security_level` = component's **capability** (what it CAN handle)
- `classification` = data's **constraint** (what protection REQUIRED)

**Example**:
```python
# Component clearance (capability)
sink.security_level = SecurityLevel.SECRET  # Can handle up to SECRET

# Data classification (constraint)
data.classification = SecurityLevel.PROTECTED  # Requires PROTECTED

# Access control check
if data.classification > sink.security_level:
    # Violation (PROTECTED > SECRET would be false, so no violation here)
```

---

### ❌ Misconception 2: Operating level is the HIGHEST security level in pipeline

**Correction**: Operating level is the **MINIMUM** (lowest clearance)

**Rationale**: Pipeline operates at the level of the LEAST capable component

**Example**:
```python
datasource.security_level = SecurityLevel.OFFICIAL  # Lowest
llm.security_level = SecurityLevel.SECRET
sink.security_level = SecurityLevel.SECRET

# Operating level = OFFICIAL (minimum, not maximum)
operating_level = min(OFFICIAL, SECRET, SECRET) = OFFICIAL
```

---

### ❌ Misconception 3: Insufficient clearance errors happen during normal pipeline operation

**Correction**: Insufficient clearance errors **only occur in specific scenarios**, not during normal operation

**Automatic Behavior**: With default automatic computation, `operating_level = min(all clearances)`, so every component can always operate at or above the minimum. Insufficient clearance errors are **impossible** under normal circumstances.

**When Errors Occur**: Only in two scenarios:
1. **Manual override**: Operators force a higher operating level via configuration
2. **Frozen plugins** (ADR-005): Plugins with **explicitly set** `allow_downgrade=False` refuse to operate below their declared level

**Critical Design Choice**: `allow_downgrade` has **no default** - every plugin developer must explicitly choose `True` (trusted downgrade) or `False` (frozen). This forces security-conscious decisions at plugin creation time.

**Example (Manual Override Required)**:
```python
# Component clearances (automatic)
datasource.security_level = SecurityLevel.OFFICIAL  # Lowest
llm.security_level = SecurityLevel.SECRET
sink.security_level = SecurityLevel.SECRET

# Automatic computation (default)
operating_level = min(OFFICIAL, SECRET, SECRET) = OFFICIAL
# ✅ All components can operate at OFFICIAL (no errors possible)

# Manual override (configuration setting)
forced_operating_level = SecurityLevel.SECRET  # Operator forces higher level

# Now datasource cannot operate (OFFICIAL clearance < SECRET required)
if forced_operating_level > datasource.security_level:
    raise SecurityValidationError("Insufficient clearance")  # ❌ Error occurs
```

**Rationale**: This design makes misconfiguration (manual override errors) explicit and fail-fast, while allowing normal pipeline composition to always succeed.

---

### ❌ Misconception 4: Fail-closed means "abort on any error"

**Correction**: Fail-closed means "deny operation when **security cannot be validated**"

**Non-security errors**: May use other strategies (retry, skip) per ADR-011 (draft)

**Example**:
```python
# Security validation failure → fail-closed (ABORT)
if cannot_validate_clearance():
    raise SecurityValidationError(...)  # ✅ Abort

# Network timeout → retry (NOT fail-closed)
if network_timeout():
    retry_with_backoff()  # ✅ Retry (not security-related)
```

---

### ❌ Misconception 5: Plugins default to trusted downgrade (allow_downgrade=True)

**Correction**: `allow_downgrade` has **NO DEFAULT VALUE** - developers must explicitly choose

**Rationale**: Security-first design (ADR-001) requires explicit security decisions over implicit defaults

**Breaking Change**: Pre-ADR-005 versions defaulted to `True`, but current implementation **requires explicit choice**

**Example (CORRECT - explicit choice)**:
```python
# Trusted downgrade (EXPLICIT)
source = MyDatasource(
    security_level=SecurityLevel.SECRET,
    allow_downgrade=True  # ✅ Explicit choice required
)

# Frozen plugin (EXPLICIT)
frozen_sink = MyResultSink(
    security_level=SecurityLevel.SECRET,
    allow_downgrade=False  # ✅ Explicit choice required
)
```

**Example (INCORRECT - missing parameter)**:
```python
# ERROR: Missing allow_downgrade
plugin = MyPlugin(security_level=SecurityLevel.SECRET)
# Raises: TypeError - allow_downgrade is required (no default)
```

**Design Philosophy**: Forcing explicit choice prevents developers from unknowingly creating plugins that can downgrade. Every plugin author must consciously decide whether their component should be trusted to operate at lower classification levels.

---

## Quick Reference Table

| Term | Definition | Example Value | Where Used |
|------|------------|---------------|------------|
| `security_level` | Component clearance (capability) | `SecurityLevel.SECRET` | Plugin property |
| `classification` | Data label (constraint) | `SecurityLevel.PROTECTED` | SecureDataFrame |
| `operating_level` | Pipeline envelope (minimum) | `SecurityLevel.OFFICIAL` | Pipeline validation |
| `allow_downgrade` | Downgrade permission (REQUIRED, no default) | `True` or `False` | Plugin constructor |
| `correlation_id` | Request trace ID | `550e8400-...` | PluginContext.run_id |
| `audit_trail` | Security event log | JSONL file | `logs/run_*.jsonl` |
| `fail-closed` | Deny on validation failure | Raise exception | Security controls |
| `fail-fast` | Abort before data access | Pre-execution validation | Pipeline construction |

---

## Related Documentation

- **[ADR-001](decisions/001-design-philosophy.md)** – Fail-closed principle, security-first priority
- **[ADR-002](decisions/002-security-architecture.md)** – Bell-LaPadula MLS model, operating_level
- **[ADR-002-A](decisions/002-a-trusted-container-model.md)** – SecureDataFrame, high water mark
- **[ADR-004](decisions/004-mandatory-baseplugin-inheritance.md)** – Security bones pattern (proposed)
- **[ADR-005](decisions/005-frozen-plugin-capability.md)** – Frozen plugin capability (implemented)
- **[ADR-006](decisions/006-security-critical-exception-policy.md)** – Exception taxonomy (proposed)
- **[ADR-013](decisions/013-global-observability-policy.md)** – Audit trail, correlation IDs (draft)
- **[security-controls.md](security-controls.md)** – Security control implementation
- **[plugin-security-model.md](plugin-security-model.md)** – Plugin security architecture

---

**Maintained By**: Architecture Team
**Review Frequency**: After any security ADR change
**Version**: 1.0
