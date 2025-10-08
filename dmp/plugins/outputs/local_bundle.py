"""Filesystem bundle sink for archiving experiment outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import logging

from dmp.core.interfaces import ResultSink
from dmp.plugins.outputs.csv_file import CsvResultSink


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

    def __post_init__(self) -> None:
        self.base_path = Path(self.base_path)
        if self.on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
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
                csv_sink = CsvResultSink(path=csv_path, overwrite=True)
                csv_sink.write(results, metadata=metadata)
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Local bundle sink failed; skipping bundle creation: %s", exc)
                return
            raise

    # ------------------------------------------------------------------ helpers
    def _resolve_bundle_dir(self, metadata: Dict[str, Any], timestamp: datetime) -> Path:
        name = self.bundle_name or str(metadata.get("experiment") or metadata.get("name") or "experiment")
        if self.timestamped:
            stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
            name = f"{name}_{stamp}"
        return self.base_path / name

    @staticmethod
    def _build_manifest(results: Dict[str, Any], metadata: Dict[str, Any], timestamp: datetime) -> Dict[str, Any]:
        manifest = {
            "generated_at": timestamp.isoformat(),
            "rows": len(results.get("results", [])),
            "metadata": metadata,
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
