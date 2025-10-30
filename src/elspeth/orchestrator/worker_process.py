"""Plugin worker process entrypoint (UID 1002: appplugin).

This module runs in a separate subprocess with reduced privileges and no access
to sidecar daemon secrets. It communicates with the orchestrator via msgpack
over stdin/stdout.

Security Properties:
- Runs as UID 1002 (appplugin) with no /run/sidecar/ access
- Never imports elspeth.core.security.sidecar_client
- Receives only SecureFrameProxy handles (opaque strings)
- All frame operations marshaled back to orchestrator
- No access to seal keys or construction tokens

Protocol:
- Input (stdin): Msgpack-encoded request dicts
- Output (stdout): Msgpack-encoded response dicts
- Stderr: Logging and error messages

Request Format:
    {
        "operation": "transform",
        "proxy_id": "abc123...",
        "plugin_name": "my_transform",
        "plugin_params": {...},
        "request_id": "req_001"
    }

Response Format (Success):
    {
        "status": "ok",
        "result_proxy_id": "def456...",
        "request_id": "req_001"
    }

Response Format (Error):
    {
        "status": "error",
        "error_type": "PluginError",
        "message": "Plugin failed: ...",
        "request_id": "req_001"
    }

Descriptor Safety:
- Worker process spawned with no inherited file descriptors (FD_CLOEXEC)
- Only stdin/stdout/stderr available
- No socket access to /run/sidecar/
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

import msgpack

# CRITICAL: Do NOT import elspeth.core.security.sidecar_client
# Worker must never have access to sidecar communication


class WorkerError(Exception):
    """Worker process error."""

    pass


class WorkerProtocolError(Exception):
    """Invalid protocol message."""

    pass


def _handle_transform_operation(
    proxy_id: str,
    plugin_name: str,
    plugin_params: dict[str, Any],
) -> str:
    """Execute plugin transformation on proxy.

    Args:
        proxy_id: Opaque proxy handle from orchestrator
        plugin_name: Name of plugin to execute
        plugin_params: Plugin-specific parameters

    Returns:
        New proxy ID after transformation

    Raises:
        WorkerError: If plugin execution fails
    """
    # TODO: Implement actual plugin loading and execution
    # For now, this is a stub that will be implemented when we have:
    # 1. Plugin registry accessible to workers
    # 2. RPC client for proxy operations
    # 3. Plugin discovery mechanism

    # Create proxy handle (no RPC client yet, so operations will fail)
    # proxy = SecureFrameProxy(proxy_id=proxy_id, rpc_client=None)

    # Load and execute plugin
    # plugin = load_plugin(plugin_name)
    # result_proxy = plugin.transform(proxy, **plugin_params)

    # For now, return the same proxy ID (echo behavior)
    # This will be replaced with actual plugin execution
    return proxy_id


def _handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle single request from orchestrator.

    Args:
        request: Msgpack-decoded request dict

    Returns:
        Response dict to send back to orchestrator, or None if shutdown requested

    Raises:
        WorkerProtocolError: If request format is invalid
    """
    # Validate request format
    operation = request.get("operation")
    request_id = request.get("request_id", "unknown")

    # Handle shutdown request (returns None to signal exit)
    if operation == "shutdown":
        return None

    if operation != "transform":
        return {
            "status": "error",
            "error_type": "WorkerProtocolError",
            "message": f"Unknown operation: {operation}",
            "request_id": request_id,
        }

    # Extract parameters
    try:
        proxy_id = request["proxy_id"]
        plugin_name = request["plugin_name"]
        plugin_params = request.get("plugin_params", {})
    except KeyError as e:
        return {
            "status": "error",
            "error_type": "WorkerProtocolError",
            "message": f"Missing required field: {e}",
            "request_id": request_id,
        }

    # Execute transformation
    try:
        result_proxy_id = _handle_transform_operation(
            proxy_id=proxy_id,
            plugin_name=plugin_name,
            plugin_params=plugin_params,
        )

        return {
            "status": "ok",
            "result_proxy_id": result_proxy_id,
            "request_id": request_id,
        }

    except Exception as e:
        # Log full traceback to stderr
        print(f"Worker error in request {request_id}:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        return {
            "status": "error",
            "error_type": type(e).__name__,
            "message": str(e),
            "request_id": request_id,
        }


def worker_main() -> None:
    """Main worker process loop.

    Reads msgpack requests from stdin, processes them, and writes msgpack
    responses to stdout. Continues until EOF received on stdin.

    Shutdown Protocol:
        1. Orchestrator sends {"operation": "shutdown"} message
        2. Orchestrator closes stdin (sends EOF)
        3. msgpack.Unpacker iterator exits immediately on EOF
        4. Worker processes shutdown message (if buffered) or exits cleanly

    Security Notes:
        - Worker runs as UID 1002 (appplugin)
        - No access to /run/sidecar/ directory or session key
        - All seal operations mediated by orchestrator
        - Uses msgpack for compact, safe serialization
    """
    # Use msgpack unpacker for streaming input
    # Access the raw unbuffered stream to avoid Python's buffering layers
    unpacker = msgpack.Unpacker(sys.stdin.buffer.raw, raw=False)
    packer = msgpack.Packer(use_bin_type=True)

    try:
        for packed_request in unpacker:
            # Decode request
            try:
                request = packed_request
                if not isinstance(request, dict):
                    raise WorkerProtocolError(
                        f"Request must be dict, got {type(request)}"
                    )
            except Exception as e:
                # Send error response for malformed request
                error_response = {
                    "status": "error",
                    "error_type": "WorkerProtocolError",
                    "message": f"Failed to decode request: {e}",
                    "request_id": "unknown",
                }
                sys.stdout.buffer.write(packer.pack(error_response))
                sys.stdout.buffer.flush()
                continue

            # Handle request
            response = _handle_request(request)

            # If response is None, shutdown was requested
            if response is None:
                print("Worker received shutdown request", file=sys.stderr)
                break

            # Send response
            sys.stdout.buffer.write(packer.pack(response))
            sys.stdout.buffer.flush()

    except KeyboardInterrupt:
        print("Worker process interrupted", file=sys.stderr)
    except Exception as e:
        print(f"Worker process fatal error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    print("Worker process exiting normally", file=sys.stderr)


if __name__ == "__main__":
    worker_main()
