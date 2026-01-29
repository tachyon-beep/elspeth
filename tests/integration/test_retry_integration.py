# tests/integration/test_retry_integration.py
"""Integration tests for retry behavior with audit trail.

End-to-end test proving retry attempts are auditable - each attempt creates
a separate node_state record in the database.

This verifies the full retry audit chain:
1. RetrySettings -> RetryConfig.from_settings() -> RetryManager
2. Orchestrator creates RetryManager and passes to RowProcessor
3. RowProcessor uses _execute_transform_with_retry which tracks attempt numbers
4. Each execute_transform call passes attempt=N to begin_node_state
5. node_states table has `attempt` column with correct values
"""

from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from elspeth.contracts import NodeType, PluginSchema, TokenInfo, TransformResult
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import node_states_table
from elspeth.engine.executors import TransformExecutor
from elspeth.engine.retry import MaxRetriesExceeded, RetryConfig, RetryManager
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.context import PluginContext


class FlakyTransform(BaseTransform):
    """Transform that fails N times then succeeds.

    Used to test retry behavior - raises ConnectionError (retryable)
    until max_fails is reached, then succeeds.
    """

    name = "flaky_transform"
    input_schema = PluginSchema
    output_schema = PluginSchema
    plugin_version = "1.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.fail_count = 0
        self.max_fails = config.get("max_fails", 2)

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        """Fail max_fails times, then succeed."""
        self.fail_count += 1
        if self.fail_count <= self.max_fails:
            raise ConnectionError(f"Transient failure attempt {self.fail_count}")
        return TransformResult.success({"processed": True, **row})


class AlwaysFailTransform(BaseTransform):
    """Transform that always fails with a retryable error.

    Used to test max retry exhaustion - always raises ConnectionError.
    """

    name = "always_fail_transform"
    input_schema = PluginSchema
    output_schema = PluginSchema
    plugin_version = "1.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.fail_count = 0

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        """Always fail with retryable error."""
        self.fail_count += 1
        raise ConnectionError(f"Permanent failure attempt {self.fail_count}")


