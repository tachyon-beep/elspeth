# ADR 005 – Multi-Level Security Enforcement

## Status

Accepted (2025‑10‑23).

## Context

Elspeth orchestrates experiments that chain datasources, LLM transforms, and sinks. Many
deployments handle data with strict classification requirements (e.g., government TOP
SECRET/SECRET/UNOFFICIAL, healthcare HIPAA data, PCI-DSS cardholder data). We need a
mechanism that prevents sensitive information from flowing into less trusted components.

## Decision

Adopt a Multi-Level Security (MLS) model inspired by Bell-LaPadula (“no read up, no write
down”):

1. All plugins declare a `security_level` (e.g., `public`, `internal`, `confidential`,
   `secret`).
2. **Clearance-based enforcement:** components may only consume data whose classification is
   less than or equal to their declared `security_level`. This is the traditional clearance
   check — a `SECRET` sink may receive `SECRET`, `CONFIDENTIAL`, or `PUBLIC` data, whereas an
   `UNOFFICIAL` sink may only receive `UNOFFICIAL` data.
3. **Pipeline-wide minimum evaluation:** before execution, the orchestrator evaluates the minimum
   security level across the
   configured pipeline (datasource, all transforms, sinks).
4. The experiment inherits that minimum level. Components whose declared level is higher
   than the computed minimum refuse to run at the downgraded level.
5. The run aborts early if any component cannot operate at the downgraded level—preventing
   classified data from reaching low-trust sinks.

## Consequences

### Benefits

- Enforces fail-fast behaviour: misconfigured pipelines (e.g., secret datasource + unofficial
  sink) abort before data is retrieved.
- Provides defence-in-depth: clearance checks guard at consumption time, while pipeline-wide
  minimum evaluation prevents execution from even starting with mismatched components.
- Blocks Trojan or malicious sinks that advertise a low security level—secret sources will
  refuse to serve them.
- Guards against accidental downgrade (“debug logger” sinks) by computing the minimum level
  before execution.

### Limitations / Mitigations

- Requires every plugin to declare an accurate security level; governance is needed to vet new
  plugins.
- Conservative: a single low-level sink will block the entire pipeline; operators must remove
  or isolate such sinks or provide a high-security equivalent.

## Implementation

- Security level metadata lives on each plugin definition (`security_level` field in config).
- Prior to instantiation, the suite runner computes the minimum level and enforces it via
  the plugin registry/context.
- Datasources and sinks validate that they are not running below their declared level—raising
  an error and aborting the run if the downgrade would occur.
- Clearance checks are enforced in plugin interfaces (`security.allowed()` style helpers) so
  that `SecurityLevel.SECRET` components can serve data to equal-or-higher clearance peers but
  never to lower ones.

### Example

```python
# Declared levels
datasource.security_level = SecurityLevel.SECRET
llm.security_level = SecurityLevel.SECRET
sink_secure.security_level = SecurityLevel.SECRET
sink_debug.security_level = SecurityLevel.UNOFFICIAL  # misconfigured

pipeline_level = min(SecurityLevel.SECRET, SecurityLevel.SECRET,
                     SecurityLevel.SECRET, SecurityLevel.UNOFFICIAL)
# => SecurityLevel.UNOFFICIAL

# Datasource refuses to initialise below its classification.
if datasource.security_level > pipeline_level:
    raise SecurityError("Cannot operate SECRET datasource in UNOFFICIAL pipeline")
```

The run fails before the datasource is queried, ensuring that no secret data can be retrieved
until the misconfigured sink is removed or elevated.

## Related Documents

- ADR‑001 Design Philosophy (security-first priority hierarchy)
- `docs/architecture/security-controls.md`
- `docs/architecture/threat-surfaces.md`
- ADR‑003 Remove Legacy Code (for context on registry enforcement)
