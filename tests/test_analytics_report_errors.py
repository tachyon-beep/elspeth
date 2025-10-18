from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.analytics_report import AnalyticsReportSink


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


def test_analytics_report_error_path_logged(monkeypatch, tmp_path: Path) -> None:
    sink = AnalyticsReportSink(base_path=str(tmp_path), formats=["json"], on_error="skip")
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]

    def _boom(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("boom")

    # Cause summary build to fail, exercising skip + log_error branch
    monkeypatch.setattr(sink, "_build_summary", _boom)
    sink.write({"results": []})
    assert sink.plugin_logger.errors, "Expected error recorded on plugin logger"  # type: ignore[attr-defined]
