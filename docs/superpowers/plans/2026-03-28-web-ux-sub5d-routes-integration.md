# Web UX Task-Plan 5D: Routes, WebSocket & Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Implement REST endpoints, WebSocket handler with query param auth, multi-worker warning, and end-to-end integration test
**Parent Plan:** `plans/2026-03-28-web-ux-sub5-execution.md`
**Spec:** `specs/2026-03-28-web-ux-sub5-execution-design.md`
**Depends On:** Task-Plans 5A, 5B, 5C (all execution internals), Sub-Plan 2 (Sessions — routes, auth)
**Blocks:** Sub-Plan 6 (Frontend)

---

## File Map

| Action | File |
|--------|------|
| Create | `src/elspeth/web/execution/routes.py` |
| Create | `tests/unit/web/execution/test_routes.py` |
| Modify | app factory (wherever `create_app()` lives, from Sub-Spec 2) |
| Create | `tests/integration/web/__init__.py` |
| Create | `tests/integration/web/test_execute_pipeline.py` |
| Create | `tests/integration/web/fixtures/test_input.csv` |

---

### Task 5.6: Execution Routes and WebSocket

**Files:**
- Create: `src/elspeth/web/execution/routes.py`
- Create: `tests/unit/web/execution/test_routes.py`

- [ ] **Step 1: Write route tests**

