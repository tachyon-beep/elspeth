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
import sys

import pytest
from hypothesis import Phase, Verbosity, settings

# Belt-and-suspenders fence: the Tier-1 guards in production code are
# explicit ``raise AuditIntegrityError`` (survives ``python -O``), but a
# handful of existing tests still use plain ``assert`` statements in
# arrange/act lines.  Running the suite under ``-O`` would silently erase
# those assertions, turning coverage-theatre into green-on-broken.  We
# refuse to import the suite under an optimised interpreter so the
# failure is loud and unmistakable.  Expressed as an ``if / raise`` (not
# ``assert``) because ``-O`` strips asserts at import time.
if sys.flags.optimize != 0:
    raise RuntimeError(
        "ELSPETH tests must not run under `python -O` — assert statements are stripped, "
        "which silently disables assertion-based test contracts.  Re-run without -O."
    )

# ---------------------------------------------------------------------------
# DeclarationContract registry population
# ---------------------------------------------------------------------------
#
# ADR-010 Phase 2A introduced a set-equality bootstrap check against
# EXPECTED_CONTRACTS (issue elspeth-b03c6112c0 / C2). Every contract in
# the manifest MUST be registered before ``prepare_for_run()`` is called,
# or bootstrap raises. Registration is a module-import side effect — see
# ``src/elspeth/contracts/declaration_contracts.py`` CLOSED-SET comment.
#
# Test files that invoke the orchestrator (directly or via ``elspeth
# run``) but do not transitively import the contract-defining executors
# hit an empty-registry bootstrap failure. In xdist-distributed runs the
# failure manifests non-deterministically depending on which worker
# receives which test file first. Importing the executor module at root
# conftest level populates the registry once per pytest process (xdist
# workers included) so every test starts from the production registry
# state. Individual tests that need to clear or mutate the registry use
# the ``_snapshot_registry_for_tests`` / ``_restore_registry_snapshot_for_tests``
# helpers, which are pytest-gated (issue elspeth-cc511e7234 / C3).
from elspeth.engine.executors import pass_through  # noqa: F401  (import side-effect registers PassThroughDeclarationContract)

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
