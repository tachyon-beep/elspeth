"""Base class for CSV datasources with shared functionality."""

from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Type

import pandas as pd

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.protocols import DataSource
from elspeth.core.base.schema import DataFrameSchema, infer_schema_from_dataframe, schema_from_config
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.security import ensure_determinism_level

logger = logging.getLogger(__name__)


class BaseCSVDataSource(BasePlugin, DataSource):
    """Base class for CSV datasources with common functionality.

    Inherits from BasePlugin to provide security enforcement (ADR-002-B).

    **IMPORTANT**: security_level and allow_downgrade are internal parameters for subclass
    use only. Subclasses MUST hard-code these values per ADR-002-B immutable policy.
    They are NOT exposed in YAML configuration.
    """

    def __init__(
        self,
        *,
        path: str | Path,
        base_path: str | Path | None = None,
        allowed_base_path: str | Path | None = None,
        dtype: dict[str, Any] | None = None,
        encoding: str = "utf-8",
        on_error: str = "abort",
        security_level: SecurityLevel,  # ADR-002-B: Required - subclasses must hard-code (no default to prevent backdoor)
        allow_downgrade: bool,  # ADR-002-B: Required - subclasses must hard-code explicit policy
        determinism_level: DeterminismLevel | None = None,
        schema: dict[str, str | dict[str, Any]] | None = None,
        infer_schema: bool = True,
        retain_local: bool,  # REQUIRED - no default
        retain_local_path: str | None = None,
    ):
        # Initialize BasePlugin with security level and downgrade policy (ADR-002-B)
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)

        # Resolve input path relative to base_path or ELSPETH_INPUTS_DIR when provided
        raw_path = Path(path) if isinstance(path, str) else path
        base_candidate: Path | None = None
        if base_path is not None:
            base_candidate = Path(base_path)
        elif inp := os.environ.get("ELSPETH_INPUTS_DIR"):
            base_candidate = Path(inp)
        elif allowed_base_path is not None:
            base_candidate = Path(allowed_base_path)

        if raw_path.is_absolute():
            raw_path = raw_path.resolve()
        else:
            if base_candidate is None:
                base_candidate = Path.cwd()
            raw_path = (base_candidate / raw_path).resolve()

        self.allowed_base_path = Path(allowed_base_path).resolve() if allowed_base_path else None
        if self.allowed_base_path is not None:
            try:
                within = raw_path.is_relative_to(self.allowed_base_path)
            except ValueError as exc:
                # Normalize Path-related incompatibilities as ValueError with context
                raise ValueError(f"Invalid CSV datasource path resolution: {exc}") from exc
            except Exception:  # pragma: no cover - unexpected Path error
                logger.exception("Unexpected exception during CSV datasource path containment check")
                raise
            if not within:
                raise ValueError(
                    f"CSV datasource path '{raw_path}' escapes allowed base '{self.allowed_base_path}'",
                )
        self.path = raw_path
        self.dtype = dtype
        self.encoding = encoding
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        # security_level is now set by BasePlugin.__init__() (ADR-004)
        self.determinism_level = ensure_determinism_level(determinism_level)
        self.schema_config = schema
        self.infer_schema = infer_schema
        self.retain_local = retain_local
        self.retain_local_path = retain_local_path
        self._cached_schema: Type[DataFrameSchema] | None = None
        self._df_loaded = False

    @property
    def datasource_type(self) -> str:
        """Override in subclass to specify datasource type for messages."""
        return "CSV"

    def load(self) -> pd.DataFrame:
        """Load CSV file with optional logging and retention."""
        plugin_logger = getattr(self, "plugin_logger", None)

        # Log file check
        self._log_file_check(plugin_logger)

        # Check file exists
        if not self.path.exists():
            return self._handle_missing_file(plugin_logger)

        # Load CSV
        start_time = time.time()
        try:
            df = self._read_csv()
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level

            duration_ms = (time.time() - start_time) * 1000

            # Attach schema
            schema = self.output_schema()
            if schema:
                df.attrs["schema"] = schema
                logger.debug("Attached schema %s to DataFrame from %s", schema.__name__, self.path)
                self._log_schema_attached(plugin_logger, schema)

            # Log successful load
            self._log_load_success(plugin_logger, df, duration_ms, schema)

            # Retain local copy if requested
            if self.retain_local:
                local_path = self._copy_to_audit_location()
                df.attrs["retained_local_path"] = str(local_path)
                logger.info("Retained local copy of source data: %s", local_path)
                self._log_retention(plugin_logger, df, local_path)

            self._df_loaded = True
            return df
        except (OSError, ValueError, pd.errors.ParserError, RuntimeError) as exc:
            return self._handle_load_error(plugin_logger, exc)

    def _read_csv(self) -> pd.DataFrame:
        """Read CSV file. Override for custom reading logic."""
        # Pandas dtype parameter has strict typing; our dict[str, Any] is compatible at runtime
        return pd.read_csv(self.path, dtype=self.dtype, encoding=self.encoding)  # type: ignore[arg-type]

    def _handle_missing_file(self, plugin_logger) -> pd.DataFrame:
        """Handle missing file based on on_error strategy."""
        if plugin_logger:
            plugin_logger.log_error(
                f"CSV file not found: {self.path}",
                context=f"{self.datasource_type} datasource load",
                recoverable=(self.on_error == "skip"),
            )

        if self.on_error == "skip":
            logger.warning("%s datasource missing file '%s'; returning empty dataset", self.datasource_type, self.path)
            df = pd.DataFrame()
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level
            df.attrs["schema"] = self.output_schema()
            return df

        raise FileNotFoundError(f"{self.datasource_type} datasource file not found: {self.path}")

    def _handle_load_error(self, plugin_logger, exc: OSError | ValueError | pd.errors.ParserError | RuntimeError) -> pd.DataFrame:
        """Handle errors during CSV loading.

        Args:
            plugin_logger: Optional plugin logger for error tracking
            exc: The specific exception that occurred during loading

        Returns:
            Empty DataFrame if on_error='skip', otherwise re-raises the exception

        Raises:
            OSError: For file access errors
            ValueError: For data type conversion errors
            pd.errors.ParserError: For CSV parsing errors
            RuntimeError: For other runtime errors during loading
        """
        if plugin_logger:
            plugin_logger.log_error(
                exc,
                context=f"{self.datasource_type} datasource load",
                recoverable=(self.on_error == "skip"),
            )

        if self.on_error == "skip":
            logger.warning("%s datasource failed; returning empty dataset: %s", self.datasource_type, exc)
            df = pd.DataFrame()
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level
            df.attrs["schema"] = self.output_schema()
            return df
        raise exc

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
        try:
            shutil.copy2(self.path, dest_path)
            logger.debug("Copied source file %s to %s (%d bytes)", self.path, dest_path, dest_path.stat().st_size)
        except OSError as exc:
            logger.error("Failed to copy source file to audit location: %s", exc)
            raise

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
            logger.debug("Built schema from config for %s: %s", self.path, schema_name)
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
                    logger.debug("Inferred schema for %s: %s", self.path, schema_name)
                    return self._cached_schema
            except (OSError, ValueError, pd.errors.ParserError, RuntimeError) as exc:
                logger.warning("Failed to infer schema from %s: %s", self.path, exc)
                return None

        # No schema available
        return None

    def _log_file_check(self, plugin_logger):
        """Log file check event."""
        if plugin_logger:
            plugin_logger.log_datasource_event(
                "checking_file",
                source_path=str(self.path),
                metadata={"encoding": self.encoding},
            )

    def _log_schema_attached(self, plugin_logger, schema):
        """Log schema attachment event."""
        if plugin_logger:
            plugin_logger.log_datasource_event(
                "schema_attached",
                schema=schema.__name__,
                source_path=str(self.path),
            )

    def _log_load_success(self, plugin_logger, df: pd.DataFrame, duration_ms: float, schema):
        """Log successful load event."""
        if plugin_logger:
            plugin_logger.log_datasource_event(
                "loaded",
                rows=len(df),
                columns=len(df.columns),
                source_path=str(self.path),
                duration_ms=duration_ms,
                schema=schema.__name__ if schema else None,
            )

    def _log_retention(self, plugin_logger, df: pd.DataFrame, local_path: Path):
        """Log data retention event."""
        if plugin_logger:
            plugin_logger.log_event(
                "data_retained",
                message=f"Retained local copy: {local_path}",
                metrics={"rows": len(df), "bytes": local_path.stat().st_size if local_path.exists() else 0},
                metadata={"local_path": str(local_path)},
            )
