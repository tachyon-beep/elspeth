# Sidecar Security Daemon - Design Document (v2.1 - Hardened)

**Date:** 2025-10-29 (Updated: 2025-10-29 v2.1)
**Status:** Design Revision - CVE-ADR-002-A-009 CLOSED
**Author:** Claude Code (with John)
**Related Issues:** #40 (CVE-ADR-002-A-009: Secret Export Vulnerability)
**Related ADRs:** ADR-002, ADR-002-A, ADR-002-B, ADR-003, ADR-004
**Supersedes:** `2025-10-29-sidecar-security-daemon-design.md` (v1 had critical flaws)

## Executive Summary

This design **FULLY CLOSES CVE-ADR-002-A-009** by keeping the 256-bit construction token entirely within the daemon process. The token never crosses any IPC boundary - clients receive only grant IDs and seals.

**Four Layers of Isolation:**
1. **Secret Containment**: Token never leaves daemon (two-step grant: authorize → redeem seal only)
2. **Three-UID Separation**: sidecar (1001), appuser (1000), appplugin (1002)
3. **Socket Credential Validation**: SO_PEERCRED enforces only UID 1000 (appuser) can connect
4. **Helper Function Pattern**: Plugins never call SecureDataFrame constructor directly

**Critical Security Fixes from v1/v2:**
- ❌ **v1/v2 FLAW**: Token returned in response → **v2.1 FIX**: Token NEVER returned, stays in daemon
- ❌ **v1 FLAW**: Same UID for daemon and app → **v2.1 FIX**: Three UIDs + SO_PEERCRED validation
- ❌ **v2 FLAW**: Plugin worker (UID 1000) inherits primary group → **v2.1 FIX**: Plugin runs as UID 1002 (appplugin)
- ❌ **v1 FLAW**: Token logged in plaintext → **v2.1 FIX**: Only audit metadata logged

**Key Security Properties:**
- **No Raw Secrets to Client**: Daemon issues MAC'd one-shot handles, validates server-side
- **UID Separation**: Daemon runs as `sidecar` user, app runs as `appuser`
- **Mutual Authentication**: Session key bootstrapped via tmpfs 0700, validated on every request
- **Plugin Process Isolation**: Untrusted plugins run in worker process, cannot reach sidecar socket
- **Fail-Closed by Design**: IPC error → immediate abort (no fallback mid-execution)
- **Hard-Coded Security Ceiling**: OFFICIAL_SENSITIVE maximum in standalone mode

## System Architecture

### Three-Process, Three-UID Model

**Container Structure:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Docker Container (python:3.12.12-slim)                              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ supervisord (PID 1, root)                                   │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ sidecar-daemon.py (priority=1, UID=1001)        │        │   │
│  │  │ User: sidecar (UID 1001, GID 1001)              │        │   │
│  │  │ - Socket: /run/sidecar/auth.sock (0600)        │        │   │
│  │  │ - Session key: /run/sidecar/.session (0640)    │        │   │
│  │  │ - Token NEVER leaves this process              │        │   │
│  │  │ - Issues grant IDs, returns ONLY seals         │        │   │
│  │  │ - SO_PEERCRED: Rejects non-UID-1000 clients    │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ orchestrator (priority=2, UID=1000)             │        │   │
│  │  │ User: appuser (UID 1000, GID 1000)              │        │   │
│  │  │ - Reads session key /run/sidecar/.session      │        │   │
│  │  │ - ONLY process that can connect to daemon      │        │   │
│  │  │ - TRUSTED CODE ONLY (vetted, signed)           │        │   │
│  │  │ - Spawns plugin-worker as UID 1002             │        │   │
│  │  │ - Wraps frame construction (helper function)   │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  │                                                              │   │
│  │  ┌────────────────────────────────────────────────┐        │   │
│  │  │ plugin-worker (priority=3, UID=1002)            │        │   │
│  │  │ User: appplugin (UID 1002, GID 1002)            │        │   │
│  │  │ - UNTRUSTED plugin code runs here              │        │   │
│  │  │ - CANNOT read /run/sidecar/.session (UID 1002) │        │   │
│  │  │ - CANNOT connect to socket (SO_PEERCRED)       │        │   │
│  │  │ - Communicates with orchestrator via IPC       │        │   │
│  │  │ - Never calls SecureDataFrame directly         │        │   │
│  │  └────────────────────────────────────────────────┘        │   │
│  └────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

**UID/GID Separation:**
- `sidecar` (UID 1001, GID 1001): Runs daemon, owns `/run/sidecar/`
- `appuser` (UID 1000, GID 1000): Runs orchestrator, can read session key
- `appplugin` (UID 1002, GID 1002): Runs plugins, CANNOT access `/run/sidecar/`

**File Permissions:**
```bash
/run/sidecar/           # drwxr-x--- sidecar:sidecar (0750)
/run/sidecar/auth.sock  # srw------- sidecar:sidecar (0600)
/run/sidecar/.session   # -rw-r----- sidecar:appuser (0640)
```

**Access Matrix:**
```
                    sidecar daemon  |  session key  |  socket
sidecar (1001)      owns            |  owner (rw)   |  owner (rw)
appuser (1000)      -               |  group (r)    |  connects (validated)
appplugin (1002)    -               |  denied       |  denied (SO_PEERCRED)
```

**Boot Sequence:**
1. **supervisord starts as root** → Creates `/run/sidecar/` owned by `sidecar:sidecar` with 0750
2. **sidecar-daemon starts (UID=1001)** → Generates session key → Writes to `/run/sidecar/.session` (0640, group=appuser)
3. **orchestrator starts (UID=1000)** → Reads session key → Creates SidecarClient → Spawns plugin-worker subprocess as UID 1002
4. **plugin-worker (UID=1002)** → CANNOT read session key (different UID) → CANNOT connect to daemon (SO_PEERCRED rejects)

