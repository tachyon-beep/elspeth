from __future__ import annotations

import json
from pathlib import Path

from elspeth.plugins.nodes.sinks.blob import BlobResultSink


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


def _write_blob_config(path: Path) -> Path:
    content = {
        "default": {
            "connection_name": "c",
            "azureml_datastore_uri": "azureml://workspaces/w/datasets/d",
            "account_name": "acct",
            "container_name": "cont",
            "blob_path": "base/path",
        }
    }
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_blob_sink_logs_error_when_upload_fails(monkeypatch, tmp_path: Path) -> None:
    cfg = _write_blob_config(tmp_path / "blob.json")
    sink = BlobResultSink(config_path=str(cfg), on_error="skip")
    sink.plugin_logger = _DummyLogger()  # type: ignore[attr-defined]

    def _boom(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("upload failed")

    # Avoid Azure SDK imports by patching upload path directly
    monkeypatch.setattr(sink, "_upload_bytes", _boom)
    sink.write({"results": []}, metadata={"experiment": "e"})
    assert sink.plugin_logger.errors, "Expected blob sink to log error on upload failure"  # type: ignore[attr-defined]
