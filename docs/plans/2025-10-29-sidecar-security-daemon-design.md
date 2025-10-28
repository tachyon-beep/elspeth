# Sidecar Security Daemon - Design Document

**Date:** 2025-10-29
**Status:** Design Complete - Ready for Implementation
**Author:** Claude Code (with John)
**Related Issues:** #40 (CVE-ADR-002-A-009: Secret Export Vulnerability)
**Related ADRs:** ADR-002, ADR-002-A, ADR-002-B, ADR-003, ADR-004

## Executive Summary

This design addresses CVE-ADR-002-A-009 by moving cryptographic secrets (construction tokens and seal keys) from in-process closure encapsulation to a separate daemon process with OS-enforced process boundary isolation. The sidecar daemon prevents secret extraction via Python introspection while maintaining the existing security model based on Bell-LaPadula Multi-Level Security enforcement.

**Key Security Properties:**
- **Process Boundary Isolation**: Secrets exist only in daemon process, unreachable from main application
- **Fail-Closed by Design**: Missing daemon + missing insecure mode configuration = container abort
- **Hard-Coded Security Ceiling**: OFFICIAL_SENSITIVE maximum in insecure mode (no configuration override)
- **Bilateral Boundary Validation**: Both sender and receiver validate security level at every plugin handoff
- **Zero Security Configuration**: Users configure plugins, system computes security level automatically

## System Architecture

### Container Structure

**Single Container, Multi-Process (Supervisord):**

```
┌─────────────────────────────────────────────────────────────┐
│ Docker Container (python:3.12.12-slim)                      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │ supervisord (PID 1)                                 │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │ sidecar-daemon.py (priority=1)            │      │    │
│  │  │ - Listens on /tmp/elspeth-sidecar.sock   │      │    │
│  │  │ - Loads 256-bit token + seal key         │      │    │
│  │  │ - JSON protocol: get_token, compute_seal │      │    │
│  │  │ - Imports: socket, secrets, hashlib only │      │    │
│  │  │ - Auto-restart: true                      │      │    │
│  │  └──────────────────────────────────────────┘      │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │ boot-validator.py (priority=2)            │      │    │
│  │  │ - Probes /tmp/elspeth-sidecar.sock       │      │    │
│  │  │ - Validates insecure_mode config          │      │    │
│  │  │ - Checks for SECRET+ datasources          │      │    │
│  │  │ - Exit 0 = proceed, Exit 1 = abort        │      │    │
│  │  │ - Auto-restart: false (one-shot)          │      │    │
│  │  └──────────────────────────────────────────┘      │    │
│  │                                                      │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │ elspeth.cli (priority=3)                  │      │    │
│  │  │ - Starts ONLY if boot-validator succeeded│      │    │
│  │  │ - Connects to sidecar via Unix socket    │      │    │
│  │  │ - Falls back to in-process if allowed    │      │    │
│  │  │ - Auto-restart: unexpected                │      │    │
│  │  └──────────────────────────────────────────┘      │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Boot Sequence:**
1. **supervisord starts** → Reads `/etc/supervisor/conf.d/elspeth.conf`
2. **sidecar-daemon.py starts (priority=1)** → 2 second startup grace period
3. **boot-validator.py starts (priority=2)** → Probes socket, validates config
4. **Boot validation success** → main app starts (priority=3)
5. **Boot validation failure** → Exit 1, supervisord aborts container

### Process Isolation & Attack Surface Reduction

**Sidecar Daemon (`scripts/sidecar-daemon.py`):**
- **Zero main codebase dependencies**: Imports ONLY `socket`, `secrets`, `hashlib`, `json`, `sys`
- **Minimal attack surface**: ~150 lines of auditable Python code
- **Independent security review**: Can audit crypto code in complete isolation
- **Dependency isolation**: Main app vulnerabilities cannot affect daemon
- **Blast radius containment**: Compromised main app cannot pivot to daemon secrets

**Why Standalone Script vs. Python Module:**
Following security-by-isolation principle (used in Chromium, OpenBSD):
- ✅ Minimal dependencies = minimal attack surface
- ✅ Independent audit = high-assurance crypto boundary
- ✅ Process boundary = OS-enforced isolation
- ⚠️ Cannot share types (duplicate SecurityLevel enum as strings)
- ⚠️ Harder to unit test (but daemon is simple enough for integration tests)

## IPC Protocol

### Communication Model

**Transport:** Unix domain socket at `/tmp/elspeth-sidecar.sock`
**Permissions:** `0600` (owner-only read/write)
**Format:** Line-delimited JSON (one request per line, one response per line)
**Timeout:** 500ms per operation (fail-fast if daemon hung)

### Protocol Specification

#### Operation 1: Get Construction Token
```json
→ Request:  {"op": "get_token"}
← Response: {"token": "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU2Nzg5"}
            (base64-encoded 32 bytes)
