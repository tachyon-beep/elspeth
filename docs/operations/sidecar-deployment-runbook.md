# Sidecar Security Daemon Deployment Runbook

This runbook covers deployment, configuration, and credential management for the Elspeth sidecar security daemon (Rust process) and the 3-UID separation model.

## Architecture Overview

Elspeth uses **three-process privilege separation** to enforce security boundaries:

```
┌─────────────────────────────────────────────────┐
│  Container                                       │
│  ┌───────────────────────────────────────────┐  │
│  │ Sidecar Daemon                            │  │
│  │ - UID: 1001 (sidecar)                     │  │
│  │ - Owns: /run/sidecar/                     │  │
│  │ - Holds: _SEAL_KEY, _CONSTRUCTION_TOKEN   │  │
│  │ - Socket: /run/sidecar/auth.sock          │  │
│  └───────────────────────────────────────────┘  │
│                    ↑ CBOR + HMAC                 │
│  ┌───────────────────────────────────────────┐  │
│  │ Orchestrator                              │  │
│  │ - UID: 1000 (appuser)                     │  │
│  │ - Can read session key                    │  │
│  │ - Spawns workers via sudo                 │  │
│  └───────────────────────────────────────────┘  │
│                    ↑ msgpack pipes              │
│  ┌───────────────────────────────────────────┐  │
│  │ Plugin Workers (on-demand)                │  │
│  │ - UID: 1002 (appplugin)                   │  │
│  │ - NO /run/sidecar/ access                 │  │
│  │ - NO session key access                   │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## User Setup

### UID Allocation

| User | UID | Purpose | Access |
|------|-----|---------|--------|
| `sidecar` | 1001 | Rust daemon process | Owns `/run/sidecar/`, holds seal keys |
| `appuser` | 1000 | Python orchestrator | Can read session key, spawn workers |
| `appplugin` | 1002 | Plugin workers | NO sidecar access, isolated execution |

### User Creation (Container)

Users are automatically created during Docker build:

```bash
# From Dockerfile
useradd -m -u 1000 -s /bin/bash appuser
useradd -m -u 1001 -s /bin/bash sidecar
useradd -m -u 1002 -s /bin/bash appplugin
```

### Group Membership

- **appuser** is added to the **sidecar** group for session key read access
- **appplugin** has NO group memberships (maximal isolation)

```bash
# Automatically configured in entrypoint.sh
usermod -aG sidecar appuser
```

### Privilege Escalation (Sudo)

The orchestrator (appuser) needs sudo access to spawn workers as appplugin:

```bash
# /etc/sudoers.d/elspeth (installed during Docker build)
appuser ALL=(appplugin) NOPASSWD: /opt/venv/bin/python -m elspeth.orchestrator.worker_process
```

**Security Note:** This is privilege *separation*, not escalation. Workers run with FEWER privileges than the orchestrator.

## Directory Structure

```
/run/sidecar/                     # Runtime directory (tmpfs, destroyed on reboot)
├── .session                      # Session key file (HMAC authentication)
│   ├── Owner: sidecar:sidecar
│   ├── Mode: 0640 (rw-r-----)
│   └── Size: 32 bytes (raw binary, NOT base64)
└── auth.sock                     # Unix socket (created by daemon)
    ├── Owner: sidecar:sidecar
    ├── Mode: 0600 (rw-------)
    └── Enforces: SO_PEERCRED check (UID 1000 only)
```

### Permissions Table

| Path | Owner | Group | Mode | Notes |
|------|-------|-------|------|-------|
| `/run/sidecar/` | sidecar | sidecar | 0750 | Only sidecar can write, sidecar group can list |
| `/run/sidecar/.session` | sidecar | sidecar | 0640 | Daemon owns, appuser reads via group membership |
| `/run/sidecar/auth.sock` | sidecar | sidecar | 0600 | Only daemon can access, enforced by SO_PEERCRED |

## Session Key Management

### Generation

Session keys are generated automatically by `entrypoint.sh` if not provided:

```bash
# Generate 32-byte (256-bit) random session key (raw binary)
head -c 32 /dev/urandom > /run/sidecar/.session
```

**Important:** The session key file contains raw 32-byte binary data, NOT base64-encoded text. The Rust daemon reads exactly 32 bytes.

### External Key Injection

For production deployments, inject the session key via environment variable:

```bash
# Generate key externally (base64-encoded for safe transport)
export ELSPETH_SIDECAR_SESSION_KEY="$(head -c 32 /dev/urandom | base64 -w 0)"

