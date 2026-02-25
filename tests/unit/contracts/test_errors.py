"""Tests for error/reason schema contracts.

Tests for:
- ExecutionError frozen dataclass (exception, exception_type, traceback, phase)
- CoalesceFailureReason frozen dataclass (failure_reason, expected_branches, etc.)
- RoutingReason TypedDict (rule, matched_value, threshold fields)
- TransformReason TypedDict (action, fields_modified fields)
"""

import dataclasses

import pytest


class TestExecutionErrorSchema:
    """Tests for ExecutionError frozen dataclass schema."""

    def test_execution_error_is_frozen_dataclass(self) -> None:
        """ExecutionError is a frozen dataclass (immutable after construction)."""
        from elspeth.contracts import ExecutionError

        assert dataclasses.is_dataclass(ExecutionError)
        error = ExecutionError(exception="test", exception_type="ValueError")
        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            error.exception = "modified"  # type: ignore[misc]

    def test_execution_error_required_and_optional_fields(self) -> None:
        """ExecutionError has 2 required fields and 2 optional (None-default) fields."""
        from elspeth.contracts import ExecutionError

        fields = {f.name: f for f in dataclasses.fields(ExecutionError)}
        assert set(fields.keys()) == {"exception", "exception_type", "traceback", "phase"}
        # Required fields have no default
        assert fields["exception"].default is dataclasses.MISSING
        assert fields["exception_type"].default is dataclasses.MISSING
        # Optional fields default to None
        assert fields["traceback"].default is None
        assert fields["phase"].default is None

    def test_execution_error_to_dict_required_only(self) -> None:
        """to_dict() serializes exception_type as 'type' and omits None fields."""
        from elspeth.contracts import ExecutionError

        error = ExecutionError(exception="boom", exception_type="RuntimeError")
        d = error.to_dict()
        assert d == {"exception": "boom", "type": "RuntimeError"}
        assert "traceback" not in d
        assert "phase" not in d

    def test_execution_error_to_dict_with_optionals(self) -> None:
        """to_dict() includes optional fields when set."""
        from elspeth.contracts import ExecutionError

        error = ExecutionError(
            exception="boom",
            exception_type="RuntimeError",
            traceback="Traceback ...",
            phase="flush",
        )
        d = error.to_dict()
        assert d == {
            "exception": "boom",
            "type": "RuntimeError",
            "traceback": "Traceback ...",
            "phase": "flush",
        }


class TestRoutingReasonSchema:
    """Tests for RoutingReason union type schema introspection."""

    def test_routing_reason_is_union_type(self) -> None:
        """RoutingReason is a union of ConfigGateReason."""
        import types

        from elspeth.contracts import (
            ConfigGateReason,
            RoutingReason,
        )

        assert isinstance(RoutingReason, types.UnionType)
        # Union contains ConfigGateReason
        assert ConfigGateReason in RoutingReason.__args__

    def test_routing_reason_variants_are_typed_dicts(self) -> None:
        """RoutingReason variant is a TypedDict."""
        from typing import is_typeddict

        from elspeth.contracts import ConfigGateReason

        assert is_typeddict(ConfigGateReason)


class TestTransformSuccessReasonSchema:
    """Tests for TransformSuccessReason TypedDict schema introspection."""

    def test_transform_success_reason_required_keys(self) -> None:
        """TransformSuccessReason has action as required key."""
        from elspeth.contracts import TransformSuccessReason

        assert TransformSuccessReason.__required_keys__ == frozenset({"action"})

    def test_transform_success_reason_optional_keys(self) -> None:
        """TransformSuccessReason has expected optional keys."""
        from elspeth.contracts import TransformSuccessReason

        assert TransformSuccessReason.__optional_keys__ == frozenset(
            {
                "fields_modified",
                "fields_added",
                "fields_removed",
                "validation_warnings",
                "metadata",
                "queries_completed",
            }
        )

    def test_transform_action_category_values(self) -> None:
        """TransformActionCategory contains expected action types."""
        from typing import get_args

        from elspeth.contracts import TransformActionCategory

        categories = get_args(TransformActionCategory)
        assert "processed" in categories
        assert "mapped" in categories
        assert "skipped" in categories
        assert "enriched" in categories