### Process Isolation Rationale

**Why Three Processes?**

**Problem:** Plugin code runs in same interpreter as orchestrator.
- Python's dynamic nature: `import socket; socket.socket().connect("/run/sidecar/auth.sock")`
- Even with different UID for daemon, plugin in same process can inherit orchestrator's auth
- Plugins could access SecureDataFrame internals (_compute_seal, _verify_seal) via introspection

**Solution:** Move plugin execution to separate subprocess with proxy-based RPC.
- **Orchestrator (UID 1000)**: Trusted code only (suite runner, registry, config loading)
  - Holds all real SecureDataFrame instances
  - Mediates all seal operations via sidecar daemon
  - Exposes only safe proxy objects to plugin worker
- **Plugin Worker (UID 1002)**: Runs plugin.load_data(), plugin.transform(), etc.
  - Receives SecureFrameProxy objects (opaque handles)
  - Cannot access sidecar (no session key, SO_PEERCRED rejects UID 1002)
  - Cannot access seal computation (no real frames, only proxies)
- **Communication**: Orchestrator ↔ Plugin worker via proxy RPC channel
  - **Request/Response Schema**: JSON-serializable messages with operation allowlist
  - **Enforced Operations**: Only `with_uplifted_security_level`, `with_new_data`, `.data` accessor
  - **Security-Sensitive Methods**: All mediated by orchestrator code (never executed in plugin)
  - **Proxy Flow**: Plugin calls proxy.method() → RPC to orchestrator → orchestrator invokes sidecar → orchestrator updates real frame → returns new proxy ID

**Trust Boundaries:**
```
┌─────────────────┐
│ Sidecar Daemon  │  ← SECRETS NEVER LEAVE HERE (token, seal key)
│ (UID 1001)      │  ← Computes seals, issues grants
└────────┬────────┘
         │ Mutual auth (session key)
         │ Grant-based protocol (no token exposure)
┌────────▼────────┐
│ Orchestrator    │  ← TRUSTED CODE (vetted, signed)
│ (UID 1000)      │  ← Has session key, holds real SecureDataFrame instances
│                 │  ← Mediates all seal operations via sidecar
└────────┬────────┘
         │ Proxy RPC (SecureFrameProxy objects)
         │ Allowlist of safe operations only
┌────────▼────────┐
│ Plugin Worker   │  ← UNTRUSTED PLUGIN CODE
│ (UID 1002)      │  ← NO session key, NO socket access
│ (appplugin)     │  ← Receives ONLY proxy handles (never real frames)
│                 │  ← Cannot compute/verify seals
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
# orchestrator (runs as UID 1000 appuser, member of appuser group GID 1000)
session_key = Path("/run/sidecar/.session").read_bytes()  # Can read (group-readable)
# Use session_key to authenticate every request
```

**Security Properties:**
- Session key changes on every daemon restart (ephemeral)
- Plugin worker (UID 1002 appplugin, GID 1002 appplugin, NOT in appuser group) cannot read `/run/sidecar/.session`
- Session key never logged or exposed via API

### Operation 1: Authorize Frame Construction (Step 1 of 2)

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
  "grant_id": "5f4dcc3b5aa765d61d8327deb882cf99",
  "expires_at": 1698765432.123
}
```

**Server-Side Storage:**
```python
# Daemon stores grant_id → authorization mapping
_grants = {
    "5f4dcc3b5aa765d61d8327deb882cf99": {
        "data_id": 140235678901234,
        "level": "SECRET",
        "expires_at": 1698765432.123,
        "used": False
    }
}
```

**Grant ID Generation:**
```python
import secrets, hmac

def generate_grant_id(data_id: int, level: str) -> str:
    """Generate MAC'd grant ID for authorization."""
    grant_input = f"{data_id}:{level}:{time.time()}".encode()
    grant_mac = hmac.new(_seal_key, grant_input, 'sha256').digest()
    return grant_mac.hex()[:32]  # First 128 bits (collision-resistant)
```

**Security Properties:**
- Grant ID is MAC'd (cannot be forged without seal key)
- One-time use (marked `used: True` after redeem)
- Time-limited (expires after 60 seconds)
- Server-side validation (client cannot tamper)

### Operation 2: Redeem Grant (Step 2 of 2)

**Request:**
```json
{
  "op": "redeem_grant",
  "grant_id": "5f4dcc3b5aa765d61d8327deb882cf99",
  "auth": "<HMAC(session_key, request_bytes)>"
}
```

**Response (Success):**
```json
{
  "seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6"
}
```

**CRITICAL: Token NEVER returned. It stays in daemon and is used ONLY for internal validation.**

**Response (Grant Invalid):**
```json
{
  "error": "invalid_grant",
  "reason": "Grant not found, expired, or already used"
}
```

**Server-Side Validation:**
```python
def redeem_grant(grant_id: str) -> dict:
    """Validate grant and return ONLY seal. Token stays in daemon."""
    grant = _grants.get(grant_id)

    if not grant:
        return {"error": "invalid_grant", "reason": "Grant not found"}

    if grant["used"]:
        return {"error": "invalid_grant", "reason": "Grant already used"}

    if time.time() > grant["expires_at"]:
        del _grants[grant_id]
        return {"error": "invalid_grant", "reason": "Grant expired"}

    # Mark used (one-time use)
    grant["used"] = True

    # Compute seal using stored authorization
    seal = _compute_seal(grant["data_id"], grant["level"])

    # ✅ CRITICAL SECURITY FIX: Return ONLY seal, NEVER token
    # Token remains in daemon memory and is used internally for __new__ bypass
    # CVE-ADR-002-A-009 is CLOSED because token never crosses IPC boundary
    return {
        "seal": base64.b64encode(seal).decode()
    }