# Pass to container (entrypoint auto-decodes base64 → raw bytes)
docker run -d \
  -e ELSPETH_SIDECAR_SESSION_KEY="$ELSPETH_SIDECAR_SESSION_KEY" \
  elspeth:latest
```

**Note:** The `ELSPETH_SIDECAR_SESSION_KEY` environment variable accepts:
- Base64-encoded strings (auto-decoded to raw bytes by entrypoint)
- Raw binary data (written as-is)

The entrypoint automatically detects the format and ensures `/run/sidecar/.session` contains exactly 32 raw bytes.

### Key Rotation

To rotate the session key:

1. **Generate new key** externally
2. **Stop orchestrator** process (supervisorctl stop orchestrator)
3. **Stop daemon** process (supervisorctl stop sidecar-daemon)
4. **Update key file** or environment variable
5. **Restart daemon** (supervisorctl start sidecar-daemon)
6. **Restart orchestrator** (supervisorctl start orchestrator)

**⚠️ WARNING:** Rotating the session key invalidates all active grants and seals. All in-flight SecureDataFrame instances become invalid.

### Key Security

- **Never log session keys** in plaintext
- **Never commit keys to version control**
- **Rotate keys every 90 days** (recommended)
- **Use external secret management** in production (Vault, AWS Secrets Manager, etc.)

## Deployment

### Docker Deployment

```bash
# Build image
docker build --target runtime -t elspeth:latest .

# Start container
docker run -d \
  --name elspeth \
  -e ELSPETH_SIDECAR_SESSION_KEY="$(head -c 32 /dev/urandom | base64 -w 0)" \
  -e ORCHESTRATOR_ARGS="--settings /workspace/config/suite.yaml" \
  -v /path/to/config:/workspace/config:ro \
  -v /path/to/outputs:/workspace/outputs \
  elspeth:latest

# Check status
docker exec elspeth supervisorctl status

# View logs
docker logs -f elspeth
docker exec elspeth tail -f /var/log/supervisor/sidecar-stderr.log
docker exec elspeth tail -f /var/log/supervisor/orchestrator-stderr.log
```

### Supervisord Management

Supervisord manages both the daemon and orchestrator processes:

```bash
# Check status of all processes
docker exec elspeth supervisorctl status

# Restart daemon
docker exec elspeth supervisorctl restart sidecar-daemon

# Restart orchestrator
docker exec elspeth supervisorctl restart orchestrator

# View full supervisord status
docker exec elspeth supervisorctl
```

### Health Checks

Verify the deployment is healthy:

```bash
# Check users exist with correct UIDs
docker exec elspeth id sidecar
# Expected: uid=1001(sidecar) gid=1001(sidecar) groups=1001(sidecar)

docker exec elspeth id appuser
# Expected: uid=1000(appuser) gid=1000(appuser) groups=1000(appuser),1001(sidecar)

docker exec elspeth id appplugin
# Expected: uid=1002(appplugin) gid=1002(appplugin) groups=1002(appplugin)

# Check /run/sidecar/ permissions
docker exec elspeth ls -la /run/sidecar/
# Expected: drwxr-x--- sidecar sidecar .
#           -rw-r----- sidecar sidecar .session
#           srwx------ sidecar sidecar auth.sock (after daemon starts)

# Check daemon is listening on socket
docker exec elspeth test -S /run/sidecar/auth.sock && echo "Socket exists" || echo "Socket missing"

