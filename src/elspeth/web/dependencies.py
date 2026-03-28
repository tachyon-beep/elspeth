"""FastAPI dependency injection providers.

Sub-1 provides only get_settings().  Service dependencies are added
as Sub-2 through Sub-5 land.

Service construction order follows
docs/superpowers/specs/2026-03-28-web-ux-seam-contracts.md.
ProgressBroadcaster and event-loop reference are created in the lifespan()
async context manager (not in the synchronous create_app()), per the seam
contract for async service wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from elspeth.web.config import WebSettings

if TYPE_CHECKING:
    from elspeth.web.catalog.service import CatalogServiceImpl


def get_settings(request: Request) -> WebSettings:
    """Retrieve application settings from app state.

    Intended for use as a FastAPI Depends() provider.
    """
    settings: WebSettings = request.app.state.settings
    return settings


def create_catalog_service() -> CatalogServiceImpl:
    """Create CatalogService backed by the shared PluginManager singleton.

    get_shared_plugin_manager() returns an already-initialized manager
    (with register_builtin_plugins() called). CatalogServiceImpl does
    not re-initialize — it caches the existing plugin lists.
    """
    from elspeth.plugins.infrastructure.manager import get_shared_plugin_manager
    from elspeth.web.catalog.service import CatalogServiceImpl

    return CatalogServiceImpl(get_shared_plugin_manager())