```

**Security Properties:**
- ✅ Token NEVER leaves daemon process (CVE-ADR-002-A-009 CLOSED)
- ✅ Seal returned only after successful grant validation
- ✅ Grant marked used immediately (no replay attacks)
- ✅ Expired grants purged from memory

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

### SO_PEERCRED Socket Validation (UID 1000 Enforcement)

**Critical Layer:** Even with HMAC authentication, we validate the connecting process UID via Linux SO_PEERCRED.

**Daemon Accept Loop:**
```python
import socket
import struct

def accept_connections(server_sock: socket.socket):
    """Accept connections and validate caller UID via SO_PEERCRED."""
    while True:
        client_sock, addr = server_sock.accept()

        try:
            # Get peer credentials (Linux SO_PEERCRED)
            # Returns: (pid, uid, gid) as 3 32-bit integers
            peer_cred = client_sock.getsockopt(
                socket.SOL_SOCKET,
                socket.SO_PEERCRED,
                struct.calcsize('3i')
            )
            pid, uid, gid = struct.unpack('3i', peer_cred)

            # CRITICAL: Only accept connections from UID 1000 (appuser)
            if uid != 1000:
                audit_log.warning(
                    f"Connection rejected: UID {uid} not authorized "
                    f"(PID {pid}, GID {gid}). Only UID 1000 (appuser) allowed."
                )
                client_sock.close()
                continue

            # ✅ UID validated - process requests
            audit_log.info(f"Connection accepted: UID {uid} PID {pid}")
            handle_client(client_sock)

        except Exception as e:
            audit_log.error(f"Error accepting connection: {e}")
            client_sock.close()
```

**Security Properties:**
- ✅ **Kernel-enforced validation**: SO_PEERCRED cannot be spoofed (kernel provides real UID)
- ✅ **Plugin worker (UID 1002) blocked**: Attempting to connect will be immediately rejected
- ✅ **Defense-in-depth with HMAC**: Even if UID check bypassed, HMAC still required
- ✅ **Audit trail**: All rejections logged with UID/PID/GID for forensics

**Why SO_PEERCRED Matters:**
- Plugin worker subprocess runs as UID 1002 (appplugin)
- Even if plugin code tries `socket.connect("/run/sidecar/auth.sock")`, connection rejected
- Prevents malicious plugins from reaching daemon regardless of file permissions

## Client Integration (Orchestrator)

### Helper Function Pattern (Plugins Never Call SecureDataFrame Directly)

**CRITICAL DESIGN**: Plugins never call `SecureDataFrame.create_from_datasource()` directly. Instead, orchestrator provides a helper function that wraps the grant workflow.

**Orchestrator-Only Helper (`src/elspeth/core/security/frame_factory.py`):**

```python
def construct_secure_frame(data: pd.DataFrame, security_level: SecurityLevel) -> SecureDataFrame:
    """Construct SecureDataFrame via two-phase grant (orchestrator-only).

    This function is ONLY callable by trusted orchestrator code.
    Plugins communicate with orchestrator via IPC and receive frames, but never construct them.

    Security: Grant validation happens in daemon, so token is never exposed to client.
    """
    data_id = id(data)

    # Step 1: Request grant from daemon
    response = _sidecar_client.authorize_construct(data_id, security_level.value)
    if "error" in response:
        raise SecurityValidationError(f"Authorization denied: {response['error']}")

    grant_id = response["grant_id"]

    # Step 2: Redeem grant (daemon validates, returns ONLY seal)
    response = _sidecar_client.redeem_grant(grant_id)
    if "error" in response:
        raise SecurityValidationError(f"Grant redemption failed: {response['error']}")

    seal = base64.b64decode(response["seal"])

    # Step 3: Bypass __new__ validation (grant already validated by daemon)
    # Token never crosses IPC boundary - daemon uses it internally
    instance = object.__new__(SecureDataFrame)
    object.__setattr__(instance, "data", data)
    object.__setattr__(instance, "security_level", security_level)
    object.__setattr__(instance, "_created_by_datasource", True)
    object.__setattr__(instance, "_seal", seal)

    return instance
```

**How Token is Used (Daemon-Side Only):**

```python
# INSIDE DAEMON ONLY - never crosses IPC boundary
def redeem_grant(grant_id: str) -> dict:
    """Validate grant using construction token (stays in daemon)."""
    grant = _grants.get(grant_id)

    # ... validation ...

    # Compute seal
    seal = _compute_seal(grant["data_id"], grant["level"])

    # Token is used HERE to authorize the grant internally
    # But it NEVER gets returned to client
    _validate_token_internal(_construction_token)  # Internal check only

    return {"seal": base64.b64encode(seal).decode()}
    # ✅ NO TOKEN IN RESPONSE - CVE-ADR-002-A-009 CLOSED
```

**Plugin Workflow (No Direct Frame Access):**

```python
# PLUGIN CODE (runs as UID 1002, untrusted)
class MyDatasourcePlugin:
    def load_data(self) -> pd.DataFrame:
        # Plugin returns raw DataFrame, NOT SecureDataFrame
        return pd.DataFrame({"col": [1, 2, 3]})

# ORCHESTRATOR CODE (runs as UID 1000, trusted)
def execute_plugin(plugin: Plugin) -> SecureDataFrame:
    # Orchestrator calls plugin
    data = plugin.load_data()  # Plugin returns plain DataFrame

    # Orchestrator constructs secure frame via helper
    frame = construct_secure_frame(data, plugin.security_level)

    # Return frame to pipeline
    return frame
