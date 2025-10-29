# Elspeth Docker Configuration

This directory contains Docker deployment configuration for the Elspeth security platform.

## Architecture Overview

Elspeth uses a **3-UID separation model** to enforce security boundaries between components:

```
┌─────────────────────────────────────────────────┐
│  Container (supervisord manages processes)      │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │ Sidecar Daemon (UID 1001: sidecar)       │  │
│  │ - Rust process                            │  │
│  │ - Owns /run/sidecar/ directory            │  │
│  │ - Holds _SEAL_KEY and _CONSTRUCTION_TOKEN │  │
│  │ - Unix socket: /run/sidecar/auth.sock     │  │
│  └──────────────────────────────────────────┘  │
│                    ↑ CBOR protocol               │
│                    │ (HMAC-authenticated)        │
│  ┌──────────────────────────────────────────┐  │
│  │ Orchestrator (UID 1000: appuser)         │  │
│  │ - Python process                          │  │
│  │ - Can read session key                    │  │
│  │ - Spawns plugin workers via sudo          │  │
│  │ - Manages SecureDataFrame instances       │  │
│  └──────────────────────────────────────────┘  │
│                    ↑ msgpack protocol            │
│                    │ (stdin/stdout pipes)        │
│  ┌──────────────────────────────────────────┐  │
│  │ Plugin Workers (UID 1002: appplugin)     │  │
│  │ - Python subprocess (on-demand)           │  │
│  │ - NO access to /run/sidecar/              │  │
│  │ - NO session key access                   │  │
│  │ - Receives only opaque proxy handles      │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Security Properties

1. **Privilege Separation**: Three distinct UIDs enforce OS-level access control
2. **Secret Isolation**: Workers cannot read `/run/sidecar/.session` (permission denied)
3. **Socket Protection**: Daemon enforces SO_PEERCRED checks (only UID 1000 allowed)
4. **FD_CLOEXEC**: Workers spawned with no inherited file descriptors
5. **Environment Sanitization**: SIDECAR_SESSION_KEY removed from worker environment

## Files

### `supervisord.conf`

Manages the sidecar daemon and orchestrator processes:

- **sidecar-daemon** (UID 1001, priority 10): Starts first
- **orchestrator** (UID 1000, priority 20): Starts after daemon is ready
- **Plugin workers**: Spawned on-demand by orchestrator (not managed by supervisord)

### `elspeth-sudoers`

Sudoers configuration allowing orchestrator (appuser) to spawn workers as appplugin without password.

**Install location**: `/etc/sudoers.d/elspeth`
**Permissions**: `0440` (read-only, owned by root)

### `entrypoint.sh`

Container initialization script that:

1. Creates `/run/sidecar/` directory structure
2. Generates or loads session key from environment
3. Sets correct ownership and permissions
4. Adds appuser to sidecar group (for session key read access)
5. Starts supervisord

### `sidecar.toml.example`

Sample configuration for the Rust sidecar daemon. Copy to `/etc/elspeth/sidecar.toml` and customize as needed.

## Building the Image

```bash
# Build runtime image
docker build --target runtime -t elspeth:latest .

# Build dev image (includes test dependencies)
docker build --target dev -t elspeth:dev .
```

## Running the Container

### Production Mode (Multi-Process)

```bash
# Start container with default entrypoint (supervisord)
docker run -d \
  --name elspeth \
  -e ELSPETH_SIDECAR_SESSION_KEY="$(head -c 32 /dev/urandom | base64 -w 0)" \
  -e ORCHESTRATOR_ARGS="--settings /workspace/config/suite.yaml" \
  elspeth:latest

# Note: Session key can be provided as base64 (auto-decoded by entrypoint)
# or as raw bytes. The daemon expects raw 32-byte binary format.

# View logs
docker logs -f elspeth

# Check process status
docker exec elspeth supervisorctl status
```

### Development Mode (Direct Python)

```bash
# Override entrypoint for direct testing
docker run --rm -it \
  --entrypoint python \
  elspeth:dev \
  -m pytest tests/orchestrator/test_runtime.py -v
```

### Interactive Shell

```bash
# Open shell as appuser
docker run --rm -it \
  --entrypoint /bin/bash \
  elspeth:dev

# Open shell as root (for debugging)
docker run --rm -it \
  --user root \
  --entrypoint /bin/bash \
  elspeth:dev
```

## Testing UID Separation

```bash
# Verify users exist with correct UIDs
docker run --rm elspeth:latest id sidecar
# uid=1001(sidecar) gid=1001(sidecar) groups=1001(sidecar)

docker run --rm elspeth:latest id appuser
# uid=1000(appuser) gid=1000(appuser) groups=1000(appuser),1001(sidecar)

docker run --rm elspeth:latest id appplugin
# uid=1002(appplugin) gid=1002(appplugin) groups=1002(appplugin)

# Verify /run/sidecar/ permissions (after entrypoint runs)
docker run --rm elspeth:latest ls -la /run/sidecar/
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ELSPETH_SIDECAR_SESSION_KEY` | Session key for HMAC authentication (base64) | Generated if not provided |
| `ORCHESTRATOR_ARGS` | Arguments passed to `python -m elspeth.cli` | `""` (none) |
| `RUST_LOG` | Rust logging level (sidecar daemon) | `info` |

## Security Considerations

1. **Session Key Rotation**: Generate new session key for each deployment
2. **Credential Isolation**: Never mount cloud credentials into `/run/sidecar/`
3. **File Permissions**: Verify `/run/sidecar/.session` is `0640` owned by `sidecar:sidecar`
4. **Worker Spawning**: Orchestrator must use `sudo -u appplugin` for privilege separation
5. **SO_PEERCRED**: Daemon enforces peer credential checks on Unix socket

## Troubleshooting

### Supervisord won't start

- Check `/var/log/supervisor/supervisord.log`
- Verify entrypoint.sh created `/run/sidecar/` correctly

### Sidecar daemon fails to start

- Check `/var/log/supervisor/sidecar-stderr.log`
- Verify session key exists and has correct permissions
- Ensure `/etc/elspeth/sidecar.toml` is valid TOML

### Orchestrator can't connect to daemon

- Verify sidecar daemon is running: `supervisorctl status sidecar-daemon`
- Check socket exists: `ls -la /run/sidecar/auth.sock`
- Verify appuser is in sidecar group: `groups appuser`

### Workers can't spawn

- Check sudo permissions: `sudo -u appplugin -l`
- Verify `/etc/sudoers.d/elspeth` exists with mode `0440`
- Test manual spawn: `sudo -u appplugin python -m elspeth.orchestrator.worker_process`

## Development Workflow

1. **Build dev image**: `docker build --target dev -t elspeth:dev .`
2. **Run tests**: `docker run --rm elspeth:dev pytest -v`
3. **Test worker isolation**: `docker run --rm elspeth:dev pytest tests/integration/test_worker_isolation.py -v`
4. **Test multi-process**: Build runtime image and start with supervisord

## Related Documentation

- [Implementation Plan](../docs/plans/2025-10-29-sidecar-implementation.md)
- [Security Design](../docs/plans/2025-10-29-sidecar-security-daemon-design-v3.md)
- [ADR-002: Multi-Level Security](../docs/architecture/decisions/002-security-architecture.md)
