"""CSV-backed stand-in for blob datasource connections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import logging

import pandas as pd

from elspeth.core.interfaces import DataSource
from elspeth.core.security import normalize_security_level


logger = logging.getLogger(__name__)


class CSVBlobDataSource(DataSource):
    """Mimics blob CSV ingestion by reading from a local file path."""

    def __init__(
        self,
        *,
        path: str | Path,
        dtype: Dict[str, Any] | None = None,
        encoding: str = "utf-8",
        on_error: str = "abort",
        security_level: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.dtype = dtype
        self.encoding = encoding
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.security_level = normalize_security_level(security_level)

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            if self.on_error == "skip":
                logger.warning("CSV blob datasource missing file '%s'; returning empty dataset", self.path)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                return df
            raise FileNotFoundError(f"CSV blob datasource file not found: {self.path}")
        try:
            df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding)
            df.attrs["security_level"] = self.security_level
            return df
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("CSV blob datasource failed; returning empty dataset: %s", exc)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                return df
            raise


__all__ = ["CSVBlobDataSource"]