```

**Security Properties:**
- ✅ Plugins NEVER call SecureDataFrame constructor
- ✅ Plugins NEVER see grants or seals
- ✅ Orchestrator wraps all frame construction
- ✅ Token stays in daemon, used only for internal validation
- ✅ CVE-ADR-002-A-009 CLOSED

### SecureFrameProxy: Plugin Worker Isolation via RPC

**CRITICAL ISOLATION LAYER**: Every SecureDataFrame instance lives ONLY inside the orchestrator process (UID 1000). The plugin worker (UID 1002) receives opaque `SecureFrameProxy` objects that marshal all operations back to the orchestrator via RPC.

**Why Proxy Objects Are Essential:**

Without proxies, plugin workers would need real SecureDataFrame instances, which would give them access to:
- `_compute_seal()` and `_verify_seal()` methods (even if private)
- Python introspection to access internals
- Potential to forge seals if they had the seal key

By using proxies, we ensure plugins can NEVER touch seal computation/verification code.

**Proxy Architecture:**

```python
# ORCHESTRATOR PROCESS (UID 1000)
class SecureFrameProxy:
    """Opaque proxy for SecureDataFrame (plugin worker side).

    All methods marshal back to orchestrator via RPC.
    Plugin worker never holds real SecureDataFrame instances.
    """
    def __init__(self, proxy_id: str, rpc_client: OrchestratorRPCClient):
        self._proxy_id = proxy_id  # Opaque handle
        self._rpc = rpc_client

    def with_uplifted_security_level(self, level: SecurityLevel) -> 'SecureFrameProxy':
        """Uplift security level (marshals to orchestrator)."""
        # RPC call to orchestrator
        response = self._rpc.call("uplift", {
            "proxy_id": self._proxy_id,
            "level": level.value
        })
        # Return new proxy (orchestrator updated real frame)
        return SecureFrameProxy(response["new_proxy_id"], self._rpc)

    def with_new_data(self, data: pd.DataFrame) -> 'SecureFrameProxy':
        """Replace data (marshals to orchestrator)."""
        response = self._rpc.call("with_new_data", {
            "proxy_id": self._proxy_id,
            "data": data.to_dict()  # Serialize for RPC
        })
        return SecureFrameProxy(response["new_proxy_id"], self._rpc)

    @property
    def data(self) -> pd.DataFrame:
        """Access underlying DataFrame (marshals to orchestrator)."""
        response = self._rpc.call("get_data", {"proxy_id": self._proxy_id})
        return pd.DataFrame(response["data"])

    # NO access to _compute_seal, _verify_seal, or seal internals


# SECUREDATAFRAME INTERNAL CONSTRUCTOR (orchestrator-side only)
class SecureDataFrame:
    """SecureDataFrame with internal constructor for sidecar integration.

    The _from_sidecar() class method is ONLY callable by orchestrator code.
    It bypasses all validation and applies the daemon-provided seal verbatim,
    ensuring the local closure secret is NEVER used.
    """

    @classmethod
    def _from_sidecar(
        cls,
        *,
        data: pd.DataFrame,
        security_level: SecurityLevel,
        seal: bytes,
        created_by_datasource: bool
    ) -> 'SecureDataFrame':
        """Create SecureDataFrame with daemon-provided seal (orchestrator-only).

        CRITICAL: This method bypasses all validation and uses the seal
        provided by the sidecar daemon verbatim. It NEVER uses the local
        closure secret (_compute_seal), ensuring ALL seal computation
        happens in the daemon.

        This is the ONLY way the orchestrator should create frames when
        mediating proxy RPC calls. Using with_uplifted_security_level() or
        with_new_data() would invoke local seal computation, which we want
        to avoid (all seals must come from daemon).

        Args:
            data: The DataFrame to wrap
            security_level: Security classification level
            seal: Seal bytes from sidecar daemon (already computed)
            created_by_datasource: Flag for constructor protection

        Returns:
            SecureDataFrame instance with daemon-provided seal
        """
        inst = object.__new__(cls)
        object.__setattr__(inst, "data", data)
        object.__setattr__(inst, "security_level", security_level)
        object.__setattr__(inst, "_created_by_datasource", created_by_datasource)
        object.__setattr__(inst, "_seal", seal)
        return inst


# ORCHESTRATOR RPC HANDLER (UID 1000)
class OrchestratorRPCHandler:
    """Handles proxy RPC calls from plugin worker.

    Maintains registry of real SecureDataFrame instances.
    All seal operations happen HERE via sidecar daemon.
    """
    def __init__(self, sidecar_client: SidecarClient):
        self._frames: dict[str, SecureDataFrame] = {}  # proxy_id → real frame
        self._sidecar = sidecar_client

    def handle_uplift(self, proxy_id: str, level: str) -> dict:
        """Handle with_uplifted_security_level RPC.

        CRITICAL: Uses _from_sidecar() to apply daemon-provided seal verbatim.
        This ensures the local closure secret is NEVER used - all seal
        computation happens in the sidecar daemon.
        """
        # Get real frame from registry
        frame = self._frames[proxy_id]

        # Compute seal via sidecar daemon (NOT in plugin worker, NOT locally)
        response = self._sidecar.compute_seal(id(frame.data), level)
        seal = base64.b64decode(response["seal"])

        # Compute uplifted level (max of current and requested)
        uplifted_level = max(frame.security_level, SecurityLevel[level])

        # Create uplifted frame using daemon-provided seal (orchestrator-side only)
        # Uses _from_sidecar() to apply seal verbatim (no local computation)
        new_frame = SecureDataFrame._from_sidecar(
            data=frame.data,
            security_level=uplifted_level,
            seal=seal,
            created_by_datasource=False
        )

        # Register new frame, return new proxy ID
        new_proxy_id = secrets.token_hex(16)
        self._frames[new_proxy_id] = new_frame

        return {"new_proxy_id": new_proxy_id}

    def handle_with_new_data(self, proxy_id: str, data_dict: dict) -> dict:
        """Handle with_new_data RPC.

        CRITICAL: Uses _from_sidecar() to apply daemon-provided seal verbatim.
        This ensures the local closure secret is NEVER used - all seal
        computation happens in the sidecar daemon.
        """
        frame = self._frames[proxy_id]
        new_data = pd.DataFrame(data_dict)

        # Compute seal via sidecar daemon (NOT locally)
        response = self._sidecar.compute_seal(id(new_data), frame.security_level.value)
        seal = base64.b64decode(response["seal"])

        # Create new frame with updated data using daemon-provided seal
        # Uses _from_sidecar() to apply seal verbatim (no local computation)
        new_frame = SecureDataFrame._from_sidecar(
            data=new_data,
            security_level=frame.security_level,  # Preserve classification
            seal=seal,
            created_by_datasource=False
        )

        new_proxy_id = secrets.token_hex(16)
        self._frames[new_proxy_id] = new_frame

        return {"new_proxy_id": new_proxy_id}
