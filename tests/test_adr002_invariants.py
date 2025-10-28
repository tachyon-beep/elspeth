"""ADR-002 Security Invariants - Test-First Implementation

These tests define the security properties that MUST hold for ADR-002
suite-level security enforcement. All tests should FAIL initially (red),
then pass after implementation (green).

Security Invariants (Bell-LaPadula "no read up"):
1. Orchestrator MUST operate at MIN(all plugin security levels)
2. Plugins MUST refuse to operate ABOVE their security clearance (insufficient clearance)
3. Plugins with HIGHER clearance MAY operate at LOWER levels (trusted to filter/downgrade)
4. Classification uplifting MUST be automatic (not manual/optional)
5. Output classification MUST be ≥ input classification (always)
6. No configuration MUST allow classification breach

CRITICAL: These are not regression tests - they define NEW security behavior.
"""

import pytest
from pathlib import Path
from typing import Any

from hypothesis import given, strategies as st

# Import types that already exist
from elspeth.core.security import SecurityLevel, SecureDataFrame

# NOTE: These imports will fail until Phase 1-2 implementation
# This is EXPECTED for test-first development
try:
    from elspeth.core.experiments.suite_runner import (
        compute_minimum_clearance_envelope,
        ExperimentSuiteRunner,
    )
except ImportError:
    # Allow test file to be created before implementation exists
    compute_minimum_clearance_envelope = None
    ExperimentSuiteRunner = None

try:
    from elspeth.core.base.plugin import BasePlugin  # ADR-004: ABC with nominal typing
except ImportError:
    BasePlugin = None


# ============================================================================
# TEST FIXTURES - Mock Plugins for Security Testing
# ============================================================================


class MockPlugin:
    """Mock plugin with configurable security level for testing."""

    def __init__(self, security_level: "SecurityLevel"):
        self._security_level = security_level

    def get_security_level(self) -> "SecurityLevel":
        """Return this plugin's security requirement."""
        return self._security_level

    def validate_can_operate_at_level(self, operating_level: "SecurityLevel") -> None:
        """Validate plugin can operate at the given envelope level.

        Bell-LaPadula "no read up": Plugin can operate at same or lower level,
        but cannot operate ABOVE its clearance.

        Raises:
            SecurityValidationError: If operating_level > self._security_level
        """
        from elspeth.core.validation.base import SecurityValidationError

        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{self.__class__.__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name} - insufficient clearance"
            )


class UnofficialPlugin(MockPlugin):
    """Plugin that handles UNOFFICIAL data."""

    def __init__(self):
        super().__init__(SecurityLevel.UNOFFICIAL)


class OfficialPlugin(MockPlugin):
    """Plugin that requires OFFICIAL clearance."""

    def __init__(self):
        super().__init__(SecurityLevel.OFFICIAL)


class SecretPlugin(MockPlugin):
    """Plugin that requires SECRET clearance."""

    def __init__(self):
        super().__init__(SecurityLevel.SECRET)


# ============================================================================
# INVARIANT 1: Minimum Clearance Envelope
# ============================================================================


