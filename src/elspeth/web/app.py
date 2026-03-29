"""FastAPI application factory."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine

from elspeth.web.auth.local import LocalAuthProvider
from elspeth.web.auth.protocol import AuthProvider
from elspeth.web.auth.routes import create_auth_router
from elspeth.web.catalog.routes import catalog_router
from elspeth.web.composer import yaml_generator as yaml_generator_module
from elspeth.web.composer.service import ComposerServiceImpl
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import create_catalog_service
from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.routes import create_execution_router
from elspeth.web.execution.service import ExecutionServiceImpl
from elspeth.web.middleware.rate_limit import ComposerRateLimiter
from elspeth.web.sessions.migrations import run_migrations
from elspeth.web.sessions.protocol import RunAlreadyActiveError
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Async lifespan context manager for the FastAPI application.

    Services that require a running event loop must be constructed here,
    not in the synchronous create_app() function. The ProgressBroadcaster
    captures asyncio.get_running_loop() and the ExecutionServiceImpl
    depends on both the broadcaster and the loop.
    """
    import asyncio

    import structlog

    slog = structlog.get_logger()

    # Cancel runs orphaned by a previous server crash (D5)
    settings: WebSettings = app.state.settings
    session_service = app.state.session_service
    cancelled = await session_service.cancel_all_orphaned_runs(
        max_age_seconds=settings.orphan_run_max_age_seconds,
    )
    if cancelled:
        slog.info("cancelled_orphaned_runs", count=cancelled)

    # Sub-5: Construct ProgressBroadcaster and ExecutionServiceImpl
    # These require a running event loop, which is only available here.
    loop = asyncio.get_running_loop()
    broadcaster = ProgressBroadcaster(loop)
    app.state.broadcaster = broadcaster

    execution_service = ExecutionServiceImpl(
        loop=loop,
        broadcaster=broadcaster,
        settings=settings,
        session_service=session_service,
        yaml_generator=yaml_generator_module,
    )
    app.state.execution_service = execution_service

    yield

    # Shutdown execution service thread pool
    execution_service.shutdown()


def _settings_from_env() -> WebSettings:
    """Construct WebSettings from ELSPETH_WEB__* environment variables.

    Called when create_app() is invoked without explicit settings (e.g.,
    by uvicorn's factory protocol). The CLI sets these env vars before
    calling uvicorn.run().
    """
    kwargs: dict[str, str] = {}
    prefix = "ELSPETH_WEB__"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            field_name = key[len(prefix) :].lower()
            kwargs[field_name] = value
    return WebSettings(**kwargs)


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Web application settings. When None, reads from
            ELSPETH_WEB__* environment variables (set by the CLI).

    Returns:
        Configured FastAPI instance with CORS middleware and health endpoint.
    """
    if settings is None:
        settings = _settings_from_env()

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
    run_migrations(session_engine)

    session_service = SessionServiceImpl(session_engine)
    app.state.session_service = session_service

    # --- Composer service (singleton, not per-request) ---
    app.state.composer_service = ComposerServiceImpl(
        catalog=app.state.catalog_service,
        settings=settings,
    )
    app.state.composer_availability = app.state.composer_service.get_availability()

    # --- Rate limiter (per-process in-memory) ---
    app.state.rate_limiter = ComposerRateLimiter(
        limit=settings.composer_rate_limit_per_minute,
    )

    # --- Multi-worker enforcement (W10 -> R6) ---
    if "WEB_CONCURRENCY" in os.environ:
        web_concurrency = int(os.environ["WEB_CONCURRENCY"])
    else:
        web_concurrency = 1
    if web_concurrency > 1:
        raise RuntimeError(
            f"WEB_CONCURRENCY={web_concurrency} is not supported. "
            "ProgressBroadcaster holds subscriber queues in process memory — "
            "WebSocket progress streaming requires a single worker. "
            "Set WEB_CONCURRENCY=1 or remove the variable. "
            "For multi-worker deployment, replace ProgressBroadcaster with Redis Streams."
        )

    # --- Register routers ---
    app.include_router(create_auth_router())
    app.include_router(create_session_router())
    app.include_router(create_execution_router())

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

    @app.get("/api/system/status")
    async def system_status() -> dict[str, object]:
        composer = app.state.composer_availability
        return {
            "composer_available": composer.available,
            "composer_model": composer.model,
            "composer_provider": composer.provider,
            "composer_reason": composer.reason,
            "composer_missing_keys": list(composer.missing_keys),
        }

    # --- Static file serving for the React SPA (production) ---
    # Mount frontend/dist/ AFTER all API and WS routes so /api/* takes precedence.
    # Only active when the build output exists (i.e., after `npm run build`).
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="spa")

    return app
