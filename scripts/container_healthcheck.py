#!/usr/bin/env python3
"""Container health check script for Elspeth.

Checks daemon availability based on security mode:
- standalone: Sidecar not required (always healthy)
- sidecar: Sidecar must be responsive

Exit codes:
- 0: Healthy
- 1: Unhealthy

Usage:
    python scripts/container_healthcheck.py

Environment variables:
    ELSPETH_SIDECAR_MODE: "standalone" or "sidecar" (default: standalone)
    ELSPETH_SIDECAR_SOCKET: Path to daemon socket (default: /run/sidecar/auth.sock)
"""

import os
import socket
import sys
from pathlib import Path

try:
    import cbor2
except ImportError:
    # If cbor2 not available, we're probably in a minimal container
    # In that case, we can't do health checks anyway
    print("WARN: cbor2 not available, assuming healthy", file=sys.stderr)
    sys.exit(0)


def check_daemon_health(socket_path: Path, timeout_secs: float = 2.0) -> bool:
    """Check if daemon is responsive.

    Args:
        socket_path: Path to Unix socket
        timeout_secs: Connection timeout

    Returns:
        True if daemon responds to health check, False otherwise
    """
    if not socket_path.exists():
        return False

    try:
        # Create health check request (no auth required)
        request = {"op": "health_check"}
        request_bytes = cbor2.dumps(request)

        # Connect to daemon
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout_secs)
        sock.connect(str(socket_path))

        # Send request
        sock.sendall(request_bytes)

        # Signal end of request
        sock.shutdown(socket.SHUT_WR)

        # Receive response (read until EOF)
        response_chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_chunks.append(chunk)

        sock.close()

        if not response_chunks:
            return False

        response_bytes = b"".join(response_chunks)

        # Deserialize response
        response = cbor2.loads(response_bytes)

        # Check if daemon reports healthy
        return response.get("status") == "healthy"

    except (socket.timeout, socket.error, OSError, ValueError, KeyError):
        return False
    except Exception as e:
        print(f"WARN: Unexpected error checking daemon: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Run container health check.

    Returns:
        Exit code: 0 for healthy, 1 for unhealthy
    """
    # Detect security mode
    mode = os.environ.get("ELSPETH_SIDECAR_MODE", "standalone").lower()

    # In standalone mode, sidecar is optional
    if mode == "standalone":
        return 0

    # In sidecar mode, daemon must be responsive
    socket_path = Path(os.environ.get("ELSPETH_SIDECAR_SOCKET", "/run/sidecar/auth.sock"))

    if check_daemon_health(socket_path):
        return 0
    else:
        print(f"ERROR: Sidecar daemon not responding at {socket_path}", file=sys.stderr)
        print(
            "Container is in sidecar mode but daemon is unavailable - marking unhealthy",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