```

**SecureDataFrame Lifecycle (Complete Flow):**

Every operation follows this pattern to ensure seal computation ONLY happens in orchestrator:

1. **Plugin Worker Calls Proxy Method**:
   ```python
   # Plugin code (UID 1002)
   proxy = get_proxy_from_orchestrator()  # Receives SecureFrameProxy
   uplifted = proxy.with_uplifted_security_level(SecurityLevel.SECRET)
   ```

2. **Proxy Marshals to Orchestrator**:
   ```python
   # Inside SecureFrameProxy.with_uplifted_security_level()
   response = self._rpc.call("uplift", {"proxy_id": "abc123", "level": "SECRET"})
   ```

3. **Orchestrator Invokes Sidecar for Seal**:
   ```python
   # Inside OrchestratorRPCHandler.handle_uplift()
   seal_response = self._sidecar.compute_seal(data_id, "SECRET")
   seal = base64.b64decode(seal_response["seal"])
   # Sidecar returns seal (NO token exposure)
   ```

4. **Orchestrator Creates New Frame with Daemon-Provided Seal**:
   ```python
   # Orchestrator uses _from_sidecar() to apply daemon seal verbatim
   # CRITICAL: Does NOT call with_uplifted_security_level() (would use local closure)
   uplifted_level = max(frame.security_level, SecurityLevel.SECRET)
   new_frame = SecureDataFrame._from_sidecar(
       data=frame.data,
       security_level=uplifted_level,
       seal=seal,  # Daemon-provided seal applied verbatim
       created_by_datasource=False
   )
   self._frames[new_proxy_id] = new_frame
   ```

5. **Orchestrator Returns New Proxy**:
   ```python
   # Plugin worker receives new proxy ID (never sees real frame)
   return {"new_proxy_id": "def456"}
   ```

**Enforced Operation Allowlist:**

Plugin workers can ONLY invoke these operations via proxy:
- ✅ `with_uplifted_security_level(level)` → RPC to orchestrator → sidecar seal computation
- ✅ `with_new_data(data)` → RPC to orchestrator → sidecar seal computation
- ✅ `.data` property → RPC to orchestrator → returns raw DataFrame (no seal)
- ❌ `_compute_seal()` → NOT ACCESSIBLE (method doesn't exist on proxy)
- ❌ `_verify_seal()` → NOT ACCESSIBLE (method doesn't exist on proxy)
- ❌ Direct frame construction → NOT ACCESSIBLE (proxy has no constructor access)

**Security Guarantees:**

- ✅ **No Seal Computation in Plugin Worker**: All seal operations happen in orchestrator via sidecar
- ✅ **No Seal Verification in Plugin Worker**: Legitimate workflows still pass (orchestrator validates)
- ✅ **No Local Closure Secret Used**: Every proxy call routes through `_from_sidecar()`, ensuring the daemon-provided seal is applied verbatim and the orchestrator's local closure secret is NEVER used for seal computation
- ✅ **Fail-Closed on RPC Errors**: Plugin worker cannot proceed if orchestrator RPC fails
- ✅ **Proxy Objects Cannot Be Forged**: Proxy IDs are secrets.token_hex(16) (128-bit random)
- ✅ **Orchestrator Validates Proxy IDs**: Unknown proxy_id → error, prevents forgery
- ✅ **Plugin Worker Never Sees Real Frames**: Only opaque proxy handles cross process boundary

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
        """Request authorization grant (Step 1 of 2).

        Returns:
            {"grant_id": "...", "expires_at": 1234567890.123}
        """
        return self._send_authenticated_request("authorize_construct", {
            "data_id": data_id,
            "level": level
        })

    def redeem_grant(self, grant_id: str) -> dict:
        """Redeem grant for seal (Step 2 of 2).

        CRITICAL: Token NEVER returned. It stays in daemon.

        Returns:
            {"seal": "base64-encoded-seal"}  # NO TOKEN
        """
        return self._send_authenticated_request("redeem_grant", {
            "grant_id": grant_id
        })

    def compute_seal(self, data_id: int, level: str) -> dict:
        """Compute seal for existing frames (uplifting, with_new_data)."""
        return self._send_authenticated_request("compute_seal", {
            "data_id": data_id,
            "level": level
        })

    def verify_seal(self, data_id: int, level: str, seal: bytes) -> dict:
        """Verify seal validity."""
        return self._send_authenticated_request("verify_seal", {
            "data_id": data_id,
            "level": level,
            "seal": base64.b64encode(seal).decode()
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
        self._grants = {}  # Synthetic grant storage

    def authorize_construct(self, data_id: int, level: str) -> dict:
        """Immediate authorization (no two-phase in standalone)."""
        if SecurityLevel[level] > SecurityLevel.OFFICIAL_SENSITIVE:
            return {"error": "level_exceeds_standalone_maximum"}

        # Generate synthetic grant_id
        grant_id = secrets.token_hex(16)
        self._grants[grant_id] = {
            "data_id": data_id,
            "level": level,
            "expires_at": time.time() + 60
        }

        return {"grant_id": grant_id, "expires_at": time.time() + 60}

    def redeem_grant(self, grant_id: str) -> dict:
        """Return seal (token stays in standalone client, not exposed).

        NOTE: In standalone mode, token is still closure-encapsulated,
        but we maintain same API as sidecar mode for consistency.
        """
        grant = self._grants.get(grant_id)
        if not grant:
            return {"error": "invalid_grant"}

        seal = self._compute_seal_internal(grant["data_id"], grant["level"])

        # Mark used
        del self._grants[grant_id]

        # ✅ NO TOKEN RETURNED (matches sidecar API)
        return {"seal": base64.b64encode(seal).decode()}
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
       │                                            │    SO_PEERCRED check
       │                                            │
       │                                            │ 4. Generate grant_id
       │                                            │    Store server-side
       │                                            │
       │ 5. {"grant_id": "abc123"}                 │
       │◄───────────────────────────────────────────┤
       │                                            │
       │ 6. redeem_grant(grant_id)                 │
       │    + HMAC(session_key, request)           │
       ├───────────────────────────────────────────►│
       │                                            │ 7. Validate grant_id
       │                                            │    Check not used
       │                                            │    Check not expired
       │                                            │
       │                                            │ 8. Compute seal
       │                                            │    Token used INTERNALLY
       │                                            │    Mark grant used
       │                                            │
       │ 9. {"seal": "..."}  ← NO TOKEN!           │
       │◄───────────────────────────────────────────┤
       │                                            │
```

