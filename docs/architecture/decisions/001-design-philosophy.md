# ADR 001 – Design Philosophy

## Status

**Accepted** (2025-10-23)

**Last Updated**: 2025-10-28

## Context

### Problem Statement

Elspeth orchestrates experiments that may process sensitive data subject to stringent regulatory requirements, including Australian Government security frameworks (Protected Security Policy Framework, Information Security Manual), healthcare regulations (HIPAA), and financial compliance standards (PCI-DSS). The system must support:

1. **Confidentiality controls** for classified data at multiple security levels
2. **Reproducible analytics** with tamper-evident audit trails
3. **Operational resilience** with graceful error handling
4. **Developer productivity** through extensibility and clear APIs

Without an explicit priority hierarchy, engineering teams face inconsistent trade-off decisions when security conflicts with usability, or when availability pressures threaten data integrity. Common failure modes include:

- **Graceful degradation in security controls** – Fallback paths that bypass enforcement
- **Availability prioritised over confidentiality** – "Keep the system running" at security cost
- **Usability shortcuts that weaken integrity** – Skipping validation for convenience
- **Ad-hoc security decisions** – No consistent framework for resolving conflicts

### Threat Model Considerations

High-security orchestration systems face specific attack vectors that inform this philosophy:

1. **Insider threats** – Malicious or compromised operators with legitimate access
2. **Configuration tampering** – Attackers modifying settings to bypass controls
3. **Control failure exploitation** – Triggering security control failures to access data
4. **Gradual privilege escalation** – Chaining small bypasses into significant breaches

Traditional availability-first approaches (fail-open, graceful degradation) are incompatible with defence-in-depth security architectures required for classified data systems.

### Regulatory Context

Australian Government security certification (IRAP assessments, Authority to Operate applications) requires demonstrable security-first design with explicit trade-off resolution frameworks. This ADR establishes the foundation for ISM control implementation and compliance evidence generation.

## Decision

### Priority Hierarchy

We establish the following **immutable order of priorities** for all architectural and implementation decisions:

1. **Security** – Prevent unauthorised access, leakage, or downgrade of classified data
2. **Data Integrity** – Ensure results, artefacts, and provenance are trustworthy and reproducible; maintain tamper-evident audit trails
3. **Availability** – Keep orchestration reliable and recoverable (checkpointing, retries, graceful failure), subject to security and integrity constraints
4. **Usability / Functionality** – Provide developer ergonomics, extensibility, and feature depth, without compromising higher priorities

**Trade-off Resolution Principle**: When priorities conflict, the higher-ranked concern wins unconditionally.

**Examples of Priority Enforcement**:

| Scenario | Lower Priority | Higher Priority Wins | Decision |
|----------|----------------|----------------------|----------|
| Security vs Availability | Keep pipeline running | Protect classified data | Fail closed rather than serve data to low-clearance sink |
| Integrity vs Functionality | Add convenient feature | Maintain reproducibility | Drop features that break reproducibility or tamper-evidence |
| Security vs Usability | Simplified authentication | Prevent unauthorised access | Require multi-factor authentication despite UX friction |
| Integrity vs Availability | Continue on errors | Preserve audit trail | Abort pipeline if audit logging fails |
| Security vs Functionality | Allow flexible configurations | Enforce security boundaries | Reject plugins that cannot declare security level |

### Fail-Closed Principle (Security-First Enforcement)

**Status**: Mandatory requirement for all security controls

**Policy**:

All security controls in Elspeth **MUST fail-closed** when the control itself is unavailable, degraded, or cannot be verified.

**Definitions**:

- **Fail-closed (secure)**: Deny the operation when security enforcement cannot be validated or is unavailable
- **Fail-open (insecure)**: Allow the operation when security enforcement cannot be validated or is unavailable

**Enforcement Rules**:

When a security control cannot operate due to missing dependencies, runtime limitations, or verification failure:

- ✅ **REQUIRED**: Raise an exception and deny the operation (fail-closed)
- ✅ **REQUIRED**: Include detailed diagnostic information (what failed, why it failed, security impact)
- ❌ **FORBIDDEN**: Log a warning and allow the operation (fail-open)
- ❌ **FORBIDDEN**: Return sentinel values (None, False, empty collections) on security failures
- ❌ **FORBIDDEN**: Feature flags or configuration options to disable security controls in production

