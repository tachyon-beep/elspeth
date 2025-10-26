# ADR 002 – Multi-Level Security Enforcement

## Status

Accepted (2025-10-23)

## Context

Elspeth orchestrates experiments that chain datasources, LLM transforms, and sinks. Many
deployments handle data with strict classification requirements (e.g., Australian Government
PSPF classifications UNOFFICIAL → OFFICIAL → OFFICIAL:SENSITIVE → PROTECTED → SECRET,
healthcare HIPAA data, PCI-DSS cardholder data). We need a mechanism that prevents sensitive
information from flowing into less trusted components.

Traditional access control models rely solely on clearance checks at consumption time
("can this component access this data?"), but this approach has a critical vulnerability:
by the time a clearance violation is detected, the pipeline may have already retrieved
sensitive data into memory. We need a fail-fast mechanism that prevents execution from
starting with misconfigured security levels.

### Attack Scenario: Misconfigured Pipeline Without Fail-Fast

**Scenario**: Operator misconfigures a pipeline with incompatible security levels:

```python
# config/experiments/classified_analysis.yaml
datasource:
  type: "secret_government_data"
  clearance: SECRET

sinks:
  - type: "public_csv_export"
    path: "outputs/public_report.csv"
    clearance: UNOFFICIAL
```

**Without ADR-002 (no fail-fast validation)**:

1. Pipeline construction succeeds (no early validation)
2. Datasource retrieves SECRET-classified data into memory
3. Data flows through transforms
4. **At sink write time**: Clearance check finally triggers - UNOFFICIAL sink cannot write SECRET data
5. Pipeline aborts, but **SECRET data has already been loaded into memory**
6. Memory dumps, error logs, or debugging outputs may leak classified data

**With ADR-002 (fail-fast validation)**:

1. Pipeline construction computes: `operating_level = MIN(SECRET datasource, UNOFFICIAL sink) = UNOFFICIAL`
2. Datasource validates: "Can I operate at UNOFFICIAL level?" → **NO** (insufficient clearance - SECRET data requires SECRET level)
3. **Pipeline aborts BEFORE data retrieval** → No classified data loaded into memory
4. Safe failure: Configuration error detected, no data exposure

**Key Insight**: Fail-fast prevents the window where SECRET data exists in memory but cannot be safely written,
eliminating the risk of data leakage through error handling, logging, or debugging pathways.

## Decision

