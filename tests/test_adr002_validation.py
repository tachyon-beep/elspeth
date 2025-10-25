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

    def test_mixed_levels_fails_at_start(self):
        """Test validation FAILS when SECRET component mixed with UNOFFICIAL.

        Given: SECRET datasource, UNOFFICIAL sink
        When: Validating security
        Then: SecurityValidationError raised before job starts
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

        # Execute - should raise
        with pytest.raises(SecurityValidationError) as exc_info:
            suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

        # Assert error message quality
        error_msg = str(exc_info.value)
        assert "ADR-002 Start-Time Validation Failed" in error_msg
        assert "SECRET" in error_msg
        assert "UNOFFICIAL" in error_msg
        assert experiment.name in error_msg

    def test_minimum_envelope_computed_correctly(self):
        """Test minimum clearance envelope = MIN(all plugin levels).

        Given: SECRET, OFFICIAL, OFFICIAL plugins
        When: Computing envelope
        Then: operating_security_level = OFFICIAL (minimum)
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
            datasource=MockSecureComponent("datasource"),
            llm_client=MockOfficialComponent("llm"),
        )
        sinks = [MockOfficialComponent("sink")]
        ctx = SuiteExecutionContext.create(
            suite=suite,
            defaults={},
            preflight_info={},
        )

        # Execute - SECRET datasource should REJECT OFFICIAL envelope
        with pytest.raises(SecurityValidationError):
            suite_runner._validate_experiment_security(experiment, runner, sinks, ctx)

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

❌ test_mixed_levels_fails_at_start
   - Verifies: Validation BLOCKS when SECRET + UNOFFICIAL mixed
   - Property: Start-time validation prevents classification breach
   - CRITICAL: Main certification test for ADR-002 T1

❌ test_minimum_envelope_computed_correctly
   - Verifies: Envelope = MIN(all plugin levels)
   - Property: Weakest-link principle enforced

✅ test_backward_compatibility_non_baseplugin
   - Verifies: Legacy components without BasePlugin work
   - Property: Validation is opt-in

✅ test_empty_plugins_list_safe
   - Verifies: Handles edge case of no plugins
   - Property: Graceful degradation

Total: 5 focused unit tests covering core validation logic
"""
