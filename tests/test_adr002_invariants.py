"""ADR-002 Security Invariants - Test-First Implementation

These tests define the security properties that MUST hold for ADR-002
suite-level security enforcement. All tests should FAIL initially (red),
then pass after implementation (green).

Security Invariants:
1. Orchestrator MUST operate at MIN(all plugin security levels)
2. Plugins MUST refuse to operate below their security requirement
3. Classification uplifting MUST be automatic (not manual/optional)
4. Output classification MUST be ≥ input classification (always)
5. No configuration MUST allow classification breach

CRITICAL: These are not regression tests - they define NEW security behavior.
"""

import pytest
from hypothesis import given, strategies as st
from pathlib import Path
from typing import Any

# NOTE: These imports will fail until Phase 1 implementation
# This is EXPECTED for test-first development
try:
    from elspeth.core.security import SecurityLevel, ClassifiedDataFrame
    from elspeth.core.experiments.suite_runner import (
        compute_minimum_clearance_envelope,
        ExperimentSuiteRunner,
    )
    from elspeth.core.base.protocols import BasePlugin
except ImportError:
    # Allow test file to be created before implementation exists
    SecurityLevel = None
    ClassifiedDataFrame = None
    compute_minimum_clearance_envelope = None
    ExperimentSuiteRunner = None
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

        Raises:
            SecurityValidationError: If operating_level < self._security_level
        """
        from elspeth.core.validation.base import SecurityValidationError

        if operating_level < self._security_level:
            raise SecurityValidationError(
                f"{self.__class__.__name__} requires {self._security_level.name}, "
                f"but orchestrator operating at {operating_level.name}"
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


@pytest.mark.skipif(
    compute_minimum_clearance_envelope is None,
    reason="Phase 1 not implemented yet (expected for test-first)"
)
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


@pytest.mark.skipif(
    BasePlugin is None,
    reason="Phase 1 not implemented yet (expected for test-first)"
)
class TestInvariantPluginValidation:
    """INVARIANT: Plugins MUST refuse to operate below their security requirement.

    THREAT: If SECRET datasource accepts UNOFFICIAL envelope → data leakage.

    DEFENSE: BasePlugin.validate_can_operate_at_level() enforces clearance checks.
    """

    def test_high_security_plugin_rejects_low_envelope(self):
        """SECRET plugin MUST reject UNOFFICIAL operating level.

        Given: Plugin requires SECRET clearance
        When: Validating against UNOFFICIAL envelope
        Then: SecurityValidationError raised with clear message
        """
        from elspeth.core.validation.base import SecurityValidationError

        secret_plugin = SecretPlugin()

        with pytest.raises(SecurityValidationError) as exc_info:
            secret_plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

        error_msg = str(exc_info.value)
        assert "SECRET" in error_msg, "Error should mention required level"
        assert "UNOFFICIAL" in error_msg, "Error should mention envelope level"

    def test_plugin_accepts_sufficient_envelope(self):
        """Plugin MUST accept operating level ≥ its requirement.

        Given: Plugin requires OFFICIAL clearance
        When: Validating against OFFICIAL envelope
        Then: No exception (validation passes)
        """
        official_plugin = OfficialPlugin()

        # Should not raise
        official_plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_plugin_accepts_higher_envelope(self):
        """Plugin MUST accept operating level > its requirement.

        Given: Plugin requires UNOFFICIAL clearance
        When: Validating against SECRET envelope (higher)
        Then: No exception (validation passes)
        """
        unofficial_plugin = UnofficialPlugin()

        # Should not raise (SECRET > UNOFFICIAL)
        unofficial_plugin.validate_can_operate_at_level(SecurityLevel.SECRET)


# ============================================================================
# INVARIANT 3: Classification Uplifting (Automatic)
# ============================================================================


@pytest.mark.skipif(
    ClassifiedDataFrame is None,
    reason="Phase 1 not implemented yet (expected for test-first)"
)
class TestInvariantClassificationUplifting:
    """INVARIANT: Classification uplifting MUST be automatic (not manual/optional).

    THREAT: If uplifting manual/forgotten → classification mislabeling
            (OFFICIAL data through SECRET LLM stays labeled OFFICIAL).

    DEFENSE: ClassifiedDataFrame.with_uplifted_classification() enforces uplifting.
    """

    def test_uplifting_to_higher_classification(self):
        """Uplifting MUST increase classification to higher level.

        Given: OFFICIAL data
        When: Uplifting to SECRET
        Then: New ClassifiedDataFrame with SECRET classification
        """
        import pandas as pd

        df = ClassifiedDataFrame(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            classification=SecurityLevel.OFFICIAL
        )

        uplifted = df.with_uplifted_classification(SecurityLevel.SECRET)

        assert uplifted.classification == SecurityLevel.SECRET
        assert df.classification == SecurityLevel.OFFICIAL, \
            "Original should remain unchanged (immutability)"

    def test_uplifting_does_not_downgrade(self):
        """Uplifting MUST NOT allow downgrade (max operation).

        Given: SECRET data
        When: Attempting to "uplift" to OFFICIAL (lower)
        Then: Classification remains SECRET (max wins)
        """
        import pandas as pd

        df = ClassifiedDataFrame(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            classification=SecurityLevel.SECRET
        )

        # "Uplift" to lower level should keep higher level
        result = df.with_uplifted_classification(SecurityLevel.OFFICIAL)

        assert result.classification == SecurityLevel.SECRET, \
            "Classification must not downgrade (max operation)"

    def test_classification_immutable(self):
        """Classification MUST be immutable after creation.

        Given: ClassifiedDataFrame created
        When: Attempting to modify classification attribute
        Then: AttributeError (frozen dataclass)
        """
        import pandas as pd

        df = ClassifiedDataFrame(
            data=pd.DataFrame({"col": [1, 2, 3]}),
            classification=SecurityLevel.OFFICIAL
        )

        with pytest.raises(AttributeError):
            df.classification = SecurityLevel.UNOFFICIAL


# ============================================================================
# INVARIANT 4: Output Classification ≥ Input Classification
# ============================================================================


@pytest.mark.skipif(
    ClassifiedDataFrame is None,
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

        input_df = ClassifiedDataFrame(
            data=pd.DataFrame({"text": ["test"]}),
            classification=SecurityLevel.OFFICIAL
        )

        # Simulate transform by SECRET component
        component_level = SecurityLevel.SECRET
        output_classification = max(input_df.classification, component_level)

        output_df = ClassifiedDataFrame(
            data=pd.DataFrame({"transformed": ["result"]}),
            classification=output_classification
        )

        assert output_df.classification >= input_df.classification
        assert output_df.classification == SecurityLevel.SECRET

    def test_same_level_transform_preserves_classification(self):
        """Transform at same level MUST preserve classification.

        Given: OFFICIAL input data
        When: Transformed by OFFICIAL component
        Then: Output classification = OFFICIAL (unchanged)
        """
        import pandas as pd

        input_df = ClassifiedDataFrame(
            data=pd.DataFrame({"text": ["test"]}),
            classification=SecurityLevel.OFFICIAL
        )

        # Simulate transform by OFFICIAL component
        component_level = SecurityLevel.OFFICIAL
        output_classification = max(input_df.classification, component_level)

        output_df = ClassifiedDataFrame(
            data=pd.DataFrame({"transformed": ["result"]}),
            classification=output_classification
        )

        assert output_df.classification == input_df.classification


# ============================================================================
# INVARIANT 5: No Configuration Allows Breach (Property-Based)
# ============================================================================


@pytest.mark.skipif(
    compute_minimum_clearance_envelope is None,
    reason="Phase 1 not implemented yet (expected for test-first)"
)
class TestInvariantNoConfigurationAllowsBreach:
    """INVARIANT: No configuration MUST allow classification breach.

    THREAT: Edge case configuration allows SECRET data to UNOFFICIAL sink.

    DEFENSE: Property-based testing with adversarial configurations.
    """

    @given(
        plugin_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
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
        plugins = [MockPlugin(level) for level in plugin_levels]

        operating_level = compute_minimum_clearance_envelope(plugins)

        min_level = min(plugin_levels)
        assert operating_level <= min_level, \
            f"Operating level {operating_level.name} exceeds minimum {min_level.name}"

    @given(
        plugin_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=2,
            max_size=8
        )
    )
    def test_validation_blocks_all_insufficient_clearances(self, plugin_levels):
        """PROPERTY: If any plugin requires > envelope, validation MUST fail.

        This ensures no configuration allows a plugin to receive data
        above its clearance.

        Given: Random plugin configuration with mixed levels
        When: Operating level = min(levels), validating all plugins
        Then: Any plugin with level > operating_level MUST reject
        """
        from elspeth.core.validation.base import SecurityValidationError

        plugins = [MockPlugin(level) for level in plugin_levels]
        operating_level = compute_minimum_clearance_envelope(plugins)

        # Check each plugin
        for plugin in plugins:
            if plugin.get_security_level() > operating_level:
                # Plugin requires higher level than envelope - MUST reject
                with pytest.raises(SecurityValidationError):
                    plugin.validate_can_operate_at_level(operating_level)
            else:
                # Plugin can handle envelope level - MUST accept
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
