#!/usr/bin/env python3
"""Validate YAML templates under config/templates/.

This script loads all .yaml/.yml files and reports parsing errors.
It does not enforce schema; it is intended as a quick syntactic check.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"PyYAML is required: {exc}", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    root = Path("config/templates")
    if not root.exists():
        print("No config/templates directory found; nothing to validate.")
        return 0
    failures = 0
    files = sorted(p for p in root.glob("*.y*ml"))
    if not files:
        print("No YAML templates found.")
        return 0
    for path in files:
        try:
            _ = yaml.safe_load(path.read_text(encoding="utf-8"))
            print(f"✓ {path}")
        except Exception as exc:  # yaml.YAMLError and friends
            failures += 1
            print(f"✗ {path}: {exc}")
    if failures:
        print(f"Validation failed for {failures} file(s).", file=sys.stderr)
        return 1
    print(f"Validated {len(files)} template(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