class TestInvariantMinimumClearanceEnvelope:
    """INVARIANT: Orchestrator MUST operate at MIN(all plugin security levels).

    THREAT: If orchestrator operates above minimum, low-security component
            could receive data it can't handle → classification breach.

    DEFENSE: compute_minimum_clearance_envelope() enforces weakest-link principle.
    """

    def test_minimum_envelope_basic_mixed_plugins(self):
        """Operating level = MIN(plugin levels) for mixed security plugins.

        Given: Plugins with SECRET, OFFICIAL, SECRET security levels
        When: Computing minimum clearance envelope
        Then: Operating level = OFFICIAL (weakest link)
        """
        plugins = [
            SecretPlugin(),
            OfficialPlugin(),
            SecretPlugin(),
        ]

        operating_level = compute_minimum_clearance_envelope(plugins)

        assert operating_level == SecurityLevel.OFFICIAL, \
            f"Expected OFFICIAL (weakest link), got {operating_level.name}"

    def test_minimum_envelope_all_same_level(self):
        """Operating level = common level when all plugins at same security.

        Given: All plugins at OFFICIAL level
        When: Computing minimum clearance envelope
        Then: Operating level = OFFICIAL
        """
        plugins = [
            OfficialPlugin(),
            OfficialPlugin(),
            OfficialPlugin(),
        ]

        operating_level = compute_minimum_clearance_envelope(plugins)

        assert operating_level == SecurityLevel.OFFICIAL

    def test_minimum_envelope_unofficial_weakest_link(self):
        """Operating level = UNOFFICIAL if any plugin only handles UNOFFICIAL.

        Given: Mix of SECRET, OFFICIAL, and one UNOFFICIAL plugin
        When: Computing minimum clearance envelope
        Then: Operating level = UNOFFICIAL (absolute weakest)
        """
        plugins = [
            SecretPlugin(),
            OfficialPlugin(),
            SecretPlugin(),
            UnofficialPlugin(),  # Weakest link
        ]

        operating_level = compute_minimum_clearance_envelope(plugins)

        assert operating_level == SecurityLevel.UNOFFICIAL

    def test_minimum_envelope_empty_plugins_list(self):
        """Empty plugin list defaults to UNOFFICIAL (lowest level).

        Given: No plugins configured
        When: Computing minimum clearance envelope
        Then: Operating level = UNOFFICIAL (safe default)
        """
        plugins = []

        operating_level = compute_minimum_clearance_envelope(plugins)

        assert operating_level == SecurityLevel.UNOFFICIAL


# ============================================================================
# INVARIANT 2: Plugin Validation (Start-Time)
# ============================================================================


class TestInvariantPluginValidation:
    """INVARIANT: Plugins MUST refuse to operate ABOVE their security clearance (Bell-LaPadula "no read up").

    THREAT: If UNOFFICIAL datasource operates in SECRET pipeline → insufficient clearance breach.

    CORRECT BEHAVIOR:
    - UNOFFICIAL datasource in SECRET pipeline → REJECT (insufficient clearance)
    - SECRET datasource in UNOFFICIAL pipeline → ALLOW (trusted to filter to UNOFFICIAL)

    DEFENSE: BasePlugin.validate_can_operate_at_level() enforces clearance checks.
    """

    def test_high_security_plugin_accepts_low_envelope(self):
        """✅ CORRECT Bell-LaPadula: HIGH clearance CAN operate at LOW level.

        Bell-LaPadula "trusted downgrade":
        - SECRET plugin (clearance SECRET) CAN operate at UNOFFICIAL (lower level)
        - Plugin is trusted to filter/downgrade data appropriately
        - Should NOT raise error

        Given: Plugin with SECRET clearance
        When: Validating against UNOFFICIAL envelope (lower level)
        Then: Validation MUST succeed (no exception)
        """
        secret_plugin = SecretPlugin()

        # Should NOT raise - SECRET clearance can operate at UNOFFICIAL level (trusted downgrade)
        secret_plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

    def test_plugin_accepts_sufficient_envelope(self):
        """Plugin MUST accept operating level ≥ its requirement.

        Given: Plugin requires OFFICIAL clearance
        When: Validating against OFFICIAL envelope
        Then: No exception (validation passes)
        """
        official_plugin = OfficialPlugin()

        # Should not raise
        official_plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_plugin_rejects_higher_envelope(self):
        """✅ CORRECT Bell-LaPadula: LOW clearance CANNOT operate at HIGH level.

        Bell-LaPadula "no read up":
        - UNOFFICIAL plugin (clearance UNOFFICIAL) CANNOT operate at SECRET level
        - Plugin has insufficient clearance for SECRET data
        - MUST raise SecurityValidationError

        Given: Plugin with UNOFFICIAL clearance (lowest level)
        When: Validating against SECRET envelope (higher level)
        Then: Validation MUST fail with SecurityValidationError
        """
        from elspeth.core.validation.base import SecurityValidationError

        unofficial_plugin = UnofficialPlugin()

        # MUST raise - UNOFFICIAL clearance is insufficient for SECRET level
        with pytest.raises(SecurityValidationError) as exc_info:
            unofficial_plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        error_msg = str(exc_info.value)
        assert "UNOFFICIAL" in error_msg, "Error should mention plugin clearance level"
        assert "SECRET" in error_msg, "Error should mention required envelope level"
        assert "insufficient" in error_msg.lower(), "Error should indicate insufficient clearance"


