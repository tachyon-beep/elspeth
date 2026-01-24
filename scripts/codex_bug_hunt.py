#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from tqdm.asyncio import tqdm as async_tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

    # Fallback for when tqdm not installed
    class async_tqdm:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            self.total = kwargs.get("total", 0)
            self.desc = kwargs.get("desc", "")
            self.n = 0

        def update(self, n: int = 1) -> None:
            self.n += n
            if self.total > 0:
                pct = (self.n / self.total) * 100
                print(f"\r{self.desc}: {self.n}/{self.total} ({pct:.1f}%)", end="", file=sys.stderr)

        def close(self) -> None:
            if self.total > 0:
                print(file=sys.stderr)


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


# Directories and file patterns to exclude from scanning
_EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".tox",
    ".nox",
    ".hypothesis",
    "node_modules",
    ".venv",
    "venv",
    ".eggs",
    "htmlcov",
    ".coverage",
}

_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def _is_cache_path(path: Path) -> bool:
    """Check if path is a cache file or inside a cache directory."""
    # Check if any parent directory is an excluded directory
    for part in path.parts:
        if part in _EXCLUDE_DIRS:
            return True
        # Handle *.egg-info directories
        if part.endswith(".egg-info"):
            return True
    # Check file suffix
    return path.suffix in _EXCLUDE_SUFFIXES


def _is_python_file(path: Path) -> bool:
    """Check if path is a Python source file (not test)."""
    return path.suffix == ".py" and not path.name.startswith("test_")


def _build_prompt(file_path: Path, template: str, context: str) -> str:
    return (
        "You are a static analysis agent doing a deep bug audit.\n"
        f"Target file: {file_path}\n\n"
        "Instructions:\n"
        "- Use the bug report template below verbatim.\n"
        "- Fill in every section. If unknown, write 'Unknown'.\n"
        "- You may read any repo file to confirm integration behavior. Prefer\n"
        "  verification over speculation.\n"
        "- Report bugs only if the primary fix belongs in the target file.\n"
        "  If the root cause is in another file, do not report it unless the\n"
        "  severity is P0. If you report a P0 outside the target file, explain\n"
        "  why and cite the true root-cause file.\n"
        "- Integration issues can reference other files for evidence, but the\n"
        "  actionable fix must be in the target file (unless P0 as above).\n"
        "- If you find multiple distinct bugs, output one full template per bug,\n"
        "  separated by a line with only '---'.\n"
        "- If you find no credible bug, output one template with Summary set to\n"
        f"  'No concrete bug found in {file_path}', Severity 'trivial', Priority 'P3',\n"
        "  and Root Cause Hypothesis 'No bug identified'.\n"
        "- Evidence should cite file paths and line numbers when possible.\n\n"
        "Repository context (read-only):\n"
        f"{context}\n\n"
        "Bug report template:\n"
        f"{template}\n"
    )


class RateLimiter:
    """Simple token bucket rate limiter for API calls."""

    def __init__(self, rate: int, per_seconds: float):
        self.rate = rate
        self.per_seconds = per_seconds
        self.tokens = float(rate)
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            # Add tokens based on time elapsed
            self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / self.per_seconds))
            self.updated_at = now

            if self.tokens < 1:
                # Need to wait for a token
                sleep_time = (1 - self.tokens) * (self.per_seconds / self.rate)
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1


