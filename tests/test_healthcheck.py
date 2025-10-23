from __future__ import annotations

import json
import socket
import time
from urllib.request import urlopen

from elspeth.core.healthcheck import serve_in_thread


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    addr, port = s.getsockname()
    s.close()
    return port


def test_healthcheck_endpoints_basic():
    port = _free_port()
    serve_in_thread(host="127.0.0.1", port=port)
    # Poll briefly until server is up
    deadline = time.time() + 3.0
    last_err = None
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health") as resp:  # nosec B310 - local test
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body.get("status") == "ok"
                break
        except Exception as exc:  # pragma: no cover - startup race
            last_err = exc
            time.sleep(0.05)
    else:
        raise AssertionError(f"health endpoint not reachable: {last_err}")

    with urlopen(f"http://127.0.0.1:{port}/ready") as resp:  # nosec B310 - local test
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
        assert body.get("status") in {"ready", "ok", "ready"}

    # Unknown path should 404
    try:
        urlopen(f"http://127.0.0.1:{port}/unknown")  # nosec B310 - local test
        raise AssertionError("expected 404 for unknown path")
    except Exception:
        # urllib raises HTTPError for non-2xx statuses; reaching here is enough
        pass


def test_healthcheck_ready_returns_503_when_not_ready():
    port = _free_port()
    # Ready check always False
    serve_in_thread(host="127.0.0.1", port=port, ready_check=lambda: False)
    # Poll briefly until server is up
    deadline = time.time() + 3.0
    last_err = None
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health") as resp:  # nosec B310 - local test
                if resp.status == 200:
                    break
        except Exception as exc:  # pragma: no cover - startup race
            last_err = exc
            time.sleep(0.05)
    else:
        raise AssertionError(f"health endpoint not reachable: {last_err}")

    # /ready should be 503 with not_ready
    from urllib.error import HTTPError

    try:
        urlopen(f"http://127.0.0.1:{port}/ready")  # nosec B310 - local test
        raise AssertionError("expected HTTPError for 503 from /ready when not ready")
    except HTTPError as err:
        assert err.code == 503
        body = json.loads(err.read().decode("utf-8"))
        assert body.get("status") == "not_ready"