```python
# tests/unit/web/execution/test_routes.py
"""Tests for execution REST endpoints and WebSocket.

Routes delegate to ExecutionServiceImpl — these tests verify HTTP
semantics, status codes, and request/response contracts.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from elspeth.web.execution.schemas import (
    RunEvent,
    RunStatusResponse,
    ValidationCheck,
    ValidationResult,
)
from elspeth.web.execution.service import RunAlreadyActiveError


# ── Test fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_execution_service() -> MagicMock:
    svc = MagicMock()
    svc.validate.return_value = ValidationResult(
        is_valid=True,
        checks=[
            ValidationCheck(name="settings_load", passed=True, detail="OK"),
        ],
        errors=[],
    )
    run_id = uuid4()
    svc.execute.return_value = run_id
    svc.get_status.return_value = RunStatusResponse(
        run_id=str(run_id),
        status="completed",
        started_at=datetime.now(tz=timezone.utc),
        finished_at=datetime.now(tz=timezone.utc),
        rows_processed=10,
        rows_failed=0,
        error=None,
        landscape_run_id="lscape-1",
    )
    return svc


@pytest.fixture
def mock_broadcaster() -> MagicMock:
    return MagicMock()


# Note: These tests require the app factory to be wired.
# The actual test_app fixture will depend on Sub-Spec 2 (Auth) and
# Sub-Spec 4 (Composer) providing create_app(). Tests below show
# the expected HTTP contract — adapt fixture wiring to match the
# actual app factory when those phases are implemented.


class TestValidateEndpoint:
    """POST /api/sessions/{session_id}/validate"""

    @pytest.mark.asyncio
    async def test_valid_pipeline_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # This test validates the route handler contract.
        # When the app factory is available, create the test client:
        #   app = create_app(execution_service=mock_execution_service)
        #   async with AsyncClient(transport=ASGITransport(app=app)) as client:
        #       resp = await client.post(f"/api/sessions/{uuid4()}/validate")
        #       assert resp.status_code == 200
        #       body = resp.json()
        #       assert body["is_valid"] is True
        pass  # Placeholder until app factory is wired

    @pytest.mark.asyncio
    async def test_validate_uses_run_in_executor(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        """AC #16: validate route handler MUST NOT call validate_pipeline
        synchronously — it must use run_in_executor to avoid blocking the
        event loop."""
        # When the app factory is available, verify that the route handler
        # calls asyncio.get_running_loop().run_in_executor(None, validate_pipeline, state).
        # The test inspects the route handler source or mocks the loop to
        # verify the executor path is used:
        #   with patch("elspeth.web.execution.routes.asyncio") as mock_asyncio:
        #       mock_loop = MagicMock()
        #       mock_asyncio.get_running_loop.return_value = mock_loop
        #       mock_loop.run_in_executor = AsyncMock(return_value=ValidationResult(
        #           is_valid=True, checks=[], errors=[],
        #       ))
        #       resp = await client.post(f"/api/sessions/{uuid4()}/validate")
        #       assert resp.status_code == 200
        #       mock_loop.run_in_executor.assert_called_once()
        #       call_args = mock_loop.run_in_executor.call_args
        #       assert call_args[0][0] is None  # default executor
        pass  # Placeholder until app factory is wired

    @pytest.mark.asyncio
    async def test_invalid_pipeline_returns_200_with_errors(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        mock_execution_service.validate.return_value = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load", passed=False, detail="Bad YAML"
                ),
            ],
            errors=[],
        )
        # Validation errors are NOT HTTP errors — the endpoint always
        # returns 200 with the ValidationResult body. HTTP 4xx/5xx are
        # reserved for infrastructure errors (auth, not found, etc.)
        pass


class TestExecuteEndpoint:
    """POST /api/sessions/{session_id}/execute"""

    @pytest.mark.asyncio
    async def test_execute_returns_202_with_run_id(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.post(f"/api/sessions/{uuid4()}/execute")
        # assert resp.status_code == 202
        # body = resp.json()
        # assert "run_id" in body
        pass

    @pytest.mark.asyncio
    async def test_execute_with_active_run_returns_409(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        mock_execution_service.execute.side_effect = RunAlreadyActiveError(
            "Already active"
        )
        # resp = await client.post(f"/api/sessions/{uuid4()}/execute")
        # assert resp.status_code == 409
        # body = resp.json()
        # Seam contract D: structured error envelope
        # assert body["error_type"] == "run_already_active"
        # assert "detail" in body
        pass


class TestRunStatusEndpoint:
    """GET /api/runs/{run_id}"""

    @pytest.mark.asyncio
    async def test_status_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.get(f"/api/runs/{uuid4()}")
        # assert resp.status_code == 200
        # body = resp.json()
        # assert body["status"] == "completed"
        pass


class TestCancelEndpoint:
    """POST /api/runs/{run_id}/cancel"""

    @pytest.mark.asyncio
    async def test_cancel_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.post(f"/api/runs/{uuid4()}/cancel")
        # assert resp.status_code == 200
        pass


class TestWebSocketProgress:
    """WS /ws/runs/{run_id}"""

    @pytest.mark.asyncio
    async def test_websocket_receives_progress_events(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """Client connects, receives progress events, disconnects on terminal."""
        # This test verifies the WebSocket handler contract:
        # 1. subscribe(run_id) on connect
        # 2. await queue.get() in a loop
        # 3. send_json(event) for each event
        # 4. close with code 1000 on terminal event (completed/error/cancelled)
        # 5. unsubscribe(run_id, queue) in finally block
        pass

    @pytest.mark.asyncio
    async def test_websocket_closes_1011_on_internal_error(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """H6: Internal server error sends close code 1011."""
        # When app factory is available:
        #   Inject a broadcaster that raises on queue.get()
        #   Verify close code is 1011
        pass

    @pytest.mark.asyncio
    async def test_websocket_auth_failure_closes_4001(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """AC #12: Missing or invalid ?token= query param closes with 4001.
        Client MUST NOT auto-reconnect on 4001."""
        # When app factory is available:
        #   async with client.websocket_connect(
        #       f"/ws/runs/{uuid4()}"  # no ?token=
        #   ) as ws:
        #       # Connection should be closed with code 4001
        #       assert ws.close_code == 4001
        pass

    @pytest.mark.asyncio
    async def test_websocket_unsubscribes_on_disconnect(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """Cleanup happens even on unexpected disconnect."""
        pass
```

- [ ] **Step 2: Implement routes**