```

#### Operation 2: Compute Seal
```json
→ Request:  {"op": "compute_seal", "data_id": 140235678901234, "level": "SECRET"}
← Response: {"seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6"}
            (base64-encoded HMAC-BLAKE2s, 32 bytes)
```

**Parameters:**
- `data_id`: Python `id(dataframe)` as integer (memory address for identity binding)
- `level`: Security level as string ("UNOFFICIAL", "OFFICIAL", "OFFICIAL_SENSITIVE", "SECRET", "TOP_SECRET")

#### Operation 3: Verify Seal
```json
→ Request:  {"op": "verify_seal", "data_id": 140235678901234, "level": "SECRET",
             "seal": "MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6"}
← Response: {"valid": true}
← Response: {"valid": false}
```

#### Error Response (All Operations)
```json
← Response: {"error": "Invalid operation: unknown_op"}
← Response: {"error": "Missing required field: data_id"}
← Response: {"error": "Invalid security level: INVALID_LEVEL"}
```

### Security Properties

1. **No Authentication Beyond Socket Permissions**: Process isolation sufficient (only container processes can access)
2. **Secrets Never Leave Daemon**: Only computed tokens/seals returned, never raw keys
3. **Input Validation**: Daemon validates `data_id` is integer, `level` is valid enum string
4. **Constant-Time Comparison**: Seal verification uses `secrets.compare_digest()` to prevent timing attacks
5. **Connection Timeout**: 500ms limit prevents hung daemon from blocking main app indefinitely

## Security Model

### Bell-LaPadula Multi-Level Security

**Core Principle:** Data flows only when both sender AND receiver have appropriate clearance.

#### Pipeline Security Level Computation

```python
# At pipeline construction (before data access):
pipeline_min_clearance = MIN(
    datasource.security_level,
    transform1.security_level,
    transform2.security_level,
    sink1.security_level,
    sink2.security_level
)
```

**Datasource operates at `pipeline_min_clearance`:**
```python
datasource.load_data(operating_level=pipeline_min_clearance)
```

#### Trusted Datasource Model

**Datasources are TRUSTED components** responsible for:

1. **Inspecting actual data classification** (metadata, file location, headers)
2. **Refusing to downgrade** (SECRET data requested at OFFICIAL level → ABORT)
3. **Only returning data at or below requested operating level**

**Example:**
```python
# Inside datasource.load_data(operating_level=OFFICIAL):
actual_classification = self._inspect_data_source()  # Reads metadata → SECRET

if actual_classification > operating_level:  # SECRET > OFFICIAL
    raise SecurityValidationError(
        f"Data source contains {actual_classification} data "
        f"but pipeline operating at {operating_level}. "
        f"Cannot downgrade - Bell-LaPadula violation."
    )
