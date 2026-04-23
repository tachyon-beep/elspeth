"""Tests for session API routes -- CRUD, IDOR, fork, YAML."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.composer.protocol import ComposerPluginCrashError, ComposerResult
from elspeth.web.composer.state import CompositionState, PipelineMetadata
from elspeth.web.config import WebSettings
from elspeth.web.sessions.engine import create_session_engine
from elspeth.web.sessions.migrations import run_migrations
from elspeth.web.sessions.protocol import CompositionStateData
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl

# Sentinel empty state for mock composer responses
_EMPTY_STATE = CompositionState(
    source=None,
    nodes=(),
    edges=(),
    outputs=(),
    metadata=PipelineMetadata(),
    version=1,
)


def _make_composer_mock(
    response_text: str = "Sure, I can help.",
    state: CompositionState | None = None,
) -> AsyncMock:
    """Create a mock ComposerServiceImpl.compose that returns a fixed result."""
    mock = AsyncMock()
    mock.compose = AsyncMock(
        return_value=ComposerResult(
            message=response_text,
            state=state or _EMPTY_STATE,
        ),
    )
    return mock


class _BlockingRecordingComposer:
    """Composer stub that lets tests observe and gate concurrent compose() calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.first_call_started = asyncio.Event()
        self.second_call_started = asyncio.Event()
        self.release_first_call = asyncio.Event()

    async def compose(
        self,
        message: str,
        chat_messages: list[dict[str, object]],
        state: CompositionState,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
    ) -> ComposerResult:
        del state, session_id, user_id

        self.calls.append(
            {
                "message": message,
                "chat_messages": [dict(entry) for entry in chat_messages],
            }
        )

        if len(self.calls) == 1:
            self.first_call_started.set()
            await self.release_first_call.wait()
            reply = "Reply to first"
        else:
            self.second_call_started.set()
            reply = "Reply to second"

        return ComposerResult(message=reply, state=_EMPTY_STATE)


def _make_app(
    tmp_path: Path,
    user_id: str = "alice",
    max_upload_bytes: int = 10 * 1024 * 1024,
) -> tuple[FastAPI, SessionServiceImpl]:
    """Create a test app with session routes and a mock auth user."""
    engine = create_session_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    run_migrations(engine)
    service = SessionServiceImpl(engine)

    app = FastAPI()

    # Override auth dependency to return a fixed user
    identity = UserIdentity(user_id=user_id, username=user_id)

    async def mock_user():
        return identity

    app.dependency_overrides[get_current_user] = mock_user

    # Set up app state
    app.state.session_service = service
    app.state.settings = WebSettings(
        data_dir=tmp_path,
        max_upload_bytes=max_upload_bytes,
        composer_max_composition_turns=15,
        composer_max_discovery_turns=10,
        composer_timeout_seconds=85.0,
        composer_rate_limit_per_minute=10,
    )
    # composer_service is set to None here; tests that POST messages
    # must replace it with a mock before sending requests.
    app.state.composer_service = None

    from unittest.mock import MagicMock

    from elspeth.web.middleware.rate_limit import ComposerRateLimiter

    app.state.rate_limiter = ComposerRateLimiter(limit=100)

    # Minimal mock for execution service — delete_session calls
    # cleanup_session_lock() after archiving.
    app.state.execution_service = MagicMock()

    router = create_session_router()
    app.include_router(router)

    return app, service


