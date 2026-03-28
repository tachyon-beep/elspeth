"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from elspeth.web.catalog.routes import catalog_router
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import create_catalog_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Async lifespan context manager for the FastAPI application.

    Services that require a running event loop must be constructed here,
    not in the synchronous create_app() function.

    Sub-1: stub -- no async services yet.
    Sub-5 will construct ProgressBroadcaster here using
    asyncio.get_running_loop().
    """
    yield


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Web application settings. Constructs defaults if None.

    Returns:
        Configured FastAPI instance with CORS middleware and health endpoint.
    """
    if settings is None:
        settings = WebSettings()

    app = FastAPI(title="ELSPETH Web", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings

    # --- Catalog ---
    app.state.catalog_service = create_catalog_service()
    app.include_router(catalog_router, prefix="/api/catalog")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
