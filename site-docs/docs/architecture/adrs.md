# Architecture Decision Records (ADRs)

Elspeth's design is guided by documented architecture decisions. This catalog provides an overview of all ADRs.

!!! info "What are ADRs?"
    **Architecture Decision Records (ADRs)** document significant architectural choices, their context, rationale, and consequences. They provide a historical record of "why" decisions were made, helping future maintainers understand the system.

---

## ADR Summary

| ID | Title | Status | Category | Impact |
|----|-------|--------|----------|--------|
| [001](#adr-001-design-philosophy) | Design Philosophy | ✅ Accepted | Foundation | 🔴 Critical |
| [002](#adr-002-multi-level-security-enforcement) | Multi-Level Security Enforcement | ✅ Accepted | Security | 🔴 Critical |
| [002a](#adr-002a-trusted-container-model) | Trusted Container Model (ClassifiedDataFrame) | ✅ Accepted | Security | 🔴 Critical |
| [002b](#adr-002b-immutable-security-policy-metadata) | Immutable Security Policy Metadata | 🟡 Proposed | Security | 🔴 Critical |
| [003](#adr-003-plugin-type-registry) | Plugin Type Registry | ✅ Accepted | Architecture | 🟡 High |
| [004](#adr-004-mandatory-baseplugin-inheritance) | Mandatory BasePlugin Inheritance | ✅ Accepted | Security | 🔴 Critical |
| [005](#adr-005-frozen-plugin-protection) | Frozen Plugin Protection | ✅ Accepted | Security | 🟡 High |
| [006](#adr-006-security-critical-exception-policy) | Security-Critical Exception Policy | ✅ Accepted | Security | 🟡 High |
| [007](#adr-007-universal-dual-output-protocol) | Universal Dual-Output Protocol | ✅ Accepted | Architecture | 🟢 Medium |
| [008](#adr-008-unified-registry-pattern) | Unified Registry Pattern | ✅ Accepted | Architecture | 🟡 High |
| [009](#adr-009-configuration-composition) | Configuration Composition | ✅ Accepted | Architecture | 🟡 High |
| [010](#adr-010-pass-through-lifecycle-and-routing) | Pass-Through Lifecycle and Routing | ✅ Accepted | Architecture | 🟢 Medium |
| [011](#adr-011-error-classification-and-recovery) | Error Classification and Recovery | ✅ Accepted | Reliability | 🟢 Medium |
| [012](#adr-012-testing-strategy-and-quality-gates) | Testing Strategy and Quality Gates | ✅ Accepted | Quality | 🟡 High |
| [013](#adr-013-global-observability-policy) | Global Observability Policy | ✅ Accepted | Operations | 🟢 Medium |
| [014](#adr-014-tamper-evident-reproducibility-bundle) | Tamper-Evident Reproducibility Bundle | ✅ Accepted | Compliance | 🔴 Critical |

---

## Core Philosophy & Security

### ADR-001: Design Philosophy

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Establishes security-first priority hierarchy for all architectural decisions.

**Priority Order**:
1. **Security** - Prevent unauthorized access, leakage, or downgrade
2. **Data Integrity** - Ensure reproducibility and tamper-evident audit trails
3. **Availability** - Keep system reliable and recoverable
4. **Usability/Functionality** - Developer ergonomics without compromising higher priorities

**Key Principle**: **Fail-closed** - Security controls deny operations when unavailable (never fail-open).

**Impact**: Guides all subsequent architectural decisions. When priorities conflict, higher-ranked wins.

**Full ADR**: [docs/architecture/decisions/001-design-philosophy.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/001-design-philosophy.md)

---

### ADR-002: Multi-Level Security Enforcement

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Implements Bell-LaPadula Multi-Level Security (MLS) with fail-fast validation.

**Key Concepts**:
- **Security Levels**: UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET
- **Operating Level**: MIN of all component security levels (weakest link)
- **"No Read Up"**: Components can only access data at or below their clearance
- **Trusted Downgrade**: High-clearance components can operate at lower levels (filtering data)

**Validation Rules**:
- ✅ SECRET datasource + OFFICIAL sink → Pipeline operates at OFFICIAL (datasource filters)
- ❌ UNOFFICIAL datasource + SECRET sink → Pipeline aborts (datasource has insufficient clearance)

**Implementation**:
- `SecurityLevel` enum (UNOFFICIAL=0 → SECRET=4)
- `BasePlugin.validate_can_operate_at_level()` enforcement
- Pipeline computes operating level before data retrieval

**Impact**: Foundation of Elspeth's security model. All plugins must declare security levels.

**See Also**: [Security Model Guide](../user-guide/security-model.md), [ADR-002a](#adr-002a-trusted-container-model)

**Full ADR**: [docs/architecture/decisions/002-security-architecture.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/002-security-architecture.md)

---

### ADR-002a: Trusted Container Model

**Status**: ✅ Accepted (2025-10-23)

**Summary**: `ClassifiedDataFrame` implements immutable classification with constructor protection.

**Security Properties**:
- **Immutable**: Classification cannot be modified after creation (frozen dataclass)
- **Uplifting Only**: Classification can only increase via `max()` operation
- **Constructor Protection**: Only datasources can create instances (prevents laundering)
- **Access Validation**: Runtime failsafe via `validate_access_by()`

**Threat Prevention**:
- **T3 (Runtime Bypass)**: `validate_access_by()` catches start-time validation bypass
- **T4 (Classification Mislabeling)**: Constructor protection prevents laundering attacks

**API**:
```python
# ✅ Datasource creation (trusted)
frame = ClassifiedDataFrame.create_from_datasource(data, SecurityLevel.OFFICIAL)

# ✅ Plugin uplifting (automatic max)
uplifted = frame.with_uplifted_classification(plugin.get_security_level())

# ❌ Direct construction (blocked)
frame = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)  # SecurityValidationError
```

**Impact**: Prevents data laundering and downgrade attacks. All data flows through ClassifiedDataFrame.

**See Also**: [ClassifiedDataFrame API](../api-reference/core/classified-dataframe.md), [ADR-002](#adr-002-multi-level-security-enforcement)

**Full ADR**: [docs/architecture/decisions/002-a-trusted-container-model.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/002-a-trusted-container-model.md)

---

### ADR-002b: Immutable Security Policy Metadata

**Status**: 🟡 Proposed (2025-10-26)

**Summary**: Security policy metadata (`security_level`, `allow_downgrade`) is immutable, author-owned, and cannot be overridden via configuration.

**Problem Prevented**:
```yaml
# ❌ REJECTED: Configuration overrides security policy
datasource:
  type: azure_blob_secret
  security_level: UNOFFICIAL  # ← Override from SECRET to UNOFFICIAL
  allow_downgrade: true       # ← Enable downgrade for frozen plugin
```

**Policy Field Classification**:
- **Immutable** (plugin-author-owned): `security_level`, `allow_downgrade`, `max_operating_level`
- **Mutable** (operator-configurable): `path`, `container`, `timeout`, `batch_size`, etc.

**Registry Enforcement**:
- Configuration exposing forbidden policy fields → `RegistrationError`
- Security policy hardcoded in plugin implementation, certified with code
- Aligns with ADR-005 (frozen plugins) and ADR-014 (reproducibility bundles)

**Impact**: Prevents silent security bypass via configuration. Security policy is code-certified, not user-configurable.

**See Also**: [ADR-002](#adr-002-multi-level-security-enforcement), [ADR-005](#adr-005-frozen-plugin-protection)

**Full ADR**: [docs/architecture/decisions/002-b-security-policy-metadata.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/002-b-security-policy-metadata.md)

---

### ADR-004: Mandatory BasePlugin Inheritance

**Status**: ✅ Accepted (2025-10-23)

**Summary**: All plugins must explicitly inherit from `BasePlugin` ABC (nominal typing, not duck typing).

**Why ABC over Protocol?**
- **Nominal typing**: `isinstance(plugin, BasePlugin)` requires explicit inheritance
- **Security enforcement**: Prevents bypass via duck-typed classes
- **"Security Bones"**: Concrete `@final` methods prevent override

**Security Methods (non-overridable)**:
- `get_security_level()` - Returns plugin clearance
- `validate_can_operate_at_level()` - Enforces Bell-LaPadula rules

**Runtime Enforcement**:
- `__init_subclass__` hook prevents override attempts
- Attempting to override raises `TypeError` at class definition time

**Impact**: Foundation of ADR-002 security validation. All plugins use consistent security logic.

**See Also**: [BasePlugin API](../api-reference/core/base-plugin.md), [ADR-002](#adr-002-multi-level-security-enforcement)

**Full ADR**: [docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md)

---

### ADR-005: Frozen Plugin Protection

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Plugins can opt-out of trusted downgrade via `allow_downgrade=False`.

**Use Case**: Dedicated infrastructure that should NEVER serve lower-classified pipelines.

**Example**:
```python
class FrozenSecretDataSource(BasePlugin):
    def __init__(self):
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False  # ← Frozen at SECRET only
        )

# ✅ Can operate at SECRET (exact match)
frozen.validate_can_operate_at_level(SecurityLevel.SECRET)

# ❌ Cannot operate at OFFICIAL (rejects downgrade)
frozen.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # Raises SecurityValidationError
```

**Bell-LaPadula Directionality**:
- **Data classification**: Can only INCREASE (UNOFFICIAL → SECRET)
- **Plugin operations**: Can only DECREASE (SECRET → UNOFFICIAL), unless frozen

**Impact**: Allows dedicated SECRET infrastructure that refuses to handle lower-classified data.

**See Also**: [BasePlugin API](../api-reference/core/base-plugin.md), [ADR-002](#adr-002-multi-level-security-enforcement)

**Full ADR**: [docs/architecture/decisions/005-frozen-plugin-capability.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/005-frozen-plugin-capability.md)

---

### ADR-006: Security-Critical Exception Policy

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Defines exception hierarchy for security-critical vs. operational errors.

**Exception Taxonomy**:

| Exception | When to Raise | Recovery |
|-----------|---------------|----------|
| `SecurityCriticalError` | Security control failure (PII detected, insufficient clearance) | ❌ Never catch (fail-closed) |
| `SecurityValidationError` | Invalid security configuration | ❌ Never catch (fail-fast) |
| `ConfigurationError` | Invalid YAML/schema | ✅ Catch at CLI (show user-friendly message) |
| `OperationalError` | Network timeout, file not found | ✅ Catch and retry or log |

**Key Principle**: Security exceptions are **never caught** - they propagate to top-level and abort execution.

**Example**:
```python
# ❌ NEVER catch security exceptions
try:
    plugin.validate_can_operate_at_level(level)
except SecurityValidationError:
    logging.warning("Insufficient clearance, continuing anyway")  # FORBIDDEN

# ✅ Let security exceptions propagate
plugin.validate_can_operate_at_level(level)  # Raises SecurityValidationError → abort
```

**Impact**: Ensures fail-closed behavior for all security controls.

**See Also**: [ADR-001](#adr-001-design-philosophy) (Fail-Closed Principle)

**Full ADR**: [docs/architecture/decisions/006-security-critical-exception-policy.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/006-security-critical-exception-policy.md)

---

## Architecture & Design Patterns

### ADR-003: Plugin Type Registry

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Plugin registries use factory pattern with JSON schema validation.

**Registry Types**:
- `DatasourceRegistry` - CSV, Azure Blob
- `TransformRegistry` - LLM clients, middleware
- `SinkRegistry` - CSV, Excel, signed artifacts
- `ExperimentPluginRegistry` - Row, aggregation, validation plugins

**Benefits**:
- Schema validation before instantiation
- Context-aware plugin creation
- Centralized plugin discovery

**Impact**: Foundation of plugin architecture. All plugins register via factories.

**See Also**: [Plugin Registry API](../api-reference/registries/base.md)

**Full ADR**: [docs/architecture/decisions/003-plugin-type-registry.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/003-plugin-type-registry.md)

---

### ADR-007: Universal Dual-Output Protocol

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Sinks return metadata for downstream consumers via dual-output pattern.

**Pattern**:
```python
def write(self, frame: ClassifiedDataFrame, metadata: dict) -> dict:
    """Write data and return metadata for downstream."""
    # Write data
    path = write_csv(frame.data)

    # Return metadata for downstream sinks
    return {"output_path": path, "row_count": len(frame.data)}
```

**Benefits**:
- Sink chaining (signed bundles consume CSV outputs)
- Metadata propagation (costs, retries, paths)
- Backward compatible (return value optional)

**Impact**: Enables artifact pipeline dependency resolution.

**See Also**: [Artifact Pipeline API](../api-reference/pipeline/artifact-pipeline.md)

**Full ADR**: [docs/architecture/decisions/007-universal-dual-output-protocol.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/007-universal-dual-output-protocol.md)

---

### ADR-008: Unified Registry Pattern

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Consolidates registry implementations under `BasePluginRegistry[T]`.

**Before**: 5 duplicate registry implementations
**After**: Single `BasePluginRegistry[T]` with generic type parameter

**Benefits**:
- Code reuse (1 implementation, not 5)
- Consistency (same validation logic everywhere)
- Type safety (generic `T` for plugin type)

**Impact**: Simplified plugin architecture with consistent validation.

**See Also**: [Plugin Registry API](../api-reference/registries/base.md)

**Full ADR**: [docs/architecture/decisions/008-unified-registry-pattern.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/008-unified-registry-pattern.md)

---

### ADR-009: Configuration Composition

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Configuration merges in predictable order: defaults → prompt packs → experiment overrides.

**Merge Order**:
```
1. Suite defaults (settings.yaml)
        ↓
2. Prompt packs (optional)
        ↓
3. Experiment overrides (experiments/*.yaml)
```

**Merge Rules**:
- **Simple values**: Later overwrites earlier
- **Lists** (middleware, sinks): Later appends to earlier (unless `inherit: false`)
- **Nested objects**: Deep merge (only specified keys overwrite)

**Benefits**:
- Define security middleware once (suite defaults)
- Share prompts across experiments (prompt packs)
- Override per-experiment as needed

**Impact**: Foundation of configuration system. Enables DRY configuration.

**See Also**: [Configuration Guide](../user-guide/configuration.md)

**Full ADR**: [docs/architecture/decisions/009-configuration-composition.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/009-configuration-composition.md)

---

### ADR-010: Pass-Through Lifecycle and Routing

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Middleware lifecycle events (suite loaded, retry exhausted) propagate to all middleware instances.

**Lifecycle Hooks**:
- `on_suite_loaded()` - Suite starts (share state across experiments)
- `on_retry_exhausted()` - Row retry failed (publish failure telemetry)

**Benefits**:
- Middleware can track suite-level state
- Telemetry captures retry context
- Azure ML run integration

**Impact**: Enables suite-aware middleware (health monitoring, cost aggregation).

**Full ADR**: [docs/architecture/decisions/010-pass-through-lifecycle-and-routing.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/010-pass-through-lifecycle-and-routing.md)

---

### ADR-011: Error Classification and Recovery

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Defines error taxonomy and recovery strategies for operational errors.

**Error Categories**:
- **Transient** (network timeout) → Retry with exponential backoff
- **Invalid Input** (malformed data) → Skip row or abort
- **Resource Exhaustion** (rate limit) → Wait and retry
- **Security** (insufficient clearance) → Abort immediately (fail-closed)

**Recovery Strategies**:
- `on_error: abort` - Stop pipeline immediately
- `on_error: skip` - Log error and continue
- `on_error: log` - Log warning and continue

**Impact**: Enables resilient pipelines with configurable error handling.

**See Also**: [ADR-006](#adr-006-security-critical-exception-policy)

**Full ADR**: [docs/architecture/decisions/011-error-classification-and-recovery.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/011-error-classification-and-recovery.md)

---

## Quality & Operations

### ADR-012: Testing Strategy and Quality Gates

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Defines testing requirements and quality gates for CI/CD.

**Test Categories**:
- **Unit Tests**: ≥80% coverage on core modules
- **Integration Tests**: End-to-end experiment runs
- **Security Tests**: Validation bypass attempts, classification laundering
- **Performance Tests**: Baseline latency and throughput

**Quality Gates**:
- ✅ All tests passing (100%)
- ✅ MyPy clean (type checking)
- ✅ Ruff clean (linting)
- ✅ Coverage ≥80% on security-critical paths
- ✅ No known vulnerabilities (audit)

**Impact**: Ensures code quality and security before deployment.

**See Also**: Testing documentation in developer docs

**Full ADR**: [docs/architecture/decisions/012-testing-strategy-and-quality-gates.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/012-testing-strategy-and-quality-gates.md)

---

### ADR-013: Global Observability Policy

**Status**: ✅ Accepted (2025-10-23)

**Summary**: Defines logging, telemetry, and audit trail requirements.

**Logging Requirements**:
- **Structured Logging**: JSON format (JSONL)
- **Audit Trail**: All security decisions logged
- **Correlation IDs**: Track requests across components
- **Security Classification**: Log metadata includes security level

**Log Levels**:
- **ERROR**: Security violations, unrecoverable errors
- **WARNING**: Operational issues, retry attempts
- **INFO**: Normal execution (datasource loaded, sinks written)
- **DEBUG**: Detailed execution trace

**Audit Events**:
- Security validation decisions
- Classification uplifts
- Retry attempts and exhaustion
- Cost and token usage

**Impact**: Enables compliance audits and troubleshooting.

**See Also**: Audit logging documentation in operations docs

**Full ADR**: [docs/architecture/decisions/013-global-observability-policy.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/013-global-observability-policy.md)

---

### ADR-014: Tamper-Evident Reproducibility Bundle

**Status**: ✅ Accepted (2025-10-26)

**Summary**: Elspeth emits a single, cryptographically signed, tamper-evident reproducibility bundle for every experiment suite execution.

**Compliance Requirements**:
- Government PSPF, HIPAA, PCI-DSS, defence export control
- Auditors must verify: what data/config/prompts/code produced results
- Detect post-run modifications to artifacts

**Core Requirements**:

1. **Mandatory Reproducibility Sink**:
   - `ReproducibilityBundleSink` enabled by default in production templates
   - Explicit opt-out required with formal risk acceptance

2. **Comprehensive Contents**:
   - Experiment results (JSON + sanitized CSV)
   - Source data snapshot + datasource config
   - Full merged configuration + rendered prompts
   - Plugin source code used during run
   - Optional framework source code
   - All artifacts from other sinks (logs, analytics)
   - Sanitization metadata

3. **Cryptographic Integrity**:
   - Every file hashed (SHA-256) and recorded in `MANIFEST.json`
   - Manifest signed using configured algorithm: `hmac-sha256`, `hmac-sha512`, `rsa-pss-sha256`, `ecdsa-p256-sha256`
   - Signature stored in `SIGNATURE.json`
   - Final archive: `.tar` or `.tar.gz` with signed manifest

4. **Immutable Policy Metadata** (ADR-002-B alignment):
   - Sink has hard-coded `security_level=SecurityLevel.UNOFFICIAL` and `allow_downgrade=True`
   - Operators cannot lower signing requirements via configuration

**Verification**:
```bash
python -m elspeth.cli verify-bundle \
  --bundle-path outputs/bundle_2025-10-26_experiment.tar.gz \
  --public-key /path/to/signing.pub
```

**Impact**: Every run is independently auditable with tamper detection. Meets compliance requirements for reproducibility.

**See Also**: [ADR-002-B](#adr-002b-immutable-security-policy-metadata), Artifact signing documentation

**Full ADR**: [docs/architecture/decisions/014-reproducibility-bundle.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/014-reproducibility-bundle.md)

---

## Reading Guide

### By Role

**Security Architect**:
- [ADR-001](#adr-001-design-philosophy) - Fail-closed principle
- [ADR-002](#adr-002-multi-level-security-enforcement) - Bell-LaPadula MLS
- [ADR-002a](#adr-002a-trusted-container-model) - Immutable classification
- [ADR-002b](#adr-002b-immutable-security-policy-metadata) - Immutable security policy
- [ADR-004](#adr-004-mandatory-baseplugin-inheritance) - Security bones
- [ADR-005](#adr-005-frozen-plugin-protection) - Dedicated infrastructure
- [ADR-006](#adr-006-security-critical-exception-policy) - Security exceptions
- [ADR-014](#adr-014-tamper-evident-reproducibility-bundle) - Tamper-evident bundles

**Plugin Developer**:
- [ADR-003](#adr-003-plugin-type-registry) - Registry pattern
- [ADR-004](#adr-004-mandatory-baseplugin-inheritance) - BasePlugin requirements
- [ADR-007](#adr-007-universal-dual-output-protocol) - Sink metadata return
- [ADR-008](#adr-008-unified-registry-pattern) - Registry API

**Operations/SRE**:
- [ADR-001](#adr-001-design-philosophy) - Priority hierarchy
- [ADR-011](#adr-011-error-classification-and-recovery) - Error recovery strategies
- [ADR-013](#adr-013-global-observability-policy) - Logging and telemetry

**Configuration Manager**:
- [ADR-009](#adr-009-configuration-composition) - Merge order
- [ADR-010](#adr-010-pass-through-lifecycle-and-routing) - Middleware lifecycle

### By Topic

**Security**:
- [ADR-001](#adr-001-design-philosophy), [ADR-002](#adr-002-multi-level-security-enforcement), [ADR-002a](#adr-002a-trusted-container-model), [ADR-002b](#adr-002b-immutable-security-policy-metadata), [ADR-004](#adr-004-mandatory-baseplugin-inheritance), [ADR-005](#adr-005-frozen-plugin-protection), [ADR-006](#adr-006-security-critical-exception-policy)

**Architecture**:
- [ADR-003](#adr-003-plugin-type-registry), [ADR-007](#adr-007-universal-dual-output-protocol), [ADR-008](#adr-008-unified-registry-pattern), [ADR-009](#adr-009-configuration-composition), [ADR-010](#adr-010-pass-through-lifecycle-and-routing)

**Reliability**:
- [ADR-011](#adr-011-error-classification-and-recovery), [ADR-012](#adr-012-testing-strategy-and-quality-gates)

**Operations**:
- [ADR-013](#adr-013-global-observability-policy)

**Compliance**:
- [ADR-014](#adr-014-tamper-evident-reproducibility-bundle)

---

## ADR Process

### When to Write an ADR

Create an ADR when making decisions about:
- ✅ **Security model** changes
- ✅ **Plugin architecture** changes
- ✅ **Configuration structure** changes
- ✅ **Error handling** strategy changes
- ✅ **Testing** or quality gate changes
- ✅ **Breaking changes** to public APIs

### ADR Template

Use the template at [docs/architecture/decisions/000-template.md](https://github.com/johnm-dta/elspeth/blob/main/docs/architecture/decisions/000-template.md).

---

## Related Documentation

- **[Architecture Overview](overview.md)** - System architecture guide
- **[Security Model](../user-guide/security-model.md)** - Bell-LaPadula MLS user guide
- **[API Reference](../api-reference/index.md)** - Plugin development APIs

---

!!! tip "Understanding Elspeth"
    ADRs provide the **"why"** behind Elspeth's design. Read them to understand:

    - Why security-first priority hierarchy? → [ADR-001](#adr-001-design-philosophy)
    - Why Bell-LaPadula MLS? → [ADR-002](#adr-002-multi-level-security-enforcement)
    - Why immutable classification? → [ADR-002a](#adr-002a-trusted-container-model)
    - Why ABC not Protocol? → [ADR-004](#adr-004-mandatory-baseplugin-inheritance)
    - Why fail-closed exceptions? → [ADR-006](#adr-006-security-critical-exception-policy)

    Start with ADR-001 and ADR-002 for foundational understanding.
