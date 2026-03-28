"""FastAPI dependency injection providers.

Each phase adds its service dependency here.  Phase 1 provides only
get_settings().  Service stubs are added as phases 2-5 land.

Service construction order follows specs/2026-03-28-web-ux-seam-contracts.md.
ProgressBroadcaster and event-loop reference are created in the lifespan()
async context manager (not in the synchronous create_app()), per the seam
contract for async service wiring.
"""

from __future__ import annotations

from fastapi import Request

from elspeth.web.config import WebSettings


def get_settings(request: Request) -> WebSettings:
    """Retrieve application settings from app state.

    Intended for use as a FastAPI Depends() provider.
    """
    settings: WebSettings = request.app.state.settings
    return settings
