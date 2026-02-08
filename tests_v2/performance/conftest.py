# tests_v2/performance/conftest.py
"""Performance test configuration.

Timer context manager, memory tracker, and benchmark registry.
Performance tests are deselected by default.
"""

from __future__ import annotations

import resource
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class TimingResult:
    """Result from benchmark_timer context manager."""

    wall_seconds: float = 0.0
    cpu_seconds: float = 0.0


@contextmanager
def benchmark_timer():
    """Context manager that records wall time and CPU time."""
    result = TimingResult()
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    yield result
    result.wall_seconds = time.perf_counter() - wall_start
    result.cpu_seconds = time.process_time() - cpu_start


@dataclass
class MemorySnapshot:
    """Memory usage snapshot."""

    rss_bytes: int
    delta_bytes: int = 0


@pytest.fixture
def memory_tracker():
    """Track RSS memory before/after test execution."""
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

    class Tracker:
        def snapshot(self) -> MemorySnapshot:
            current = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            return MemorySnapshot(rss_bytes=current, delta_bytes=current - before)

    return Tracker()


@dataclass
class BenchmarkRegistry:
    """Stores benchmark results for cross-test comparison."""

    results: dict[str, Any] = field(default_factory=dict)

    def record(self, name: str, value: float, unit: str = "ops/sec") -> None:
        self.results[name] = {"value": value, "unit": unit}


@pytest.fixture
def benchmark_registry() -> BenchmarkRegistry:
    """Registry for recording benchmark results."""
    return BenchmarkRegistry()
