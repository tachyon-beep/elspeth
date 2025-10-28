"""ADR-002 Security Validation Unit Tests

Direct tests of _validate_experiment_security() method to verify the security
enforcement logic works correctly.

These are UNIT tests - they test the validation method directly with mock
plugins, not the full suite execution flow.
"""

import pandas as pd
import pytest

from elspeth.core.base.plugin import BasePlugin  # ADR-004: ABC with nominal typing
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import (
    ExperimentSuiteRunner,
    SuiteExecutionContext,
)
from elspeth.core.validation.base import SecurityValidationError


# ============================================================================
# Mock Plugins
# ============================================================================


class MockSecureComponent(BasePlugin):
    """Component requiring SECRET clearance."""

    def __init__(self, name: str = "SecureComponent"):
        super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)
        self.name = name


class MockOfficialComponent(BasePlugin):
    """Component requiring OFFICIAL clearance."""

    def __init__(self, name: str = "OfficialComponent"):
        super().__init__(security_level=SecurityLevel.OFFICIAL, allow_downgrade=True)
        self.name = name


class MockUnofficialComponent(BasePlugin):
    """Component handling UNOFFICIAL data."""

    def __init__(self, name: str = "UnofficialComponent"):
        super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
        self.name = name


class MockRunner:
    """Mock ExperimentRunner with configurable plugins."""

    def __init__(self, datasource=None, llm_client=None, llm_middlewares=None):
        self.datasource = datasource
        self.llm_client = llm_client
        self.llm_middlewares = llm_middlewares or []
        # Add attributes expected by _propagate_operating_level()
        self.row_plugins = []
        self.aggregator_plugins = []  # Note: aggregator_plugins, not aggregators
        self.validation_plugins = []  # Note: validation_plugins, not validators
        self.early_stop_plugins = []  # Note: plural, not singular
        self.rate_limiter = None
        self.cost_tracker = None


# ============================================================================
# Unit Tests for _validate_experiment_security
# ============================================================================


class TestValidateExperimentSecurity:
    """Unit tests for ADR-002 security validation logic."""

    def test_all_plugins_same_level_succeeds(self):
        """Test validation succeeds when all plugins at same security level.

        Given: All plugins at OFFICIAL level
        When: Validating security
        Then: No exception, operating_security_level = OFFICIAL
        """
        # Setup
        experiment = ExperimentConfig(
            name="test",
            prompt_system="test",
            prompt_template="test",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])
        suite_runner = ExperimentSuiteRunner(suite, llm_client=object(), sinks=[])

        runner = MockRunner(
            datasource=MockOfficialComponent("datasource"),
            llm_client=MockOfficialComponent("llm"),
        )
        sinks = [MockOfficialComponent("sink1"), MockOfficialComponent("sink2")]
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - should not raise
        suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # Assert
        assert ctx.operating_security_level == SecurityLevel.OFFICIAL

    def test_mixed_levels_succeeds_with_trusted_downgrade(self):
        """Test validation SUCCEEDS when SECRET datasource trusted to downgrade to UNOFFICIAL.

        Given: SECRET datasource (allow_downgrade=True), UNOFFICIAL sink
        When: Validating security
        Then: Validation succeeds, operating_level = UNOFFICIAL

        Trusted Downgrade Model:
        - SECRET datasource is CAPABLE of accessing UNOFFICIAL→SECRET data
        - When operating at UNOFFICIAL, datasource is RESPONSIBLE for filtering
        - Framework TRUSTS certified plugins to enforce filtering correctly
        - Enforcement = audit + certification, NOT runtime checks
        """
        # Setup
        experiment = ExperimentConfig(
            name="test",
            prompt_system="test",
            prompt_template="test",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])
        suite_runner = ExperimentSuiteRunner(suite, llm_client=object(), sinks=[])

        runner = MockRunner(datasource=MockSecureComponent("datasource"))
        sinks = [MockUnofficialComponent("sink")]
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - should NOT raise (trusted downgrade)
        suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # Assert operating level = minimum
        assert ctx.operating_security_level == SecurityLevel.UNOFFICIAL

    def test_minimum_envelope_computed_correctly(self):
        """Test minimum clearance envelope = MIN(all plugin levels).

        Given: SECRET datasource, OFFICIAL llm, OFFICIAL sink (all with allow_downgrade=True)
        When: Computing envelope
        Then: operating_security_level = OFFICIAL (minimum), validation succeeds

        Trusted Downgrade:
        - SECRET datasource CAN downgrade to OFFICIAL (allow_downgrade=True)
        - Datasource is trusted to filter and return only OFFICIAL-level data
        """
        # Setup
        experiment = ExperimentConfig(
            name="test",
            prompt_system="test",
            prompt_template="test",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])
        suite_runner = ExperimentSuiteRunner(suite, llm_client=object(), sinks=[])

        runner = MockRunner(
            datasource=MockSecureComponent("datasource"),  # SECRET with allow_downgrade=True
            llm_client=MockOfficialComponent("llm"),
        )
        sinks = [MockOfficialComponent("sink")]
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - should succeed (trusted downgrade)
        suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # Assert operating level = minimum
        assert ctx.operating_security_level == SecurityLevel.OFFICIAL

    def test_backward_compatibility_non_baseplugin(self):
        """Test validation skipped for components not implementing BasePlugin.

        Given: Components without BasePlugin protocol
        When: Validating security
        Then: Validation skipped, no exception
        """
        # Setup
        experiment = ExperimentConfig(
            name="test",
            prompt_system="test",
            prompt_template="test",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])
        suite_runner = ExperimentSuiteRunner(suite, llm_client=object(), sinks=[])

        # Legacy components without BasePlugin
        class LegacyDatasource:
            pass

        class LegacySink:
            pass

        runner = MockRunner(datasource=LegacyDatasource())
        sinks = [LegacySink()]
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - should not raise (validation skipped)
        suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # operating_security_level should remain None (no BasePlugin components)
        assert ctx.operating_security_level is None

    def test_empty_plugins_list_safe(self):
        """Test validation handles empty plugins list safely.

        Given: No plugins implementing BasePlugin
        When: Validating security
        Then: Validation skipped gracefully
        """
        # Setup
        experiment = ExperimentConfig(
            name="test",
            prompt_system="test",
            prompt_template="test",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])
        suite_runner = ExperimentSuiteRunner(suite, llm_client=object(), sinks=[])

        runner = MockRunner()  # No datasource, no llm, no middleware
        sinks = []  # No sinks
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - should not raise
        suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # No plugins = no security requirements
        assert ctx.operating_security_level is None


# ============================================================================
# Test Summary
# ============================================================================


"""
Unit Test Coverage:

✅ test_all_plugins_same_level_succeeds
   - Verifies: Validation succeeds when security levels match
   - Property: operating_level = common level

✅ test_mixed_levels_succeeds_with_trusted_downgrade
   - Verifies: Validation SUCCEEDS with trusted downgrade
   - Property: SECRET datasource trusted to filter to UNOFFICIAL
   - Model: Trusted downgrade (audit + certification)

✅ test_minimum_envelope_computed_correctly
   - Verifies: Envelope = MIN(all plugin levels)
   - Property: Weakest-link principle enforced
   - Verifies: Trusted downgrade allows operation

✅ test_backward_compatibility_non_baseplugin
   - Verifies: Legacy components without BasePlugin work
   - Property: Validation is opt-in

✅ test_empty_plugins_list_safe
   - Verifies: Handles edge case of no plugins
   - Property: Graceful degradation

Total: 5 focused unit tests covering core validation logic
"""