# Check daemon process is running
docker exec elspeth supervisorctl status sidecar-daemon
# Expected: sidecar-daemon RUNNING pid X, uptime 0:XX:XX
```

## Troubleshooting

### Issue: Daemon fails to start

**Symptoms:**
- `supervisorctl status` shows `sidecar-daemon FATAL`
- `/var/log/supervisor/sidecar-stderr.log` shows errors

**Diagnosis:**

```bash
# Check daemon logs
docker exec elspeth tail -100 /var/log/supervisor/sidecar-stderr.log

# Verify session key exists
docker exec elspeth ls -la /run/sidecar/.session

# Verify sidecar user can read session key
docker exec --user sidecar elspeth cat /run/sidecar/.session
```

**Resolutions:**

1. **Session key missing**: Restart container to regenerate
2. **Permission denied**: Check ownership is `sidecar:sidecar`, mode `0640`
3. **Config file invalid**: Verify `/etc/elspeth/sidecar.toml` syntax

### Issue: Orchestrator can't connect to daemon

**Symptoms:**
- Orchestrator logs show "Connection refused" or "Permission denied"
- `supervisorctl status orchestrator` shows `BACKOFF` or `FATAL`

**Diagnosis:**

```bash
# Check orchestrator logs
docker exec elspeth tail -100 /var/log/supervisor/orchestrator-stderr.log

# Verify socket exists
docker exec elspeth ls -la /run/sidecar/auth.sock

# Check appuser can read session key
docker exec --user appuser elspeth cat /run/sidecar/.session

# Verify appuser is in sidecar group
docker exec elspeth groups appuser | grep sidecar
```

**Resolutions:**

1. **Socket doesn't exist**: Daemon not started, check daemon logs
2. **Permission denied on session key**: appuser not in sidecar group, run `usermod -aG sidecar appuser`
3. **SO_PEERCRED rejection**: Orchestrator running as wrong UID (must be 1000)

### Issue: Workers fail to spawn

**Symptoms:**
- Orchestrator logs show "sudo: command not found" or "Permission denied"
- Plugin transformations fail with worker spawn errors

**Diagnosis:**

```bash
# Verify sudo is installed
docker exec elspeth which sudo

# Check sudoers file exists
docker exec elspeth ls -la /etc/sudoers.d/elspeth

# Test manual worker spawn
docker exec --user appuser elspeth sudo -u appplugin python -m elspeth.orchestrator.worker_process
```

**Resolutions:**

1. **sudo not installed**: Rebuild Docker image (sudo should be in base stage)
2. **sudoers file missing**: Check Dockerfile copied `docker/elspeth-sudoers` correctly
3. **sudoers syntax error**: Verify `/etc/sudoers.d/elspeth` mode is `0440` and syntax is valid

### Issue: Workers can access sidecar resources

**⚠️ SECURITY ISSUE**: Workers should NEVER access `/run/sidecar/` or session key.

**Diagnosis:**

```bash
# Test worker isolation (should fail with permission denied)
docker exec --user appplugin elspeth cat /run/sidecar/.session

