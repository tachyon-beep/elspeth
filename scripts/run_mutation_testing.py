#!/usr/bin/env python3
"""Run mutation testing on ELSPETH core modules using cosmic-ray.

Mutation testing validates test effectiveness by introducing artificial bugs
(mutants) and checking if tests catch them. A high mutation score means tests
actually verify behavior, not just execute code.

Usage:
    # Run on canonical.py (default, critical module)
    python scripts/run_mutation_testing.py

    # Run on specific module
    python scripts/run_mutation_testing.py --module landscape/recorder.py

    # Run on all core modules (slow!)
    python scripts/run_mutation_testing.py --all

    # Show survived mutants from last run
    python scripts/run_mutation_testing.py --show-survivors

Target mutation scores:
    - canonical.py: 95%+ (hash integrity is foundational)
    - landscape/: 90%+ (audit trail is the legal record)
    - engine/: 85%+ (orchestration correctness)

Exit codes:
    0: Mutation testing completed (check output for score)
    1: Error during testing
    2: Mutation score below threshold (when --strict is used)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Module paths relative to src/elspeth/core/, with per-module test scopes
MODULES: dict[str, dict[str, str | list[str]]] = {
    "canonical.py": {
        "path": "src/elspeth/core/canonical.py",
        "tests": ["tests/unit/core/test_canonical.py", "tests/unit/core/test_canonical_mutation_gaps.py"],
    },
    "landscape/recorder.py": {
        "path": "src/elspeth/core/landscape/recorder.py",
        "tests": ["tests/unit/core/landscape/"],
    },
    "landscape/exporter.py": {
        "path": "src/elspeth/core/landscape/exporter.py",
        "tests": ["tests/unit/core/landscape/"],
    },
    "landscape/models.py": {
        "path": "src/elspeth/core/landscape/models.py",
        "tests": ["tests/unit/core/landscape/"],
    },
}

# Target mutation scores per module
THRESHOLDS: dict[str, int] = {
    "canonical.py": 95,
    "landscape/recorder.py": 90,
    "landscape/exporter.py": 90,
    "landscape/models.py": 90,
}

SESSION_DIR = Path(".cosmic-ray")


def _session_path(module_key: str) -> Path:
    """Get session file path for a module."""
    safe_name = module_key.replace("/", "_").replace(".py", "")
    return SESSION_DIR / f"{safe_name}.sqlite"


def _config_path(module_key: str) -> Path:
    """Get config file path for a module."""
    safe_name = module_key.replace("/", "_").replace(".py", "")
    return SESSION_DIR / f"{safe_name}.toml"


def _write_config(module_key: str) -> Path:
    """Generate a cosmic-ray TOML config for a module."""
    module_info = MODULES[module_key]
    module_path = module_info["path"]
    test_paths = module_info["tests"]

    test_args = " ".join(str(t) for t in test_paths)
    test_command = f"python -m pytest {test_args} --tb=short -q"

    config = f"""[cosmic-ray]
module-path = "{module_path}"
timeout = 30
excluded-modules = []
test-command = "{test_command}"

