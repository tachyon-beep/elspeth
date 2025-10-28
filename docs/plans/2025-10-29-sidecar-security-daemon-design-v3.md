# Sidecar Security Daemon – Rust Implementation (v3 Draft)

**Date:** 2025-10-29  
**Status:** Draft Design – Rust sidecar implementation  
**Author:** Claude Code (with John)  
**Related Issues:** #40 (CVE-ADR-002-A-009: Secret Export Vulnerability)  
**Related ADRs:** ADR-002, ADR-002-A, ADR-002-B, ADR-003, ADR-004  
**Supersedes:** `2025-10-29-sidecar-security-daemon-design-v2.md` (Python prototype)

---

## Executive Summary

To harden `SecureDataFrame` against insider laundering while keeping latency low, we move the capability token and seal key into a native Rust sidecar. The daemon runs as a separate UID, owns the secrets, exposes a minimal authenticated IPC protocol, and returns seals plus authorization proofs to the trusted orchestrator. Untrusted plugin code executes behind proxy objects and never receives genuine `SecureDataFrame` instances. This architecture preserves the high-water-mark enforcement from ADR-002/002-A/002-B and closes CVE-ADR-002-A-009 with production-ready performance.

**Security Highlights**

- ✅ **Secrets in Rust memory:** Token & seal key live only inside the Rust daemon (zero Python exposure).  
- ✅ **Grant-based protocol:** Two-phase authorize → redeem workflow; handles are one-shot, MAC’d, server-side validated.  
- ✅ **Three-UID separation:** `sidecar` (daemon), `appuser` (orchestrator), `appplugin` (plugin workers).  
- ✅ **SO_PEERCRED enforcement:** Daemon rejects any client not running as UID `appuser`.  
- ✅ **Proxy isolation:** Plugin workers see only `SecureFrameProxy` handles; orchestrator performs all seal operations.  
- ✅ **Fail-closed:** Any IPC failure aborts the pipeline—no degraded fallback in sidecar mode.  
- ✅ **Standalone mode:** Explicit opt-in (`OFFICIAL_SENSITIVE` ceiling) retains dev ergonomics with documented risk.

---

## Architecture Overview

### Process / UID Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ Container (python:3.12-slim + Rust)                                  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ supervisord (PID 1, root)                                    │     │
│  │  ├─ prepare-sidecar-dir (root → chown /run/sidecar 0750)     │     │
│  │  ├─ sidecar-daemon (UID 1001:sidecar)                        │     │
│  │  │    • Rust binary holding token & seal key                 │     │
│  │  │    • Unix socket: /run/sidecar/auth.sock (0600)           │     │
│  │  │    • Session key file: /run/sidecar/.session (0640)       │     │
│  │  ├─ orchestrator (UID 1000:appuser)                          │     │
│  │  │    • Reads session key, keeps persistent UDS connection   │     │
│  │  │    • Owns real SecureDataFrame objects in-process         │     │
│  │  │    • Spawns plugin worker(s) as UID 1002                  │     │
│  │  └─ plugin-worker (UID 1002:appplugin)                       │     │
│  │       • Runs untrusted plugin code                           │     │
│  │       • Receives only SecureFrameProxy handles               │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### Threat Model Recap

- Plugins are audited & signed but may attempt laundering (e.g., relabeling) or introduce accidental mistakes.
- Orchestrator + datasource pipeline is trusted; only this code may mint `SecureDataFrame` instances.
- Attack to block: trusted insider attempts to wrap data in a fresh `SecureDataFrame` so it appears legitimate.
- Python-level isolation alone is insufficient; introspection can reach any secret kept in-process.

---

## Rust Sidecar Design

### Responsibilities

- Hold `_CONSTRUCTION_TOKEN` and `_SEAL_KEY` in native memory.
- Authorize SecureDataFrame creation and compute/verify seals on demand.
- Enforce single-use grants with server-side state.
- Authenticate clients via HMAC (session key) plus SO_PEERCRED UID checks.
- Provide minimal, deterministic IPC for microsecond-level latency.

### Implementation Notes

- **Language:** Rust 1.77+, edition 2021.  
- **Binary:** `elspeth-sidecar-daemon`.  
- **Crypto:** `ring` for HMAC-BLAKE2s (or BLAKE3) and constant-time comparisons.  
- **IPC:** Tokio async runtime + `tokio-uds` (Unix sockets).  
- **Message format:** Compact CBOR (newline-delimited frames) via `serde_cbor`.  
- **State:** `DashMap<GrantId, GrantState>` with TTL cleanup task.  
- **Metrics/logging:** `tracing` crate; no secret material logged.  
- **Config:** Socket path, session key path, log level; provided via env or config file.

### Protocol Specification

