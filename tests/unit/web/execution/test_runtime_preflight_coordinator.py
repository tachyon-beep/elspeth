"""Runtime preflight in-flight coordination tests."""

from __future__ import annotations

import asyncio

import pytest

from elspeth.web.execution.runtime_preflight import (
    RuntimePreflightCoordinator,
    RuntimePreflightFailure,
    RuntimePreflightKey,
)
from elspeth.web.execution.schemas import ValidationResult


@pytest.mark.asyncio
async def test_coordinator_deduplicates_concurrent_same_session_state_settings() -> None:
    coordinator = RuntimePreflightCoordinator()
    key = RuntimePreflightKey(
        session_scope="session:abc123",
        state_version=7,
        settings_hash="settings-hash",
    )
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()
    expected = ValidationResult(is_valid=True, checks=[], errors=[])

    async def worker() -> ValidationResult:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return expected

    first_task = asyncio.create_task(coordinator.run(key, worker))
    await started.wait()
    second_task = asyncio.create_task(coordinator.run(key, worker))

    await asyncio.sleep(0)
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert first is expected
    assert second is expected
    assert calls == 1


@pytest.mark.asyncio
async def test_coordinator_deduplicates_concurrent_failure_for_same_key() -> None:
    coordinator = RuntimePreflightCoordinator()
    key = RuntimePreflightKey(
        session_scope="session:abc123",
        state_version=7,
        settings_hash="settings-hash",
    )
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()
    original = RuntimeError("constructor failed")

    async def worker() -> ValidationResult:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        raise original

    first_task = asyncio.create_task(coordinator.run(key, worker))
    await started.wait()
    second_task = asyncio.create_task(coordinator.run(key, worker))

    await asyncio.sleep(0)
    release.set()
    first, second = await asyncio.gather(first_task, second_task)

    assert isinstance(first, RuntimePreflightFailure)
    assert isinstance(second, RuntimePreflightFailure)
    assert first.original_exc is original
    assert second.original_exc is original
    assert calls == 1


@pytest.mark.asyncio
async def test_coordinator_does_not_share_different_session_scopes() -> None:
    coordinator = RuntimePreflightCoordinator()
    calls = 0

    async def worker() -> ValidationResult:
        nonlocal calls
        calls += 1
        return ValidationResult(is_valid=True, checks=[], errors=[])

    await asyncio.gather(
        coordinator.run(RuntimePreflightKey("session:http", 1, "settings"), worker),
        coordinator.run(RuntimePreflightKey("session:mcp", 1, "settings"), worker),
    )

    assert calls == 2
