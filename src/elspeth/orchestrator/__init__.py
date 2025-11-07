"""Orchestrator module for managing SecureDataFrame operations.

The orchestrator runs as UID 1000 (appuser) and coordinates:
- Real SecureDataFrame instances (in-process)
- Plugin worker processes (UID 1002, subprocess isolation)
- Sidecar daemon communication (UID 1001, Unix socket)

Security Architecture:
- Orchestrator owns all SecureDataFrame instances
- Workers receive only SecureFrameProxy handles
- All seal operations go through sidecar daemon
- Worker processes isolated via UID separation

Components:
- worker_process: Plugin worker subprocess entrypoint
- runtime: Orchestrator runtime for spawning and managing workers
- sidecar_client: Client for communicating with Rust daemon
"""

from .runtime import WorkerProcess, WorkerRuntimeError, worker_pool
from .worker_process import WorkerError, WorkerProtocolError, worker_main

__all__ = [
    "WorkerProcess",
    "WorkerRuntimeError",
    "worker_pool",
    "WorkerError",
    "WorkerProtocolError",
    "worker_main",
]