class TestSessionCRUDRoutes:
    """Tests for session create, list, get, delete endpoints."""

    def test_create_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.post(
            "/api/sessions",
            json={"title": "My Pipeline"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "My Pipeline"
        assert body["user_id"] == "alice"
        assert "id" in body

    def test_create_session_default_title(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.post("/api/sessions", json={})
        assert response.status_code == 201
        assert response.json()["title"] == "New session"

    def test_list_sessions(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        client.post("/api/sessions", json={"title": "S1"})
        client.post("/api/sessions", json={"title": "S2"})

        response = client.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 2

    def test_get_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post(
            "/api/sessions",
            json={"title": "Test"},
        )
        session_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == session_id

    def test_get_session_not_found(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_delete_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post(
            "/api/sessions",
            json={"title": "To Delete"},
        )
        session_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 204

        # Verify cleanup_session_lock was called with the correct session ID
        app.state.execution_service.cleanup_session_lock.assert_called_once_with(session_id)

        # Verify it's gone
        get_resp = client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_blocked_by_active_run(self, tmp_path) -> None:
        """Deleting a session with a pending/running run returns 409.

        Without this guard, archive_session() deletes run rows and blob
        directories out from under the background pipeline worker.
        """
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post("/api/sessions", json={"title": "Active Run"})
        session_id = uuid.UUID(create_resp.json()["id"])

        # Create a pending run via the service layer
        state = await service.save_composition_state(
            session_id,
            CompositionStateData(is_valid=True),
        )
        await service.create_run(session_id, state.id)

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 409
        assert "active" in del_resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_session_allowed_after_run_completes(self, tmp_path) -> None:
        """After a run reaches a terminal state, deletion is allowed."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post("/api/sessions", json={"title": "Completed Run"})
        session_id = uuid.UUID(create_resp.json()["id"])

        state = await service.save_composition_state(
            session_id,
            CompositionStateData(is_valid=True),
        )
        run = await service.create_run(session_id, state.id)
        await service.update_run_status(run.id, "running")
        await service.update_run_status(run.id, "completed", landscape_run_id="lscp-delete-allowed")

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 204


def _collect_ownership_call_site_identities(module: object, helper_name: str) -> set[str]:
    """Walk ``module``'s AST and return enclosing function names for each call to ``helper_name``.

    Shared implementation for the IDOR drift guards across the three
    session-scoped routers (sessions/, execution/, blobs/).  Each
    router has its own ownership-check helper — the drift guard is
    parametrized per (module, helper) pair so the failure message
    points at one specific inventory that drifted, rather than
    reporting an aggregate mismatch across all three.

    Why a shared walker (not a per-module assertion) — the AST-walking
    logic is identical across routers; duplicating it per drift test
    would itself be a drift surface (a future fix to one copy would
    silently leave the others subtly different).
    """
    import ast

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Build a child->parent map so each call can be attributed to
    # its SMALLEST enclosing function def.  ``ast.walk`` alone would
    # also match the outer factory (``create_session_router`` etc.)
    # — which contains every nested endpoint — bloating the set with
    # a non-endpoint name.  Walking upward from the call to the
    # nearest FunctionDef / AsyncFunctionDef is the only correct way
    # to attribute ownership to the handler that actually contains it.
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    identities: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == helper_name):
            continue
        # Walk up to the nearest function def.  A call outside any
        # function (module level) is a structural anomaly we want the
        # assertion to surface, not silently absorb — so we only
        # record names of function-scoped calls, and let the set
        # comparison below flag any missing endpoint.
        current: ast.AST | None = parents.get(node)
        while current is not None and not isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
            current = parents.get(current)
        if current is not None:
            identities.add(current.name)

    # The helper's own def may contain a self-reference if a future
    # refactor introduces recursion/delegation; drop it explicitly so
    # the drift guard stays focused on ROUTE HANDLERS, not plumbing.
    identities.discard(helper_name)
    return identities


class TestIDORCoverageDrift:
    """Drift guard: every session-scoped endpoint across all three routers must invoke an ownership check.

    ``TestIDORProtection.test_idor_session_crud`` walks one
    cross-session request for each session-scoped endpoint.  The risk
    is that someone adds a new route that calls an ownership-check
    helper but forgets to add a matching IDOR assertion — the
    ownership primitive is in place, but its coverage in this suite
    silently rots.

    Session-scoped endpoints live in three routers, each with its
    own ownership-check helper:

    * ``sessions/routes.py`` via ``_verify_session_ownership`` — the
      chat-and-state endpoints (``GET``/``DELETE``/``POST`` under
      ``/api/sessions/{id}``).
    * ``execution/routes.py`` via ``_verify_session_ownership`` —
      ``/validate`` and ``/execute``.  Also hosts run-scoped endpoints
      which use ``_verify_run_ownership`` (not a session-ownership
      helper, but the same drift risk for run identities; covered by
      a separate inventory).
    * ``blobs/routes.py`` via ``_verify_session_and_get_blob_service``
      — blob upload/list/metadata/download/delete.  This helper is
      dual-role (checks ownership AND returns the service); both
      branches of its callers depend on the ownership check for
      IDOR safety.

    Each (module, helper, inventory) tuple is pinned independently so
    a failure message names exactly which router's audit drifted.  A
    pure count across all three would satisfy ``{add endpoint X in
    router A, drop endpoint Y in router B}`` — the count stays
    constant while the audit silently swaps a covered endpoint for an
    uncovered one in a different router.
    """

    EXPECTED_SESSIONS_OWNERSHIP_ENDPOINTS: frozenset[str] = frozenset(
        {
            "get_session",
            "delete_session",
            "get_messages",
            "send_message",
            "recompose",
            "list_session_runs",
            "get_current_state",
            "get_state_versions",
            "revert_state",
            "get_state_yaml",
            "fork_from_message",
        }
    )

    EXPECTED_EXECUTION_SESSION_OWNERSHIP_ENDPOINTS: frozenset[str] = frozenset(
        {
            "validate_session_pipeline",
            "execute_pipeline",
        }
    )

    EXPECTED_EXECUTION_RUN_OWNERSHIP_ENDPOINTS: frozenset[str] = frozenset(
        {
            "get_run_status",
            "cancel_run",
            "get_run_results",
        }
    )

    EXPECTED_BLOBS_OWNERSHIP_ENDPOINTS: frozenset[str] = frozenset(
        {
            "create_blob_upload",
            "create_blob_inline",
            "list_blobs",
            "get_blob_metadata",
            "download_blob_content",
            "delete_blob",
        }
    )

    @staticmethod
    def _assert_inventory(router_label: str, helper_name: str, expected: frozenset[str], found: set[str]) -> None:
        """Render the drift-diagnostic message and assert set-equality."""
        missing = expected - found
        unexpected = found - expected
        assert found == expected, (
            f"IDOR audit drift detected in {router_label}.\n"
            f"  Expected endpoints calling {helper_name!r}: {sorted(expected)}\n"
            f"  Found: {sorted(found)}\n"
            f"  Missing (endpoint advertised in audit but no call found): {sorted(missing)}\n"
            f"  Unexpected (endpoint calls helper but not in audit inventory): {sorted(unexpected)}\n"
            "Update BOTH the corresponding IDOR assertion walk AND the "
            "inventory here in the SAME commit when endpoints enter or "
            "leave this set. Bumping one without the other leaves the "
            "audit in a lying state — the whole point of this drift "
            "guard is to force the three locations (inventory, "
            "assertion, handler set) to stay in sync."
        )

    def test_sessions_routes_ownership_call_sites(self) -> None:
        """sessions/routes.py — _verify_session_ownership inventory."""
        from elspeth.web.sessions import routes

        found = _collect_ownership_call_site_identities(routes, "_verify_session_ownership")
        self._assert_inventory(
            "sessions/routes.py",
            "_verify_session_ownership",
            self.EXPECTED_SESSIONS_OWNERSHIP_ENDPOINTS,
            found,
        )

    def test_execution_routes_session_ownership_call_sites(self) -> None:
        """execution/routes.py — _verify_session_ownership inventory.

        Independent from the sessions/ inventory because the two
        helpers — while presently sharing a name — are file-local
        symbols.  A symbol rename in one router must not silently
        pass because the other router still uses the old name.
        """
        from elspeth.web.execution import routes

        found = _collect_ownership_call_site_identities(routes, "_verify_session_ownership")
        self._assert_inventory(
            "execution/routes.py",
            "_verify_session_ownership",
            self.EXPECTED_EXECUTION_SESSION_OWNERSHIP_ENDPOINTS,
            found,
        )

    def test_execution_routes_run_ownership_call_sites(self) -> None:
        """execution/routes.py — _verify_run_ownership inventory.

        Run-scoped endpoints (``/api/runs/{run_id}``) verify a
        different identity dimension (run ownership, resolved through
        the run's parent session).  The IDOR surface is identical in
        principle: an authenticated user probing run_id UUIDs against
        their own endpoints must not be able to distinguish "doesn't
        exist" from "exists in another user's session".
        """
        from elspeth.web.execution import routes

        found = _collect_ownership_call_site_identities(routes, "_verify_run_ownership")
        self._assert_inventory(
            "execution/routes.py",
            "_verify_run_ownership",
            self.EXPECTED_EXECUTION_RUN_OWNERSHIP_ENDPOINTS,
            found,
        )

    def test_blobs_routes_ownership_call_sites(self) -> None:
        """blobs/routes.py — _verify_session_and_get_blob_service inventory.

        The helper is dual-role (ownership check + service lookup).
        Every blob-management endpoint that operates under a
        ``/api/sessions/{session_id}/blobs`` path MUST call it.  A
        handler that acquires the blob service directly from
        ``request.app.state`` without the ownership check would
        bypass the session IDOR guard entirely — that is the drift
        this inventory exists to catch.
        """
        from elspeth.web.blobs import routes

        found = _collect_ownership_call_site_identities(routes, "_verify_session_and_get_blob_service")
        self._assert_inventory(
            "blobs/routes.py",
            "_verify_session_and_get_blob_service",
            self.EXPECTED_BLOBS_OWNERSHIP_ENDPOINTS,
            found,
        )


class TestIDORProtection:
    """Tests for W5 -- IDOR protection on all session-scoped routes.

    Creates a session as user A, then attempts to access it as user B.
    All should return 404 (not 403).

    Inventory of session-scoped routes audited here (must match the set
    of callers of ``_verify_session_ownership`` in
    ``src/elspeth/web/sessions/routes.py``). If a new session-scoped
    route is added upstream, its cross-session request MUST be added
    to ``test_idor_session_crud`` — the test's purpose is to walk
    EVERY endpoint that depends on the ownership primitive, so a new
    route added without a matching assertion here is a silent
    coverage regression.

    Audited endpoints:

    - ``GET  /{session_id}``                 (get_session)
    - ``DELETE /{session_id}``               (delete_session)
    - ``GET  /{session_id}/messages``        (get_messages)
    - ``POST /{session_id}/messages``        (send_message)
    - ``POST /{session_id}/recompose``       (recompose)
    - ``GET  /{session_id}/runs``            (list_session_runs)
    - ``GET  /{session_id}/state``           (get_current_state)
    - ``GET  /{session_id}/state/versions``  (get_state_versions)
    - ``POST /{session_id}/state/revert``    (revert_state)
    - ``GET  /{session_id}/state/yaml``      (get_state_yaml)
    - ``POST /{session_id}/fork``            (fork_from_message)

    Counter-test: alice's own access continues to return 200 at the end,
    guarding against the regression where an over-eager 404 breaks
    legitimate access.
    """

    def test_idor_session_crud(self, tmp_path) -> None:
        """Shared-DB IDOR test: alice creates, bob tries to access."""
        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)
        service = SessionServiceImpl(engine)

        # Create two apps sharing the same service
        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(
                data_dir=tmp_path,
                composer_max_composition_turns=15,
                composer_max_discovery_turns=10,
                composer_timeout_seconds=85.0,
                composer_rate_limit_per_minute=10,
            )
            app.state.catalog_service = None

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)
            app.include_router(create_session_router())
            return app

        alice_app = make_app_for_user("alice")
        bob_app = make_app_for_user("bob")

        alice_client = TestClient(alice_app)
        bob_client = TestClient(bob_app)

        # Alice creates a session
        resp = alice_client.post(
            "/api/sessions",
            json={"title": "Alice Only"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Bob tries to GET it -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 404

        # Bob tries to DELETE it -- should be 404
        resp = bob_client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 404

        # Bob tries to GET messages -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/messages")
        assert resp.status_code == 404

        # Bob tries to POST a message -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "hacked"},
        )
        assert resp.status_code == 404

        # Bob tries to GET state -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/state")
        assert resp.status_code == 404

        # Bob tries to GET state versions -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/state/versions")
        assert resp.status_code == 404

        # Bob tries to revert state -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session_id}/state/revert",
            json={"state_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

        # Bob tries to POST recompose -- should be 404.  The ownership
        # check runs before the rate limiter's side effects in the
        # ``recompose`` route handler, so an attacker cannot use this
        # endpoint to probe for session existence through rate-limit
        # timing either.
        resp = bob_client.post(f"/api/sessions/{session_id}/recompose")
        assert resp.status_code == 404

        # Bob tries to GET runs -- should be 404.  Without this guard,
        # an attacker could enumerate run IDs / timings for sessions
        # belonging to other users and correlate them with activity
        # signals (response size, latency).
        resp = bob_client.get(f"/api/sessions/{session_id}/runs")
        assert resp.status_code == 404

        # Bob tries to GET state/yaml -- should be 404.  The YAML export
        # is the most information-dense state projection (full plugin
        # options, source/sink names, routing); missing this guard would
        # be the highest-bandwidth IDOR leak of the state-read family.
        resp = bob_client.get(f"/api/sessions/{session_id}/state/yaml")
        assert resp.status_code == 404

        # Bob tries to POST fork -- should be 404.  A successful fork
        # would create a new session owned by Bob but seeded from
        # Alice's state history, cross-contaminating audit lineage.
        # The ownership check runs before ``fork_session()`` is called
        # in the ``fork_from_message`` route handler, so no rows are
        # written on denial.
        resp = bob_client.post(
            f"/api/sessions/{session_id}/fork",
            json={
                "from_message_id": str(uuid.uuid4()),
                "new_message_content": "hijacked",
            },
        )
        assert resp.status_code == 404

        # Alice can still access her own session
        resp = alice_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200


class TestSendMessageStateIdValidation:
    """Route-layer IDOR + information-leak coverage for ``POST /messages``
    ``state_id`` validation.

    The ``send_message`` handler accepts an optional ``state_id`` in the
    request body (see ``sessions/routes.py``'s ``send_message`` around
    the ``if body.state_id is not None`` block). That value is used as
    the ``composition_state_id`` stamped onto the persisted user
    message (AD-2 provenance), so any path that lets a client assert
    a state owned by a *different* session would corrupt Tier 1
    audit lineage — a message in session B claiming to have been
    composed against session A's state.

    The outer ``_verify_session_ownership`` check only gates the
    session itself. The ``state_id`` gate is an independent check that
    runs AFTER ownership passes, so it needs its own assertions:

    * ``test_cross_session_state_id_rejected`` (Gap 16): Bob owns his
      own session but supplies a ``state_id`` owned by Alice's session.
      The route must return 404 — not 200 (silently stamp the user
      message with cross-session provenance), not 403 (acknowledges
      the state exists), and not 500 (a ``RuntimeError`` from the
      service-layer defensive guard would indicate the route check
      was bypassed — that would be a separate bug, tested elsewhere).

    * ``test_404_body_is_identical_for_unknown_and_cross_session``
      (Gap 17): the commit that introduced this validation called
      the 404 mapping "load-bearing ... to avoid leaking other
      sessions' state existence". A distinguishable 404 body (for
      example ``"State not found"`` for unknown UUIDs vs ``"State
      not found for this session"`` for owned-by-other) would defeat
      that claim — an attacker who held any UUID could tell from the
      response text whether the UUID exists in a different session,
      reviving the IDOR information leak. This test pins the two
      responses to byte-for-byte parity.

    Sibling ``test_revert_state_not_belonging_to_session`` already
    covers the analogous case for ``POST /state/revert``; the send-
    message handler has its own ``state_id`` check and needs its own
    pins.
    """

    def _alice_plus_bob_with_state(
        self,
        tmp_path: Path,
    ) -> tuple[TestClient, str, str]:
        """Seed the shared-DB IDOR scenario used by both tests below.

        Returns ``(bob_client, bob_session_id, alice_state_id)``:

        * ``alice_state_id`` is a composition_state owned by ``alice``
          in a session ``alice`` alone can access. Bob never touched it.
        * ``bob_session_id`` is a session owned by ``bob`` with a
          composition_state of its own — so ``get_current_state``
          returns non-None in the send_message handler and the
          ``state_id`` validation branch is actually exercised (an
          empty session would route through the ``state_record is
          None`` branch and SKIP the cross-session check, which
          would make the test vacuous).

        The helper owns the engine and service so both users share the
        same underlying DB — the only way the cross-session lookup can
        resolve at all.
        """
        import asyncio

        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)
        service = SessionServiceImpl(engine)

        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(
                data_dir=tmp_path,
                composer_max_composition_turns=15,
                composer_max_discovery_turns=10,
                composer_timeout_seconds=85.0,
                composer_rate_limit_per_minute=10,
            )
            app.state.catalog_service = None
            # Composer MUST NOT be called — state_id validation fails
            # before compose is reached. Set to None so any
            # regression that skips validation surfaces as an
            # AttributeError in the test run rather than silently
            # succeeding against a mock.
            app.state.composer_service = None

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)
            app.include_router(create_session_router())
            return app

        # Alice creates her own session and a state in it.
        loop = asyncio.new_event_loop()
        try:
            alice_session = loop.run_until_complete(
                service.create_session("alice", "Alice Only", "local"),
            )
            alice_state = loop.run_until_complete(
                service.save_composition_state(
                    alice_session.id,
                    CompositionStateData(
                        metadata_={"name": "Alice", "description": ""},
                        is_valid=True,
                    ),
                ),
            )
            # Bob creates his own session AND seeds a composition state
            # so get_current_state on bob's session returns non-None —
            # otherwise the send_message handler skips the state_id
            # validation branch and the test is vacuous. ``metadata_``
            # must be a non-None mapping because the route goes through
            # ``_state_from_record`` which Tier-1 crashes on ``None``
            # (see ``converters.state_from_record``).
            bob_session = loop.run_until_complete(
                service.create_session("bob", "Bob's Own", "local"),
            )
            loop.run_until_complete(
                service.save_composition_state(
                    bob_session.id,
                    CompositionStateData(
                        metadata_={"name": "Bob", "description": ""},
                        is_valid=True,
                    ),
                ),
            )
        finally:
            loop.close()

        bob_app = make_app_for_user("bob")
        bob_client = TestClient(bob_app)
        return bob_client, str(bob_session.id), str(alice_state.id)

    def test_cross_session_state_id_rejected(self, tmp_path) -> None:
        """Gap 16: POST /messages with a state_id owned by ANOTHER session → 404.

        This closes the specific IDOR vector where Bob's session is
        legitimately his (``_verify_session_ownership`` passes), but
        the ``state_id`` in the request body points at a state from
        a session he does NOT own. Without the route-layer cross-
        session check, the persisted user message would record
        Alice's state_id as its ``composition_state_id`` — corrupting
        audit lineage. The outer session-ownership check does not
        catch this (Bob legitimately owns the session he is posting
        to); the state_id check is a separate, independent guard.

        Mirrors the existing ``test_revert_state_not_belonging_to_session``
        for ``POST /state/revert`` — every endpoint that accepts a
        client-supplied ``state_id`` needs its own cross-session
        assertion, since the primitive isn't shared.
        """
        bob_client, bob_session_id, alice_state_id = self._alice_plus_bob_with_state(tmp_path)

        resp = bob_client.post(
            f"/api/sessions/{bob_session_id}/messages",
            json={"content": "hello", "state_id": alice_state_id},
        )
        assert resp.status_code == 404, (
            f"Expected 404 for cross-session state_id, got {resp.status_code}. "
            f"Body: {resp.text!r}. Without this guard, the persisted user "
            "message would claim provenance from a session Bob does not own."
        )

    def test_404_body_is_identical_for_unknown_and_cross_session(self, tmp_path) -> None:
        """Gap 17: pin the "load-bearing" 404 parity claim that underpins
        the cross-session IDOR guard on ``/messages``.

        Two distinct failure modes MUST produce byte-identical response
        bodies:

        1. The UUID does not exist anywhere (``service.get_state``
           raises ``ValueError`` → caught by the route).
        2. The UUID exists but belongs to a session the requester
           does not own (route's ``client_state.session_id !=
           session.id`` branch fires).

        If these two paths return distinguishable bodies, an attacker
        holding any UUID can tell whether it maps to a real state in
        *some other user's* session — the exact IDOR information leak
        the commit claimed to prevent. Bytes must match, not just
        status codes.

        Both requests use Bob's client against Bob's own session, so
        ``_verify_session_ownership`` passes for both — the
        differentiating factor is purely the ``state_id`` value. The
        ``offset=1`` placeholder UUID is constructed to be astronomically
        unlikely to collide with alice_state_id (the only real
        composition_state a UUID could match in this scenario).
        """
        bob_client, bob_session_id, alice_state_id = self._alice_plus_bob_with_state(tmp_path)
        unknown_state_id = str(uuid.uuid4())
        # Sanity: guard against the minuscule probability of collision
        # — if uuid4 ever produced alice's id, the test would
        # accidentally exercise the same branch twice.
        assert unknown_state_id != alice_state_id, "uuid4 collided — retry the test"

        unknown_resp = bob_client.post(
            f"/api/sessions/{bob_session_id}/messages",
            json={"content": "hello", "state_id": unknown_state_id},
        )
        cross_session_resp = bob_client.post(
            f"/api/sessions/{bob_session_id}/messages",
            json={"content": "hello", "state_id": alice_state_id},
        )

        assert unknown_resp.status_code == 404
        assert cross_session_resp.status_code == 404

        # Byte-identical bodies — the strict assertion. FastAPI serialises
        # the HTTPException detail into ``{"detail": "..."}``, and any
        # divergence in the detail string shows up here as a byte-diff.
        assert unknown_resp.content == cross_session_resp.content, (
            "404 body parity broken — unknown-UUID vs cross-session UUID "
            "responses differ. This re-introduces the IDOR information "
            "leak the route-level ownership check was added to prevent.\n"
            f"  unknown:       {unknown_resp.content!r}\n"
            f"  cross-session: {cross_session_resp.content!r}\n"
            "Unify the HTTPException detail strings in send_message's "
            "state_id validation block."
        )
        # Also pin the detail text explicitly so a future refactor that
        # renames BOTH strings symmetrically (preserving parity but
        # introducing a new leak vector through a different channel
        # like response headers) still surfaces as a diff here.
        assert unknown_resp.json() == {"detail": "State not found"}, (
            f"Unexpected 404 body shape: {unknown_resp.json()!r}. "
            "The route's 404 detail must remain the generic "
            '"State not found" — anything more specific (e.g. '
            '"State not found in session", "Wrong owner") leaks '
            "membership information."
        )


class TestMessageRoutes:
    """Tests for message send and retrieval endpoints."""

    def test_send_message(self, tmp_path) -> None:
        mock_composer = _make_composer_mock(response_text="Got it!")

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello, build me a pipeline"},
        )
        assert msg_resp.status_code == 200
        body = msg_resp.json()
        assert body["message"]["content"] == "Got it!"
        assert body["message"]["role"] == "assistant"
        # State unchanged (version stayed at 1) -> no state in response
        assert body["state"] is None

    def test_send_message_with_state_id(self, tmp_path) -> None:
        """Message with state_id references a specific composition state snapshot.

        Exercises the UUID-typed state_id field in SendMessageRequest end-to-end:
        FastAPI parses the JSON string into a UUID, the route validates the state
        belongs to the session, and the user message is persisted with the
        client-asserted state_id as its composition_state_id (AD-2 provenance).
        """
        import asyncio

        mock_composer = _make_composer_mock(response_text="Acknowledged")

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        # Create a session
        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        # Create a composition state via the service (the mock composer
        # returns version=1 which won't trigger state persistence in the
        # route, so we seed one directly).
        loop = asyncio.new_event_loop()
        state_record = loop.run_until_complete(
            service.save_composition_state(
                uuid.UUID(session_id),
                CompositionStateData(
                    metadata_={"name": "Test", "description": ""},
                    is_valid=True,
                ),
            ),
        )
        loop.close()
        state_id = str(state_record.id)

        # Send message WITH state_id as UUID string in JSON body
        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello", "state_id": state_id},
        )
        assert msg_resp.status_code == 200
        body = msg_resp.json()
        assert body["message"]["role"] == "assistant"
        assert body["message"]["content"] == "Acknowledged"

        # Verify provenance: the user message was persisted with the
        # client-asserted state_id as its composition_state_id.
        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        messages = msgs_resp.json()
        user_msg = next(m for m in messages if m["role"] == "user")
        assert user_msg["composition_state_id"] == state_id

    def test_get_messages(self, tmp_path) -> None:
        mock_composer = _make_composer_mock()

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "First"},
        )
        client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Second"},
        )

        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        # Each POST creates a user message + assistant message = 4 total
        assert len(messages) == 4
        assert messages[0]["content"] == "First"
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "Sure, I can help."
        assert messages[1]["role"] == "assistant"

    def test_get_messages_returns_stored_tool_call_arrays(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        app.state.composer_service = _make_composer_mock()
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = uuid.UUID(resp.json()["id"])

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            service.add_message(
                session_id,
                "assistant",
                "Calling a tool",
                tool_calls=[
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "list_sources",
                            "arguments": '{"kind":"csv"}',
                        },
                    }
                ],
            )
        )
        loop.close()

        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        assert len(messages) == 1
        assert messages[0]["tool_calls"] == [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "list_sources",
                    "arguments": '{"kind":"csv"}',
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_send_message_serializes_concurrent_requests_per_session(self, tmp_path) -> None:
        """Concurrent sends must not compose against an in-flight partial transcript."""
        composer = _BlockingRecordingComposer()

        app, _ = _make_app(tmp_path)
        app.state.composer_service = composer

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/sessions", json={"title": "Chat"})
            assert create_resp.status_code == 201
            session_id = create_resp.json()["id"]

            async def send(content: str):
                return await client.post(
                    f"/api/sessions/{session_id}/messages",
                    json={"content": content},
                )

            first_task = asyncio.create_task(send("First"))
            await asyncio.wait_for(composer.first_call_started.wait(), timeout=1.0)

            second_task = asyncio.create_task(send("Second"))

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(composer.second_call_started.wait(), timeout=0.3)

            composer.release_first_call.set()

            first_resp, second_resp = await asyncio.gather(first_task, second_task)

        assert first_resp.status_code == 200
        assert second_resp.status_code == 200
        assert [call["message"] for call in composer.calls] == ["First", "Second"]
        assert composer.calls[0]["chat_messages"] == []
        assert composer.calls[1]["chat_messages"] == [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply to first"},
        ]


class TestLiteLLMErrorRedaction:
    """LiteLLM exception bodies must not leak provider internals.

    ``str(LiteLLMAuthError)`` / ``str(LiteLLMAPIError)`` includes the
    provider name, model ID, request payload fragments, and — on
    certain provider code paths — the upstream HTTP response body
    which has been observed to echo the ``Authorization`` header.
    The 502 HTTP body must therefore carry only the class name, not
    ``str(exc)``.  Paired send_message + recompose assertions pin
    the two mirror paths; any future divergence becomes a selective
    leak surface.
    """

    # Distinct, recognisably synthetic canaries per leakage surface.  Each
    # probes a different way LiteLLM's ``str(exc)`` could expose provider
    # internals:
    #
    # * ``_CANARY_MESSAGE_*`` — the ``message`` constructor argument, the
    #   most common leak vector (Authorization headers, request payload
    #   fragments, upstream response bodies).
    # * ``_CANARY_PROVIDER`` / ``_CANARY_MODEL`` — fields LiteLLM embeds
    #   in its ``__str__`` rendering; even though these are operator-
    #   chosen today, a future provider name that carries credentials
    #   (e.g. tenant-scoped Azure deployments) must not flow through.
    # * ``_CANARY_CAUSE`` — the ``__cause__`` chain from ``raise ... from``;
    #   a 502 body that serialises ``exc.__cause__`` / ``exc.__context__``
    #   would leak upstream DB URLs, credentials, or internal tracebacks
    #   that never appeared in the LiteLLM exception itself.  Mirror of
    #   the SQLAlchemy-side canary coverage (see
    #   ``test_recompose_convergence_save_failure_redacts_sqlalchemy_internals``).
    _CANARY_MESSAGE_TOKEN = "__CANARY_LITELLM_MSG_sk_leaked_token_abc123__"
    _CANARY_MESSAGE_AUTH_HEADER = "__CANARY_LITELLM_MSG_Authorization_Bearer__"
    _CANARY_MESSAGE_PAYLOAD = "__CANARY_LITELLM_MSG_request_payload_opaque__"
    _CANARY_PROVIDER = "__CANARY_LITELLM_PROVIDER_internal__"
    _CANARY_MODEL = "__CANARY_LITELLM_MODEL_secret_deployment__"
    _CANARY_CAUSE = "__CANARY_LITELLM_CAUSE_upstream_conn_str__"

    @classmethod
    def _canary_message(cls) -> str:
        """Assemble a message that packs every message-field canary.

        Kept as a single concatenated string so every canary rides
        through the same ``message`` constructor argument — the exact
        path the redaction contract is designed to sever.
        """
        return (
            f"Auth failed token={cls._CANARY_MESSAGE_TOKEN} header={cls._CANARY_MESSAGE_AUTH_HEADER} payload={cls._CANARY_MESSAGE_PAYLOAD}"
        )

    @classmethod
    def _all_canaries(cls) -> tuple[tuple[str, str], ...]:
        """Canary name → value pairs for the leak-surface sweep.

        Returned as ordered tuples so assertion failures identify the
        specific leak surface (e.g. ``__cause__`` chain vs ``model`` field)
        rather than a generic "something leaked" signal.
        """
        return (
            ("message.token", cls._CANARY_MESSAGE_TOKEN),
            ("message.auth_header", cls._CANARY_MESSAGE_AUTH_HEADER),
            ("message.payload", cls._CANARY_MESSAGE_PAYLOAD),
            ("llm_provider", cls._CANARY_PROVIDER),
            ("model", cls._CANARY_MODEL),
            ("__cause__", cls._CANARY_CAUSE),
        )

    def _make_auth_error(self):
        from litellm.exceptions import AuthenticationError as LiteLLMAuthError

        exc = LiteLLMAuthError(
            message=self._canary_message(),
            llm_provider=self._CANARY_PROVIDER,
            model=self._CANARY_MODEL,
        )
        # ``raise ... from cause`` chained manually so the test can run
        # without an actual DB/network cause — what matters is that a
        # serialiser that walks ``__cause__`` will encounter the canary.
        exc.__cause__ = RuntimeError(f"upstream: {self._CANARY_CAUSE}")
        return exc

    def _make_api_error(self):
        from litellm.exceptions import APIError as LiteLLMAPIError

        exc = LiteLLMAPIError(
            status_code=503,
            message=self._canary_message(),
            llm_provider=self._CANARY_PROVIDER,
            model=self._CANARY_MODEL,
        )
        exc.__cause__ = RuntimeError(f"upstream: {self._CANARY_CAUSE}")
        return exc

    def _assert_redacted(self, resp, expected_error_type: str, expected_exc_class: str) -> None:
        """Assert the 502 body is class-name-only and contains no canary strings."""
        assert resp.status_code == 502
        body = resp.json()
        detail = body["detail"]
        assert detail["error_type"] == expected_error_type
        # The ``detail`` field now carries ONLY the exception class name,
        # not the leaky ``str(exc)``.  Byte equality is the load-bearing
        # assertion — a substring check would admit "AuthenticationError:
        # Auth failed for provider=openai ..." which is precisely the
        # shape the redaction exists to prevent.
        assert detail["detail"] == expected_exc_class
        # Defence-in-depth: sweep every canary across the full serialised
        # body.  Per-surface failure messages so a regression names which
        # leak channel opened (``message`` field vs ``__cause__`` chain vs
        # ``model`` field) — mirrors the SQLAlchemy-side coverage in
        # ``test_recompose_convergence_save_failure_redacts_sqlalchemy_internals``.
        serialised = resp.text
        for surface, canary in self._all_canaries():
            assert canary not in serialised, (
                f"LiteLLM canary leaked into HTTP response body via "
                f"{surface!r} surface: {canary!r} appears in serialised 502 body. "
                "The redaction contract requires the body to carry only the "
                "exception class name — inspect the handler for a code path "
                "that re-introduced str(exc), exc.__cause__, or an individual "
                "exception field into the response."
            )

    def test_send_message_auth_error_body_carries_class_name_only(self, tmp_path) -> None:
        """LiteLLMAuthError from compose() → 502 with class-name-only detail."""
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(side_effect=self._make_auth_error())

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello"},
        )
        self._assert_redacted(msg_resp, "llm_auth_error", "AuthenticationError")

    def test_send_message_api_error_body_carries_class_name_only(self, tmp_path) -> None:
        """LiteLLMAPIError from compose() → 502 with class-name-only detail."""
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(side_effect=self._make_api_error())

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello"},
        )
        self._assert_redacted(msg_resp, "llm_unavailable", "APIError")

    def test_recompose_auth_error_body_carries_class_name_only(self, tmp_path) -> None:
        """recompose path must mirror send_message's redaction."""
        import asyncio

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(side_effect=self._make_auth_error())

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        # recompose precondition: last message must be user turn.
        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build a pipeline"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")
        self._assert_redacted(recompose_resp, "llm_auth_error", "AuthenticationError")

    def test_recompose_api_error_body_carries_class_name_only(self, tmp_path) -> None:
        """recompose path must mirror send_message's redaction for APIError too."""
        import asyncio

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(side_effect=self._make_api_error())

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build a pipeline"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")
        self._assert_redacted(recompose_resp, "llm_unavailable", "APIError")


class TestRecomposeConvergencePartialState:
    """Tests for partial state persistence on composer convergence failure."""

    def test_recompose_convergence_preserves_partial_state(self, tmp_path) -> None:
        """When recompose hits convergence error with partial state,
        the state is persisted and included in the 422 response."""
        import asyncio

        from elspeth.web.composer.protocol import ComposerConvergenceError

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,  # > initial (1), so it's a real mutation
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        # Create session
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        # Simulate a failed send_message: user message saved, no assistant
        # response. This is the precondition for recompose — the last
        # message must be a user turn.
        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build a CSV pipeline"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"
        assert "partial_state" in detail

    def test_recompose_convergence_without_partial_state(self, tmp_path) -> None:
        """When convergence error has no partial state (no mutations),
        response omits partial_state key."""
        import asyncio

        from elspeth.web.composer.protocol import ComposerConvergenceError

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=3,
                budget_exhausted="discovery",
                partial_state=None,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build something"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"
        assert "partial_state" not in detail

    def test_convergence_redacts_blob_path_from_response_but_preserves_in_db(self, tmp_path) -> None:
        """When partial_state has a blob-backed source, the HTTP response must
        redact the internal storage path while the DB copy retains it."""
        import asyncio

        from elspeth.contracts.freeze import deep_freeze
        from elspeth.web.composer.protocol import ComposerConvergenceError
        from elspeth.web.composer.state import SourceSpec

        partial = CompositionState(
            source=SourceSpec(
                plugin="csv",
                options=deep_freeze(
                    {
                        "path": "/internal/blobs/data.csv",
                        "blob_ref": "abc123",
                        "schema": {"mode": "observed"},
                    }
                ),
                on_success="t1",
                on_validation_failure="quarantine",
            ),
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        # Create session and seed a user message for recompose precondition
        resp = client.post("/api/sessions", json={"title": "Blob test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            service.add_message(uuid.UUID(session_id), "user", "Load my CSV"),
        )
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"

        # HTTP response: path must be redacted, blob_ref must be present
        response_source_opts = detail["partial_state"]["source"]["options"]
        assert "path" not in response_source_opts
        assert response_source_opts["blob_ref"] == "abc123"

        # DB copy: path must be preserved alongside blob_ref
        loop = asyncio.new_event_loop()
        db_record = loop.run_until_complete(
            service.get_current_state(uuid.UUID(session_id)),
        )
        loop.close()

        assert db_record is not None
        assert db_record.source is not None, "composition state must carry a source"
        db_source_opts = db_record.source["options"]
        assert db_source_opts["path"] == "/internal/blobs/data.csv"
        assert db_source_opts["blob_ref"] == "abc123"

    def test_recompose_convergence_save_operational_error_preserves_422_body(self, tmp_path) -> None:
        """Regression (elspeth-303f751204): when save_composition_state
        raises an ``OperationalError`` (lock timeout / pool disconnect)
        while persisting partial_state from a convergence error, the
        handler MUST still return the structured 422 body with
        ``partial_state_save_failed=True`` rather than upgrading the
        user-driven 422 to an uncaught 500.

        Before the fix, the handler's ``except`` clause caught only
        ``IntegrityError``; any other ``SQLAlchemyError`` subclass escaped
        and the user received a generic 500 with no structured diagnostic.
        """
        import asyncio

        from sqlalchemy.exc import OperationalError

        from elspeth.web.composer.protocol import ComposerConvergenceError

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        async def _raise_operational(*_args, **_kwargs):
            raise OperationalError(
                "INSERT INTO composition_states ...",
                {},
                Exception("server has gone away"),
            )

        service.save_composition_state = _raise_operational  # type: ignore[method-assign]

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            service.add_message(uuid.UUID(session_id), "user", "Build a pipeline"),
        )
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        # Structured 422 body is preserved despite the secondary save failure.
        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"
        assert detail["partial_state_save_failed"] is True
        # partial_state is not populated on save failure (no successful row).
        assert "partial_state" not in detail

    def test_recompose_convergence_save_failure_redacts_sqlalchemy_internals(self, tmp_path) -> None:
        """Regression: the 422 body's ``partial_state_save_error`` field must
        carry only the exception class name — never SQL statements, parameter
        tuples, or ``__cause__`` text. ``str(SQLAlchemyError)`` includes
        ``[SQL: ...]`` and ``[parameters: ...]`` which on this code path carry
        the composition-state JSON payload (potential secret refs); on
        ``OperationalError`` the ``__cause__`` message can carry DB URLs or
        credentials. The slog side already redacts
        (``exc_class=type(save_err).__name__``); the HTTP response body must
        match that redaction so a 422 cannot become a leak channel.

        Paired with the sibling ``_handle_plugin_crash`` contract (same file),
        which emits no response-body diagnostic at all.
        """
        import asyncio

        from sqlalchemy.exc import OperationalError

        from elspeth.web.composer.protocol import ComposerConvergenceError

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        # Canary strings chosen to be recognisably synthetic — if any appear
        # anywhere in the JSON response body, redaction failed.
        sql_canary = "__CANARY_SQL_INSERT_composition_states_source_options__"
        params_canary = "__CANARY_PARAM_secret_ref_opaque_token__"
        cause_canary = "__CANARY_CAUSE_postgresql_conn_str_password__"

        async def _raise_operational(*_args, **_kwargs):
            raise OperationalError(
                f"INSERT INTO composition_states (id, session_id, source) VALUES (...) -- {sql_canary}",
                {"source_options": params_canary},
                Exception(f"connection closed: {cause_canary}"),
            )

        service.save_composition_state = _raise_operational  # type: ignore[method-assign]

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Redaction"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            service.add_message(uuid.UUID(session_id), "user", "Build a pipeline"),
        )
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        body_text = recompose_resp.text
        # Primary assertion: no canary substring anywhere in the serialised body.
        assert sql_canary not in body_text, "SQL statement leaked into HTTP response body"
        assert params_canary not in body_text, "parameter tuple leaked into HTTP response body"
        assert cause_canary not in body_text, "DBAPI __cause__ text leaked into HTTP response body"

        detail = recompose_resp.json()["detail"]
        # The boolean signal is preserved so clients can still distinguish
        # "partial state saved" from "partial state lost to a save failure".
        assert detail["partial_state_save_failed"] is True
        # The diagnostic field carries ONLY the exception class name.
        assert detail.get("partial_state_save_error") == "OperationalError"


class TestStateRoutes:
    """Tests for composition state endpoints."""

    def test_get_state_empty(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Empty"})
        session_id = resp.json()["id"]

        state_resp = client.get(f"/api/sessions/{session_id}/state")
        assert state_resp.status_code == 200
        assert state_resp.json() is None

    def test_get_state_versions(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Pipeline"})
        session_id = resp.json()["id"]

        versions_resp = client.get(
            f"/api/sessions/{session_id}/state/versions",
        )
        assert versions_resp.status_code == 200
        assert versions_resp.json() == []


class TestRevertEndpoint:
    """Tests for POST /api/sessions/{id}/state/revert (R1)."""

    @pytest.mark.asyncio
    async def test_revert_creates_new_version(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        # Create session and two state versions via the service
        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "csv"}, is_valid=True),
        )
        await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "api"}, is_valid=True),
        )

        # Revert to v1
        resp = client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 3
        # Should match v1's source, not v2's
        assert body["source"] == {"type": "csv"}
        # Lineage: new version derives from v1
        assert body["derived_from_state_id"] == str(v1.id)

    @pytest.mark.asyncio
    async def test_revert_injects_system_message(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )
        await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )

        client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )

        # Check that a system message was injected
        msgs_resp = client.get(f"/api/sessions/{session.id}/messages")
        messages = msgs_resp.json()
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "Pipeline reverted to version 1."

    @pytest.mark.asyncio
    async def test_revert_idor_protection(self, tmp_path) -> None:
        """Revert to a state in another user's session returns 404."""
        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)
        service = SessionServiceImpl(engine)

        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(
                data_dir=tmp_path,
                composer_max_composition_turns=15,
                composer_max_discovery_turns=10,
                composer_timeout_seconds=85.0,
                composer_rate_limit_per_minute=10,
            )

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)
            app.include_router(create_session_router())
            return app

        bob_app = make_app_for_user("bob")
        bob_client = TestClient(bob_app)

        # Alice creates a session with a state
        session = await service.create_session("alice", "Alice Only", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )

        # Bob tries to revert -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_revert_state_not_belonging_to_session(self, tmp_path) -> None:
        """Revert with a state_id from a different session returns 404."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        s1 = await service.create_session("alice", "Session 1", "local")
        s2 = await service.create_session("alice", "Session 2", "local")
        v1_s2 = await service.save_composition_state(
            s2.id,
            CompositionStateData(is_valid=True),
        )

        # Try to revert s1 using s2's state -- should fail
        resp = client.post(
            f"/api/sessions/{s1.id}/state/revert",
            json={"state_id": str(v1_s2.id)},
        )
        assert resp.status_code == 404


class TestYamlEndpoint:
    """Tests for GET /api/sessions/{id}/state/yaml."""

    @pytest.mark.asyncio
    async def test_yaml_returns_yaml_when_state_exists(self, tmp_path) -> None:
        """Returns generated YAML for a valid state even when edge_contracts is empty."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={"plugin": "csv", "on_success": "out", "options": {"path": "/data.csv"}, "on_validation_failure": "quarantine"},
                outputs=[
                    {
                        "name": "out",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Test Pipeline", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 200
        body = resp.json()
        assert "yaml" in body
        assert "csv" in body["yaml"]

    @pytest.mark.asyncio
    async def test_yaml_allows_connection_valid_state_without_ui_edges(self, tmp_path) -> None:
        """Connection-defined pipelines should export even when the editor graph is incomplete."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "text",
                    "on_success": "mapper_in",
                    "options": {
                        "path": "/data/input.txt",
                        "column": "text",
                        "schema": {"mode": "observed"},
                    },
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "map_body",
                        "node_type": "transform",
                        "plugin": "field_mapper",
                        "input": "mapper_in",
                        "on_success": "main",
                        "on_error": "discard",
                        "options": {
                            "schema": {"mode": "observed", "guaranteed_fields": ["text"], "required_fields": ["text"]},
                            "mapping": {"text": "body"},
                        },
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                ],
                edges=[],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {
                            "path": "outputs/out.csv",
                            "schema": {"mode": "observed", "required_fields": ["body"]},
                        },
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Connection-only Pipeline", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 200
        assert "field_mapper" in resp.json()["yaml"]
        assert "body" in resp.json()["yaml"]

    @pytest.mark.asyncio
    async def test_yaml_serializes_coalesce_on_success_runtime_route(self, tmp_path) -> None:
        """Coalesce terminal routing must survive export/reload parity checks."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "csv",
                    "on_success": "gate_in",
                    "options": {"path": "/data/input.csv"},
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "fork_gate",
                        "node_type": "gate",
                        "plugin": None,
                        "input": "gate_in",
                        "on_success": None,
                        "on_error": None,
                        "options": {},
                        "condition": "True",
                        "routes": {},
                        "fork_to": ["path_a", "path_b"],
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                    {
                        "id": "merge_point",
                        "node_type": "coalesce",
                        "plugin": None,
                        "input": "join",
                        "on_success": "main",
                        "on_error": None,
                        "options": {},
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": ["path_a", "path_b"],
                        "policy": "require_all",
                        "merge": "nested",
                    },
                ],
                edges=[],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv"},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Fork and merge", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")

        assert resp.status_code == 200
        doc = yaml.safe_load(resp.json()["yaml"])
        assert doc["coalesce"][0]["on_success"] == "main"

    @pytest.mark.asyncio
    async def test_yaml_returns_409_when_current_state_is_invalid(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "csv",
                    "on_success": "t1",
                    "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "t1",
                        "node_type": "transform",
                        "plugin": "value_transform",
                        "input": "t1",
                        "on_success": "main",
                        "on_error": "discard",
                        "options": {
                            "required_input_fields": ["text"],
                            "operations": [{"target": "out", "expression": "row['text']"}],
                            "schema": {"mode": "observed"},
                        },
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                ],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Invalid Contract Pipeline", "description": ""},
                is_valid=True,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 409
        assert "invalid" in resp.json()["detail"].lower()

    def test_yaml_returns_404_when_no_state(self, tmp_path) -> None:
        """No composition state yet -> 404."""
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Empty"})
        session_id = resp.json()["id"]

        yaml_resp = client.get(f"/api/sessions/{session_id}/state/yaml")
        assert yaml_resp.status_code == 404


class TestRunAlreadyActiveError:
    """Tests for seam contract D: RunAlreadyActiveError → 409 with error_type.

    The create_run endpoint does not exist yet (Sub-5), but the exception
    handler is wired. These tests exercise it via direct service calls +
    app-level exception propagation to verify the contract.
    """

    @pytest.mark.asyncio
    async def test_run_already_active_returns_409(self, tmp_path) -> None:
        """RunAlreadyActiveError produces 409 with error_type field."""
        from elspeth.web.sessions.protocol import RunAlreadyActiveError

        app, service = _make_app(tmp_path)

        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )
        # Create a run to block the session
        await service.create_run(session.id, v1.id)

        # Register the app-level exception handler (wired in create_app,
        # but our test app uses create_session_router directly). Wire it here.
        from fastapi.responses import JSONResponse

        @app.exception_handler(RunAlreadyActiveError)
        async def handle_run_already_active(
            request,
            exc: RunAlreadyActiveError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=409,
                content={"detail": str(exc), "error_type": "run_already_active"},
            )

        # Add a test endpoint that triggers the error
        @app.post("/api/_test_create_run")
        async def _test_create_run():
            await service.create_run(session.id, v1.id)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/_test_create_run")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_type"] == "run_already_active"
        assert "detail" in body


