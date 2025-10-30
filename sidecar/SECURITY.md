# Sidecar Security Daemon - Security Documentation

## Overview

The Elspeth Sidecar Security Daemon implements **CVE-ADR-002-A-009** mitigation: isolating secrets (construction_token, seal_key) in a separate Rust process to prevent Python introspection attacks.

**Architecture:** OS-enforced process boundary isolation with cryptographic authentication.

**Threat Model:** Protects against malicious plugins accessing secrets through Python's introspection capabilities (`__dict__`, `gc.get_objects()`, debugger hooks).

---

## Security Architecture

### 1. Privilege Separation (3-UID Model)

The system uses three distinct UIDs to enforce OS-level security boundaries:

| UID  | User      | Role                          | Access                     |
|------|-----------|-------------------------------|----------------------------|
| 1001 | `sidecar` | Security daemon               | `/run/sidecar/`, secrets   |
| 1000 | `appuser` | Orchestrator (Python)         | Session key (read-only)    |
| 1002 | `appplugin` | Plugin workers                | **NO** sidecar access      |

**Security Property:** Plugin workers (UID 1002) cannot access the sidecar socket or session key due to Unix file permissions.

### 2. Unix Socket Security

**Socket Path:** `/run/sidecar/auth.sock`
**Permissions:** `0600` (owner-only read/write)
**Authentication:** `SO_PEERCRED` validation + HMAC-SHA256

**Defense in Depth:**
- File permissions prevent unauthorized connection attempts
- `SO_PEERCRED` validates peer UID before processing requests
- HMAC-SHA256 prevents request tampering even if socket is accessible

**File Descriptor Isolation (FD_CLOEXEC):**
- Unix socket file descriptor has `FD_CLOEXEC` flag set
- Prevents inheritance by child processes (plugin workers)
- Verified by `tests/fd_cloexec_test.rs`
- tokio's `UnixListener` sets `SOCK_CLOEXEC` by default (Linux kernel ≥2.6.27)

### 3. Cryptographic Authentication

**Algorithm:** HMAC-SHA256
**Key Material:** 32-byte session key (`/var/lib/sidecar/session.key`, mode `0640`)
**Verification:** Constant-time comparison via `ring::hmac::verify()`

**Replay Protection:** One-shot grant-based capability model (see below) makes traditional timestamp-based replay detection unnecessary.

### 4. Capability-Based Authorization

**Grant Lifecycle:**
1. **Authorize:** Client requests grant → daemon issues 16-byte grant_id + 32-byte construction_ticket (30s TTL)
2. **Redeem:** Client redeems grant_id (one-shot) → daemon returns construction_ticket + seal
3. **Consume:** Client presents construction_ticket before `SecureDataFrame.__new__()` → daemon marks as consumed (one-shot)

**Security Properties:**
- Grants are unforgeable (cryptographically random)
- Grants expire after 30 seconds (prevents long-lived credentials)
- Grants can only be redeemed once (prevents replay)
- Construction tickets can only be consumed once (prevents reuse)
- Construction tickets must have been issued by daemon (prevents forgery - see CVE-ADR-002-A-010)

**Why No Timestamp-Based Replay Protection?**
The grant-based capability model already prevents meaningful replay attacks:
- Each `authorize_construct()` creates a **unique** grant with random grant_id
- Even if an attacker replays the request, they get a **different** grant_id
- The original client's grant is unaffected
- Attack window: 30 seconds (grant TTL)
- Attack impact: Denial of service to one frame creation (low severity)

See ADR-002-C for detailed analysis of authentication architecture decisions.

---

## Configuration Security

### Environment Variables

**Trust Model:** Environment variables are part of the **trusted deployment configuration**.

In containerized deployments (Docker, Kubernetes), environment variables are set by the orchestration platform and inherit the security boundary of the container runtime.

**Environment Variables:**
- `ELSPETH_SIDECAR_SOCKET`: Path to Unix socket (default: `/run/sidecar/auth.sock`)
- `ELSPETH_SIDECAR_SESSION_KEY`: Path to session key file (default: `/var/lib/sidecar/session.key`)
- `ELSPETH_SIDECAR_MODE`: Deployment mode (`standalone` or `sidecar`)

**Security Note:** Untrusted users should **not** have access to modify container environment variables. This is enforced by:
- Container runtime isolation (Docker/Kubernetes RBAC)
- Host OS user permissions (UID namespacing)
- Supervisor process privileges (supervisord runs as root, spawns daemon as UID 1001)

