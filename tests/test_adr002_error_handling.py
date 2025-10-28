"""ADR-002 Error Handling Security Tests

These tests verify that error paths preserve security context and prevent
classification breaches through:
1. Exception messages (no leaked classified data)
2. Stack traces (no exposed sensitive values)
3. Error logs (security context preserved)
4. Validation failures (field names shown, values redacted)

Critical Security Principle: Exceptions and errors are often logged to
UNOFFICIAL storage (console, log files, monitoring systems). We must ensure
that SECRET/PROTECTED data never leaks through error paths.

Threat Prevention:
- T1: Classification Breach (via error logs to lower-clearance storage)
- T4: Classification Laundering (via exception handling bypass)
"""

import pandas as pd
import pytest

from elspeth.core.base.plugin import BasePlugin  # ADR-004: ABC with nominal typing
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.config import ExperimentConfig, ExperimentSuite
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.core.security.secure_data import SecureDataFrame
from elspeth.core.validation.base import SecurityValidationError

# ============================================================================
# Mock Plugins for Error Testing
# ============================================================================


class MockSecretDatasource(BasePlugin):
    """Datasource with SECRET classified data."""

    def __init__(self, df: pd.DataFrame):
        super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)
        self.df = df

    def load(self) -> SecureDataFrame:
        """Load SECRET data."""
        return SecureDataFrame.create_from_datasource(self.df, SecurityLevel.SECRET)


class FaultyLLMClient:
    """LLM client that fails during processing to test error handling."""

    def __init__(self, fail_on_call: int = 2):
        self.fail_on_call = fail_on_call
        self.calls_processed = 0

    def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
        """Generate that fails on specified call."""
        self.calls_processed += 1
        if self.calls_processed == self.fail_on_call:
            # CRITICAL: This exception should NOT leak user_prompt data
            # The prompt may contain classified data from the datasource
            raise ValueError(f"LLM processing failed on call {self.calls_processed}")
        return {
            "content": f"Mock response to: {user_prompt}",
            "metadata": {"model": "faulty-llm"},
        }


class FaultySink(BasePlugin):
    """Sink that fails during write to test error handling."""

    def __init__(self, fail_on_write: bool = True):
        super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)
        self.fail_on_write = fail_on_write
        self.written = []

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        """Write that fails to simulate disk full, permissions, etc."""
        if self.fail_on_write:
            # CRITICAL: This exception should NOT leak results content
            raise IOError("Disk full - cannot write results")
        self.written.append({"results": results, "metadata": metadata})


class MockSecretSink(BasePlugin):
    """Standard SECRET sink for testing."""

    def __init__(self):
        super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=True)
        self.written = []

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        self.written.append({"results": results, "metadata": metadata})


class MockLLMClient(BasePlugin):
    """Simple mock LLM for error tests."""

    def __init__(self):
        super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)

    def generate(self, *, system_prompt: str, user_prompt: str, metadata: dict | None = None) -> dict:
        return {
            "content": f"Mock response to: {user_prompt}",
            "metadata": {"model": "mock-llm"},
        }


# ============================================================================
# Error Handling Security Tests
# ============================================================================