class TestExecutionError:
    """Tests for ExecutionError frozen dataclass construction."""

    def test_execution_error_has_required_fields(self) -> None:
        """ExecutionError requires exception and exception_type fields."""
        from elspeth.contracts import ExecutionError

        error = ExecutionError(
            exception="ValueError: invalid input",
            exception_type="ValueError",
        )

        assert error.exception == "ValueError: invalid input"
        assert error.exception_type == "ValueError"
        # to_dict() maps exception_type → "type" for audit stability
        assert error.to_dict()["type"] == "ValueError"

    def test_execution_error_accepts_optional_traceback(self) -> None:
        """ExecutionError can include traceback."""
        from elspeth.contracts import ExecutionError

        error = ExecutionError(
            exception="KeyError: 'foo'",
            exception_type="KeyError",
            traceback="Traceback (most recent call last):\n...",
        )

        assert error.traceback is not None
        assert "traceback" in error.to_dict()


class TestRoutingReason:
    """Tests for RoutingReason union type usage."""

    def test_routing_reason_accepts_config_gate_reason(self) -> None:
        """RoutingReason union accepts ConfigGateReason variant."""
        from elspeth.contracts import ConfigGateReason, RoutingReason

        reason: RoutingReason = {
            "condition": "row['score'] > 100",
            "result": "true",
        }

        # At runtime, it's just a dict - cast to access variant-specific fields
        config_reason: ConfigGateReason = reason  # type: ignore[assignment]
        assert config_reason["condition"] == "row['score'] > 100"


class TestTransformSuccessReason:
    """Tests for TransformSuccessReason TypedDict."""

    def test_transform_success_reason_has_action_field(self) -> None:
        """TransformSuccessReason defines action field."""
        from elspeth.contracts import TransformSuccessReason

        reason: TransformSuccessReason = {
            "action": "normalized_field",
        }

        assert reason["action"] == "normalized_field"

    def test_transform_success_reason_accepts_optional_fields(self) -> None:
        """TransformSuccessReason can include optional field tracking and warnings."""
        from elspeth.contracts import TransformSuccessReason

        reason: TransformSuccessReason = {
            "action": "validated_and_normalized",
            "fields_modified": ["name", "email"],
            "fields_added": ["normalized_name"],
            "validation_warnings": ["phone format non-standard"],
        }

        assert reason["fields_modified"] == ["name", "email"]
        assert reason["fields_added"] == ["normalized_name"]
        assert reason["validation_warnings"] == ["phone format non-standard"]

    def test_transform_success_reason_accepts_metadata(self) -> None:
        """TransformSuccessReason can include plugin-specific metadata."""
        from elspeth.contracts import TransformSuccessReason

        reason: TransformSuccessReason = {
            "action": "enriched",
            "metadata": {"source": "external_api", "latency_ms": 42},
        }

        assert reason["metadata"]["source"] == "external_api"
        assert reason["metadata"]["latency_ms"] == 42


class TestRoutingReasonVariants:
    """Tests for RoutingReason variant structure."""

    def test_config_gate_reason_required_keys(self) -> None:
        """ConfigGateReason has condition and result as required."""
        from elspeth.contracts import ConfigGateReason

        assert ConfigGateReason.__required_keys__ == frozenset({"condition", "result"})


class TestRoutingReasonUsage:
    """Tests for constructing valid RoutingReason variants."""

    def test_config_gate_reason_construction(self) -> None:
        """ConfigGateReason can be constructed with required fields."""
        from elspeth.contracts import ConfigGateReason

        reason: ConfigGateReason = {
            "condition": "row['score'] > 100",
            "result": "true",
        }
        assert reason["condition"] == "row['score'] > 100"
        assert reason["result"] == "true"


