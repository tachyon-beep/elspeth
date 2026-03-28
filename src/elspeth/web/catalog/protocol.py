"""CatalogService protocol — internal service boundary for plugin catalog."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from elspeth.web.catalog.schemas import PluginSchemaInfo, PluginSummary


@runtime_checkable
class CatalogService(Protocol):
    """Read-only plugin catalog.

    Four methods, all synchronous (plugin discovery is CPU-bound).
    When the Catalog module is later extracted to a microservice,
    this protocol stays and the implementation becomes an HTTP client.
    """

    def list_sources(self) -> list[PluginSummary]: ...

    def list_transforms(self) -> list[PluginSummary]: ...

    def list_sinks(self) -> list[PluginSummary]: ...

    def get_schema(self, plugin_type: str, name: str) -> PluginSchemaInfo: ...