| Message | Direction | Fields | Description |
|---------|-----------|--------|-------------|
| `AuthorizeConstruct` | Orchestrator → Daemon | `{ "op": "authorize_construct", "data_id": u64, "level": u32, "auth": hmac }` | Request a one-shot grant for `(data_id, level)`. |
| `AuthorizeConstructReply` | Daemon → Orchestrator | `{ "grant_id": bytes[16], "expires_at": f64 }` | Grant registered; expires after 60 s. |
| `RedeemGrant` | Orchestrator → Daemon | `{ "op": "redeem_grant", "grant_id": bytes[16], "auth": hmac }` | Redeem the grant for a seal. |
| `RedeemGrantReply` | Daemon → Orchestrator | `{ "seal": bytes[32], "audit_id": u64 }` | Seal computed using daemon key; token never leaves daemon. |
| `ComputeSeal` | Orchestrator → Daemon | `{ "op": "compute_seal", "data_id": u64, "level": u32, "auth": hmac }` | Compute seal for existing frame metadata. |
| `VerifySeal` | Orchestrator → Daemon | `{ "op": "verify_seal", "data_id": u64, "level": u32, "seal": bytes[32], "auth": hmac }` | Check seal integrity. |
| `Error` | Daemon → Orchestrator | `{ "error": "string", "reason": "string" }` | Failure response; log-only reason. |

**GrantId:** 128-bit random handle, MAC’d internally.  
**AuditId:** Monotonic counter (logged for traceability only).  
**Session Key:** 256-bit random, persisted to `/run/sidecar/.session` (0640 `sidecar:appuser`).  
**HMAC:** `HMAC-BLAKE2s(session_key, canonical_cbor(request_without_auth))`.  
**Timeouts:** connect 50 ms; authorize/redeem 100 ms; compute/verify 75 ms.  
**Retries:** none—fail closed by design.

### Performance Targets

- Single daemon instance handles ≥ 50 k ops/s (async runtime, zero-copy CBOR).  
- P99 latency per request ≤ 150 µs under load.  
- Supports 32 concurrent orchestrator connections (configurable).  
- Memory footprint < 10 MB.

---

## Orchestrator Integration

### Sidecar Client (Python)

- Replaces `_create_secure_factories`; maintains a small pool of persistent Unix-socket connections.  
- Uses asyncio with background tasks (or synchronous wrapper) to serialize requests.  
- Signs each message with HMAC; raises `SecurityValidationError` on any `Error` reply.  
- Surfaces daemon `audit_id` in logs for traceability.

### SecureDataFrame Factories

- `_from_sidecar(...)` (orchestrator-only) consumes daemon-provided seals verbatim.  
- `create_from_datasource`: authorize → redeem → `_from_sidecar`.  
- Uplift / new-data flows skip authorize and use `ComputeSeal` + `_from_sidecar`.  
- `_verify_seal` calls `VerifySeal` via sidecar client; failures trigger `SecurityValidationError`.

### SecureFrameProxy (Worker Isolation)

- Plugin workers receive opaque `SecureFrameProxy` handles.  
- Proxy methods marshal RPCs to orchestrator (msgpack over a dedicated pipe/queue).  
- Orchestrator RPC handlers call the Rust sidecar, create new frames via `_from_sidecar`, and return fresh proxy IDs.  
- Plugin code never touches real frames, secrets, or seal routines.

### Worker ↔ Orchestrator RPC Schema (msgpack)

```python
# Request (plugin worker → orchestrator)
{"op": "with_uplifted_security_level", "proxy_id": "hex", "level": "SECRET"}

# Response (orchestrator → plugin worker)
{"status": "ok", "new_proxy_id": "hex", "audit_id": 12345}
```

All orchestrator responses include the daemon-issued `audit_id`.

---

## Rust Daemon Skeleton (Pseudo-Code)

```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::load("/etc/elspeth/sidecar.toml")?;
    let secrets = Arc::new(Secrets::generate()); // holds token + seal key
    let grants = Arc::new(GrantTable::new(config.grant_ttl));
    let listener = UdsListener::bind(&config.socket_path)?;

    Listener::prepare_socket(&listener, &config)?;

    loop {
        let (stream, _) = listener.accept().await?;
        let creds = stream.get_peer_credentials()?; // SO_PEERCRED

        if creds.uid() != config.appuser_uid {
            tracing::warn!(uid = creds.uid(), gid = creds.gid(), "connection denied");
            continue;
        }

        let session_key = config.session_key.clone();
        let grants = grants.clone();
        let secrets = secrets.clone();

        tokio::spawn(async move {
            if let Err(err) = handle_client(stream, &session_key, grants, secrets).await {
                tracing::error!(%err, "client connection error");
            }
        });
    }
}
```

`handle_client` loops over CBOR frames, validates HMAC, executes the requested operation, and writes back the response.

---

## Docker / Supervisord Updates

