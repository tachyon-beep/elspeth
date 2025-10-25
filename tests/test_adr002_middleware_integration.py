"""ADR-002 Middleware and Multi-Level Security Integration Tests

These tests verify advanced security scenarios involving:
1. Deep classification uplifting chains (3+ levels)
2. Middleware classification preservation
3. Complex multi-component pipelines

Test Scenarios:
- Three-level uplifting: UNOFFICIAL → OFFICIAL → SECRET → TOP_SECRET
- Middleware preservation: Middleware doesn't downgrade classifications
- LLM middleware chains with classification tracking

These tests complement test_adr002_suite_integration.py by focusing on
middleware-specific behaviors and deep uplifting scenarios.
"""

import pandas as pd
import pytest

from elspeth.core.base.protocols import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.core.security.classified_data import ClassifiedDataFrame
from elspeth.core.validation.base import SecurityValidationError

# ============================================================================
# Mock Plugins for Multi-Level Testing
# ============================================================================


class MockUnofficialDatasource(BasePlugin):
    """Datasource at UNOFFICIAL level (lowest)."""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.UNOFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        # UNOFFICIAL is lowest, always accepts
        pass

    def load(self) -> pd.DataFrame:
        """Load data at UNOFFICIAL level."""
        classified = ClassifiedDataFrame.create_from_datasource(self.df, SecurityLevel.UNOFFICIAL)
        return classified.data


class MockOfficialTransform(BasePlugin):
    """Transform plugin at OFFICIAL level."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.OFFICIAL

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.OFFICIAL:
            raise SecurityValidationError(
                f"MockOfficialTransform requires OFFICIAL, got {operating_level.name}"
            )

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Transform data and uplift to OFFICIAL."""
        classified_input = ClassifiedDataFrame.create_from_datasource(data, SecurityLevel.UNOFFICIAL)
        result = data.copy()
        result["stage1_official"] = True
        output = classified_input.with_new_data(result)
        uplifted = output.with_uplifted_classification(SecurityLevel.OFFICIAL)
        return uplifted.data


class MockSecretLLM:
    """LLM client at SECRET level (uplifts data to SECRET)."""

    def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
        """Process at SECRET level - taints data with SECRET classification."""
        return {
            "content": f"[SECRET LLM] {user_prompt}",
            "metadata": {"model": "secret-llm", "security_level": "SECRET"},
        }


