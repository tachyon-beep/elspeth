#!/usr/bin/env python3
"""
Update Anchore Grype version in CI workflows.

Targets:
- .github/workflows/ci.yml
- .github/workflows/publish.yml

Behavior:
- Fetch latest Grype release tag from GitHub API (anchore/grype).
- Replace YAML inputs like `grype-version: vX.Y.Z` with latest tag.
- Emit outputs NEW_VERSION and UPDATED (true/false) for GitHub Actions.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Iterable


FILES = [
    ".github/workflows/ci.yml",
    ".github/workflows/publish.yml",
]

GITHUB_API = "https://api.github.com/repos/anchore/grype/releases/latest"


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "elspeth-grype-bump-bot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def latest_grype_tag() -> str:
    data = http_get_json(GITHUB_API)
    tag = (data.get("tag_name") or "").strip()
    if not tag or not tag.startswith("v"):
        raise RuntimeError("Could not resolve latest Grype tag")
    return tag


def update_files(paths: Iterable[str], new_tag: str) -> bool:
    pattern = re.compile(r"(grype-version:\s*)(v\d+\.\d+\.\d+)")
    updated_any = False
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            continue

        new_content, n = pattern.subn(rf"\1{new_tag}", content)
        if n > 0 and new_content != content:
            with open(p, "w", encoding="utf-8") as f:
                f.write(new_content)
            updated_any = True
    return updated_any


def write_outputs(new_version: str, updated: bool) -> None:
    lines = [
        f"NEW_VERSION={new_version}",
        f"UPDATED={'true' if updated else 'false'}",
    ]
    for line in lines:
        print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")


def main() -> int:
    try:
        new_tag = latest_grype_tag()
        updated = update_files(FILES, new_tag)
        write_outputs(new_tag, updated)
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

