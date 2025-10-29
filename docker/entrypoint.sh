#!/bin/bash
set -euo pipefail

# Elspeth Docker Entrypoint
#
# Initializes sidecar daemon environment and starts supervisord.
# Runs as root to create directories and set ownership, then supervisord
# manages processes with correct UIDs.

echo "[entrypoint] Elspeth container starting..."

# Verify users exist
if ! getent passwd sidecar > /dev/null; then
    echo "[entrypoint] ERROR: sidecar user not found" >&2
    exit 1
fi

if ! getent passwd appuser > /dev/null; then
    echo "[entrypoint] ERROR: appuser user not found" >&2
    exit 1
fi

if ! getent passwd appplugin > /dev/null; then
    echo "[entrypoint] ERROR: appplugin user not found" >&2
    exit 1
fi

# Create /run/sidecar/ directory structure
echo "[entrypoint] Creating /run/sidecar/ directory..."
mkdir -p /run/sidecar
chmod 0750 /run/sidecar
chown sidecar:sidecar /run/sidecar

# Check for session key environment variable or generate one
if [ -n "${ELSPETH_SIDECAR_SESSION_KEY:-}" ]; then
    echo "[entrypoint] Using session key from ELSPETH_SIDECAR_SESSION_KEY environment"
    # If environment provides base64, decode it; otherwise assume raw bytes
    if echo -n "$ELSPETH_SIDECAR_SESSION_KEY" | base64 -d > /tmp/session_key_test 2>/dev/null; then
        # Valid base64, decode and write raw bytes
        echo -n "$ELSPETH_SIDECAR_SESSION_KEY" | base64 -d > /run/sidecar/.session
    else
        # Assume raw bytes, write as-is
        echo -n "$ELSPETH_SIDECAR_SESSION_KEY" > /run/sidecar/.session
    fi
    rm -f /tmp/session_key_test
elif [ -f /run/sidecar/.session ]; then
    echo "[entrypoint] Using existing session key at /run/sidecar/.session"
else
    echo "[entrypoint] Generating new session key..."
    # Generate 32-byte (256-bit) session key as RAW BYTES (not base64)
    head -c 32 /dev/urandom > /run/sidecar/.session
fi

# Set session key permissions
# - Owner: sidecar (UID 1001) - daemon reads this
# - Readable by: sidecar, appuser (orchestrator group)
# - Not readable by: appplugin (workers)
chmod 0640 /run/sidecar/.session
chown sidecar:sidecar /run/sidecar/.session

# Add appuser to sidecar group so orchestrator can read session key
if ! groups appuser | grep -q sidecar; then
    echo "[entrypoint] Adding appuser to sidecar group..."
    usermod -aG sidecar appuser
fi

echo "[entrypoint] Permissions configured:"
ls -la /run/sidecar/

# Create log directory for supervisord
mkdir -p /var/log/supervisor
chmod 0755 /var/log/supervisor

# Start supervisord (manages sidecar daemon and orchestrator)
echo "[entrypoint] Starting supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