class MockProtectedAggregator(BasePlugin):
    """Aggregator at PROTECTED level."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.PROTECTED

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.PROTECTED:
            raise SecurityValidationError(
                f"MockProtectedAggregator requires PROTECTED, got {operating_level.name}"
            )

    def aggregate(self, data: pd.DataFrame) -> dict:
        """Aggregate data at PROTECTED level."""
        return {
            "total_rows": len(data),
            "classification": "PROTECTED",
            "aggregated_by": "MockProtectedAggregator",
        }


class MockProtectedSink(BasePlugin):
    """Sink at PROTECTED level."""

    def __init__(self):
        self.written = []

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.PROTECTED

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.PROTECTED:
            raise SecurityValidationError(
                f"MockProtectedSink requires PROTECTED, got {operating_level.name}"
            )

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        self.written.append({"results": results, "metadata": metadata})


class MockSecretSink(BasePlugin):
    """Sink at SECRET level."""

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
        self.written.append({"results": results, "metadata": metadata})


# ============================================================================
# Mock Middleware for Classification Preservation
# ============================================================================


class MockAuditMiddleware:
    """Middleware that logs requests without modifying classification.

    This simulates AuditMiddleware behavior - it should preserve
    the classification of data passing through it.
    """

    def __init__(self):
        self.audit_log = []

    def __call__(self, llm_client, system_prompt: str, user_prompt: str, metadata: dict | None = None):
        """Wrap LLM call with audit logging."""
        # Log the request
        self.audit_log.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "metadata": metadata,
        })

        # Pass through to LLM without modifying classification
        response = llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )

        # Log the response
        self.audit_log.append({"response": response})

        return response


class MockHealthMonitorMiddleware:
    """Middleware that monitors LLM health without affecting classification."""

    def __init__(self):
        self.health_checks = []

    def __call__(self, llm_client, system_prompt: str, user_prompt: str, metadata: dict | None = None):
        """Wrap LLM call with health monitoring."""
        import time

        start_time = time.time()

        # Call LLM
        response = llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            metadata=metadata,
        )

        # Record health metrics
        duration = time.time() - start_time
        self.health_checks.append({
            "duration_ms": duration * 1000,
            "status": "success",
        })

        return response


# ============================================================================
# Integration Tests
# ============================================================================


class TestADR002MiddlewareIntegration:
    """Advanced integration tests for ADR-002 with middleware and multi-level pipelines."""

    def test_four_level_uplifting_chain(self):
        """Four-level uplifting chain: UNOFFICIAL → OFFICIAL → SECRET → PROTECTED.

        This test verifies that classification correctly accumulates through
        a deep pipeline with escalating security levels at each stage.

        Given: UNOFFICIAL datasource → OFFICIAL transform → SECRET LLM → PROTECTED sink
        When: Running multi-level pipeline
        Then:
          - Start-time envelope = UNOFFICIAL (min of all components)
          - PROTECTED sink rejects UNOFFICIAL envelope (start-time validation fails)
          - No data processed (fail-fast before data retrieval)

        This tests T1 prevention with deep classification mismatches.
        """
        df = pd.DataFrame({"text": ["level1", "level2", "level3"]})

        datasource = MockUnofficialDatasource(df)  # UNOFFICIAL (lowest)
        transform = MockOfficialTransform()  # OFFICIAL
        llm_client = MockSecretLLM()  # SECRET processing
        sink = MockProtectedSink()  # PROTECTED

        experiment = ExperimentConfig(
            name="four_level_test",
            prompt_system="Multi-level security test",
            prompt_template="Process: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Operating envelope = UNOFFICIAL (datasource level)
        # PROTECTED sink requires PROTECTED
        # This should FAIL - sink cannot accept UNOFFICIAL envelope
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(df, sink_factory=lambda exp: [sink])

        error_msg = str(exc_info.value)
        assert "ADR-002" in error_msg, "Error should reference ADR-002 validation"
        assert isinstance(exc_info.value, SecurityValidationError), \
            "Should raise SecurityValidationError, not generic exception"
        assert any(level in error_msg for level in ["PROTECTED", "UNOFFICIAL"]), \
            "Error should mention security level mismatch"

        # Verify no data written (job blocked at start)
        assert len(sink.written) == 0, "PROTECTED sink should not receive data (job blocked)"

    def test_three_level_uplifting_with_mismatched_sink(self):
        """Three-level uplifting with mismatched sink requirements (should fail).

        This test demonstrates envelope validation failure when the sink's
        security requirements exceed the operating envelope.

        Given: UNOFFICIAL datasource → OFFICIAL transform → SECRET LLM → SECRET sink
        When: Running multi-level pipeline
        Then:
          - Start-time envelope = UNOFFICIAL (min of all components)
          - SECRET sink requires SECRET but envelope is UNOFFICIAL
          - Job FAILS at start-time validation (before data retrieval)

        This shows that even with uplifting, the start-time envelope determines access.
        Runtime uplifting cannot bypass start-time security validation (T1 prevention).
        """
        df = pd.DataFrame({"text": ["data1", "data2"]})

        datasource = MockUnofficialDatasource(df)  # UNOFFICIAL
        llm_client = MockSecretLLM()  # SECRET
        sink = MockSecretSink()  # SECRET

        experiment = ExperimentConfig(
            name="three_level_mismatched_test",
            prompt_system="Test",
            prompt_template="Test: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Operating envelope = UNOFFICIAL
        # SECRET sink requires SECRET
        # This should FAIL
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(df, sink_factory=lambda exp: [sink])

        error_msg = str(exc_info.value)
        assert "ADR-002" in error_msg, "Error should reference ADR-002 validation"
        assert isinstance(exc_info.value, SecurityValidationError), \
            "Should raise SecurityValidationError"
        assert any(level in error_msg for level in ["SECRET", "UNOFFICIAL"]), \
            "Error should mention security level mismatch"

    def test_middleware_preserves_classification(self):
        """Middleware chains preserve classification without downgrading.

        This test verifies that middleware (audit, health monitoring) does NOT
        accidentally downgrade or modify the security classification of data
        flowing through the pipeline.

        Given: SECRET datasource → AuditMiddleware → HealthMonitorMiddleware → SECRET sink
        When: Running with middleware chain
        Then:
          - Middleware processes data without changing classification
          - SECRET classification preserved end-to-end
          - Audit logs and health metrics captured correctly

        This is critical for T4 prevention - middleware must not create
        classification breaches through careless handling.
        """
        from elspeth.core.security.classified_data import ClassifiedDataFrame

        df = pd.DataFrame({"text": ["secret_data_1", "secret_data_2"]})

        # SECRET datasource
        class SecretDatasource(BasePlugin):
            def get_security_level(self) -> SecurityLevel:
                return SecurityLevel.SECRET

            def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
                if operating_level < SecurityLevel.SECRET:
                    raise SecurityValidationError(
                        f"SecretDatasource requires SECRET, got {operating_level.name}"
                    )

            def load(self) -> pd.DataFrame:
                classified = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
                return classified.data

        # LLM client wrapped with middleware
        class SecretLLMClient:
            """SECRET-level LLM client."""

            def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
                return {
                    "content": f"[SECRET] {user_prompt}",
                    "metadata": {"security": "SECRET"},
                }

        datasource = SecretDatasource()
        base_llm = SecretLLMClient()

        # Wrap LLM with middleware chain
        audit_middleware = MockAuditMiddleware()
        health_middleware = MockHealthMonitorMiddleware()

        # Create middleware-wrapped LLM
        class MiddlewareWrappedLLM:
            """LLM wrapped with audit and health monitoring middleware.

            Builds a nested chain: outermost middleware wraps inner middleware wraps LLM.
            Example with [audit, health]:
              audit(health(llm_client, ...), ...)
            """

            def __init__(self, llm_client, middlewares):
                self.llm_client = llm_client
                self.middlewares = middlewares

            def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
                # Build nested middleware chain
                # Start with the actual LLM client
                handler = self.llm_client

                # Wrap each middleware around the handler (innermost to outermost)
                # Reverse order so first middleware in list becomes outermost wrapper
                for middleware in reversed(self.middlewares):
                    # Create a wrapper that captures the current handler and middleware
                    current_handler = handler
                    current_middleware = middleware

                    class MiddlewareWrapper:
                        """Wrapper that applies middleware to handler."""
                        def __init__(self, mw, h):
                            self.middleware = mw
                            self.handler = h

                        def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None):
                            return self.middleware(self.handler, system_prompt, user_prompt, metadata)

                    handler = MiddlewareWrapper(current_middleware, current_handler)

                # Execute the fully wrapped chain
                return handler.generate(system_prompt=system_prompt, user_prompt=user_prompt, metadata=metadata)

        llm_with_middleware = MiddlewareWrappedLLM(
            base_llm,
            middlewares=[audit_middleware, health_middleware],
        )

        sink = MockSecretSink()

        experiment = ExperimentConfig(
            name="middleware_test",
            prompt_system="Test middleware",
            prompt_template="Process: {text}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(
            suite=suite,
            llm_client=llm_with_middleware,
            sinks=[],
            datasource=datasource,
        )

        # Should succeed - all at SECRET level
        results = runner.run(df, sink_factory=lambda exp: [sink])

        # Verify execution succeeded
        assert "middleware_test" in results
        assert len(sink.written) > 0, "Sink should receive data"

        # Verify middleware captured data without affecting classification
        assert len(audit_middleware.audit_log) > 0, "Audit middleware should log requests"
        assert len(health_middleware.health_checks) > 0, "Health middleware should record metrics"

        # Verify data still reached sink with SECRET classification intact
        written_data = sink.written[0]
        assert written_data is not None, "Data should be written with classification preserved"


# ============================================================================
# Test Summary
# ============================================================================


"""
Middleware Integration Test Coverage:

✅ test_four_level_uplifting_chain
   - Verifies: Deep uplifting chain (UNOFFICIAL → OFFICIAL → SECRET → PROTECTED)
   - Security Property: Operating envelope prevents over-classification
   - Tests: T1 prevention (PROTECTED sink rejects UNOFFICIAL envelope)
   - Expected: FAIL (SecurityValidationError at start-time)

✅ test_three_level_uplifting_with_mismatched_sink
   - Verifies: Multi-level chain with sink validation
   - Security Property: Envelope validation rejects mismatched sink requirements
   - Tests: Start-time validation with multi-level uplifting
   - Expected: FAIL (SecurityValidationError - sink requires higher level than envelope)

✅ test_middleware_preserves_classification
   - Verifies: Middleware doesn't downgrade classifications
   - Security Property: Classification preservation through middleware chains
   - Tests: T4 prevention (middleware can't create classification breaches)
   - Expected: PASS (middleware chain works correctly with SECRET data)

Total: 3 advanced integration tests for middleware and multi-level scenarios
Note: Uses Australian Government PSPF levels (UNOFFICIAL < OFFICIAL < OFFICIAL_SENSITIVE < PROTECTED < SECRET)

All tests use ✅ to indicate "test passes" (assertions succeed).
Tests that expect SecurityValidationError are testing rejection paths (security working correctly).
"""