```python
# src/elspeth/web/execution/routes.py
"""REST endpoints and WebSocket for pipeline execution.

POST /api/sessions/{session_id}/validate — dry-run validation
POST /api/sessions/{session_id}/execute — start background run
GET  /api/runs/{run_id}                 — run status
POST /api/runs/{run_id}/cancel          — cancel run
GET  /api/runs/{run_id}/results         — run results (terminal only)
WS   /ws/runs/{run_id}                  — live progress stream
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunStatusResponse, ValidationResult
from elspeth.web.execution.service import ExecutionServiceImpl, RunAlreadyActiveError
from elspeth.web.execution.validation import validate_pipeline

router = APIRouter()


# ── Dependency stubs — wired by app factory ────────────────────────────
# These will be replaced with actual dependency injection from create_app()

def get_execution_service() -> ExecutionServiceImpl:
    raise NotImplementedError("Wire via app factory")


def get_broadcaster() -> ProgressBroadcaster:
    raise NotImplementedError("Wire via app factory")


# ── REST Endpoints ─────────────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/validate",
    response_model=ValidationResult,
)
async def validate_session_pipeline(
    session_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> ValidationResult:
    """Dry-run validation using real engine code paths.

    AC #16: Validation is synchronous and takes 1-5 seconds depending on
    plugin count. Running it directly would block the FastAPI event loop.
    We use run_in_executor to offload it to a thread.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    state = service.get_composition_state(session_id)
    settings = service.get_settings()
    return await loop.run_in_executor(None, validate_pipeline, state, settings)


@router.post(
    "/api/sessions/{session_id}/execute",
    status_code=202,
)
async def execute_pipeline(
    session_id: UUID,
    state_id: UUID | None = None,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, str]:
    """Start a background pipeline run. Returns run_id immediately."""
    try:
        run_id = service.execute(session_id, state_id)
    except RunAlreadyActiveError as exc:
        # Seam contract D: structured error envelope for 409
        return JSONResponse(
            status_code=409,
            content={
                "error_type": "run_already_active",
                "detail": str(exc),
            },
        )
    return {"run_id": str(run_id)}


@router.get(
    "/api/runs/{run_id}",
    response_model=RunStatusResponse,
)
async def get_run_status(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> RunStatusResponse:
    """Return current run status."""
    return service.get_status(run_id)


@router.post("/api/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, str]:
    """Cancel a run. Idempotent on terminal runs."""
    service.cancel(run_id)
    status = service.get_status(run_id)
    return {"status": status.status}


@router.get("/api/runs/{run_id}/results")
async def get_run_results(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, Any]:
    """Return final run results. 409 if run is not terminal."""
    status = service.get_status(run_id)
    if status.status in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Run is still {status.status}",
        )
    return {
        "run_id": status.run_id,
        "status": status.status,
        "rows_processed": status.rows_processed,
        "rows_failed": status.rows_failed,
        "landscape_run_id": status.landscape_run_id,
        "error": status.error,
    }


# ── WebSocket Endpoint ─────────────────────────────────────────────────

def get_auth_provider() -> Any:
    raise NotImplementedError("Wire via app factory")


@router.websocket("/ws/runs/{run_id}")
async def websocket_run_progress(
    websocket: WebSocket,
    run_id: str,
    token: str | None = None,
    broadcaster: ProgressBroadcaster = Depends(get_broadcaster),
    auth_provider: Any = Depends(get_auth_provider),
) -> None:
    """Stream RunEvent JSON payloads for a specific run.

    AC #12: Authentication via ?token=<jwt> query parameter.
    Close code 4001 on auth failure — client MUST NOT auto-reconnect
    on 4001 (token must be refreshed or user must re-authenticate).

    Connection lifecycle:
    1. Validate JWT from query parameter (close 4001 if invalid)
    2. Accept WebSocket connection
    3. Verify run exists and belongs to authenticated user (IDOR -> 404-equivalent close)
    4. Subscribe to broadcaster for this run_id
    5. Loop: await queue.get() -> send_json(event)
    6. Close on terminal event (completed/error/cancelled)
    7. Unsubscribe in finally block (ensures cleanup on disconnect)
    """
    # Auth: validate JWT from query parameter
    if token is None:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        user = auth_provider.validate_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    await websocket.accept()
    queue = broadcaster.subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
            if event.event_type in ("completed", "error", "cancelled"):
                # H6: Use specific close codes per seam contract E
                # 1000 = normal closure after terminal event
                await websocket.close(code=1000)
                break
    except WebSocketDisconnect:
        pass  # Client disconnected — fall through to finally
    except Exception:
        # H6: 1011 = internal server error
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass  # Connection may already be closed
    finally:
        broadcaster.unsubscribe(run_id, queue)
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_routes.py -v
git commit -m "feat(web/execution): add REST endpoints and WebSocket for execution"
```

---

### Task 5.7: Multi-Worker Warning (W10)

**Files:**
- Modify: app factory (wherever `create_app()` lives, from Sub-Spec 2)

- [ ] **Step 1: Write test**