class TestTransformErrorReasonSchema:
    """Tests for TransformErrorReason TypedDict schema."""

    def test_transform_error_reason_required_keys(self) -> None:
        """TransformErrorReason has reason as required."""
        from elspeth.contracts import TransformErrorReason

        assert TransformErrorReason.__required_keys__ == frozenset({"reason"})

    def test_transform_error_reason_has_expected_optional_keys(self) -> None:
        """TransformErrorReason has expected optional keys."""
        from elspeth.contracts import TransformErrorReason

        # Check a subset of important optional keys
        optional = TransformErrorReason.__optional_keys__
        assert "error" in optional
        assert "field" in optional
        assert "error_type" in optional
        assert "query" in optional
        assert "max_tokens" in optional
        assert "status_code" in optional
        assert "template_errors" in optional
        assert "row_errors" in optional

    def test_transform_error_category_literal_values(self) -> None:
        """TransformErrorCategory contains expected error types."""
        from typing import get_args

        from elspeth.contracts import TransformErrorCategory

        categories = get_args(TransformErrorCategory)
        # Verify key categories exist
        assert "api_error" in categories
        assert "missing_field" in categories
        assert "template_rendering_failed" in categories
        assert "response_truncated" in categories
        assert "batch_failed" in categories


class TestTransformErrorReasonUsage:
    """Tests for constructing valid TransformErrorReason values."""

    def test_minimal_error_reason(self) -> None:
        """TransformErrorReason works with only required field."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {"reason": "api_error"}
        assert reason["reason"] == "api_error"

    def test_api_error_pattern(self) -> None:
        """Common API error pattern with error and error_type."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "api_error",
            "error": "Connection refused",
            "error_type": "network_error",
        }
        assert reason["reason"] == "api_error"
        assert reason["error"] == "Connection refused"
        assert reason["error_type"] == "network_error"

    def test_field_error_pattern(self) -> None:
        """Common field-related error pattern."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "missing_field",
            "field": "customer_id",
        }
        assert reason["reason"] == "missing_field"
        assert reason["field"] == "customer_id"

    def test_llm_truncation_pattern(self) -> None:
        """LLM response truncation with token counts."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "response_truncated",
            "error": "Response truncated at 1000 tokens",
            "query": "sentiment",
            "max_tokens": 1000,
            "completion_tokens": 1000,
            "prompt_tokens": 500,
        }
        assert reason["reason"] == "response_truncated"
        assert reason["max_tokens"] == 1000

    def test_type_mismatch_pattern(self) -> None:
        """Type validation error pattern."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "type_mismatch",
            "field": "score",
            "expected": "float",
            "actual": "str",
            "value": "not_a_number",
        }
        assert reason["reason"] == "type_mismatch"
        assert reason["expected"] == "float"
        assert reason["actual"] == "str"

    def test_rate_limit_pattern(self) -> None:
        """Rate limiting/timeout error pattern."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "retry_timeout",
            "error": "Max retry time exceeded",
            "elapsed_seconds": 60.5,
            "max_seconds": 60.0,
            "status_code": 429,
        }
        assert reason["reason"] == "retry_timeout"
        assert reason["status_code"] == 429

    def test_batch_job_error_pattern(self) -> None:
        """Azure/OpenRouter batch job failure."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "batch_failed",
            "batch_id": "batch_abc123",
            "error": "Job expired",
            "queries_completed": 42,
        }
        assert reason["batch_id"] == "batch_abc123"
        assert reason["queries_completed"] == 42

    def test_batch_template_errors_pattern(self) -> None:
        """Template errors in batch processing with nested TypedDict."""
        from elspeth.contracts import TemplateErrorEntry, TransformErrorReason

        error1: TemplateErrorEntry = {"row_index": 0, "error": "Missing field 'customer_id'"}
        error2: TemplateErrorEntry = {"row_index": 5, "error": "Invalid template syntax"}

        reason: TransformErrorReason = {
            "reason": "all_templates_failed",
            "template_errors": [error1, error2],
        }
        assert len(reason["template_errors"]) == 2
        assert reason["template_errors"][0]["row_index"] == 0

    def test_content_safety_violation_pattern(self) -> None:
        """Content safety API violation."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "content_safety_violation",
            "field": "user_input",
            "categories": ["Violence", "SelfHarm"],
            "message": "Content violates safety policy",
        }
        assert reason["reason"] == "content_safety_violation"
        assert "Violence" in reason["categories"]

    def test_json_parsing_failure_pattern(self) -> None:
        """JSON parsing failure with response preview."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "invalid_json_type",
            "expected": "object",
            "actual": "list",
            "raw_response_preview": "[1, 2, 3]",
            "query": "classification",
        }
        assert reason["expected"] == "object"
        assert reason["actual"] == "list"

    def test_template_rendering_failure_pattern(self) -> None:
        """Jinja2 template rendering failure."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "template_rendering_failed",
            "error": "UndefinedError: 'customer_id' is undefined",
            "query": "sentiment_analysis",
            "template_hash": "sha256:abc123def456",
        }
        assert reason["template_hash"] is not None

    def test_usage_stats_nested_typeddict(self) -> None:
        """UsageStats nested TypedDict works correctly."""
        from elspeth.contracts import TransformErrorReason, UsageStats

        usage: UsageStats = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
        reason: TransformErrorReason = {
            "reason": "response_truncated",
            "usage": usage,
        }
        assert reason["usage"]["total_tokens"] == 150