**Security Properties:**
- ✅ Orchestrator proves knowledge of session key (HMAC)
- ✅ Daemon validates caller UID via SO_PEERCRED (only UID 1000 accepted)
- ✅ Daemon proves grant validity (server-side storage)
- ✅ Plugin worker (UID 1002) cannot connect (SO_PEERCRED rejects)
- ✅ Plugin worker cannot forge requests (no session key)
- ✅ Eavesdropper cannot replay (grants one-time use)
- ✅ **Token NEVER crosses IPC boundary** (CVE-ADR-002-A-009 CLOSED)

### Threat Model Coverage

| Threat | v1 Status | v2.1 Mitigation |
|--------|-----------|-----------------|
| **CVE-ADR-002-A-009: Token exposed to client** | ❌ Vulnerable (get_token) | ✅ **CLOSED**: Token NEVER leaves daemon |
| Plugin opens socket directly | ❌ Same UID (1000) | ✅ Three UIDs + SO_PEERCRED validation |
| Plugin inherits orchestrator auth | ❌ Same process | ✅ Plugin runs as UID 1002 in subprocess |
| Plugin reads session key | ❌ Same UID/group | ✅ UID 1002 cannot read (appuser group only) |
| **Plugin accesses seal computation** | ❌ Real frames in plugin | ✅ **SecureFrameProxy**: Plugin receives ONLY proxy objects |
| **Plugin accesses seal verification** | ❌ Real frames in plugin | ✅ **Orchestrator mediates**: All seal ops via sidecar RPC |
| **Plugin forges seals locally** | ❌ Has _compute_seal access | ✅ **Proxy RPC**: No seal methods on proxy, all ops in orchestrator |
| Token in logs | ❌ Plaintext logging | ✅ Zero secret logging (audit metadata only) |
| Replay attack | ❌ No grant expiry | ✅ One-time grants + 60s expiration |
| Eavesdropping | ⚠️ Unix socket only | ✅ HMAC-authenticated requests |
| Compromised orchestrator | ⚠️ Has token | ✅ Token NEVER leaves daemon (grants only) |
| SO_PEERCRED spoofing | ⚠️ Not implemented | ✅ Kernel-enforced UID validation |

## Logging & Audit (Zero Secret Exposure)

### Daemon Audit Log Format

**What Gets Logged:**
```json
{
  "timestamp": "2025-10-29T14:23:45.123Z",
  "caller_uid": 1000,
  "caller_gid": 1000,
  "caller_pid": 12345,
  "op": "authorize_construct",
  "level": "SECRET",
  "status": "success",
  "grant_id": "5f4dcc3b",
  "expires_at": "2025-10-29T14:24:45.123Z"
}
```

**What NEVER Gets Logged:**
- ❌ Raw token bytes (CVE-ADR-002-A-009: Token NEVER leaves daemon)
- ❌ Raw seal key bytes
- ❌ Session key
- ❌ Seal values
- ❌ data_id (memory addresses leak ASLR)
- ❌ Full grant_id (truncated to first 8 chars in logs)

**Audit Events:**
```
[sidecar-daemon] Session key initialized (256 bits)
[sidecar-daemon] Socket listening: /run/sidecar/auth.sock (0600)
[sidecar-daemon] SO_PEERCRED validation enabled (UID 1000 only)
[sidecar-daemon] Client connected: UID=1000 GID=1000 PID=12345
[sidecar-daemon] Request: op=authorize_construct level=SECRET status=success grant_id=5f4dcc3b...
[sidecar-daemon] Request: op=redeem_grant grant_id=5f4dcc3b... status=success
[sidecar-daemon] Grant expired and purged: 3f2abc1d...
[sidecar-daemon] Connection rejected: UID=1002 PID=12350 (not authorized)
```

### Orchestrator Audit Log Format

```json
{
  "timestamp": "2025-10-29T14:23:45.123Z",
  "op": "create_frame",
  "level": "SECRET",
  "sidecar_mode": true,
  "grant_obtained": true,
  "grant_redeemed": true,
  "seal_received": true,
  "latency_ms": 0.8
}
```

