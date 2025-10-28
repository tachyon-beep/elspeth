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
- ✅ **Digest-bound seals:** Every authorize/compute/verify call includes a BLAKE3 digest of canonical Parquet bytes, preventing data swaps and post-creation tampering.  
- ✅ **Grant-based protocol:** Two-phase authorize → redeem workflow; handles are one-shot, MAC’d, server-side validated.  
- ✅ **Three-UID separation:** `sidecar` (daemon), `appuser` (orchestrator), `appplugin` (plugin workers).  
- ✅ **SO_PEERCRED enforcement:** Daemon rejects any client not running as UID `appuser`.  
- ✅ **Descriptor hygiene:** Session-key and sidecar sockets are opened with `FD_CLOEXEC` (or created after worker fork) so plugin processes never inherit authenticated handles.  
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

**UID separation in practice**
- `sidecar` (UID 1001) owns `/run/sidecar/*` and is the only process that ever holds the capability token or seal key in memory.
- `appuser` (UID 1000) runs the orchestrator, reads the session key, and is the sole client allowed to connect to the daemon socket.
- `appplugin` (UID 1002) hosts plugin workers; it never learns the session key and all direct socket attempts are rejected via SO_PEERCRED.
- Orchestrator marks the session-key file descriptor and every sidecar socket `FD_CLOEXEC`, or creates the daemon connection only after the plugin workers have been fork/exec’d, guaranteeing no authenticated descriptors leak into untrusted processes.

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
- Bind every seal to a canonical digest of the DataFrame payload (`data_digest`).
- Enforce single-use grants with server-side state.
- Authenticate clients via HMAC (session key) plus SO_PEERCRED UID checks.
- Provide minimal, deterministic IPC for microsecond-level latency.

### Implementation Notes

- **Language:** Rust 1.77+, edition 2021.  
- **Binary:** `elspeth-sidecar-daemon`.  
- **Crypto:** `ring` for HMAC-BLAKE2s (or BLAKE3) and constant-time comparisons.  
- **IPC:** Tokio async runtime + `tokio-uds` (Unix sockets).  
- **Message format:** Compact CBOR (newline-delimited frames) via `serde_cbor`.  
- **State:** `DashMap<GrantId, GrantState>` with TTL cleanup task. Each `GrantState` records `(frame_id, level, data_digest)` ensuring redeems always use the original digest.  
- **Metrics/logging:** `tracing` crate; no secret material logged.  
- **Config:** Socket path, session key path, log level; provided via env or config file.
- **Descriptor hygiene:** All Unix sockets and session-key files are opened with `O_CLOEXEC` / `FD_CLOEXEC`, and the orchestrator establishes sidecar connections only after spawning plugin workers when using fork/exec.

### Protocol Specification

| Message | Direction | Fields | Description |
|---------|-----------|--------|-------------|
| `AuthorizeConstruct` | Orchestrator → Daemon | `{ "op": "authorize_construct", "frame_id": bytes[16], "level": u32, "data_digest": bytes[32], "auth": hmac }` | Request a one-shot grant for `(frame_id, level, digest)`. |
| `AuthorizeConstructReply` | Daemon → Orchestrator | `{ "grant_id": bytes[16], "expires_at": f64 }` | Grant registered; expires after 60 s. |
| `RedeemGrant` | Orchestrator → Daemon | `{ "op": "redeem_grant", "grant_id": bytes[16], "auth": hmac }` | Redeem the grant for a seal (digest looked up from grant). |
| `RedeemGrantReply` | Daemon → Orchestrator | `{ "seal": bytes[32], "audit_id": u64 }` | Seal computed from `(frame_id, level, digest)`; token never leaves daemon. |
| `ComputeSeal` | Orchestrator → Daemon | `{ "op": "compute_seal", "frame_id": bytes[16], "level": u32, "data_digest": bytes[32], "auth": hmac }` | Compute seal for existing frame metadata + digest. |
| `VerifySeal` | Orchestrator → Daemon | `{ "op": "verify_seal", "frame_id": bytes[16], "level": u32, "data_digest": bytes[32], "seal": bytes[32], "auth": hmac }` | Check seal integrity against the digest. |
| `Error` | Daemon → Orchestrator | `{ "error": "string", "reason": "string" }` | Failure response; log-only reason. |

