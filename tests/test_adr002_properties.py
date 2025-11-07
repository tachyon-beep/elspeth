"""ADR-002 Property-Based Security Tests

Property-based tests using Hypothesis to generate adversarial configurations
and verify security properties hold under ALL possible scenarios.

These tests complement test_adr002_invariants.py by:
1. Testing with 1000+ randomly generated configurations
2. Finding edge cases human testers might miss
3. Simulating adversarial/malicious configurations
4. Verifying properties under concurrent access patterns

CRITICAL: Each property test should run 1000+ examples to have confidence
          in the security property.
"""

import pytest
from pathlib import Path
from typing import List

from hypothesis import given, strategies as st, settings

from elspeth.core.security import SecurityLevel, SecureDataFrame
from elspeth.core.experiments.suite_runner import (
    compute_minimum_clearance_envelope,
    ExperimentSuiteRunner,
    SuiteExecutionContext,
)
from elspeth.core.experiments.config import ExperimentSuite
from elspeth.core.base.plugin import BasePlugin  # ADR-004: ABC with nominal typing


# ============================================================================
# PROPERTY 1: Minimum Envelope Correctness
# ============================================================================
class TestPropertyMinimumEnvelope:
    """PROPERTY: Minimum clearance envelope computation is correct under
               ALL possible plugin configurations.

    THREAT: Edge case configuration causes incorrect envelope calculation.
    """

    @settings(max_examples=1000)  # Run 1000+ adversarial examples
    @given(
        plugin_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=1,
            max_size=20  # Test with larger configurations
        )
    )
    def test_envelope_always_equals_minimum_level(self, plugin_levels):
        """PROPERTY: Operating level = MIN(plugin levels) for ANY configuration.

        Given: ANY plugin configuration (1-20 plugins, random levels)
        When: Computing minimum clearance envelope
        Then: Operating level = exact minimum of all plugin levels
        """
        from adr002_test_helpers import MockPlugin

        plugins = [MockPlugin(level) for level in plugin_levels]
        operating_level = compute_minimum_clearance_envelope(plugins)

        expected_minimum = min(plugin_levels)

        assert operating_level == expected_minimum, \
            f"Envelope {operating_level.name} != min {expected_minimum.name}"

    @settings(max_examples=1000)
    @given(
        plugin_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=1,
            max_size=20
        )
    )
    def test_envelope_never_higher_than_any_plugin(self, plugin_levels):
        """PROPERTY: Operating level ≤ EVERY plugin level (not just minimum).

        This is a stronger property - envelope must not exceed ANY plugin.

        Given: ANY plugin configuration
        When: Computing minimum clearance envelope
        Then: Operating level ≤ every individual plugin level
        """
        from adr002_test_helpers import MockPlugin

        plugins = [MockPlugin(level) for level in plugin_levels]
        operating_level = compute_minimum_clearance_envelope(plugins)

        for plugin_level in plugin_levels:
            assert operating_level <= plugin_level, \
                f"Envelope {operating_level.name} exceeds plugin {plugin_level.name}"


# ============================================================================
# PROPERTY 2: No Configuration Allows Breach
# ============================================================================