```

**Why Datasources Require Signing & Audit:**
Datasources are the enforcement point for classification integrity. This is why they require positive auditing and code signing.

### Bilateral Boundary Validation (Defense-in-Depth)

**Every plugin-to-plugin handoff validates BOTH sides:**

```python
# Sender validation: "Can I send this?"
def datasource.produce_frame() -> SecureDataFrame:
    frame = SecureDataFrame(data, security_level=ACTUAL_LEVEL)

    if frame.security_level > next_component.security_level:
        raise SecurityValidationError(
            f"Cannot send {frame.security_level} data to component "
            f"with only {next_component.security_level} clearance."
        )
    return frame

# Receiver validation: "Can I accept this?"
def transform.accept_frame(frame: SecureDataFrame):
    if frame.security_level > self.security_level:
        raise SecurityValidationError(
            f"Received {frame.security_level} data but I only have "
            f"{self.security_level} clearance. Refusing."
        )
    # Process frame...
```

**Defense Properties:**
- ✅ **Double validation**: Both sender AND receiver independently check
- ✅ **Fail-closed**: Either side can abort entire pipeline
- ✅ **No trust assumptions**: Even if sender compromised, receiver will refuse
- ✅ **Bilateral agreement**: Data flows only when BOTH sides validate correctly

**Example:** Well-formed OFFICIAL sink refuses SECRET data even if compromised datasource tries to force it through.

### Insecure Mode Configuration

**Problem:** Sidecar daemon unavailable (development, testing, environments where process isolation not feasible).

**Solution:** Explicit opt-in with hard-coded security ceiling.

#### Configuration (settings.yaml)

```yaml
security:
  insecure_mode:
    enabled: false  # Default: false (sidecar required)
```

**ONLY configurable setting:** `enabled: true` or `enabled: false`
**NOT configurable:** Maximum security level (hard-coded in code)

#### Hard-Coded Security Ceiling

```python
# In src/elspeth/core/security/secure_data.py
MAX_INSECURE_LEVEL = SecurityLevel.OFFICIAL_SENSITIVE  # Code constant, never configurable

def create_from_datasource(cls, data, security_level):
    if not sidecar_available and insecure_mode_enabled:
        if security_level > MAX_INSECURE_LEVEL:
            raise SecurityValidationError(
                f"Cannot create {security_level.value} frame in insecure mode. "
                f"Maximum allowed: {MAX_INSECURE_LEVEL.value}. "
                f"Start sidecar daemon for classified data (SECRET+)."
            )
        # Fall back to in-process crypto (closure-encapsulated secrets)
```

**Design Rationale:**
- ❌ **Cannot configure max level**: Prevents accidental misconfiguration
- ✅ **Code enforces ceiling**: Security boundary in code, not config
- ✅ **Explicit opt-in only**: User can only say "yes insecure" or "no insecure"
- ✅ **Fail-closed by default**: `enabled: false` means container aborts without sidecar

### Zero Security Configuration Philosophy

**Users configure PLUGINS, not SECURITY:**

```yaml
# ✅ User configures functional behavior:
datasource:
  type: "local_csv"     # Plugin declares security_level in code
  path: "data.csv"

transforms:
  - type: "mock_llm"    # Plugin declares security_level in code

sinks:
  - type: "csv"         # Plugin declares security_level in code
    path: "output.csv"

# ❌ User CANNOT configure security levels directly
# ❌ No "max_classification" or "min_clearance" settings
# ✅ System computes security_level = MIN(all plugin declarations)
```

**Security Computation:**
```python
pipeline_level = MIN(datasource.security_level,
                     transform.security_level,
                     sink.security_level)
# System enforces pipeline_level, never user-configurable
```

**Operators control:**
- ✅ Which plugins to use (plugins declare their security level internally)
- ✅ Whether to allow insecure mode (explicit opt-in)
- ❌ Security levels (computed by system from plugin declarations)
- ❌ Security ceilings (hard-coded: MAX_INSECURE_LEVEL)

## Boot-Time Validation (Fail-Fast)

### Boot Validator (`scripts/boot-validator.py`)

**Purpose:** Verify security preconditions before main application starts.

**Validation Steps:**

```python
# Step 1: Socket existence check
if not os.path.exists("/tmp/elspeth-sidecar.sock"):
    sidecar_available = False