**GrantId:** 128-bit random handle, MAC’d internally.  
**AuditId:** Monotonic counter (logged for traceability only).  
**Session Key:** 256-bit random, persisted to `/run/sidecar/.session` (0640 `sidecar:appuser`).  
**Data Digest:** 256-bit BLAKE3 hash of a canonical Parquet serialization (`df.to_parquet()` with sorted columns/index) computed in orchestrator.  
**HMAC:** `HMAC-BLAKE2s(session_key, canonical_cbor(request_without_auth))`.  
**Seal Definition:** `seal = HMAC-BLAKE2s(_SEAL_KEY, frame_id || level || data_digest)` stored in daemon memory and returned on redeem/compute.  
**Timeouts:** connect 50 ms; authorize/redeem 100 ms; compute/verify 75 ms.  
**Retries:** none—fail closed by design.

**Registered frame guard:** `RedeemGrant` inserts the `(frame_id, level)` pair into a `RegisteredFrameTable`. Both `ComputeSeal` and `VerifySeal` must reject any request whose `frame_id` is absent from this table (or marked revoked) so future regressions cannot mint fresh frames via `compute_seal` without first passing through the grant flow. The Python `FrameRegistry` enforces the same invariant and raises `SecurityValidationError` if a caller attempts to reseal or verify an unknown `frame_id`.

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
- Exposes typed helpers (`authorize_construct`, `compute_seal`, `verify_seal`) that require explicit `frame_id`, `level`, and `data_digest` arguments; digests are BLAKE3 hashes of canonical Parquet bytes computed in orchestrator code.
- Ensures no authenticated descriptors leak to plugin workers: open the session key and initiate sidecar connections only after worker processes are spawned, or set `FD_CLOEXEC` on every sensitive file descriptor before the fork.

### SecureDataFrame Factories

- **Stable frame identifiers:** Each SecureDataFrame receives a 128-bit `frame_id` generated by the orchestrator’s registry. The id is stable for the lifetime of the frame and never derived from `id()` pointers, preventing reuse after GC.  
- **Canonical data digest:** Every seal operation includes `data_digest = blake3(parquet_frame_bytes)` where parquet bytes are produced via deterministic serialization (sorted columns/index, little-endian types). Digests are recomputed on every mutation and stored alongside the frame in the registry.  
- `_from_sidecar(frame_id, level, data_digest, seal)` (orchestrator-only) consumes daemon-provided seals verbatim and persists the digest in the registry entry.  
- `create_from_datasource`: orchestrator computes digest → authorize (frame_id, level, digest) → redeem → `_from_sidecar`.  
- Uplift / new-data flows reuse the existing `frame_id`, compute a fresh digest, call `ComputeSeal(frame_id, level, digest)`, and construct a new instance via `_from_sidecar`.  
- `_verify_seal` recomputes the digest, sends `VerifySeal(frame_id, level, digest, seal)` to the daemon, and raises `SecurityValidationError` on mismatch.

The orchestrator maintains a `FrameRegistry`, a process-local map from `frame_id` → `{frame, digest, level}`. Frame ids are generated as 16-byte UUIDv4 values, never reused, and retained until the corresponding frame is explicitly de-registered. Grant TTL (60 s) is shorter than the registry retention window, eliminating the possibility of re-binding a stale `frame_id` to a different dataframe during grant redemption.

```python
def compute_canonical_digest(df: pd.DataFrame) -> bytes:
    """Return BLAKE3 digest over canonical Parquet representation."""
    buffer = io.BytesIO()
    (
        df.sort_index(axis=0, key=_stable_sort_key)
        .sort_index(axis=1, key=_stable_sort_key)
        .as_type_safe()
    ).to_parquet(
        buffer,
        engine="pyarrow",
        compression=None,
        index=True,
        coerce_timestamps="us",
        use_deprecated_int96_timestamps=False
    )
    return blake3(buffer.getvalue()).digest()
```

Canonicalization rules:

- `as_type_safe()` converts any unsupported dtypes (e.g., mixed-object, extension arrays we do not certify) into lossless, ordered Arrow-compatible representations. If we encounter data we cannot canonically serialize, we raise `SecurityValidationError` with a clear remediation message instead of letting a `to_parquet` crash propagate.
- `_stable_sort_key` produces tuple-based ordering for heterogeneous labels, guaranteeing deterministic ordering even when columns/indices mix ints and strings. This prevents malicious or legacy frames from causing sort-time type errors.
- The orchestrator logs and rejects frames that still fail canonicalization so a plugin cannot DoS the pipeline; datasources must normalize their schema before retrying.

Helper primitives (Python pseudocode):

```python
def _stable_sort_key(label: Hashable) -> tuple:
    """Return total-orderable key for heterogeneous labels."""
    return (
        type(label).__name__,
        str(label) if isinstance(label, (Enum, Path)) else label,
    )

def DataFrame.as_type_safe(self: pd.DataFrame) -> pd.DataFrame:
    """Map unsupported dtypes into deterministic Arrow-friendly encodings."""
    converted = {}
    for name, series in self.items():
        if series.dtype in _SUPPORTED_ARROW_DTYPES:
            converted[name] = series
        else:
            converted[name] = _encode_extension_series(series)
    return pd.DataFrame(converted, index=self.index)
```

`_encode_extension_series` delegates to specific adapters (e.g., categorical → codes + metadata columns, complex decimals → string canonicalization) and records the adapter identity in the registry so seal validation knows how to reverse the process for auditing. During canonicalization failures we emit both the offending column name and dtype in the raised `SecurityValidationError`.

Canonicalization pipeline:

```
┌────────────┐   sort_index(axis=0, key=_stable_sort_key)
│ DataFrame  │ ───────────────────────────────────────────► ┌────────────┐
└────────────┘                                             │ Row-sorted  │
                                                           │ DataFrame   │
                                                           └────────────┘
          ▲                    sort_index(axis=1, key=_stable_sort_key)
          │────────────────────────────────────────────────────────────►
                                                           ┌────────────┐
                                                           │ Row + Col  │
                                                           │ Sorted     │
                                                           └────────────┘
          ▲                          as_type_safe()
          │───────────────────────────────────────────────► ┌────────────┐
                                                           │ Arrow-safe  │
                                                           │ DataFrame   │
                                                           └────────────┘
          ▲                          Arrow serialization (parquet)
          │───────────────────────────────────────────────► ┌────────────┐
                                                           │ Parquet     │
                                                           │ Bytes       │
                                                           └────────────┘
          ▲                          BLAKE3
          │───────────────────────────────────────────────► ┌────────────┐
                                                           │ Digest      │
                                                           │ (32 bytes)  │
                                                           └────────────┘
```

```rust
fn seal_from_digest(frame_id: [u8; 16], level: u32, digest: [u8; 32], seal_key: &[u8]) -> [u8; 32] {
    let mut mac = hmac::Key::new(hmac::HMAC_SHA256, seal_key);
    hmac::sign(&mac, &[&frame_id, &level.to_be_bytes(), &digest].concat()).as_ref().try_into().unwrap()
}
```

### SecureFrameProxy (Worker Isolation)

- Plugin workers receive opaque `SecureFrameProxy` handles.  
- Proxy methods marshal allow-listed RPCs (`get_view`, `replace_data`, `with_uplifted_security_level`, `with_new_data`) to the orchestrator over msgpack.  
- Read access returns immutable snapshots: `get_view()` materializes a deep copy of the frame (Arrow round-trip) and tags it with a view version. Workers cannot mutate the live frame through shared references, and any attempt to push a modified snapshot back must go through `replace_data(new_df)` which recomputes the digest and bumps the version.  
- We record the view version and digest on the orchestrator; if a worker tries to reuse a stale snapshot (version mismatch) or mutate outside the RPC flow, the orchestrator raises `SecurityValidationError` and logs the attempt. This keeps the existing security guarantees while preserving debuggability.  
- Orchestrator RPC handlers recompute the canonical digest, call the Rust sidecar with `(frame_id, level, data_digest)`, create new frames via `_from_sidecar`, and return fresh proxy IDs.  
- Plugin code never touches real frames, secrets, or seal routines.

