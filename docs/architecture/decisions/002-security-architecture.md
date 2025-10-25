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

### Bell-LaPadula Directionality: Data vs Plugin Operations

**CRITICAL DISTINCTION**: Data classifications and plugin operations move in OPPOSITE directions under Bell-LaPadula:

**Data Classifications (Can Only INCREASE)** - ADR-002a:
- Data tagged UNOFFICIAL can be **uplifted** to OFFICIAL or SECRET (via `with_uplifted_classification()`)
- Data tagged SECRET **CANNOT** be downgraded to OFFICIAL or UNOFFICIAL
- Violates Bell-LaPadula "no write down" rule
- Example: SECRET-tagged DataFrame cannot be written to UNOFFICIAL sink
- Classification increases are EXPLICIT and AUDITED (never implicit)
- Enforced by ClassifiedDataFrame container model (ADR-002a)

**Plugin Operations (Can Only DECREASE - if allow_downgrade=True)** - ADR-002/ADR-005:
- Plugin with SECRET clearance **CAN** operate at OFFICIAL or UNOFFICIAL levels (trusted downgrade)
- Plugin with UNOFFICIAL clearance **CANNOT** operate at SECRET level (insufficient clearance)
- Violates Bell-LaPadula "no read up" rule
- Example: UNOFFICIAL datasource cannot participate in SECRET pipeline
- Operation decreases require `allow_downgrade=True` (frozen plugins reject ALL downgrade attempts)
- Enforced by BasePlugin.validate_can_operate_at_level() (ADR-004)

**Asymmetry Summary**:
```
Data Classification:  UNOFFICIAL → OFFICIAL → SECRET  (can only increase via uplift)
Plugin Operation:     SECRET → OFFICIAL → UNOFFICIAL  (can only decrease via trusted downgrade)
```

**Forbidden Operations**:
- ❌ UNOFFICIAL plugin running at SECRET level (insufficient clearance - plugin operation violation)
- ❌ SECRET data downgrading to UNOFFICIAL (no write down - data classification violation)
- ❌ Frozen plugin (allow_downgrade=False) operating below its clearance (strict enforcement)

**Allowed Operations**:
- ✅ SECRET plugin operating at UNOFFICIAL level (if allow_downgrade=True) - trusted to filter
- ✅ UNOFFICIAL data uplifted to SECRET (explicit via with_uplifted_classification())
- ✅ Frozen plugin operating at EXACT declared level only

**See Also**: ADR-005 (Frozen Plugin Capability) for detailed frozen behavior specification.

### Example Implementation

```python
# Declared levels (component clearances)
datasource.security_level = SecurityLevel.OFFICIAL  # Cleared for OFFICIAL data
llm.security_level = SecurityLevel.SECRET           # Cleared for SECRET data
sink_secure.security_level = SecurityLevel.SECRET   # Cleared for SECRET data

# AUTOMATIC computation: pipeline operating level = MIN of all clearances
pipeline_level = min(SecurityLevel.OFFICIAL, SecurityLevel.SECRET, SecurityLevel.SECRET)
# => SecurityLevel.OFFICIAL (lowest clearance)

# Each component validates: Can I operate at this level?
# Datasource validation: OFFICIAL clearance, asked to operate at OFFICIAL → ✅ OK (exact match)
# LLM validation: SECRET clearance, asked to operate at OFFICIAL → ✅ OK (can downgrade, trusted to filter)
# Sink validation: SECRET clearance, asked to operate at OFFICIAL → ✅ OK (can downgrade, accepts lower data)

# Now suppose operator FORCES a higher minimum (configuration override):
forced_operating_level = SecurityLevel.SECRET  # Manual override, NOT automatic min()

# Datasource refuses to operate ABOVE its clearance (Bell-LaPadula "no read up")
# This is the ONLY scenario where insufficient-clearance errors occur
if forced_operating_level > datasource.security_level:
    raise SecurityError(
        f"Cannot operate OFFICIAL datasource at forced SECRET level - insufficient clearance. "
        f"Component clearance: {datasource.security_level.name}, "
        f"Required operating level: {forced_operating_level.name}"
    )

# LLM and sink still validate successfully (SECRET clearance ≥ SECRET operating level)
```

