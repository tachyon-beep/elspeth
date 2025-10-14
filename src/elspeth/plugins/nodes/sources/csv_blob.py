"""CSV-backed stand-in for blob datasource connections."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Type

import pandas as pd

from elspeth.core.protocols import DataSource
from elspeth.core.schema import DataFrameSchema, infer_schema_from_dataframe, schema_from_config
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


class CSVBlobDataSource(DataSource):
    """Mimics blob CSV ingestion by reading from a local file path."""

    def __init__(
        self,
        *,
        path: str | Path,
        dtype: dict[str, Any] | None = None,
        encoding: str = "utf-8",
        on_error: str = "abort",
        security_level: str | None = None,
        determinism_level: str | None = None,
        schema: dict[str, str | dict[str, Any]] | None = None,
        infer_schema: bool = True,
        retain_local: bool,  # REQUIRED - no default
        retain_local_path: str | None = None,
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
        self.retain_local = retain_local
        self.retain_local_path = retain_local_path
        self._cached_schema: Type[DataFrameSchema] | None = None
        self._df_loaded = False

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            if self.on_error == "skip":
                logger.warning("CSV blob datasource missing file '%s'; returning empty dataset", self.path)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                df.attrs["determinism_level"] = self.determinism_level
                df.attrs["schema"] = self.output_schema()
                return df
            raise FileNotFoundError(f"CSV blob datasource file not found: {self.path}")
        try:
            # Pandas dtype parameter has strict typing; our dict[str, Any] is compatible at runtime
            df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding)  # type: ignore[arg-type]
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level

            # Attach schema to DataFrame
            schema = self.output_schema()
            if schema:
                df.attrs["schema"] = schema
                logger.debug(f"Attached schema {schema.__name__} to DataFrame from {self.path}")

            # Retain local copy if requested
            if self.retain_local:
                local_path = self._copy_to_audit_location()
                df.attrs["retained_local_path"] = str(local_path)
                logger.info("Retained local copy of source data: %s", local_path)

            self._df_loaded = True
            return df
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("CSV blob datasource failed; returning empty dataset: %s", exc)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                df.attrs["determinism_level"] = self.determinism_level
                df.attrs["schema"] = self.output_schema()
                return df
            raise

    def _copy_to_audit_location(self) -> Path:
        """Copy source CSV to audit directory for archival purposes."""
        if self.retain_local_path:
            # Use explicit path if provided
            dest_path = Path(self.retain_local_path)
        else:
            # Auto-generate path with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"source_{self.path.stem}_{timestamp}.csv"
            dest_path = Path("audit_data") / filename

        # Create parent directory
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(self.path, dest_path)
        logger.debug("Copied source file %s to %s (%d bytes)", self.path, dest_path, dest_path.stat().st_size)

        return dest_path

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
                    # Pandas dtype parameter has strict typing; our dict[str, Any] is compatible at runtime
                    df = pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding, nrows=100)  # type: ignore[arg-type]
                    schema_name = f"{self.path.stem}_InferredSchema"
                    self._cached_schema = infer_schema_from_dataframe(df, schema_name)
                    logger.debug(f"Inferred schema for {self.path}: {schema_name}")
                    return self._cached_schema
            except Exception as exc:
                logger.warning(f"Failed to infer schema from {self.path}: {exc}")
                return None

        # No schema available
        return None


__all__ = ["CSVBlobDataSource"]
