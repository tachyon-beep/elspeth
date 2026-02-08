# tests/conftest.py
"""Root conftest for test suite v2.

Responsibilities:
- Register ALL pytest markers
- Register Hypothesis profiles (ci, nightly, debug)
- Autouse telemetry cleanup fixture
- Auto-mark tests by directory location
"""

from __future__ import annotations

import os
import queue as queue_module
import warnings
from collections.abc import Iterator
from typing import Any

import pytest
from hypothesis import Phase, Verbosity, settings

# ---------------------------------------------------------------------------
# Marker Registration
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test tiers."""
    config.addinivalue_line("markers", "integration: multi-component tests with real DB")
    config.addinivalue_line("markers", "e2e: full pipeline, real I/O, file-based DB")
    config.addinivalue_line("markers", "performance: benchmarks and regression detection")
    config.addinivalue_line("markers", "stress: load tests requiring ChaosLLM HTTP server")
    config.addinivalue_line("markers", "slow: long-running tests (>10s)")
    config.addinivalue_line(
        "markers",
        "chaosllm(preset=None, **kwargs): Configure ChaosLLM server for the test. "
        "Use preset='name' to load a preset, and keyword args to override specific settings.",
    )


# ---------------------------------------------------------------------------
# Auto-Marking by Directory
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply markers based on test file location."""
    for item in items:
        path = str(item.fspath)
        if "/e2e/" in path:
            item.add_marker(pytest.mark.e2e)
        elif "/performance/" in path and "/stress/" in path:
            item.add_marker(pytest.mark.stress)
            item.add_marker(pytest.mark.performance)
        elif "/performance/" in path:
            item.add_marker(pytest.mark.performance)
        # integration/ tests get marker from their conftest


# ---------------------------------------------------------------------------
# Hypothesis Profiles
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
)
settings.register_profile(
    "nightly",
    max_examples=1000,
    deadline=None,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
)
settings.register_profile(
    "debug",
    max_examples=10,
    deadline=None,
    verbosity=Verbosity.verbose,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))


# ---------------------------------------------------------------------------
# Autouse: Telemetry Cleanup
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_close_telemetry_managers() -> Iterator[None]:
    """Close TelemetryManager instances to prevent thread leaks.

    TelemetryManager starts a non-daemon background thread for async export.
    Without cleanup, these threads block pytest from exiting. This fixture
    tracks all instances created during each test and closes them in teardown.
    """
    from elspeth.telemetry.manager import TelemetryManager

    created_managers: list[tuple[TelemetryManager, queue_module.Queue[Any]]] = []
    original_init = TelemetryManager.__init__

    def tracking_init(self: TelemetryManager, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        created_managers.append((self, self._queue))

    TelemetryManager.__init__ = tracking_init  # type: ignore[method-assign]

    try:
        yield
    finally:
        TelemetryManager.__init__ = original_init  # type: ignore[method-assign]
        cleanup_errors: list[str] = []

        for manager_index, (manager, original_queue) in enumerate(created_managers):
            try:
                manager._shutdown_event.set()

                current_queue = manager._queue
                if current_queue is not original_queue:
                    try:
                        original_queue.put_nowait(None)
                    except queue_module.Full:
                        try:
                            original_queue.get_nowait()
                            original_queue.put_nowait(None)
                        except (queue_module.Full, queue_module.Empty):
                            pass

                if manager._export_thread.is_alive():
                    manager.close()

                if manager._export_thread.is_alive():
                    manager._export_thread.join(timeout=1.0)
            except Exception as exc:
                cleanup_errors.append(f"manager[{manager_index}] {type(exc).__name__}: {exc}")

        if cleanup_errors:
            preview = "\n".join(cleanup_errors[:5])
            if len(cleanup_errors) > 5:
                preview += f"\n... and {len(cleanup_errors) - 5} more"
            warnings.warn(
                f"TelemetryManager cleanup encountered errors.\n{preview}",
                RuntimeWarning,
                stacklevel=1,
            )
