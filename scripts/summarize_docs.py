#!/usr/bin/env python3
"""Generate a markdown catalog of documentation files with summaries and timestamps."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = REPO_ROOT / "audit_data" / "docs_audit.json"
OUTPUT_MD = REPO_ROOT / "audit_data" / "docs_catalog.md"


def load_records() -> list[dict[str, Any]]:
    data = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    # ensure deterministic order
    return sorted(data, key=lambda r: r["path"].lower())


def clean_line(line: str) -> str:
    line = line.strip()
    if line.startswith("#"):
        line = line.lstrip("#").strip()
    line = re.sub(r"^[-*]\s+", "", line)
    return line


def summarize_content(record: dict[str, Any]) -> str:
    if record.get("binary"):
        return "Binary document"
    content = record.get("content") or ""
    if not content:
        return "No textual content"

    lines = [clean_line(ln) for ln in content.splitlines()]
    # filter out boilerplate markers
    meaningful: list[str] = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("---"):
            continue
        if ln.lower().startswith("last updated"):
            continue
        meaningful.append(ln)
    if not meaningful:
        return "No textual content"

    first = meaningful[0]
    # If the first line is a yaml key like 'name:' use it directly
    # Otherwise grab first sentence.
    sentence_match = re.match(r"(.+?[.!?])\s", first + " ")
    if sentence_match:
        sentence = sentence_match.group(1).strip()
    else:
        sentence = first.strip()

    # Include second line if the first is too short (<20 chars)
    if len(sentence) < 20 and len(meaningful) > 1:
        sentence = (sentence + " " + meaningful[1]).strip()

    return sentence


def to_display(ts: str | None) -> str:
    return ts if ts else "—"


def build_markdown(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Documentation Catalog")
    lines.append("")
    lines.append("Path | Purpose | Modified (UTC) | Created (UTC) | Accessed (UTC)")
    lines.append(":-- | :-- | :-- | :-- | :--")

    for rec in records:
        path = rec["path"]
        purpose = summarize_content(rec)
        # escape pipe characters
        purpose = purpose.replace("|", "\\|")
        lines.append(
            f"{path} | {purpose} | {to_display(rec.get('modify_time'))} | "
            f"{to_display(rec.get('create_time'))} | {to_display(rec.get('access_time'))}"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    records = load_records()
    markdown = build_markdown(records)
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(markdown, encoding="utf-8")
    print(f"Wrote catalog with {len(records)} entries to {OUTPUT_MD}")


if __name__ == "__main__":
    main()