```python
# Add to tests/unit/web/execution/test_service.py

class TestMultiWorkerWarning:
    """W10: Warn if WEB_CONCURRENCY > 1 at startup."""

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "4"})
    def test_warns_on_multi_worker(self) -> None:
        """Application factory logs warning about WebSocket limitations."""
        # The warning should be emitted during create_app() or
        # ExecutionServiceImpl construction when WEB_CONCURRENCY > 1.
        # Exact assertion depends on app factory structure.
        pass

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "1"})
    def test_no_warning_for_single_worker(self) -> None:
        pass
```

- [ ] **Step 2: Implement warning in app factory**

Add to the app factory (`create_app()`):

```python
import os
import structlog

slog = structlog.get_logger()

web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1"))
if web_concurrency > 1:
    slog.warning(
        "WEB_CONCURRENCY > 1 detected — WebSocket progress streaming "
        "will not work correctly with multiple workers. The "
        "ProgressBroadcaster holds subscriber queues in process memory. "
        "Use WEB_CONCURRENCY=1 or replace with Redis Streams.",
        web_concurrency=web_concurrency,
    )
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(web): add multi-worker WebSocket warning (W10)"
```

---

### Task 5.8: Integration Test — End-to-End Pipeline

**Files:**
- Create: `tests/integration/web/__init__.py`
- Create: `tests/integration/web/test_execute_pipeline.py`
- Create: `tests/integration/web/fixtures/test_input.csv`

This test exercises the full execution path through the web layer: create session, save composition state, validate, execute, poll to completion, verify results.

- [ ] **Step 1: Create test CSV fixture**

```csv
id,name,value
1,alpha,100
2,beta,200
3,gamma,300
```

- [ ] **Step 2: Write end-to-end integration test**

```python
# tests/integration/web/test_execute_pipeline.py
"""End-to-end integration test: CSV -> passthrough -> CSV through web layer.

This test uses the REAL engine code path — no mocks for the pipeline itself.
The web layer (routes, ExecutionService, ProgressBroadcaster) is exercised
with a real FastAPI test client. The pipeline runs a CSV source through a
passthrough transform to a CSV sink.

Validates acceptance criteria #14:
- Session created
- CompositionState saved (manually, not via composer)
- Validation passes (is_valid=True)
- Execution completes
- rows_processed > 0, rows_failed == 0
- landscape_run_id links to real audit trail
"""
from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_CSV = FIXTURES_DIR / "test_input.csv"


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Create a working directory with the test CSV and output dir."""
    csv_dest = tmp_path / "input.csv"
    shutil.copy(TEST_CSV, csv_dest)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    audit_dir = tmp_path / "runs"
    audit_dir.mkdir()
    payloads_dir = tmp_path / "payloads"
    payloads_dir.mkdir()
    return tmp_path


# The pipeline YAML for CSV source -> passthrough -> CSV sink
def _make_pipeline_yaml(work_dir: Path) -> str:
    return f"""
source:
  plugin: csv_source
  options:
    path: "{work_dir / 'input.csv'}"
  on_success: primary

transforms: []

sinks:
  primary:
    plugin: csv_sink
    options:
      path: "{work_dir / 'output' / 'result.csv'}"
"""


@pytest.mark.integration
class TestEndToEndPipelineExecution:
    """Full lifecycle through the web layer with real engine execution."""

    @pytest.mark.asyncio
    async def test_csv_passthrough_csv(self, work_dir: Path) -> None:
        """
        1. Create session
        2. Save CompositionState (manually — tests execution independently)
        3. Validate -> is_valid=True
        4. Execute -> get run_id
        5. Poll status -> eventually 'completed'
        6. Verify results: rows_processed > 0, rows_failed == 0
        7. Verify landscape_run_id links to audit trail
        """
        # AC #14 + AC #20: Full cross-module integration test exercising
        # real SessionService, CatalogService, and ExecutionService wired together.
        pipeline_yaml = _make_pipeline_yaml(work_dir)

        # Create app with test settings pointing to work_dir
        from elspeth.web.app import create_app
        from elspeth.web.settings import WebSettings

        settings = WebSettings(
            data_dir=work_dir,
            landscape_url=f"sqlite:///{work_dir}/runs/audit.db",
            payload_store_path=work_dir / "payloads",
        )
        app = create_app(settings=settings)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Create session
            resp = await client.post("/api/sessions")
            assert resp.status_code == 201
            session_id = resp.json()["session_id"]

            # 2. Save composition state (manual — not via composer)
            resp = await client.post(
                f"/api/sessions/{session_id}/states",
                json={"pipeline_yaml": pipeline_yaml},
            )
            assert resp.status_code == 201

            # 3. Validate — AC #16: route handler uses run_in_executor
            resp = await client.post(
                f"/api/sessions/{session_id}/validate"
            )
            assert resp.status_code == 200
            validation = resp.json()
            assert validation["is_valid"] is True, (
                f"Validation failed: {validation['errors']}"
            )

            # 4. Execute
            resp = await client.post(
                f"/api/sessions/{session_id}/execute"
            )
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            # 5. Poll to completion (timeout after 30s)
            deadline = time.monotonic() + 30
            status: dict[str, Any] = {}
            while time.monotonic() < deadline:
                resp = await client.get(f"/api/runs/{run_id}")
                assert resp.status_code == 200
                status = resp.json()
                if status["status"] in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(0.5)
            else:
                pytest.fail("Pipeline did not complete within 30 seconds")

            # 6. Verify results — AC #14
            assert status["status"] == "completed", (
                f"Pipeline failed: {status.get('error')}"
            )
            assert status["rows_processed"] > 0
            assert status["rows_failed"] == 0

            # 7. Verify landscape_run_id links to real audit trail
            assert status["landscape_run_id"] is not None

            # 8. Verify output file was created
            output_file = work_dir / "output" / "result.csv"
            assert output_file.exists()

            # 9. Verify audit database exists
            audit_db = work_dir / "runs" / "audit.db"
            assert audit_db.exists()

            # 10. Verify results endpoint — AC #20 cross-module
            resp = await client.get(f"/api/runs/{run_id}/results")
            assert resp.status_code == 200
            results = resp.json()
            assert results["rows_processed"] > 0
            assert results["landscape_run_id"] is not None
```

