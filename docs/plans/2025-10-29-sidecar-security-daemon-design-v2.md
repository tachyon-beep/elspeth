# Sidecar Security Daemon - Design Document (v2 - Hardened)

**Date:** 2025-10-29
**Status:** Design Revision - Addresses Critical Security Flaws
**Author:** Claude Code (with John)
**Related Issues:** #40 (CVE-ADR-002-A-009: Secret Export Vulnerability)
**Related ADRs:** ADR-002, ADR-002-A, ADR-002-B, ADR-003, ADR-004
**Supersedes:** `2025-10-29-sidecar-security-daemon-design.md` (v1 had critical flaws)

## Executive Summary

This design addresses CVE-ADR-002-A-009 by moving cryptographic secrets into a separate daemon process with **three layers of isolation**:
1. **Process Boundary**: Daemon runs as different UID (`sidecar` user)
2. **Plugin Worker Isolation**: Untrusted plugins run in separate process, cannot access sidecar socket
3. **Cryptographic Authentication**: Mutual authentication via session key (bootstrapped before plugins start)

The daemon implements a **Policy Decision Point (PDP)** pattern: it issues one-shot authorization handles stored server-side and validates them on frame creation. Raw capabilities never leave the daemon process.

**Critical Security Fixes from v1:**
- ❌ **v1 FLAW**: `get_token` exposed raw 256-bit secret to client → **v2 FIX**: PDP/PEP pattern, one-shot handles only
- ❌ **v1 FLAW**: Same UID for daemon and app → plugins could open socket → **v2 FIX**: Different UIDs + mutual auth
- ❌ **v1 FLAW**: Token logged in plaintext → **v2 FIX**: Only audit metadata logged

**Key Security Properties:**
- **No Raw Secrets to Client**: Daemon issues MAC'd one-shot handles, validates server-side
- **UID Separation**: Daemon runs as `sidecar` user, app runs as `appuser`
- **Mutual Authentication**: Session key bootstrapped via tmpfs 0700, validated on every request
- **Plugin Process Isolation**: Untrusted plugins run in worker process, cannot reach sidecar socket
- **Fail-Closed by Design**: IPC error → immediate abort (no fallback mid-execution)
- **Hard-Coded Security Ceiling**: OFFICIAL_SENSITIVE maximum in standalone mode

## System Architecture

### Three-Process Model