# Test worker socket access (should fail)
docker exec --user appplugin elspeth ls -la /run/sidecar/auth.sock
```

**Expected Output:**
```
cat: /run/sidecar/.session: Permission denied
ls: cannot access '/run/sidecar/auth.sock': Permission denied
```

**If workers CAN access these resources:**

1. **Check file permissions**: Session key must be `0640`, NOT `0644`
2. **Check directory permissions**: `/run/sidecar/` must be `0750`, owned by `sidecar:sidecar`
3. **Check user not in sidecar group**: `groups appplugin` should NOT show `sidecar`
4. **CRITICAL**: Report as security vulnerability

## Monitoring and Observability

### Log Locations

| Component | Log Path |
|-----------|----------|
| Supervisord | `/var/log/supervisor/supervisord.log` |
| Sidecar daemon (stdout) | `/var/log/supervisor/sidecar-stdout.log` |
| Sidecar daemon (stderr) | `/var/log/supervisor/sidecar-stderr.log` |
| Orchestrator (stdout) | `/var/log/supervisor/orchestrator-stdout.log` |
| Orchestrator (stderr) | `/var/log/supervisor/orchestrator-stderr.log` |

### Metrics (Future)

The daemon will export Prometheus metrics on port 9090 (disabled by default):

```toml
# /etc/elspeth/sidecar.toml
[performance]
enable_metrics = true
metrics_port = 9090
```

Metrics to monitor:

- `sidecar_grants_issued_total` - Total grants issued
- `sidecar_grants_redeemed_total` - Total grants redeemed
- `sidecar_seals_computed_total` - Total seals computed
- `sidecar_seals_verified_total` - Total seals verified
- `sidecar_request_duration_seconds` - Request latency (histogram)

## Security Hardening

### Container Security

1. **Run as non-root**: Supervisord runs as root but processes run as dedicated users
2. **Read-only root filesystem**: Use `--read-only` with tmpfs mounts for `/run` and `/tmp`
3. **No new privileges**: Use `--security-opt=no-new-privileges`
4. **Drop capabilities**: Use `--cap-drop=ALL`

```bash
docker run -d \
  --name elspeth \
  --read-only \
  --tmpfs /run:rw,noexec,nosuid,size=10m \
  --tmpfs /tmp:rw,noexec,nosuid,size=100m \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  -e ELSPETH_SIDECAR_SESSION_KEY="$KEY" \
  elspeth:latest
```

### Network Isolation

The sidecar daemon does NOT require network access:

```bash
# Run with network disabled
docker run -d --network=none elspeth:latest
```

**Note:** Orchestrator may need network for cloud datasources/sinks. Use least-privilege networking.

### Audit Logging

All daemon operations are logged with structured JSON logging:

```json
{
  "timestamp": "2025-10-30T03:00:00Z",
  "level": "INFO",
  "operation": "compute_seal",
  "frame_id": "550e8400-e29b-41d4-a716-446655440000",
  "level": "OFFICIAL",
  "peer_uid": 1000,
  "duration_ms": 2.5
}
```

Enable trace logging for detailed security audits:

```toml
# /etc/elspeth/sidecar.toml
[daemon]
log_level = "trace"
```

## Credential Rotation Procedures

### Session Key Rotation (Quarterly Recommended)

1. **Schedule maintenance window** (all operations will be interrupted)
2. **Generate new key**:
   ```bash
   NEW_KEY="$(head -c 32 /dev/urandom | base64 -w 0)"
   ```
3. **Stop processes**:
   ```bash
   docker exec elspeth supervisorctl stop orchestrator
   docker exec elspeth supervisorctl stop sidecar-daemon
   ```
4. **Update key**:
   ```bash
   docker exec elspeth bash -c "echo -n '$NEW_KEY' > /run/sidecar/.session"
   ```
5. **Restart processes**:
   ```bash
   docker exec elspeth supervisorctl start sidecar-daemon
   docker exec elspeth supervisorctl start orchestrator
   ```
6. **Verify health checks** (see Health Checks section)

### Seal Key Rotation (Generated on Daemon Start)

The `_SEAL_KEY` is generated automatically by the daemon on startup and stored in memory only (never persisted).

To rotate seal keys:

1. **Stop daemon** (destroys seal key)
2. **Restart daemon** (generates new seal key)

**⚠️ WARNING:** This invalidates ALL existing seals. Only rotate if you suspect seal key compromise.

## Related Documentation

- [Docker Configuration](../../docker/README.md)
- [Sidecar Implementation Plan](../plans/2025-10-29-sidecar-implementation.md)
- [Security Design](../plans/2025-10-29-sidecar-security-daemon-design-v3.md)
- [ADR-002: Multi-Level Security](../architecture/decisions/002-security-architecture.md)

## Emergency Contacts

- **Security Issues**: See [SECURITY.md](../SECURITY.md)
- **Incident Response**: See [Incident Response Plan](../compliance/incident-response.md)