Concrete proxy flow:

1. **Proxy creation** – When the orchestrator hands a frame to the worker it stores `{proxy_id, frame_id, version, digest}` in a `ProxyTable`. The worker receives only `SecureFrameProxy(proxy_id)`.
2. **View retrieval (`get_view`)** – Worker invokes `{"op":"get_view","proxy_id":...}`. The orchestrator deep-copies the frame (`frame.data.copy(deep=True)`), serializes it with Arrow IPC, increments the `version`, and returns `{status:"ok", view:bytes, version:int}`. The worker surfaces the DataFrame to plugin code but tags it with the returned version.
3. **Mutation (`replace_data`)** – Worker sends back the mutated payload plus the version it was derived from. The orchestrator checks the version, re-canonicalizes the payload, recomputes the digest, invokes `ComputeSeal` on the sidecar, creates a new frame via `_from_sidecar`, updates both `FrameRegistry` and `ProxyTable`, and replies with the new proxy id + version.
4. **Security checks** – Version mismatch, canonicalization failure, or sidecar rejection all raise `SecurityValidationError` and invalidate the proxy. We log the proxy id, plugin name, and audit id for forensics.

RPC schema additions:

```python
# Worker → orchestrator (mutation)
{"op": "replace_data", "proxy_id": "hex", "version": 5, "payload": arrow_bytes}

# Orchestrator → worker (mutation response)
{"status": "ok", "new_proxy_id": "hex", "version": 6, "audit_id": 4242}
```

`with_uplifted_security_level` follows the same pattern but augments the RPC with the requested level. Orchestrator-side handlers perform seal verification first (`VerifySeal`), then call `ComputeSeal` for the uplift and return the new proxy. All RPC handlers run in a dedicated asyncio task with backpressure so malicious workers cannot starve the orchestrator main loop.

Proxy/sidecar interaction (sequence diagram):

```
Plugin Worker (UID 1002)         Orchestrator (UID 1000)            Rust Sidecar (UID 1001)
        |                                  |                                   |
        | get_view(proxy)                  |                                   |
        |─────────────────────────────────►|                                   |
        |                                  | deep copy + serialize             |
        |                                  |                                   |
        |            view bytes + version  |                                   |
        |◄─────────────────────────────────|                                   |
        | mutate snapshot                  |                                   |
        | replace_data(proxy, version, df) |                                   |
        |─────────────────────────────────►| compute digest                    |
        |                                  | authorize/compute request         |
        |                                  |──────────────────────────────────►|
        |                                  |      seal, audit_id               |
        |                                  |◄──────────────────────────────────|
        |                                  | create new frame + proxy          |
        |          status OK, new_proxy_id |                                   |
        |◄─────────────────────────────────|                                   |
        | continue with new proxy          |                                   |
```

IPC message definitions (Msgpack/CBOR over Unix socket):

| Operation | Direction | Required Fields | Description |
|-----------|-----------|-----------------|-------------|
| `get_view` | Worker → Orchestrator | `proxy_id` | Request immutable snapshot of current frame; orchestrator replies with `status`, `view` (Arrow IPC bytes), `version`. |
| `replace_data` | Worker → Orchestrator | `proxy_id`, `version`, `payload` | Submit mutated snapshot derived from `version`. Orchestrator recomputes digest, reseals via sidecar, returns `new_proxy_id`, `version+1`, `audit_id`. |
| `with_uplifted_security_level` | Worker → Orchestrator | `proxy_id`, `version`, `level` | Request higher classification; orchestrator verifies seal, reseals at new level, responds like `replace_data`. |
| `get_metadata` | Worker → Orchestrator | `proxy_id` | Retrieve read-only proxy metadata (level, version, audit trail id); no sidecar call. |
| `verify_clearance` | Worker → Orchestrator | `proxy_id`, `requested_level` | Validates access against current frame level; orchestrator uses existing metadata, no sidecar call. |

Sidecar operations (CBOR frames, HMAC signed):

