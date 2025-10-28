# ADR-002: Multi-Level Security Enforcement

## Status

**Accepted** (2025-10-23)

**Implementation Status**: Complete (Sprint 1, 2025-10-27)
- SecureDataFrame trusted container (ADR-002-A)
- Runtime clearance validation (`suite_runner.py`)
- BasePlugin security enforcement (ADR-004)
- Plugin type registry completeness (ADR-003)

**Related Documents**:
- [ADR-001: Design Philosophy](001-design-philosophy.md) – Security-first priority hierarchy
- [ADR-002-A: Trusted Container Model](002-a-trusted-container-model.md) – SecureDataFrame immutability enforcement
- [ADR-003: Central Plugin Registry](003-plugin-type-registry.md) – Unified registry architecture
- [ADR-004: Mandatory BasePlugin Inheritance](004-mandatory-baseplugin-inheritance.md) – Security enforcement foundation
- [ADR-005: Frozen Plugin Capability](005-frozen-plugin-capability.md) – Strict level enforcement option

## Context

### Problem Statement

Elspeth orchestrates secure data workflows that chain datasources, LLM transforms, and output sinks. Many deployments handle data with strict classification requirements mandated by regulatory frameworks:

- **Australian Government**: PSPF classifications (UNOFFICIAL → OFFICIAL → OFFICIAL:SENSITIVE → PROTECTED → SECRET)
- **Healthcare**: HIPAA Protected Health Information (PHI)
- **Financial Services**: PCI-DSS cardholder data
- **National Security**: Classified intelligence data

Traditional access control models rely solely on clearance checks at data consumption time ("can this component access this data?"). This approach has a critical vulnerability: by the time a clearance violation is detected, the pipeline may have already retrieved sensitive data into memory. We need a fail-fast mechanism that prevents pipeline execution from starting with misconfigured security levels.

### Regulatory Context

**Australian Government Requirements**:
- **ISM Control**: ISM-0037 (Classification and Sensitivity) – Information must be classified according to its sensitivity and handled appropriately
- **ISM Control**: ISM-0380 (Access Control) – Access to systems and data must be based on valid security clearances
- **PSPF Policy**: Policy 8 (Sensitive and Classified Information) – Information security classification must prevent unauthorised access
- **IRAP Assessment**: Security controls must be auditable with evidence of enforcement mechanisms

**Bell-LaPadula Multi-Level Security (MLS)**: Proven model for classified systems (developed by US Department of Defense, adopted internationally) providing mathematically sound security properties through:
- **No Read Up**: Subjects (plugins) cannot read data classified above their clearance
- **No Write Down**: Objects (data) cannot be downgraded to lower classifications
- **Tranquility Principle**: Security levels do not change during execution

### Attack Scenario: Misconfigured Pipeline Without Fail-Fast

**Configuration Error Example**:

```yaml
# config/experiments/classified_analysis.yaml
datasource:
  type: "secret_government_data"
  security_level: SECRET  # Datasource handles SECRET data

sinks:
  - type: "public_csv_export"
    path: "outputs/public_report.csv"
    security_level: UNOFFICIAL  # Sink only authorised for UNOFFICIAL data
```

**Without ADR-002 (Late Validation - Vulnerable)**:

1. Pipeline construction succeeds (no early validation)
2. **Datasource retrieves SECRET-classified data into memory** ← Security breach begins
3. Data flows through transforms (SECRET data in application memory)
4. At sink write time: Clearance check finally triggers
   - UNOFFICIAL sink detects it cannot write SECRET data
   - Pipeline aborts with error
5. **SECRET data has been loaded into memory** despite misconfiguration
6. Potential leakage through:
   - Memory dumps captured by monitoring tools
   - Error logs containing data snippets
   - Debugging outputs or stack traces
   - Process memory inspection (if attacker has system access)
   - Core dumps on crash

**Attack Surface**: Window where SECRET data exists in memory but cannot be safely written creates opportunity for data exfiltration through side channels.

**With ADR-002 (Fail-Fast Validation - Secure)**:

1. Pipeline construction computes operating level:
   ```python
   operating_level = min(SECRET datasource, UNOFFICIAL sink) = UNOFFICIAL
   ```
2. **Validation occurs before data retrieval**:
   - Datasource validates: "Can I operate at UNOFFICIAL level?"
   - Answer: NO (datasource has insufficient clearance for UNOFFICIAL-only pipeline)
   - Alternatively: YES if datasource is certified for trusted downgrade (see Trusted Downgrade Model)
3. **Pipeline aborts BEFORE data retrieval** → No classified data loaded into memory
4. Safe failure: Configuration error detected at pipeline construction time, zero exposure

**Security Property**: Fail-fast eliminates the vulnerable window where classified data exists in memory but cannot be safely handled, preventing data leakage through error handling, logging, or debugging pathways.

**ISM Control Mapping**: This fail-fast mechanism implements:
- ISM-0380 (Access Control) – Prevents components with insufficient clearance from accessing data
- ISM-1084 (Event Logging) – All validation failures are logged before data access
- ISM-1433 (Error Handling) – Errors prevent execution rather than allowing degraded security

### Comparison to Traditional Access Control

| Approach | Validation Timing | Data Exposure Risk | Failure Mode | Compliance Posture |
|----------|-------------------|-------------------|--------------|-------------------|
| **Traditional ACL** | Runtime (data access time) | HIGH – Data in memory before rejection | Late detection, potential leakage | Difficult to audit |
| **ADR-002 MLS** | Pipeline construction (pre-execution) | ZERO – Validation before data retrieval | Early detection, safe abort | Clear audit trail |

**Key Insight**: Traditional access control checks "what data can you access?" at access time. ADR-002 checks "what security level will this pipeline operate at?" before any data is accessed, implementing defence-in-depth through fail-fast validation.

