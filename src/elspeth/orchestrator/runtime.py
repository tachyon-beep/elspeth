"""Orchestrator runtime for managing plugin workers and sidecar communication.

The orchestrator runs as UID 1000 (appuser) and coordinates:
- SecureDataFrame instances (in-process)
- Plugin workers (UID 1002, subprocess isolation)
- Sidecar daemon (UID 1001, Unix socket)

Security Architecture:
- Workers spawned with reduced privileges (UID 1002)
- No worker access to /run/sidecar/ or session key
- FD_CLOEXEC on all orchestrator descriptors
- Msgpack IPC over stdin/stdout pipes

Worker Lifecycle:
1. Spawn worker subprocess (python -m elspeth.orchestrator.worker_process)
2. Establish msgpack communication channel
3. Send transformation requests with proxy handles
4. Receive transformed proxy handles
5. Terminate worker when done
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from typing import Any, Generator

import msgpack


class WorkerRuntimeError(Exception):
    """Worker runtime error."""

    pass


class WorkerProcess:
    """Manages a single plugin worker subprocess.

    The worker runs as UID 1002 (appplugin) with no access to sidecar secrets.
    Communication happens via msgpack over stdin/stdout pipes.

    Security Properties:
        - Worker UID isolation (1002 vs 1000 orchestrator)
        - No SIDECAR_SESSION_KEY in environment
        - FD_CLOEXEC on all orchestrator descriptors
        - Msgpack-only communication (no shared memory)

    Example:
        with WorkerProcess() as worker:
            result_proxy_id = worker.transform(
                proxy_id="abc123",
                plugin_name="my_transform",
                params={"threshold": 0.5}
            )
    """

    def __init__(self, worker_uid: int | None = None):
        """Initialize worker process manager.

        Args:
            worker_uid: Target UID for worker process (None = current user)
                       In production: 1002 (appplugin)
                       In development: None (run as current user)
        """
        self.worker_uid = worker_uid
        self.process: subprocess.Popen | None = None
        self._request_counter = 0
        self._unpacker: msgpack.Unpacker | None = None

    def _get_worker_command(self) -> list[str]:
        """Build command to spawn worker process.

        Returns:
            Command list for subprocess.Popen

        Notes:
            In container with supervisord:
                sudo -u appplugin python -u -m elspeth.orchestrator.worker_process

            In development (same user):
                python -u -m elspeth.orchestrator.worker_process

            The -u flag runs Python unbuffered to ensure msgpack responses
            flush immediately without buffering in userspace.
        """
        base_cmd = [sys.executable, "-u", "-m", "elspeth.orchestrator.worker_process"]

        if self.worker_uid is not None:
            # Production: Use sudo to switch UID
            # Requires /etc/sudoers entry: appuser ALL=(appplugin) NOPASSWD: ...
            return ["sudo", "-u", f"#{self.worker_uid}"] + base_cmd
        else:
            # Development: Run as current user
            return base_cmd

    def _sanitize_environment(self) -> dict[str, str]:
        """Create sanitized environment for worker.

        Returns:
            Environment dict with secrets removed

        Security:
            - Removes SIDECAR_SESSION_KEY if present
            - Preserves PATH, PYTHONPATH, etc. for imports
            - Removes any AWS_, AZURE_, etc. credential variables
        """
        # Start with current environment
        env = os.environ.copy()

        # Remove sidecar secrets
        env.pop("SIDECAR_SESSION_KEY", None)
        env.pop("ELSPETH_SIDECAR_SESSION_KEY", None)

        # Remove cloud credentials (workers shouldn't access cloud directly)
        secrets_prefixes = ["AWS_", "AZURE_", "GOOGLE_", "GCP_"]
        for key in list(env.keys()):
            if any(key.startswith(prefix) for prefix in secrets_prefixes):
                del env[key]

        return env

    def start(self) -> None:
        """Spawn worker subprocess with privilege separation.

        Raises:
            WorkerRuntimeError: If worker fails to start
        """
        if self.process is not None:
            raise WorkerRuntimeError("Worker already started")

        cmd = self._get_worker_command()
        env = self._sanitize_environment()

        try:
            # Spawn worker with stdin/stdout pipes
            # FD_CLOEXEC is set automatically on pipes in Python 3.4+
            # stderr → DEVNULL prevents back-pressure from filling stderr buffer
            self.process = subprocess.Popen(  # noqa: S603 - cmd is trusted worker entry point, not user input
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Prevent stderr back-pressure
                env=env,
                close_fds=True,  # Close all non-stdio FDs in child
                bufsize=0,  # Unbuffered pipes for immediate I/O
            )

            # Create single persistent Unpacker wrapping stdout for blocking reads
            # This is the SIMPLE approach: blocking is fine, EOF from stdin.close() unblocks
            self._unpacker = msgpack.Unpacker(self.process.stdout, raw=False)

        except Exception as e:
            raise WorkerRuntimeError(f"Failed to spawn worker: {e}") from e

    def stop(self) -> None:
        """Terminate worker process gracefully.

        Sends shutdown message and closes stdin to trigger EOF.
        The msgpack iterator in the worker unblocks immediately on EOF.
        If worker doesn't exit within timeout, sends SIGTERM.
        """
        if self.process is None:
            return

        try:
            # Send shutdown message and close stdin to trigger EOF
            if self.process.stdin and not self.process.stdin.closed:
                try:
                    shutdown_msg = {"operation": "shutdown"}
                    packer = msgpack.Packer(use_bin_type=True)
                    self.process.stdin.write(packer.pack(shutdown_msg))
                    self.process.stdin.flush()

                    # Close stdin to send EOF → unblocks msgpack iterator immediately
                    self.process.stdin.close()
                except (OSError, BrokenPipeError):
                    # Pipe broken, worker already exited
                    pass

            # Wait for clean shutdown (2 second timeout)
            # Worker should exit immediately after receiving EOF
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                # Worker didn't exit cleanly, force termination
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    # Still didn't exit, kill it
                    self.process.kill()
                    self.process.wait()

        except Exception:
            # Best effort cleanup
            if self.process and self.process.poll() is None:
                self.process.kill()

        finally:
            self.process = None
            self._unpacker = None

    def transform(
        self,
        proxy_id: str,
        plugin_name: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Execute plugin transformation on proxy.

        Args:
            proxy_id: Opaque proxy handle from orchestrator
            plugin_name: Name of plugin to execute
            params: Plugin-specific parameters

        Returns:
            New proxy ID after transformation

        Raises:
            WorkerRuntimeError: If worker is not running or communication fails
            RuntimeError: If plugin execution fails
        """
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise WorkerRuntimeError("Worker not started")

        # Generate request ID for correlation
        self._request_counter += 1
        request_id = f"req_{self._request_counter}"

        # Build request
        request = {
            "operation": "transform",
            "proxy_id": proxy_id,
            "plugin_name": plugin_name,
            "plugin_params": params or {},
            "request_id": request_id,
        }

        try:
            # Send request via msgpack
            packer = msgpack.Packer(use_bin_type=True)
            self.process.stdin.write(packer.pack(request))
            self.process.stdin.flush()

            # Receive response using simple blocking read
            # EOF from stdin.close() will unblock the iterator when worker shuts down
            if self._unpacker is None:
                raise WorkerRuntimeError("Unpacker not initialized")

            response = next(self._unpacker)

            # Validate response
            if not isinstance(response, dict):
                raise WorkerRuntimeError(
                    f"Invalid response type: {type(response)}"
                )

            if response.get("request_id") != request_id:
                raise WorkerRuntimeError(
                    f"Request ID mismatch: expected {request_id}, "
                    f"got {response.get('request_id')}"
                )

            # Check status
            if response["status"] != "ok":
                error_msg = response.get("message", "Unknown error")
                error_type = response.get("error_type", "WorkerError")
                raise RuntimeError(f"{error_type}: {error_msg}")

            return response["result_proxy_id"]

        except (OSError, EOFError) as e:
            # Worker died or pipe broken
            raise WorkerRuntimeError(f"Worker communication failed: {e}") from e
        except StopIteration:
            # No response received (EOF)
            raise WorkerRuntimeError("Worker closed stdout unexpectedly")

    def __enter__(self) -> WorkerProcess:
        """Context manager entry - start worker."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit - stop worker."""
        self.stop()


@contextmanager
def worker_pool(
    num_workers: int = 1,
    worker_uid: int | None = None,
) -> Generator[list[WorkerProcess], None, None]:
    """Context manager for pool of worker processes.

    Args:
        num_workers: Number of workers to spawn
        worker_uid: Target UID for workers (None = current user)

    Yields:
        List of WorkerProcess instances

    Example:
        with worker_pool(num_workers=4, worker_uid=1002) as workers:
            # Distribute work across workers
            for i, proxy_id in enumerate(proxy_ids):
                worker = workers[i % len(workers)]
                result = worker.transform(proxy_id, "my_plugin", {})
    """
    workers = [WorkerProcess(worker_uid=worker_uid) for _ in range(num_workers)]

    try:
        # Start all workers
        for worker in workers:
            worker.start()

        yield workers

    finally:
        # Stop all workers
        for worker in workers:
            worker.stop()