async def _run_codex_with_retry(
    *,
    file_path: Path,
    output_path: Path,
    model: str | None,
    prompt: str,
    repo_root: Path,
    log_path: Path,
    log_lock: asyncio.Lock,
    file_display: str,
    output_display: str,
    rate_limiter: RateLimiter | None,
    max_retries: int = 3,
) -> None:
    """Run codex with retry logic and rate limiting."""
    if rate_limiter:
        await rate_limiter.acquire()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()
    status = "ok"
    note = ""
    gated_count = 0

    cmd = [
        "codex",
        "exec",
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "--output-last-message",
        str(output_path),
    ]
    if model is not None:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    for attempt in range(max_retries):
        try:
            process = await asyncio.create_subprocess_exec(*cmd, cwd=repo_root)
            return_code = await process.wait()
            if return_code != 0:
                raise RuntimeError(f"codex exec failed for {file_path} with code {return_code}")

            gated_count = _apply_evidence_gate(output_path)
            if gated_count > 0:
                note = f"evidence_gate={gated_count}"

            # Success - break out of retry loop
            break

        except Exception as exc:
            if attempt < max_retries - 1:
                # Wait with exponential backoff before retry
                wait_time = (2**attempt) * 2  # 2s, 4s, 8s
                await asyncio.sleep(wait_time)
                note = f"retry_{attempt + 1}"
            else:
                # Final attempt failed
                status = "failed"
                note = str(exc)
                raise

    # Only reached if we broke out of loop successfully
    duration_s = time.monotonic() - start_time
    await _append_log(
        log_path=log_path,
        log_lock=log_lock,
        timestamp=_utc_now(),
        status=status,
        file_display=file_display,
        output_display=output_display,
        model=model or "",
        duration_s=duration_s,
        note=note,
    )


def _chunked(paths: list[Path], size: int) -> list[list[Path]]:
    return [paths[i : i + size] for i in range(0, len(paths), size)]


async def _run_batches(
    *,
    files: list[Path],
    output_dir: Path,
    model: str | None,
    prompt_template: str,
    repo_root: Path,
    skip_existing: bool,
    batch_size: int,
    root_dir: Path,
    log_path: Path,
    context: str,
    rate_limit: int | None,
    organize_by_priority: bool,
) -> dict[str, int]:
    """Run analysis in batches. Returns statistics."""
    log_lock = asyncio.Lock()
    failed_files: list[tuple[Path, Exception]] = []

    # Setup rate limiter if requested
    rate_limiter = RateLimiter(rate=rate_limit, per_seconds=60.0) if rate_limit else None

    # Progress bar
    pbar = async_tqdm(total=len(files), desc="Analyzing files", unit="file")

    for batch in _chunked(files, batch_size):
        tasks: list[asyncio.Task[None]] = []
        batch_files: list[Path] = []

        for file_path in batch:
            relative = file_path.relative_to(root_dir)
            output_path = output_dir / relative
            output_path = output_path.with_suffix(output_path.suffix + ".md")

            if skip_existing and output_path.exists():
                pbar.update(1)
                continue

            prompt = _build_prompt(file_path, prompt_template, context)
            batch_files.append(file_path)
            tasks.append(
                asyncio.create_task(
                    _run_codex_with_retry(
                        file_path=file_path,
                        output_path=output_path,
                        model=model,
                        prompt=prompt,
                        repo_root=repo_root,
                        log_path=log_path,
                        log_lock=log_lock,
                        file_display=str(file_path.relative_to(repo_root).as_posix()),
                        output_display=str(output_path.relative_to(repo_root).as_posix()),
                        rate_limiter=rate_limiter,
                    )
                )
            )

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for file_path, result in zip(batch_files, results, strict=False):
                if isinstance(result, Exception):
                    failed_files.append((file_path, result))
                pbar.update(1)

    pbar.close()

    # Report failures
    if failed_files:
        print(f"\n⚠️  {len(failed_files)} files failed:", file=sys.stderr)
        for path, exc in failed_files[:10]:
            print(f"  {path.relative_to(repo_root)}: {exc}", file=sys.stderr)
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more (see {log_path})", file=sys.stderr)

    # Organize outputs by priority if requested
    if organize_by_priority:
        _organize_by_priority(output_dir)

    # Generate summary statistics
    return _generate_summary(output_dir)


