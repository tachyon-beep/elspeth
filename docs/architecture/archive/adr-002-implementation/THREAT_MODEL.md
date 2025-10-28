# ADR-002 Threat Model & Risk Assessment

**⚠️ ARCHIVED DOCUMENT - CONTAINS INVERTED BELL-LAPADULA LOGIC**

This document is ARCHIVED and was written when Bell-LaPadula validation logic was INVERTED
throughout the codebase. T1 threat scenario and defense layers describe WRONG behavior.

**For current threat model, see**: `docs/security/adr-002-threat-model.md`

**Correct Model**: Plugin `security_level` = maximum clearance. Plugins CAN operate at lower
levels (trusted to filter). Plugins CANNOT operate above their clearance (insufficient clearance).

---

**Date**: 2025-10-25 (Updated)
**Status**: ADR-002 Phase 2 Complete ✅ | ADR-002-A Phase 3 Complete ✅ | Phase 4 Complete ✅
**Security Controls**:
1. Suite-level minimum clearance envelope (ADR-002)
2. Trusted container model - constructor protection (ADR-002-A)

---

## Executive Summary

**What we're preventing**: Classification breaches where SECRET data reaches UNOFFICIAL components.

**How**: Four-layer defense:
1. **Start-time validation** (PRIMARY - ADR-002): Job fails to start if any plugin requires higher security than minimum envelope
2. **Constructor protection** (TECHNICAL CONTROL - ADR-002-A): Framework blocks plugins from creating arbitrary SecureDataFrame instances, preventing classification laundering attacks
3. **Runtime failsafe** (DEFENSE IN DEPTH - ADR-002): Data access blocked if component clearance insufficient
4. **Certification** (VERIFICATION): Human review confirms Layers 1-3 correctly implemented

**Security Invariant**: No configuration can allow data to reach a component with lower security clearance.

**ADR-002-A Impact**: Reduces certification burden by blocking classification laundering attacks at framework level (previously required manual code review of every plugin transformation).

---

## Threat Catalog

### T1: Classification Breach (Direct Data Leakage)

**Scenario**: SECRET datasource configured with UNOFFICIAL sink

**Attack Vector**:
```python
# Misconfigured suite
suite = ExperimentSuite(
    datasource=SecretDatasource(),  # Requires SECRET clearance
    sinks=[UnofficialSink()],       # Only handles UNOFFICIAL data
)
# Without our control: SECRET data writes to UNOFFICIAL sink → CLASSIFICATION BREACH
```

**Impact**: **CRITICAL** - Direct violation of classification policy, potential data spillage

**Likelihood**: **HIGH** - Easy to misconfigure, especially in multi-agency environments

**Subtlety**: **LOW** - Obvious misconfiguration, but automation makes it easy to miss

**Defense Layers**:
- **Primary (Start-time)**: `_validate_security_envelope()` computes pipeline minimum and validates components
  - Datasource reports "I have SECRET clearance"
  - Sink reports "I have UNOFFICIAL clearance"
  - Orchestrator computes: `operating_level = MIN(SECRET, UNOFFICIAL) = UNOFFICIAL`
  - Validation: SECRET-cleared datasource CAN operate at UNOFFICIAL level (trusted to filter)
  - Validation: UNOFFICIAL-cleared sink CAN operate at UNOFFICIAL level (exact match)
  - **Note**: Start-time validation does NOT reject higher-clearance components at lower operating levels.
    It only rejects insufficient-clearance scenarios (component clearance < operating level).
- **Failsafe (Runtime)**: `SecureDataFrame.validate_compatible_with()` blocks data hand-off if classification exceeds clearance
  - Datasource must filter SECRET-tagged data when operating at UNOFFICIAL level (certified behavior)
  - If filtering fails and SECRET data reaches UNOFFICIAL sink → runtime validation catches it
  - If start-time validation bypassed/broken → runtime validation provides defense-in-depth
  - Datasource tries to give SECRET data to sink
  - Sink clearance checked: UNOFFICIAL < SECRET
  - Access BLOCKED with SecurityValidationError
- **Certification**: Auditor verifies both layers exist and work correctly

**Test Evidence**: `test_INTEGRATION_secret_datasource_rejects_unofficial_sink`

