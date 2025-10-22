# isort: skip_file
"""HTTP health check server for container orchestration.

Provides /health and /ready endpoints suitable for Kubernetes liveness/readiness probes.

Security note:
- The default bind address is "0.0.0.0" to be container-friendly. This exposes the
  endpoints on all interfaces. In local or multi-tenant environments, prefer
  "127.0.0.1" or restrict exposure via network policy/ingress.
- The background server uses a daemon thread; it will not block process exit and
  may be terminated abruptly on shutdown. This is acceptable for health probes
  but should be considered if reusing for other purposes.

Usage (programmatic):
    from elspeth.core.healthcheck import serve
    serve(host="0.0.0.0", port=8080)

CLI: `python -m elspeth.cli health-server --port 8080`
"""

import logging


logger = logging.getLogger(__name__)


class _HealthState:
    def __init__(self, ready_check=None) -> None:
        self.ready_check = ready_check or (lambda: True)


def _make_handler(state: _HealthState):
    from http.server import BaseHTTPRequestHandler  # local import to avoid top-level sort issues
    import json  # local import

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003 - BaseHTTPRequestHandler API
            logger.debug("healthcheck: " + format, *args)

        def _write_json(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path.startswith("/health"):
                self._write_json(200, {"status": "ok"})
                return
            if self.path.startswith("/ready"):
                try:
                    ready = bool(state.ready_check())
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("readiness check failed: %s", exc, exc_info=False)
                    ready = False
                code = 200 if ready else 503
                body = {"status": "ready" if ready else "not_ready"}
                self._write_json(code, body)
                return
            self._write_json(404, {"error": "not_found"})

    return Handler


def serve(host: str = "0.0.0.0", port: int = 8080, *, ready_check=None) -> None:
    """Start a blocking HTTP health server.

    Args:
        host: Interface to bind.
        port: TCP port to listen on.
        ready_check: Optional callable returning True when service is ready.
    """
    state = _HealthState(ready_check=ready_check)
    from http.server import HTTPServer  # local import

    server = HTTPServer((host, port), _make_handler(state))
    logger.info("Healthcheck server listening on %s:%d", host, port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        logger.info("Healthcheck server stopping (KeyboardInterrupt)")
    finally:
        server.server_close()


def serve_in_thread(host: str = "0.0.0.0", port: int = 8080, *, ready_check=None):
    """Start the health server in a background daemon thread.

    Returns the thread; caller is responsible for lifecycle.
    """
    import threading  # local import

    thread = threading.Thread(target=serve, args=(host, port), kwargs={"ready_check": ready_check}, daemon=True)
    thread.start()
    return thread


__all__ = ["serve", "serve_in_thread"]
