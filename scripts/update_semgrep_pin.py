#!/usr/bin/env python3
"""
Update the pinned Semgrep Docker image tag and digest in .github/workflows/ci.yml.

- Fetches latest release tag from GitHub (semgrep/semgrep)
- Resolves Docker Hub digest for that tag (semgrep/semgrep:{tag})
- Rewrites the image reference in the workflow to {tag}@{digest} if changed

Outputs (to logs and GITHUB_OUTPUT if set):
- NEW_TAG
- NEW_DIGEST
- UPDATED ("true"/"false")
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Optional, Tuple

GITHUB_RELEASES_URL = "https://api.github.com/repos/semgrep/semgrep/releases/latest"
DOCKER_TAG_URL_TMPL = "https://hub.docker.com/v2/repositories/semgrep/semgrep/tags/{tag}"
WORKFLOW_PATH = ".github/workflows/ci.yml"


def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "elspeth-semgrep-pin-bot"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_latest_semgrep_tag() -> str:
    data = http_get_json(GITHUB_RELEASES_URL)
    tag = data.get("tag_name", "").strip()
    if not tag:
        raise RuntimeError("Failed to obtain latest semgrep release tag")
    # Normalize: prefer Docker tag without leading 'v'
    return tag[1:] if tag.startswith("v") else tag


def get_docker_digest(tag: str) -> str:
    data = http_get_json(DOCKER_TAG_URL_TMPL.format(tag=tag))
    digest = data.get("digest", "").strip()
    if not digest or not digest.startswith("sha256:"):
        raise RuntimeError(f"Failed to obtain digest for semgrep/semgrep:{tag}")
    return digest


def update_workflow_image_ref(path: str, new_tag: str, new_digest: str) -> Tuple[bool, str]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match existing image reference like: semgrep/semgrep:1.140.0@sha256:...
    pattern = re.compile(r"(semgrep/semgrep:)([^\s\\]+)")
    match = pattern.search(content)
    if not match:
        raise RuntimeError("Could not find semgrep image reference in workflow")

    current_spec = match.group(2)
    new_spec = f"{new_tag}@{new_digest}"
    if current_spec == new_spec:
        return False, current_spec

    updated = pattern.sub(rf"\1{new_spec}", content, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    return True, current_spec


def write_outputs(new_tag: str, new_digest: str, updated: bool) -> None:
    lines = [
        f"NEW_TAG={new_tag}",
        f"NEW_DIGEST={new_digest}",
        f"UPDATED={'true' if updated else 'false'}",
    ]

    # Log to stdout
    for line in lines:
        print(line)

    # Also write to GITHUB_OUTPUT if available
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")


def main() -> int:
    try:
        latest_tag = get_latest_semgrep_tag()
        digest = get_docker_digest(latest_tag)
        updated, prev_spec = update_workflow_image_ref(WORKFLOW_PATH, latest_tag, digest)
        write_outputs(latest_tag, digest, updated)
        if updated:
            print(f"Updated semgrep image: {prev_spec} -> {latest_tag}@{digest}")
        else:
            print("Semgrep image already up-to-date.")
        return 0
    except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