---

### T2: Security Downgrade Attack (Malicious Plugin)

**Scenario**: Compromised plugin lies about its security level

**Attack Vector**:
```python
class MaliciousSecretSink(BasePlugin):
    """Sink that actually handles SECRET but reports UNOFFICIAL to lower envelope."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL  # LIE - actually stores SECRET data

    def write(self, data: SecureDataFrame) -> None:
        # Secretly writes to UNOFFICIAL storage → classification breach
        write_to_unofficial_storage(data)
```

**Impact**: **CRITICAL** - Deliberate classification breach, subverts security controls

**Likelihood**: **LOW** - Requires compromised signed plugin (certification catches this)

**Subtlety**: **HIGH** - Looks legitimate, requires code review to detect

**Defense Layers**:
- **Primary (Start-time)**: Cannot prevent (malicious code lies about level)
- **Failsafe (Runtime)**: Cannot prevent (malicious code bypasses checks)
- **Certification (MUST CATCH)**:
  - Code review verifies `get_security_level()` returns true capability
  - Audit trail: Who signed plugin? When? What testing?
  - Cryptographic signing ensures tamper detection

**Out of Scope**: Framework CANNOT prevent malicious code (would require solving Halting Problem per Rice's Theorem)

**Mitigation**:
- Clear documentation that certification MUST verify security level honesty
- Audit trail for all plugin approvals
- Cryptographic signing detects post-certification tampering

**Test Evidence**: Documented as "Certification Must Verify" in evidence package

---

### T3: Runtime Bypass (Start-Time Validation Circumvented)

**Scenario**: Bug/exploit allows job to start despite failing validation

**Attack Vector**:
```python
# Scenario 1: Exception handling bug swallows SecurityValidationError
try:
    runner.run(...)
except SecurityValidationError:
    log.warning("Validation failed, continuing anyway")  # BUG!

# Scenario 2: Race condition - plugin changes security level after validation
plugin.get_security_level()  # Returns OFFICIAL at check time
# ... time passes ...
plugin._security_level = SecurityLevel.UNOFFICIAL  # Changed!
plugin.write(secret_data)  # Now at wrong level
```

**Impact**: **HIGH** - Classification breach due to implementation bug

**Likelihood**: **MEDIUM** - Possible if error handling or concurrency not carefully designed

**Subtlety**: **MEDIUM** - Requires specific bug conditions

**Defense Layers**:
- **Primary (Start-time)**: Careful implementation (no swallowing validation errors)
- **Failsafe (Runtime)**: `SecureDataFrame.validate_compatible_with()` catches this
  - Even if start-time validation bypassed
  - Every data hand-off re-checks clearance
  - BLOCKS access with SecurityValidationError
- **Certification**: Code review verifies error handling correct

**Mitigation**:
- Make `SecurityValidationError` uncatchable at suite level (let it propagate)
- Runtime validation as failsafe (defense in depth)
- Immutable security levels (frozen dataclass)
- Property-based tests with Hypothesis simulate race conditions

**Test Evidence**:
- `test_classified_dataframe_rejects_access_above_clearance` (runtime failsafe)
- `test_PROPERTY_no_configuration_allows_classification_breach` (adversarial scenarios)

---

### T4: Classification Mislabeling (Uplifting Forgotten / Laundering Attack)

**Scenario 1**: Data passes through high-security component but output not uplifted

**Attack Vector 1** (Forgotten Uplifting):
```python
# OFFICIAL data enters SECRET LLM
input_df = SecureDataFrame(data, SecurityLevel.OFFICIAL)
secret_llm = SecretLLM()  # Trained on SECRET data

# Without automatic uplifting:
output_df = secret_llm.transform(input_df)
# output_df.classification still OFFICIAL → WRONG!
# Data has been "tainted" by SECRET model but labeled OFFICIAL

# If output_df sent to OFFICIAL sink:
# Sink thinks "this is OFFICIAL data" but actually contains SECRET influence
# Classification breach through mislabeling
```

**Scenario 2**: Malicious plugin creates "fresh" frame to bypass uplifting (ADR-002-A)

**Attack Vector 2** (Classification Laundering):
```python
class SubtlyMaliciousPlugin(BasePlugin):
    """Plugin that launders SECRET data as OFFICIAL."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # ✅ Truthful - passes start-time validation

    def process(self, input_data: SecureDataFrame) -> SecureDataFrame:
        # input_data.classification == SECRET (legitimate)
        result = input_data.data.copy()
        result["processed"] = True

        # ❌ ATTACK: Create "fresh" frame claiming OFFICIAL classification
        # Bypasses with_uplifted_security_level() enforcement
        return SecureDataFrame(result, SecurityLevel.OFFICIAL)

# Without ADR-002-A: Attack succeeds, SECRET data relabeled as OFFICIAL
# With ADR-002-A: SecurityValidationError raised at construction
```

**Impact**: **HIGH** - Subtle classification breach, hard to detect

**Likelihood**:
- Scenario 1 (Forgotten Uplifting): **MEDIUM** - Developer error
- Scenario 2 (Laundering Attack): **LOW** - Requires malicious plugin, but technically feasible

**Subtlety**: **VERY HIGH** - "Blended data" problem, not obvious; laundering attack looks like legitimate code

**Defense Layers**:
- **Primary (Automatic Uplifting)**: `SecureDataFrame.with_uplifted_security_level()`
  - Every component MUST uplift: `max(input.classification, self.get_security_level())`
  - NOT optional, NOT manual
  - Enforced by inherited BasePlugin behavior
- **Technical Control (ADR-002-A - Constructor Protection)**: **NEW** ✅
  - Only datasources can create SecureDataFrame via `create_from_datasource()`
  - Plugins BLOCKED from direct construction (SecurityValidationError)
  - Frame inspection in `__post_init__` enforces trusted creation path
  - Prevents classification laundering attack (Scenario 2)
  - **IMPACT**: Reduces certification burden - framework blocks attack automatically
  - **Security Hardening**: Fail-closed behavior (see below) - blocks when inspection unavailable
- **Failsafe (Immutability)**: Classification cannot be downgraded
  - `@dataclass(frozen=True)` prevents modification
  - Only `with_uplifted_security_level()` and `with_new_data()` allowed (internal methods)
- **Certification**: Code review verifies datasources label correctly (reduced scope vs. before)

**Constructor Protection Implementation Details** (ADR-002-A):

Frame inspection mechanism (`src/elspeth/core/security/secure_data.py:70-119`):
1. Walks up 5 stack frames to find caller method name
2. Allows: `create_from_datasource()`, `with_uplifted_security_level()`, `with_new_data()`
3. Verifies caller's `self` is SecureDataFrame instance (prevents method name spoofing - CVE-ADR-002-A-001)
4. Blocks all other construction attempts with SecurityValidationError

**Security Hardening - Fail-Closed Behavior** (Updated post-CVE-ADR-002-A-003):
- **Current behavior**: If frame inspection cannot determine caller, constructor BLOCKS creation
- **Change from original**: Original design failed open (allowed creation), now fails closed (blocks)
- **Security improvement**:
  - Aligns with ADR-001 fail-closed principle
  - Eliminates attack vector via C extensions or async contexts
  - No exploitation path even if stack inspection unavailable
- **Trade-off**:
  - May block legitimate use in exotic Python runtimes (PyPy, embedded interpreters)
  - Acceptable for high-security deployments where fail-closed is mandatory
  - Standard CPython 3.12+ supports stack inspection (target platform)
- **Verification**:
  - Caller identity verification (CVE-ADR-002-A-001): Checks `caller_self` is SecureDataFrame
  - Prevents spoofing via external functions with matching names
  - Test coverage validates both fail-closed path and caller verification

**Mitigation**:
- Make uplifting automatic and unavoidable
- Block direct construction to prevent laundering (ADR-002-A)
- Type system enforces: `transform(input: SecureDataFrame) -> SecureDataFrame`
- Property test: `output.classification >= input.classification` ALWAYS

**Test Evidence**:
- `test_INVARIANT_classification_uplifting_automatic`
- `test_INTEGRATION_classification_uplifting_through_secret_llm`
- **`test_invariant_plugin_cannot_create_frame_directly` (ADR-002-A)** ✅
- **`test_invariant_malicious_classification_laundering_blocked` (ADR-002-A)** ✅

---

## Threat Model Boundary

**What This Framework Protects Against**:
- ✅ **Accidental developer errors** (forgot to inherit BasePlugin, misconfigured security levels)
- ✅ **Moderate attacker with code access** (can write plugins, but not bypass CI/signing)
- ✅ **Classification accidents** (developer doesn't realize their code breaches classification)
- ✅ **Configuration mistakes** (wrong security levels in suite configuration)

**What This Framework Does NOT Protect Against**:
- ❌ **Insider threat with admin rights** (can bypass CI, modify build pipeline, sign arbitrary code)
- ❌ **Compromised signing infrastructure** (attacker has code signing keys)
- ❌ **Malicious plugin author with certification approval** (background check passed, but malicious)
- ❌ **Root/admin access to production systems** (can replace entire framework with `def steal_all_data()`)

**Key Principle**: Defense in depth is about **preventing accidents** and **raising the bar for attackers**, NOT about protecting against adversaries who control the entire build/deployment pipeline.

**Honest Assessment**: If an attacker can:
1. Bypass MyPy type checking (`# type: ignore`)
2. Bypass Ruff linting (`# noqa`)
3. Bypass pre-commit hooks (`--no-verify`)
4. Bypass CI checks (admin override)
5. Obtain code signing keys (cryptographic signing)
6. Deploy to production (admin access)

...then they might as well replace the entire codebase with a single function that exfiltrates all data. At this point, **the threat model has failed at a more fundamental level** (insider threat, compromised credentials, organizational security breach). The framework cannot defend against this - it's an operational/personnel security problem, not a technical control problem.

---

## Out of Scope (Certification Verifies)

These threats CANNOT be prevented by framework code (would require solving undecidable problems per Rice's Theorem, or defending against root-level compromise):

### OS1: Malicious Code in Plugins
**Why Out of Scope**: Framework cannot detect malicious intent in code (Halting Problem)
**Certification Handles**: Code review, background checks, approval process

### OS2: Backdoors in Signed Plugins
**Why Out of Scope**: Requires semantic analysis of all code paths (undecidable per Rice's Theorem)
**Certification Handles**: Security review, penetration testing, cryptographic signatures

### OS3: Social Engineering
**Why Out of Scope**: Human factors, not technical control
**Certification Handles**: Training, operational security, audit trails

### OS4: Data Exfiltration via Side Channels
**Why Out of Scope**: Timing attacks, covert channels require operational controls
**Certification Handles**: Network monitoring, air-gapped systems, TEMPEST controls

### OS5: Privilege Escalation Outside Framework
**Why Out of Scope**: OS-level security, not framework responsibility
**Certification Handles**: System hardening, access control, monitoring

### OS6: Insider Threat with Signing Keys + Admin Rights
**Why Out of Scope**: If attacker controls build pipeline, signing infrastructure, AND production deployment, they can replace entire codebase
**Reality Check**: At this threat level, framework security is irrelevant - attacker can just sign `def exfiltrate_all(): ...` and deploy it
**Certification Handles**:
- **Personnel Security**: Background checks, clearance verification, least privilege
- **Separation of Duties**: Different people control signing keys vs. deployment vs. code approval
- **Audit Trails**: All signing events logged, deployments monitored, code changes tracked
- **Infrastructure Security**: HSM-protected signing keys, multi-party control, time-limited credentials
- **Incident Response**: Rapid key revocation, deployment rollback, forensic investigation

**Design Philosophy**: Framework provides **defense in depth** for accidents and moderate threats. It does NOT claim to defend against adversaries with root access and signing keys - that's a **fundamentally different security domain** (personnel/operational security, not technical controls).

---

## Risk Assessment: Implementation Risks

### R1: False Negatives (Security Bypass)

**Risk**: Implementation bug allows classification breach

**Impact**: **CRITICAL** (defeats entire purpose)

**Likelihood**: **MEDIUM** (complex logic, easy to miss edge case)

**Mitigations**:
- ✅ Property-based testing with Hypothesis (1000+ adversarial examples)
- ✅ Integration tests cover all threat scenarios
- ✅ Security reviewer with fresh eyes
- ✅ Start-time + runtime dual validation (defense in depth)
- ✅ Comprehensive test coverage (≥95% on security-critical paths)

**Detection**:
- Property test fails (catches at development)
- Integration test fails (catches at development)
- Security review catches (pre-merge)
- Penetration testing (post-merge, during certification)

**Residual Risk**: **LOW** after mitigations

---

### R2: False Positives (Breaks Valid Use Cases)

**Risk**: Validation too strict, blocks legitimate jobs

**Impact**: **HIGH** (users frustrated, work blocked)

**Likelihood**: **MEDIUM** (security vs usability tradeoff)

**Mitigations**:
- ✅ Run against existing test suites (39 suite_runner tests must still pass)
- ✅ Clear error messages explaining why validation failed
- ✅ Documentation showing valid configuration patterns
- ✅ Test suite includes valid mixed-security scenarios

**Detection**:
- Existing test suite fails (catches at development)
- User reports during trial period
- Documentation review catches unclear policies

**Remediation**:
- If false positive found: Document as test case, adjust validation logic
- Must verify adjustment doesn't introduce false negative
- Re-run full security test suite

**Residual Risk**: **MEDIUM** (some edge cases may emerge in production)

---

### R3: Performance Overhead

**Risk**: Validation adds unacceptable latency

**Impact**: **LOW** (annoyance, not security issue)

**Likelihood**: **LOW** (validation only at job start, not per-record)

**Mitigations**:
- ✅ Validation only at suite start (one-time cost)
- ✅ Runtime validation only at data hand-offs (not per-row)
- ✅ Simple MIN() computation (O(n) where n = number of plugins)
- ✅ No cryptography or network calls in hot path

**Measurement**:
- Benchmark existing suite execution time
- Re-benchmark with security validation
- Target: <1% overhead for typical suite

**Residual Risk**: **NEGLIGIBLE**

---

### R4: Certification Delays

**Risk**: Incomplete documentation delays certification approval

**Impact**: **MEDIUM** (blocks production deployment)

**Likelihood**: **MEDIUM** (government certification rigorous)

**Mitigations**:
- ✅ Certification evidence package documents all threats
- ✅ Each threat maps to specific test
- ✅ Test coverage documented (≥95% target)
- ✅ Clear separation: framework prevents T1/T3/T4, certification prevents T2/OS1-5
- ✅ Rice's Theorem framing (theoretically optimal architecture)

**Prevention**:
- Write evidence package concurrently with implementation (Phase 3)
- Security reviewer previews evidence package before final review
- Include example valid/invalid configurations

**Residual Risk**: **LOW** after mitigations

---

### R5: Race Conditions in Security Level Queries

**Risk**: Plugin security level changes between validation and use

**Impact**: **MEDIUM** (could bypass start-time validation)

**Likelihood**: **LOW** (requires mutable security level + concurrent access)

**Mitigations**:
- ✅ Make security levels immutable (frozen dataclass or const)
- ✅ Runtime validation catches if level changed
- ✅ Property-based tests with concurrent execution
- ✅ Clear documentation: `get_security_level()` must be deterministic for job

**Detection**:
- Runtime validation catches changed level
- Property tests with threading/asyncio
- Code review verifies immutability

**Residual Risk**: **NEGLIGIBLE** with immutability

---

### R6: Error Message Information Disclosure

**Risk**: Error messages leak sensitive information about data classification

**Impact**: **LOW** (metadata leakage, not data leakage)

**Likelihood**: **MEDIUM** (easy to over-disclose in error messages)

**Mitigations**:
- ✅ Error messages describe configuration, not data content
- ✅ No classification values in logs (just "insufficient clearance")
- ✅ Actionable guidance without sensitive details
- ✅ Security reviewer checks error message content

**Example Safe Error**:
```
SecurityValidationError: Datasource requires higher security clearance than
configured sink can handle. Review plugin security requirements.
```

**Example Unsafe Error** (DON'T):
```
SecurityValidationError: Cannot send SECRET data to UNOFFICIAL sink.
Input data classified SECRET contains: [REDACTED DATA]
```

**Residual Risk**: **LOW** with careful message design

---

## Implementation Risk Score

| Risk | Impact | Likelihood | Mitigation | Residual |
|------|--------|------------|------------|----------|
| R1: False Negatives | CRITICAL | MEDIUM | Strong | LOW |
| R2: False Positives | HIGH | MEDIUM | Moderate | MEDIUM |
| R3: Performance | LOW | LOW | Strong | NEGLIGIBLE |
| R4: Certification Delays | MEDIUM | MEDIUM | Strong | LOW |
| R5: Race Conditions | MEDIUM | LOW | Strong | NEGLIGIBLE |
| R6: Information Disclosure | LOW | MEDIUM | Moderate | LOW |

**Overall Risk**: **ACCEPTABLE** with planned mitigations

**Highest Residual Risk**: R2 (False Positives) - Some valid edge cases may be blocked

**Mitigation Plan for R2**:
- Phase 2: Run all existing tests, ensure they pass
- Phase 3: Document valid configuration patterns
- Post-merge: Trial period with early adopter users
- Establish process for false positive reports

---

## Defense Layer Mapping

| Threat | Start-Time Validation | Runtime Failsafe | Certification |
|--------|----------------------|------------------|---------------|
| T1: Classification Breach | ✅ PRIMARY | ✅ BACKUP | ✅ VERIFY |
| T2: Security Downgrade | ❌ Cannot Prevent | ❌ Cannot Prevent | ✅ MUST CATCH |
| T3: Runtime Bypass | ✅ PRIMARY | ✅ BACKUP | ✅ VERIFY |
| T4: Uplifting Forgotten | ✅ AUTOMATIC | ✅ IMMUTABLE | ✅ VERIFY |

**Coverage**: All threats have at least one defense layer, most have two+ layers

---

## Testing Strategy

### Security Invariants (5+ tests)
Property-based tests defining what MUST be true:
- Minimum envelope never exceeds weakest plugin
- High-security plugins reject low envelopes
- Classification uplifting automatic and unavoidable
- Output classification ≥ input classification
- No configuration allows classification breach

### Integration Tests (5+ tests)
End-to-end scenarios demonstrating threat prevention:
- SECRET datasource + UNOFFICIAL sink → BLOCKED
- Mixed security plugins → operate at minimum
- OFFICIAL data through SECRET LLM → SECRET output
- Valid same-level configuration → ALLOWED
- Multiple sinks at different levels → minimum respected

### Property-Based Tests (5+ tests)
Adversarial testing with Hypothesis (1000+ examples each):
- Random plugin configurations → no breach possible
- Concurrent access patterns → no race conditions
- Edge cases (empty plugins, all same level, etc.)

**Total Test Target**: 15+ tests covering all threats and risks

---

## Success Criteria

**Threat Coverage**: All 4 threats have test evidence
**Risk Mitigation**: All 6 risks have documented mitigations
**Test Coverage**: ≥95% on security-critical code paths
**False Negatives**: Zero bypasses found in property tests (1000+ examples)
**False Positives**: All 39 existing suite_runner tests still pass

---

## Emergency Procedures

**If false negative discovered**:
1. STOP all work immediately
2. Document the bypass scenario
3. Write failing test demonstrating bypass
4. Assess if design flaw (needs ADR update) or implementation bug
5. DO NOT MERGE until fixed and re-tested

**If false positive blocks valid use case**:
1. Document the blocked scenario
2. Get security reviewer to confirm it's actually valid (not a disguised threat)
3. Write test case for the valid scenario
4. Adjust validation logic to permit
5. Re-run FULL security test suite (ensure fix didn't introduce bypass)

**If timeline exceeds estimate by >50%**:
1. Review what's taking longer (usually integration tests)
2. Consider breaking into smaller PRs (each must be security-complete)
3. DON'T cut corners on testing or documentation
4. Get checkpoint review from security reviewer

---

## Sign-Off

**Phase 0 Complete**: _______________
**Date**: _______________

**Security Reviewer Acknowledgment**:
- [ ] Threat model covers all relevant attack scenarios
- [ ] Out-of-scope threats appropriately delegated to certification
- [ ] Risk assessment realistic and complete
- [ ] Mitigations adequate for identified risks
- [ ] Testing strategy comprehensive

**Reviewer**: _______________
**Date**: _______________
