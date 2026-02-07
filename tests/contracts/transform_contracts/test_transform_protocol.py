# tests/contracts/transform_contracts/test_transform_protocol.py
"""Contract tests for Transform plugins.

These tests verify that transform implementations honor the TransformProtocol contract.
They test interface guarantees, not implementation details.

Contract guarantees verified:
1. process() MUST return TransformResult
2. Success results MUST have output data (row or rows)
3. Error results MUST have reason dict
4. close() MUST be idempotent
5. Lifecycle hooks on_start/on_complete MUST not raise

Usage:
    Create a subclass with fixtures providing:
    - transform: The transform plugin instance
    - valid_input: A dict that should process successfully
    - ctx: A PluginContext for the test

    class TestMyTransformContract(TransformContractTestBase):
        @pytest.fixture
        def transform(self):
            return MyTransform({"config": "value"})

        @pytest.fixture
        def valid_input(self):
            return {"field": "value"}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from elspeth.contracts import Determinism, PluginSchema, TransformResult
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.testing import make_pipeline_row

if TYPE_CHECKING:
    from elspeth.plugins.protocols import TransformProtocol


class TransformContractTestBase(ABC):
    """Abstract base class for transform contract verification.

    Subclasses must provide fixtures for:
    - transform: The transform plugin instance to test
    - valid_input: A row dict that should process successfully
    - ctx: A PluginContext for the test
    """

    @pytest.fixture
    @abstractmethod
    def transform(self) -> TransformProtocol:
        """Provide a configured transform instance."""
        raise NotImplementedError

    @pytest.fixture
    @abstractmethod
    def valid_input(self) -> dict[str, Any]:
        """Provide a valid input row that should process successfully."""
        raise NotImplementedError

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Provide a PluginContext for testing."""
        return PluginContext(
            run_id="test-run-001",
            config={},
            node_id="test-transform",
            plugin_name="test",
        )

    # =========================================================================
    # Protocol Attribute Contracts
    # =========================================================================

    def test_transform_has_name(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have a 'name' attribute."""
        assert hasattr(transform, "name")
        assert isinstance(transform.name, str)
        assert len(transform.name) > 0

    def test_transform_has_input_schema(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have an 'input_schema' attribute that is a PluginSchema subclass."""
        assert isinstance(transform.input_schema, type)
        assert issubclass(transform.input_schema, PluginSchema)

    def test_transform_has_output_schema(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have an 'output_schema' attribute that is a PluginSchema subclass."""
        assert isinstance(transform.output_schema, type)
        assert issubclass(transform.output_schema, PluginSchema)

    def test_transform_has_determinism(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have a 'determinism' attribute."""
        assert hasattr(transform, "determinism")
        assert isinstance(transform.determinism, Determinism)

    def test_transform_has_plugin_version(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have a 'plugin_version' attribute."""
        assert hasattr(transform, "plugin_version")
        assert isinstance(transform.plugin_version, str)

    def test_transform_has_batch_awareness_flag(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have 'is_batch_aware' attribute."""
        assert hasattr(transform, "is_batch_aware")
        assert isinstance(transform.is_batch_aware, bool)

    def test_transform_has_creates_tokens_flag(self, transform: TransformProtocol) -> None:
        """Contract: Transform MUST have 'creates_tokens' attribute."""
        assert hasattr(transform, "creates_tokens")
        assert isinstance(transform.creates_tokens, bool)

    # =========================================================================
    # process() Method Contracts
    # =========================================================================

    def test_process_returns_transform_result(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: process() MUST return TransformResult."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        assert isinstance(result, TransformResult), f"process() returned {type(result).__name__}, expected TransformResult"

    def test_success_result_has_status(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: TransformResult MUST have status field."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        assert hasattr(result, "status")
        assert result.status in ("success", "error")

    def test_success_result_has_output_data(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Success results MUST have output data (row or rows)."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        if result.status == "success":
            assert result.has_output_data, (
                "Success TransformResult has no output data. Use TransformResult.success(row) or TransformResult.success_multi(rows)."
            )

    def test_success_single_row_is_pipeline_row(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Success single-row output MUST be a PipelineRow."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        if result.status == "success" and result.row is not None:
            assert isinstance(result.row, PipelineRow), f"TransformResult.row is {type(result.row).__name__}, expected PipelineRow"

    def test_success_multi_row_is_list_of_pipeline_rows(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Success multi-row output MUST be a list of PipelineRows."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        if result.status == "success" and result.rows is not None:
            assert isinstance(result.rows, list), f"TransformResult.rows is {type(result.rows).__name__}, expected list"
            for i, row in enumerate(result.rows):
                assert isinstance(row, PipelineRow), f"TransformResult.rows[{i}] is {type(row).__name__}, expected PipelineRow"

    # =========================================================================
    # Lifecycle Contracts
    # =========================================================================

    def test_close_is_idempotent(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: close() MUST be safe to call multiple times."""
        # Process something first (skip process() for batch transforms)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if not isinstance(transform, BatchTransformMixin):
            pipeline_row = make_pipeline_row(valid_input)
            transform.process(pipeline_row, ctx)

        # close() should not raise on first call
        transform.close()

        # close() should not raise on subsequent calls (idempotent)
        transform.close()
        transform.close()

    def test_on_start_does_not_raise(
        self,
        transform: TransformProtocol,
        ctx: PluginContext,
    ) -> None:
        """Contract: on_start() lifecycle hook MUST not raise."""
        transform.on_start(ctx)

    def test_on_complete_does_not_raise(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: on_complete() lifecycle hook MUST not raise."""
        # Process something first (skip process() for batch transforms)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if not isinstance(transform, BatchTransformMixin):
            pipeline_row = make_pipeline_row(valid_input)
            transform.process(pipeline_row, ctx)
        transform.on_complete(ctx)


class TransformContractPropertyTestBase(TransformContractTestBase):
    """Extended base with property-based contract verification.

    Adds Hypothesis property tests for stronger contract guarantees.
    """

    @given(extra_field=st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,19}", fullmatch=True))
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.differing_executors,
        ],
    )
    def test_process_handles_extra_fields_gracefully(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
        extra_field: str,
    ) -> None:
        """Property: Transform MUST return TransformResult even with extra fields.

        Extra fields are ignored per PluginSchema (extra="ignore").
        """
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        input_with_extra = {**valid_input, extra_field: "extra_value"}
        pipeline_row = make_pipeline_row(input_with_extra)
        result = transform.process(pipeline_row, ctx)
        assert isinstance(result, TransformResult)

    def test_deterministic_transform_produces_same_output(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Property: DETERMINISTIC transforms MUST produce same output for same input."""
        if transform.determinism == Determinism.DETERMINISTIC:
            pipeline_row = make_pipeline_row(valid_input)
            result1 = transform.process(pipeline_row, ctx)
            result2 = transform.process(pipeline_row, ctx)

            assert result1.status == "success"
            assert result2.status == "success"
            assert result1.row is not None
            assert result2.row is not None
            assert result1.row.to_dict() == result2.row.to_dict(), "Deterministic transform produced different outputs"


class TransformErrorContractTestBase(TransformContractTestBase):
    """Base class for testing transform error handling contracts.

    Subclasses should provide an error_input fixture that triggers an error.
    """

    @pytest.fixture
    @abstractmethod
    def error_input(self) -> dict[str, Any]:
        """Provide an input that should cause the transform to return an error."""
        raise NotImplementedError

    def test_error_input_returns_error_status(
        self,
        transform: TransformProtocol,
        error_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: error_input fixture MUST produce an error result."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(error_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error", f"error_input MUST produce error, got status={result.status}"

    def test_error_result_has_reason(
        self,
        transform: TransformProtocol,
        error_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Error results MUST have a reason dict."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(error_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert result.reason is not None, "Error TransformResult has None reason"
        assert isinstance(result.reason, dict), f"TransformResult.reason is {type(result.reason).__name__}, expected dict"

    def test_error_result_has_no_output_data(
        self,
        transform: TransformProtocol,
        error_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Error results should NOT have output data."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(error_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert result.row is None, "Error result should not have row"
        assert result.rows is None, "Error result should not have rows"

    def test_error_result_has_retryable_flag(
        self,
        transform: TransformProtocol,
        error_input: dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Contract: Error results MUST have a retryable flag."""
        # Skip for transforms using BatchTransformMixin (use accept() instead)
        from elspeth.plugins.batching.mixin import BatchTransformMixin

        if isinstance(transform, BatchTransformMixin):
            pytest.skip("Transform uses BatchTransformMixin - process() not supported, use accept()")

        pipeline_row = make_pipeline_row(error_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert isinstance(result.retryable, bool)