class TestPropertyNoClassificationBreach:
    """PROPERTY: No configuration allows data to reach component with
               insufficient clearance.

    THREAT: Edge case configuration bypasses security validation.

    NOTE: This is THE MOST CRITICAL property - it defines the entire
          security guarantee of ADR-002.
    """

    @settings(max_examples=1000)
    @given(
        datasource_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ]),
        sink_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ])
    )
    def test_no_breach_possible_datasource_sink(self, datasource_level, sink_level):
        """PROPERTY: If datasource > sink level, job MUST fail at start.

        This is the core classification breach prevention.

        Given: Datasource and sink with random security levels
        When: Attempting to run suite
        Then: Either job succeeds (datasource ≤ sink) OR fails at start (datasource > sink)
        """
        # TODO: Implement in Phase 2 after ExperimentSuiteRunner integration
        # This test skeleton documents the required property
        pytest.skip("Phase 2 not implemented yet - test skeleton only")

    @settings(max_examples=1000)
    @given(
        plugin_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=2,
            max_size=10
        )
    )
    def test_validation_consistent_with_envelope(self, plugin_levels):
        """PROPERTY: Validation results consistent with envelope calculation.

        If envelope = MIN(levels), then with trusted downgrade (allow_downgrade=True):
        - Plugins with level >= envelope should PASS validation (sufficient clearance)
        - Plugins with level < envelope should FAIL validation (insufficient clearance)

        MockPlugin implements allow_downgrade=True behavior implicitly:
        - Only rejects when operating_level > plugin_level (insufficient clearance)
        - Allows operating at lower levels (trusted downgrade)

        Given: ANY plugin configuration
        When: Computing envelope and validating plugins
        Then: Validation results match expected based on envelope and Bell-LaPadula rules
        """
        from adr002_test_helpers import MockPlugin
        from elspeth.core.validation.base import SecurityValidationError

        plugins = [MockPlugin(level) for level in plugin_levels]
        operating_level = compute_minimum_clearance_envelope(plugins)

        for plugin in plugins:
            plugin_level = plugin.get_security_level()

            if operating_level > plugin_level:
                # Operating level HIGHER than plugin's clearance - insufficient clearance
                # Example: UNOFFICIAL plugin cannot handle SECRET operating level
                with pytest.raises(SecurityValidationError):
                    plugin.validate_can_operate_at_level(operating_level)
            else:
                # Plugin level >= operating level (sufficient clearance)
                # With allow_downgrade=True (MockPlugin default): can operate at lower levels
                # Example: SECRET plugin can operate at UNOFFICIAL level (trusted downgrade)
                plugin.validate_can_operate_at_level(operating_level)


# ============================================================================
# PROPERTY 3: Classification Uplifting Monotonicity
# ============================================================================


class TestPropertyClassificationUplifting:
    """PROPERTY: Classification uplifting is monotonic (never decreases).

    THREAT: Sequence of transforms could downgrade classification.
    """

    @settings(max_examples=1000)
    @given(
        initial_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ]),
        transform_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=1,
            max_size=10
        )
    )
    def test_uplifting_sequence_monotonic(self, initial_level, transform_levels):
        """PROPERTY: Sequence of uplifts MUST be monotonically non-decreasing.

        Given: Initial classification and sequence of transform levels
        When: Applying uplifts sequentially
        Then: Classification never decreases
        """
        import pandas as pd

        current_df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1]}),
            security_level=initial_level
        )

        previous_level = initial_level

        for transform_level in transform_levels:
            current_df = current_df.with_uplifted_security_level(transform_level)
            current_level = current_df.security_level

            assert current_level >= previous_level, \
                f"Classification decreased: {previous_level.name} -> {current_level.name}"

            previous_level = current_level

    @settings(max_examples=1000)
    @given(
        initial_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ]),
        transform_levels=st.lists(
            st.sampled_from([
                SecurityLevel.UNOFFICIAL,
                SecurityLevel.OFFICIAL,
                SecurityLevel.SECRET
            ]),
            min_size=1,
            max_size=10
        )
    )
    def test_final_classification_is_maximum(self, initial_level, transform_levels):
        """PROPERTY: After sequence of uplifts, classification = MAX(all levels).

        Given: Initial level and sequence of transform levels
        When: Applying all uplifts
        Then: Final classification = MAX(initial, all transforms)
        """
        import pandas as pd

        current_df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1]}),
            security_level=initial_level
        )

        for transform_level in transform_levels:
            current_df = current_df.with_uplifted_security_level(transform_level)

        all_levels = [initial_level] + transform_levels
        expected_max = max(all_levels)

        assert current_df.security_level == expected_max, \
            f"Final classification {current_df.security_level.name} != " \
            f"max {expected_max.name}"


# ============================================================================
# PROPERTY 4: Immutability Guarantees
# ============================================================================