class TestNestedTypeDicts:
    """Tests for nested TypedDict structures."""

    def test_template_error_entry_structure(self) -> None:
        """TemplateErrorEntry has correct fields."""
        from elspeth.contracts import TemplateErrorEntry

        entry: TemplateErrorEntry = {"row_index": 5, "error": "Missing field"}
        assert entry["row_index"] == 5
        assert entry["error"] == "Missing field"

    def test_row_error_entry_structure(self) -> None:
        """RowErrorEntry has correct fields."""
        from elspeth.contracts import RowErrorEntry

        entry: RowErrorEntry = {"row_index": 3, "reason": "api_error", "error": "Timeout"}
        assert entry["row_index"] == 3
        assert entry["reason"] == "api_error"

    def test_usage_stats_partial(self) -> None:
        """UsageStats allows partial fields (total=False)."""
        from elspeth.contracts import UsageStats

        # Only some fields provided
        usage: UsageStats = {"prompt_tokens": 100}
        assert usage["prompt_tokens"] == 100


class TestQueryFailureDetailSchema:
    """Tests for QueryFailureDetail TypedDict schema."""

    def test_query_failure_detail_required_keys(self) -> None:
        """QueryFailureDetail has query as required."""
        from elspeth.contracts import QueryFailureDetail

        assert QueryFailureDetail.__required_keys__ == frozenset({"query"})

    def test_query_failure_detail_optional_keys(self) -> None:
        """QueryFailureDetail has error, error_type, status_code as optional."""
        from elspeth.contracts import QueryFailureDetail

        assert QueryFailureDetail.__optional_keys__ == frozenset({"error", "error_type", "status_code"})


class TestQueryFailureDetailUsage:
    """Tests for constructing valid QueryFailureDetail values."""

    def test_minimal_query_failure(self) -> None:
        """QueryFailureDetail works with only required field."""
        from elspeth.contracts import QueryFailureDetail

        detail: QueryFailureDetail = {"query": "sentiment"}
        assert detail["query"] == "sentiment"

    def test_query_failure_with_error(self) -> None:
        """QueryFailureDetail with error details."""
        from elspeth.contracts import QueryFailureDetail

        detail: QueryFailureDetail = {
            "query": "classification",
            "error": "Rate limit exceeded",
            "error_type": "rate_limit",
            "status_code": 429,
        }
        assert detail["query"] == "classification"
        assert detail["error"] == "Rate limit exceeded"
        assert detail["error_type"] == "rate_limit"
        assert detail["status_code"] == 429


class TestErrorDetailSchema:
    """Tests for ErrorDetail TypedDict schema."""

    def test_error_detail_required_keys(self) -> None:
        """ErrorDetail has message as required."""
        from elspeth.contracts import ErrorDetail

        assert ErrorDetail.__required_keys__ == frozenset({"message"})

    def test_error_detail_optional_keys(self) -> None:
        """ErrorDetail has error_type, row_index, details as optional."""
        from elspeth.contracts import ErrorDetail

        assert ErrorDetail.__optional_keys__ == frozenset({"error_type", "row_index", "details"})