else:
    # Step 2: Socket connectivity check
    try:
        response = socket_request({"op": "get_token"}, timeout=500ms)
        sidecar_available = True
    except (ConnectionError, TimeoutError):
        sidecar_available = False

# Step 3: Configuration validation
settings = load_settings_yaml()
insecure_mode_enabled = settings.get("security", {}).get("insecure_mode", {}).get("enabled", False)

# Step 4: Security mode enforcement
if not sidecar_available and not insecure_mode_enabled:
    print("ERROR: Sidecar daemon unavailable and insecure mode disabled.", file=sys.stderr)
    print("Set security.insecure_mode.enabled=true to proceed at OFFICIAL_SENSITIVE maximum.", file=sys.stderr)
    sys.exit(1)  # Abort container

# Step 5: SECRET+ datasource detection
if insecure_mode_enabled:
    for experiment in settings.get("experiments", []):
        datasource = experiment.get("datasource", {})
        # Check if datasource implies SECRET+ classification
        if datasource_requires_sidecar(datasource):
            print("ERROR: Cannot run SECRET+ datasources in insecure mode.", file=sys.stderr)
            print("Maximum classification: OFFICIAL_SENSITIVE", file=sys.stderr)
            sys.exit(1)  # Abort container

# Step 6: Success - set environment variable for main app
os.environ["SIDECAR_AVAILABLE"] = "true" if sidecar_available else "false"
sys.exit(0)  # Allow main app to start
```

**Failure Modes:**

| Condition | insecure_mode.enabled | Result |
|-----------|----------------------|--------|
| Sidecar available | N/A | ✅ Proceed with sidecar |
| Sidecar unavailable | `false` (default) | ❌ **ABORT** container |
| Sidecar unavailable | `true` | ⚠️ Proceed with in-process crypto (OFFICIAL_SENSITIVE max) |
| Sidecar unavailable + SECRET datasource | `true` | ❌ **ABORT** (ceiling exceeded) |

### Runtime Failure Handling

**Sidecar Crash During Execution:**

```python
# If daemon dies mid-execution, never fall back:
try:
    seal = _sidecar_client.compute_seal(data_id, level)
except (ConnectionError, TimeoutError):
    # Daemon crashed - fail immediately
    raise SecurityValidationError(
        "Sidecar daemon connection lost during operation. "
        "Cannot proceed - cryptographic boundary violated. "
        "Container will restart via supervisord."
    )
```

**Design Principle:** Once execution starts with sidecar, system is committed to using it. Mid-execution fallback would create inconsistent security boundaries.

## Docker Integration

### Dockerfile Modifications

```dockerfile
# ==================== BASE STAGE ====================
FROM python:3.12.12-slim@sha256:... AS base

