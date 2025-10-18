from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.analytics_report import AnalyticsReportSink
from elspeth.plugins.nodes.sinks.repository import GitHubRepoSink


class _DummyLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []
        self.errors: list[tuple[Exception, dict]] = []

    def log_event(
        self,
        event_type: str,
        *,
        message: str | None = None,
        metrics: dict | None = None,
        metadata: dict | None = None,
        level: str = "info",
    ) -> None:  # noqa: D401
        self.events.append(
            (
                event_type,
                {
                    "message": message,
                    "metrics": metrics or {},
                    "metadata": metadata or {},
                    "level": level,
                },
            )
        )

    def log_error(self, exc: Exception, *, context: str | None = None, recoverable: bool = False) -> None:
        self.errors.append((exc, {"context": context or "", "recoverable": recoverable}))


def test_analytics_report_emits_logger_events(tmp_path: Path) -> None:
    sink = AnalyticsReportSink(
        base_path=str(tmp_path),
        file_stem="obs_test",
        formats=["json"],
        include_metadata=False,
        include_aggregates=False,
        include_comparisons=False,
    )
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]
    sink.write({"results": [{"row": {"a": 1}}]}, metadata={"experiment": "e"})

    events = [e for e, _ in sink.plugin_logger.events]  # type: ignore[attr-defined]
    assert "sink_write_attempt" in events
    assert "sink_write" in events


def test_repo_sink_emits_logger_events_in_dry_run(tmp_path: Path) -> None:
    sink = GitHubRepoSink(owner="o", repo="r")
    sink.dry_run = True
    sink.session = None  # no network usage in dry-run
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]
    sink.write({"results": []}, metadata={"experiment": "e"})

    events = [etype for etype, _ in sink.plugin_logger.events]  # type: ignore[attr-defined]
    assert "sink_write_attempt" in events
    assert "sink_write" in events  # dry-run success