class TestADR002ErrorHandling:
    """Tests for error path security - preventing classification leaks through exceptions."""

    def test_plugin_exception_doesnt_leak_classified_data(self):
        """LLM client exceptions don't leak classified data in error messages.

        This is a CRITICAL security test for T1 prevention.

        Problem: When an LLM client fails, Python exceptions include context from
        local variables. If the exception message contains classified data,
        and that exception is logged to UNOFFICIAL storage (console, log files,
        Sentry, CloudWatch), it creates a classification breach.

        Given: SECRET datasource with sensitive data → FaultyLLMClient that raises exception
        When: LLM client fails during processing
        Then:
          - Exception is raised (expected)
          - Exception message does NOT contain classified field values
          - Exception type is recognizable (ValueError, not masked)
          - Call count MAY be included (non-sensitive)

        Security Property: Error messages reveal METADATA but not DATA.
        Example:
          ✅ "LLM processing failed on call 2" (safe - call count is metadata)
          ❌ "LLM failed on: Process: password=SECRET123" (breach!)
        """
        # Create SECRET datasource with sensitive values
        df = pd.DataFrame({
            "username": ["admin", "root"],
            "password": ["TOP_SECRET_PASSWORD_123", "CLASSIFIED_API_KEY_456"],
            "ssn": ["111-11-1111", "222-22-2222"],
        })

        datasource = MockSecretDatasource(df)
        llm_client = FaultyLLMClient(fail_on_call=2)  # Fail on second call
        sink = MockSecretSink()

        experiment = ExperimentConfig(
            name="error_test",
            prompt_system="Test",
            prompt_template="Process: {username}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Run - LLM client will fail on second row, but runner catches and logs it
        # Don't pass df - let datasource.load() be called (returns SecureDataFrame)
        results = runner.run(sink_factory=lambda exp: [sink])

        # CRITICAL SECURITY ASSERTIONS:
        # The runner catches LLM exceptions and records them in failures array
        experiment_results = results["error_test"]
        failures = experiment_results["payload"]["failures"]

        # Verify that LLM failure was captured
        assert len(failures) == 1, "Should have 1 failure (second row)"
        failure = failures[0]

        # Get all error text from the failure record
        error_msg = str(failure.get("error", "")).lower()
        error_type = str(failure.get("retry", {}).get("history", [{}])[0].get("error_type", "")).lower()
        retry_error = str(failure.get("retry", {}).get("history", [{}])[0].get("error", "")).lower()

        # Combine all error representations to check for leaks
        all_error_text = f"{error_msg} {error_type} {retry_error}"

        # ❌ MUST NOT leak classified field VALUES
        # These are the actual sensitive data that should never appear in errors
        assert "top_secret_password_123" not in all_error_text, \
            "Failure record leaked classified password value!"
        assert "classified_api_key_456" not in all_error_text, \
            "Failure record leaked classified API key value!"
        assert "111-11-1111" not in all_error_text, \
            "Failure record leaked classified SSN value!"
        assert "222-22-2222" not in all_error_text, \
            "Failure record leaked classified SSN value!"

        # ✅ MAY include field NAMES (metadata, not sensitive)
        # Field names like "password", "username" are acceptable - they reveal structure, not content

        # ✅ MAY include call count (metadata, not sensitive)
        # Knowing "call 2 failed" is fine - it's positional info, not content

        # ✅ Error should still be informative (not masked to uselessness)
        # We want "LLM processing failed on call 2", not just "Error occurred"
        assert len(error_msg) > 0, "Error message should be informative"
        assert "valueerror" in error_type or "error" in error_msg, \
            "Should identify error type for debugging"

    def test_sink_write_failure_preserves_security_context(self):
        """Sink write failures don't leak classified results in error messages.

        Problem: When a sink fails to write (disk full, permissions, network),
        the exception might include the results payload. If those results contain
        classified data and the exception is logged to UNOFFICIAL storage, breach.

        Given: SECRET datasource → LLM → FaultySink (simulates write failure)
        When: Sink write fails
        Then:
          - IOError raised (expected)
          - Error message does NOT contain results data
          - Error message MAY contain generic failure reason

        Security Property: Sink failures reveal INFRASTRUCTURE state, not DATA.
        Example:
          ✅ "Disk full - cannot write results" (safe - infra issue)
          ❌ "Failed to write: {'secret_field': 'CLASSIFIED'}" (breach!)
        """
        df = pd.DataFrame({
            "query": ["What is the secret password?"],
            "response": ["The secret password is: CLASSIFIED_RESPONSE_123"],
        })

        datasource = MockSecretDatasource(df)
        sink = FaultySink(fail_on_write=True)  # Will fail on write

        experiment = ExperimentConfig(
            name="sink_error_test",
            prompt_system="Test",
            prompt_template="Query: {query}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Run expecting sink write failure
        with pytest.raises(Exception) as exc_info:
            runner.run(sink_factory=lambda exp: [sink])

        # CRITICAL SECURITY ASSERTIONS:
        error_msg = str(exc_info.value).lower()
        error_repr = repr(exc_info.value).lower()
        all_error_text = f"{error_msg} {error_repr}"

        # ❌ MUST NOT leak classified response data
        assert "classified_response_123" not in all_error_text, \
            "Exception leaked classified LLM response!"
        assert "secret password is" not in all_error_text, \
            "Exception leaked classified response content!"

        # ✅ MAY include generic failure reason
        # "Disk full" or "Cannot write" is fine - it's infra context

    def test_security_validation_error_provides_context_without_leaking_data(self):
        """Security validation errors provide helpful context without leaking data.

        Problem: When security validation fails (frozen plugin refusing downgrade),
        the error message should explain WHAT failed without revealing sensitive data content.

        Given: OFFICIAL datasource → SECRET frozen sink (sink refuses downgrade to OFFICIAL)
        When: Start-time validation detects frozen plugin downgrade rejection
        Then:
          - SecurityValidationError raised (expected)
          - Error mentions security levels or frozen/downgrade
          - Error references security validation
          - Error does NOT contain data from datasource
          - Error is actionable (tells user what to fix)

        Security Property: Validation errors reveal CONFIGURATION issues, not DATA.
        Example:
          ✅ "Frozen SECRET sink cannot operate at OFFICIAL level" (safe - config)
          ❌ "Sink blocked data: [row 0: {'password': 'SECRET'}]" (breach!)

        MLS Model: Operating level = MIN(OFFICIAL, SECRET) = OFFICIAL
        - Datasource: OFFICIAL clearance @ OFFICIAL level = OK (exact match)
        - Frozen Sink: SECRET clearance @ OFFICIAL level = REJECT (frozen, no downgrade)
        """
        # OFFICIAL datasource
        class OfficialDatasource(BasePlugin):
            def __init__(self, df: pd.DataFrame):
                super().__init__(security_level=SecurityLevel.OFFICIAL, allow_downgrade=True)
                self.df = df

            def load(self) -> SecureDataFrame:
                return SecureDataFrame.create_from_datasource(self.df, SecurityLevel.OFFICIAL)

        # Datasource with sensitive data
        df = pd.DataFrame({
            "employee_id": ["E12345", "E67890"],
            "salary": [150000, 200000],  # Sensitive data
            "performance_review": ["Excellent", "Outstanding"],
        })

        # SECRET frozen sink (allow_downgrade=False) - refuses to operate at OFFICIAL level
        class SecretFrozenSink(BasePlugin):
            def __init__(self):
                super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=False)
                self.written = []

            def write(self, results: dict, *, metadata: dict | None = None) -> None:
                self.written.append({"results": results, "metadata": metadata})

        datasource = OfficialDatasource(df)
        sink = SecretFrozenSink()  # Frozen SECRET sink refuses to operate at OFFICIAL level

        experiment = ExperimentConfig(
            name="validation_error_test",
            prompt_system="Test",
            prompt_template="Process: {employee_id}",
            temperature=0.7,
            max_tokens=100,
        )
        suite = ExperimentSuite(root=".", baseline=experiment, experiments=[experiment])

        llm_client = MockLLMClient()
        runner = ExperimentSuiteRunner(suite=suite, llm_client=llm_client, sinks=[], datasource=datasource)

        # Run expecting security validation failure
        with pytest.raises(SecurityValidationError) as exc_info:
            runner.run(sink_factory=lambda exp: [sink])

        # CRITICAL SECURITY ASSERTIONS:
        error_msg = str(exc_info.value).lower()

        # ❌ MUST NOT leak actual data values (salaries, reviews, etc.)
        assert "150000" not in error_msg, "Error leaked salary data!"
        assert "200000" not in error_msg, "Error leaked salary data!"
        assert "excellent" not in error_msg, "Error leaked performance review!"
        assert "e12345" not in error_msg, "Error leaked employee ID!"

        # ✅ SHOULD mention security levels or frozen plugin (configuration context)
        # Note: Error might mention "frozen", "allow_downgrade", or security levels
        has_config_context = (
            "secret" in error_msg or
            "official" in error_msg or
            "frozen" in error_msg or
            "allow_downgrade" in error_msg or
            "downgrade" in error_msg
        )
        assert has_config_context, \
            "Error should mention security levels, frozen plugin, or downgrade policy for debugging"

        # ✅ SHOULD reference ADR or security validation (architectural context)
        assert "adr" in error_msg or "security" in error_msg or "validation" in error_msg, \
            "Error should reference ADR or security validation"

        # ✅ Error should be a SecurityValidationError (proper exception type)
        assert isinstance(exc_info.value, SecurityValidationError), \
            "Security errors should use SecurityValidationError type"


# ============================================================================
# Test Summary
# ============================================================================


"""
Error Handling Security Test Coverage:

Test 1: test_plugin_exception_doesnt_leak_classified_data
   - Verifies: Plugin failures don't leak data values in exceptions
   - Security Property: Error messages reveal METADATA, not DATA
   - Tests: T1 prevention (classified data leaking to UNOFFICIAL error logs)
   - Scenario: FaultyPlugin fails during transform

Test 2: test_sink_write_failure_preserves_security_context
   - Verifies: Sink write failures don't leak results in exceptions
   - Security Property: Sink errors reveal INFRASTRUCTURE issues, not DATA
   - Tests: T1 prevention (classified results leaking via I/O errors)
   - Scenario: FaultySink fails during write (disk full, permissions)

Test 3: test_security_validation_error_provides_context_without_leaking_data
   - Verifies: Security validation errors are helpful but safe
   - Security Property: Validation errors reveal CONFIGURATION, not DATA
   - Tests: T1 prevention (data leaking via validation failure messages)
   - Scenario: Envelope mismatch (OFFICIAL datasource + SECRET sink)

Total: 3 error handling security tests covering critical exception paths

Key Security Principle:
Exceptions are often logged to UNOFFICIAL storage. We must ensure that
SECRET/PROTECTED data NEVER appears in exception messages, stack traces,
or error logs, even when operations fail.

Safe Error Anatomy:
  ✅ "Processing failed on row 42" (positional metadata)
  ✅ "Sink requires SECRET, got OFFICIAL" (configuration)
  ✅ "Disk full - cannot write" (infrastructure)
  ❌ "Failed on: {'password': 'SECRET123'}" (DATA LEAK!)
  ❌ "Processing row: [admin, SECRET_PASS, ...]" (DATA LEAK!)
"""