**Security Rationale**:

Fail-open behaviour creates exploitable attack surfaces where adversaries can deliberately trigger control failures to bypass security enforcement. In classified data systems operating under Bell-LaPadula Multi-Level Security models (see ADR-002), allowing operations when security is unverifiable violates fundamental confidentiality requirements and creates regulatory non-compliance.

**Attack Scenarios Prevented**:

1. **Control bypass via resource exhaustion** – Attacker exhausts authentication service, system fails open
2. **Dependency removal attacks** – Attacker removes security library, system continues without validation
3. **Configuration tampering** – Attacker modifies settings to trigger fallback paths with weaker enforcement
4. **Environmental manipulation** – Attacker alters runtime environment to disable security features

**Fail-Closed Implementation Examples**:

| Scenario | ❌ Fail-Open (Insecure - FORBIDDEN) | ✅ Fail-Closed (Secure - REQUIRED) |
|----------|-------------------------------------|-------------------------------------|
| Stack inspection unavailable (Python runtime limitation) | Allow `SecureDataFrame` creation with warning | `SecurityValidationError` – Cannot verify caller identity |
| Authentication service unreachable | Grant access with degraded logging | Deny access – Cannot verify credentials |
| Encryption key not available | Store data in plaintext with warning | Refuse to store – Cannot protect confidentiality |
| Security level unknown (plugin missing declaration) | Assume `UNOFFICIAL` (lowest level) | Require explicit declaration – Reject plugin instantiation |
| Signature verification fails (corrupted or missing) | Accept unsigned artefact | `SignatureValidationError` – Reject artefact |
| Operating level not set (pre-validation state) | Return plugin's declared clearance level | `RuntimeError` – Programming error, fail loudly |
| Path validation dependencies missing | Allow write to any location | Fail write operation – Cannot verify path safety |

**Reference Implementations**:

The following production code demonstrates fail-closed enforcement:

1. **Stack Inspection Failure** (`src/elspeth/core/security/secure_data.py:88-102`)
   ```python
   frame = inspect.currentframe()
   if frame is None:
       # SECURITY: Fail-closed when stack inspection unavailable (CVE-ADR-002-A-003)
       raise SecurityValidationError(
           "Cannot verify caller identity - stack inspection is unavailable. "
           "SecureDataFrame creation blocked for security."
       )
   ```
   **Context**: `SecureDataFrame` uses stack inspection to verify creation only from trusted callers (datasources or trusted container methods). If Python runtime doesn't support stack inspection, deny creation rather than allowing unverified construction.

2. **Path Validation Enforcement** (`src/elspeth/core/utils/path_guard.py:18-38`)
   ```python
   def resolve_under_base(target: Path, base: Path) -> Path:
       """Resolve target under base without following the final component.

       Raises:
           ValueError: If path escapes allowed base (fail-closed)
       """
       # ... validation logic ...
       if common != base_resolved:
           raise ValueError(f"Path parent '{parent_resolved}' escapes allowed base")
   ```
   **Context**: File sinks validate all write paths remain within allowed directories. If validation cannot confirm path safety, reject write operation. Verified by `tests/test_runner_characterization.py:377-400`.

3. **Operating Level Access** (`src/elspeth/core/base/plugin.py:254-336`)
   ```python
   @final
   def get_effective_level(self) -> SecurityLevel:
       """Return pipeline operating level (fail-loud if not set)."""
       context = getattr(self, 'plugin_context', None)
       if context is None:
           raise RuntimeError(
               f"{type(self).__name__}.get_effective_level() called before plugin_context attached. "
               f"This is a programming error."
           )
       if context.operating_level is None:
           raise RuntimeError(
               f"{type(self).__name__}.get_effective_level() called before pipeline validation."
           )
       return context.operating_level
   ```
   **Context**: Plugins access pipeline operating level for security-aware decisions. If operating level hasn't been computed (programming error), fail loudly rather than returning a default or fallback value.

