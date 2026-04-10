"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import json
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
from elspeth.web.blobs.routes import create_blobs_router
from elspeth.web.blobs.service import BlobServiceImpl
from elspeth.web.catalog.routes import catalog_router
from elspeth.web.composer import yaml_generator as yaml_generator_module
from elspeth.web.composer.service import ComposerServiceImpl
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import create_catalog_service
from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.routes import create_execution_router
from elspeth.web.execution.service import ExecutionServiceImpl
from elspeth.web.middleware.rate_limit import ComposerRateLimiter
from elspeth.web.secrets.routes import create_secrets_router
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.service import WebSecretService
from elspeth.web.secrets.user_store import UserSecretStore
from elspeth.web.sessions.migrations import run_migrations
from elspeth.web.sessions.protocol import RunAlreadyActiveError
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl


async def _periodic_orphan_cleanup(
    session_service: SessionServiceImpl,
    *,
    interval_seconds: int,
    max_age_seconds: int,
) -> None:
    """Background task that periodically cancels orphaned runs.

    Runs orphaned by SIGKILL, OOM, or other unclean termination leave
    sessions permanently blocked (partial unique index on active runs).
    Startup cleanup handles the bulk case, but if the server runs for
    days/weeks without restart, this catches runs orphaned mid-uptime.

    Uses max_age_seconds (not None) because a run younger than the
    threshold may still be legitimately executing in a background thread.
    """
    import structlog

    slog = structlog.get_logger()
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            cancelled = await session_service.cancel_all_orphaned_runs(
                max_age_seconds=max_age_seconds,
            )
            if cancelled:
                slog.info("periodic_orphan_cleanup", cancelled=cancelled)
        except Exception:
            slog.error("periodic_orphan_cleanup_failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Async lifespan context manager for the FastAPI application.

    Services that require a running event loop must be constructed here,
    not in the synchronous create_app() function. The ProgressBroadcaster
    captures asyncio.get_running_loop() and the ExecutionServiceImpl
    depends on both the broadcaster and the loop.
    """
    import structlog

    slog = structlog.get_logger()

    # Cancel runs orphaned by a previous server crash (D5).
    # Single-process server: every non-terminal run is orphaned after restart.
    # No age filter — cancel ALL pending/running runs immediately.
    settings: WebSettings = app.state.settings
    session_service = app.state.session_service
    cancelled = await session_service.cancel_all_orphaned_runs()
    if cancelled:
        slog.info("cancelled_orphaned_runs", count=cancelled)

    # Resolve OIDC authorization_endpoint from discovery or explicit config
    if settings.auth_provider in ("oidc", "entra"):
        if settings.oidc_authorization_endpoint:
            app.state.oidc_authorization_endpoint = settings.oidc_authorization_endpoint
        else:
            import httpx

            if settings.oidc_issuer:
                issuer = settings.oidc_issuer.rstrip("/")
            elif settings.auth_provider == "entra" and settings.entra_tenant_id:
                issuer = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
            else:
                raise SystemExit("FATAL: OIDC discovery requires either oidc_issuer or entra_tenant_id to derive the issuer URL.")
            discovery_url = f"{issuer}/.well-known/openid-configuration"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                    resp = await client.get(discovery_url)
                    resp.raise_for_status()
                    doc = resp.json()
                    app.state.oidc_authorization_endpoint = doc["authorization_endpoint"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise SystemExit(
                    f"FATAL: OIDC discovery failed for issuer {issuer!r}: {exc}. "
                    f"Either fix the issuer URL or set oidc_authorization_endpoint explicitly."
                ) from exc

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
        blob_service=app.state.blob_service,
        secret_service=app.state.secret_service,
    )
    app.state.execution_service = execution_service

    # Periodic orphan cleanup — catches runs orphaned by SIGKILL/OOM
    # between restarts. Startup cleanup (above) handles the bulk case;
    # this catches runs orphaned while the server is still running.
    orphan_task = asyncio.create_task(
        _periodic_orphan_cleanup(
            session_service,
            interval_seconds=settings.orphan_run_check_interval_seconds,
            max_age_seconds=settings.orphan_run_max_age_seconds,
        )
    )

    yield

    # Cancel periodic cleanup before shutting down the executor
    orphan_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await orphan_task

    # Shutdown execution service thread pool
    execution_service.shutdown()


def _settings_from_env() -> WebSettings:
    """Construct WebSettings from ELSPETH_WEB__* environment variables.

    Called when create_app() is invoked without explicit settings (e.g.,
    by uvicorn's factory protocol). The CLI sets these env vars before
    calling uvicorn.run().
    """
    kwargs: dict[str, object] = {}
    prefix = "ELSPETH_WEB__"
    for key, value in os.environ.items():
        if key.startswith(prefix):
            field_name = key[len(prefix) :].lower()
            # Attempt JSON decode for non-scalar types (tuples, lists).
            # E.g. ELSPETH_WEB__CORS_ORIGINS='["https://app.example.com"]'
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    kwargs[field_name] = tuple(parsed)
                else:
                    kwargs[field_name] = parsed
            except (json.JSONDecodeError, ValueError):
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

    # Ensure data directory and subdirectories exist before any DB access.
    # get_landscape_url() defaults to data_dir/runs/audit.db — SQLite does
    # not create parent directories, so we must ensure runs/ exists too.
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "runs").mkdir(exist_ok=True)

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
    app.state.oidc_authorization_endpoint = None  # Set by lifespan for OIDC/Entra

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

    session_service = SessionServiceImpl(session_engine, data_dir=settings.data_dir)
    app.state.session_service = session_service

    # --- Blob service ---
    app.state.blob_service = BlobServiceImpl(
        session_engine,
        settings.data_dir,
        settings.max_blob_storage_per_session_bytes,
    )

    # --- Secret service ---
    user_secret_store = UserSecretStore(session_engine, settings.secret_key)
    server_secret_store = ServerSecretStore(settings.server_secret_allowlist)
    app.state.secret_service = WebSecretService(user_secret_store, server_secret_store)

    # --- Composer service (singleton, not per-request) ---
    app.state.composer_service = ComposerServiceImpl(
        catalog=app.state.catalog_service,
        settings=settings,
        session_engine=session_engine,
        secret_service=app.state.secret_service,
    )
    app.state.composer_availability = app.state.composer_service.get_availability()

    # --- Rate limiter (per-process in-memory) ---
    app.state.rate_limiter = ComposerRateLimiter(
        limit=settings.composer_rate_limit_per_minute,
    )

    # --- Multi-worker enforcement (W10 -> R6) ---
    # ProgressBroadcaster and the rate limiter are process-local, so
    # multi-worker mode is unsupported.  Check multiple signals because
    # different deployment tools advertise workers in different ways.
    multi_worker_reason: str | None = None

    # 1. WEB_CONCURRENCY env var (Heroku, Railway, render.com)
    web_concurrency_str = os.environ.get("WEB_CONCURRENCY", "1")
    try:
        if int(web_concurrency_str) > 1:
            multi_worker_reason = f"WEB_CONCURRENCY={web_concurrency_str}"
    except ValueError:
        pass

    # 2. sys.argv: uvicorn --workers N, gunicorn -w N / --workers N
    if multi_worker_reason is None:
        argv = sys.argv
        for i, arg in enumerate(argv):
            if arg == "--workers" and i + 1 < len(argv):
                try:
                    if int(argv[i + 1]) > 1:
                        multi_worker_reason = f"--workers {argv[i + 1]}"
                except ValueError:
                    pass
            elif arg.startswith("--workers="):
                try:
                    if int(arg.split("=", 1)[1]) > 1:
                        multi_worker_reason = f"{arg}"
                except ValueError:
                    pass
            elif arg == "-w" and i + 1 < len(argv):
                try:
                    if int(argv[i + 1]) > 1:
                        multi_worker_reason = f"-w {argv[i + 1]}"
                except ValueError:
                    pass

    if multi_worker_reason is not None:
        raise RuntimeError(
            f"Multi-worker mode detected ({multi_worker_reason}) but is not supported. "
            "ProgressBroadcaster holds subscriber queues in process memory — "
            "WebSocket progress streaming requires a single worker. "
            "For multi-worker deployment, replace ProgressBroadcaster with Redis Streams."
        )

    # --- Register routers ---
    app.include_router(create_auth_router())
    app.include_router(create_session_router())
    app.include_router(create_blobs_router())
    app.include_router(create_secrets_router())
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
