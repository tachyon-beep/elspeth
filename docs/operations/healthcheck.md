Health Check Server
===================

Overview
- Exposes `/health` (always 200 OK) and `/ready` (200 OK when ready, otherwise 503) for container/Kubernetes probes.
- Available via code (`serve` / `serve_in_thread`) and CLI (`python -m elspeth.cli health-server --port 8080`).

Security Considerations
- Bind Address: The server defaults to `0.0.0.0` for container friendliness. In local or multi-tenant environments, prefer `127.0.0.1` or restrict exposure using firewall rules, Kubernetes NetworkPolicies, or Ingress.
- Daemon Thread: `serve_in_thread()` runs the server in a daemon thread which does not prevent process exit and may be terminated abruptly during shutdown. This is acceptable for liveness/readiness probes.

Usage Examples
- Programmatic: `serve(host="127.0.0.1", port=8080, ready_check=my_ready_func)`
- CLI: `python -m elspeth.cli health-server --port 8080`

Readiness Logic
- Pass an optional `ready_check` callable to report dynamic readiness. When it returns `True`, `/ready` returns 200. Otherwise, it returns 503 with `{ "status": "not_ready" }`.

