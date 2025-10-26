# ADR 002 – Multi-Level Security Enforcement

## Status

Accepted (2025-10-23)

## Context

Elspeth orchestrates experiments that chain datasources, LLM transforms, and sinks. Many
deployments handle data with strict classification requirements (e.g., government TOP
SECRET/SECRET/UNOFFICIAL, healthcare HIPAA data, PCI-DSS cardholder data). We need a
mechanism that prevents sensitive information from flowing into less trusted components.

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

4. **Downgrade prevention** – The experiment inherits that minimum level. Components whose
   declared level is higher than the computed minimum refuse to run at the downgraded level.

5. **Fail-fast abort** – The run aborts early if any component cannot operate at the downgraded
   level, preventing classified data from reaching low-trust sinks.

### Example Implementation

```python
# Declared levels
datasource.security_level = SecurityLevel.SECRET
llm.security_level = SecurityLevel.SECRET
sink_secure.security_level = SecurityLevel.SECRET
sink_debug.security_level = SecurityLevel.UNOFFICIAL  # misconfigured

# Compute pipeline minimum
pipeline_level = min(SecurityLevel.SECRET, SecurityLevel.SECRET,
                     SecurityLevel.SECRET, SecurityLevel.UNOFFICIAL)
# => SecurityLevel.UNOFFICIAL

# Datasource refuses to initialise below its classification
if datasource.security_level > pipeline_level:
    raise SecurityError("Cannot operate SECRET datasource in UNOFFICIAL pipeline")
```

The run fails before the datasource is queried, ensuring that no secret data can be retrieved
until the misconfigured sink is removed or elevated.

## Consequences

### Benefits

- **Fail-fast security** – Misconfigured pipelines (e.g., secret datasource + unofficial sink)
  abort before data is retrieved, preventing data leakage
- **Defence-in-depth** – Two-layer approach: clearance checks guard at consumption time, while
  pipeline-wide minimum evaluation prevents execution from even starting with mismatched
  components
- **Trojan sink protection** – Blocks malicious sinks that advertise a low security level;
  secret sources will refuse to serve them
- **Accidental downgrade prevention** – Guards against "debug logger" sinks by computing the
  minimum level before execution
- **Regulatory compliance** – MLS model aligns with government (PSPF), healthcare (HIPAA), and
  financial (PCI-DSS) security frameworks

### Limitations / Trade-offs

- **Plugin governance overhead** – Requires every plugin to declare an accurate security level;
  governance processes are needed to vet new plugins before acceptance. *Mitigation*: Plugin
  acceptance criteria mandate security level declaration and review.
- **Conservative pipeline rejection** – A single low-level sink will block the entire pipeline;
  operators must remove or isolate such sinks or provide a high-security equivalent.
  *Mitigation*: This is intentional fail-closed behaviour (see ADR-001); clear error messages
  guide operators to resolution.
- **No dynamic reclassification** – Security levels are static at pipeline configuration time;
  cannot dynamically upgrade/downgrade during execution. *Mitigation*: This prevents time-of-check
  to time-of-use (TOCTOU) vulnerabilities; operators configure separate pipelines for different
  classification levels.

### Implementation Impact

- **Plugin definitions** – Security level metadata lives on each plugin definition
  (`security_level` field in config)
- **Suite runner changes** – Prior to instantiation, the suite runner computes the minimum
  level and enforces it via the plugin registry/context
- **Plugin validation** – Datasources and sinks validate that they are not running below
  their declared level, raising an error and aborting the run if downgrade would occur
- **Clearance helpers** – Clearance checks are enforced in plugin interfaces
  (`security.allowed()` style helpers) so that `SecurityLevel.SECRET` components can serve
  data to equal-or-higher clearance peers but never to lower ones
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
