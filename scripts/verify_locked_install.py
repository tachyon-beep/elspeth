#!/usr/bin/env python3
"""
Verify that the active environment matches a pip-tools lockfile exactly for
all packages pinned in the lock (name==version).

This guards against accidental unpinned installs from pyproject ranges
(`pip install -e .[dev]`) by failing CI if versions drift from the lock.

Usage:
  python scripts/verify_locked_install.py -r requirements-dev.lock
  python scripts/verify_locked_install.py -r requirements.lock
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

try:
    # Python 3.12
    from importlib import metadata as ilmd
except ImportError:  # pragma: no cover - legacy fallback
    import importlib_metadata as ilmd  # type: ignore


LOCK_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\\\s#]+)")


def _norm(name: str) -> str:
    """PEP 503 normalization: lowercase and replace non-alphanumerics with '-'."""
    s = name.strip().lower()
    # Replace any run of non [a-z0-9] with '-'
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_lockfile(path: Path) -> Dict[str, str]:
    """Parse pip-tools lockfile and extract package==version pins."""
    pinned: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        m = LOCK_RE.match(raw)
        if not m:
            continue
        name = _norm(m.group("name"))
        version = m.group("version")
        pinned[name] = version
    return pinned


def get_installed() -> Dict[str, str]:
    """Get all installed packages and versions from the active environment."""
    installed: Dict[str, str] = {}
    for dist in ilmd.distributions():
        try:
            name = _norm(dist.metadata["Name"])
            version = dist.version
        except (KeyError, AttributeError):  # pragma: no cover - defensive
            # Malformed distribution metadata; skip
            continue
        installed[name] = version
    return installed


@dataclass
class Diff:
    """Result of comparing installed packages against lockfile pins."""

    missing: Dict[str, str]
    mismatched: Dict[str, Tuple[str, str]]  # name -> (installed, locked)


def diff_env(pinned: Dict[str, str], installed: Dict[str, str]) -> Diff:
    """Compare installed packages against lockfile pins and return differences."""
    missing: Dict[str, str] = {}
    mismatched: Dict[str, Tuple[str, str]] = {}
    for name, locked_version in pinned.items():
        inst = installed.get(name)
        if inst is None:
            missing[name] = locked_version
            continue
        if inst != locked_version:
            mismatched[name] = (inst, locked_version)
    return Diff(missing=missing, mismatched=mismatched)


def main() -> int:
    """Main entry point: verify active environment matches lockfile versions."""
    ap = argparse.ArgumentParser(description="Verify environment matches lockfile versions")
    ap.add_argument("-r", "--requirements", required=True, help="Path to pip-tools lockfile")
    args = ap.parse_args()

    lock_path = Path(args.requirements)
    if not lock_path.exists():
        print(f"Lockfile not found: {lock_path}", file=sys.stderr)
        return 2

    pinned = parse_lockfile(lock_path)
    installed = get_installed()
    diff = diff_env(pinned, installed)

    if diff.missing or diff.mismatched:
        print("Environment does not match lockfile:")
        if diff.missing:
            print("  Missing packages:")
            for name, ver in sorted(diff.missing.items()):
                print(f"    - {name}=={ver}")
        if diff.mismatched:
            print("  Version mismatches:")
            for name, (have, want) in sorted(diff.mismatched.items()):
                print(f"    - {name}: installed {have}, locked {want}")
        print("\nRemediation: run 'pip-sync <lockfile>' to restore the environment.")
        return 1

    print(f"✓ Environment matches lockfile ({lock_path.name}) for {len(pinned)} packages")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
