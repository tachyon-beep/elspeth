# tests/conftest.py
"""Root conftest for test suite v2.

Responsibilities:
- Register ALL pytest markers
- Register Hypothesis profiles (ci, nightly, debug)
- Auto-mark tests by directory location
- Autouse secrets fixture for CI parity
"""

from __future__ import annotations

import os

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


@pytest.fixture(autouse=True)
def _allow_raw_secrets_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow raw secrets in all tests — CI has no .env file.

    Locally, .env sets ELSPETH_ALLOW_RAW_SECRETS=true which bypasses
    the fingerprint key requirement for test API keys.  CI doesn't load
    .env, so tests that create AuditedHTTPClient with auth headers fail
    with FrameworkBugError.  This fixture ensures consistent behaviour.
    """
    monkeypatch.setenv("ELSPETH_ALLOW_RAW_SECRETS", "true")