class TestPropertyImmutability:
    """PROPERTY: SecureDataFrame immutability prevents accidental downgrades.

    THREAT: Mutable classification allows accidental security violations.
    """

    @settings(max_examples=500)
    @given(
        initial_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ]),
        uplift_level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ])
    )
    def test_uplifting_creates_new_instance(self, initial_level, uplift_level):
        """PROPERTY: Uplifting MUST create new instance, not modify original.

        Given: SecureDataFrame at initial level
        When: Uplifting to different level
        Then: Original unchanged, new instance returned
        """
        import pandas as pd

        original = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1]}),
            security_level=initial_level
        )

        uplifted = original.with_uplifted_security_level(uplift_level)

        # Original must be unchanged
        assert original.security_level == initial_level

        # New instance returned
        assert uplifted is not original

    @settings(max_examples=500)
    @given(
        level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ])
    )
    def test_classification_attribute_immutable(self, level):
        """PROPERTY: Classification attribute MUST be immutable (frozen).

        Given: SecureDataFrame at any level
        When: Attempting to modify classification attribute
        Then: AttributeError raised (frozen dataclass)
        """
        import pandas as pd

        df = SecureDataFrame.create_from_datasource(
            data=pd.DataFrame({"col": [1]}),
            security_level=level
        )

        with pytest.raises(AttributeError):
            df.security_level = SecurityLevel.UNOFFICIAL


# ============================================================================
# PROPERTY 5: Adversarial Edge Cases
# ============================================================================


class TestPropertyAdversarialEdgeCases:
    """PROPERTY: Security properties hold even for adversarial/unusual configurations.

    THREAT: Edge cases like empty lists, all same level, etc. bypass security.
    """

    def test_empty_plugins_safe_default(self):
        """PROPERTY: Empty plugin list has safe default (UNOFFICIAL).

        Given: No plugins configured
        When: Computing minimum clearance envelope
        Then: Operating level = UNOFFICIAL (safest default)
        """
        operating_level = compute_minimum_clearance_envelope([])

        assert operating_level == SecurityLevel.UNOFFICIAL

    @settings(max_examples=500)
    @given(
        level=st.sampled_from([
            SecurityLevel.UNOFFICIAL,
            SecurityLevel.OFFICIAL,
            SecurityLevel.SECRET
        ]),
        count=st.integers(min_value=1, max_value=100)
    )
    def test_all_same_level_correct(self, level, count):
        """PROPERTY: All plugins at same level → envelope = that level.

        Given: N plugins all at same security level
        When: Computing minimum clearance envelope
        Then: Operating level = common level
        """
        from adr002_test_helpers import MockPlugin

        plugins = [MockPlugin(level) for _ in range(count)]
        operating_level = compute_minimum_clearance_envelope(plugins)

        assert operating_level == level


# ============================================================================
# TEST SUMMARY
# ============================================================================


"""
Property-Based Security Tests:

1. ✅ Minimum Envelope Correctness (2 properties, 1000 examples each)
   - Envelope always equals minimum level
   - Envelope never higher than any plugin

2. ✅ No Classification Breach (2 properties, 1000 examples each)
   - No breach possible datasource→sink
   - Validation consistent with envelope

3. ✅ Classification Uplifting Monotonicity (2 properties, 1000 examples each)
   - Uplifting sequence monotonic
   - Final classification is maximum

4. ✅ Immutability Guarantees (2 properties, 500 examples each)
   - Uplifting creates new instance
   - Classification attribute immutable

5. ✅ Adversarial Edge Cases (2 properties, 500 examples each)
   - Empty plugins safe default
   - All same level correct

TOTAL: 10 property-based tests × 500-1000 examples = 7500+ test scenarios

Expected Status: ALL FAIL/SKIP until Phase 1-2 implementation
Target Status: ALL PASS after Phase 1-2 implementation

Hypothesis will find edge cases like:
- All UNOFFICIAL plugins
- Single SECRET plugin among many UNOFFICIAL
- Alternating levels
- Large configurations (20+ plugins)
- Empty configurations

Next Steps:
- Phase 1: Implement core primitives (unskip tests)
- Phase 2: Implement suite integration (complete skipped tests)
- Phase 3: Add integration tests for end-to-end scenarios
"""
