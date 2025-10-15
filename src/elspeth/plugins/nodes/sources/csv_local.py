"""Local CSV datasource for sample suites and offline runs."""

from __future__ import annotations

from elspeth.plugins.nodes.sources._csv_base import BaseCSVDataSource


class CSVDataSource(BaseCSVDataSource):
    """Local CSV datasource - inherits all functionality from BaseCSVDataSource."""

    @property
    def datasource_type(self) -> str:
        """Specify datasource type for log messages."""
        return "CSV"


__all__ = ["CSVDataSource"]