class TestErrorDetailUsage:
    """Tests for constructing valid ErrorDetail values."""

    def test_minimal_error_detail(self) -> None:
        """ErrorDetail works with only required field."""
        from elspeth.contracts import ErrorDetail

        detail: ErrorDetail = {"message": "Something went wrong"}
        assert detail["message"] == "Something went wrong"

    def test_error_detail_with_context(self) -> None:
        """ErrorDetail with full context."""
        from elspeth.contracts import ErrorDetail

        detail: ErrorDetail = {
            "message": "JSON parse failed",
            "error_type": "json_parse_error",
            "row_index": 42,
            "details": "Unexpected token at position 15",
        }
        assert detail["message"] == "JSON parse failed"
        assert detail["error_type"] == "json_parse_error"
        assert detail["row_index"] == 42
        assert detail["details"] == "Unexpected token at position 15"


class TestFailedQueriesFieldType:
    """Tests for failed_queries field with union type."""

    def test_failed_queries_with_strings(self) -> None:
        """failed_queries accepts list of query names."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "query_failed",
            "failed_queries": ["sentiment", "classification"],
        }
        assert reason["failed_queries"] == ["sentiment", "classification"]

    def test_failed_queries_with_details(self) -> None:
        """failed_queries accepts list of QueryFailureDetail."""
        from elspeth.contracts import QueryFailureDetail, TransformErrorReason

        detail1: QueryFailureDetail = {"query": "sentiment", "error": "Timeout"}
        detail2: QueryFailureDetail = {"query": "classification", "status_code": 500}

        reason: TransformErrorReason = {
            "reason": "query_failed",
            "failed_queries": [detail1, detail2],
        }
        assert len(reason["failed_queries"]) == 2

    def test_failed_queries_mixed(self) -> None:
        """failed_queries accepts mixed list of strings and QueryFailureDetail."""
        from elspeth.contracts import QueryFailureDetail, TransformErrorReason

        detail: QueryFailureDetail = {"query": "sentiment", "error": "Timeout"}

        reason: TransformErrorReason = {
            "reason": "query_failed",
            "failed_queries": ["classification", detail],
        }
        assert len(reason["failed_queries"]) == 2


class TestErrorsFieldType:
    """Tests for errors field with union type."""

    def test_errors_with_strings(self) -> None:
        """errors accepts list of error message strings."""
        from elspeth.contracts import TransformErrorReason

        reason: TransformErrorReason = {
            "reason": "batch_failed",
            "errors": ["Row 1 failed", "Row 5 failed"],
        }
        assert reason["errors"] == ["Row 1 failed", "Row 5 failed"]

    def test_errors_with_details(self) -> None:
        """errors accepts list of ErrorDetail."""
        from elspeth.contracts import ErrorDetail, TransformErrorReason

        detail1: ErrorDetail = {"message": "Row 1 failed", "row_index": 1}
        detail2: ErrorDetail = {"message": "Row 5 failed", "row_index": 5}

        reason: TransformErrorReason = {
            "reason": "batch_failed",
            "errors": [detail1, detail2],
        }
        assert len(reason["errors"]) == 2

    def test_errors_mixed(self) -> None:
        """errors accepts mixed list of strings and ErrorDetail."""
        from elspeth.contracts import ErrorDetail, TransformErrorReason

        detail: ErrorDetail = {"message": "Row 5 failed", "row_index": 5}

        reason: TransformErrorReason = {
            "reason": "batch_failed",
            "errors": ["Row 1 failed", detail],
        }
        assert len(reason["errors"]) == 2


class TestCoalesceFailureReasonSchema:
    """Tests for CoalesceFailureReason frozen dataclass schema."""

    def test_is_frozen_dataclass(self) -> None:
        """CoalesceFailureReason is a frozen dataclass (immutable after construction)."""
        from elspeth.contracts import CoalesceFailureReason

        assert dataclasses.is_dataclass(CoalesceFailureReason)
        error = CoalesceFailureReason(
            failure_reason="quorum_not_met",
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            merge_policy="union",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            error.failure_reason = "modified"  # type: ignore[misc]

    def test_has_slots(self) -> None:
        """CoalesceFailureReason uses __slots__ for memory efficiency."""
        from elspeth.contracts import CoalesceFailureReason

        assert hasattr(CoalesceFailureReason, "__slots__")

    def test_required_and_optional_fields(self) -> None:
        """CoalesceFailureReason has 4 required + 2 optional fields."""
        from elspeth.contracts import CoalesceFailureReason

        fields = {f.name: f for f in dataclasses.fields(CoalesceFailureReason)}
        assert set(fields.keys()) == {
            "failure_reason",
            "expected_branches",
            "branches_arrived",
            "merge_policy",
            "timeout_ms",
            "select_branch",
        }
        # Required fields have no default
        assert fields["failure_reason"].default is dataclasses.MISSING
        assert fields["expected_branches"].default is dataclasses.MISSING
        assert fields["branches_arrived"].default is dataclasses.MISSING
        assert fields["merge_policy"].default is dataclasses.MISSING
        # Optional fields default to None
        assert fields["timeout_ms"].default is None
        assert fields["select_branch"].default is None

    def test_to_dict_required_only(self) -> None:
        """to_dict() omits None-valued optional fields."""
        from elspeth.contracts import CoalesceFailureReason

        error = CoalesceFailureReason(
            failure_reason="incomplete_branches",
            expected_branches=["path_a", "path_b"],
            branches_arrived=["path_a"],
            merge_policy="union",
        )
        d = error.to_dict()
        assert d == {
            "failure_reason": "incomplete_branches",
            "expected_branches": ["path_a", "path_b"],
            "branches_arrived": ["path_a"],
            "merge_policy": "union",
        }
        assert "timeout_ms" not in d
        assert "select_branch" not in d

    def test_to_dict_with_timeout(self) -> None:
        """to_dict() includes timeout_ms when set."""
        from elspeth.contracts import CoalesceFailureReason

        error = CoalesceFailureReason(
            failure_reason="quorum_not_met_at_timeout",
            expected_branches=["a", "b", "c"],
            branches_arrived=["a"],
            merge_policy="nested",
            timeout_ms=30000,
        )
        d = error.to_dict()
        assert d["timeout_ms"] == 30000
        assert "select_branch" not in d

    def test_to_dict_with_select_branch(self) -> None:
        """to_dict() includes select_branch when set."""
        from elspeth.contracts import CoalesceFailureReason

        error = CoalesceFailureReason(
            failure_reason="select_branch_not_arrived",
            expected_branches=["fast", "slow"],
            branches_arrived=["slow"],
            merge_policy="select",
            select_branch="fast",
        )
        d = error.to_dict()
        assert d["select_branch"] == "fast"
        assert "timeout_ms" not in d

    def test_to_dict_with_all_optionals(self) -> None:
        """to_dict() includes all fields when all are set."""
        from elspeth.contracts import CoalesceFailureReason

        error = CoalesceFailureReason(
            failure_reason="select_branch_not_arrived",
            expected_branches=["a", "b"],
            branches_arrived=["b"],
            merge_policy="select",
            timeout_ms=5000,
            select_branch="a",
        )
        d = error.to_dict()
        assert d == {
            "failure_reason": "select_branch_not_arrived",
            "expected_branches": ["a", "b"],
            "branches_arrived": ["b"],
            "merge_policy": "select",
            "timeout_ms": 5000,
            "select_branch": "a",
        }

    def test_late_arrival_has_empty_branches_arrived(self) -> None:
        """Late arrival failures have empty branches_arrived list."""
        from elspeth.contracts import CoalesceFailureReason

        error = CoalesceFailureReason(
            failure_reason="late_arrival_after_merge",
            expected_branches=["a", "b"],
            branches_arrived=[],
            merge_policy="union",
        )
        assert error.branches_arrived == []
        assert error.to_dict()["branches_arrived"] == []