4. **Security Validation** (`src/elspeth/core/experiments/suite_runner.py:635-680`)
   ```python
   def _validate_experiment_security(
       self, experiment: ExperimentConfig, runner: ExperimentRunner,
       sinks: list[ResultSink], ctx: SuiteExecutionContext
   ) -> None:
       """Validate experiment security using ADR-002 minimum clearance envelope.

       Raises:
           SecurityValidationError: If any plugin has insufficient clearance
       """
       # Collect all plugins, compute minimum, validate all can operate
       # Abort pipeline construction on any validation failure
   ```
   **Context**: Suite runner validates all plugins have sufficient clearance for pipeline operating level. Any insufficient clearance aborts pipeline construction before data access.

**Testing Requirements**:

All security controls with fail-closed behaviour MUST have test coverage verifying:

1. ✅ Success path when security control is available and validation passes
2. ✅ Failure path when security control is unavailable (raises exception, does not continue)
3. ✅ Failure path when security validation fails (raises exception with diagnostic message)
4. ✅ Exception messages are detailed and actionable (what/why/where)

### Fail-Loud Principle (NO Graceful Degradation)

**Status**: Mandatory requirement for all security-critical operations

**Policy**:

When anything is not 100% correct in security-critical paths, we **FAIL LOUD** immediately with obvious, detailed errors. Graceful degradation is an attack vector in high-security systems.

**Enforcement Rules**:

- ✅ **REQUIRED**: Raise `RuntimeError`, `SecurityValidationError`, or similar exception immediately at detection point
- ✅ **REQUIRED**: Include detailed diagnostic message explaining what failed, why it failed, expected vs actual state, and security impact
- ✅ **REQUIRED**: Fail immediately at point of detection (don't defer, accumulate, or batch security errors)
- ✅ **REQUIRED**: Make failure impossible to ignore (exception propagates to pipeline coordinator, logs at ERROR level, includes stack trace)
- ❌ **FORBIDDEN**: Graceful degradation (fallbacks to weaker controls, default values, "best effort" modes)
- ❌ **FORBIDDEN**: Silent failures (logging warning/info and continuing execution)
- ❌ **FORBIDDEN**: Returning sentinel values (None, False, empty collections, success=False flags) on security failures
- ❌ **FORBIDDEN**: "Try to recover" logic in security-critical paths (recover at architectural boundaries only)
- ❌ **FORBIDDEN**: Convenience flags for bypassing security (no "skip SSL verification", "disable signing", "trust all" options)

**Security Rationale**:

Graceful degradation in security controls creates four critical vulnerabilities:

1. **Delayed detection** – Operators don't notice security failures until damage is done (hours/days later in audit logs)
2. **Attack surface expansion** – Adversaries trigger fallback paths to access weaker security controls
3. **Partial operation risk** – System limps along in insecure states ("works on my machine" with degraded security)
4. **Root cause obscurity** – Security failures hidden by layers of fallback logic and partial success states

By failing loud and failing immediately, we:

- **Stop execution at failure point** – Prevent security failure from propagating or compounding
- **Make failures impossible to ignore** – Operators must investigate and resolve before continuing
- **Provide diagnostic context** – Detailed error messages enable rapid root cause analysis
- **Enforce all-or-nothing semantics** – No half-broken states, no partial security

**Fail-Loud Implementation Examples**:

| Scenario | ❌ Graceful Degradation (FORBIDDEN) | ✅ Fail Loud (REQUIRED) |
|----------|-------------------------------------|-------------------------|
| Operating level not set (programming error) | `return self.security_level` (fallback to declared clearance) | `RuntimeError` with diagnostic: "get_effective_level() called before pipeline validation. This is a programming error - operating level must be set during validation." |
| Plugin context missing (lifecycle error) | Return default context object | `RuntimeError`: "plugin_context not attached. This is a programming error - context attachment happens during pipeline initialisation." |
| Security level validation fails (insufficient clearance) | Log warning, skip plugin, continue pipeline | `SecurityValidationError`: "Plugin has clearance OFFICIAL but pipeline requires PROTECTED. Insufficient clearance (Bell-LaPadula MLS violation). Aborting pipeline." |
| Signature missing from artefact (integrity violation) | Accept unsigned artefact with warning | `SignatureValidationError`: "Artefact signature missing or invalid. Cannot verify integrity. Rejecting artefact." |
| Clearance insufficient (MLS violation) | Skip plugin execution, continue experiment | `SecurityValidationError`: "Datasource clearance insufficient for pipeline operating level. Aborting experiment construction." |
| Audit logger unavailable (integrity control failure) | Continue without audit trail | `RuntimeError`: "Audit logger initialisation failed. Cannot guarantee integrity. Aborting pipeline." |
| Path traversal detected (directory escape attempt) | Sanitise path and continue | `ValueError`: "Path parent '/etc/passwd' escapes allowed base '/app/data'. Rejecting write operation." |

**Implementation Requirements for Fail-Loud**:

1. **Exception Types**:
   - Use `SecurityValidationError` for security policy violations (insufficient clearance, MLS violations)
   - Use `RuntimeError` for programming errors (wrong lifecycle usage, missing required state)
   - Use domain-specific exceptions for integrity failures (`SignatureValidationError`, `ChecksumMismatchError`)

2. **Exception Messages** MUST include:
   - **What failed**: Specific control, validation, or operation
   - **Why it failed**: Root cause, expected vs actual state
   - **Security impact**: What risk the failure creates
   - **Remediation hint**: Where to look or what to fix (when applicable)

   **Example**:
   ```python
   raise SecurityValidationError(
       f"{type(self).__name__} has clearance {self._security_level.name}, "
       f"but pipeline requires {operating_level.name}. "
       f"Insufficient clearance for higher classification (Bell-LaPadula MLS violation). "
       f"Ensure plugin security_level matches or exceeds pipeline operating level."
   )
   ```

3. **No Recovery in Security Paths**:
   - Security validation functions MUST raise exceptions on failure (never return False/None)
   - NO "try to recover" logic within security enforcement code
   - Recovery only at architectural boundaries (suite coordinator, experiment runner)
   - Recovery MUST NOT bypass security checks or retry with weakened enforcement

4. **Audit Logging for Security Failures**:
   - All security exceptions MUST be logged at ERROR level before propagating
   - Include security context (operating level, plugin clearances, attempted operation)
   - Capture attempted bypass attempts for security monitoring
   - Preserve full exception context and stack trace

**Reference Implementations**:

The following production code demonstrates fail-loud enforcement:

1. **Operating Level Not Set** (`src/elspeth/core/base/plugin.py:319-332`)
   ```python
   if context is None:
       raise RuntimeError(
           f"{type(self).__name__}.get_effective_level() called before plugin_context attached. "
           f"This is a programming error - plugins must not call get_effective_level() during construction."
       )
   if context.operating_level is None:
       raise RuntimeError(
           f"{type(self).__name__}.get_effective_level() called before pipeline validation. "
           f"Operating level is computed during validation and propagated via _propagate_operating_level()."
       )
   ```
   **Context**: Plugins accessing operating level before validation completes indicates programming error (wrong lifecycle usage). Fail immediately with detailed diagnostic rather than returning fallback value.

2. **Insufficient Clearance** (`src/elspeth/core/base/plugin.py:376-382`)
   ```python
   @final
   def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
       """Validate plugin can operate at given security level (Bell-LaPadula MLS)."""
       if operating_level > self._security_level:
           raise SecurityValidationError(
               f"{type(self).__name__} has clearance {self._security_level.name}, "
               f"but pipeline requires {operating_level.name}. "
               f"Insufficient clearance for higher classification (Bell-LaPadula MLS violation)."
           )
   ```
   **Context**: Plugins with insufficient clearance cannot access higher-classification data. Fail immediately rather than attempting to run with limited access or skipping the plugin.

3. **Frozen Plugin Downgrade Rejection** (`src/elspeth/core/base/plugin.py:384-390`)
   ```python
   if operating_level < self._security_level and not self._allow_downgrade:
       raise SecurityValidationError(
           f"{type(self).__name__} is frozen at {self._security_level.name} "
           f"(allow_downgrade=False). Cannot operate at lower level {operating_level.name}. "
           f"This plugin requires exact level matching and does not support trusted downgrade."
       )
   ```
   **Context**: Frozen plugins (ADR-005) require exact security level matching. Attempting to use at different level fails loudly rather than adapting behaviour.

**Architectural Boundaries for Recovery**:

While security controls fail loud immediately, system-level recovery is handled at specific architectural boundaries:

- **Experiment Suite Runner**: Catches experiment-level failures, logs context, continues to next experiment (isolation)
- **Pipeline Coordinator**: Catches plugin instantiation failures, aborts pipeline construction, reports to operator
- **CLI Entry Point**: Catches suite-level failures, reports to user, exits with error code

Recovery at these boundaries MUST NOT:
- Retry with weakened security controls
- Bypass validation that failed
- Mask security failures with generic error messages
- Continue processing with partial security enforcement

### Implementation Guidance

**For Plugin Authors**:

When implementing plugins (datasources, transforms, sinks):

1. **Security Level Declaration**: All plugins MUST declare `security_level` during construction (no defaults, no inference)
2. **Validation Usage**: Call `self.validate_can_operate_at_level(operating_level)` to verify clearance before data processing
3. **Operating Level Access**: Use `self.get_effective_level()` for security-aware decisions (filtering, conditional processing)
4. **Error Handling**: Raise exceptions on security failures (never return None/False/empty)
5. **No Bypass Flags**: Do not add configuration options to disable security features

**For Code Reviewers**:

Evaluate implementations against this priority hierarchy:

1. **Security Review** (Priority 1):
   - ✅ Fail-closed: Security controls raise exceptions when unavailable
   - ✅ Fail-loud: Detailed exception messages on all security failures
   - ✅ No bypass flags: No configuration options to weaken/disable security
   - ✅ Explicit declaration: Security level declared explicitly (no defaults)

2. **Integrity Review** (Priority 2):
   - ✅ Audit logging: All security-relevant operations logged
   - ✅ Reproducibility: Results deterministic given same inputs
   - ✅ Tamper-evidence: Signatures validated, checksums verified

3. **Availability Review** (Priority 3):
   - ✅ Error recovery at boundaries: Appropriate isolation/retry (subject to security constraints)
   - ✅ Resource cleanup: Proper cleanup on failure paths
   - ⚠️ Graceful degradation: Only for non-security features (performance optimisations, optional UI features)

4. **Usability Review** (Priority 4):
   - ✅ Clear error messages: Actionable diagnostics
   - ✅ Documentation: Security requirements documented
   - ⚠️ Convenience features: Only if higher priorities not compromised

**For CI/CD Pipeline**:

Enforce priority hierarchy through automated guardrails:

1. **Security Gates** (Priority 1 - MANDATORY):
   - Security scanning (SAST, dependency vulnerabilities)
   - License compliance (permissive licenses only, no GPL/AGPL)
   - Secret detection (no credentials in code/configs)
   - Type checking (MyPy strict mode for security-critical modules)

2. **Integrity Gates** (Priority 2 - MANDATORY):
   - Test coverage ≥80% for security-critical paths
   - Integration tests for security validation flows
   - Mutation testing for security test quality

3. **Availability Gates** (Priority 3 - ADVISORY):
   - Performance regression detection
   - Resource leak detection

4. **Functionality Gates** (Priority 4 - ADVISORY):
   - Linting (code style, complexity)
   - Documentation coverage

**Gates 1 and 2 MUST pass for merge approval. Gates 3 and 4 are advisory only.**

## Consequences

### Benefits

1. **Explicit Trade-off Resolution**
   - Engineering teams have clear guidance when priorities conflict
   - No ad-hoc security vs usability debates ("the ADR decides")
   - Consistent decision-making across features and components
   - Audit trail of design decisions referencing priority hierarchy

2. **Security by Design**
   - Security considerations embedded in every architectural decision from inception
   - Fail-closed and fail-loud principles prevent common security pitfalls
   - No "add security later" retrofitting with architectural compromises
   - Regulatory confidence from security-first approach

3. **Regulatory Confidence**
   - Priority hierarchy aligns with compliance frameworks:
     - Australian Government PSPF (confidentiality paramount for classified data)
     - ISM controls emphasising fail-safe defaults and least privilege
     - HIPAA Security Rule (confidentiality, integrity, availability in that order)
     - PCI-DSS (security controls cannot be bypassed or degraded)
   - Clear evidence for IRAP assessments and ATO applications
   - Auditors can verify design principles match implementation

4. **Predictable Behaviour**
   - Fail-fast patterns reduce unexpected security incidents
   - Loud failures during development/testing (caught early)
   - No silent security degradation in production
   - Clear operational expectations (system fails safely)

5. **Attack Surface Reduction**
   - Fail-closed eliminates bypass opportunities via control failures
   - Fail-loud prevents gradual privilege escalation via partial failures
   - Explicit priority ordering prevents security compromises for convenience
   - No fallback paths with weaker enforcement

### Limitations and Trade-offs

1. **Developer Friction**

   **Issue**: Security-first approach requires more ceremony (authentication, validation, audit logging) than developers may expect from permissive frameworks.

   **Impact**:
   - More boilerplate for plugin development (explicit security level declaration, validation calls)
   - Additional testing requirements (security validation test cases)
   - Steeper learning curve for new contributors
   - Longer code review cycles (security review before functionality review)

   **Mitigation**:
   - Comprehensive documentation with worked examples (`docs/development/plugin-authoring.md`)
   - Base classes providing security enforcement (`BasePlugin` with concrete security methods)
   - Code generation tools for plugin scaffolding (future ADR)
   - Clear error messages guiding developers to correct patterns
   - Investment in testing utilities (security mocks, validation fixtures)

   **Acceptance**: This friction is intentional and necessary. Elspeth targets high-security environments where the cost of security incidents far exceeds developer convenience.

2. **Conservative Operational Posture**

   **Issue**: System will abort operations when lower priorities (availability, usability) conflict with higher priorities (security, integrity).

   **Impact**:
   - Pipeline aborts on any security validation failure (no partial execution)
   - Strict clearance enforcement may require duplicating experiments with different security levels
   - Failed experiments in suite do not compromise subsequent experiments (isolation overhead)
   - Operators must resolve security issues immediately (cannot "work around" failures)

   **Mitigation**:
   - Comprehensive validation before execution (`validate-schemas` CLI command)
   - Detailed error messages for rapid troubleshooting
   - Experiment isolation prevents cascade failures
   - Dry-run mode for configuration testing without data access

   **Acceptance**: Conservative posture is intentional. Operational resilience comes FROM security enforcement, not despite it. Classified data systems cannot tolerate "keep it running" compromises.

3. **Feature Velocity Impact**

   **Issue**: Some features may be rejected or significantly delayed if they cannot meet security and integrity requirements.

   **Impact**:
   - Features requiring privileged access may need architectural review before implementation
   - "Quick and dirty" prototypes incompatible with security requirements
   - External integrations must support security model (may exclude some third-party libraries)
   - Performance optimisations subordinate to security (may limit caching, parallelism)

   **Mitigation**:
   - Plan security requirements during design phase (not as implementation afterthought)
   - Security review integrated into feature design process (not separate gate)
   - Architecture team support for complex security patterns
   - Documented patterns for common scenarios (secure caching, parallel processing with isolation)

   **Acceptance**: Feature velocity is subordinate to security correctness. A fast system that leaks classified data has negative value. Thoughtful design enables both security and functionality, but security wins when they conflict.

4. **Error Handling Complexity**

   **Issue**: Fail-loud principle increases error handling burden (cannot silently skip errors).

   **Impact**:
   - More exception types to handle and test
   - Detailed error messages require maintenance
   - Stack traces can be verbose (security context in exceptions)
   - Recovery logic concentrated at architectural boundaries

   **Mitigation**:
   - Clear exception hierarchy with documented semantics
   - Structured logging for error context
   - Testing utilities for exception verification
   - Boundary coordinators handle common recovery patterns

   **Acceptance**: Error handling complexity is visible but manageable. Silent failures are far more dangerous than explicit exceptions.

### Implementation Impact

This ADR affects all subsequent development:

1. **Architecture Decisions**:
   - All ADRs MUST reference this priority hierarchy when justifying design choices
   - Trade-offs explicitly documented with priority rankings
   - Security and integrity considerations addressed before availability and usability

2. **Code Review Process**:
   - Reviews evaluate whether implementations respect priority ordering
   - Security review is first gate (before functionality review)
   - Bypass flags or graceful security degradation require architecture team escalation

3. **CI/CD Guardrails**:
   - Security gates (SAST, dependency scanning, secret detection) are mandatory
   - Integrity gates (test coverage, mutation testing) are mandatory
   - Availability and functionality gates are advisory
   - Cannot merge without passing Priority 1 and 2 gates

4. **Plugin Acceptance Criteria**:
   - Security level declaration required before functionality review
   - Fail-closed and fail-loud patterns verified in plugin tests
   - No configuration options to bypass security enforcement
   - Documentation includes security implications and threat model

5. **Testing Requirements**:
   - Security validation paths require ≥80% coverage
   - Fail-closed behaviour verified for all security controls
   - Fail-loud behaviour verified with exception message assertions
   - Integration tests verify priority ordering (security blocks lower priorities)

6. **Documentation Standards**:
   - Security implications documented for all public APIs
   - Threat model included for security-critical components
   - Compliance mapping (ISM controls, HIPAA rules) for security features
   - Examples demonstrate secure usage patterns

## Related Documents

### Architecture Decision Records

- [ADR-002: Multi-Level Security Enforcement](002-security-architecture.md) – Bell-LaPadula MLS model implementation, operating level computation, pipeline validation (depends on this ADR's fail-closed and fail-loud principles)
- [ADR-002-A: Trusted Container Model](002-a-trusted-container-model.md) – Stack inspection-based access control for `SecureDataFrame`, demonstrating fail-closed when inspection unavailable
- [ADR-002-B: Security Policy Metadata](002-b-security-policy-metadata.md) – Security metadata propagation and validation (implements this ADR's fail-loud principle)
- [ADR-004: Mandatory BasePlugin Inheritance](004-mandatory-baseplugin-inheritance.md) – Concrete security enforcement in base class (implements this ADR's fail-closed validation requirements)
- [ADR-005: Frozen Plugins](docs/architecture/decisions/005-frozen-plugins.md) – Strict security level enforcement without downgrade (implements this ADR's fail-closed and fail-loud principles for level-specific plugins)

### Implementation References

**Core Security Modules**:
- `src/elspeth/core/base/plugin.py` – BasePlugin with sealed security methods (`get_security_level`, `get_effective_level`, `validate_can_operate_at_level`)
- `src/elspeth/core/security/secure_data.py` – SecureDataFrame with fail-closed stack inspection (lines 88-102)
- `src/elspeth/core/experiments/suite_runner.py` – Pipeline security validation (`_validate_experiment_security`, line 635+)
- `src/elspeth/core/utils/path_guard.py` – Fail-closed path validation for sink writes

**Security Control Documentation**:
- `docs/architecture/security-controls.md` – Comprehensive security control inventory with ISM mapping
- `docs/architecture/plugin-security-model.md` – Plugin security architecture and clearance model
- `docs/compliance/CONTROL_INVENTORY.md` – Security control evidence for certification
- `docs/compliance/TRACEABILITY_MATRIX.md` – ISM control traceability to implementation

**Testing References**:
- `tests/test_runner_characterization.py` – Characterisation tests verifying fail-closed behaviour (line 377: `test_checkpoint_config_fails_closed_on_missing_allowed_base`)
- `tests/test_security_*.py` – Security validation test suites
- `tests/security/test_security_hardening.py` – Security hardening integration tests

### Compliance Frameworks

This priority hierarchy aligns with:

- **Australian Government PSPF** – Confidentiality paramount for classified information
- **ISM Controls** – Fail-safe defaults (ISM-0421), least privilege (ISM-0432), mandatory access control (ISM-0441)
- **HIPAA Security Rule** – Confidentiality, integrity, availability (in that order per 45 CFR §164.306)
- **PCI-DSS** – Security controls cannot be bypassed (Requirement 6, 10, 11)
- **NIST SP 800-53** – AC (Access Control), AU (Audit), SC (System and Communications Protection) families

---

**Author(s)**: Architecture Team
**Reviewers**: Security Team, Compliance Team
**Related Vulnerabilities**: CVE-ADR-002-A-003 (stack inspection unavailability), path traversal vulnerabilities in sink writes
**Future Work**: ADR-005 (Frozen Plugins extending fail-closed to exact-level enforcement), Security certification package references
