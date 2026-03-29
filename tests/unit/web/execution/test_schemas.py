"""Tests for execution response models."""

from __future__ import annotations

from datetime import UTC, datetime

import pydantic
import pytest

from elspeth.web.execution.schemas import (
    RunEvent,
    RunStatusResponse,
    ValidationCheck,
    ValidationError,
    ValidationResult,
)


class TestValidationResult:
    def test_valid_result(self) -> None:
        result = ValidationResult(
            is_valid=True,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=True,
                    detail="Settings loaded successfully",
                ),
                ValidationCheck(
                    name="plugin_instantiation",
                    passed=True,
                    detail="All plugins instantiated",
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=True,
                    detail="Graph is valid",
                ),
                ValidationCheck(
                    name="schema_compatibility",
                    passed=True,
                    detail="All edge schemas compatible",
                ),
            ],
            errors=[],
        )
        assert result.is_valid is True
        assert len(result.checks) == 4
        assert all(c.passed for c in result.checks)

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
    def test_progress_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=UTC),
            event_type="progress",
            data={"rows_processed": 50, "rows_failed": 2},
        )
        assert event.event_type == "progress"
        assert event.data["rows_processed"] == 50

    def test_completed_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=UTC),
            event_type="completed",
            data={
                "rows_processed": 100,
                "rows_succeeded": 98,
                "rows_failed": 2,
                "rows_quarantined": 0,
                "landscape_run_id": "lscape-456",
            },
        )
        assert event.event_type == "completed"
        assert event.data["landscape_run_id"] == "lscape-456"

    def test_error_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=UTC),
            event_type="error",
            data={"detail": "Division by zero", "node_id": "transform_1", "row_id": "row-5"},
        )
        assert event.event_type == "error"
        assert event.data["node_id"] == "transform_1"

    def test_invalid_event_type_rejected(self) -> None:
        """event_type is a Literal — Pydantic rejects unknown values."""
        with pytest.raises(pydantic.ValidationError):
            RunEvent(
                run_id="run-123",
                timestamp=datetime.now(tz=UTC),
                event_type="unknown",  # type: ignore[arg-type]
                data={},
            )


class TestRunStatusResponse:
    def test_pending_status(self) -> None:
        status = RunStatusResponse(
            run_id="run-123",
            status="pending",
            started_at=None,
            finished_at=None,
            rows_processed=0,
            rows_failed=0,
            error=None,
            landscape_run_id=None,
        )
        assert status.status == "pending"
        assert status.started_at is None

    def test_completed_status(self) -> None:
        now = datetime.now(tz=UTC)
        status = RunStatusResponse(
            run_id="run-123",
            status="completed",
            started_at=now,
            finished_at=now,
            rows_processed=100,
            rows_failed=0,
            error=None,
            landscape_run_id="lscape-456",
        )
        assert status.landscape_run_id == "lscape-456"

    def test_failed_status_has_error(self) -> None:
        now = datetime.now(tz=UTC)
        status = RunStatusResponse(
            run_id="run-123",
            status="failed",
            started_at=now,
            finished_at=now,
            rows_processed=50,
            rows_failed=50,
            error="Connection refused",
            landscape_run_id=None,
        )
        assert status.error == "Connection refused"