We will adopt a Multi-Level Security (MLS) model inspired by Bell-LaPadula ("no read up,
no write down") with two layers of enforcement:

1. **Plugin security level declarations** – All plugins declare a `security_level` (e.g.,
   `UNOFFICIAL`, `OFFICIAL`, `OFFICIAL:SENSITIVE`, `PROTECTED`, `SECRET` per Australian PSPF
   classification).

2. **Clearance-based enforcement** – Components may only consume data whose classification is
   less than or equal to their declared `security_level`. This is the traditional clearance
   check: a `SECRET` sink may receive `SECRET`, `CONFIDENTIAL`, or `PUBLIC` data, whereas an
   `UNOFFICIAL` sink may only receive `UNOFFICIAL` data.

3. **Pipeline-wide minimum evaluation** – Before execution, the orchestrator evaluates the
   minimum security level across the configured pipeline (datasource, all transforms, sinks).
   This becomes the **operating level** for the entire pipeline: `operating_level = min(all component clearances)`.

4. **Insufficient clearance prevention (Bell-LaPadula "no read up")** – Components whose
   declared level (clearance) is LOWER than the computed operating level refuse to run, as they
   lack sufficient clearance. This occurs when an operator forces a higher minimum (e.g., via
   configuration override) rather than using the automatic minimum. Components with HIGHER
   clearance than the operating level are trusted to operate at the lower level
   (filtering/downgrading data appropriately).

5. **Fail-fast abort** – The run aborts early if any component has insufficient clearance
   for the required operating level, preventing low-clearance components from handling
   classified data. **Note**: In normal automatic computation, the operating level equals the
   LOWEST component clearance, so insufficient-clearance errors only occur with manual overrides
   or when a component has explicitly set `allow_downgrade=False` (frozen plugin).

### Bell-LaPadula Interpretation: Architectural Split

Elspeth implements Bell-LaPadula MLS with a critical **architectural split** between data classification enforcement and plugin operation enforcement. Understanding this distinction is essential for correctly implementing and auditing security policies.

#### The Architectural Split

**"No Write Down" (Data Classification Layer)** - ADR-002-A:

- **What it controls**: ClassifiedDataFrame objects (data containers)
- **Enforcement**: Immutable classification via frozen dataclass
- **Rule**: Data tagged SECRET CANNOT be downgraded to UNOFFICIAL
- **Mechanism**: Runtime prevention - `ClassifiedDataFrame` has no downgrade method, only `with_uplifted_classification()`
- **Violation example**: Attempting to write `ClassifiedDataFrame(data, SecurityLevel.SECRET)` to UNOFFICIAL sink
- **Result**: TypeError or AttributeError (no downgrade API exists)

**"No Read Up" (Plugin Clearance Layer)** - ADR-002/ADR-004:

- **What it controls**: Plugin operations (datasource retrieval, transform processing, sink writes)
- **Enforcement**: Clearance validation via `BasePlugin.validate_can_operate_at_level()`
- **Rule**: Plugin with UNOFFICIAL clearance CANNOT operate at SECRET level (insufficient clearance)
- **Mechanism**: Pipeline construction time - fail-fast before data retrieval
- **Violation example**: UNOFFICIAL datasource in a forced SECRET pipeline
- **Result**: `SecurityValidationError` raised during pipeline setup

**"Trusted Downgrade" (Plugin Operation Flexibility)** - ADR-002/ADR-005:

- **What it enables**: Plugins with SECRET clearance CAN operate at UNOFFICIAL level (if `allow_downgrade=True`)
- **Trust model**: Certified plugins are responsible for filtering data appropriately at lower operating levels
- **Enforcement**: Certification + audit, NOT runtime validation
- **Example**: SECRET Azure datasource operating at UNOFFICIAL level filters to only retrieve UNOFFICIAL blobs
- **Responsibility**: Plugin author implements filtering logic, certification process validates correctness

#### Why SECRET Datasource → UNOFFICIAL Sink is NOT a Violation

**Common Misconception**: "SECRET datasource writing to UNOFFICIAL sink violates 'no write down'"

**Correct Understanding**:

1. Pipeline computes `operating_level = MIN(SECRET datasource, UNOFFICIAL sink) = UNOFFICIAL`
2. SECRET datasource validates: "Can I operate at UNOFFICIAL level?" → YES (trusted downgrade)
3. Datasource operates at UNOFFICIAL level → produces `ClassifiedDataFrame(data, SecurityLevel.UNOFFICIAL)`
4. UNOFFICIAL sink receives UNOFFICIAL data → ✅ No violation

**Key Insight**: The SECRET datasource **does not produce SECRET data** when operating at UNOFFICIAL level. It is responsible for filtering and producing UNOFFICIAL-classified data only. This filtering responsibility is validated through:

- Certification process (pre-deployment audit)
- Code review of datasource filtering logic
- Attestation that datasource correctly handles multi-level data sources
- **NOT** runtime enforcement (system trusts certified plugins)

**What WOULD be a violation**: If the datasource produced `ClassifiedDataFrame(data, SecurityLevel.SECRET)` while operating at UNOFFICIAL level, the sink would reject it (ClassifiedDataFrame cannot be downgraded). This is the "no write down" enforcement working correctly.

#### Asymmetry Summary

```
Layer 1 - Data Classification:
  UNOFFICIAL → OFFICIAL → SECRET  (can only increase via explicit uplift)
  Enforcement: ClassifiedDataFrame immutability (ADR-002-A)

Layer 2 - Plugin Operation:
  SECRET → OFFICIAL → UNOFFICIAL  (can decrease via trusted downgrade if allow_downgrade=True)
  Enforcement: BasePlugin.validate_can_operate_at_level() + certification (ADR-004)
```

**Forbidden Operations**:

- ❌ **Plugin clearance violation**: UNOFFICIAL plugin running at SECRET level (insufficient clearance - "no read up")
- ❌ **Data classification violation**: SECRET ClassifiedDataFrame downgraded to UNOFFICIAL (impossible - no API exists - "no write down")
- ❌ **Frozen plugin violation**: Plugin with `allow_downgrade=False` operating below its clearance (ADR-005 strict enforcement)

**Allowed Operations**:

- ✅ **Trusted downgrade**: SECRET plugin operating at UNOFFICIAL level (if `allow_downgrade=True`) - trusted to filter appropriately
- ✅ **Explicit uplift**: UNOFFICIAL data uplifted to SECRET (via `with_uplifted_classification()` - explicit and audited)
- ✅ **Exact match**: Frozen plugin operating at EXACT declared level only (strict enforcement)

**See Also**: ADR-005 (Frozen Plugin Capability) for detailed frozen behavior specification.

#### Concrete Example: Multi-Level Pipeline

```python
# Scenario: SECRET datasource → UNOFFICIAL sink (VALID configuration)

# Component declarations (clearances)
datasource.security_level = SecurityLevel.SECRET    # Can access UNOFFICIAL→SECRET blobs
sink.security_level = SecurityLevel.UNOFFICIAL      # Can only write UNOFFICIAL data

# Pipeline construction
operating_level = min(SecurityLevel.SECRET, SecurityLevel.UNOFFICIAL)
# => SecurityLevel.UNOFFICIAL

# Validation (both components check if they can operate at UNOFFICIAL)
datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
# ✅ PASSES: SECRET clearance ≥ UNOFFICIAL operating level + allow_downgrade=True
# Datasource is trusted to filter and only retrieve UNOFFICIAL blobs

sink.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
# ✅ PASSES: UNOFFICIAL clearance == UNOFFICIAL operating level (exact match)

# Runtime execution
data = datasource.load_data()  # Returns ClassifiedDataFrame(df, SecurityLevel.UNOFFICIAL)
# ↑ Datasource filtered appropriately - only UNOFFICIAL data retrieved

sink.write(data)  # ✅ SUCCEEDS: UNOFFICIAL sink receiving UNOFFICIAL data
```

**What if datasource misbehaves?**

```python
# Buggy/malicious datasource returns wrong classification
data = ClassifiedDataFrame(secret_df, SecurityLevel.SECRET)  # ❌ BUG: wrong level

sink.write(data)  # ❌ FAILS: Sink validation rejects SECRET data
# ClassifiedDataFrame cannot be downgraded, so sink must reject it
# This is the "no write down" protection working correctly
```

#### Enforcement Mechanisms

| Layer | Rule | Enforced By | When | Failure Mode |
|-------|------|-------------|------|--------------|
| **Data** | No write down | `ClassifiedDataFrame` immutability | Runtime (construction) | TypeError (no downgrade API) |
| **Plugin** | No read up | `BasePlugin.validate_can_operate_at_level()` | Pipeline construction | SecurityValidationError |
| **Plugin** | Trusted downgrade | Certification + audit | Pre-deployment | Manual audit failure |

**Key Principle**: Plugins with HIGHER clearance can operate at LOWER levels (trusted to filter appropriately).
Plugins with LOWER clearance CANNOT operate at HIGHER levels (insufficient clearance).

**Datasource Filtering Responsibility**: When a SECRET-cleared datasource operates at an OFFICIAL pipeline level,
it MUST filter its data retrieval to produce only OFFICIAL-classified data. This responsibility is validated through:

- Pre-deployment certification audit
- Code review of filtering logic
- Attestation documentation
- **NOT** runtime enforcement (system trusts certified plugins to implement filtering correctly)

### Plugin Customization: Frozen Plugins (Strict Level Enforcement)

**Default Behavior**: The standard `BasePlugin` implementation allows components with higher
clearance to operate at lower levels (trusted downgrade model). This is the recommended pattern
for most deployments: a SECRET-cleared datasource CAN operate at OFFICIAL level by filtering
data appropriately.

**Frozen Behavior**: Organizations with strict operational security requirements can create
plugins that refuse ALL operations below their declared level using the `allow_downgrade=False`
parameter. Example: a SECRET-only datasource that should NEVER participate in non-SECRET
pipelines, regardless of filtering capabilities.

**For complete specification, implementation details, test patterns, and migration guidance,
see [ADR-005: Frozen Plugin Capability](005-frozen-plugin-capability.md).**

**Quick Reference**:

- `allow_downgrade=True`: Trusted downgrade (ADR-002 default semantics)
- `allow_downgrade=False`: Frozen plugin (strict level enforcement - ADR-005)

**When to Use Frozen Plugins**:

- ✅ Dedicated classification domains (physically/logically separated by level)
- ✅ Regulatory mandates requiring explicit per-level certification
- ✅ High-assurance systems where filtering trust is insufficient
- ❌ General-purpose deployments (default trusted-downgrade is simpler)
- ❌ Mixed-classification workflows (frozen plugins break multi-level orchestration)

### Exposing Operating Level to Plugins

**Context**: Plugin authors need to make security-aware decisions based on the pipeline's
effective operating level, not just their declared clearance. For example, a SECRET-cleared
datasource operating at UNOFFICIAL level should filter data appropriately.

**Implementation**: The pipeline operating level (minimum clearance envelope) is exposed to
plugins via `PluginContext.operating_level` and accessed through `BasePlugin.get_effective_level()`.

**Security Boundary**: Plugins receive read-only access to the operating level through the
frozen `PluginContext`. They cannot modify it or bypass validation.

#### Terminology Clarification

- **security_level** (declared clearance): What the plugin CAN handle (maximum)
- **operating_level** (effective level): What the plugin SHOULD produce (pipeline minimum)

**Example**:

```python
# SECRET datasource in UNOFFICIAL pipeline
datasource.get_security_level()   # Returns SECRET (declared clearance)
datasource.get_effective_level()  # Returns UNOFFICIAL (pipeline operating level)
```

#### Correct Usage Patterns

Plugins should use `get_effective_level()` for:

✅ **Filtering Optimization** (datasources):

```python
def load_data(self) -> ClassifiedDataFrame:
    effective_level = self.get_effective_level()

    # Filter data retrieval to only fetch blobs at effective level
    if effective_level == SecurityLevel.UNOFFICIAL:
        blobs = self._fetch_blobs_with_tag("classification:unofficial")
    elif effective_level == SecurityLevel.SECRET:
        blobs = self._fetch_blobs_with_tag("classification:unofficial|official|secret")

    # Tag retrieved data at effective level
    return ClassifiedDataFrame(data, classification=effective_level)
```

✅ **Conditional Processing** (transforms):

```python
def transform(self, df: ClassifiedDataFrame) -> ClassifiedDataFrame:
    effective_level = self.get_effective_level()

    # Skip expensive compliance checks at lower levels
    if effective_level >= SecurityLevel.PROTECTED:
        df = self._apply_hipaa_compliance_checks(df)

    return df
```

✅ **Audit Logging** (all plugins):

```python
def load_data(self) -> ClassifiedDataFrame:
    effective_level = self.get_effective_level()
    declared_level = self.get_security_level()

    self.logger.info(
        "Datasource operating at effective level",
        declared_clearance=declared_level.name,
        effective_level=effective_level.name,
        downgrading=effective_level < declared_level,
    )

    return self._load_filtered_data()
```

✅ **Performance Optimization** (all plugins):

```python
def process(self, data):
    effective_level = self.get_effective_level()

    # Use different algorithms based on security level
    if effective_level >= SecurityLevel.SECRET:
        return self._slow_secure_processing(data)
    else:
        return self._fast_standard_processing(data)
```

#### Anti-Patterns (DO NOT)

❌ **Bypassing Filtering**:

```python
# WRONG: Skipping filtering based on effective level
def load_data(self):
    if self.get_effective_level() == self.get_security_level():
        # "No filtering needed - levels match"
        return self._load_all_data()  # ❌ May include higher-classified data!
```

**Why Wrong**: Even when levels match, datasource must filter correctly. The multi-level
data source may contain data ABOVE the operating level that must be excluded.

❌ **Assuming Level == Content Classification**:

```python
# WRONG: Assuming effective level determines data classification
def load_data(self):
    data = self._fetch_data()
    effective_level = self.get_effective_level()
    # "Data is at effective level, so tag it as such"
    return ClassifiedDataFrame(data, effective_level)  # ❌ Data may be UNOFFICIAL!
```

**Why Wrong**: Operating level is pipeline constraint, not data classification. Data
classification is determined by content, not pipeline level. Use
`with_uplifted_classification()` if data needs higher classification.

❌ **Skipping Validation**:

```python
# WRONG: Bypassing validation based on effective level
def validate_data(self, data):
    if self.get_effective_level() == SecurityLevel.UNOFFICIAL:
        return  # "No validation needed at low level" ❌
```

**Why Wrong**: Validation requirements are independent of security level. All data must
be validated according to schema and business rules.

#### Certification Requirements

Plugins using `get_effective_level()` must demonstrate correct behavior during certification:

1. **Filtering Correctness**: When operating below declared level, datasource filters out
   higher-classified data (verified through unit tests with multi-level test data)

2. **Classification Accuracy**: Data is tagged at correct classification level based on
   content, not operating level (verified through integration tests)

3. **Audit Trail**: Effective level logged for security audits (verified through log inspection)

4. **Performance Claims**: If using level-based optimization, performance characteristics
   documented and tested at all supported levels

**Certification Test Pattern**:

```python
def test_datasource_filters_at_lower_level():
    # SECRET-cleared datasource with mixed data
    datasource = SecretAzureDatasource(
        security_level=SecurityLevel.SECRET,
        allow_downgrade=True,
    )

    # Force operating at UNOFFICIAL level
    datasource.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)
    context = PluginContext(
        plugin_name="test",
        plugin_kind="datasource",
        security_level=SecurityLevel.SECRET,
        operating_level=SecurityLevel.UNOFFICIAL,  # Pipeline operating level
    )
    datasource.plugin_context = context

    # Load data - should only retrieve UNOFFICIAL blobs
    result = datasource.load_data()

    # Verify filtering
    assert result.classification == SecurityLevel.UNOFFICIAL
    assert all(row["classification"] == "unofficial" for _, row in result.df.iterrows())
    assert datasource.get_effective_level() == SecurityLevel.UNOFFICIAL
```

#### Implementation Details

**Context Propagation**:

1. Pipeline validation computes `operating_level = MIN(all plugin clearances)`
2. `ExperimentSuiteRunner._propagate_operating_level()` updates all plugin contexts
3. Plugins access via `self.get_effective_level()`

**Fail-Fast Behavior**:

- `operating_level` field defaults to `None` (pre-validation state)
- `get_effective_level()` raises `RuntimeError` if `operating_level` is `None`
- **High-security principle**: LOUD CATASTROPHIC FAILURE, not graceful degradation
- Plugins calling `get_effective_level()` during construction will fail immediately
- This catches programming errors early (using effective level before validation completes)

**Security Properties**:

- `PluginContext` is frozen (immutable) - plugins cannot modify `operating_level`
- `get_effective_level()` is `@final` - plugins cannot override it
- Operating level always ≤ declared security level (guaranteed by validation)

**See Also**: `BasePlugin.get_effective_level()` docstring for complete API documentation.

## Consequences

### Benefits

- **Fail-fast security** – Misconfigured pipelines (e.g., UNOFFICIAL datasource in SECRET pipeline)
  abort before data is retrieved, preventing insufficient-clearance components from handling
  classified data
- **Defence-in-depth** – Two-layer approach: clearance checks prevent insufficient-clearance
  components from participating, while certified datasources are trusted to filter data when
  operating at lower levels
- **Upgrade prevention** – Blocks components from operating at levels ABOVE their declared clearance,
  enforcing Bell-LaPadula "no read up" rule
- **Trusted downgrade model** – Components with HIGHER clearance can operate at LOWER levels,
  with certified datasources responsible for filtering data appropriately (e.g., SECRET-cleared
  Azure datasource operating at OFFICIAL level filters out SECRET-tagged blobs)
- **Regulatory compliance** – MLS model aligns with government (PSPF), healthcare (HIPAA), and
  financial (PCI-DSS) security frameworks

### Limitations / Trade-offs

- **Plugin governance overhead** – Requires every plugin to declare an accurate security level;
  governance processes are needed to vet new plugins before acceptance. *Mitigation*: Plugin
  acceptance criteria mandate security level declaration and review.
- **Trust in certified datasources** – The model trusts that certified datasources correctly filter
  data when operating at lower levels (e.g., SECRET-cleared datasource filtering out SECRET blobs
  when running at OFFICIAL level). *Mitigation*: Certification process validates datasource
  filtering logic; datasources must demonstrate correct behavior across all supported security levels.
- **Pipeline minimum computation** – Pipeline operating level is the MINIMUM of all component
  clearances, meaning a single low-clearance component (e.g., UNOFFICIAL sink) will cause the
  entire pipeline to operate at that lower level. High-clearance datasources must filter data
  accordingly. *Mitigation*: This is intentional defense-in-depth (see ADR-001); operators can
  isolate sensitive operations into separate pipelines if needed.
- **No dynamic reclassification** – Security levels are static at pipeline configuration time;
  cannot dynamically upgrade/downgrade during execution. *Mitigation*: This prevents time-of-check
  to time-of-use (TOCTOU) vulnerabilities; operators configure separate pipelines for different
  classification levels.

### Implementation Impact

- **Plugin definitions** – Security level metadata lives on each plugin definition
  (`security_level` field in config)
- **Suite runner changes** – Prior to instantiation, the suite runner computes the minimum
  level and enforces it via the plugin registry/context
- **Plugin validation** – Datasources and sinks validate that the operating level does not
  exceed their declared clearance (Bell-LaPadula "no read up"), raising an error and aborting
  the run if insufficient clearance is detected. Components with higher clearance can operate
  at lower levels and are trusted to filter/downgrade data appropriately.
- **Clearance helpers** – Clearance checks are enforced in plugin interfaces so that components
  cannot be forced to operate above their declared clearance. Components with SECRET clearance
  can serve data at lower classification levels (OFFICIAL, UNOFFICIAL) by filtering appropriately.
- **Testing requirements** – Security level enforcement must be validated in integration tests
  with misconfigured pipeline scenarios

## Related Documents

- [ADR-001](001-design-philosophy.md) – Design Philosophy (security-first priority hierarchy)
- `docs/architecture/security-controls.md` – Security control inventory
- `docs/architecture/plugin-security-model.md` – Plugin security model and context propagation
- `docs/architecture/threat-surfaces.md` – Attack surface analysis
- [ADR-003](historical/003-remove-legacy-code.md) – Remove Legacy Code (historical) – registry
  enforcement context

---

**Last Updated**: 2025-10-26 (Added operating_level exposure with fail-loud enforcement)
**Author(s)**: Architecture Team