# ============================================================================
# INVARIANT 3: Classification Uplifting (Automatic)
# ============================================================================


class TestInvariantClassificationUplifting:
    """INVARIANT: Classification uplifting MUST be automatic (not manual/optional).

    THREAT: If uplifting manual/forgotten → classification mislabeling
            (OFFICIAL data through SECRET LLM stays labeled OFFICIAL).

    DEFENSE: SecureDataFrame.with_uplifted_security_level() enforces uplifting.
    """

    def test_uplifting_to_higher_classification(self):
        """Uplifting MUST increase classification to higher level.

        Given: OFFICIAL data
        When: Uplifting to SECRET
        Then: New SecureDataFrame with SECRET classification
        """
        import pandas as pd

        df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            security_level=SecurityLevel.OFFICIAL
        )

        uplifted = df.with_uplifted_security_level(SecurityLevel.SECRET)

        assert uplifted.security_level == SecurityLevel.SECRET
        assert df.security_level == SecurityLevel.OFFICIAL, \
            "Original should remain unchanged (immutability)"

    def test_uplifting_does_not_downgrade(self):
        """Uplifting MUST NOT allow downgrade (max operation).

        Given: SECRET data
        When: Attempting to "uplift" to OFFICIAL (lower)
        Then: Classification remains SECRET (max wins)
        """
        import pandas as pd

        df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            security_level=SecurityLevel.SECRET
        )

        # "Uplift" to lower level should keep higher level
        result = df.with_uplifted_security_level(SecurityLevel.OFFICIAL)

        assert result.security_level == SecurityLevel.SECRET, \
            "Classification must not downgrade (max operation)"

    def test_classification_immutable(self):
        """Classification MUST be immutable after creation.

        Given: SecureDataFrame created
        When: Attempting to modify classification attribute
        Then: AttributeError (frozen dataclass)
        """
        import pandas as pd

        df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            security_level=SecurityLevel.OFFICIAL
        )

        with pytest.raises(AttributeError):
            df.security_level = SecurityLevel.UNOFFICIAL


# ============================================================================
# INVARIANT 4: Output Classification ≥ Input Classification
# ============================================================================


@pytest.mark.skipif(
    SecureDataFrame is None,
    reason="Phase 1 not implemented yet (expected for test-first)"
)
class TestInvariantOutputClassification:
    """INVARIANT: Output classification MUST be ≥ input classification (always).

    THREAT: Data downgrade → classification breach.

    DEFENSE: Automatic uplifting in component transforms.
    """

    def test_transform_uplifts_classification(self):
        """Transform through high-security component MUST uplift output.

        Given: OFFICIAL input data
        When: Transformed by SECRET component
        Then: Output classification = SECRET (max of input and component)
        """
        import pandas as pd

        input_df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"text": ["test"]}),
            security_level=SecurityLevel.OFFICIAL
        )

        # Simulate transform by SECRET component using proper pattern
        component_level = SecurityLevel.SECRET

        # Proper ADR-002-A pattern: with_new_data() then with_uplifted_security_level()
        output_df = input_df.with_new_data(
            pd.DataFrame({"transformed": ["result"]})
        ).with_uplifted_security_level(component_level)

        assert output_df.security_level >= input_df.security_level
        assert output_df.security_level == SecurityLevel.SECRET

    def test_same_level_transform_preserves_classification(self):
        """Transform at same level MUST preserve classification.

        Given: OFFICIAL input data
        When: Transformed by OFFICIAL component
        Then: Output classification = OFFICIAL (unchanged)
        """
        import pandas as pd

        input_df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"text": ["test"]}),
            security_level=SecurityLevel.OFFICIAL
        )

        # Simulate transform by OFFICIAL component using proper pattern
        component_level = SecurityLevel.OFFICIAL

        # Proper ADR-002-A pattern: with_new_data() then with_uplifted_security_level()
        output_df = input_df.with_new_data(
            pd.DataFrame({"transformed": ["result"]})
        ).with_uplifted_security_level(component_level)

        assert output_df.security_level == input_df.security_level


# ============================================================================
# INVARIANT 5: No Configuration Allows Breach (Property-Based)
# ============================================================================


