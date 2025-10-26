"""Local CSV datasource for sample suites and offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource


class CSVDataSource(BaseCSVDataSource):
    """Local CSV datasource - inherits all functionality from BaseCSVDataSource.

    Security policy: Datasources are trusted to downgrade (can operate at lower security levels).
    This allows a SECRET-cleared datasource to filter/sanitize data for OFFICIAL pipelines.
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
        determinism_level: DeterminismLevel | None = None,
        schema: dict[str, str | dict[str, Any]] | None = None,
        infer_schema: bool = True,
        retain_local: bool,  # REQUIRED - no default
        retain_local_path: str | None = None,
    ) -> None:
        """Initialize CSV datasource with hard-coded security policy.

        ADR-002-B: Security policy is immutable. CSV datasources operate at UNOFFICIAL level
        and can be trusted to downgrade (filter/sanitize data for lower-security pipelines).
        """
        super().__init__(
            path=path,
            base_path=base_path,
            allowed_base_path=allowed_base_path,
            dtype=dtype,
            encoding=encoding,
            on_error=on_error,
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
            determinism_level=determinism_level,
            schema=schema,
            infer_schema=infer_schema,
            retain_local=retain_local,
            retain_local_path=retain_local_path,
        )

    @property
    def datasource_type(self) -> str:
        """Specify datasource type for log messages."""
        return "CSV"


__all__ = ["CSVDataSource"]
