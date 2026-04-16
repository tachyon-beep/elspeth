"""Tests for execution response models."""

from __future__ import annotations

from datetime import UTC, datetime

import pydantic
import pytest

from elspeth.web.execution.schemas import (
    CancelledData,
    CompletedData,
    ErrorData,
    FailedData,
    ProgressData,
    RunEvent,
    ValidationCheck,
    ValidationError,
    ValidationResult,
)


class TestValidationResult:
    def test_invalid_result_with_attributed_error(self) -> None:
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(name="settings_load", passed=True, detail="OK"),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Graph validation failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id="gate_1",
                    component_type="gate",
                    message="Route destination 'nonexistent_sink' not found",
                    suggestion="Check sink names in gate configuration",
                ),
            ],
        )
        assert result.is_valid is False
        assert result.errors[0].component_id == "gate_1"
        assert result.errors[0].component_type == "gate"

    def test_structural_error_has_null_component(self) -> None:
        err = ValidationError(
            component_id=None,
            component_type=None,
            message="Graph contains a cycle",
            suggestion=None,
        )
        assert err.component_id is None
        assert err.component_type is None

    def test_skipped_check_recorded(self) -> None:
        """When settings_load fails, downstream checks are skipped but recorded."""
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=False,
                    detail="Invalid YAML syntax",
                ),
                ValidationCheck(
                    name="plugin_instantiation",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="schema_compatibility",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id=None,
                    component_type=None,
                    message="Invalid YAML syntax",
                    suggestion=None,
                ),
            ],
        )
        assert result.is_valid is False
        skipped = [c for c in result.checks if "Skipped" in c.detail]
        assert len(skipped) == 3


class TestRunEvent:
    def test_invalid_event_type_rejected(self) -> None:
        """event_type is a Literal — Pydantic rejects unknown values."""
        with pytest.raises(pydantic.ValidationError):
            RunEvent(
                run_id="run-123",
                timestamp=datetime.now(tz=UTC),
                event_type="unknown",
                data=ProgressData(rows_processed=0, rows_failed=0),
            )

    def test_progress_event_valid(self) -> None:
        event = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="progress",
            data=ProgressData(rows_processed=10, rows_failed=2),
        )
        assert event.data.rows_processed == 10
        assert event.data.rows_failed == 2

    def test_completed_event_valid(self) -> None:
        event = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="completed",
            data=CompletedData(
                rows_processed=100,
                rows_succeeded=95,
                rows_failed=3,
                rows_quarantined=2,
                landscape_run_id="lscape-1",
            ),
        )
        assert event.data.rows_succeeded == 95
        assert event.data.landscape_run_id == "lscape-1"

    def test_cancelled_event_valid(self) -> None:
        event = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="cancelled",
            data=CancelledData(rows_processed=50, rows_failed=1),
        )
        assert event.data.rows_processed == 50

    def test_failed_event_valid(self) -> None:
        event = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="failed",
            data=FailedData(detail="Pipeline crashed", node_id=None),
        )
        assert event.data.detail == "Pipeline crashed"

    def test_error_event_valid(self) -> None:
        event = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="error",
            data=ErrorData(message="Row parse failure", node_id="csv_source", row_id="row-42"),
        )
        assert event.data.message == "Row parse failure"

    def test_mismatched_event_type_and_data_rejected(self) -> None:
        """event_type='progress' with FailedData must crash — offensive programming."""
        with pytest.raises(pydantic.ValidationError, match="requires ProgressData"):
            RunEvent(
                run_id="run-1",
                timestamp=datetime.now(tz=UTC),
                event_type="progress",
                data=FailedData(detail="wrong type", node_id=None),
            )

    def test_empty_dict_data_rejected(self) -> None:
        """Regression: data={} was accepted under the old untyped schema."""
        with pytest.raises(pydantic.ValidationError):
            RunEvent(
                run_id="run-1",
                timestamp=datetime.now(tz=UTC),
                event_type="cancelled",
                data={},
            )

    def test_cancelled_requires_row_counts(self) -> None:
        """CancelledData must include rows_processed and rows_failed."""
        with pytest.raises(pydantic.ValidationError):
            RunEvent(
                run_id="run-1",
                timestamp=datetime.now(tz=UTC),
                event_type="cancelled",
                data=CancelledData(rows_processed=0),  # type: ignore[call-arg]
            )