[cosmic-ray.distributor]
name = "local"
"""
    config_file = _config_path(module_key)
    config_file.write_text(config)
    return config_file


def run_cosmic_ray(module_key: str, timeout_minutes: int = 120) -> int:
    """Run cosmic-ray on a specific module.

    Args:
        module_key: Key in MODULES dict (e.g., "canonical.py")
        timeout_minutes: Maximum time to wait

    Returns:
        Exit code (0 = success)
    """
    module_info = MODULES[module_key]
    module_path = module_info["path"]

    if not Path(module_path).exists():
        print(f"Module not found: {module_path}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"Running mutation testing on: {module_key}")
    print(f"{'=' * 60}\n")

    config_file = _write_config(module_key)
    session_file = _session_path(module_key)

    # Phase 1: Init - discover all mutants
    print("Phase 1: Discovering mutants...")
    try:
        subprocess.run(
            [sys.executable, "-m", "cosmic_ray.cli", "init", str(config_file), str(session_file), "--force"],
            timeout=60,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Init failed with exit code {e.returncode}")
        return 1
    except subprocess.TimeoutExpired:
        print("Init timed out after 60 seconds")
        return 1

    # Phase 2: Baseline - verify tests pass without mutations
    print("Phase 2: Running baseline (verifying tests pass unmutated)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "cosmic_ray.cli", "baseline", str(config_file)],
            timeout=120,
            check=True,
        )
    except subprocess.CalledProcessError:
        print("Baseline FAILED: tests don't pass without mutations!")
        print("Fix your tests before running mutation testing.")
        return 1
    except subprocess.TimeoutExpired:
        print("Baseline timed out after 120 seconds")
        return 1

    # Phase 3: Exec - run mutations
    print("Phase 3: Executing mutations (this takes a while)...")
    try:
        subprocess.run(
            [sys.executable, "-m", "cosmic_ray.cli", "exec", str(config_file), str(session_file)],
            timeout=timeout_minutes * 60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"Exec timed out after {timeout_minutes} minutes")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1

    return 0


def calculate_score(module_key: str) -> tuple[int, int, int, float] | None:
    """Calculate mutation score from session results.

    Returns:
        Tuple of (killed, survived, total, score_percent) or None if no results.
    """
    session_file = _session_path(module_key)
    if not session_file.exists():
        return None

    try:
        from cosmic_ray.work_db import WorkDB, use_db
        from cosmic_ray.work_item import TestOutcome, WorkerOutcome
    except ImportError:
        print("cosmic-ray not installed, cannot parse results")
        return None

    with use_db(str(session_file), WorkDB.Mode.open) as db:
        killed = 0
        survived = 0
        incompetent = 0
        timeout = 0

        for _job_id, result in db.results:
            if result.worker_outcome == WorkerOutcome.NORMAL:
                if result.test_outcome == TestOutcome.KILLED:
                    killed += 1
                elif result.test_outcome == TestOutcome.SURVIVED:
                    survived += 1
                elif result.test_outcome == TestOutcome.INCOMPETENT:
                    incompetent += 1
            elif result.worker_outcome == WorkerOutcome.ABNORMAL:
                timeout += 1

        # Total = killed + survived (incompetent mutants are excluded from score)
        total = killed + survived
        if total == 0:
            return None

        score = (killed / total) * 100
        return killed, survived, total, score


def show_results(module_key: str) -> None:
    """Show mutation testing results for a module."""
    score_data = calculate_score(module_key)
    if score_data is None:
        print(f"\nNo results for {module_key}")
        return

    killed, survived, total, score = score_data
    print(f"\nResults for {module_key}:")
    print(f"  Killed:   {killed}")
    print(f"  Survived: {survived}")
    print(f"  Total:    {total}")
    print(f"  Score:    {score:.1f}%")


def show_survivors(module_key: str) -> None:
    """Show details of survived mutants for a module."""
    session_file = _session_path(module_key)
    if not session_file.exists():
        print(f"\nNo session file for {module_key}")
        return

    try:
        from cosmic_ray.work_db import WorkDB, use_db
        from cosmic_ray.work_item import TestOutcome, WorkerOutcome
    except ImportError:
        print("cosmic-ray not installed")
        return

    print(f"\nSurvived mutants for {module_key}:")
    print("-" * 50)

    with use_db(str(session_file), WorkDB.Mode.open) as db:
        survivor_count = 0
        for job_id, result in db.results:
            if result.worker_outcome == WorkerOutcome.NORMAL and result.test_outcome == TestOutcome.SURVIVED:
                survivor_count += 1
                if result.diff:
                    print(f"\n  Mutant {job_id}:")
                    for line in result.diff.split("\n"):
                        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                            print(f"    {line}")

        if survivor_count == 0:
            print("  No survivors - all mutants were killed!")
        else:
            print(f"\n  Total survivors: {survivor_count}")


def main() -> int:
    """Run mutation testing."""
    parser = argparse.ArgumentParser(
        description="Run mutation testing on ELSPETH core modules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--module",
        "-m",
        help="Module to test (e.g., canonical.py, landscape/recorder.py)",
        default="canonical.py",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run on all core modules (slow!)",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Don't clean session files before running",
    )
    parser.add_argument(
        "--show-survivors",
        action="store_true",
        help="Show survived mutants from last run",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if score below threshold",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in minutes (default: 120)",
    )

    args = parser.parse_args()

    # Determine modules to test
    if args.all:
        modules = list(MODULES.keys())
    else:
        if args.module not in MODULES:
            print(f"Unknown module: {args.module}")
            print(f"Available: {', '.join(MODULES.keys())}")
            return 1
        modules = [args.module]

    # Show survivors and exit
    if args.show_survivors:
        for module in modules:
            show_results(module)
            show_survivors(module)
        return 0

    # Ensure session directory exists
    SESSION_DIR.mkdir(exist_ok=True)

    # Clean session files unless --no-clean
    if not args.no_clean:
        for module in modules:
            session = _session_path(module)
            if session.exists():
                print(f"Cleaning {session}...")
                session.unlink()

    if args.all:
        print("Running mutation testing on ALL core modules")
        print("This will take a long time (potentially hours)")

    # Run mutation testing
    exit_code = 0
    for module in modules:
        result = run_cosmic_ray(module, timeout_minutes=args.timeout)
        if result != 0:
            exit_code = 1
            continue

        # Show results
        show_results(module)

        # Check threshold if strict mode
        if args.strict:
            score_data = calculate_score(module)
            if score_data:
                killed, survived, total, score = score_data
                threshold = THRESHOLDS.get(module, 80)
                print(f"\n  Threshold: {threshold}%")
                if score < threshold:
                    print(f"  FAILED: Score {score:.1f}% below {threshold}% threshold")
                    exit_code = 2
                else:
                    print(f"  PASSED: Score {score:.1f}% meets {threshold}% threshold")

    print(f"\n{'=' * 60}")
    print("Tips:")
    print("  - Use '--show-survivors' to see which mutations weren't caught")
    print("  - Session files are in .cosmic-ray/ for manual inspection")
    print("  - Use 'cosmic-ray dump <session.sqlite>' for raw JSON output")
    print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