**Key Principle**: Plugins with HIGHER clearance can operate at LOWER levels (trusted to filter/downgrade).
Plugins with LOWER clearance CANNOT operate at HIGHER levels (insufficient clearance).

**Source Responsibility**: When a SECRET-cleared datasource operates at an OFFICIAL pipeline level,
it is responsible for filtering out SECRET-tagged data. This is validated through certification.
The system trusts that properly certified datasources understand their data context and enforce
filtering correctly.

### Plugin Customization: Freezing at Declared Level

**Default Behavior**: The standard `BasePlugin` implementation allows components with higher
clearance to operate at lower levels (trusted downgrade model). This is the recommended pattern
for most deployments: a SECRET-cleared datasource CAN operate at OFFICIAL level by filtering
data appropriately, and a SECRET-cleared sink CAN receive OFFICIAL data.

**Frozen Behavior**: Organizations with strict operational security requirements can create
plugins that refuse ALL operations below their declared level using the `allow_downgrade=False`
parameter (ADR-005). Example use case: a SECRET-only datasource that should NEVER participate
in non-SECRET pipelines, regardless of filtering capabilities.

**Implementation** (ADR-005 - Configuration-Driven Approach):

```python
class FrozenSecretDataSource(BasePlugin, DataSource):
    """SECRET-only datasource - refuses to operate at lower classification levels.

    This pattern is useful when organizational policy requires strict level separation
    rather than trusted downgrade. For example:
    - Dedicated SECRET infrastructure that should never serve lower-classified pipelines
    - Compliance requirements mandating physical separation of classification domains
    - High-assurance environments requiring explicit per-level certification
    """

    def __init__(self):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False  # ← Frozen behavior (ADR-005)
        )

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        """Load data - validation already enforced at pipeline construction.

        Pipeline will reject configuration if any component has lower clearance
        (e.g., OFFICIAL sink) because operating_level would be OFFICIAL, but this
        frozen plugin requires exact SECRET level match.
        """
        # Implementation here - knows it's operating at declared level only
        ...
```

-**How It Works**:

- `allow_downgrade=True` (explicit): Plugin with SECRET clearance can operate at OFFICIAL or UNOFFICIAL levels (trusted to filter)
- `allow_downgrade=False` (frozen): Plugin with SECRET clearance can ONLY operate at SECRET level (exact match required)
- Sealed `validate_can_operate_at_level()` method checks both insufficient clearance AND frozen downgrade
- No override attack surface (configuration parameter, not method override)
- Explicit security choice required (`allow_downgrade` has no default)

**Trade-offs**:

- **Reduced flexibility** – Frozen plugins cannot participate in mixed-classification pipelines.
  A SECRET-only datasource will abort if configured with an OFFICIAL sink, even though the
  datasource could technically filter SECRET data appropriately.

- **Increased certification burden** – Custom validation logic requires separate certification
  review to verify security properties. Default trusted-downgrade behavior is pre-certified
  as part of BasePlugin.

- **Deployment complexity** – Operators must configure separate pipelines for each classification
  level, increasing infrastructure overhead.

**When to Use**:

- ✅ **Dedicated classification domains** – Infrastructure physically/logically separated by level
- ✅ **Regulatory mandates** – Compliance frameworks requiring explicit per-level certification
- ✅ **High-assurance systems** – Environments where filtering trust is insufficient
- ❌ **General-purpose deployments** – Default trusted-downgrade is simpler and more flexible
- ❌ **Mixed-classification workflows** – Frozen plugins break multi-level orchestration

**Certification Note**: Frozen plugins (`allow_downgrade=False`) require separate certification
review. Certification must verify:
1. Constructor correctly sets `allow_downgrade=False` (visible in code review)
2. Plugin implementation is safe to operate at single level only
3. No inadvertent cross-level data leakage
4. Deployment infrastructure supports exact level matching

Frozen plugins use the same `BasePlugin.validate_can_operate_at_level()` sealed method as default
plugins, so certification scope is reduced compared to custom override approaches (no override
logic to audit).

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

**Last Updated**: 2025-10-24
**Author(s)**: Architecture Team