## Decision

We will adopt a **Bell-LaPadula Multi-Level Security (MLS) model** with fail-fast enforcement through a two-layer security architecture:

### Layer 1: Plugin Clearance (Bell-LaPadula "No Read Up")

**Purpose**: Prevent components with insufficient clearance from participating in classified pipelines.

**Mechanism**:

1. **Security Level Declarations**: All plugins declare a `security_level` representing their security clearance (e.g., `UNOFFICIAL`, `OFFICIAL`, `OFFICIAL:SENSITIVE`, `PROTECTED`, `SECRET` per Australian PSPF classification framework).

2. **Pipeline-Wide Operating Level Computation**: Before execution, the orchestrator computes the minimum security level across all pipeline components (datasource, transforms, sinks):

   ```python
   operating_level = min(
       datasource.security_level,
       *[transform.security_level for transform in transforms],
       *[sink.security_level for sink in sinks]
   )
   ```

3. **Fail-Fast Clearance Validation**: Each component validates whether it can operate at the computed `operating_level`:
   - Components with clearance LOWER than `operating_level` **reject operation** (insufficient clearance - Bell-LaPadula "no read up")
   - Components with clearance HIGHER than or EQUAL to `operating_level` **accept operation** (sufficient clearance)

4. **Trusted Downgrade Model**: Components with clearance HIGHER than `operating_level` are **trusted to filter/downgrade data** appropriately when operating at lower levels (see detailed explanation below).

5. **Early Abort**: Pipeline aborts at construction time if any component has insufficient clearance, preventing data retrieval.

**Implementation Location**:
- Operating level computation: `src/elspeth/core/experiments/suite_runner.py:40` (`compute_minimum_clearance_envelope()`)
- Validation enforcement: `src/elspeth/core/experiments/suite_runner.py:724-734` (`_validate_experiment_security()`)
- Plugin validation API: `src/elspeth/core/base/plugin.py:96-97` (`validate_can_operate_at_level()`)

### Layer 2: Data Classification (Bell-LaPadula "No Write Down")

**Purpose**: Ensure data classification cannot be downgraded once established.

**Mechanism**:

1. **Immutable Classification**: `SecureDataFrame` is a frozen dataclass – once data is tagged with a security level, that classification cannot be reduced.

2. **No Downgrade API**: `SecureDataFrame` provides only `with_uplifted_security_level()` for increasing classification – no method exists to downgrade.

3. **Runtime Prevention**: Attempting to construct a `SecureDataFrame` with lower classification triggers runtime error (frozen dataclass prevents modification).

4. **Automatic Uplifting**: When data flows through higher-clearance transforms, classification automatically increases via `max()` operation.

**Implementation Location**:
- Container definition: `src/elspeth/core/security/secure_data.py:26-64` (`SecureDataFrame` frozen dataclass)
- Constructor protection: `src/elspeth/core/security/secure_data.py:70-100` (`__post_init__` validation)
- Uplifting API: `SecureDataFrame.with_uplifted_security_level()` method

### Bell-LaPadula Architectural Split: Critical Concept

Understanding the **architectural separation** between data classification enforcement and plugin clearance enforcement is essential for correctly implementing, auditing, and certifying security policies in Elspeth.

#### The Two Enforcement Layers Explained

**Layer 2-A: Data Classification Layer (Bell-LaPadula "No Write Down")**

| Property | Details |
|----------|---------|
| **Controls** | `SecureDataFrame` objects (data containers) |
| **Enforcement Mechanism** | Immutable classification via frozen dataclass |
| **Security Rule** | Data tagged SECRET cannot be downgraded to UNOFFICIAL |
| **Implementation** | Runtime prevention – no downgrade method exists, only `with_uplifted_security_level()` |
| **Violation Example** | Attempting to write `SecureDataFrame(data, SecurityLevel.SECRET)` to UNOFFICIAL sink |
| **Failure Mode** | TypeError or AttributeError (no downgrade API available) |
| **ADR Reference** | ADR-002-A (Trusted Container Model) |

**Layer 1-A: Plugin Clearance Layer (Bell-LaPadula "No Read Up")**

| Property | Details |
|----------|---------|
| **Controls** | Plugin operations (datasource retrieval, transform processing, sink writes) |
| **Enforcement Mechanism** | Clearance validation via `BasePlugin.validate_can_operate_at_level()` |
| **Security Rule** | Plugin with UNOFFICIAL clearance cannot operate at SECRET level (insufficient clearance) |
| **Implementation** | Pipeline construction time – fail-fast before data retrieval |
| **Violation Example** | UNOFFICIAL datasource forced to participate in SECRET pipeline |
| **Failure Mode** | `SecurityValidationError` raised during pipeline setup, execution aborted |
| **ADR Reference** | ADR-002 (this document), ADR-004 (BasePlugin enforcement) |

**Layer 1-B: Trusted Downgrade Layer (Plugin Operation Flexibility)**

| Property | Details |
|----------|---------|
| **Enables** | Plugins with SECRET clearance **can** operate at UNOFFICIAL level (if `allow_downgrade=True`) |
| **Trust Model** | Certified plugins are responsible for filtering data appropriately at lower operating levels |
| **Enforcement Mechanism** | Certification + audit + code review (NOT runtime validation) |
| **Example** | SECRET Azure datasource operating at UNOFFICIAL level filters to only retrieve UNOFFICIAL-classified blobs |
| **Responsibility** | Plugin author implements filtering logic; certification process validates correctness |
| **ADR Reference** | ADR-002 (this document), ADR-005 (Frozen Plugin option to disable trusted downgrade) |

#### Common Misconception: SECRET Datasource → UNOFFICIAL Sink

