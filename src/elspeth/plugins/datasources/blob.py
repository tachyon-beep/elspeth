"""Plugin wrapping the existing blob loader."""

from __future__ import annotations

from typing import Any, Dict

import logging

import pandas as pd

from elspeth.core.interfaces import DataSource
from elspeth.core.security import normalize_security_level
from elspeth.datasources import load_blob_csv


logger = logging.getLogger(__name__)


class BlobDataSource(DataSource):
    def __init__(
        self,
        *,
        config_path: str,
        profile: str = "default",
        pandas_kwargs: Dict[str, Any] | None = None,
        on_error: str = "abort",
        security_level: str | None = None,
    ):
        self.config_path = config_path
        self.profile = profile
        self.pandas_kwargs = pandas_kwargs or {}
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.security_level = normalize_security_level(security_level)

    def load(self) -> pd.DataFrame:
        try:
            df = load_blob_csv(
                self.config_path,
                profile=self.profile,
                pandas_kwargs=self.pandas_kwargs,
            )
            df.attrs["security_level"] = self.security_level
            return df
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Blob datasource failed; returning empty dataset: %s", exc)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                return df
            raise