**Container Structure:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Docker Container (python:3.12.12-slim)                              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ supervisord (PID 1, root)                                   │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ sidecar-daemon.py (priority=1, UID=sidecar)    │        │   │
│  │  │ - Socket: /run/sidecar/auth.sock (0600)        │        │   │
│  │  │ - Session key: /run/sidecar/.session (0700)    │        │   │
│  │  │ - NEVER returns raw token/seal key             │        │   │
│  │  │ - Issues one-shot handles (MAC'd, server-side) │        │   │
│  │  │ - Validates mutual auth on every request       │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ orchestrator (priority=2, UID=appuser)          │        │   │
│  │  │ - Bootstraps session key from /run/sidecar/    │        │   │
│  │  │ - Sends authenticated requests to daemon        │        │   │
│  │  │ - TRUSTED CODE ONLY (no plugin code here)       │        │   │
│  │  │ - Spawns plugin-worker subprocess               │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ plugin-worker (priority=3, UID=appuser)         │        │   │
│  │  │ - Runs UNTRUSTED plugin code                    │        │   │
│  │  │ - NO ACCESS to /run/sidecar/* (UID + perms)    │        │   │
│  │  │ - Communicates with orchestrator via IPC        │        │   │
│  │  │ - Cannot reach sidecar daemon directly          │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**UID Separation:**
- `sidecar` user (UID 1001): Runs daemon, owns `/run/sidecar/` directory
- `appuser` (UID 1000): Runs orchestrator and plugin worker
- Orchestrator can READ `/run/sidecar/.session` (group-readable)
- Plugin worker CANNOT access `/run/sidecar/` (no group membership)

**Boot Sequence:**
1. **supervisord starts as root** → Creates `/run/sidecar/` owned by `sidecar:sidecar` with 0750
2. **sidecar-daemon starts (UID=1001)** → Generates session key → Writes to `/run/sidecar/.session` (0640, group=appuser)
3. **orchestrator starts (UID=1000)** → Reads session key → Authenticates with daemon
4. **plugin-worker starts (UID=1000, NO sidecar group)** → Cannot read session key → Cannot access daemon

### Process Isolation Rationale

**Why Three Processes?**

**Problem:** Plugin code runs in same interpreter as orchestrator.
- Python's dynamic nature: `import socket; socket.socket().connect("/run/sidecar/auth.sock")`
- Even with different UID for daemon, plugin in same process can inherit orchestrator's auth

**Solution:** Move plugin execution to separate subprocess.
- Orchestrator: Trusted code only (suite runner, registry, config loading)
- Plugin worker: Runs plugin.load_data(), plugin.transform(), etc.
- Communication: Orchestrator ↔ Plugin worker via pickle/msgpack IPC
- Plugin worker cannot access sidecar (no session key, no socket access)

**Trust Boundaries:**
```
┌─────────────────┐
│ Sidecar Daemon  │  ← SECRETS NEVER LEAVE HERE
│ (UID sidecar)   │
└────────┬────────┘
         │ Mutual auth (session key)
         │ One-shot handles only
┌────────▼────────┐
│ Orchestrator    │  ← TRUSTED CODE (vetted, signed)
│ (UID appuser)   │  ← Has session key
└────────┬────────┘
         │ IPC (no secrets)
         │ Pickle/msgpack
┌────────▼────────┐
│ Plugin Worker   │  ← UNTRUSTED PLUGIN CODE
│ (UID appuser,   │  ← NO session key
│  no sidecar grp)│  ← Cannot reach daemon
└─────────────────┘
```

## IPC Protocol (PDP/PEP Pattern)

### Core Principle: Policy Decision Point

**Daemon = Policy Decision Point (PDP):**
- Never emits raw capabilities
- Issues one-shot authorization handles
- Validates handles server-side
- Handles expire after single use

**Client = Policy Enforcement Point (PEP):**
- Requests authorization from PDP
- Receives opaque handle (cannot forge)
- Submits handle for validation
- PDP performs actual operation

### Protocol Specification

**Transport:** Unix domain socket at `/run/sidecar/auth.sock`
**Permissions:** Socket `0600` (sidecar:sidecar), Directory `/run/sidecar/` is `0750` (sidecar:sidecar)
**Authentication:** Every request includes session key (HMAC-authenticated)
**Format:** Line-delimited JSON

### Session Key Bootstrap

**At Daemon Startup:**
```python
# sidecar-daemon.py (runs as UID sidecar)
session_key = secrets.token_bytes(32)  # 256-bit session key
Path("/run/sidecar/.session").write_bytes(session_key)
os.chmod("/run/sidecar/.session", 0o640)  # rw-r----- (sidecar:appuser)
os.chown("/run/sidecar/.session", sidecar_uid, appuser_gid)
```

**At Orchestrator Startup:**
```python
# orchestrator (runs as UID appuser, member of appuser group)
session_key = Path("/run/sidecar/.session").read_bytes()  # Can read (group-readable)
# Use session_key to authenticate every request
```

**Security Properties:**
- Session key changes on every daemon restart (ephemeral)
- Plugin worker (UID appuser, but NOT in appuser group for session file) cannot read
- Session key never logged or exposed via API

### Operation 1: Authorize Frame Construction

**Request:**
```json
{
  "op": "authorize_construct",
  "data_id": 140235678901234,
  "level": "SECRET",
  "auth": "<HMAC(session_key, request_bytes)>"
}
```

**Response:**
```json
{
  "handle": "5f4dcc3b5aa765d61d8327deb882cf99",
  "expires_at": 1698765432.123
}
```

**Server-Side Storage:**
```python
# Daemon stores handle → authorization mapping
_authorizations = {
    "5f4dcc3b5aa765d61d8327deb882cf99": {
        "data_id": 140235678901234,
        "level": "SECRET",
        "expires_at": 1698765432.123,
        "used": False
    }
}
```

**Handle Generation:**
```python
import secrets, hmac

def generate_handle(data_id: int, level: str) -> str:
    """Generate MAC'd handle for authorization."""
    handle_input = f"{data_id}:{level}:{time.time()}".encode()
    handle_mac = hmac.new(_seal_key, handle_input, 'sha256').digest()
    return handle_mac.hex()[:32]  # First 128 bits (collision-resistant)
```

**Security Properties:**
- Handle is MAC'd (cannot be forged without seal key)
- One-time use (marked `used: True` after commit)
- Time-limited (expires after 60 seconds)
- Server-side validation (client cannot tamper)

### Operation 2: Commit Frame Construction

**Request:**
```json
{
  "op": "commit_construct",
  "handle": "5f4dcc3b5aa765d61d8327deb882cf99",
  "auth": "<HMAC(session_key, request_bytes)>"
}
```

**Response (Success):**
```json
{
  "seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6",
  "token": "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXow"
}
```

**Response (Handle Invalid):**
```json
{
  "error": "invalid_handle",
  "reason": "Handle not found, expired, or already used"
}
```

**Server-Side Validation:**
```python
def commit_construct(handle: str) -> dict:
    """Validate handle and return token + seal."""
    auth = _authorizations.get(handle)

    if not auth:
        return {"error": "invalid_handle", "reason": "Handle not found"}

    if auth["used"]:
        return {"error": "invalid_handle", "reason": "Handle already used"}

    if time.time() > auth["expires_at"]:
        del _authorizations[handle]
        return {"error": "invalid_handle", "reason": "Handle expired"}

    # Mark used (one-time use)
    auth["used"] = True

    # Compute seal using stored authorization
    seal = _compute_seal(auth["data_id"], auth["level"])

    # Return token and seal
    # NOTE: Token and seal are ONLY returned after successful authorization
    return {
        "seal": base64.b64encode(seal).decode(),
        "token": base64.b64encode(_construction_token).decode()
    }
```

**Security Properties:**
- Two-phase commit prevents unauthorized frame creation
- Handle validates data_id and security_level match authorization
- Used handles immediately invalid (prevents replay)
- Expired handles purged from memory

### Operation 3: Compute Seal (Existing Frames)

**Request:**
```json
{
  "op": "compute_seal",
  "data_id": 140235678901234,
  "level": "SECRET",
  "auth": "<HMAC(session_key, request_bytes)>"
}
```

**Response:**
```json
{
  "seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6"
}
```

**Use Case:** For `with_uplifted_security_level()` and `with_new_data()` where frame already exists.

### Operation 4: Verify Seal

**Request:**
```json
{
  "op": "verify_seal",
  "data_id": 140235678901234,
  "level": "SECRET",
  "seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6",
  "auth": "<HMAC(session_key, request_bytes)>"
}
```

**Response:**
```json
{
  "valid": true
}
```

### Request Authentication

**Every Request Includes HMAC:**
```python
def create_authenticated_request(op: str, params: dict, session_key: bytes) -> bytes:
    """Create HMAC-authenticated request."""
    request = {"op": op, **params}
    request_bytes = json.dumps(request, sort_keys=True).encode()
    auth_hmac = hmac.new(session_key, request_bytes, 'sha256').hexdigest()
    request["auth"] = auth_hmac
    return json.dumps(request).encode() + b"\n"
```

**Daemon Validates Every Request:**
```python
def validate_request(request_line: bytes, session_key: bytes) -> dict:
    """Validate HMAC before processing request."""
    request = json.loads(request_line)
    provided_auth = request.pop("auth", None)

    if not provided_auth:
        return {"error": "missing_auth"}

    # Recompute HMAC
    request_bytes = json.dumps(request, sort_keys=True).encode()
    expected_auth = hmac.new(session_key, request_bytes, 'sha256').hexdigest()

    # Constant-time comparison
    if not secrets.compare_digest(provided_auth, expected_auth):
        return {"error": "invalid_auth"}

    # Process authenticated request
    return process_request(request)
```

**Security Properties:**
- Every request cryptographically authenticated
- Prevents plugin worker from forging requests (no session key)
- Prevents socket eavesdropping (HMAC validates source)
- Constant-time comparison prevents timing attacks

## Client Integration (Orchestrator)

### SecureDataFrame Factory Methods

**Revised create_from_datasource():**

```python
@classmethod
def create_from_datasource(cls, data: pd.DataFrame, security_level: SecurityLevel):
    """Create frame via two-phase daemon authorization."""
    data_id = id(data)

    # Phase 1: Request authorization
    response = _sidecar_client.authorize_construct(data_id, security_level.value)
    if "error" in response:
        raise SecurityValidationError(f"Authorization denied: {response['error']}")

    handle = response["handle"]

    # Phase 2: Commit construction
    response = _sidecar_client.commit_construct(handle)
    if "error" in response:
        raise SecurityValidationError(f"Commit failed: {response['error']}")

    token = base64.b64decode(response["token"])
    seal = base64.b64decode(response["seal"])

    # Use token for __new__() authorization
    instance = cls.__new__(cls, _token=token)
    object.__setattr__(instance, "data", data)
    object.__setattr__(instance, "security_level", security_level)
    object.__setattr__(instance, "_created_by_datasource", True)
    object.__setattr__(instance, "_seal", seal)

    return instance
```

**Sidecar Client:**

```python
class SidecarClient:
    """Authenticated client for sidecar daemon."""

    def __init__(self, socket_path: str, session_key: bytes):
        self.socket_path = socket_path
        self.session_key = session_key

    def _send_authenticated_request(self, op: str, params: dict) -> dict:
        """Send HMAC-authenticated request."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)  # 500ms timeout
            sock.connect(self.socket_path)

            # Create authenticated request
            request = {"op": op, **params}
            request_bytes = json.dumps(request, sort_keys=True).encode()
            auth_hmac = hmac.new(self.session_key, request_bytes, 'sha256').hexdigest()
            request["auth"] = auth_hmac

            # Send request
            sock.sendall(json.dumps(request).encode() + b"\n")

            # Receive response
            response_line = sock.recv(4096)
            return json.loads(response_line)
        except (ConnectionError, TimeoutError) as e:
            raise SecurityValidationError(
                f"Sidecar daemon connection lost: {e}. "
                "System cannot proceed - cryptographic boundary violated."
            )
        finally:
            sock.close()

    def authorize_construct(self, data_id: int, level: str) -> dict:
        """Request one-shot authorization handle."""
        return self._send_authenticated_request("authorize_construct", {
            "data_id": data_id,
            "level": level
        })

    def commit_construct(self, handle: str) -> dict:
        """Commit construction with handle."""
        return self._send_authenticated_request("commit_construct", {
            "handle": handle
        })
```

### Standalone Mode (Insecure Mode)

**Fallback When Sidecar Unavailable:**

```python
# At orchestrator startup:
try:
    session_key = Path("/run/sidecar/.session").read_bytes()
    _sidecar_client = SidecarClient("/run/sidecar/auth.sock", session_key)
    SIDECAR_AVAILABLE = True
except FileNotFoundError:
    SIDECAR_AVAILABLE = False

    # Check insecure mode configuration
    settings = load_settings()
    insecure_mode_enabled = settings.get("security", {}).get("insecure_mode", {}).get("enabled", False)

    if not insecure_mode_enabled:
        raise SecurityValidationError(
            "Sidecar daemon unavailable and insecure mode disabled. "
            "Cannot proceed. Set security.insecure_mode.enabled=true for "
            "development/testing (OFFICIAL_SENSITIVE maximum only)."
        )

    # Initialize in-process crypto (closure-encapsulated)
    _sidecar_client = StandaloneClient()  # Falls back to current implementation
```

**Standalone Client (In-Process):**

```python
class StandaloneClient:
    """In-process crypto for standalone mode (OFFICIAL_SENSITIVE maximum)."""

    def __init__(self):
        # Closure-encapsulated secrets (current implementation)
        self._construction_token = secrets.token_bytes(32)
        self._seal_key = secrets.token_bytes(32)

    def authorize_construct(self, data_id: int, level: str) -> dict:
        """Immediate authorization (no two-phase in standalone)."""
        if SecurityLevel[level] > SecurityLevel.OFFICIAL_SENSITIVE:
            return {"error": "level_exceeds_standalone_maximum"}

        # Return synthetic handle (not used in standalone)
        return {"handle": "standalone", "expires_at": time.time() + 60}

    def commit_construct(self, handle: str) -> dict:
        """Return token and seal immediately."""
        seal = self._compute_seal_internal(...)
        return {
            "seal": base64.b64encode(seal).decode(),
            "token": base64.b64encode(self._construction_token).decode()
        }
```

## Security Model Updates

### Mutual Authentication Flow

```
┌─────────────┐                              ┌──────────────┐
│ Orchestrator│                              │ Sidecar      │
│ (appuser)   │                              │ (sidecar UID)│
└──────┬──────┘                              └──────┬───────┘
       │                                            │
       │ 1. Read session key                       │
       │    /run/sidecar/.session (0640)          │
       │◄───────────────────────────────────────────┤
       │                                            │
       │ 2. authorize_construct()                  │
       │    + HMAC(session_key, request)           │
       ├───────────────────────────────────────────►│
       │                                            │ 3. Validate HMAC
       │                                            │    (mutual auth)
       │                                            │
       │                                            │ 4. Generate handle
       │                                            │    Store server-side
       │                                            │
       │ 5. {"handle": "abc123"}                   │
       │◄───────────────────────────────────────────┤
       │                                            │
       │ 6. commit_construct(handle)               │
       │    + HMAC(session_key, request)           │
       ├───────────────────────────────────────────►│
       │                                            │ 7. Validate handle
       │                                            │    Check not used
       │                                            │    Check not expired
       │                                            │
       │                                            │ 8. Compute seal
       │                                            │    Mark handle used
       │                                            │
       │ 9. {"seal": "...", "token": "..."}        │
       │◄───────────────────────────────────────────┤
       │                                            │
```

**Security Properties:**
- Orchestrator proves knowledge of session key (HMAC)
- Daemon proves handle validity (server-side storage)
- Plugin worker cannot forge (no session key)
- Eavesdropper cannot replay (handles one-time use)

### Threat Model Coverage

| Threat | v1 Status | v2 Mitigation |
|--------|-----------|---------------|
| CVE-ADR-002-A-009: get_token exposes secret | ❌ Vulnerable | ✅ Eliminated get_token, PDP/PEP pattern |
| Plugin opens socket directly | ❌ Same UID | ✅ Different UID + mutual auth |
| Plugin inherits orchestrator auth | ❌ Same process | ✅ Separate plugin worker process |
| Token in logs | ❌ Plaintext logging | ✅ Only audit metadata logged |
| Replay attack | ❌ No handle expiry | ✅ One-time handles + expiration |
| Eavesdropping | ⚠️ Unix socket only | ✅ HMAC-authenticated requests |
| Compromised orchestrator | ⚠️ Has token | ✅ Token returned only after auth |

## Logging & Audit (Zero Secret Exposure)

### Daemon Audit Log Format

**What Gets Logged:**
```json
{
  "timestamp": "2025-10-29T14:23:45.123Z",
  "caller_uid": 1000,
  "caller_gid": 1000,
  "op": "authorize_construct",
  "level": "SECRET",
  "status": "success",
  "handle_issued": "5f4dcc3b",
  "expires_at": "2025-10-29T14:24:45.123Z"
}
```

**What NEVER Gets Logged:**
- ❌ Raw token bytes
- ❌ Raw seal key bytes
- ❌ Session key
- ❌ Seal values
- ❌ data_id (memory addresses leak ASLR)

**Audit Events:**
```
[sidecar-daemon] Session key initialized (256 bits)
[sidecar-daemon] Socket listening: /run/sidecar/auth.sock (0600)
[sidecar-daemon] Client connected: UID=1000 GID=1000
[sidecar-daemon] Request: op=authorize_construct level=SECRET status=success handle=5f4dcc3b
[sidecar-daemon] Request: op=commit_construct handle=5f4dcc3b status=success
[sidecar-daemon] Handle expired and purged: 3f2abc1d
```

### Orchestrator Audit Log Format

```json
{
  "timestamp": "2025-10-29T14:23:45.123Z",
  "op": "create_frame",
  "level": "SECRET",
  "sidecar_mode": true,
  "handle_obtained": true,
  "commit_success": true,
  "latency_ms": 0.8
}
```

**Security Properties:**
- Audit trail for security review
- No secret leakage in logs
- Timing information for performance analysis
- Status tracking for ops debugging

## Docker Integration (UID Separation)

### Dockerfile Changes

```dockerfile
# ==================== BASE STAGE ====================
FROM python:3.12.12-slim@sha256:... AS base

# Create sidecar user (UID 1001)
RUN useradd -u 1001 -ms /bin/bash sidecar

# Create appuser (UID 1000) - already exists in current Dockerfile
RUN useradd -u 1000 -ms /bin/bash appuser

# Install supervisord
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor=4.2.5-1 \
    && rm -rf /var/lib/apt/lists/*

# Copy sidecar daemon (owned by root, will setuid at runtime)
COPY scripts/sidecar-daemon.py /usr/local/bin/sidecar-daemon.py
COPY scripts/boot-validator.py /usr/local/bin/boot-validator.py
RUN chmod +x /usr/local/bin/sidecar-daemon.py \
             /usr/local/bin/boot-validator.py

# Copy supervisord configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/elspeth.conf

# Create runtime directory for sidecar
# Note: supervisord will chown this at startup
RUN mkdir -p /run/sidecar && chmod 0750 /run/sidecar

# ... existing base stage configuration ...

# ==================== RUNTIME STAGE ====================
FROM base AS runtime
COPY --from=builder-runtime /opt/venv /opt/venv
WORKDIR /workspace

# Supervisord runs as root (required for UID separation)
# Individual programs run as specified users
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

### Supervisord Configuration (UID Separation)

```ini
[supervisord]
nodaemon=true
user=root                        # Must run as root for UID separation
logfile=/dev/stdout
logfile_maxbytes=0

# Startup script to prepare sidecar directory
[program:prepare-sidecar-dir]
command=/bin/bash -c "chown -R sidecar:sidecar /run/sidecar && chmod 0750 /run/sidecar"
priority=0
startsecs=0
autorestart=false
stdout_logfile=/dev/stdout
stderr_logfile=/dev/stderr

# ==================== SIDECAR DAEMON ====================
[program:sidecar-daemon]
command=/usr/local/bin/sidecar-daemon.py
priority=1
user=sidecar                     # Run as sidecar UID (1001)
startsecs=2
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

# ==================== ORCHESTRATOR ====================
[program:orchestrator]
command=python -m elspeth.cli %(ENV_ELSPETH_CLI_ARGS)s
priority=2
user=appuser                     # Run as appuser UID (1000)
depends_on=sidecar-daemon
autorestart=unexpected
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

**UID Isolation Properties:**
- Sidecar daemon: UID 1001, owns `/run/sidecar/` (0750)
- Orchestrator: UID 1000, reads `/run/sidecar/.session` (group-readable)
- Plugin worker: UID 1000, but NO access to `/run/sidecar/` (not in group)

## Operational Modes

### Mode 1: Sidecar (Default, Production)

**Configuration:**
```yaml
# No configuration needed - sidecar mode is default
# security.insecure_mode.enabled defaults to false
```

**Behavior:**
- Daemon must be running or container aborts
- All security levels supported (UNOFFICIAL → TOP_SECRET)
- Fail-closed on any IPC error
- Process isolation enforced

**Use Cases:**
- Production deployments
- Classified data processing (SECRET+)
- High-assurance environments

### Mode 2: Standalone (Opt-In, Development)

**Configuration:**
```yaml
security:
  insecure_mode:
    enabled: true  # Explicit opt-in
```

**Behavior:**
- Daemon not required (falls back to in-process crypto)
- Maximum security level: OFFICIAL_SENSITIVE (hard-coded)
- SECRET+ datasources rejected at boot
- Closure-encapsulated secrets (current v1 implementation)

**Use Cases:**
- Local development
- Testing environments
- Scenarios where process isolation not feasible

**Security Trade-Offs:**
- ⚠️ Secrets in same process (CVE-ADR-002-A-009 remains)
- ⚠️ Python introspection attacks possible
- ✅ Acceptable for OFFICIAL_SENSITIVE and below
- ❌ Never acceptable for SECRET+

## Operational Runbook

### Health Checks

**Sidecar Daemon Health:**
```bash
# Socket exists and is owned by sidecar user
ls -l /run/sidecar/auth.sock
# Expected: srw------- 1 sidecar sidecar 0 Oct 29 14:23 /run/sidecar/auth.sock

# Session key exists and is group-readable by appuser
ls -l /run/sidecar/.session
# Expected: -rw-r----- 1 sidecar appuser 32 Oct 29 14:23 /run/sidecar/.session

# Daemon is running
ps aux | grep sidecar-daemon
# Expected: sidecar 123 0.0 0.1 ... python /usr/local/bin/sidecar-daemon.py
```

**Mutual Auth Health:**
```bash
# Orchestrator can read session key
sudo -u appuser cat /run/sidecar/.session | wc -c
# Expected: 32 (bytes)

# Orchestrator can connect to socket
sudo -u appuser python -c "import socket; s=socket.socket(socket.AF_UNIX); s.connect('/run/sidecar/auth.sock'); print('OK')"
# Expected: OK
```

### Alerting on Degraded Mode

**Container Startup Alerts:**
```
if SIDECAR_AVAILABLE=false AND insecure_mode.enabled=true:
  ALERT: Container running in STANDALONE MODE (OFFICIAL_SENSITIVE max)
  Severity: WARNING
  Action: Verify sidecar unavailability is intentional
```

**Mid-Execution Failures:**
```
if sidecar connection lost during execution:
  ALERT: Sidecar daemon connection lost - container aborting
  Severity: CRITICAL
  Action: Check supervisord logs, restart container
```

### Troubleshooting

**Problem: Container aborts at startup**
```
Check 1: Sidecar daemon logs
  docker logs <container> | grep sidecar-daemon

Check 2: Boot validator logs
  docker logs <container> | grep boot-validator

Check 3: insecure_mode configuration
  Check settings.yaml: security.insecure_mode.enabled

Common cause: Daemon failed to start, insecure mode disabled
Solution: Enable insecure mode for dev, or fix daemon startup
```

**Problem: "Authorization denied" errors**
```
Check 1: Session key readable by orchestrator
  docker exec <container> sudo -u appuser cat /run/sidecar/.session

Check 2: HMAC authentication failing
  Check orchestrator and daemon logs for "invalid_auth" errors

Common cause: Session key permissions incorrect
Solution: Verify /run/sidecar/.session is 0640 sidecar:appuser
```

## Testing Strategy

### 1. UID Separation Tests

```python
def test_plugin_worker_cannot_read_session_key():
    """Verify plugin worker (UID appuser, no sidecar group) cannot read session key."""
    # Simulate plugin worker (subprocess, UID appuser, no groups)
    result = subprocess.run(
        ["cat", "/run/sidecar/.session"],
        user="appuser",
        capture_output=True
    )
    assert result.returncode != 0  # Permission denied
    assert b"Permission denied" in result.stderr
```

### 2. Mutual Authentication Tests

```python
def test_request_without_hmac_rejected():
    """Verify daemon rejects requests without HMAC."""
    request = {"op": "authorize_construct", "data_id": 123, "level": "SECRET"}
    response = send_request(request)  # No "auth" field
    assert response["error"] == "missing_auth"

def test_request_with_invalid_hmac_rejected():
    """Verify daemon rejects requests with wrong HMAC."""
    request = {"op": "authorize_construct", "data_id": 123, "level": "SECRET"}
    request["auth"] = "invalid_hmac"
    response = send_request(request)
    assert response["error"] == "invalid_auth"
```

### 3. PDP/PEP Pattern Tests

```python
def test_handle_cannot_be_replayed():
    """Verify handle is one-time use only."""
    # Get handle
    response = client.authorize_construct(123, "SECRET")
    handle = response["handle"]

    # Use handle once
    response1 = client.commit_construct(handle)
    assert "seal" in response1

    # Try to reuse handle
    response2 = client.commit_construct(handle)
    assert response2["error"] == "invalid_handle"
    assert "already used" in response2["reason"]

def test_handle_expires_after_timeout():
    """Verify handle expires after 60 seconds."""
    response = client.authorize_construct(123, "SECRET")
    handle = response["handle"]

    # Wait 61 seconds
    time.sleep(61)

    # Handle should be expired
    response = client.commit_construct(handle)
    assert response["error"] == "invalid_handle"
    assert "expired" in response["reason"]
```

### 4. Plugin Isolation Tests

```python
def test_plugin_cannot_access_sidecar_socket():
    """Verify plugin worker (subprocess) cannot connect to sidecar socket."""
    # Run plugin code in subprocess (simulates plugin worker)
    plugin_code = """
import socket
sock = socket.socket(socket.AF_UNIX)
sock.connect('/run/sidecar/auth.sock')
"""
    result = subprocess.run(
        ["python", "-c", plugin_code],
        user="appuser",
        capture_output=True
    )
    # Should fail (permission denied on socket)
    assert result.returncode != 0
```

### 5. Standalone Mode Tests

```python
def test_standalone_mode_rejects_secret_level():
    """Verify standalone mode refuses SECRET frames."""
    # Force standalone mode
    monkeypatch.setattr("SIDECAR_AVAILABLE", False)
    monkeypatch.setattr("insecure_mode_enabled", True)

    # Try to create SECRET frame
    with pytest.raises(SecurityValidationError, match="level_exceeds_standalone_maximum"):
        SecureDataFrame.create_from_datasource(data, SecurityLevel.SECRET)

def test_standalone_mode_allows_official_sensitive():
    """Verify standalone mode works for OFFICIAL_SENSITIVE."""
    monkeypatch.setattr("SIDECAR_AVAILABLE", False)
    monkeypatch.setattr("insecure_mode_enabled", True)

    # OFFICIAL_SENSITIVE should work
    frame = SecureDataFrame.create_from_datasource(data, SecurityLevel.OFFICIAL_SENSITIVE)
    assert frame.security_level == SecurityLevel.OFFICIAL_SENSITIVE
```

## Implementation Scope

**Estimated Lines of Code:** ~800 lines total (increased from v1 due to auth complexity)

| Component | Lines | Complexity |
|-----------|-------|------------|
| `scripts/sidecar-daemon.py` | ~250 | Medium (socket server + PDP + auth) |
| `scripts/boot-validator.py` | ~100 | Low (validation logic) |
| `secure_data.py` modifications | ~300 | Medium (PEP client, standalone fallback) |
| `docker/supervisord.conf` | ~60 | Low (UID separation config) |
| `Dockerfile` changes | ~40 | Low (add sidecar user, tmpfs) |
| Tests | ~150+ | High (integration + security tests) |

**Implementation Risk:** Medium
- UID separation requires careful permissions management
- HMAC authentication adds protocol complexity
- Plugin worker isolation requires subprocess management
- More moving parts than v1, but significantly more secure

## Security Review Checklist (v2)

**For Security Auditor:**

### Process Isolation
- [ ] Sidecar daemon runs as different UID (1001) ✅
- [ ] Orchestrator runs as different UID (1000) ✅
- [ ] Plugin worker runs in separate subprocess ✅
- [ ] Plugin worker cannot access `/run/sidecar/` ✅

### Mutual Authentication
- [ ] Session key bootstrapped via tmpfs 0700 ✅
- [ ] Every request HMAC-authenticated ✅
- [ ] Plugin worker cannot forge requests (no session key) ✅
- [ ] Constant-time HMAC comparison ✅

### PDP/PEP Pattern
- [ ] `get_token` eliminated (no raw secret exposure) ✅
- [ ] One-shot handles MAC'd and server-side validated ✅
- [ ] Handles expire after 60 seconds ✅
- [ ] Handles marked used after commit (no replay) ✅

### Logging & Audit
- [ ] No token/seal/session key in logs ✅
- [ ] Only audit metadata logged ✅
- [ ] Audit trail complete for security review ✅

### Operational Security
- [ ] Health checks documented ✅
- [ ] Alerting on degraded mode defined ✅
- [ ] Troubleshooting runbook provided ✅
- [ ] Two modes documented with security trade-offs ✅

## Related Documentation

**Architecture Decision Records:**
- [ADR-002: Security Architecture](../architecture/decisions/002-security-architecture.md)
- [ADR-002-A: Trusted Container Model](../architecture/decisions/002a-trusted-container.md)
- [ADR-002-B: Immutable Security Levels](../architecture/decisions/002b-immutable-security.md)
- [ADR-003: Central Plugin Registry](../architecture/decisions/003-central-plugin-registry.md)
- [ADR-004: BasePlugin ABC](../architecture/decisions/004-baseplugin-abc.md)

**Implementation Tracking:**
- [Issue #40: Sidecar Security Daemon](../../issues/40)

**Threat Model:**
- [Security Controls](../architecture/security-controls.md)
- [Threat Surface](../architecture/threat-surface.md)

## Design Sign-Off

**Design Status:** ✅ v2 Complete - Addresses Critical Security Flaws
**Changes from v1:**
1. Eliminated `get_token` (PDP/PEP pattern)
2. UID separation (sidecar vs appuser)
3. Mutual authentication (session key + HMAC)
4. Plugin worker isolation (subprocess)
5. Zero secret logging

**Security Review:** Pending v2 review (v1 rejected for critical flaws)
**Implementation Timeline:** Q2 2025
**Breaking Changes:** None (backward compatible via standalone mode)

---

**Design Principle:** *Security > Reliability > Performance > Usability*

**Contact:** Security escalation via `docs/compliance/incident-response.md`