**Incorrect Understanding**: "SECRET datasource writing to UNOFFICIAL sink violates Bell-LaPadula 'no write down' rule."

**Correct Understanding**:

1. **Operating Level Computation**:
   ```python
   operating_level = min(
       datasource.security_level=SECRET,
       sink.security_level=UNOFFICIAL
   )
   # Result: operating_level = UNOFFICIAL
   ```

2. **Datasource Clearance Validation**:
   ```python
   datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
   # Checks: Can SECRET-cleared datasource operate at UNOFFICIAL level?
   # Answer: YES (trusted downgrade permitted if allow_downgrade=True)
   ```

3. **Datasource Operation at Lower Level**:
   - Datasource operates at UNOFFICIAL level (not SECRET level)
   - Produces: `SecureDataFrame(data, SecurityLevel.UNOFFICIAL)`
   - Data is UNOFFICIAL-classified (datasource filtered appropriately)

4. **Sink Reception**:
   - UNOFFICIAL sink receives `SecureDataFrame(data, SecurityLevel.UNOFFICIAL)`
   - Classification matches sink clearance: ✅ **No violation**

**Key Security Property**: The SECRET-cleared datasource **does not produce SECRET data** when operating at UNOFFICIAL level. It is trusted and certified to filter data sources appropriately and produce only UNOFFICIAL-classified data. This filtering responsibility is validated through:

- **Certification Process**: Pre-deployment security audit
- **Code Review**: Architecture team review of datasource filtering logic
- **Attestation Documentation**: Written evidence of multi-level filtering capability
- **Certification Tests**: Automated tests demonstrating correct filtering at all supported levels
- **NOT Runtime Enforcement**: System trusts certified plugins to implement filtering correctly

**What WOULD Be a Violation**:

If the datasource produced `SecureDataFrame(data, SecurityLevel.SECRET)` while operating at UNOFFICIAL level, the sink would reject it:

```python
# Buggy/malicious datasource returns wrong classification
data = SecureDataFrame(secret_data, SecurityLevel.SECRET)  # ❌ BUG: Wrong level

sink.write(data)  # ❌ FAILS: Sink validation rejects SECRET data
# SecureDataFrame cannot be downgraded (immutability), so sink must reject
# This is "no write down" protection working correctly
```

**Defence-in-Depth**: Even if a datasource misbehaves and returns data with wrong classification, the SecureDataFrame immutability prevents downgrade at the sink, providing a second layer of protection.

#### Architectural Asymmetry Summary

The Bell-LaPadula MLS model in Elspeth exhibits intentional asymmetry between the two layers:

```
Layer 2: Data Classification (Immutable)
  UNOFFICIAL → OFFICIAL → OFFICIAL:SENSITIVE → PROTECTED → SECRET
  (Can only increase via explicit uplift)
  Enforcement: SecureDataFrame frozen dataclass (ADR-002-A)

Layer 1: Plugin Operation (Flexible)
  SECRET → PROTECTED → OFFICIAL:SENSITIVE → OFFICIAL → UNOFFICIAL
  (Can decrease via trusted downgrade if allow_downgrade=True)
  Enforcement: BasePlugin.validate_can_operate_at_level() + certification (ADR-004)
```

**Forbidden Operations** (Violations):

| Operation | Layer | Violation Type | Result |
|-----------|-------|----------------|--------|
| UNOFFICIAL plugin operating at SECRET level | Plugin Clearance | Insufficient clearance ("no read up") | `SecurityValidationError` |
| SECRET `SecureDataFrame` downgraded to UNOFFICIAL | Data Classification | Impossible operation ("no write down") | TypeError (no downgrade API exists) |
| Frozen plugin operating below declared level | Plugin Clearance | Strict enforcement violation (ADR-005) | `SecurityValidationError` |

**Allowed Operations**:

| Operation | Layer | Justification | Validation Method |
|-----------|-------|---------------|-------------------|
| SECRET plugin operating at UNOFFICIAL level | Plugin Clearance | Trusted downgrade (if `allow_downgrade=True`) | Certification process |
| UNOFFICIAL data uplifted to SECRET | Data Classification | Explicit classification increase | `with_uplifted_security_level()` API |
| Frozen plugin operating at exact declared level | Plugin Clearance | Strict enforcement (ADR-005) | Exact level match only |

**See Also**: [ADR-005: Frozen Plugin Capability](005-frozen-plugin-capability.md) for detailed specification of strict level enforcement behaviour when `allow_downgrade=False`.

#### Enforcement Mechanisms Comparison

| Layer | Rule | Enforced By | Timing | Failure Mode | Audit Evidence |
|-------|------|-------------|--------|--------------|----------------|
| **Data Classification** | No write down | `SecureDataFrame` immutability | Runtime (object construction) | TypeError (no downgrade method) | Stack trace, error log |
| **Plugin Clearance** | No read up | `BasePlugin.validate_can_operate_at_level()` | Pipeline construction (pre-execution) | `SecurityValidationError` | Audit log, pipeline config |
| **Trusted Downgrade** | Higher clearance can operate lower | Certification + code review | Pre-deployment | Manual audit failure | Certification documentation |

**Security Principle**: Plugins with HIGHER clearance can operate at LOWER levels (trusted to filter appropriately). Plugins with LOWER clearance CANNOT operate at HIGHER levels (insufficient clearance prevents participation).

**Datasource Filtering Responsibility**: When a SECRET-cleared datasource operates at an OFFICIAL pipeline level, it **must** filter its data retrieval to produce only OFFICIAL-classified data. This responsibility is validated through:

1. **Pre-Deployment Certification Audit**: Security team reviews datasource code before production deployment
2. **Filtering Logic Code Review**: Architecture team verifies correct implementation of multi-level filtering
3. **Attestation Documentation**: Written statement from plugin author documenting filtering behaviour across all supported levels
4. **Certification Test Suite**: Automated tests demonstrating datasource produces correct classification at all operating levels
5. **NOT Runtime Enforcement**: System trusts certified plugins to implement filtering correctly (runtime validation would require re-inspecting all retrieved data, defeating performance benefits of trusted model)

### Trusted Downgrade Model: Certification Requirements

The trusted downgrade model allows high-clearance plugins to operate in lower-clearance pipelines, enabling operational flexibility while maintaining security. This trust is established through rigorous certification processes, not runtime enforcement.

#### When Trusted Downgrade Applies

**Scenario**: Pipeline contains components with different security clearances.

**Example Configuration**:
```yaml
datasource:
  type: "azure_classified_storage"
  security_level: SECRET  # Can access UNOFFICIAL→SECRET blobs
  allow_downgrade: true   # Permit trusted downgrade

sink:
  type: "local_csv"
  security_level: UNOFFICIAL  # Can only write UNOFFICIAL data
```

**Operating Level Computation**:
```python
operating_level = min(SECRET, UNOFFICIAL) = UNOFFICIAL
```

**Clearance Validation**:
- Datasource validates: `Can I operate at UNOFFICIAL?`
  - Clearance: SECRET (sufficient for UNOFFICIAL level)
  - Allow downgrade: True (permits operating below declared level)
  - **Result**: ✅ Validation passes
- Sink validates: `Can I operate at UNOFFICIAL?`
  - Clearance: UNOFFICIAL (exact match)
  - **Result**: ✅ Validation passes

**Runtime Execution**:
```python
# Datasource operates at UNOFFICIAL level
data = datasource.load_data()
# Datasource filters to only retrieve UNOFFICIAL-classified blobs
# Returns: SecureDataFrame(df, SecurityLevel.UNOFFICIAL)

sink.write(data)  # ✅ Succeeds: UNOFFICIAL sink receiving UNOFFICIAL data
```

**Critical Security Property**: The datasource does NOT retrieve SECRET data when operating at UNOFFICIAL level. It filters its data source to only access blobs/records tagged as UNOFFICIAL.

#### Certification Process for Trusted Downgrade Plugins

Plugins implementing trusted downgrade must undergo certification before production deployment:

**1. Code Review Requirements**:
- Architecture team reviews filtering logic for all supported security levels
- Verification that datasource correctly interprets security level metadata (e.g., blob tags, database columns)
- Confirmation that operating level is used for filtering, not just for classification

**2. Documentation Requirements**:
- **Filtering Behaviour Specification**: Written description of how plugin filters data at each supported level
- **Threat Model**: Analysis of what could go wrong if filtering fails
- **Attestation Statement**: Plugin author signs statement confirming correct implementation

**3. Test Coverage Requirements**:
- **Multi-Level Test Data**: Test suite must include data at all supported security levels
- **Operating Level Tests**: Automated tests for each supported operating level (UNOFFICIAL, OFFICIAL, SECRET, etc.)
- **Filtering Verification Tests**: Tests that verify only appropriate data is retrieved at each level
- **Classification Accuracy Tests**: Tests that verify returned `SecureDataFrame` has correct classification

**Example Certification Test Pattern**:

```python
def test_secret_datasource_filters_at_unofficial_level():
    """Verify SECRET-cleared datasource filters correctly at UNOFFICIAL level.

    Certification Requirement: Datasource must demonstrate correct filtering
    when operating at levels below its declared clearance.
    """
    # Setup: SECRET-cleared datasource with mixed-classification data source
    datasource = AzureClassifiedBlobDatasource(
        security_level=SecurityLevel.SECRET,
        allow_downgrade=True,
        storage_account="test_account",
        container="classified_data",
    )

    # Simulate multi-level data source (blobs tagged with classifications)
    # - blob_unofficial.csv (tagged: classification=UNOFFICIAL)
    # - blob_official.csv (tagged: classification=OFFICIAL)
    # - blob_secret.csv (tagged: classification=SECRET)

    # Force datasource to operate at UNOFFICIAL level
    datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
    context = PluginContext(
        plugin_name="test_datasource",
        plugin_kind="datasource",
        security_level=SecurityLevel.SECRET,
        operating_level=SecurityLevel.UNOFFICIAL,  # Pipeline operating level
    )
    datasource.plugin_context = context

    # Execute: Load data at UNOFFICIAL operating level
    result = datasource.load_data()

    # Verify filtering correctness:
    # 1. Returned classification matches operating level
    assert result.security_level == SecurityLevel.UNOFFICIAL

    # 2. Only UNOFFICIAL blobs were retrieved (filtering worked)
    assert "blob_unofficial.csv" in result.data["source_blob"].values
    assert "blob_official.csv" not in result.data["source_blob"].values  # Filtered out
    assert "blob_secret.csv" not in result.data["source_blob"].values    # Filtered out

    # 3. Datasource correctly reports effective level
    assert datasource.get_effective_level() == SecurityLevel.UNOFFICIAL

    # 4. Audit logging includes effective level
    # (Verify through log inspection in integration tests)
```

**4. Audit Evidence Requirements**:
- Certification test results must be included in deployment package
- Test coverage report showing all security levels tested
- Code review sign-off from architecture team member with security clearance
- Attestation document signed by plugin author

**5. Re-Certification Triggers**:
- Any modification to filtering logic
- Addition of new security levels
- Change to data source schema or metadata structure
- Discovery of filtering bug in production

#### When Trusted Downgrade is Disallowed: Frozen Plugins (ADR-005)

**Use Case**: Organisations with strict operational security requirements where plugins must NEVER operate below their declared level.