class TestRunEventJsonRoundTrip:
    """Verify model_dump(mode='json') → model_validate round-trip.

    The production WebSocket path serializes via model_dump(mode='json')
    and the reconnect path constructs through model_validate. Both must
    produce identical results.
    """

    def _round_trip(self, event: RunEvent) -> RunEvent:
        json_dict = event.model_dump(mode="json")
        return RunEvent.model_validate(json_dict)

    def test_progress_round_trip(self) -> None:
        original = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="progress",
            data=ProgressData(rows_processed=50, rows_failed=3),
        )
        restored = self._round_trip(original)
        assert restored.event_type == "progress"
        assert isinstance(restored.data, ProgressData)
        assert restored.data.rows_processed == 50

    def test_completed_round_trip(self) -> None:
        original = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="completed",
            data=CompletedData(
                rows_processed=100,
                rows_succeeded=95,
                rows_failed=3,
                rows_quarantined=2,
                landscape_run_id="lscape-1",
            ),
        )
        restored = self._round_trip(original)
        assert restored.event_type == "completed"
        assert isinstance(restored.data, CompletedData)
        assert restored.data.rows_succeeded == 95
        assert restored.data.landscape_run_id == "lscape-1"

    def test_cancelled_round_trip(self) -> None:
        """Cancelled has identical shape to Progress — round-trip must
        preserve the correct type via model_validator.
        """
        original = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="cancelled",
            data=CancelledData(rows_processed=10, rows_failed=1),
        )
        restored = self._round_trip(original)
        assert restored.event_type == "cancelled"
        assert isinstance(restored.data, CancelledData)

    def test_failed_round_trip(self) -> None:
        original = RunEvent(
            run_id="run-1",
            timestamp=datetime.now(tz=UTC),
            event_type="failed",
            data=FailedData(detail="kaboom", node_id=None),
        )
        restored = self._round_trip(original)
        assert isinstance(restored.data, FailedData)
        assert restored.data.detail == "kaboom"


class TestCompletedDataDecomposition:
    """Enforce rows_processed == rows_succeeded + rows_failed + rows_quarantined."""

    def test_consistent_counts_accepted(self) -> None:
        data = CompletedData(
            rows_processed=100,
            rows_succeeded=95,
            rows_failed=3,
            rows_quarantined=2,
            landscape_run_id="lscape-1",
        )
        assert data.rows_processed == 100

    def test_inconsistent_counts_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="decomposition mismatch"):
            CompletedData(
                rows_processed=100,
                rows_succeeded=95,
                rows_failed=5,
                rows_quarantined=3,  # 95 + 5 + 3 = 103 != 100
                landscape_run_id="lscape-1",
            )

    def test_zero_counts_accepted(self) -> None:
        data = CompletedData(
            rows_processed=0,
            rows_succeeded=0,
            rows_failed=0,
            rows_quarantined=0,
            landscape_run_id="lscape-empty",
        )
        assert data.rows_processed == 0


class TestRowCountConstraints:
    """Row count fields must be non-negative."""

    def test_negative_rows_processed_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            ProgressData(rows_processed=-1, rows_failed=0)

    def test_negative_rows_failed_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            ProgressData(rows_processed=0, rows_failed=-1)

    def test_negative_cancelled_rows_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            CancelledData(rows_processed=-1, rows_failed=0)

    def test_negative_completed_rows_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            CompletedData(
                rows_processed=-1,
                rows_succeeded=0,
                rows_failed=0,
                rows_quarantined=0,
                landscape_run_id="lscape-1",
            )


class TestFailedDataConstraints:
    """FailedData.detail must be non-empty."""

    def test_empty_detail_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="string_too_short"):
            FailedData(detail="", node_id=None)

    def test_nonempty_detail_accepted(self) -> None:
        data = FailedData(detail="Pipeline crashed", node_id=None)
        assert data.detail == "Pipeline crashed"


class TestErrorDataConstraints:
    """ErrorData.message must be non-empty (parity with FailedData.detail)."""

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="string_too_short"):
            ErrorData(message="", node_id=None, row_id=None)

    def test_nonempty_message_accepted(self) -> None:
        data = ErrorData(message="Row parse failure", node_id="src", row_id="r1")
        assert data.message == "Row parse failure"


class TestCompletedDataLandscapeRunId:
    """CompletedData.landscape_run_id must be non-empty."""

    def test_empty_landscape_run_id_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="string_too_short"):
            CompletedData(
                rows_processed=10,
                rows_succeeded=10,
                rows_failed=0,
                rows_quarantined=0,
                landscape_run_id="",
            )


class TestResponseModelConstraints:
    """RunStatusResponse and RunResultsResponse enforce non-negative row counts."""

    def test_status_response_rejects_negative_rows(self) -> None:
        from elspeth.web.execution.schemas import RunStatusResponse

        with pytest.raises(pydantic.ValidationError):
            RunStatusResponse(
                run_id="r1",
                status="completed",
                started_at=None,
                finished_at=None,
                rows_processed=-1,
                rows_succeeded=0,
                rows_failed=0,
                rows_quarantined=0,
                error=None,
                landscape_run_id=None,
            )

    def test_results_response_rejects_negative_rows(self) -> None:
        from elspeth.web.execution.schemas import RunResultsResponse

        with pytest.raises(pydantic.ValidationError):
            RunResultsResponse(
                run_id="r1",
                status="completed",
                rows_processed=10,
                rows_succeeded=10,
                rows_failed=-1,
                rows_quarantined=0,
                landscape_run_id=None,
                error=None,
            )
