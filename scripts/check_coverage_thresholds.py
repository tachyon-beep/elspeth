#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enforce per-file coverage thresholds using coverage.xml (Cobertura format)")
    p.add_argument("--xml", default="coverage.xml", help="Path to coverage.xml")
    p.add_argument(
        "--file",
        action="append",
        default=[],
        help="File threshold in the form path:threshold (e.g., src/elspeth/cli.py:0.85)",
    )
    return p.parse_args()


def main() -> int:
    ns = parse_args()
    xml_path = Path(ns.xml)
    if not xml_path.exists():
        print(f"[coverage] File not found: {xml_path}", file=sys.stderr)
        return 2

    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        print(f"[coverage] Failed to parse {xml_path}: {exc}", file=sys.stderr)
        return 2

    # Build a map of filename -> line-rate
    rates: dict[str, float] = {}
    for cl in root.findall(".//class"):
        fn = cl.get("filename")
        lr = cl.get("line-rate")
        if fn and lr is not None:
            try:
                rates[fn] = float(lr)
            except ValueError:
                continue

    failures: list[str] = []
    for spec in ns.file:
        if ":" not in spec:
            print(f"[coverage] Invalid --file spec (expected path:threshold): {spec}", file=sys.stderr)
            return 2
        path, thresh = spec.split(":", 1)
        try:
            threshold = float(thresh)
        except ValueError:
            print(f"[coverage] Invalid threshold for {path}: {thresh}", file=sys.stderr)
            return 2
        observed = rates.get(path)
        if observed is None:
            failures.append(f"{path}: no coverage data found")
            continue
        if observed + 1e-9 < threshold:
            failures.append(f"{path}: observed {observed:.4f} < required {threshold:.4f}")
        else:
            print(f"[coverage] OK {path}: {observed:.4f} >= {threshold:.4f}")

    if failures:
        print("[coverage] Per-file coverage check failed:", file=sys.stderr)
        for f in failures:
            print(f" - {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

