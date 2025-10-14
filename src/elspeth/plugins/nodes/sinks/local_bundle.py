"""Filesystem bundle sink for archiving experiment outputs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from elspeth.core.interfaces import ResultSink
from elspeth.plugins.outputs.csv_file import CsvResultSink

logger = logging.getLogger(__name__)


@dataclass
class LocalBundleSink(ResultSink):
    base_path: str | Path
    bundle_name: str | None = None
    timestamped: bool = True
    write_json: bool = True
    write_csv: bool = False
    manifest_name: str = "manifest.json"
    results_name: str = "results.json"
    csv_name: str = "results.csv"
    on_error: str = "abort"
    sanitize_formulas: bool = True
    sanitize_guard: str = "'"

    def __post_init__(self) -> None:
        self.base_path: Path = Path(self.base_path)
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        if not self.sanitize_guard:
            self.sanitize_guard = "'"
        if len(self.sanitize_guard) != 1:
            raise ValueError("sanitize_guard must be a single character")
        if not self.sanitize_formulas:
            logger.warning("Local bundle CSV sanitization disabled; outputs may trigger spreadsheet formulas.")

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        metadata = metadata or {}
        timestamp = datetime.now(timezone.utc)
        try:
            bundle_dir = self._resolve_bundle_dir(metadata, timestamp)
            bundle_dir.mkdir(parents=True, exist_ok=True)

            manifest = self._build_manifest(results, metadata, timestamp)
            manifest_path = bundle_dir / self.manifest_name
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

            if self.write_json:
                results_path = bundle_dir / self.results_name
                results_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")

            if self.write_csv:
                csv_path = bundle_dir / self.csv_name
                csv_sink = CsvResultSink(
                    path=str(csv_path),
                    overwrite=True,
                    sanitize_formulas=self.sanitize_formulas,
                    sanitize_guard=self.sanitize_guard,
                )
                csv_sink.write(results, metadata=metadata)
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Local bundle sink failed; skipping bundle creation: %s", exc)
                return
            raise

    # ------------------------------------------------------------------ helpers
    def _resolve_bundle_dir(self, metadata: dict[str, Any], timestamp: datetime) -> Path:
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "experiment")
        if self.timestamped:
            stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
            name = f"{name}_{stamp}"
        # base_path is guaranteed to be Path after __post_init__
        return Path(self.base_path) / name

    def _build_manifest(self, results: dict[str, Any], metadata: dict[str, Any], timestamp: datetime) -> dict[str, Any]:
        manifest = {
            "generated_at": timestamp.isoformat(),
            "rows": len(results.get("results", [])),
            "metadata": metadata,
            "sanitization": {
                "enabled": self.sanitize_formulas,
                "guard": self.sanitize_guard,
            },
        }
        if "aggregates" in results:
            manifest["aggregates"] = results["aggregates"]
        if "cost_summary" in results:
            manifest["cost_summary"] = results["cost_summary"]
        if results.get("results"):
            manifest["columns"] = sorted({key for row in results["results"] for key in row.get("row", {}).keys()})
        return manifest

    def produces(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def consumes(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(self, artifacts, *, metadata=None):  # pragma: no cover - optional cleanup
        return None
