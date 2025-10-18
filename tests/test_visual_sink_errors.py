from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink


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


def test_visual_sink_logs_error_when_write_fails(monkeypatch, tmp_path: Path) -> None:
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], on_error="skip")
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]

    # Cause write_bytes to fail to exercise error handling with plugin logger
    def _boom_write_bytes(self, data):  # noqa: D401
        raise RuntimeError("cannot write")

    monkeypatch.setattr(Path, "write_bytes", _boom_write_bytes)
    sink.write({"results": [{"metrics": {"scores": {"x": 1.0}}}]}, metadata={"experiment": "e"})
    assert sink.plugin_logger.errors, "Expected visual sink to log error on write failure"  # type: ignore[attr-defined]
