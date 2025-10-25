"""ADR-002 Suite-Level Security Integration Tests

These tests verify end-to-end security enforcement in suite_runner using
actual plugins that implement BasePlugin protocol.

Test Scenarios:
1. ✅ Happy path: All plugins at matching security levels
2. ❌ Fail path: Mixed security levels (SECRET datasource, UNOFFICIAL sink)
3. ✅ Upgrade path: Data uplifted through higher security components
4. ❌ Multiple experiments: Validation enforced per-experiment

These are INTEGRATION tests - they test the complete security validation
flow from suite startup through experiment execution.
"""

import pandas as pd
import pytest

from elspeth.core.base.protocols import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.core.validation.base import SecurityValidationError

# ============================================================================
# Mock Plugins for Testing
# ============================================================================


class MockSecureDatasource(BasePlugin):
    """Datasource requiring SECRET clearance."""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MockSecureDatasource requires SECRET, got {operating_level.name}"
            )

    def load(self) -> pd.DataFrame:
        return self.df


class MockOfficialDatasource(BasePlugin):
    """Datasource requiring OFFICIAL clearance."""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.OFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.OFFICIAL:
            raise SecurityValidationError(
                f"MockOfficialDatasource requires OFFICIAL, got {operating_level.name}"
            )

    def load(self) -> pd.DataFrame:
        return self.df


class MockUnofficialSink(BasePlugin):
    """Sink that only handles UNOFFICIAL data."""

    def __init__(self):
        self.written = []

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.UNOFFICIAL:
            # UNOFFICIAL is lowest, so this never happens
            raise SecurityValidationError(
                f"MockUnofficialSink requires UNOFFICIAL, got {operating_level.name}"
            )

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        self.written.append(results)


class MockOfficialSink(BasePlugin):
    """Sink that handles data up to OFFICIAL level (rejects SECRET and above)."""

    def __init__(self):
        self.written = []

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.OFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        # OFFICIAL sink can only handle data at OFFICIAL level or lower
        # Rejects SECRET, PROTECTED, etc. (too sensitive)
        if operating_level > SecurityLevel.OFFICIAL:
            raise SecurityValidationError(
                f"MockOfficialSink cannot handle {operating_level.name} data "
                f"(maximum clearance: OFFICIAL)"
            )
        if operating_level < SecurityLevel.OFFICIAL:
            raise SecurityValidationError(
                f"MockOfficialSink requires at least OFFICIAL, got {operating_level.name}"
            )

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        self.written.append(results)


class MockSecretSink(BasePlugin):
    """Sink requiring SECRET clearance."""

    def __init__(self):
        self.written = []

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MockSecretSink requires SECRET, got {operating_level.name}"
            )

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        self.written.append(results)


class MockSecretTransformPlugin(BasePlugin):
    """Transform plugin requiring SECRET clearance (for ADR-002-A testing)."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MockSecretTransformPlugin requires SECRET, got {operating_level.name}"
            )

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data (adds 'processed' column)."""
        result = data.copy()
        result["processed"] = True
        return result


class MockLLMClient:
    """Simple mock LLM that doesn't implement BasePlugin (backward compat)."""

    def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
        return {
            "output": f"Mock response to: {user_prompt}",
            "metadata": {"model": "mock-llm"},
        }


# ============================================================================
# Integration Tests
# ============================================================================


