"""Async coordination for runtime-equivalent composer preflight.

This module is transport-neutral L3 infrastructure. HTTP composer and
composer MCP can share the same process-local coordinator when they share a
logical session. Standalone MCP processes cannot share this lock with the web
process; cross-process safety comes from side-effect-free preflight mode.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from elspeth.web.execution.schemas import ValidationResult


@dataclass(frozen=True, slots=True)
class RuntimePreflightKey:
    session_scope: str
    state_version: int
    settings_hash: str


@dataclass(frozen=True, slots=True)
class RuntimePreflightFailure:
    original_exc: Exception


RuntimePreflightEntry = ValidationResult | RuntimePreflightFailure
RuntimePreflightWorker = Callable[[], Awaitable[ValidationResult]]


class RuntimePreflightCoordinator:
    """Deduplicate in-flight runtime preflight for one Python process."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._inflight: dict[RuntimePreflightKey, asyncio.Task[RuntimePreflightEntry]] = {}

    async def run(
        self,
        key: RuntimePreflightKey,
        worker: RuntimePreflightWorker,
    ) -> RuntimePreflightEntry:
        async with self._lock:
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._capture(worker))
                self._inflight[key] = task

        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._lock:
                    if self._inflight.get(key) is task:
                        self._inflight.pop(key, None)

    async def _capture(self, worker: RuntimePreflightWorker) -> RuntimePreflightEntry:
        try:
            return await worker()
        except Exception as exc:
            return RuntimePreflightFailure(exc)
