"""Result sink that writes results to a local CSV file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from elspeth.core.interfaces import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security import normalize_security_level
from elspeth.plugins.outputs._sanitize import sanitize_cell


logger = logging.getLogger(__name__)


class CsvResultSink(ResultSink):
    def __init__(
        self,
        *,
        path: str,
        overwrite: bool = True,
        on_error: str = "abort",
        sanitize_formulas: bool = True,
        sanitize_guard: str = "'",
    ) -> None:
        self.path = Path(path)
        self.overwrite = overwrite
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        if not sanitize_guard:
            sanitize_guard = "'"
        if len(sanitize_guard) != 1:
            raise ValueError("sanitize_guard must be a single character")
        self.sanitize_formulas = sanitize_formulas
        self.sanitize_guard = sanitize_guard
        if not self.sanitize_formulas:
            logger.warning(
                "CSV sink sanitization disabled; outputs may trigger spreadsheet formulas."
            )
        self._last_written_path: str | None = None
        self._security_level: str | None = None
        self._sanitization = {"enabled": self.sanitize_formulas, "guard": self.sanitize_guard}

    # ------------------------------------------------------------------ helpers
    def _sanitize_key(self, key: Any) -> Any:
        if not self.sanitize_formulas or not isinstance(key, str):
            return key
        return sanitize_cell(key, guard=self.sanitize_guard)

    def _sanitize_value(self, value: Any) -> Any:
        if not self.sanitize_formulas:
            return value
        return sanitize_cell(value, guard=self.sanitize_guard)

    def write(self, results: Dict[str, Any], *, metadata: Dict[str, Any] | None = None) -> None:
        try:
            entries = results.get("results", [])
            if not entries:
                df = pd.DataFrame()
            else:
                rows = []
                for item in entries:
                    row = item.get("row", {})
                    response = item.get("response", {})
                    record: Dict[Any, Any] = {}
                    if isinstance(row, dict):
                        for key, value in row.items():
                            record[self._sanitize_key(key)] = self._sanitize_value(value)
                    record[self._sanitize_key("llm_content")] = self._sanitize_value(
                        response.get("content")
                    )
                    responses = item.get("responses") or {}
                    if isinstance(responses, dict):
                        for name, resp in responses.items():
                            record[self._sanitize_key(f"llm_{name}")] = self._sanitize_value(
                                (resp or {}).get("content")
                            )
                    rows.append(record)
                df = pd.DataFrame(rows)
                if not df.empty:
                    df.columns = [self._sanitize_key(col) for col in df.columns]
            if self.path.exists() and not self.overwrite:
                raise FileExistsError(f"CSV sink destination exists: {self.path}")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(self.path, index=False)
            self._last_written_path = str(self.path)
            if metadata:
                self._security_level = normalize_security_level(metadata.get("security_level"))
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("CSV sink failed; skipping write to '%s': %s", self.path, exc)
                return
            raise

    def produces(self):  # pragma: no cover - placeholder for artifact chaining
        return [
            ArtifactDescriptor(name="csv", type="file/csv", persist=True, alias="csv"),
        ]

    def consumes(self):  # pragma: no cover - placeholder for artifact chaining
        return []

    def finalize(self, artifacts, *, metadata=None):  # pragma: no cover - optional cleanup
        return None

    def collect_artifacts(self) -> Dict[str, Artifact]:  # pragma: no cover - optional
        if not self._last_written_path:
            return {}
        artifact = Artifact(
            id="",
            type="file/csv",
            path=self._last_written_path,
            metadata={
                "path": self._last_written_path,
                "content_type": "text/csv",
                "security_level": self._security_level,
                "sanitization": self._sanitization,
            },
            persist=True,
            security_level=self._security_level,
        )
        self._last_written_path = None
        self._security_level = None
        return {"csv": artifact}
