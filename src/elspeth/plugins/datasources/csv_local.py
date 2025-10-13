"""Local CSV datasource for sample suites and offline runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Type

import pandas as pd

from elspeth.core.interfaces import DataSource
from elspeth.core.schema import DataFrameSchema, infer_schema_from_dataframe, schema_from_config
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


class CSVDataSource(DataSource):
    def __init__(
        self,
        *,
        path: str | Path,
        dtype: Dict[str, Any] | None = None,
        encoding: str = "utf-8",
        on_error: str = "abort",
        security_level: str | None = None,
        determinism_level: str | None = None,
        schema: Dict[str, str | Dict[str, Any]] | None = None,
        infer_schema: bool = True,
    ) -> None:
        self.path = Path(path)
        self.dtype = dtype
        self.encoding = encoding
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.security_level = normalize_security_level(security_level)
        self.determinism_level = normalize_determinism_level(determinism_level)
        self.schema_config = schema
        self.infer_schema = infer_schema
        self._cached_schema: Type[DataFrameSchema] | None = None
        self._df_loaded = False

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            if self.on_error == "skip":
                logger.warning("CSV datasource missing file '%s'; returning empty dataset", self.path)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                df.attrs["determinism_level"] = self.determinism_level
                df.attrs["schema"] = self.output_schema()
                return df
            raise FileNotFoundError(f"CSV datasource file not found: {self.path}")
        try:
            df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding)
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level

            # Attach schema to DataFrame
            schema = self.output_schema()
            if schema:
                df.attrs["schema"] = schema
                logger.debug(f"Attached schema {schema.__name__} to DataFrame from {self.path}")

            self._df_loaded = True
            return df
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("CSV datasource failed; returning empty dataset: %s", exc)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                df.attrs["determinism_level"] = self.determinism_level
                df.attrs["schema"] = self.output_schema()
                return df
            raise

    def output_schema(self) -> Type[DataFrameSchema] | None:
        """
        Return the schema of the DataFrame this datasource produces.

        Priority:
        1. If schema provided in config, use schema_from_config()
        2. If infer_schema=True and CSV loaded, infer from DataFrame
        3. Otherwise return None (no schema available)
        """
        # Return cached schema if available
        if self._cached_schema:
            return self._cached_schema

        # Priority 1: Explicit schema from config
        if self.schema_config:
            schema_name = f"{self.path.stem}_ConfigSchema"
            self._cached_schema = schema_from_config(self.schema_config, schema_name)
            logger.debug(f"Built schema from config for {self.path}: {schema_name}")
            return self._cached_schema

        # Priority 2: Infer from DataFrame
        if self.infer_schema and self.path.exists():
            try:
                # Load DataFrame temporarily for inference if not already loaded
                if not self._df_loaded:
                    df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding, nrows=100)
                    schema_name = f"{self.path.stem}_InferredSchema"
                    self._cached_schema = infer_schema_from_dataframe(df, schema_name)
                    logger.debug(f"Inferred schema for {self.path}: {schema_name}")
                    return self._cached_schema
            except Exception as exc:
                logger.warning(f"Failed to infer schema from {self.path}: {exc}")
                return None

        # No schema available
        return None


__all__ = ["CSVDataSource"]