# Install supervisord for process management
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor=4.2.5-1 \
    && rm -rf /var/lib/apt/lists/*

# Copy sidecar daemon and boot validator
COPY scripts/sidecar-daemon.py /usr/local/bin/sidecar-daemon.py
COPY scripts/boot-validator.py /usr/local/bin/boot-validator.py
RUN chmod +x /usr/local/bin/sidecar-daemon.py \
             /usr/local/bin/boot-validator.py

# Copy supervisord configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/elspeth.conf

# ... existing base stage configuration ...

# ==================== RUNTIME STAGE ====================
FROM base AS runtime
COPY --from=builder-runtime /opt/venv /opt/venv
USER appuser
WORKDIR /workspace

# Start with supervisord (replaces direct python -m elspeth.cli)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

### Supervisord Configuration

**File:** `docker/supervisord.conf`

```ini
[supervisord]
nodaemon=true                    # Run in foreground (Docker requirement)
user=appuser                     # Run as non-root user
logfile=/dev/stdout              # Send logs to Docker stdout
logfile_maxbytes=0               # Disable log rotation (Docker handles this)
pidfile=/tmp/supervisord.pid    # PID file location

# ==================== SIDECAR DAEMON ====================
[program:sidecar-daemon]
command=/usr/local/bin/sidecar-daemon.py
priority=1                       # Start FIRST (before validator)
startsecs=2                      # Wait 2 seconds before considering "started"
autorestart=true                 # Auto-restart if crashes
stdout_logfile=/dev/stdout       # Log to Docker stdout
stdout_logfile_maxbytes=0        # Disable log rotation
stderr_logfile=/dev/stderr       # Errors to Docker stderr
stderr_logfile_maxbytes=0

# ==================== BOOT VALIDATOR ====================
[program:boot-validator]
command=/usr/local/bin/boot-validator.py
priority=2                       # Start SECOND (after daemon, before app)
startsecs=1                      # Quick validation
autorestart=false                # One-shot process (never restart)
exitcodes=0                      # Only exit code 0 is success
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

# ==================== MAIN APPLICATION ====================
[program:elspeth-app]
command=python -m elspeth.cli %(ENV_ELSPETH_CLI_ARGS)s
priority=3                       # Start LAST (only if validator succeeded)
depends_on=boot-validator        # Wait for validator exit code 0
autorestart=unexpected           # Restart on unexpected exit (not normal termination)
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

**Dependency Chain:**
```
supervisord → sidecar-daemon (priority=1, autorestart=true)
           → boot-validator (priority=2, autorestart=false, exitcodes=0)
           → elspeth-app (priority=3, depends_on=boot-validator)
```

## Error Handling & User Experience

### Clear Error Messages

**Scenario 1: Sidecar Unavailable, Insecure Mode Disabled**
```
ERROR: Sidecar daemon unavailable
  → Socket not found: /tmp/elspeth-sidecar.sock
  → Container cannot proceed without sidecar daemon

To run in development/testing mode (OFFICIAL_SENSITIVE maximum):
  Add to settings.yaml:
    security:
      insecure_mode:
        enabled: true

For production/classified data (SECRET+):
  → Ensure sidecar daemon is running
  → Check supervisord logs: docker logs <container>
```

**Scenario 2: SECRET Datasource in Insecure Mode**
```
ERROR: Cannot run SECRET datasources in insecure mode
  → Datasource: experiments/001/datasource (declared SECRET)
  → Maximum classification in insecure mode: OFFICIAL_SENSITIVE
  → Required: Sidecar daemon for SECRET+ data

Actions:
  1. Remove security.insecure_mode.enabled from settings.yaml
  2. Ensure sidecar daemon running (check supervisord logs)
  3. Container will restart with sidecar
```

**Scenario 3: Sidecar Connection Lost Mid-Execution**
```
CRITICAL: Sidecar daemon connection lost
  → Operation: compute_seal(data_id=140235678901234, level=SECRET)
  → Error: Connection refused to /tmp/elspeth-sidecar.sock
  → Time: 2025-10-29 14:23:45.123 UTC

Security boundary violated - aborting immediately.
Container will restart via supervisord.

Check daemon logs:
  docker logs <container> | grep sidecar-daemon
```

### Logging Strategy

**Sidecar Daemon Logs:**
```
[sidecar-daemon] Starting on /tmp/elspeth-sidecar.sock
[sidecar-daemon] Socket created with permissions 0600
[sidecar-daemon] Secrets loaded: token=32 bytes, seal_key=32 bytes
[sidecar-daemon] Ready for connections
[sidecar-daemon] Request: {"op": "get_token"} from PID 1234
[sidecar-daemon] Response: {"token": "YWJj..."} (32 bytes)
```

**Boot Validator Logs:**
```
[boot-validator] Checking sidecar availability...
[boot-validator] Socket found: /tmp/elspeth-sidecar.sock
[boot-validator] Connectivity test: SUCCESS (response in 15ms)
[boot-validator] Configuration: insecure_mode.enabled=false
[boot-validator] Datasource scan: 0 SECRET+ sources found
[boot-validator] Validation PASSED - starting main application
```

**Main App Logs:**
```
[elspeth] Sidecar mode: ENABLED (sidecar available)
[elspeth] Creating SECRET frame: data_id=140235678901234
[elspeth] Requesting seal from sidecar: level=SECRET
[elspeth] Seal received: 32 bytes (response in 0.8ms)
```

## Testing Strategy

### 1. Sidecar Daemon Unit Tests

**File:** `tests/test_sidecar_daemon.py`

```python
def test_socket_creation_and_permissions():
    """Verify socket created with 0600 permissions."""

def test_get_token_returns_32_bytes():
    """Verify token is 256-bit (32 bytes)."""

def test_compute_seal_correctness():
    """Verify seal matches reference HMAC-BLAKE2s implementation."""

def test_verify_seal_constant_time():
    """Verify timing-safe comparison (no timing oracle)."""

def test_invalid_operation_returns_error():
    """Verify {"op": "invalid"} → {"error": "..."}."""

def test_malformed_json_returns_error():
    """Verify non-JSON input handled gracefully."""

def test_missing_required_fields():
    """Verify {"op": "compute_seal"} (no data_id) → error."""
```

### 2. Boot Validator Tests

**File:** `tests/test_boot_validator.py`

```python
def test_validator_succeeds_with_sidecar():
    """Verify exit code 0 when sidecar available."""

def test_validator_fails_without_sidecar_or_insecure():
    """Verify exit code 1 when both missing."""

def test_validator_succeeds_with_insecure_mode():
    """Verify exit code 0 when insecure_mode.enabled=true."""

def test_validator_detects_secret_datasource():
    """Verify exit code 1 if SECRET datasource + insecure mode."""

def test_error_messages_are_clear():
    """Verify stderr contains actionable guidance."""
```

### 3. Integration Tests

**File:** `tests/test_sidecar_integration.py`

```python
def test_end_to_end_frame_creation():
    """Start daemon, create SECRET frame, verify seal."""

def test_insecure_mode_fallback():
    """No sidecar + insecure_mode=true → in-process crypto."""

def test_insecure_mode_ceiling():
    """OFFICIAL_SENSITIVE works, SECRET fails in insecure mode."""

def test_sidecar_crash_detection():
    """Kill daemon mid-execution → SecurityValidationError."""

def test_bilateral_validation():
    """OFFICIAL sink refuses SECRET frame."""
```

### 4. Container Tests

**File:** `tests/docker/test_supervisord.py`

```python
def test_supervisor_starts_all_processes():
    """Verify all three processes start in correct order."""

def test_boot_validator_blocks_main_app():
    """Kill sidecar → validator fails → app never starts."""

def test_sidecar_auto_restart():
    """Kill sidecar → supervisord restarts it."""

def test_main_app_unexpected_restart():
    """Main app crashes → supervisord restarts it."""
```

### Performance Acceptance

**Target:** <1ms overhead per seal operation (IPC + crypto)
**Priority:** Security > Reliability > Performance > Usability

**Acceptable performance characteristics:**
- IPC overhead tolerable if security maintained
- Boot-time validation adds <1 second to container startup
- Socket communication may be slower than in-process (acceptable trade-off)

## Implementation Scope

**Estimated Lines of Code:** ~600 lines total

| Component | Lines | Complexity |
|-----------|-------|------------|
| `scripts/sidecar-daemon.py` | ~150 | Low (socket server + crypto) |
| `scripts/boot-validator.py` | ~100 | Low (validation logic) |
| `secure_data.py` modifications | ~200 | Medium (socket client, fallback) |
| `docker/supervisord.conf` | ~50 | Low (config file) |
| `Dockerfile` changes | ~30 | Low (add supervisor, copy scripts) |
| Tests | ~100+ | Medium (integration tests) |

**Implementation Risk:** Low
- All components are simple, well-understood patterns
- No novel algorithms or complex state management
- Clear separation of concerns (daemon, validator, client, orchestration)

## Security Review Checklist

**For Security Auditor:**

- [ ] **Process Isolation**: Secrets exist only in daemon process ✅
- [ ] **Socket Permissions**: `/tmp/elspeth-sidecar.sock` has 0600 permissions ✅
- [ ] **Fail-Closed Boot**: Missing sidecar + missing insecure mode = abort ✅
- [ ] **Hard-Coded Ceiling**: `MAX_INSECURE_LEVEL` cannot be configured ✅
- [ ] **Bilateral Validation**: Both sender and receiver validate at boundaries ✅
- [ ] **No Trust Assumptions**: Receiver refuses data even if sender compromised ✅
- [ ] **Timing-Safe Comparison**: Seal verification uses `secrets.compare_digest()` ✅
- [ ] **Minimal Attack Surface**: Daemon imports only stdlib crypto primitives ✅
- [ ] **Clear Error Messages**: Guidance for operators without leaking secrets ✅
- [ ] **Audit Trail**: All operations logged (request type, security level, timing) ✅

**Threat Model Coverage:**

| Threat | Mitigation | Status |
|--------|-----------|--------|
| CVE-ADR-002-A-009: Secret export via `_get_construction_token()` | Secrets in daemon process, unreachable from main app | ✅ Resolved |
| Python introspection attacks | Process boundary prevents access to daemon memory | ✅ Resolved |
| Accidental SECRET in insecure mode | Boot validator + hard-coded ceiling | ✅ Resolved |
| Compromised sender bypassing security | Bilateral validation (receiver independently checks) | ✅ Resolved |
| Sidecar crash mid-execution | Immediate abort, no fallback after commitment | ✅ Resolved |
| Configuration errors | Fail-closed default, explicit opt-in required | ✅ Resolved |

## Related Documentation

**Architecture Decision Records:**
- [ADR-002: Security Architecture](../architecture/decisions/002-security-architecture.md) - Bell-LaPadula MLS model
- [ADR-002-A: Trusted Container Model](../architecture/decisions/002a-trusted-container.md) - Datasource-only frame creation
- [ADR-002-B: Immutable Security Levels](../architecture/decisions/002b-immutable-security.md) - No downgrade policy
- [ADR-003: Central Plugin Registry](../architecture/decisions/003-central-plugin-registry.md) - Plugin validation
- [ADR-004: BasePlugin ABC](../architecture/decisions/004-baseplugin-abc.md) - Security level declaration

**Implementation Tracking:**
- [Issue #40: Sidecar Security Daemon](../../issues/40) - Implementation plan, timeline, deployment considerations

**Threat Model:**
- [Security Controls](../architecture/security-controls.md) - Defense-in-depth layers
- [Threat Surface](../architecture/threat-surface.md) - Attack vectors and mitigations

## Design Sign-Off

**Design Status:** ✅ Complete - Ready for Implementation
**Security Review:** Pending (submit to security auditor)
**Implementation Timeline:** Q2 2025 (per Issue #40)
**Breaking Changes:** None (backward compatible with insecure mode)

**Next Steps:**
1. Security auditor review of this design
2. Create implementation worktree: `feature/sidecar-security-daemon`
3. Write detailed implementation plan (task breakdown)
4. Begin implementation following TDD workflow

---

**Design Principle:** *Security > Reliability > Performance > Usability*

**Contact:** Security escalation via `docs/compliance/incident-response.md`
