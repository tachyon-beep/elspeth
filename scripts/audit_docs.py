#!/usr/bin/env python3
"""
Audit documentation files in the repository.

Outputs:
  - audit_data/docs_audit.json  (full records incl. content)
  - audit_data/docs_audit.csv   (metadata only)
  - audit_data/docs_audit_summary.md (human summary)

Documents scanned: .md, .mdx, .rst, .txt, .pdf
Directory excludes: .git, .venv, .tox, caches, outputs, logs, audit_data
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_EXTS = {".md", ".mdx", ".rst", ".txt", ".pdf", ".yml", ".yaml"}
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    ".tox",
    ".ruff_cache",
    ".mypy_cache",
    "coverage_html",
    "htmlcov",
    "logs",
    "runlogs",
    "outputs",
    "scorecard-artifacts",
    "audit_data",
    "gh_failed_logs",
}


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_birth_time(p: Path) -> float | None:
    # Try platform birthtime, else GNU stat %w, else None
    st = os.stat(p)
    bt = getattr(st, "st_birthtime", None)
    if isinstance(bt, (int, float)):
        return float(bt)
    return None


@dataclass
class DocRecord:
    path: str
    name: str
    ext: str
    size: int
    sha256: str
    access_time: str | None
    modify_time: str | None
    create_time: str | None
    binary: bool
    content: str | None


def iter_doc_paths(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in DOC_EXTS:
                yield p


def collect() -> list[DocRecord]:
    records: list[DocRecord] = []
    for p in sorted(iter_doc_paths(REPO_ROOT)):
        try:
            st = os.stat(p)
            mtime = iso(st.st_mtime)
            atime = iso(st.st_atime)
            ctime = iso(stat_birth_time(p))
            size = st.st_size
            ext = p.suffix.lower()
            digest = sha256_path(p)

            binary = ext == ".pdf"
            content: str | None
            if binary:
                content = None
            else:
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    # fallback to binary and base64; but mark as binary and drop content
                    binary = True
                    content = None

            records.append(
                DocRecord(
                    path=str(p.relative_to(REPO_ROOT)),
                    name=p.name,
                    ext=ext,
                    size=size,
                    sha256=digest,
                    access_time=atime,
                    modify_time=mtime,
                    create_time=ctime,
                    binary=binary,
                    content=content,
                )
            )
        except FileNotFoundError:
            # file disappeared during scan
            continue
    return records


def write_outputs(records: list[DocRecord]) -> None:
    out_dir = REPO_ROOT / "audit_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON (full)
    (out_dir / "docs_audit.json").write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # CSV (metadata)
    with (out_dir / "docs_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "path",
            "name",
            "ext",
            "size",
            "sha256",
            "access_time",
            "modify_time",
            "create_time",
            "binary",
        ])
        for r in records:
            w.writerow([
                r.path,
                r.name,
                r.ext,
                r.size,
                r.sha256,
                r.access_time or "",
                r.modify_time or "",
                r.create_time or "",
                str(r.binary).lower(),
            ])

    # Summary
    by_ext: dict[str, int] = {}
    total_size = 0
    for r in records:
        by_ext[r.ext] = by_ext.get(r.ext, 0) + 1
        total_size += r.size
    top_10 = sorted(records, key=lambda r: r.size, reverse=True)[:10]
    oldest = min(records, key=lambda r: r.modify_time or "9999") if records else None
    newest = max(records, key=lambda r: r.modify_time or "") if records else None

    lines = []
    lines.append("# Docs Audit Summary")
    lines.append("")
    lines.append(f"Total documents: {len(records)}")
    lines.append(f"Total size: {total_size} bytes")
    lines.append("")
    lines.append("Counts by extension:")
    for ext, count in sorted(by_ext.items()):
        lines.append(f"- {ext}: {count}")
    lines.append("")
    if oldest:
        lines.append("Oldest by modify time:")
        lines.append(f"- {oldest.path} — {oldest.modify_time}")
    if newest:
        lines.append("Newest by modify time:")
        lines.append(f"- {newest.path} — {newest.modify_time}")
    lines.append("")
    lines.append("Top 10 largest:")
    for r in top_10:
        lines.append(f"- {r.path} — {r.size} bytes")

    (out_dir / "docs_audit_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    records = collect()
    write_outputs(records)
    print(f"Wrote {len(records)} records to audit_data/docs_audit.json and audit_data/docs_audit.csv")


if __name__ == "__main__":
    main()