class TestNewStateHasNoLineage:
    """Test that fresh composition states have null derived_from_state_id."""

    @pytest.mark.asyncio
    async def test_fresh_state_has_null_derived_from(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "csv"}, is_valid=True),
        )

        resp = client.get(f"/api/sessions/{session.id}/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["derived_from_state_id"] is None


class TestPaginationRoutes:
    """Tests for limit/offset query parameters on list endpoints."""

    def test_list_sessions_pagination(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        for i in range(5):
            client.post("/api/sessions", json={"title": f"S{i}"})

        resp = client.get("/api/sessions?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp = client.get("/api/sessions?limit=2&offset=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_sessions_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        # limit < 1
        resp = client.get("/api/sessions?limit=0")
        assert resp.status_code == 422

        # limit > 200
        resp = client.get("/api/sessions?limit=201")
        assert resp.status_code == 422

        # offset < 0
        resp = client.get("/api/sessions?offset=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        # Add messages directly via service to avoid composer dependency
        session = await service.get_session(uuid.UUID(session_id))
        for i in range(5):
            await service.add_message(session.id, "user", f"Msg {i}")

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=2")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "Msg 0"

        resp = client.get(
            f"/api/sessions/{session_id}/messages?limit=2&offset=3",
        )
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "Msg 3"

    def test_get_messages_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=0")
        assert resp.status_code == 422

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=501")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_state_versions_pagination(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        for _ in range(5):
            await service.save_composition_state(
                session.id,
                CompositionStateData(is_valid=False),
            )

        resp = client.get(
            f"/api/sessions/{session.id}/state/versions?limit=2",
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 1

        resp = client.get(
            f"/api/sessions/{session.id}/state/versions?limit=2&offset=3",
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 4

    def test_get_state_versions_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        resp = client.get(
            f"/api/sessions/{session_id}/state/versions?limit=0",
        )
        assert resp.status_code == 422

        resp = client.get(
            f"/api/sessions/{session_id}/state/versions?limit=201",
        )
        assert resp.status_code == 422


class TestComposePluginCrashResponse:
    """Plugin TypeError/ValueError from compose() must produce a structured 500.

    After the Task 4 narrowing, plugin bugs escape the service layer instead
    of being laundered as LLM retries. The route handler MUST shape these
    into a documented response rather than letting FastAPI's default handler
    emit an arbitrary traceback.

    Audit-integrity invariant: exception message content — especially
    fragments from __cause__-chained exceptions that may include DB URLs,
    filesystem paths, or secret material — MUST NOT appear in the response
    body. Only the documented error_type + generic detail string is echoed.
    """

    SECRET_PATH = "/etc/elspeth/secrets/bootstrap.key"

    def test_compose_plugin_value_error_returns_structured_500(self, tmp_path) -> None:
        original = ValueError(f"plugin bug: {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        body = response.json()
        # FastAPI serializes HTTPException(detail={...}) as {"detail": {...}}.
        assert isinstance(body.get("detail"), dict), body
        assert body["detail"]["error_type"] == "composer_plugin_error"
        assert "user-retryable" in body["detail"]["detail"].lower()

        # Audit-integrity: exception message and cause content MUST NOT leak.
        body_text = response.text
        assert "plugin bug" not in body_text
        assert self.SECRET_PATH not in body_text
        assert "ValueError" not in body_text  # exception class also redacted

    def test_recompose_plugin_type_error_returns_structured_500(self, tmp_path) -> None:
        import asyncio

        original = TypeError(f"plugin bug: NoneType has no attribute 'read' from {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        # Recompose requires a pre-existing trailing user message (see
        # TestRecomposeConvergencePartialState for the template).
        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build something"))
        loop.close()

        response = client.post(f"/api/sessions/{session_id}/recompose")

        assert response.status_code == 500
        body = response.json()
        assert isinstance(body.get("detail"), dict), body
        assert body["detail"]["error_type"] == "composer_plugin_error"

        body_text = response.text
        assert "plugin bug" not in body_text
        assert self.SECRET_PATH not in body_text
        assert "NoneType" not in body_text
        assert "TypeError" not in body_text

    def test_compose_plugin_crash_persists_partial_state(self, tmp_path) -> None:
        """P1 regression fix: when a plugin crashes AFTER one or more tool
        calls succeeded in the same request, the accumulated ``partial_state``
        MUST be persisted into ``composition_states`` before the 500 is
        returned.  Without this, recompose restarts from the stale
        pre-request state and silently reverts the LLM's successful mutations.

        Symmetric with ``TestRecomposeConvergencePartialState`` for the
        convergence-error path.
        """
        import asyncio

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="after-first-mutation"),
            version=5,
        )
        original = ValueError(f"plugin bug after mutation: {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_type"] == "composer_plugin_error"
        # Response body still fully redacted — persisting partial_state
        # into composition_states does NOT echo it on the failure response.
        assert self.SECRET_PATH not in response.text

        # The partial_state row MUST exist in composition_states now.
        loop = asyncio.new_event_loop()
        try:
            persisted = loop.run_until_complete(service.get_current_state(uuid.UUID(session_id)))
        finally:
            loop.close()
        assert persisted is not None, "partial_state must be persisted to composition_states on plugin crash"
        assert persisted.metadata_ is not None
        assert persisted.metadata_.get("name") == "after-first-mutation"

    def test_compose_plugin_crash_no_partial_state_persists_nothing(self, tmp_path) -> None:
        """When a plugin crashes BEFORE any mutation (partial_state is None),
        no new ``composition_states`` row is written. The 500 response shape
        is identical to the persisted-partial case.
        """
        import asyncio

        original = ValueError("plugin bug on first call")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )
        assert response.status_code == 500

        loop = asyncio.new_event_loop()
        try:
            persisted = loop.run_until_complete(service.get_current_state(uuid.UUID(session_id)))
        finally:
            loop.close()
        # A brand-new session with no successful mutations → no composition
        # state row should have been created by the crash path.
        assert persisted is None

    def test_compose_plugin_crash_log_has_no_traceback_fields(self, tmp_path) -> None:
        """P2 regression fix: the plugin-crash structured log MUST NOT
        carry traceback-shaped fields. ``exc_info=True`` was dropped
        because plugin exception ``__cause__`` chains may include DB
        URLs, filesystem paths, or secret fragments.
        """
        from structlog.testing import capture_logs

        original = ValueError(f"plugin bug with secret {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        with capture_logs() as cap_logs:
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"content": "Build me a pipeline"},
            )
        assert response.status_code == 500

        crash_events = [e for e in cap_logs if e.get("event") == "compose_plugin_crash"]
        assert len(crash_events) == 1, cap_logs
        event = crash_events[0]
        # Triage fields present.
        assert event["exc_class"] == "ValueError"
        assert event["session_id"] == session_id
        # Traceback-shaped fields absent.
        assert "exc_info" not in event
        assert "exception" not in event
        assert "stack_info" not in event
        # Exception message / secret fragments MUST NOT appear anywhere
        # in the structured event (defense-in-depth).
        serialised = str(event)
        assert self.SECRET_PATH not in serialised
        assert "plugin bug" not in serialised

    def test_compose_plugin_crash_sentinel_leak(self, tmp_path) -> None:
        """Multi-sentinel test: inject an exception whose ``__str__`` and
        whose ``__cause__.__str__`` each carry a distinct secret sentinel.
        Neither must appear in the HTTP response body nor in any captured
        log record. This guards against future regressions where a
        structlog processor or log field addition inadvertently serialises
        exception content.
        """
        from structlog.testing import capture_logs

        message_secret = "postgres://user:p4ss@prod-db.internal:5432/audit"
        cause_secret = "/var/secrets/elspeth/bootstrap-key.pem"

        original = RuntimeError(f"upstream failure: {message_secret}")
        original.__cause__ = FileNotFoundError(cause_secret)

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        with capture_logs() as cap_logs:
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"content": "Build me a pipeline"},
            )
        assert response.status_code == 500

        # Neither sentinel in response body.
        assert message_secret not in response.text
        assert cause_secret not in response.text

        # Neither sentinel in any captured log record.
        for event in cap_logs:
            serialised = str(event)
            assert message_secret not in serialised, event
            assert cause_secret not in serialised, event

    def test_compose_plugin_crash_save_operational_error_preserves_500_body(self, tmp_path) -> None:
        """Regression (elspeth-303f751204): when save_composition_state
        raises an ``OperationalError`` (lock timeout, pool disconnect,
        deadlock) while persisting partial_state during a plugin crash,
        the handler MUST still return the structured ``composer_plugin_error``
        500 body rather than letting the secondary DB failure mask the
        primary crash.  The save failure is recorded via
        ``_plugin_crash_partial_state_save_failed`` slog.

        Before the fix, the handler's ``except`` clause caught only
        ``IntegrityError``; any other ``SQLAlchemyError`` subclass escaped,
        producing a generic (unstructured) 500 and losing the redacted
        response path entirely.
        """
        from sqlalchemy.exc import OperationalError
        from structlog.testing import capture_logs

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="mid-crash-mutation"),
            version=3,
        )
        original = ValueError(f"plugin bug: {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        # Patch save_composition_state to raise a non-IntegrityError
        # SQLAlchemyError subclass — simulates lock timeout / deadlock /
        # pool disconnect / schema drift.
        async def _raise_operational(*_args, **_kwargs):
            raise OperationalError(
                "UPDATE composition_states ...",
                {},
                Exception("lock wait timeout exceeded"),
            )

        service.save_composition_state = _raise_operational  # type: ignore[method-assign]

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        with capture_logs() as cap_logs:
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"content": "Build me a pipeline"},
            )

        # Structured 500 body is preserved despite the secondary save failure.
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_type"] == "composer_plugin_error"
        assert self.SECRET_PATH not in response.text

        # The secondary failure is recorded via slog.
        save_fail_events = [e for e in cap_logs if e.get("event") == "compose_plugin_crash_partial_state_save_failed"]
        assert len(save_fail_events) == 1, cap_logs
        assert save_fail_events[0]["exc_class"] == "OperationalError"

        # And the primary plugin_crash slog still fires.
        crash_events = [e for e in cap_logs if e.get("event") == "compose_plugin_crash"]
        assert len(crash_events) == 1, cap_logs

    def test_compose_plugin_crash_save_failure_sets_partial_state_save_failed_flag(self, tmp_path) -> None:
        """Regression (P2d): when partial-state persistence fails during a
        plugin crash, the 500 response body MUST include
        ``partial_state_save_failed=True`` and ``partial_state_save_error``
        symmetric with the 422 convergence-error response. The frontend
        recovery UX branches on this flag to distinguish "state is
        captured, safe to retry later" from "state is lost, start over."
        Without the flag, the two plugin-crash outcomes (save success
        vs save failure) are indistinguishable to the client.
        """
        from sqlalchemy.exc import OperationalError

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="mid-crash-mutation"),
            version=3,
        )
        original = ValueError("plugin bug")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        async def _raise_operational(*_args, **_kwargs):
            raise OperationalError(
                "UPDATE composition_states ...",
                {},
                Exception("lock wait timeout exceeded"),
            )

        service.save_composition_state = _raise_operational  # type: ignore[method-assign]

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error_type"] == "composer_plugin_error"
        # The two symmetry fields introduced to match _handle_convergence_error.
        assert detail.get("partial_state_save_failed") is True
        assert detail.get("partial_state_save_error") == "OperationalError"

    def test_compose_plugin_crash_save_successful_omits_partial_state_save_failed_flag(self, tmp_path) -> None:
        """Regression (P2d, negative): when partial-state persistence
        SUCCEEDS, the 500 response body MUST NOT carry a false
        ``partial_state_save_failed`` flag. The flag is a signal of
        recovery failure, not a constant field."""
        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="mid-crash-mutation"),
            version=3,
        )
        original = ValueError("plugin bug")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error_type"] == "composer_plugin_error"
        # Both keys absent on the success path — no false signal.
        assert "partial_state_save_failed" not in detail
        assert "partial_state_save_error" not in detail

    def test_compose_plugin_crash_save_typeerror_propagates_tier1_crash(self, tmp_path) -> None:
        """Regression (P2b): when ``save_composition_state`` raises a
        ``TypeError`` (our own code, Tier 1), the handler MUST let it
        propagate as an unstructured 500 rather than laundering it into
        ``partial_state_save_failed=True``. Pre-fix behaviour caught
        (ValueError, TypeError, KeyError, SQLAlchemyError) and produced
        a soft 500 with the flag set — which is exactly the silent-
        wrong-result pattern CLAUDE.md forbids for our own data.
        """
        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="mid-crash-mutation"),
            version=3,
        )
        original = ValueError("plugin bug")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer

        # TypeError from our own dataclass path — a Tier 1 bug that must propagate.
        async def _raise_type_error(*_args, **_kwargs):
            raise TypeError("dataclass field contract violated")

        service.save_composition_state = _raise_type_error  # type: ignore[method-assign]

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        # 500 from FastAPI's default handler — NOT the composer_plugin_error
        # structured body. The crashed request is the correct outcome; a
        # soft partial_state_save_failed=True would hide the Tier 1 bug.
        assert response.status_code == 500
        assert "composer_plugin_error" not in response.text
        assert "partial_state_save_failed" not in response.text

    def test_compose_unknown_exception_class_is_not_absorbed(self, tmp_path) -> None:
        """Deliberately narrow typed catch: RuntimeError (not in the handler's
        catch list) must propagate past the composer_plugin_error handler.
        With raise_server_exceptions=False, TestClient returns FastAPI's
        default 500 response; the critical invariant is that the structured
        composer_plugin_error body is NOT produced for unknown classes.
        """
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=RuntimeError("unknown failure class"),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        # Unconditional: the composer_plugin_error marker MUST NOT appear
        # anywhere in the response body, regardless of whether FastAPI
        # renders detail as a dict or a string.  This closes the vacuous-
        # pass risk of an `if isinstance(...)` guard.
        assert "composer_plugin_error" not in response.text
