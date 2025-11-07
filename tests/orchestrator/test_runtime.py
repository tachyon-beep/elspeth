"""Tests for orchestrator runtime and worker spawning."""

import os
import sys
import time
from unittest.mock import Mock, patch

import pytest

from elspeth.orchestrator.runtime import WorkerProcess, WorkerRuntimeError, worker_pool


def test_worker_process_sanitizes_environment():
    """Test that worker environment has secrets removed."""
    worker = WorkerProcess(worker_uid=None)

    # Set some secret environment variables
    os.environ["SIDECAR_SESSION_KEY"] = "secret123"
    os.environ["AWS_ACCESS_KEY_ID"] = "aws_secret"
    os.environ["AZURE_CLIENT_SECRET"] = "azure_secret"

    try:
        env = worker._sanitize_environment()

        # Secrets should be removed
        assert "SIDECAR_SESSION_KEY" not in env
        assert "AWS_ACCESS_KEY_ID" not in env
        assert "AZURE_CLIENT_SECRET" not in env

        # PATH should still be present
        assert "PATH" in env

    finally:
        # Clean up test environment
        os.environ.pop("SIDECAR_SESSION_KEY", None)
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AZURE_CLIENT_SECRET", None)


def test_worker_process_get_worker_command_with_uid():
    """Test worker command generation with UID specified."""
    worker = WorkerProcess(worker_uid=1002)
    cmd = worker._get_worker_command()

    assert cmd[0] == "sudo"
    assert cmd[1] == "-u"
    assert cmd[2] == "#1002"
    assert cmd[3] == sys.executable
    assert cmd[4] == "-u"  # Unbuffered Python
    assert cmd[5] == "-m"
    assert cmd[6] == "elspeth.orchestrator.worker_process"


def test_worker_process_get_worker_command_without_uid():
    """Test worker command generation without UID (development mode)."""
    worker = WorkerProcess(worker_uid=None)
    cmd = worker._get_worker_command()

    assert cmd[0] == sys.executable
    assert cmd[1] == "-u"  # Unbuffered Python
    assert cmd[2] == "-m"
    assert cmd[3] == "elspeth.orchestrator.worker_process"
    assert "sudo" not in cmd


def test_worker_process_lifecycle():
    """Test worker start/stop lifecycle.

    This test spawns a real worker subprocess in development mode (same UID).
    """
    worker = WorkerProcess(worker_uid=None)  # Development mode

    # Start worker
    worker.start()
    assert worker.process is not None
    assert worker.process.poll() is None  # Still running

    # Stop worker
    worker.stop()
    assert worker.process is None


def test_worker_process_context_manager():
    """Test worker as context manager."""
    with WorkerProcess(worker_uid=None) as worker:
        assert worker.process is not None
        assert worker.process.poll() is None

    # After context, worker should be stopped
    # (process attribute is None after stop())


def test_worker_process_start_already_started():
    """Test that starting already-started worker raises error."""
    worker = WorkerProcess(worker_uid=None)

    try:
        worker.start()
        with pytest.raises(WorkerRuntimeError, match="already started"):
            worker.start()
    finally:
        worker.stop()


def test_worker_process_transform_echo():
    """Test transform operation through real worker subprocess.

    Uses actual subprocess communication to verify msgpack IPC works.
    Shutdown works via EOF (stdin close) unblocking msgpack iterator.
    """
    worker = WorkerProcess(worker_uid=None)
    worker.start()

    try:
        # Send transform request
        result_proxy_id = worker.transform(
            proxy_id="test_proxy_123",
            plugin_name="test_plugin",
            params={"threshold": 0.5},
        )

        # Current stub implementation echoes proxy_id
        assert result_proxy_id == "test_proxy_123"

    finally:
        worker.stop()


def test_worker_process_transform_multiple_requests():
    """Test multiple transform requests in same worker session."""
    worker = WorkerProcess(worker_uid=None)
    worker.start()

    try:
        # Send multiple requests
        result1 = worker.transform("proxy1", "plugin_a", {})
        result2 = worker.transform("proxy2", "plugin_b", {})
        result3 = worker.transform("proxy3", "plugin_c", {})

        # All should succeed (echo behavior)
        assert result1 == "proxy1"
        assert result2 == "proxy2"
        assert result3 == "proxy3"

    finally:
        worker.stop()


