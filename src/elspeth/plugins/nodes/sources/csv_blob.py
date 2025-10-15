"""CSV-backed stand-in for blob datasource connections."""

from __future__ import annotations

from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource


class CSVBlobDataSource(BaseCSVDataSource):
    """Mimics blob CSV ingestion by reading from a local file path."""

    @property
    def datasource_type(self) -> str:
        """Specify datasource type for log messages."""
        return "CSV blob"


__all__ = ["CSVBlobDataSource"]
