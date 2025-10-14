"""Plugin wrapping the existing blob loader."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from elspeth.adapters import load_blob_csv
from elspeth.core.protocols import DataSource
from elspeth.core.security import normalize_determinism_level, normalize_security_level

logger = logging.getLogger(__name__)


class BlobDataSource(DataSource):
    def __init__(
        self,
        *,
        config_path: str,
        profile: str = "default",
        pandas_kwargs: dict[str, Any] | None = None,
        on_error: str = "abort",
        security_level: str | None = None,
        determinism_level: str | None = None,
        retain_local: bool,  # REQUIRED - no default
        retain_local_path: str | None = None,
    ):
        self.config_path = config_path
        self.profile = profile
        self.pandas_kwargs = pandas_kwargs or {}
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self.on_error = on_error
        self.security_level = normalize_security_level(security_level)
        self.determinism_level = normalize_determinism_level(determinism_level)
        self.retain_local = retain_local
        self.retain_local_path = retain_local_path

    def load(self) -> pd.DataFrame:
        try:
            df = load_blob_csv(
                self.config_path,
                profile=self.profile,
                pandas_kwargs=self.pandas_kwargs,
            )
            df.attrs["security_level"] = self.security_level
            df.attrs["determinism_level"] = self.determinism_level

            # Retain local copy if requested
            if self.retain_local:
                local_path = self._save_local_copy(df)
                df.attrs["retained_local_path"] = str(local_path)
                logger.info("Retained local copy of source data: %s (%d rows)", local_path, len(df))

            # load_blob_csv return type not fully annotated; returns DataFrame at runtime
            return df  # type: ignore[no-any-return]
        except Exception as exc:
            if self.on_error == "skip":
                logger.warning("Blob datasource failed; returning empty dataset: %s", exc)
                df = pd.DataFrame()
                df.attrs["security_level"] = self.security_level
                df.attrs["determinism_level"] = self.determinism_level
                return df
            raise

    def _save_local_copy(self, df: pd.DataFrame) -> Path:
        """Save DataFrame to local file for archival/audit purposes."""
        if self.retain_local_path:
            # Use explicit path if provided
            path = Path(self.retain_local_path)
        else:
            # Auto-generate path with timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"source_data_{self.profile}_{timestamp}.csv"
            path = Path("audit_data") / filename

        # Create parent directory
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save CSV
        df.to_csv(path, index=False)
        logger.debug("Saved %d rows to %s (%d bytes)", len(df), path, path.stat().st_size)

        return path