def _ensure_log_file(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists() and log_path.stat().st_size > 0:
        return
    header = (
        "# Codex Bug Hunt Log\n\n"
        "| Timestamp (UTC) | Status | File | Output | Model | Duration_s | Note |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
    )
    log_path.write_text(header, encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "\\n").replace("\r", "")


def _load_context(repo_root: Path, extra_files: list[str] | None = None) -> str:
    """Load context from CLAUDE.md, ARCHITECTURE.md, and optional extra files."""
    parts = []

    # Core context files
    for filename in ["CLAUDE.md", "ARCHITECTURE.md"]:
        path = repo_root / filename
        if path.exists():
            parts.append(f"--- {filename} ---\n{path.read_text(encoding='utf-8')}")

    # Optional additional context
    if extra_files:
        for filename in extra_files:
            path = repo_root / filename
            if path.exists():
                parts.append(f"--- {filename} ---\n{path.read_text(encoding='utf-8')}")
            else:
                print(f"Warning: Context file not found: {filename}", file=sys.stderr)

    return "\n\n".join(parts)


def _extract_section(report: str, heading: str) -> str:
    lines = report.splitlines()
    in_section = False
    collected: list[str] = []
    for line in lines:
        if line.strip().startswith("## "):
            if in_section:
                break
            if line.strip() == f"## {heading}":
                in_section = True
                continue
        if in_section:
            collected.append(line)
    return "\n".join(collected).strip()


def _replace_section(report: str, heading: str, new_lines: list[str]) -> str:
    lines = report.splitlines()
    out: list[str] = []
    in_target = False
    for line in lines:
        if line.strip().startswith("## "):
            if in_target:
                in_target = False
            if line.strip() == f"## {heading}":
                out.append(line)
                out.extend(new_lines)
                in_target = True
                continue
        if in_target:
            continue
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _has_file_line_evidence(evidence: str) -> bool:
    """Check if evidence contains file:line citations."""
    patterns = [
        r"\b[\w./-]+\.[\w]+:\d+\b",  # file.py:123
        r"\b[\w./-]+#L\d+\b",  # file.py#L123
        r"\bline\s+\d+\b",  # line 123
        r"\b[\w./-]+\(line\s+\d+\)",  # file.py (line 123)
        r"\bat\s+[\w./-]+\.[\w]+:\d+",  # at file.py:123
        r"\bin\s+[\w./-]+\.[\w]+:\d+",  # in file.py:123
        r"```[a-z]*\n[\w./-]+\.[\w]+:\d+",  # code blocks with file:line
    ]
    return any(re.search(pattern, evidence, re.IGNORECASE) for pattern in patterns)


def _evidence_quality_score(evidence: str) -> int:
    """Score evidence quality 0-3 based on specificity."""
    score = 0
    if _has_file_line_evidence(evidence):
        score += 1
    if re.search(r"```python", evidence, re.IGNORECASE):
        score += 1  # Has code example
    if len(evidence) > 100:
        score += 1  # Detailed explanation
    return score


def _apply_evidence_gate(output_path: Path) -> int:
    """Apply evidence gate: downgrade reports without file:line citations."""
    text = output_path.read_text(encoding="utf-8")
    reports: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            reports.append("\n".join(current).strip())
            current = []
            continue
        current.append(line)
    if current:
        reports.append("\n".join(current).strip())

    gated_count = 0
    new_reports: list[str] = []
    for report in reports:
        if not report.strip():
            continue

        evidence = _extract_section(report, "Evidence")
        quality = _evidence_quality_score(evidence)

        # Quality-based downgrading
        if quality == 0:
            # No evidence at all - downgrade to P3/trivial
            gated_count += 1
            report = _replace_section(
                report,
                "Summary",
                ["", "- Needs verification: missing file/line evidence."],
            )
            report = _replace_section(
                report,
                "Severity",
                ["", "- Severity: trivial", "- Priority: P3"],
            )
            report = _replace_section(
                report,
                "Root Cause Hypothesis",
                ["", "- Unverified; no file/line evidence provided."],
            )
            report = _replace_section(
                report,
                "Evidence",
                ["", "- No file/line evidence provided."],
            )
        elif quality == 1:
            # Minimal evidence - downgrade to P2/minor
            gated_count += 1
            severity = _extract_section(report, "Severity")
            # Only downgrade if currently P0 or P1
            if "P0" in severity or "P1" in severity:
                report = _replace_section(
                    report,
                    "Severity",
                    ["", "- Severity: minor", "- Priority: P2 (downgraded: minimal evidence)"],
                )
        # quality >= 2: keep original

        new_reports.append(report.strip())

    new_text = "\n---\n".join(new_reports).rstrip() + "\n"
    if new_text != text:
        output_path.write_text(new_text, encoding="utf-8")

    return gated_count


def _priority_from_report(text: str) -> str:
    """Extract priority level from report text."""
    if match := re.search(r"Priority:\s*(P\d)", text, re.IGNORECASE):
        return match.group(1).upper()
    return "unknown"


def _organize_by_priority(output_dir: Path) -> None:
    """Organize outputs into by-priority/ subdirectories."""
    by_priority_dir = output_dir / "by-priority"

    for md_file in output_dir.rglob("*.md"):
        # Skip files already in by-priority
        if "by-priority" in md_file.parts:
            continue

        text = md_file.read_text(encoding="utf-8")
        priority = _priority_from_report(text)

        # Copy to priority subdirectory
        dest_dir = by_priority_dir / priority
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / md_file.name
        shutil.copy2(md_file, dest_path)


def _generate_summary(output_dir: Path) -> dict[str, int]:
    """Parse all outputs and count bugs by priority."""
    stats: Counter[str] = Counter()

    for md_file in output_dir.rglob("*.md"):
        # Skip by-priority copies to avoid double-counting
        if "by-priority" in md_file.parts:
            continue

        text = md_file.read_text(encoding="utf-8")

        if "No concrete bug found" in text:
            stats["no_bug"] += 1
        else:
            priority = _priority_from_report(text)
            stats[priority] += 1

    return dict(stats)


def _print_summary(stats: dict[str, int]) -> None:
    """Print formatted summary statistics."""
    print("\n" + "=" * 60)
    print("📊 Analysis Summary")
    print("=" * 60)

    total_bugs = sum(v for k, v in stats.items() if k != "no_bug")

    if total_bugs > 0:
        print(f"\n🐛 Bugs Found: {total_bugs}")
        for priority in ["P0", "P1", "P2", "P3"]:
            count = stats.get(priority, 0)
            if count > 0:
                bar = "█" * min(count, 40)
                print(f"  {priority}: {count:3d} {bar}")

    no_bug_count = stats.get("no_bug", 0)
    if no_bug_count > 0:
        print(f"\n✅ Clean Files: {no_bug_count}")

    unknown = stats.get("unknown", 0)
    if unknown > 0:
        print(f"\n❓ Unknown Priority: {unknown}")

    print("=" * 60 + "\n")


def _paths_from_file(path_file: Path, repo_root: Path, root_dir: Path) -> list[Path]:
    selected: list[Path] = []
    lines = path_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        raw_path = Path(stripped)
        path = raw_path if raw_path.is_absolute() else (repo_root / raw_path).resolve()
        if not path.exists():
            raise RuntimeError(f"paths-from entry does not exist: {raw_path}")
        if path.is_dir():
            selected.extend([p for p in path.rglob("*") if p.is_file() and not _is_cache_path(p)])
        else:
            if not _is_cache_path(path):
                selected.append(path)
    return [path for path in selected if _is_under_root(path, root_dir)]


def _is_under_root(path: Path, root_dir: Path) -> bool:
    try:
        path.relative_to(root_dir)
        return True
    except ValueError:
        return False


def _changed_files_since(repo_root: Path, root_dir: Path, git_ref: str) -> list[Path]:
    try:
        root_rel = root_dir.relative_to(repo_root)
    except ValueError:
        root_rel = root_dir
    cmd = ["git", "diff", "--name-only", git_ref, "--", str(root_rel)]
    result = subprocess.run(cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    selected = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = (repo_root / rel).resolve()
        if path.is_file() and _is_under_root(path, root_dir) and not _is_cache_path(path):
            selected.append(path)
    return selected


def _list_files(
    *,
    root_dir: Path,
    repo_root: Path,
    changed_since: str | None,
    paths_from: Path | None,
    file_type: str,
) -> list[Path]:
    selected: set[Path] | None = None

    if changed_since:
        changed = set(_changed_files_since(repo_root, root_dir, changed_since))
        selected = changed if selected is None else selected & changed

    if paths_from:
        listed = set(_paths_from_file(paths_from, repo_root, root_dir))
        selected = listed if selected is None else selected & listed

    if selected is None:
        selected = {path for path in root_dir.rglob("*") if path.is_file() and not _is_cache_path(path)}

    # Apply file type filter
    if file_type == "python":
        selected = {p for p in selected if _is_python_file(p)}

    return sorted(selected)


async def _append_log(
    *,
    log_path: Path,
    log_lock: asyncio.Lock,
    timestamp: str,
    status: str,
    file_display: str,
    output_display: str,
    model: str,
    duration_s: float,
    note: str,
) -> None:
    line = (
        f"| {_escape_cell(timestamp)} | {_escape_cell(status)} | "
        f"{_escape_cell(file_display)} | {_escape_cell(output_display)} | "
        f"{_escape_cell(model)} | {duration_s:.2f} | {_escape_cell(note)} |\n"
    )
    async with log_lock:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Codex bug audits per file in batches.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan all Python files in src/elspeth
  %(prog)s

  # Scan only changed files since HEAD~5
  %(prog)s --changed-since HEAD~5

  # Dry run to see what would be scanned
  %(prog)s --dry-run

  # Use rate limiting for API quota management
  %(prog)s --rate-limit 30

  # Organize outputs by priority
  %(prog)s --organize-by-priority
        """,
    )
    parser.add_argument(
        "--root",
        default="src/elspeth",
        help="Root directory to scan for files (default: src/elspeth).",
    )
    parser.add_argument(
        "--template",
        default="docs/bugs/BUGS.md",
        help="Bug report template path (default: docs/bugs/BUGS.md).",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/bugs/generated",
        help="Directory to write bug reports (default: docs/bugs/generated).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Maximum concurrent Codex runs per batch (default: 10).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override Codex model (passes --model to codex exec).",
    )
    parser.add_argument(
        "--changed-since",
        default=None,
        help="Only scan files changed since this git ref (e.g. HEAD~1).",
    )
    parser.add_argument(
        "--paths-from",
        default=None,
        help="Path to a file containing newline-separated paths to scan.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already have an output report.",
    )
    parser.add_argument(
        "--file-type",
        default="python",
        choices=["python", "all"],
        help="Filter by file type (default: python, excludes tests).",
    )
    parser.add_argument(
        "--context-files",
        nargs="+",
        default=None,
        help="Additional context files beyond CLAUDE.md/ARCHITECTURE.md.",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=None,
        help="Max requests per minute (e.g., 30 for API quota management).",
    )
    parser.add_argument(
        "--organize-by-priority",
        action="store_true",
        help="Organize outputs into by-priority/ subdirectories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would be scanned without running analysis.",
    )

    args = parser.parse_args()

    # Validation
    if args.batch_size < 1:
        raise ValueError("--batch-size must be >= 1")
    if args.rate_limit is not None and args.rate_limit < 1:
        raise ValueError("--rate-limit must be >= 1")

    if shutil.which("codex") is None:
        raise RuntimeError("codex CLI not found on PATH")

    repo_root = Path(__file__).resolve().parents[1]
    root_dir = _resolve_path(repo_root, args.root)
    template_path = _resolve_path(repo_root, args.template)
    output_dir = _resolve_path(repo_root, args.output_dir)
    log_path = _resolve_path(repo_root, "docs/bugs/process/CODEX_LOG.md")

    # List files to scan
    paths_from = _resolve_path(repo_root, args.paths_from) if args.paths_from else None
    files = _list_files(
        root_dir=root_dir,
        repo_root=repo_root,
        changed_since=args.changed_since,
        paths_from=paths_from,
        file_type=args.file_type,
    )

    if not files:
        print(f"No files found under {root_dir}", file=sys.stderr)
        return 1

    # Dry run mode
    if args.dry_run:
        print(f"Would analyze {len(files)} files:")
        for f in files[:20]:
            print(f"  {f.relative_to(repo_root)}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return 0

    # Load template and context
    template_text = template_path.read_text(encoding="utf-8")
    context_text = _load_context(repo_root, extra_files=args.context_files)
    _ensure_log_file(log_path)

    # Run analysis
    stats = asyncio.run(
        _run_batches(
            files=files,
            output_dir=output_dir,
            model=args.model,
            prompt_template=template_text,
            repo_root=repo_root,
            skip_existing=args.skip_existing,
            batch_size=args.batch_size,
            root_dir=root_dir,
            log_path=log_path,
            context=context_text,
            rate_limit=args.rate_limit,
            organize_by_priority=args.organize_by_priority,
        )
    )

    # Print summary
    _print_summary(stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
