"""BUG-001: Circular Import Deadlock - Production Import Test

CRITICAL BUG (P0 - Production Blocker):
    Circular import deadlock prevents central_registry from being imported in
    production Python context (CLI, scripts). This blocks PR #15 merge.

    Import Chain:
        elspeth.core.registry.__init__
        → imports central_registry
        → imports suite_runner (for validation)
        → imports central_registry again
        → DEADLOCK (partially initialized module error)

Root Cause:
    suite_runner.py:28 - Eager import at module level
    ```python
    from elspeth.core.registry import central_registry  # EAGER - causes deadlock
    ```

Fix Strategy:
    Lazy import - Move import inside function where it's used (suite_runner.py:196)
    ```python
    def run_suite(...):
        from elspeth.core.registry import central_registry  # LAZY - breaks cycle
    ```

Test-Driven Development:
    This test is written FIRST (RED state) to demonstrate the deadlock.
    It WILL FAIL until lazy import is applied.

Expected Behavior After Fix:
    Production import succeeds without deadlock error.
"""

import subprocess
import sys

import pytest


def test_circular_import_in_production_context():
    """REGRESSION: Verify central_registry can be imported in production context.

    BUG-001: Circular import deadlock prevents production use of central_registry.
    This test simulates real CLI usage by importing in fresh Python subprocess.

    Import Chain Causing Deadlock:
        1. Import central_registry
        2. central_registry imports suite_runner for validation
        3. suite_runner imports central_registry (module-level, line 28)
        4. DEADLOCK - central_registry partially initialized

    Why Subprocess Test:
        - Pytest's import caching masks the deadlock
        - Production Python interpreter has fresh import state
        - Accurately simulates CLI usage (python -m elspeth.cli)

    Expected State: WILL FAIL (RED) until lazy import applied in suite_runner.py:28
    """
    # Arrange - Fresh Python interpreter (no pytest import caching)
    import_command = "from elspeth.core.registry import central_registry; print('SUCCESS')"

    # Act - Attempt import in production context
    result = subprocess.run(
        [sys.executable, "-c", import_command],
        capture_output=True,
        text=True,
        timeout=5
    )

    # Assert - Import should succeed (after fix)
    assert result.returncode == 0, (
        f"BUG-001: Circular import deadlock detected in production context\n"
        f"\n"
        f"Import failed with exit code {result.returncode}\n"
        f"STDERR:\n{result.stderr}\n"
        f"\n"
        f"Root Cause: suite_runner.py:28 - Eager module-level import\n"
        f"Fix: Change to lazy import inside run_suite() function\n"
        f"\n"
        f"Expected: ImportError containing 'cannot import name' and 'partially initialized'\n"
    )

    assert "SUCCESS" in result.stdout, (
        f"Import succeeded but script did not execute correctly\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )


def test_central_registry_usable_after_import():
    """REGRESSION: Verify central_registry is functional after import.

    This test ensures the fix doesn't just eliminate the error but leaves
    central_registry in a broken state. We verify basic operations work.

    Expected State: WILL FAIL (RED) until lazy import applied.
    """
    # Arrange - Import command with basic usage
    usage_command = """
from elspeth.core.registry import central_registry

# Verify basic registry operations work
datasources = central_registry.list_plugins('datasource')
llms = central_registry.list_plugins('llm')

assert len(datasources) >= 3, f"Expected >=3 datasources, got {len(datasources)}"
assert len(llms) >= 4, f"Expected >=4 LLMs, got {len(llms)}"

print('FUNCTIONAL')
"""

    # Act - Import and use central_registry
    result = subprocess.run(
        [sys.executable, "-c", usage_command],
        capture_output=True,
        text=True,
        timeout=5
    )

    # Assert - Import succeeds AND registry is functional
    assert result.returncode == 0, (
        f"BUG-001: central_registry import or usage failed\n"
        f"\n"
        f"Exit code: {result.returncode}\n"
        f"STDERR:\n{result.stderr}\n"
    )

    assert "FUNCTIONAL" in result.stdout, (
        f"central_registry imported but basic operations failed\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )


def test_cli_entry_point_not_deadlocked():
    """REGRESSION: Verify CLI entry point can import central_registry.

    The most critical test - does the actual CLI work? This simulates:
        python -m elspeth.cli --help

    Expected State: WILL FAIL (RED) until lazy import applied.
    """
    # Arrange - CLI help command (lightest touch)
    result = subprocess.run(
        [sys.executable, "-m", "elspeth.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=5
    )

    # Assert - CLI should load without import errors
    # Note: We check returncode OR stderr for import errors because
    # --help might fail with usage errors (but not import errors)
    assert "cannot import name" not in result.stderr.lower(), (
        f"BUG-001: CLI entry point has circular import deadlock\n"
        f"\n"
        f"STDERR:\n{result.stderr}\n"
        f"\n"
        f"This is the production blocker - CLI cannot start.\n"
    )

    assert "partially initialized" not in result.stderr.lower(), (
        f"BUG-001: CLI entry point has circular import deadlock\n"
        f"\n"
        f"STDERR:\n{result.stderr}\n"
    )
