"""Result sink that writes results to a local CSV file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from elspeth.core.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.security import normalize_security_level
from elspeth.plugins.nodes.sinks._sanitize import sanitize_cell

logger = logging.getLogger(__name__)


class CsvResultSink(ResultSink):
    """Result sink that writes experiment results to CSV files with formula sanitization.

    Converts experiment results into tabular CSV format with configurable sanitization
    to prevent formula injection attacks. Extracts row data, LLM responses, and named
    responses into a flat structure suitable for spreadsheet analysis.

    Features:
    - Automatic formula sanitization (prefix dangerous characters with guard)
    - Configurable overwrite behavior
    - Error handling with abort/skip strategies
    - Artifact tracking with security metadata
    """

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
            logger.warning("CSV sink sanitization disabled; outputs may trigger spreadsheet formulas.")
        self._last_written_path: str | None = None
        self._security_level: str | None = None
        self._sanitization = {
            "enabled": self.sanitize_formulas,
            "guard": self.sanitize_guard,
        }

    # ------------------------------------------------------------------ helpers
    def _sanitize_key(self, key: Any) -> Any:
        if not self.sanitize_formulas or not isinstance(key, str):
            return key
        return sanitize_cell(key, guard=self.sanitize_guard)

    def _sanitize_value(self, value: Any) -> Any:
        if not self.sanitize_formulas:
            return value
        return sanitize_cell(value, guard=self.sanitize_guard)

    def _build_record_from_item(self, item: dict[str, Any]) -> dict[Any, Any]:
        """Extract and sanitize a single record from an experiment item.

        Args:
            item: Experiment result item with row, response, and responses fields

        Returns:
            Sanitized record dictionary ready for DataFrame construction
        """
        record: dict[Any, Any] = {}

        # Extract row data
        row = item.get("row", {})
        if isinstance(row, dict):
            for key, value in row.items():
                record[self._sanitize_key(key)] = self._sanitize_value(value)

        # Extract primary response
        response = item.get("response", {})
        record[self._sanitize_key("llm_content")] = self._sanitize_value(response.get("content"))

        # Extract named responses
        responses = item.get("responses") or {}
        if isinstance(responses, dict):
            for name, resp in responses.items():
                content = (resp or {}).get("content")
                record[self._sanitize_key(f"llm_{name}")] = self._sanitize_value(content)

        return record

    def _results_to_dataframe(self, results: dict[str, Any]) -> pd.DataFrame:
        """Convert experiment results to sanitized DataFrame.

        Args:
            results: Full experiment results dictionary

        Returns:
            Pandas DataFrame with sanitized columns and values
        """
        entries = results.get("results", [])
        if not entries:
            return pd.DataFrame()

        rows = [self._build_record_from_item(item) for item in entries]
        df = pd.DataFrame(rows)

        if not df.empty:
            # Sanitize column names - use Index constructor for proper typing
            sanitized_columns = [self._sanitize_key(col) for col in df.columns]
            df.columns = pd.Index(sanitized_columns)

        return df

    def write(self, results: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> None:
        """Write experiment results to CSV file with sanitization."""
        try:
            df = self._results_to_dataframe(results)

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

    def collect_artifacts(self) -> dict[str, Artifact]:  # pragma: no cover - optional
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