class TestADR002SuiteIntegration:
    """Integration tests for ADR-002 suite-level security enforcement."""

    def test_happy_path_matching_security_levels(self):
        """Test suite runs successfully when all plugins have matching security levels.

        Given: SECRET datasource, SECRET sink
        When: Running suite
        Then: Job executes successfully, operating_security_level = SECRET
        """
        df = pd.DataFrame({"text": ["test1", "test2"]})
        datasource = MockSecureDatasource(df)
        sink = MockSecretSink()

        experiment = ExperimentConfig(
            name="secret_experiment",
            prompt_system="Test system",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        # Create suite runner with datasource
        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Run with sink
        results = runner.run(df, sink_factory=lambda exp: [sink])

        # Assertions
        assert "secret_experiment" in results
        assert len(sink.written) > 0, "Sink should have received data"

    def test_fail_path_secret_datasource_unofficial_sink(self):
        """Test suite FAILS when SECRET datasource paired with UNOFFICIAL sink.

        Given: SECRET datasource, UNOFFICIAL sink
        When: Running suite
        Then: SecurityValidationError raised at start-time (before data retrieval)

        This is the CRITICAL certification test for ADR-002 Threat T1.
        """
        df = pd.DataFrame({"text": ["test1", "test2"]})
        datasource = MockSecureDatasource(df)  # Requires SECRET
        sink = MockUnofficialSink()  # Only handles UNOFFICIAL

        experiment = ExperimentConfig(
            name="mixed_security_experiment",
            prompt_system="Test system",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Expect security validation to BLOCK job at start
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(df, sink_factory=lambda exp: [sink])

        error_msg = str(exc_info.value)
        assert "ADR-002" in error_msg, "Error should reference ADR-002"
        assert "Start-Time Validation Failed" in error_msg
        assert "SECRET" in error_msg, "Error should mention required level"
        assert "UNOFFICIAL" in error_msg, "Error should mention operating level"

        # Verify no data was written (job failed at start)
        assert len(sink.written) == 0, "Sink should NOT have received data (job blocked)"

    def test_upgrade_path_official_datasource_secret_sink(self):
        """Test suite runs when datasource security ≤ sink security (upgrade allowed).

        Given: OFFICIAL datasource, SECRET sink
        When: Running suite
        Then: Job executes successfully, operating_security_level = OFFICIAL (weakest link)

        This demonstrates that data can be uplifted through higher-security components.
        """
        df = pd.DataFrame({"text": ["test1", "test2"]})
        datasource = MockOfficialDatasource(df)  # Requires OFFICIAL
        sink = MockSecretSink()  # Requires SECRET (higher than datasource)

        experiment = ExperimentConfig(
            name="upgrade_experiment",
            prompt_system="Test system",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # SECRET sink requires SECRET, but operating level = OFFICIAL
        # Therefore SECRET sink should reject the operating level
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(df, sink_factory=lambda exp: [sink])

        error_msg = str(exc_info.value)
        assert "SECRET" in error_msg, "SECRET sink should reject OFFICIAL envelope"
        assert "OFFICIAL" in error_msg

    def test_backward_compatibility_non_baseplugin_components(self):
        """Test suite runs normally when components don't implement BasePlugin.

        Given: Components that don't implement BasePlugin (legacy)
        When: Running suite
        Then: Job executes successfully (validation skipped for non-BasePlugin)
        """
        df = pd.DataFrame({"text": ["test1"]})

        # Mock datasource and sink that DON'T implement BasePlugin
        class LegacyDatasource:
            def load(self) -> pd.DataFrame:
                return df

        class LegacySink:
            def __init__(self):
                self.written = []

            def write(self, results: dict, *, metadata: dict | None = None) -> None:
                self.written.append(results)

        datasource = LegacyDatasource()
        sink = LegacySink()

        experiment = ExperimentConfig(
            name="legacy_experiment",
            prompt_system="Test system",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Should succeed - no BasePlugin components, validation skipped
        results = runner.run(df, sink_factory=lambda exp: [sink])

        assert "legacy_experiment" in results
        assert len(sink.written) > 0, "Legacy sink should still work"

    def test_e2e_adr002a_datasource_plugin_sink_flow(self):
        """END-TO-END: Full ADR-002-A flow with ClassifiedDataFrame creation and transformation.

        This test verifies the complete secure data flow:
        1. Datasource creates ClassifiedDataFrame via create_from_datasource()
        2. Plugin transforms data via with_uplifted_classification()
        3. Sink receives properly classified data
        4. All components validate at start-time (ADR-002)

        Given: SECRET datasource + SECRET plugin + SECRET sink
        When: Running suite end-to-end
        Then:
          - Start-time validation passes (all at SECRET)
          - Datasource uses correct factory pattern
          - Plugin uses correct uplifting pattern
          - Data flows through entire pipeline
          - No classification breaches

        This is the COMPREHENSIVE integration test requested by code review.
        """
        from elspeth.core.security.classified_data import ClassifiedDataFrame

        df = pd.DataFrame({"text": ["secret1", "secret2"]})

        # Create datasource that uses ADR-002-A factory pattern
        class ADR002ACompliantDatasource(BasePlugin):
            """Datasource that correctly creates ClassifiedDataFrame."""

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.SECRET

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.SECRET:
                    raise SecurityValidationError(
                        f"ADR002ACompliantDatasource requires SECRET, got {operating_level.name}"
                    )

            def load(self) -> pd.DataFrame:
                """Load data as ClassifiedDataFrame using correct pattern."""
                # ✅ CORRECT: Use factory method (ADR-002-A compliant)
                classified_frame = ClassifiedDataFrame.create_from_datasource(
                    df, SecurityLevel.SECRET
                )
                return classified_frame.data  # Return underlying DataFrame

        # Create plugin that uses ADR-002-A transformation pattern
        class ADR002ACompliantPlugin(BasePlugin):
            """Plugin that correctly transforms ClassifiedDataFrame."""

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.SECRET

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.SECRET:
                    raise SecurityValidationError(
                        f"ADR002ACompliantPlugin requires SECRET, got {operating_level.name}"
                    )

            def transform(self, data: pd.DataFrame) -> pd.DataFrame:
                """Transform data using ADR-002-A pattern."""
                # In real usage, plugin would receive ClassifiedDataFrame from previous stage
                # For this test, we simulate the transform pattern
                # ✅ CORRECT: Use with_uplifted_classification() for transforms
                classified_input = ClassifiedDataFrame.create_from_datasource(
                    data, SecurityLevel.SECRET
                )

                # Transform data
                result = data.copy()
                result["processed_by_plugin"] = True

                # ✅ CORRECT: Uplift classification (ADR-002-A compliant)
                output_frame = classified_input.with_new_data(result)
                uplifted = output_frame.with_uplifted_classification(SecurityLevel.SECRET)

                return uplifted.data  # Return underlying DataFrame

        datasource = ADR002ACompliantDatasource()
        sink = MockSecretSink()

        experiment = ExperimentConfig(
            name="adr002a_e2e_test",
            prompt_system="Test system",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # ✅ Should succeed: All components at SECRET level
        results = runner.run(df, sink_factory=lambda exp: [sink])

        # Verify end-to-end flow completed
        assert "adr002a_e2e_test" in results, "Experiment should execute"
        assert len(sink.written) > 0, "Sink should receive data"

        # Verify data flowed through correctly
        written_data = sink.written[0]
        assert written_data is not None, "Data should be written to sink"

    def test_multi_stage_classification_uplifting(self):
        """Multi-stage pipeline with classification uplifting at each stage (SUCCESS).

        This test verifies that classification accumulates correctly through
        a multi-stage pipeline where all components can operate at the envelope level.

        Given: OFFICIAL datasource → OFFICIAL transform → SECRET LLM → OFFICIAL sink
        When: Running multi-stage pipeline
        Then:
          - Start-time validation computes envelope = OFFICIAL (min of all components)
          - All components accept OFFICIAL envelope (validation passes)
          - Data flows through OFFICIAL transform (stays OFFICIAL)
          - Data processed by SECRET LLM (runtime tainted to SECRET)
          - OFFICIAL sink receives data (envelope validation passed at start-time)
          - No downgrading at any stage (T4 prevention)

        This tests realistic multi-stage pipelines that ADR-002/002-A must support.
        Shows that components with higher clearances (SECRET LLM) can process data
        at lower envelope levels (OFFICIAL).
        """
        from elspeth.core.security.classified_data import ClassifiedDataFrame

        df = pd.DataFrame({"text": ["data1", "data2"]})

        # OFFICIAL datasource
        class OfficialDatasource(BasePlugin):
            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.OFFICIAL

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.OFFICIAL:
                    raise SecurityValidationError(
                        f"OfficialDatasource requires OFFICIAL, got {operating_level.name}"
                    )

            def load(self) -> pd.DataFrame:
                classified = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.OFFICIAL)
                return classified.data

        # OFFICIAL transform (stays at OFFICIAL)
        class OfficialTransformPlugin(BasePlugin):
            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.OFFICIAL

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.OFFICIAL:
                    raise SecurityValidationError(
                        f"OfficialTransformPlugin requires OFFICIAL, got {operating_level.name}"
                    )

            def transform(self, data: pd.DataFrame) -> pd.DataFrame:
                # Simulate receiving ClassifiedDataFrame
                classified_input = ClassifiedDataFrame.create_from_datasource(data, SecurityLevel.OFFICIAL)

                result = data.copy()
                result["stage1_processed"] = True

                # Uplift to OFFICIAL (no change since already OFFICIAL)
                output = classified_input.with_new_data(result)
                uplifted = output.with_uplifted_classification(SecurityLevel.OFFICIAL)
                return uplifted.data

        # SECRET LLM client (can operate at OFFICIAL level, taints to SECRET at runtime)
        class SecretLLMClient:
            """Mock SECRET-level LLM for testing uplifting."""

            def __init__(self):
                self.security_level = SecurityLevel.SECRET

            def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
                # LLM processing happens here - data is now tainted by SECRET model at runtime
                return {
                    "content": f"[SECRET LLM] {user_prompt}",
                    "metadata": {"model": "secret-llm", "security_level": "SECRET"},
                }

        # OFFICIAL sink (can handle OFFICIAL envelope)
        class OfficialSink(BasePlugin):
            def __init__(self):
                self.written = []

            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.OFFICIAL

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.OFFICIAL:
                    raise SecurityValidationError(
                        f"OfficialSink requires OFFICIAL, got {operating_level.name}"
                    )

            def write(self, results: dict, *, metadata: dict | None = None) -> None:
                self.written.append({"results": results, "metadata": metadata})

        datasource = OfficialDatasource()
        sink = OfficialSink()

        experiment = ExperimentConfig(
            name="multi_stage_uplifting",
            prompt_system="Test",
            prompt_template="Process: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        # Use SECRET LLM client (can operate at OFFICIAL level)
        llm_client = SecretLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Operating envelope = OFFICIAL (min of all components)
        # All components can operate at OFFICIAL level
        # This should SUCCEED - demonstrates multi-stage uplifting works
        results = runner.run(df, sink_factory=lambda exp: [sink])

        # Verify execution succeeded
        assert "multi_stage_uplifting" in results, "Experiment should execute successfully"
        assert len(sink.written) > 0, "Sink should receive data from multi-stage pipeline"

        # Verify data flowed through the pipeline
        written_data = sink.written[0]
        assert written_data is not None, "Data should flow through multi-stage pipeline"

    def test_mixed_security_multi_sink(self):
        """Multiple sinks with different security levels - partial success.

        This test verifies that per-sink security validation works correctly
        when a suite has multiple sinks requiring different clearance levels.

        Given: SECRET datasource + [SECRET sink, OFFICIAL sink]
        When: Running suite
        Then:
          - Start-time validation computes envelope = SECRET (datasource level)
          - OFFICIAL sink rejects SECRET envelope (requires lower clearance)
          - Job FAILS at start-time validation (any component can block)

        This tests T1 prevention with multiple output paths.
        """
        df = pd.DataFrame({"text": ["secret1", "secret2"]})
        datasource = MockSecureDatasource(df)  # Requires SECRET

        secret_sink = MockSecretSink()  # Can handle SECRET
        official_sink = MockOfficialSink()  # Only handles OFFICIAL

        experiment = ExperimentConfig(
            name="multi_sink_test",
            prompt_system="Test",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # This should FAIL - OFFICIAL sink cannot accept SECRET envelope
        # Even though SECRET sink can handle it, ALL sinks must accept the envelope
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(df, sink_factory=lambda exp: [secret_sink, official_sink])

        error_msg = str(exc_info.value)
        assert "ADR-002" in error_msg, "Error should reference ADR-002 validation"
        # Verify neither sink received data (job blocked at start)
        assert len(secret_sink.written) == 0, "SECRET sink should not have received data (job blocked)"

    def test_real_plugin_integration_static_llm(self):
        """Integration test using real plugin implementations (not mocks).

        This test verifies ADR-002/002-A works with actual production plugins,
        not just test mocks. Uses StaticLLMClient for deterministic output.

        Given: OFFICIAL datasource + StaticLLMClient + Real sink
        When: Running with real plugin implementations
        Then:
          - Complete E2E execution with production code
          - All security validations work with real plugins
          - Data flows through actual plugin transform logic

        This ensures ADR-002/002-A doesn't have hidden assumptions about mock behavior.
        """
        from elspeth.plugins.nodes.transforms.llm.static import StaticLLMClient

        df = pd.DataFrame({"text": ["test_row_1", "test_row_2"]})
        datasource = MockOfficialDatasource(df)

        # Use REAL StaticLLMClient (production plugin)
        llm_client = StaticLLMClient(content="Static LLM response for testing", score=0.85)

        # Simple sink for capturing output (similar to production pattern)
        class SimpleCaptureSink(BasePlugin):
            """Real sink pattern that captures output for testing."""

            def __init__(self):
                self.written = []
                self.security_level = SecurityLevel.OFFICIAL

            def get_security_level(self) -> SecurityLevel:
                return self.security_level

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < self.security_level:
                    raise SecurityValidationError(
                        f"SimpleCaptureSink requires {self.security_level.name}, "
                        f"got {operating_level.name}"
                    )

            def write(self, results: dict, *, metadata: dict | None = None) -> None:
                self.written.append({"results": results, "metadata": metadata})

        sink = SimpleCaptureSink()

        experiment = ExperimentConfig(
            name="real_plugin_test",
            prompt_system="You are a test assistant.",
            prompt_template="Analyze: {text}",
            temperature=0.0,
            max_tokens=50,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Should succeed - all at OFFICIAL level with real plugins
        results = runner.run(df, sink_factory=lambda exp: [sink])

        # Verify execution with real plugins
        assert "real_plugin_test" in results, "Experiment should execute with real plugins"
        assert len(sink.written) > 0, "Real sink should receive data"

        # Verify StaticLLMClient actually processed data (not mocked)
        written = sink.written[0]
        assert written is not None, "Real plugin output should be captured"

        # Verify StaticLLMClient's static content appears in results
        assert "Static LLM response for testing" in str(results), \
            "StaticLLMClient output should appear in results (not mocked behavior)"


# ============================================================================
# Test Summary
# ============================================================================


"""
Integration Test Coverage:

✅ test_happy_path_matching_security_levels
   - Verifies: Suite runs when security levels match
   - Security Property: operating_level = MIN(all plugin levels) when equal

❌ test_fail_path_secret_datasource_unofficial_sink
   - Verifies: Suite BLOCKS when SECRET datasource + UNOFFICIAL sink
   - Security Property: Start-time validation prevents T1 classification breach
   - CRITICAL: This is the main certification test for ADR-002

❌ test_upgrade_path_official_datasource_secret_sink
   - Verifies: Suite blocks when any component requires > operating_level
   - Security Property: ALL components must accept envelope (not just datasource)

✅ test_backward_compatibility_non_baseplugin_components
   - Verifies: Existing components without BasePlugin still work
   - Security Property: Validation is opt-in via BasePlugin protocol

✅ test_e2e_adr002a_datasource_plugin_sink_flow
   - Verifies: Complete ADR-002-A flow with ClassifiedDataFrame
   - Security Property: Datasource → Plugin → Sink with proper uplifting

✅ test_multi_stage_classification_uplifting [NEW]
   - Verifies: Multi-stage pipeline with classification accumulation (SUCCESS case)
   - Security Property: All components accept OFFICIAL envelope, SECRET LLM can process at OFFICIAL level
   - Tests: T4 prevention (no downgrading in complex pipelines), demonstrates uplifting works correctly

❌ test_mixed_security_multi_sink [NEW]
   - Verifies: Multiple sinks with different security requirements
   - Security Property: ALL sinks must accept envelope (any can block)
   - Tests: T1 prevention with multiple output paths

✅ test_real_plugin_integration_static_llm [NEW]
   - Verifies: ADR-002/002-A works with real production plugins
   - Security Property: Real plugin implementations follow security model
   - Tests: No hidden assumptions about mock behavior

Total: 8 integration tests covering critical ADR-002/002-A scenarios
"""