**Configuration**:
```python
datasource = SecretOnlyDatasource(
    security_level=SecurityLevel.SECRET,
    allow_downgrade=False,  # Frozen plugin - strict level enforcement
)
```

**Behaviour**:
- Plugin with `allow_downgrade=False` will ONLY operate at its exact declared level
- Attempting to include frozen SECRET plugin in UNOFFICIAL pipeline triggers `SecurityValidationError`
- Use case: Dedicated classification domains (physically/logically separated by level)

**When to Use Frozen Plugins**:
- ✅ Dedicated classification domains (separate SECRET-only infrastructure)
- ✅ Regulatory mandates requiring explicit per-level certification
- ✅ High-assurance systems where filtering trust is insufficient
- ❌ General-purpose deployments (default trusted-downgrade is simpler)
- ❌ Mixed-classification workflows (frozen plugins break multi-level orchestration)

**See**: [ADR-005: Frozen Plugin Capability](005-frozen-plugin-capability.md) for complete specification, implementation details, test patterns, and migration guidance.

### Exposing Operating Level to Plugins

#### Context

Plugin authors need to make security-aware decisions based on the pipeline's effective operating level (the computed minimum clearance envelope), not just their declared clearance. This enables plugins to:

1. **Optimise Data Retrieval**: Datasources filter to only fetch data at required level
2. **Conditional Processing**: Transforms apply security controls appropriate for operating level
3. **Audit Logging**: Record effective level for compliance verification
4. **Performance Tuning**: Use lighter-weight algorithms at lower security levels

#### Implementation

The pipeline operating level is exposed to plugins through:

**API Method**: `BasePlugin.get_effective_level() -> SecurityLevel`

**Access Pattern**:
```python
class SecretAzureDatasource(BasePlugin):
    def load_data(self) -> SecureDataFrame:
        effective_level = self.get_effective_level()  # Returns pipeline operating level
        declared_level = self.get_security_level()     # Returns plugin's clearance

        # Filter data retrieval based on effective level
        if effective_level == SecurityLevel.UNOFFICIAL:
            blobs = self._fetch_blobs_with_tag("classification:unofficial")
        elif effective_level == SecurityLevel.SECRET:
            blobs = self._fetch_blobs_with_tag("classification:unofficial|official|secret")

        return SecureDataFrame(data, security_level=effective_level)
```

**Context Propagation**:
1. `ExperimentSuiteRunner` computes `operating_level = min(all plugin clearances)`
2. `_propagate_operating_level()` updates all plugin contexts
3. Plugins access via `self.get_effective_level()`

**Location**: `src/elspeth/core/experiments/suite_runner.py:557-565` (`_propagate_operating_level()`)

#### Terminology Clarification

Critical distinction between two security level concepts:

| Term | Meaning | Set By | Accessed Via | Semantics |
|------|---------|--------|--------------|-----------|
| **security_level** (declared clearance) | Maximum level plugin CAN handle | Plugin author at definition time | `self.get_security_level()` | Static, immutable, defines capability |
| **operating_level** (effective level) | Level plugin SHOULD operate at | Pipeline orchestrator at construction time | `self.get_effective_level()` | Dynamic, computed from pipeline composition |

**Example**:
```python
# SECRET datasource in UNOFFICIAL pipeline
datasource.get_security_level()   # Returns: SecurityLevel.SECRET (declared clearance)
datasource.get_effective_level()  # Returns: SecurityLevel.UNOFFICIAL (pipeline operating level)
```

**Security Invariant**: `operating_level <= security_level` (always true after validation)

#### Correct Usage Patterns

Plugins should use `get_effective_level()` for:

**✅ Pattern 1: Filtering Optimisation (Datasources)**

```python
def load_data(self) -> SecureDataFrame:
    """Retrieve data filtered to pipeline operating level."""
    effective_level = self.get_effective_level()

    # Filter data retrieval to only fetch records at effective level
    if effective_level == SecurityLevel.UNOFFICIAL:
        records = self.db.query("SELECT * FROM data WHERE classification = 'UNOFFICIAL'")
    elif effective_level == SecurityLevel.OFFICIAL:
        records = self.db.query("SELECT * FROM data WHERE classification IN ('UNOFFICIAL', 'OFFICIAL')")
    elif effective_level == SecurityLevel.SECRET:
        records = self.db.query("SELECT * FROM data WHERE classification IN ('UNOFFICIAL', 'OFFICIAL', 'SECRET')")

    # Tag retrieved data at effective level (datasource is responsible for correct filtering)
    return SecureDataFrame(records, security_level=effective_level)
```

**Security Note**: Datasource filtering logic must be certified (see Certification Requirements above).

**✅ Pattern 2: Conditional Security Processing (Transforms)**

```python
def transform(self, df: SecureDataFrame) -> SecureDataFrame:
    """Apply security controls appropriate for operating level."""
    effective_level = self.get_effective_level()

    # Apply expensive compliance checks only at higher security levels
    if effective_level >= SecurityLevel.PROTECTED:
        df = self._apply_hipaa_phi_redaction(df)
        df = self._apply_audit_logging_enhancement(df)

    # Apply standard processing at all levels
    df = self._standard_transformation(df)

    return df
```

**✅ Pattern 3: Audit Logging (All Plugins)**

```python
def load_data(self) -> SecureDataFrame:
    """Log security context for audit compliance."""
    effective_level = self.get_effective_level()
    declared_level = self.get_security_level()

    self.logger.info(
        "Datasource operating at effective level",
        declared_clearance=declared_level.name,
        effective_level=effective_level.name,
        downgrading=effective_level < declared_level,  # Trusted downgrade flag
        component_id=self.plugin_context.plugin_name,
    )

    return self._load_filtered_data()
```

**ISM Control**: ISM-0580 (Event Logging) – Security-relevant events must be logged with sufficient detail.

