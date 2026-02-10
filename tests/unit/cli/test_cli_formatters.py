"""Unit tests for CLI event formatters edge branches."""

from __future__ import annotations

import json
from unittest.mock import patch

from elspeth.cli_formatters import create_console_formatters, create_json_formatters
from elspeth.contracts.cli import ProgressEvent
from elspeth.contracts.events import RunCompletionStatus, RunSummary


class TestConsoleFormatters:
    """Human-readable formatter edge behavior."""

    def test_run_summary_includes_routed_destinations_when_present(self) -> None:
        """Routed destination breakdown should render when destination list is present."""
        summary_handler = create_console_formatters(prefix="Run")[RunSummary]
        event = RunSummary(
            run_id="run-1",
            status=RunCompletionStatus.PARTIAL,
            total_rows=10,
            succeeded=7,
            failed=2,
            quarantined=1,
            duration_seconds=1.5,
            exit_code=1,
            routed=3,
            routed_destinations=(("sink_a", 2), ("sink_b", 1)),
        )

        with patch("elspeth.cli_formatters.typer.echo") as mock_echo:
            summary_handler(event)

        rendered = mock_echo.call_args.args[0]
        assert "→3 routed (sink_a:2, sink_b:1)" in rendered
        assert "PARTIAL" in rendered

    def test_run_summary_handles_empty_routed_destinations_list(self) -> None:
        """If routed count is non-zero but destinations are empty, formatter stays readable."""
        summary_handler = create_console_formatters(prefix="Run")[RunSummary]
        event = RunSummary(
            run_id="run-2",
            status=RunCompletionStatus.COMPLETED,
            total_rows=10,
            succeeded=10,
            failed=0,
            quarantined=0,
            duration_seconds=2.0,
            exit_code=0,
            routed=2,
            routed_destinations=(),
        )

        with patch("elspeth.cli_formatters.typer.echo") as mock_echo:
            summary_handler(event)

        rendered = mock_echo.call_args.args[0]
        assert "→2 routed" in rendered
        assert "()" not in rendered

    def test_progress_elapsed_zero_formats_rate_as_zero(self) -> None:
        """Progress formatter must avoid divide-by-zero when elapsed_seconds == 0."""
        progress_handler = create_console_formatters()[ProgressEvent]
        event = ProgressEvent(
            rows_processed=25,
            rows_succeeded=20,
            rows_failed=3,
            rows_quarantined=2,
            elapsed_seconds=0.0,
        )

        with patch("elspeth.cli_formatters.typer.echo") as mock_echo:
            progress_handler(event)

        rendered = mock_echo.call_args.args[0]
        assert "0 rows/sec" in rendered


class TestJsonFormatters:
    """Structured formatter edge behavior."""

    def test_progress_json_elapsed_zero_emits_zero_rows_per_second(self) -> None:
        """JSON progress formatter must emit stable numeric rate on elapsed=0."""
        progress_handler = create_json_formatters()[ProgressEvent]
        event = ProgressEvent(
            rows_processed=50,
            rows_succeeded=45,
            rows_failed=3,
            rows_quarantined=2,
            elapsed_seconds=0.0,
        )

        with patch("elspeth.cli_formatters.typer.echo") as mock_echo:
            progress_handler(event)

        payload = json.loads(mock_echo.call_args.args[0])
        assert payload["event"] == "progress"
        assert payload["rows_per_second"] == 0
        assert payload["elapsed_seconds"] == 0.0

    def test_run_summary_json_shape_is_stable_with_routed_edge_values(self) -> None:
        """JSON summary output should remain deterministic with routed edge inputs."""
        summary_handler = create_json_formatters()[RunSummary]
        event = RunSummary(
            run_id="run-3",
            status=RunCompletionStatus.FAILED,
            total_rows=1,
            succeeded=0,
            failed=1,
            quarantined=0,
            duration_seconds=0.0,
            exit_code=2,
            routed=1,
            routed_destinations=(("error_sink", 1),),
        )

        with patch("elspeth.cli_formatters.typer.echo") as mock_echo:
            summary_handler(event)

        payload = json.loads(mock_echo.call_args.args[0])
        assert payload == {
            "event": "run_completed",
            "run_id": "run-3",
            "status": "failed",
            "total_rows": 1,
            "succeeded": 0,
            "failed": 1,
            "quarantined": 0,
            "duration_seconds": 0.0,
            "exit_code": 2,
        }