**Industry Precedent:** This follows the [12-factor app methodology](https://12factor.net/config) - configuration via environment variables is standard practice for cloud-native applications.

### File Permissions

**Session Key:** `/var/lib/sidecar/session.key`
- Mode: `0640` (owner read/write, group read, world none)
- Owner: `sidecar:sidecar` (UID 1001, GID 1001)
- Allows: Orchestrator (appuser, same group) can read for HMAC computation
- Denies: Plugin workers (appplugin, different group) cannot access

**Unix Socket:** `/run/sidecar/auth.sock`
- Mode: `0600` (owner-only read/write)
- Owner: `sidecar:sidecar` (UID 1001, GID 1001)
- Allows: Only sidecar daemon can accept connections
- Denies: All other users cannot connect (enforced by OS before SO_PEERCRED check)

**Atomic Creation:** Both files use `O_CREAT | O_EXCL` with atomic permission setting to prevent TOCTOU races.

---

## Operational Security

### Authentication Failure Monitoring

**Metric:** `auth_failures` (AtomicU64 counter)
**Purpose:** Detect misconfigured clients or active attacks

**Monitoring Guidance:**
- **Normal:** 0-2 failures during client startup (race with daemon initialization)
- **Warning:** 5+ failures per minute (potential misconfiguration)
- **Critical:** 50+ failures per minute (potential active attack)

**Response Actions:**
- Check client logs for session key path mismatches
- Verify session key file permissions (`ls -l /var/lib/sidecar/session.key`)
- Inspect daemon logs for UID validation failures
- Consider rotating session key if compromise suspected

### Health Monitoring

**Endpoint:** `HealthCheck` request (no authentication required)
**Returns:** `status`, `uptime_secs`, `requests_served`

**Health Check Script:** `scripts/container_healthcheck.py`
**Container Integration:** Docker HEALTHCHECK directive calls script every 30s

**Fail-Fast Design:** If daemon is unavailable, orchestrator aborts immediately (no graceful degradation to insecure mode).

---

## Threat Mitigations

| Threat | Mitigation | Implementation |
|--------|------------|----------------|
| **Python introspection attacks** | Process boundary isolation | Secrets in Rust process, IPC via Unix socket |
| **Malicious plugin access** | 3-UID privilege separation | Plugin workers (1002) cannot access socket (0600) |
| **Request tampering** | HMAC-SHA256 authentication | Constant-time verification via `ring::hmac::verify()` |
| **Replay attacks** | One-shot grants with TTL | Grant table with 30s expiry, single-use redemption |
| **Ticket forgery** | Issued ticket validation | Dual-map validation (issued + consumed sets) - CVE-ADR-002-A-010 |
| **Timing side-channels** | Constant-time operations | HMAC verification, seal comparison use constant-time algorithms |
| **TOCTOU races** | Atomic file creation | `O_CREAT \| O_EXCL` with immediate permission setting |
| **Information disclosure** | Minimal error messages | Generic errors in production, detailed logs require daemon access |

---

## Vulnerability Disclosure

**CVE-ADR-002-A-010:** Construction Ticket Forgery Vulnerability
**Severity:** Critical (CVSS 8.1)
**Status:** Fixed in commit `f4d5e1d`
**Impact:** Attacker could bypass authorize→redeem flow by forging random tickets
**Fix:** Added issued ticket validation to reject non-daemon-issued tickets

See `docs/architecture/decisions/002-security-architecture.md` for full vulnerability tracking.

---

## Compliance & Auditing

**Audit Logging:** Phase 3 feature (not yet implemented)
**Metrics Collection:** `requests_served`, `auth_failures` (Prometheus-compatible)
**Security Controls:** Mapped to ISM controls in `docs/compliance/CONTROL_INVENTORY.md`

**Australian ISM Alignment:**
- ISM-0380: Access control enforcement (UID separation, socket permissions)
- ISM-1407: Cryptographic key management (session key permissions, rotation capability)
- ISM-1552: Authentication mechanisms (HMAC-SHA256 with constant-time verification)

---

## Development Guidelines

### Adding New Request Types

When adding new operations to the sidecar protocol:

1. **Define CBOR schema** in `protocol.rs`
2. **Implement canonical bytes** in `canonical_bytes_without_auth()`
3. **Add HMAC validation** using `validate_request_auth()`
4. **Update Python client** in `sidecar_client.py`
5. **Add integration tests** in `tests/test_sidecar_integration.py`

**Security Checklist:**
- [ ] Request includes HMAC authentication (except HealthCheck)
- [ ] Canonicalization is deterministic (sort maps, fixed encoding)
- [ ] Handler validates all inputs (lengths, ranges, formats)
- [ ] Errors don't leak sensitive information
- [ ] Constants are not hardcoded (use `config.toml`)

### Testing Security Properties

**Unit Tests:** `sidecar/src/grants.rs` (ticket lifecycle)
**Integration Tests:** `tests/test_sidecar_integration.py` (Python ↔ Rust)
**Negative Tests:** `test_forged_ticket_rejected()`, `test_hmac_validation_fails()`

**Coverage Target:** 80%+ for security-critical modules (grants, crypto, protocol)

---

## References

- **ADR-002:** Multi-Level Security Architecture
- **ADR-002-A-009:** Python Introspection Attack Mitigation
- **ADR-002-A-010:** Construction Ticket Forgery Fix
- **ADR-002-C:** Sidecar Authentication and Authorization Architecture (pending)
- **Implementation Plan:** `docs/development/sidecar_implementation_plan_v3.md`

---

**Last Updated:** 2025-10-30
**Maintainer:** ELSPETH Security Team
**Security Contact:** See `SECURITY.md` in repository root