**✅ Pattern 4: Performance Optimisation (All Plugins)**

```python
def process(self, data: SecureDataFrame) -> SecureDataFrame:
    """Use algorithms appropriate for security level."""
    effective_level = self.get_effective_level()

    # Use different algorithms based on security requirements
    if effective_level >= SecurityLevel.SECRET:
        # Use memory-safe, timing-attack-resistant algorithms
        return self._constant_time_secure_processing(data)
    else:
        # Use faster standard algorithms
        return self._optimised_standard_processing(data)
```

#### Anti-Patterns (Forbidden)

**❌ Anti-Pattern 1: Bypassing Filtering**

```python
# WRONG: Skipping filtering based on effective level
def load_data(self):
    if self.get_effective_level() == self.get_security_level():
        # "No filtering needed - levels match"
        return self._load_all_data()  # ❌ May include higher-classified data!
    else:
        return self._load_filtered_data()
```

**Why Wrong**: Even when levels match, datasource must filter correctly. The multi-level data source may contain data ABOVE the operating level that must be excluded. Filtering is ALWAYS required based on operating level.

**Correct Pattern**:
```python
def load_data(self):
    effective_level = self.get_effective_level()
    # ALWAYS filter based on effective level, regardless of declared level
    return self._load_filtered_data(max_classification=effective_level)
```

**❌ Anti-Pattern 2: Assuming Operating Level Determines Data Classification**

```python
# WRONG: Assuming effective level is the data classification
def load_data(self):
    data = self._fetch_all_data()
    effective_level = self.get_effective_level()
    # "Data is at effective level, so tag it as such"
    return SecureDataFrame(data, effective_level)  # ❌ Data may actually be UNOFFICIAL!
```

**Why Wrong**: Operating level is a pipeline constraint, not data classification. Data classification is determined by content and source, not pipeline configuration. Even if operating level is SECRET, the retrieved data might be UNOFFICIAL if that's what the data source contains.

**Correct Pattern**:
```python
def load_data(self):
    effective_level = self.get_effective_level()
    # Filter to retrieve only data at effective level
    data = self._fetch_data_with_classification(effective_level)
    # Verify retrieved data actually matches requested classification
    actual_classification = self._determine_data_classification(data)
    return SecureDataFrame(data, security_level=actual_classification)
```

**❌ Anti-Pattern 3: Skipping Validation Based on Level**

```python
# WRONG: Bypassing validation based on effective level
def validate_data(self, data: SecureDataFrame):
    if self.get_effective_level() == SecurityLevel.UNOFFICIAL:
        return  # "No validation needed at low level" ❌
    else:
        self._validate_schema(data)
```

**Why Wrong**: Validation requirements are independent of security level. All data must be validated according to schema and business rules regardless of classification. Security level affects access control, not data integrity requirements.

**Correct Pattern**:
```python
def validate_data(self, data: SecureDataFrame):
    # ALWAYS validate regardless of security level
    self._validate_schema(data)
    self._validate_business_rules(data)

    # Apply additional security-level-specific validation if needed
    if self.get_effective_level() >= SecurityLevel.PROTECTED:
        self._validate_pii_redaction(data)
```

#### Security Properties

**Fail-Loud Enforcement**:

```python
@final
def get_effective_level(self) -> SecurityLevel:
    """Return pipeline operating level (effective level).

    Raises:
        RuntimeError: If operating_level not yet set (pre-validation state).
                      This is intentional fail-loud behaviour.
    """
    if self.plugin_context.operating_level is None:
        raise RuntimeError(
            f"{self.plugin_context.plugin_name}: operating_level not set. "
            "This is a programming error - validate_can_operate_at_level() "
            "must be called before get_effective_level()."
        )
    return self.plugin_context.operating_level
```

**Design Rationale**:
- **No graceful degradation**: Raises `RuntimeError` if `operating_level` is `None` (pre-validation state)
- **No fallback to `security_level`**: Prevents accidental use of wrong level
- **Loud catastrophic failure**: Catches programming errors early (ADR-001 security-first principle)
- **Prevents unsafe defaults**: Forces developers to correctly implement validation sequence

**Immutability Guarantees**:
- `PluginContext` is frozen (Pydantic `frozen=True`) – plugins cannot modify `operating_level`
- `get_effective_level()` is `@final` (typing.final) – plugins cannot override implementation
- Operating level set once by orchestrator, never modified during execution (tranquility principle)

**Security Invariants**:
- `operating_level <= security_level` (guaranteed by validation before propagation)
- `operating_level` is same for all plugins in pipeline (single minimum computation)
- `operating_level` cannot be accessed before validation completes (fail-loud enforcement)

**Implementation Location**: `src/elspeth/core/base/plugin.py:96-97, 184-195` (BasePlugin class)

**See Also**: Complete API documentation in `BasePlugin.get_effective_level()` docstring.

## Consequences

### Benefits

**Security Benefits**:

1. **Fail-Fast Security Validation** ✅
   - Misconfigured pipelines (e.g., UNOFFICIAL datasource forced into SECRET pipeline) abort at construction time
   - Prevents insufficient-clearance components from accessing classified data
   - Zero exposure window – validation occurs before any data retrieval
   - **ISM Control**: ISM-0380 (Access Control) – Enforces clearance-based access restrictions

2. **Defence-in-Depth Architecture** ✅
   - Two-layer security model provides redundant protection:
     - Layer 1 (Plugin Clearance): Prevents low-clearance plugins from participating in high-security pipelines
     - Layer 2 (Data Classification): Prevents classification downgrade even if plugin layer fails
   - Certified datasources trusted to filter appropriately (certification process provides assurance)
   - **ISM Control**: ISM-0039 (Defence-in-Depth) – Multiple security controls for layered protection