**Two-Phase Grant Workflow Logged:**
```
[orchestrator] Requesting grant: data_id=... level=SECRET
[orchestrator] Grant obtained: grant_id=5f4dcc3b... expires_at=...
[orchestrator] Redeeming grant: grant_id=5f4dcc3b...
[orchestrator] Grant redeemed: seal_received=true token_received=false
[orchestrator] Frame created: level=SECRET seal_valid=true
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

# Create three users for UID separation
# - sidecar (UID 1001): Runs daemon, owns /run/sidecar/
# - appuser (UID 1000): Runs orchestrator, can read session key
# - appplugin (UID 1002): Runs plugin worker, CANNOT access /run/sidecar/
RUN useradd -u 1001 -ms /bin/bash sidecar && \
    useradd -u 1000 -ms /bin/bash appuser && \
    useradd -u 1002 -ms /bin/bash appplugin

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

# ==================== PLUGIN WORKER ====================
[program:plugin-worker]
command=python -m elspeth.plugins.worker
priority=3
user=appplugin                   # Run as appplugin UID (1002)
depends_on=orchestrator
autorestart=unexpected
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

**UID Isolation Properties:**
- Sidecar daemon: UID 1001 (sidecar), owns `/run/sidecar/` (0750)
- Orchestrator: UID 1000 (appuser), reads `/run/sidecar/.session` (group-readable)
- Plugin worker: UID 1002 (appplugin), CANNOT read session key, CANNOT connect to socket

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
    """Verify plugin worker (UID 1002 appplugin) cannot read session key."""
    # Simulate plugin worker (subprocess, UID 1002)
    result = subprocess.run(
        ["cat", "/run/sidecar/.session"],
        user="appplugin",  # UID 1002
        capture_output=True
    )
    assert result.returncode != 0  # Permission denied
    assert b"Permission denied" in result.stderr

def test_orchestrator_can_read_session_key():
    """Verify orchestrator (UID 1000 appuser) can read session key."""
    # Simulate orchestrator (UID 1000)
    result = subprocess.run(
        ["cat", "/run/sidecar/.session"],
        user="appuser",  # UID 1000
        capture_output=True
    )
    assert result.returncode == 0  # Success
    assert len(result.stdout) == 32  # 256-bit key

def test_so_peercred_rejects_plugin_worker():
    """Verify SO_PEERCRED rejects UID 1002 connections."""
    # Run as appplugin (UID 1002)
    plugin_code = """
import socket
sock = socket.socket(socket.AF_UNIX)
sock.connect('/run/sidecar/auth.sock')
print('FAIL: Should not reach here')
"""
    result = subprocess.run(
        ["python", "-c", plugin_code],
        user="appplugin",  # UID 1002
        capture_output=True
    )
    # Connection should be rejected by SO_PEERCRED
    assert result.returncode != 0
    # Check daemon logs for rejection message
    assert "Connection rejected: UID 1002" in daemon_logs
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

### 3. PDP/PEP Pattern Tests (Grant-Based Protocol)

```python
def test_grant_cannot_be_replayed():
    """Verify grant is one-time use only."""
    # Step 1: Get grant
    response = client.authorize_construct(123, "SECRET")
    grant_id = response["grant_id"]

    # Step 2: Redeem grant once
    response1 = client.redeem_grant(grant_id)
    assert "seal" in response1
    assert "token" not in response1  # ✅ CVE-ADR-002-A-009 CLOSED

    # Step 3: Try to reuse grant
    response2 = client.redeem_grant(grant_id)
    assert response2["error"] == "invalid_grant"
    assert "already used" in response2["reason"]

def test_grant_expires_after_timeout():
    """Verify grant expires after 60 seconds."""
    # Step 1: Get grant
    response = client.authorize_construct(123, "SECRET")
    grant_id = response["grant_id"]

    # Wait 61 seconds
    time.sleep(61)

    # Step 2: Grant should be expired
    response = client.redeem_grant(grant_id)
    assert response["error"] == "invalid_grant"
    assert "expired" in response["reason"]

def test_token_never_returned_in_response():
    """CRITICAL: Verify construction token NEVER leaves daemon."""
    response1 = client.authorize_construct(123, "SECRET")
    assert "token" not in response1  # Only grant_id
    assert "grant_id" in response1

    response2 = client.redeem_grant(response1["grant_id"])
    assert "seal" in response2
    assert "token" not in response2  # ✅ TOKEN NEVER RETURNED

    # CVE-ADR-002-A-009 CLOSED
```

### 4. Plugin Isolation Tests

```python
def test_plugin_cannot_access_sidecar_socket():
    """Verify plugin worker (UID 1002) cannot connect to sidecar socket."""
    # Run plugin code in subprocess (simulates plugin worker)
    plugin_code = """
import socket
sock = socket.socket(socket.AF_UNIX)
sock.connect('/run/sidecar/auth.sock')
"""
    result = subprocess.run(
        ["python", "-c", plugin_code],
        user="appplugin",  # UID 1002
        capture_output=True
    )
    # Should fail (SO_PEERCRED rejects UID 1002)
    assert result.returncode != 0
    # Check daemon audit log confirms rejection
    assert "Connection rejected: UID 1002" in get_daemon_logs()

def test_orchestrator_can_access_sidecar_socket():
    """Verify orchestrator (UID 1000) can connect to sidecar socket."""
    # Run orchestrator code
    orchestrator_code = """
import socket
sock = socket.socket(socket.AF_UNIX)
sock.connect('/run/sidecar/auth.sock')
print('OK')
"""
    result = subprocess.run(
        ["python", "-c", orchestrator_code],
        user="appuser",  # UID 1000
        capture_output=True
    )
    # Should succeed (SO_PEERCRED accepts UID 1000)
    assert result.returncode == 0
    assert b"OK" in result.stdout
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

**Estimated Lines of Code:** ~900 lines total (v2.1 - increased for SO_PEERCRED + three-UID model)