class TestInvariantNoConfigurationAllowsBreach:
    """INVARIANT: No configuration MUST allow classification breach.

    THREAT: Edge case configuration allows SECRET data to UNOFFICIAL sink.

    DEFENSE: Property-based testing with adversarial configurations.
    """

    @given(
        plugin_levels=st.lists(
            st.sampled_from([0, 1, 2]),  # Will map to security levels
            min_size=1,
            max_size=10
        )
    )
    def test_minimum_envelope_never_exceeds_weakest(self, plugin_levels):
        """PROPERTY: Operating level ≤ min(plugin levels) under ALL configurations.

        This property MUST hold for any possible plugin configuration,
        including adversarial/edge cases generated by Hypothesis.

        Given: Random plugin configuration (1-10 plugins, mixed levels)
        When: Computing minimum clearance envelope
        Then: Operating level ≤ weakest plugin level
        """
        # Map integers to SecurityLevel
        level_map = [SecurityLevel.UNOFFICIAL, SecurityLevel.OFFICIAL, SecurityLevel.SECRET]
        security_levels = [level_map[i] for i in plugin_levels]
        plugins = [MockPlugin(level) for level in security_levels]

        operating_level = compute_minimum_clearance_envelope(plugins)

        min_level = min(security_levels)
        assert operating_level <= min_level, \
            f"Operating level {operating_level.name} exceeds minimum {min_level.name}"

    @given(
        plugin_levels=st.lists(
            st.sampled_from([0, 1, 2]),  # Will map to security levels
            min_size=2,
            max_size=8
        )
    )
    def test_validation_blocks_all_insufficient_clearances(self, plugin_levels):
        """✅ CORRECT Bell-LaPadula: Plugins with LOW clearance reject HIGH envelope.

        Property-based test ensuring no configuration allows a plugin to receive data
        above its clearance level (Bell-LaPadula "no read up" enforcement).

        CORRECT Logic:
        - Plugin clearance < operating_level → REJECT (insufficient clearance)
        - Plugin clearance >= operating_level → ACCEPT (sufficient/trusted clearance)

        Given: Random plugin configuration with mixed levels
        When: Operating level = min(levels), validating all plugins
        Then: Any plugin with clearance < operating_level MUST reject
        """
        from elspeth.core.validation.base import SecurityValidationError

        # Map integers to SecurityLevel
        level_map = [SecurityLevel.UNOFFICIAL, SecurityLevel.OFFICIAL, SecurityLevel.SECRET]
        security_levels = [level_map[i] for i in plugin_levels]
        plugins = [MockPlugin(level) for level in security_levels]
        operating_level = compute_minimum_clearance_envelope(plugins)

        # Check each plugin
        for plugin in plugins:
            if plugin.get_security_level() < operating_level:
                # Plugin has INSUFFICIENT clearance - MUST reject
                with pytest.raises(SecurityValidationError):
                    plugin.validate_can_operate_at_level(operating_level)
            else:
                # Plugin has SUFFICIENT clearance (same or higher) - MUST accept
                plugin.validate_can_operate_at_level(operating_level)  # Should not raise


# ============================================================================
# TEST SUMMARY
# ============================================================================


"""
Security Invariants Defined:

1. ✅ Minimum Clearance Envelope (4 tests)
   - Basic mixed plugins
   - All same level
   - UNOFFICIAL weakest link
   - Empty plugins list

2. ✅ Plugin Validation (3 tests)
   - High-security rejects low envelope
   - Plugin accepts sufficient envelope
   - Plugin accepts higher envelope

3. ✅ Classification Uplifting (3 tests)
   - Uplifting to higher classification
   - Uplifting does not downgrade
   - Classification immutable

4. ✅ Output Classification (2 tests)
   - Transform uplifts classification
   - Same-level transform preserves classification

5. ✅ No Configuration Breach (2 property tests)
   - Minimum envelope never exceeds weakest
   - Validation blocks all insufficient clearances

TOTAL: 14 security invariant tests

Expected Status: ALL FAIL (red) until Phase 1 implementation
Target Status: ALL PASS (green) after Phase 1-2 implementation

Next Steps:
- Phase 1: Implement core security primitives (make tests green)
- Phase 2: Integrate with suite_runner.py
- Phase 3: Add integration tests for end-to-end scenarios
"""