3. **Clearance Upgrade Prevention** ✅
   - Blocks components from operating at levels ABOVE their declared clearance
   - Enforces Bell-LaPadula "no read up" rule mathematically
   - Prevents privilege escalation attacks through configuration manipulation
   - **ISM Control**: ISM-0380 (Access Control) – Role-based access control enforcement

4. **Trusted Downgrade Model** ✅
   - Components with HIGHER clearance can operate at LOWER levels (operational flexibility)
   - Certified datasources responsible for filtering data appropriately (e.g., SECRET-cleared Azure datasource operating at OFFICIAL level filters out SECRET-tagged blobs)
   - Certification process validates filtering correctness before deployment
   - Enables multi-level pipelines without separate infrastructure per classification level

5. **Regulatory Compliance Alignment** ✅
   - MLS model aligns with multiple security frameworks:
     - **Australian Government**: PSPF Policy 8 (Sensitive and Classified Information)
     - **Healthcare**: HIPAA Security Rule §164.308(a)(3) (Workforce Clearance Procedures)
     - **Financial Services**: PCI-DSS Requirement 7 (Restrict Access to Cardholder Data by Business Need to Know)
   - Clear audit trail for IRAP assessment
   - Evidence-based certification process

**Operational Benefits**:

6. **Clear Audit Trail** ✅
   - Every security validation decision logged with context
   - Operating level computation logged at pipeline construction
   - Plugin clearance validation results recorded
   - Supports forensic analysis and incident response

7. **Early Configuration Error Detection** ✅
   - Security misconfigurations detected at deployment time (pipeline construction)
   - Prevents runtime failures after data retrieval
   - Reduces incident response costs (configuration errors caught before production)

8. **Mathematical Security Properties** ✅
   - Bell-LaPadula MLS provides formally verifiable security properties
   - Operating level computation is deterministic: `operating_level = min(all plugin clearances)`
   - Security level ordering is total (every pair of levels is comparable)
   - Property-based testing validates invariants across all configurations

### Limitations and Trade-offs

**Governance Overhead**:

1. **Plugin Security Level Declaration Requirement** ⚠️
   - **Limitation**: Every plugin must declare accurate `security_level` and `allow_downgrade` flag
   - **Risk**: Incorrect declarations weaken security (e.g., plugin declared OFFICIAL but implements UNOFFICIAL handling)
   - **Mitigation Strategy**:
     - Plugin acceptance criteria mandate security level declaration and architecture review
     - Central plugin registry (`central_registry`) enforces security level presence at registration
     - Code review checklist includes security level accuracy verification
     - Certification process validates plugin behaviour matches declared level

2. **Certification Process for Trusted Downgrade** ⚠️
   - **Limitation**: Plugins using trusted downgrade require manual certification before production deployment
   - **Overhead**: 2-4 hours per plugin (code review, test verification, attestation documentation)
   - **Risk**: Certification backlog may delay plugin deployment
   - **Mitigation Strategy**:
     - Certification test patterns documented in ADR-002 (this document)
     - Automated certification test suite reduces manual review burden
     - Architecture team maintains certification capacity planning
     - Emergency fast-track process for critical plugins (with post-deployment audit)

**Trust Model Limitations**:

3. **Trust in Certified Datasources** ⚠️
   - **Limitation**: System trusts certified datasources correctly filter data when operating at lower levels (e.g., SECRET-cleared datasource filtering out SECRET blobs when running at OFFICIAL level)
   - **Risk**: Datasource filtering bug could leak higher-classified data into lower-clearance pipeline
   - **Mitigation Strategy**:
     - Certification process validates datasource filtering logic through code review
     - Datasources must demonstrate correct behaviour across all supported security levels in certification tests
     - Re-certification required after any modification to filtering logic
     - Defence-in-depth: SecureDataFrame immutability prevents classification downgrade even if datasource misbehaves
   - **Trade-off Rationale**: Runtime validation of every retrieved record would require re-inspecting all data, defeating performance benefits of trusted model. Certification provides adequate assurance with acceptable overhead.

**Pipeline Design Constraints**:

4. **Pipeline Minimum Computation Impact** ⚠️
   - **Limitation**: Pipeline operating level is MINIMUM of all component clearances, meaning single low-clearance component (e.g., UNOFFICIAL sink) causes entire pipeline to operate at that lower level
   - **Impact**: High-clearance datasources must filter data accordingly, potentially excluding higher-classified data even though datasource could access it
   - **Mitigation Strategy**:
     - This is intentional defence-in-depth (see ADR-001 security-first principle)
     - Operators can isolate sensitive operations into separate pipelines if full data access needed
     - Pipeline composition guidance documents common patterns for multi-level workflows
   - **Trade-off Rationale**: MIN computation enforces weakest-link security model, preventing accidental data exposure through low-clearance components

5. **No Dynamic Reclassification During Execution** ⚠️
   - **Limitation**: Security levels are static at pipeline configuration time; cannot dynamically upgrade/downgrade classification during execution
   - **Impact**: Cannot adapt to data-driven classification decisions (e.g., classifying data based on content analysis during execution)
   - **Mitigation Strategy**:
     - This prevents time-of-check to time-of-use (TOCTOU) vulnerabilities
     - Operators configure separate pipelines for different classification levels
     - Future enhancement: Pre-execution classification analysis pipeline feeding into execution pipeline
   - **Trade-off Rationale**: Static levels simplify audit and prevent TOCTOU attacks; operational flexibility through multiple pipelines is acceptable trade-off

**Testing and Verification Overhead**:

6. **Comprehensive Security Test Coverage Required** ⚠️
   - **Limitation**: Security level enforcement must be validated in integration tests with misconfigured pipeline scenarios
   - **Overhead**: 15-20% test suite increase for security validation tests
   - **Mitigation Strategy**:
     - Dedicated test modules for ADR-002 properties (`tests/test_adr002_*.py`)
     - Property-based testing with Hypothesis for invariant validation across random configurations
     - Certification test templates reduce per-plugin test writing burden

### Implementation Impact

**Code Modifications Required**:

1. **Plugin Definitions** 📝
   - Security level metadata lives on each plugin definition (`security_level` field in config)
   - Plugins must declare `allow_downgrade` flag in constructor (True for trusted downgrade, False for frozen behaviour)
   - Location: Plugin class `__init__()` methods across all plugin types

2. **Suite Runner Changes** 📝
   - Prior to plugin instantiation, suite runner computes minimum security level: `operating_level = min(all plugin clearances)`
   - Enforcement via plugin registry/context propagation
   - Location: `src/elspeth/core/experiments/suite_runner.py:724-734` (`_validate_experiment_security()`)

3. **Plugin Validation Interface** 📝
   - All BasePlugin subclasses inherit `validate_can_operate_at_level()` method (concrete implementation, not abstract)
   - Datasources and sinks validate operating level does not exceed declared clearance
   - Raises `SecurityValidationError` and aborts run if insufficient clearance detected
   - Components with higher clearance can operate at lower levels (trusted downgrade)
   - Location: `src/elspeth/core/base/plugin.py:184-227` (BasePlugin class)

4. **Clearance Enforcement Helpers** 📝
   - Clearance checks enforced in plugin interfaces preventing forced operation above declared level
   - Components with SECRET clearance can serve data at lower classification levels (OFFICIAL, UNOFFICIAL) by filtering appropriately
   - Helper function: `compute_minimum_clearance_envelope()` in suite runner
   - Location: `src/elspeth/core/experiments/suite_runner.py:40-60`

5. **Security Container Implementation** 📝
   - `SecureDataFrame` frozen dataclass enforces immutable classification
   - Constructor protection prevents plugins from creating arbitrary classifications (datasource-only creation)
   - Uplifting API: `with_uplifted_security_level()` (no downgrade API exists)
   - Location: `src/elspeth/core/security/secure_data.py:26-100`

6. **Testing Requirements** 📝
   - Security level enforcement must be validated in integration tests with misconfigured pipeline scenarios
   - Property-based tests validate invariants across random configurations (1000+ test cases)
   - Certification tests required for all trusted downgrade plugins
   - Location: `tests/test_adr002_*.py` (dedicated test modules)

**Migration Path** (for existing deployments):

- Existing plugins without `security_level` declarations: Default to `SecurityLevel.UNOFFICIAL` (safe degradation)
- Gradual rollout: Validate security levels in non-enforcing mode first (log violations without aborting)
- Plugin migration checklist: Review, declare accurate level, add tests, certification (if trusted downgrade)

**Performance Characteristics**:

- Operating level computation: O(n) where n = number of plugins (single pass minimum calculation)
- Validation overhead: O(n) plugin validations at pipeline construction (one-time cost, not per-record)
- Runtime overhead: Zero (no per-record security checks, trust certified plugins)

## Related Documents

### Architecture Decision Records

- [ADR-001: Design Philosophy](001-design-philosophy.md) – Security-first priority hierarchy, fail-closed principles
- [ADR-002-A: Trusted Container Model](002-a-trusted-container-model.md) – SecureDataFrame immutability enforcement
- [ADR-003: Central Plugin Registry](003-plugin-type-registry.md) – Unified registry interface with automatic discovery
- [ADR-004: Mandatory BasePlugin Inheritance](004-mandatory-baseplugin-inheritance.md) – Security enforcement foundation through concrete ABC methods
- [ADR-005: Frozen Plugin Capability](005-frozen-plugin-capability.md) – Strict level enforcement option for high-assurance environments

### Security Documentation

- `docs/architecture/security-controls.md` – ISM control inventory and implementation evidence
- `docs/architecture/plugin-security-model.md` – Plugin security model and context propagation
- `docs/architecture/threat-surfaces.md` – Attack surface analysis and threat model
- `docs/security/adr-002-threat-model.md` – Detailed threat analysis for MLS model
- `docs/compliance/adr-002-certification-evidence.md` – Certification process and audit evidence

### Implementation Guides

- `docs/development/plugin-authoring.md` – Plugin development guide including security requirements
- `docs/guides/plugin-development-adr002a.md` – SecureDataFrame usage patterns for plugin authors
- `docs/architecture/plugin-catalogue.md` – Plugin inventory with security level declarations

### Testing Documentation

- `tests/test_adr002_properties.py` – Property-based tests for security invariants
- `tests/test_adr002_invariants.py` – Invariant validation tests
- `tests/test_adr002_validation.py` – Clearance validation tests
- `tests/test_adr002_baseplugin_compliance.py` – BasePlugin compliance tests
- `tests/test_adr002_suite_integration.py` – End-to-end integration tests

### Compliance Evidence

- `docs/compliance/CONTROL_INVENTORY.md` – ISM control implementation inventory
- `docs/compliance/TRACEABILITY_MATRIX.md` – ISM control to code traceability
- `docs/compliance/adr-002-certification-evidence.md` – Certification evidence for IRAP assessment

---

**Document History**:
- **2025-10-23**: Initial acceptance
- **2025-10-26**: Added operating_level exposure with fail-loud enforcement
- **2025-10-27**: Implementation completed (Sprint 1)
- **2025-10-28**: Transformed to release-quality standard with comprehensive IRAP documentation

**Author(s)**: Elspeth Architecture Team

**Classification**: UNOFFICIAL (ADR documentation suitable for public release)

**Last Updated**: 2025-10-28