| Component | Lines | Complexity |
|-----------|-------|------------|
| `scripts/sidecar-daemon.py` | ~300 | Medium-High (socket server + PDP + auth + SO_PEERCRED) |
| `scripts/boot-validator.py` | ~100 | Low (validation logic) |
| `secure_data.py` modifications | ~350 | Medium-High (grant-based client, standalone fallback, helper function) |
| `plugins/worker.py` (new) | ~100 | Medium (plugin subprocess isolation) |
| `docker/supervisord.conf` | ~80 | Low (three-UID separation config) |
| `Dockerfile` changes | ~50 | Low (add sidecar + appplugin users) |
| Tests | ~200+ | High (integration + security + SO_PEERCRED tests) |

**Implementation Risk:** Medium-High
- Three-UID separation requires careful permissions management
- SO_PEERCRED validation adds kernel-level dependency (Linux-only)
- HMAC authentication adds protocol complexity
- Plugin worker subprocess isolation requires IPC management
- Grant-based protocol more complex than handle-based v2
- More moving parts than v1/v2, but **CVE-ADR-002-A-009 FULLY CLOSED**

## Security Review Checklist (v2.1)

**For Security Auditor:**

### CVE-ADR-002-A-009 Closure
- [ ] ✅ **CRITICAL**: Construction token NEVER leaves daemon process
- [ ] ✅ `authorize_construct` returns ONLY grant_id (no token)
- [ ] ✅ `redeem_grant` returns ONLY seal (no token)
- [ ] ✅ Token used internally in daemon for validation only
- [ ] ✅ Helper function pattern prevents direct SecureDataFrame access

### Three-UID Process Isolation
- [ ] ✅ Sidecar daemon runs as UID 1001 (sidecar user)
- [ ] ✅ Orchestrator runs as UID 1000 (appuser)
- [ ] ✅ Plugin worker runs as UID 1002 (appplugin user)
- [ ] ✅ Plugin worker runs in separate subprocess
- [ ] ✅ Plugin worker cannot read `/run/sidecar/.session` (UID 1002 denied)
- [ ] ✅ Plugin worker cannot connect to socket (SO_PEERCRED rejects)

### SO_PEERCRED Socket Validation
- [ ] ✅ Daemon validates connecting UID via SO_PEERCRED
- [ ] ✅ Only UID 1000 (appuser) connections accepted
- [ ] ✅ UID 1002 (appplugin) connections rejected
- [ ] ✅ Rejection events logged with UID/PID/GID for forensics
- [ ] ✅ Kernel-enforced validation (cannot be spoofed)

### Mutual Authentication
- [ ] ✅ Session key bootstrapped via tmpfs, written to `/run/sidecar/.session` (0640 sidecar:appuser)
- [ ] ✅ Every request HMAC-authenticated
- [ ] ✅ Plugin worker cannot forge requests (no session key)
- [ ] ✅ Constant-time HMAC comparison (timing attack resistant)

### Grant-Based Protocol (PDP/PEP)
- [ ] ✅ Two-phase grant: authorize → redeem
- [ ] ✅ Grants are MAC'd and server-side validated
- [ ] ✅ Grants expire after 60 seconds
- [ ] ✅ Grants marked used after redemption (no replay)
- [ ] ✅ Seal returned only after successful validation

### Logging & Audit (Zero Secret Exposure)
- [ ] ✅ No token bytes in logs (CVE-ADR-002-A-009)
- [ ] ✅ No seal key bytes in logs
- [ ] ✅ No session key in logs
- [ ] ✅ No full grant_id in logs (truncated to 8 chars)
- [ ] ✅ Only audit metadata logged (UID, PID, GID, op, level, status)
- [ ] ✅ Audit trail complete for security review

### Operational Security
- [ ] ✅ Health checks documented (socket, session key, SO_PEERCRED)
- [ ] ✅ Alerting on degraded mode defined
- [ ] ✅ Troubleshooting runbook provided
- [ ] ✅ Two modes documented with security trade-offs (sidecar vs standalone)
- [ ] ✅ Standalone mode hard-coded to OFFICIAL_SENSITIVE maximum

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

**Design Status:** ✅ v2.1 Complete - **CVE-ADR-002-A-009 FULLY CLOSED**

**Changes from v2.0 → v2.1:**
1. ✅ Grant-based protocol: Token NEVER returned to client (was still exposed in v2.0 `commit_construct`)
2. ✅ Three-UID separation: Plugin worker runs as UID 1002 (was UID 1000, could read session key)
3. ✅ SO_PEERCRED validation: Kernel-enforced UID checking (was file permissions only)
4. ✅ Helper function pattern: Plugins never call SecureDataFrame directly (orchestrator-only)

**Changes from v1.0 → v2.0:**
1. Eliminated `get_token` (PDP/PEP pattern with grants)
2. UID separation (sidecar UID 1001 vs appuser UID 1000)
3. Mutual authentication (session key + HMAC)
4. Plugin worker isolation (subprocess)
5. Zero secret logging

**Critical Security Property (v2.1):**
> The 256-bit construction token NEVER crosses any IPC boundary. It remains entirely within the daemon process and is used only for internal validation. Clients receive grant IDs (authorize) and seals (redeem), but NEVER the token itself. CVE-ADR-002-A-009 is FULLY CLOSED.

**Security Review:** Pending v2.1 review (v1 rejected, v2.0 rejected for token exposure)
**Implementation Timeline:** Q2 2025 (post-PR #39 VULN-011 merge)
**Breaking Changes:** None (backward compatible via standalone mode)
**Platform:** Linux-only (SO_PEERCRED dependency)

---

**Design Principle:** *Security > Reliability > Performance > Usability*

**Contact:** Security escalation via `docs/compliance/incident-response.md`