| Opcode | Payload Fields | Response Fields | Notes |
|--------|----------------|-----------------|-------|
| `AuthorizeConstruct` | `frame_id`, `level`, `data_digest` | `grant_id`, `expires_at`, `audit_id` | Stage construction; grant stored server-side. |
| `RedeemGrant` | `grant_id` | `seal`, `audit_id` | One-time use; mark grant consumed. |
| `ComputeSeal` | `frame_id`, `level`, `data_digest` | `seal`, `audit_id` | Reseal existing frame after mutation/uplift. |
| `VerifySeal` | `frame_id`, `level`, `data_digest`, `seal` | `valid`, `audit_id` | Returns `valid=false` when digest or seal mismatch. |
| `Heartbeat` | `nonce` | `nonce`, `timestamp` | Liveness probe used by orchestrator health checks; also refreshes session idle timers. |

### Worker ↔ Orchestrator RPC Schema (msgpack)

```python
# Request (plugin worker → orchestrator)
{"op": "replace_data", "proxy_id": "hex", "data": serialized_df}

# Response (orchestrator → plugin worker)
{"status": "ok", "new_proxy_id": "hex", "audit_id": 12345}
```

All orchestrator responses include the daemon-issued `audit_id`. Separate RPCs exist for `with_uplifted_security_level`, `get_view`, and `verify_clearance`, each returning either a new proxy id or serialized data as appropriate.

Before satisfying any proxy request, the orchestrator materializes the DataFrame into canonical Parquet bytes, computes `data_digest = blake3(canonical_bytes)`, and supplies that digest to the sidecar. The serialized payload returned to the worker remains unchanged; digests never cross process boundaries except between orchestrator and daemon.

### Why Digest Binding Matters

- **Mutable payload, immutable metadata:** Plugins continue to mutate the wrapped `DataFrame` through orchestrator-mediated operations; the digest merely reflects the latest payload when the seal is refreshed, keeping the ADR-002 contract intact.  
- **Prevents wholesale swaps:** An attacker cannot swap in an entirely different `DataFrame` and have the daemon bless it, because the digest embedded in the seal will no longer match the payload.  
- **Orchestrator-only authority:** Only trusted orchestrator code computes the digest and talks to the daemon; untrusted plugin code never sees the digest or secret key, ensuring reseals cannot be forged.  
- **Auditable lineage:** Every proxy mutation appears in the audit stream with its digest fingerprint and `audit_id`, giving security teams visibility into how payloads evolve even though the data itself remains mutable between reseals.

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
   - Proxy mutation contract: modifying a snapshot without `replace_data()` raises `SecurityValidationError`; using `replace_data()` persists changes.
   - Plugin worker attempts direct socket use → connection denied.
   - Replay attack (reuse grant) → fails cleanly.
   - Corrupted HMAC → `SecurityValidationError`.
   - Digest tampering: mutate DataFrame between digest computation and RPC → `VerifySeal` rejects with `SecurityValidationError`.
   - Descriptor inheritance guard: spawn a plugin worker that inspects `/proc/self/fd` for the sidecar socket; test asserts no authenticated descriptors are present and any attempt to send over inherited handles fails.

4. **Performance Benchmarks**
   - Rust `criterion` microbenchmarks (local operations).  
   - Python load test (e.g., `pytest-benchmark`) targeting ≥ 1 k frames/sec.

5. **Security Regression Tests**
   - Ensure `_CONSTRUCTION_TOKEN` / `_SEAL_KEY` never appear in Python heap snapshots.  
   - Validate audit logs hold only metadata (no secrets, no raw IDs).
   - Force digest mismatch (e.g., monkeypatch canonical serializer) → daemon refuses seal/verify.
   - Simulate sidecar outage → orchestrator fails closed.
6. **Canonicalization Determinism & Throughput**
   - Fuzz the Parquet canonicalization pipeline across mixed schemas to confirm identical frames always yield identical digests.
   - Benchmark Arrow/Parquet serialization plus BLAKE3 hashing on wide and tall DataFrames so we know the performance envelope for the ≥ 1 k frames/sec target and can surface hotspots.

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
