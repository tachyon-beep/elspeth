from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.local_bundle import LocalBundleSink


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


def _results(n: int = 1) -> dict:
    return {"results": [{"row": {"a": i}} for i in range(n)]}


def test_local_bundle_warns_when_sanitize_disabled(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.clear()
    with caplog.at_level("WARNING"):
        sink = LocalBundleSink(base_path=tmp_path, sanitize_formulas=False, timestamped=False)
        sink._allowed_base = tmp_path.resolve()  # type: ignore[attr-defined]
        sink.write(_results())
    assert any("CSV sanitization disabled" in rec.getMessage() for rec in caplog.records)


def test_local_bundle_on_error_skip_logs_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Force safe_atomic_write in module to raise to trigger error path
    import elspeth.plugins.nodes.sinks.local_bundle as mod

    def _boom(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(mod, "safe_atomic_write", _boom)
    sink = LocalBundleSink(base_path=tmp_path, bundle_name="b", timestamped=False, on_error="skip")
    sink._allowed_base = tmp_path.resolve()  # type: ignore[attr-defined]
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]
    sink.write(_results(), metadata={"experiment": "e"})
    assert sink.plugin_logger.errors, "Expected an error logged by plugin logger"  # type: ignore[attr-defined]