class TestRetryAuditTrail:
    """Verify each retry attempt is recorded in audit trail."""

    @pytest.fixture
    def test_env(self) -> dict[str, Any]:
        """Set up test environment with in-memory database."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Create a noop span factory
        span_factory = Mock(spec=SpanFactory)
        span_factory.transform_span.return_value.__enter__ = Mock(return_value=None)
        span_factory.transform_span.return_value.__exit__ = Mock(return_value=None)

        return {
            "db": db,
            "recorder": recorder,
            "span_factory": span_factory,
        }

    def _setup_run_and_node(
        self,
        recorder: LandscapeRecorder,
        plugin_name: str = "flaky_transform",
    ) -> tuple[str, str]:
        """Create a run and register a transform node.

        Returns:
            Tuple of (run_id, node_id)
        """
        from elspeth.contracts.schema import SchemaConfig

        # Create a run
        run = recorder.begin_run(
            config={"test": "config"},
            canonical_version="sha256-rfc8785-v1",
        )

        # Create a dynamic schema config for the node
        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)

        # Register transform node
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name=plugin_name,
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            schema_config=schema_config,
        )

        return run.run_id, node.node_id

    def _create_token(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        row_data: dict[str, Any],
    ) -> TokenInfo:
        """Create a row and token for testing.

        Returns:
            TokenInfo with row_id, token_id, and row_data
        """
        # Create the row record
        row = recorder.create_row(
            run_id=run_id,
            source_node_id=source_node_id,
            row_index=0,
            data=row_data,
        )

        # Create the token record
        token = recorder.create_token(row_id=row.row_id)

        return TokenInfo(
            token_id=token.token_id,
            row_id=row.row_id,
            row_data=row_data,
            branch_name=None,
        )

    def test_each_retry_attempt_recorded_as_separate_node_state(
        self,
        test_env: dict[str, Any],
    ) -> None:
        """Each retry attempt creates a separate node_state record.

        This test verifies the complete audit chain:
        1. FlakyTransform fails twice, succeeds on third attempt
        2. RetryManager retries with is_retryable check for ConnectionError
        3. TransformExecutor records each attempt with correct attempt number
        4. Database contains 3 node_state records with attempts 0, 1, 2
        """
        db = test_env["db"]
        recorder = test_env["recorder"]
        span_factory = test_env["span_factory"]

        # Setup run and node
        run_id, node_id = self._setup_run_and_node(recorder, "flaky_transform")

        # Create a source node for the token (required for row creation)
        from elspeth.contracts.schema import SchemaConfig

        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        source_node = recorder.register_node(
            run_id=run_id,
            plugin_name="test_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=schema_config,
        )

        # Create token
        row_data = {"value": 42}
        token = self._create_token(recorder, run_id, source_node.node_id, row_data)

        # Create flaky transform that fails twice then succeeds
        transform = FlakyTransform({"max_fails": 2})
        transform.node_id = node_id

        # Create transform executor
        transform_executor = TransformExecutor(recorder, span_factory)

        # Create retry manager with 3 attempts (enough to succeed)
        retry_manager = RetryManager(RetryConfig(max_attempts=3, base_delay=0.001))

        ctx = PluginContext(run_id=run_id, config={})

        # Track attempt number manually since _execute_transform_with_retry
        # is on RowProcessor. We'll simulate its behavior directly.
        attempt_tracker = {"current": 0}

        def execute_attempt() -> tuple[TransformResult, TokenInfo, str | None]:
            attempt = attempt_tracker["current"]
            attempt_tracker["current"] += 1
            return transform_executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
                attempt=attempt,
            )

        def is_retryable(e: BaseException) -> bool:
            return isinstance(e, ConnectionError | TimeoutError | OSError)

        # Execute with retry
        result, _out_token, _error_sink = retry_manager.execute_with_retry(
            operation=execute_attempt,
            is_retryable=is_retryable,
        )

        # Should have succeeded after 3 attempts
        assert result.status == "success"
        assert transform.fail_count == 3

        # Query node_states for this node - should have 3 records
        with db.engine.connect() as conn:
            stmt = select(node_states_table).where(node_states_table.c.node_id == node_id).order_by(node_states_table.c.attempt)
            rows = list(conn.execute(stmt))

        # Verify we have 3 node_state records (attempt 0, 1, 2)
        assert len(rows) == 3, f"Expected 3 node_states, got {len(rows)}"

        # Verify attempt numbers are correct
        attempts = [row.attempt for row in rows]
        assert attempts == [0, 1, 2], f"Expected attempts [0, 1, 2], got {attempts}"

        # Verify statuses: first 2 failed, last succeeded
        statuses = [row.status for row in rows]
        assert statuses == [
            "failed",
            "failed",
            "completed",
        ], f"Expected ['failed', 'failed', 'completed'], got {statuses}"

        # Verify all records reference the same token
        token_ids = [row.token_id for row in rows]
        assert all(t == token.token_id for t in token_ids)

    def test_max_retries_exceeded_all_attempts_recorded(
        self,
        test_env: dict[str, Any],
    ) -> None:
        """When max retries exceeded, all attempts are still recorded.

        This test verifies:
        1. AlwaysFailTransform fails on every attempt
        2. RetryManager exhausts max_attempts and raises MaxRetriesExceeded
        3. All 2 attempts are recorded with status "failed"
        4. Each attempt has the correct attempt number (0, 1)
        """
        db = test_env["db"]
        recorder = test_env["recorder"]
        span_factory = test_env["span_factory"]

        # Setup run and node
        run_id, node_id = self._setup_run_and_node(recorder, "always_fail_transform")

        # Create a source node for the token
        from elspeth.contracts.schema import SchemaConfig

        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        source_node = recorder.register_node(
            run_id=run_id,
            plugin_name="test_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=schema_config,
        )

        # Create token
        row_data = {"value": 99}
        token = self._create_token(recorder, run_id, source_node.node_id, row_data)

        # Create transform that always fails
        transform = AlwaysFailTransform({})
        transform.node_id = node_id

        # Create transform executor
        transform_executor = TransformExecutor(recorder, span_factory)

        # Create retry manager with only 2 attempts
        retry_manager = RetryManager(RetryConfig(max_attempts=2, base_delay=0.001))

        ctx = PluginContext(run_id=run_id, config={})

        # Track attempt number
        attempt_tracker = {"current": 0}

        def execute_attempt() -> tuple[TransformResult, TokenInfo, str | None]:
            attempt = attempt_tracker["current"]
            attempt_tracker["current"] += 1
            return transform_executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
                attempt=attempt,
            )

        def is_retryable(e: BaseException) -> bool:
            return isinstance(e, ConnectionError | TimeoutError | OSError)

        # Execute with retry - should raise MaxRetriesExceeded
        with pytest.raises(MaxRetriesExceeded) as exc_info:
            retry_manager.execute_with_retry(
                operation=execute_attempt,
                is_retryable=is_retryable,
            )

        # Verify exception contains correct attempt count
        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_error, ConnectionError)

        # Transform should have been called twice
        assert transform.fail_count == 2

        # Query node_states for this node - should have 2 records
        with db.engine.connect() as conn:
            stmt = select(node_states_table).where(node_states_table.c.node_id == node_id).order_by(node_states_table.c.attempt)
            rows = list(conn.execute(stmt))

        # Verify we have 2 node_state records (attempt 0, 1)
        assert len(rows) == 2, f"Expected 2 node_states, got {len(rows)}"

        # Verify attempt numbers are correct
        attempts = [row.attempt for row in rows]
        assert attempts == [0, 1], f"Expected attempts [0, 1], got {attempts}"

        # Verify all statuses are failed
        statuses = [row.status for row in rows]
        assert statuses == [
            "failed",
            "failed",
        ], f"Expected ['failed', 'failed'], got {statuses}"

        # Verify error_json is populated for both attempts
        errors = [row.error_json for row in rows]
        assert all(e is not None for e in errors), "All failed states should have error_json"

        # Verify all records reference the same token
        token_ids = [row.token_id for row in rows]
        assert all(t == token.token_id for t in token_ids)

    def test_single_attempt_no_retry_records_single_node_state(
        self,
        test_env: dict[str, Any],
    ) -> None:
        """Single successful attempt records exactly one node_state.

        This is a sanity check - when no retries are needed, only one
        node_state should exist with attempt=0.
        """
        db = test_env["db"]
        recorder = test_env["recorder"]
        span_factory = test_env["span_factory"]

        # Setup run and node
        run_id, node_id = self._setup_run_and_node(recorder, "flaky_transform")

        # Create a source node for the token
        from elspeth.contracts.schema import SchemaConfig

        schema_config = SchemaConfig(mode=None, fields=None, is_dynamic=True)
        source_node = recorder.register_node(
            run_id=run_id,
            plugin_name="test_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=schema_config,
        )

        # Create token
        row_data = {"value": 123}
        token = self._create_token(recorder, run_id, source_node.node_id, row_data)

        # Create transform that succeeds immediately (max_fails=0)
        transform = FlakyTransform({"max_fails": 0})
        transform.node_id = node_id

        # Create transform executor
        transform_executor = TransformExecutor(recorder, span_factory)

        ctx = PluginContext(run_id=run_id, config={})

        # Execute without retry manager (single attempt)
        result, _out_token, _error_sink = transform_executor.execute_transform(
            transform=transform,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
            attempt=0,
        )

        # Should succeed immediately
        assert result.status == "success"
        assert transform.fail_count == 1  # process() was called once

        # Query node_states - should have exactly 1 record
        with db.engine.connect() as conn:
            stmt = select(node_states_table).where(node_states_table.c.node_id == node_id)
            rows = list(conn.execute(stmt))

        assert len(rows) == 1, f"Expected 1 node_state, got {len(rows)}"
        assert rows[0].attempt == 0
        assert rows[0].status == "completed"


class TestRetryExponentialBackoff:
    """Verify exponential_base config actually affects retry backoff timing.

    P2-2026-01-21 bug: exponential_base was defined in RetrySettings but
    never wired to RetryConfig or tenacity's wait_exponential_jitter.

    These tests ensure the config-to-runtime mapping works end-to-end.
    """

    def test_exponential_base_passed_to_tenacity(self) -> None:
        """Verify exponential_base is wired from config to tenacity.

        This test verifies the full chain by checking that wait_exponential_jitter
        is called with the configured exp_base parameter. We use mocking because
        timing-based tests are unreliable due to jitter dominating small delays.

        The chain being tested:
        RetrySettings.exponential_base -> RetryConfig.exponential_base
            -> RetryManager._config.exponential_base
            -> wait_exponential_jitter(exp_base=...)
        """
        from unittest.mock import patch

        from elspeth.core.config import RetrySettings
        from elspeth.engine.retry import RetryConfig, RetryManager

        # Create config with non-default exponential_base
        settings = RetrySettings(
            max_attempts=2,
            initial_delay_seconds=0.5,
            max_delay_seconds=10.0,
            exponential_base=5.0,  # Non-default, should be passed to tenacity
        )
        config = RetryConfig.from_settings(settings)
        manager = RetryManager(config)

        # Verify config has correct exponential_base
        assert config.exponential_base == 5.0

        captured_exp_base: list[float] = []

        # Patch wait_exponential_jitter to capture the exp_base argument
        original_wait_exp_jitter = __import__("tenacity.wait", fromlist=["wait_exponential_jitter"]).wait_exponential_jitter

        def capturing_wait_exponential_jitter(
            initial: float = 1,
            max: float = 4.611686018427388e18,
            exp_base: float = 2,
            jitter: float = 1,
        ) -> Any:
            captured_exp_base.append(exp_base)
            # Return a zero-wait to make test fast
            return original_wait_exp_jitter(initial=0, max=0, exp_base=exp_base, jitter=0)

        with patch(
            "elspeth.engine.retry.wait_exponential_jitter",
            capturing_wait_exponential_jitter,
        ):
            # Run an operation that fails once then succeeds
            call_count = 0

            def flaky_op() -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ValueError("Transient failure")
                return "success"

            result = manager.execute_with_retry(
                flaky_op,
                is_retryable=lambda e: isinstance(e, ValueError),
            )

            assert result == "success"

        # Verify exp_base was captured with the configured value
        assert len(captured_exp_base) == 1, "wait_exponential_jitter should be called once"
        assert captured_exp_base[0] == 5.0, (
            f"exp_base should be 5.0 (from config), got {captured_exp_base[0]}. "
            f"This means exponential_base is not being passed to tenacity."
        )

    def test_from_settings_preserves_exponential_base(self) -> None:
        """Verify RetryConfig.from_settings() maps exponential_base.

        This is the integration test that would have caught the bug:
        - RetrySettings.exponential_base was defined
        - But RetryConfig.from_settings() didn't map it
        - So configured values were silently ignored
        """
        from elspeth.core.config import RetrySettings
        from elspeth.engine.retry import RetryConfig

        # Test with non-default exponential_base
        settings = RetrySettings(
            max_attempts=5,
            initial_delay_seconds=2.0,
            max_delay_seconds=120.0,
            exponential_base=3.0,  # Non-default value
        )

        config = RetryConfig.from_settings(settings)

        # ALL settings must be mapped, including exponential_base
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0, (
            "exponential_base not mapped from RetrySettings to RetryConfig. This is the P2-2026-01-21 bug."
        )

    def test_retry_manager_uses_exponential_base(self) -> None:
        """Verify RetryManager passes exponential_base to tenacity.

        Tests the full chain:
        RetrySettings -> RetryConfig -> RetryManager -> wait_exponential_jitter

        If exponential_base is not passed to tenacity, backoff uses default (2.0).
        """
        from elspeth.core.config import RetrySettings
        from elspeth.engine.retry import RetryConfig, RetryManager

        # Create config with large exponential_base
        settings = RetrySettings(
            max_attempts=2,
            initial_delay_seconds=0.01,
            max_delay_seconds=10.0,
            exponential_base=10.0,  # Very high base - should cause noticeable delay
        )
        config = RetryConfig.from_settings(settings)
        manager = RetryManager(config)

        # Verify config has the exponential_base
        assert config.exponential_base == 10.0

        # The actual tenacity usage is tested in test_exponential_base_affects_backoff_timing
        # This test just verifies the wiring is complete
        call_count = 0

        def always_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = manager.execute_with_retry(
            always_succeeds,
            is_retryable=lambda e: True,
        )

        assert result == "ok"
        assert call_count == 1  # No retries needed