### Dockerfile (Excerpt)

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl build-essential pkg-config libssl-dev \
  && curl https://sh.rustup.rs -sSf | sh -s -- -y --profile minimal \
  && /root/.cargo/bin/cargo build --release --manifest-path sidecar/Cargo.toml \
  && cp sidecar/target/release/elspeth-sidecar-daemon /usr/local/bin/ \
  && apt-get purge -y curl build-essential pkg-config libssl-dev \
  && rm -rf /var/lib/apt/lists/*

COPY sidecar/Config.toml /etc/elspeth/sidecar.toml
```

### Supervisord

```ini
[program:sidecar-daemon]
command=/usr/local/bin/elspeth-sidecar-daemon --config /etc/elspeth/sidecar.toml
user=sidecar
priority=1
autorestart=true
stdout_logfile=/dev/stdout
stderr_logfile=/dev/stderr

[program:orchestrator]
command=python -m elspeth.cli %(ENV_ELSPETH_CLI_ARGS)s
user=appuser
priority=2
depends_on=sidecar-daemon

[program:plugin-worker]
command=python -m elspeth.plugins.worker
user=appplugin
priority=3
depends_on=orchestrator
```

---

## Testing Strategy

1. **Rust Unit Tests**
   - Grant creation/redeem lifecycle, TTL expiry, double-redeem rejection.
   - HMAC validation (missing/incorrect).
   - SO_PEERCRED enforcement (mock credentials).
   - Seal computation parity against Python reference implementation.

2. **Rust Integration Tests**
   - Full authorize → redeem flow via Unix socket.
   - Compute/verify seal success + failure paths.
   - Concurrent clients (stress test with Tokio tasks).

3. **Python Integration Tests**
   - Datasource creation, uplift, new-data flows succeed end-to-end.
   - Plugin worker attempts direct socket use → connection denied.
   - Replay attack (reuse grant) → fails cleanly.
   - Corrupted HMAC → `SecurityValidationError`.

4. **Performance Benchmarks**
   - Rust `criterion` microbenchmarks (local operations).  
   - Python load test (e.g., `pytest-benchmark`) targeting ≥ 1 k frames/sec.

5. **Security Regression Tests**
   - Ensure `_CONSTRUCTION_TOKEN` / `_SEAL_KEY` never appear in Python heap snapshots.  
   - Validate audit logs hold only metadata (no secrets, no raw IDs).
   - Simulate sidecar outage → orchestrator fails closed.

---

## Operational Runbook

- **Startup Checks**
  - `ls -l /run/sidecar/auth.sock` → `srw------- sidecar sidecar`.  
  - `ls -l /run/sidecar/.session` → `-rw-r----- sidecar appuser 32`.  
  - `supervisorctl status` → sidecar, orchestrator, plugin-worker all RUNNING.

- **Health Monitoring**
  - Optional HTTP `/healthz` from sidecar (reports build hash, uptime).  
  - Metrics: `sidecar.requests`, `sidecar.failures`, `sidecar.grants_active`.

- **Alerting**
  - Sidecar restart → WARN.  
  - Grant redemption failure → ERROR (with audit_id).  
  - UID mismatch connection attempts → WARN (potential compromise).

- **Incident Response**
  - Sidecar unavailable → orchestrator aborts; restart container, inspect logs.  
  - Repeated UID violations → escalate to security (possible privilege escalation).

---

## Open Questions

1. **Multi-worker coordination:** One orchestrator per worker vs. proxy multiplexing—does orchestration overhead stay manageable under heavy load?  
2. **Protocol extensibility:** If future workflows need batch operations, do we extend the CBOR schema or adopt Protobuf/Cap’n Proto?  
3. **Key rotation cadence:** Rotation currently happens on daemon restart; do we require live rotation plus orchestrator re-auth?  
4. **Observability:** Integrate Rust `tracing` with Python logging via OpenTelemetry for unified security audit?

---

## Implementation Checklist

| Item | Owner | Status |
|------|-------|--------|
| Rust sidecar skeleton | Security | ☐ |
| IPC schema + serde models | Security | ☐ |
| Python sidecar client | Core | ☐ |
| SecureFrameProxy + orchestrator RPC handler | Core | ☐ |
| Dockerfile & supervisord updates | Ops | ☐ |
| Automated tests (Rust & Python) | QA | ☐ |
| Documentation & runbooks | Docs | ☐ |

---

## Summary

Switching to a Rust sidecar delivers:

- **Security:** Secrets never touch Python memory; laundering requires breaching the daemon boundary.  
- **Performance:** Native code handles tens of thousands of ops/sec, keeping pace with 1 k+ frames/sec workloads.  
- **Operational clarity:** UID separation, SO_PEERCRED, and audit logs align with existing compliance workflows.  
- **Developer experience:** Datasource and plugin contracts remain familiar; only orchestrator internals change to use grants and proxies.

Once approved, this design replaces the Python prototype and provides a production-ready path to close CVE-ADR-002-A-009 without sacrificing throughput.