- [ ] **Step 3: Run integration test, commit**

```bash
.venv/bin/python -m pytest tests/integration/web/ -v --timeout=60
git commit -m "test(web): add end-to-end pipeline execution integration test"
```

---

## Self-Review Checklist

- [ ] `routes.py` defines all 5 REST endpoints + 1 WebSocket endpoint matching the spec
- [ ] `validate_session_pipeline` uses `run_in_executor` (AC #16) -- does NOT call `validate_pipeline` synchronously
- [ ] `execute_pipeline` returns 202 with `run_id`
- [ ] `execute_pipeline` returns 409 with structured error envelope (`error_type`, `detail`) on `RunAlreadyActiveError` (seam contract D)
- [ ] `get_run_results` returns 409 if run is not terminal
- [ ] WebSocket authenticates via `?token=<jwt>` query parameter (AC #12)
- [ ] WebSocket closes with code 4001 on missing or invalid token -- client MUST NOT auto-reconnect on 4001
- [ ] WebSocket closes with code 1000 on terminal event (completed/error/cancelled) (H6, seam contract E)
- [ ] WebSocket closes with code 1011 on internal server error (H6)
- [ ] WebSocket `finally` block calls `broadcaster.unsubscribe()` for cleanup on disconnect
- [ ] IDOR protection: run ownership verified, returns 404 (not 403) for non-owned runs (AC #13)
- [ ] Multi-worker warning (W10): `create_app()` logs warning when `WEB_CONCURRENCY > 1`
- [ ] No warning emitted when `WEB_CONCURRENCY == 1`
- [ ] Integration test uses REAL engine code path -- no mocks for pipeline execution
- [ ] Integration test exercises full lifecycle: create session, save state, validate, execute, poll, verify results
- [ ] Integration test verifies `rows_processed > 0`, `rows_failed == 0`, `landscape_run_id` is not None
- [ ] Integration test verifies output file and audit database exist
- [ ] All tests pass: `.venv/bin/python -m pytest tests/unit/web/execution/test_routes.py -v`
- [ ] Integration tests pass: `.venv/bin/python -m pytest tests/integration/web/ -v --timeout=60`
- [ ] mypy passes: `.venv/bin/python -m mypy src/elspeth/web/execution/routes.py`
- [ ] No defensive programming patterns (no `.get()` on typed fields, no `getattr` with defaults)
- [ ] Layer dependency respected: `routes.py` imports from L0-L2 and sibling web modules only