def test_worker_process_transform_not_started():
    """Test that transform fails if worker not started."""
    worker = WorkerProcess(worker_uid=None)

    with pytest.raises(WorkerRuntimeError, match="not started"):
        worker.transform("proxy123", "test_plugin", {})


def test_worker_pool_basic():
    """Test worker pool creation and management."""
    with worker_pool(num_workers=2, worker_uid=None) as workers:
        assert len(workers) == 2
        assert all(w.process is not None for w in workers)

        # All workers should be running
        assert all(w.process.poll() is None for w in workers if w.process is not None)

    # After context, all workers stopped
    # (process attribute is None after stop())


def test_worker_pool_parallel_transforms():
    """Test distributing work across worker pool."""
    proxy_ids = [f"proxy_{i}" for i in range(10)]

    with worker_pool(num_workers=3, worker_uid=None) as workers:
        results = []
        for i, proxy_id in enumerate(proxy_ids):
            # Round-robin distribution
            worker = workers[i % len(workers)]
            result = worker.transform(proxy_id, "test_plugin", {})
            results.append(result)

    # All should succeed (echo behavior)
    assert results == proxy_ids


def test_worker_runtime_descriptor_hygiene():
    """Test that worker subprocess has FD_CLOEXEC set on pipes.

    Python's subprocess module automatically sets FD_CLOEXEC on pipes
    in Python 3.4+, and we use close_fds=True to close other descriptors.
    This test verifies that behavior.
    """
    import fcntl

    with WorkerProcess(worker_uid=None) as worker:
        assert worker.process is not None
        assert worker.process.stdin is not None

        # Get file descriptor
        stdin_fd = worker.process.stdin.fileno()

        # Check FD_CLOEXEC flag
        flags = fcntl.fcntl(stdin_fd, fcntl.F_GETFD)
        assert flags & fcntl.FD_CLOEXEC != 0, "FD_CLOEXEC should be set on worker stdin"


def test_worker_process_request_id_correlation():
    """Test that request IDs are properly correlated in responses."""
    with WorkerProcess(worker_uid=None) as worker:
        # Send multiple requests and verify request_id increments
        worker.transform("proxy1", "plugin", {})  # req_1
        worker.transform("proxy2", "plugin", {})  # req_2
        worker.transform("proxy3", "plugin", {})  # req_3

        assert worker._request_counter == 3


def test_worker_process_start_failure():
    """Test that start failure raises WorkerRuntimeError."""
    with patch("subprocess.Popen", side_effect=OSError("Mock spawn failure")):
        worker = WorkerProcess(worker_uid=None)

        # Should raise WorkerRuntimeError wrapping the OSError
        with pytest.raises(WorkerRuntimeError, match="Failed to spawn worker"):
            worker.start()


def test_worker_process_stop_when_not_started():
    """Test that calling stop() on non-started worker is safe."""
    worker = WorkerProcess(worker_uid=None)

    # Should not raise (line 166 return early)
    worker.stop()

    assert worker.process is None


def test_worker_process_stop_with_broken_pipe():
    """Test that stop() handles broken pipe gracefully."""
    worker = WorkerProcess(worker_uid=None)
    worker.start()

    try:
        if worker.process and worker.process.stdin:
            with patch.object(worker.process.stdin, "write", side_effect=BrokenPipeError):
                # Should not raise - handles BrokenPipeError gracefully (line 179)
                worker.stop()
    finally:
        # Clean up if still running
        if worker.process and worker.process.poll() is None:
            worker.process.kill()


def test_worker_process_stop_with_timeout():
    """Test that stop() uses SIGTERM/SIGKILL if worker doesn't exit."""
    # Create worker that ignores shutdown signal
    worker = WorkerProcess(worker_uid=None)
    worker.start()

    if worker.process:
        # Mock wait() to always timeout
        call_count = [0]

        def mock_wait_timeout(timeout=None):
            call_count[0] += 1
            if call_count[0] <= 2:  # First two waits timeout
                import subprocess
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout)
            # Third wait (after kill) succeeds
            return 0

        try:
            with patch.object(worker.process, "wait", side_effect=mock_wait_timeout):
                # Should handle timeout and eventually kill (lines 187-195)
                worker.stop()

                # Should have called wait() 3 times (initial, after terminate, after kill)
                assert call_count[0] == 3
        finally:
            # Ensure cleanup
            if worker.process and worker.process.poll() is None:
                worker.process.kill()
