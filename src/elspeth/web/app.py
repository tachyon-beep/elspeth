"""FastAPI application factory."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine

from elspeth.web.auth.local import LocalAuthProvider
from elspeth.web.auth.protocol import AuthProvider
from elspeth.web.auth.routes import create_auth_router
from elspeth.web.catalog.routes import catalog_router
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import create_catalog_service
from elspeth.web.sessions.models import metadata as session_metadata
from elspeth.web.sessions.protocol import RunAlreadyActiveError
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Async lifespan context manager for the FastAPI application.

    Services that require a running event loop must be constructed here,
    not in the synchronous create_app() function.

    Sub-5 will construct ProgressBroadcaster here using
    asyncio.get_running_loop().
    """
    # Cancel runs orphaned by a previous server crash (D5)
    service = app.state.session_service
    cancelled = await service.cancel_all_orphaned_runs()
    if cancelled:
        import structlog

        structlog.get_logger().info("cancelled_orphaned_runs", count=cancelled)
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

    # --- Auth provider setup ---
    auth_provider: AuthProvider
    if settings.auth_provider == "local":
        auth_provider = LocalAuthProvider(
            db_path=settings.data_dir / "auth.db",
            secret_key=settings.secret_key,
        )
    elif settings.auth_provider == "oidc":
        from elspeth.web.auth.oidc import OIDCAuthProvider

        # Validator _validate_auth_fields guarantees non-None
        assert settings.oidc_issuer is not None
        assert settings.oidc_audience is not None
        auth_provider = OIDCAuthProvider(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
        )
    elif settings.auth_provider == "entra":
        from elspeth.web.auth.entra import EntraAuthProvider

        assert settings.entra_tenant_id is not None
        assert settings.oidc_audience is not None
        auth_provider = EntraAuthProvider(
            tenant_id=settings.entra_tenant_id,
            audience=settings.oidc_audience,
        )
    app.state.auth_provider = auth_provider

    # W16/S3: Secret key production guard -- hard crash
    if settings.secret_key == "change-me-in-production" and "pytest" not in sys.modules and os.environ.get("ELSPETH_ENV") != "test":
        raise SystemExit(
            "FATAL: WebSettings.secret_key is set to the default value. "
            "Set a secure secret_key before starting the web server. "
            "See WebSettings documentation."
        )

    # --- Session database setup ---
    session_db_url = settings.get_session_db_url()
    session_engine = create_engine(session_db_url)
    session_metadata.create_all(session_engine)

    session_service = SessionServiceImpl(session_engine)
    app.state.session_service = session_service

    # --- Register routers ---
    app.include_router(create_auth_router())
    app.include_router(create_session_router())

    # --- Seam contract D: RunAlreadyActiveError -> 409 with error_type ---
    @app.exception_handler(RunAlreadyActiveError)
    async def handle_run_already_active(
        request: Request,
        exc: RunAlreadyActiveError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "error_type": "run_already_active"},
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
