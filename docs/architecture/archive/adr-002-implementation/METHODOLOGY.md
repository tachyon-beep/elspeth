# ADR-002 Security Implementation Methodology

**Adapted from:** `docs/refactoring/METHODOLOGY.md` (PR #10, PR #11 - 100% success rate)
**Target:** Suite-level security enforcement (ADR-002)
**Estimated Effort:** 4-6 hours over 1-2 days
**Risk Level:** HIGH (security control - must be correct)

---

## How This Differs from Refactoring Methodology

| Aspect | Refactoring (PR #11) | Security Implementation (ADR-002) |
|--------|----------------------|-----------------------------------|
| **Starting Point** | Existing complex code | New security controls |
| **Test Strategy** | Characterization tests (capture behavior) | Property tests (define invariants) |
| **Success Criteria** | Zero behavioral changes | Security properties satisfied |
| **Primary Risk** | Breaking existing functionality | Security bypass or false positives |
| **Documentation** | Capture implicit knowledge | ADR-002 is explicit specification |

---

## Pre-Flight Check (Before Starting)

Security implementation has stricter prerequisites than refactoring:

- [ ] ADR-002 documentation complete and reviewed
- [ ] Threat model understood (what attacks we're preventing)
- [ ] Existing plugin-level security passing (9 tests)
- [ ] 8-12 hours available over 1-2 days (security can't be rushed)
- [ ] Security reviewer available for final approval
- [ ] CI/CD, MyPy, linting infrastructure working
- [ ] Branch created: `feature/adr-002-security-enforcement`

**CRITICAL**: If interrupted mid-phase, DO NOT merge partial security controls. Security is all-or-nothing.

---

## Phase 0: Security Properties & Threat Model (2-3 hours)

### Step 1: Define Security Invariants (1 hour)

Write the security properties FIRST as executable tests, before any implementation:

```python
# tests/test_adr002_security_invariants.py

from hypothesis import given, strategies as st
import pytest

class TestMinimumClearanceEnvelope:
    """Security invariants for ADR-002 minimum clearance envelope model."""

    def test_INVARIANT_orchestrator_operates_at_minimum_level(self):
        """INVARIANT: Orchestrator MUST operate at MIN(all plugin security levels).

        THREAT: If orchestrator operates above minimum, low-security component
                could receive data it can't handle → classification breach.
        """
        # Given: Plugins with mixed security levels
        # When: Orchestrator computes operating level
        # Then: Operating level = MIN(plugin levels)

    def test_INVARIANT_high_security_plugins_reject_low_envelope(self):
        """INVARIANT: Plugins MUST refuse to operate below their security level.

        THREAT: If SECRET datasource accepts UNOFFICIAL envelope → data leakage.
        """
        # Given: Plugin requires SECRET, orchestrator at UNOFFICIAL
        # When: Start-time validation runs
        # Then: Job MUST fail with clear security error

    def test_INVARIANT_classification_uplifting_automatic(self):
        """INVARIANT: Data passing through high-security component MUST inherit
                     higher classification (automatic tainting).

        THREAT: If uplifting is manual/optional → classification mislabeling.
        """
        # Given: OFFICIAL data passes through SECRET LLM
        # When: LLM processes data
        # Then: Output MUST be classified SECRET (non-negotiable)
```

**Property-Based Testing**: Use Hypothesis to generate adversarial scenarios:
```python
@given(
    plugin_levels=st.lists(
        st.sampled_from([SecurityLevel.UNOFFICIAL, SecurityLevel.OFFICIAL, SecurityLevel.SECRET]),
        min_size=1,
        max_size=10
    )
)
def test_PROPERTY_minimum_envelope_never_exceeds_weakest_link(plugin_levels):
    """PROPERTY: Operating level ≤ min(plugin levels) under ALL configurations.

    This property MUST hold even with adversarial plugin combinations.
    """
    operating_level = compute_minimum_clearance_envelope(plugin_levels)
    assert operating_level <= min(plugin_levels)
```

### Step 2: Threat Model Documentation (30 min)

Create `THREAT_MODEL_ADR002.md` documenting:

1. **Threats We're Preventing**:
   - T1: Classification breach (SECRET data → UNOFFICIAL sink)
   - T2: Security downgrade attack (malicious plugin reports lower level)
   - T3: Runtime bypass (plugin validates at start but accepts wrong data later)
   - T4: Classification mislabeling (manual uplifting forgotten)

2. **Out of Scope** (Certification verifies these):
   - Malicious code in plugins (requires code review)
   - Backdoors in signed plugins (requires audit trail)
   - Social engineering attacks (requires operational security)

3. **Defense Layers**:
   - Layer 1: Start-time validation (PRIMARY - job fails to start)
   - Layer 2: Runtime validation (FAILSAFE - data access blocks)
   - Layer 3: Certification (human verification of Layer 1 & 2 correctness)

### Step 3: Risk Assessment (30 min)

Identify implementation risks and mitigations:

| Risk | Impact | Mitigation |
|------|--------|------------|
| False negatives (bypass) | CRITICAL | Property-based tests, security review |
| False positives (breaks valid jobs) | HIGH | Characterization tests on existing suites |
| Performance overhead | LOW | Validation only at start, not per-record |
| Certification delays | MEDIUM | Clear documentation, test coverage |

**Commit Phase 0**: `git commit -m "Docs: ADR-002 security invariants and threat model"`

---

## Phase 1: Core Security Primitives (1-2 hours)

### Step 1: SecureDataFrame (30 min)

**Test First** (Red):
```python
def test_classified_dataframe_immutable_classification():
    """Classification metadata MUST be immutable after creation."""
    df = SecureDataFrame(pd.DataFrame(), SecurityLevel.SECRET)

    with pytest.raises(AttributeError):
        df.classification = SecurityLevel.UNOFFICIAL  # MUST fail
```

**Implementation** (Green):
```python
@dataclass(frozen=True)  # Immutability guaranteed by dataclass
class SecureDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel

    def with_uplifted_security_level(self, new_level: SecurityLevel) -> "SecureDataFrame":
        """Return new instance with uplifted classification (immutable update)."""
        return SecureDataFrame(self.data, max(self.classification, new_level))
```

### Step 2: Minimum Clearance Envelope Computation (30 min)

**Test First** (Red):
```python
def test_compute_minimum_clearance_envelope_basic():
    """Operating level = MIN(plugin levels)."""
    plugins = [
        MockPlugin(SecurityLevel.SECRET),
        MockPlugin(SecurityLevel.OFFICIAL),
        MockPlugin(SecurityLevel.SECRET),
    ]

    operating_level = compute_minimum_clearance_envelope(plugins)
    assert operating_level == SecurityLevel.OFFICIAL  # Weakest link
```

**Implementation** (Green):
```python
def compute_minimum_clearance_envelope(
    plugins: list[BasePlugin]
) -> SecurityLevel:
    """Compute minimum security level across all plugins.

    Returns minimum because orchestrator operates at LOWEST common level
    that ALL components can handle.
    """
    if not plugins:
        return SecurityLevel.UNOFFICIAL  # Default to lowest

    return min(plugin.get_security_level() for plugin in plugins)
```

### Step 3: Plugin Validation (30 min)

**Test First** (Red):
```python
def test_validate_plugin_accepts_envelope_rejects_too_low():
    """Plugin MUST reject operating level below its security requirement."""
    plugin = SecretDatasource()  # Requires SECRET
    envelope = SecurityLevel.UNOFFICIAL

    with pytest.raises(SecurityValidationError, match="requires SECRET.*UNOFFICIAL"):
        plugin.validate_can_operate_at_level(envelope)
```

**Implementation** (Green):
```python
class BasePlugin(ABC):
    """Base class all plugins inherit from."""

    @abstractmethod
    def get_security_level(self) -> SecurityLevel:
        """Return security level this plugin requires for THIS job."""
        pass

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate plugin can operate at the orchestrator's envelope level.

        Raises:
            SecurityValidationError: If operating_level < self.get_security_level()
        """
        required = self.get_security_level()
        if operating_level < required:
            raise SecurityValidationError(
                f"{self.__class__.__name__} requires {required.name}, "
                f"but orchestrator operating at {operating_level.name}"
            )
```

**Commit Phase 1**: `git commit -m "Feat: Core ADR-002 security primitives (SecureDataFrame, envelope)"`

---

## Phase 2: Suite Runner Integration (1-2 hours)

### Step 1: Add Security Context to SuiteExecutionContext (30 min)

**Test First** (Red):
```python
def test_suite_execution_context_includes_security_envelope():
    """Suite context MUST track operating security level."""
    plugins = [MockPlugin(SecurityLevel.OFFICIAL), MockPlugin(SecurityLevel.SECRET)]

    ctx = SuiteExecutionContext.create(suite, defaults, plugins)

    assert ctx.operating_security_level == SecurityLevel.OFFICIAL  # MIN()
```

**Implementation** (Green):
```python
@dataclass
class SuiteExecutionContext:
    # ... existing fields ...
    operating_security_level: SecurityLevel  # NEW

    @classmethod
    def create(
        cls,
        suite: ExperimentSuite,
        defaults: dict[str, Any],
        all_plugins: list[BasePlugin],  # NEW parameter
    ) -> "SuiteExecutionContext":
        # Compute operating level from all plugins
        operating_level = compute_minimum_clearance_envelope(all_plugins)

        return cls(
            # ... existing initialization ...
            operating_security_level=operating_level,
        )
```

### Step 2: Start-Time Validation in suite_runner.py (30 min)

**Test First** (Red):
```python
def test_suite_runner_validates_all_plugins_at_start():
    """Suite runner MUST validate ALL plugins before data retrieval.

    THREAT: If validation skipped, SECRET datasource could leak to UNOFFICIAL sink.
    """
    suite = ExperimentSuite(...)
    runner = ExperimentSuiteRunner(
        suite=suite,
        datasource=SecretDatasource(),  # Requires SECRET
        sinks=[UnofficialSink()],  # Only handles UNOFFICIAL
    )

    with pytest.raises(SecurityValidationError, match="datasource requires SECRET"):
        runner.run(...)  # MUST fail at START, not during execution
```

**Implementation** (Green):
```python
class ExperimentSuiteRunner:
    def run(self, ...):
        # Collect ALL plugins
        all_plugins = [
            *self._get_all_datasources(),
            *self._get_all_llm_clients(),
            *self._get_all_sinks(),
            *self._get_all_middleware(),
        ]

        # Create context (computes operating level)
        ctx = SuiteExecutionContext.create(self.suite, defaults, all_plugins)

        # CRITICAL: Validate ALL plugins BEFORE data retrieval
        self._validate_security_envelope(all_plugins, ctx.operating_security_level)

        # Now safe to proceed with experiment execution
        # ... existing execution logic ...

    def _validate_security_envelope(
        self,
        plugins: list[BasePlugin],
        operating_level: SecurityLevel,
    ) -> None:
        """Validate all plugins can operate at the computed security level.

        This is the PRIMARY security control - job fails to start if any
        plugin requires higher security than the minimum envelope.
        """
        for plugin in plugins:
            plugin.validate_can_operate_at_level(operating_level)
            # Raises SecurityValidationError if validation fails
```

### Step 3: Runtime Failsafe in Data Access (30 min)

**Test First** (Red):
```python
def test_classified_dataframe_rejects_access_above_clearance():
    """SecureDataFrame MUST refuse to expose data to low-clearance component.

    FAILSAFE: Even if start-time validation bypassed, runtime check prevents leakage.
    """
    secret_df = SecureDataFrame(data, SecurityLevel.SECRET)
    unofficial_sink = UnofficialSink()  # Reports UNOFFICIAL level

    with pytest.raises(SecurityValidationError, match="SECRET data.*UNOFFICIAL sink"):
        unofficial_sink.write(secret_df)  # MUST block at data access
```

**Implementation** (Green):
```python
class SecureDataFrame:
    def validate_compatible_with(self, accessor: BasePlugin) -> None:
        """Validate accessor has sufficient clearance for this data.

        FAILSAFE: Defense-in-depth check if start-time validation bypassed.
        """
        accessor_level = accessor.get_security_level()
        if accessor_level < self.classification:
            raise SecurityValidationError(
                f"Cannot provide {self.classification.name} data to "
                f"{accessor.__class__.__name__} (clearance: {accessor_level.name})"
            )
```

**Commit Phase 2**: `git commit -m "Feat: ADR-002 suite-level security enforcement (start-time + runtime)"`

---

## Phase 3: Integration Tests & Certification Evidence (1-2 hours)

### Step 1: End-to-End Security Scenarios (1 hour)

Write integration tests that demonstrate security controls working across full stack:

```python
# tests/test_adr002_integration.py

def test_INTEGRATION_secret_datasource_rejects_unofficial_sink():
    """INTEGRATION: Job with SECRET datasource + UNOFFICIAL sink MUST fail at start.

    CERTIFICATION EVIDENCE: Demonstrates classification breach prevention.
    """
    suite = ExperimentSuite(...)
    runner = ExperimentSuiteRunner(
        suite=suite,
        datasource=SecretDatasource(),
        sinks=[UnofficialSink()],
    )

    with pytest.raises(SecurityValidationError) as exc_info:
        runner.run(...)

    # Verify error message is actionable
    assert "datasource requires SECRET" in str(exc_info.value)
    assert "envelope operating at UNOFFICIAL" in str(exc_info.value)


def test_INTEGRATION_mixed_security_suite_operates_at_minimum():
    """INTEGRATION: Suite with mixed plugins operates at minimum common level.

    CERTIFICATION EVIDENCE: Demonstrates minimum clearance envelope model.
    """
    suite = ExperimentSuite(...)
    runner = ExperimentSuiteRunner(
        suite=suite,
        datasource=OfficialDatasource(),  # Requires OFFICIAL
        llm=SecretLLM(),  # Requires SECRET
        sinks=[UnofficialSink(), OfficialSink()],  # Mixed
    )

    # Envelope = MIN(OFFICIAL, SECRET, UNOFFICIAL, OFFICIAL) = UNOFFICIAL
    with pytest.raises(SecurityValidationError) as exc_info:
        runner.run(...)

    # Both datasource and LLM should reject UNOFFICIAL envelope
    assert "requires OFFICIAL" in str(exc_info.value) or \
           "requires SECRET" in str(exc_info.value)


def test_INTEGRATION_classification_uplifting_through_secret_llm():
    """INTEGRATION: OFFICIAL data → SECRET LLM → SECRET output (automatic).

    CERTIFICATION EVIDENCE: Demonstrates classification uplifting works.
    """
    suite = ExperimentSuite(...)
    runner = ExperimentSuiteRunner(
        suite=suite,
        datasource=OfficialDatasource(),  # Provides OFFICIAL data
        llm=SecretLLM(),  # Trained on SECRET data
        sinks=[SecretSink()],  # Can handle SECRET
    )

    result = runner.run(...)

    # Output classification should be uplifted to SECRET
    assert result.output_classification == SecurityLevel.SECRET
```

### Step 2: Property-Based Adversarial Testing (30 min)

Use Hypothesis to generate adversarial configurations:

```python
@given(
    plugin_configs=st.lists(
        st.tuples(
            st.sampled_from(["datasource", "llm", "sink"]),
            st.sampled_from(list(SecurityLevel))
        ),
        min_size=2,
        max_size=8
    )
)
def test_PROPERTY_no_configuration_allows_classification_breach(plugin_configs):
    """PROPERTY: Under ALL possible plugin configurations, no classification breach.

    CERTIFICATION EVIDENCE: Exhaustive testing of security control.
    """
    # Build suite from adversarial configuration
    suite = build_suite_from_config(plugin_configs)

    # Either job succeeds (all at same level) OR fails at start (security block)
    try:
        result = suite.run(...)
        # If succeeded, verify output classification ≥ input classification
        assert result.output_classification >= result.input_classification
    except SecurityValidationError:
        # Job correctly blocked - this is success
        pass
```

**Commit Phase 3**: `git commit -m "Test: ADR-002 integration tests and certification evidence"`

---

## Phase 4: Documentation & Certification (1 hour)

### Step 1: Update ADR-002 Implementation Status (15 min)

Update `README-ADR002-IMPLEMENTATION.md`:
- Mark suite-level enforcement as ✅ DONE
- Document test coverage (number of tests, scenarios covered)
- Link to key commits

### Step 2: Security Control Evidence Package (30 min)

Create `ADR002_CERTIFICATION_EVIDENCE.md`:
```markdown
# ADR-002 Certification Evidence Package

## Implementation Complete

**Date**: 2025-10-25
**Commits**: [list commit SHAs]
**Tests**: 15 security tests (5 invariants + 5 integration + 5 property-based)
**Coverage**: 100% of security-critical code paths

## Threat Coverage

| Threat | Control | Evidence |
|--------|---------|----------|
| T1: Classification breach | Start-time validation | `test_INTEGRATION_secret_datasource_rejects_unofficial_sink` |
| T2: Security downgrade | Minimum envelope computation | `test_PROPERTY_minimum_envelope_never_exceeds_weakest_link` |
| T3: Runtime bypass | SecureDataFrame failsafe | `test_classified_dataframe_rejects_access_above_clearance` |
| T4: Classification mislabeling | Automatic uplifting | `test_INTEGRATION_classification_uplifting_through_secret_llm` |

## Test Results

```
tests/test_adr002_security_invariants.py ... 5 passed
tests/test_adr002_integration.py ........... 5 passed
tests/test_adr002_properties.py ............ 5 passed (1000 Hypothesis examples each)
============================== 15 passed ==============================
```

## Security Reviewer Sign-Off

- [ ] Code review completed
- [ ] All tests passing
- [ ] Threat model satisfied
- [ ] Documentation complete

**Reviewer**: _______________
**Date**: _______________
```

### Step 3: Update Main Documentation (15 min)

Update `docs/security/adr-002-orchestrator-security-model.md`:
- Add "Implementation Status: ✅ Complete" header
- Link to test files as examples
- Document any deviations from original spec

**Commit Phase 4**: `git commit -m "Docs: ADR-002 implementation complete with certification evidence"`

---

## Quality Gates (Must Pass Before Merge)

Unlike refactoring where we check for behavioral changes, security implementation has stricter gates:

### Automated Gates
- [ ] All 15+ security tests passing
- [ ] MyPy clean (type safety critical for security)
- [ ] Ruff clean (code quality)
- [ ] Coverage ≥ 95% on security-critical paths
- [ ] Property-based tests passed 1000+ examples each
- [ ] No new warnings in CI/CD

### Manual Gates
- [ ] Security reviewer approved code
- [ ] Threat model verified complete
- [ ] Documentation reviewed by peer
- [ ] Integration tests cover all threat scenarios
- [ ] Error messages are actionable (help users fix configuration)

### Certification Gates
- [ ] Certification evidence package complete
- [ ] All ADR-002 requirements satisfied
- [ ] Test coverage documented
- [ ] No known security gaps

---

## Key Differences from Refactoring

| Decision Point | Refactoring Approach | Security Implementation Approach |
|----------------|---------------------|----------------------------------|
| **When to commit** | After each small change | After each complete security control |
| **Test strategy** | Characterization (capture existing) | Property-based (define invariants) |
| **Failure mode** | Tests break (rollback) | Security gap (don't merge) |
| **Documentation** | Update after implementation | Write before implementation (threat model) |
| **Review process** | Peer review sufficient | Security review required |
| **Merge criteria** | All tests green + coverage | Security gates + certification evidence |

---

## Success Criteria

**Technical**:
- ✅ All security invariants satisfied (property tests passing)
- ✅ All threat scenarios covered (integration tests)
- ✅ Zero false negatives (no bypasses found)
- ✅ Acceptable false positives (valid jobs still work)

**Process**:
- ✅ Certification evidence package complete
- ✅ Security reviewer approved
- ✅ Documentation updated
- ✅ ADR-002 requirements met

**Outcome**:
- ✅ System prevents classification breaches
- ✅ Clear error messages guide users
- ✅ Certification can proceed
- ✅ Audit trail established

---

## Estimated Timeline

| Phase | Time | Checkpoint |
|-------|------|------------|
| Phase 0: Properties & Threat Model | 2-3 hours | Security invariants defined |
| Phase 1: Core Primitives | 1-2 hours | SecureDataFrame, envelope working |
| Phase 2: Integration | 1-2 hours | Suite runner enforces security |
| Phase 3: Certification Tests | 1-2 hours | Evidence package complete |
| Phase 4: Documentation | 1 hour | Ready for security review |
| **TOTAL** | **6-10 hours** | **Certification blocker removed** |

---

## Emergency Procedures

**If security gap discovered mid-implementation**:
1. STOP implementation immediately
2. Document the gap in threat model
3. Write failing test demonstrating gap
4. Assess if gap is in design (need ADR update) or implementation
5. DO NOT merge partial security controls

**If false positives block valid use cases**:
1. Document the use case in tests
2. Verify it's not actually a security issue (get security review)
3. Adjust validation logic to permit valid case
4. Re-run full security test suite

**If timeline exceeds estimate**:
1. Review what's taking longer (usually integration tests)
2. Consider breaking into smaller PRs (but each PR must be security-complete)
3. Don't cut corners on testing or documentation

---

**Remember**: Security implementation is like surgery - sterile technique matters more than speed.
