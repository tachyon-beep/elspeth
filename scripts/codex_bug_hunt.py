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
        "Bug Categories to Check:\n"
        "1. **Audit Trail Violations**:\n"
        "   - Missing payload recording for external API calls\n"
        "   - Incomplete state transitions (missing terminal states)\n"
        "   - Hash computation without payload persistence\n"
        "   - Token lineage breaks (missing parent_token_id)\n"
        "   - Silent data loss (rows disappearing without terminal state)\n"
        "\n"
        "2. **Data Tier Confusion** (CLAUDE.md Three-Tier Trust Model):\n"
        "   - Type coercion in transforms/sinks (only allowed in sources)\n"
        "   - Missing error handling on row operations (division, parsing, etc.)\n"
        "   - Bug-hiding patterns: .get(), getattr(), hasattr() for OUR code\n"
        "   - Defensive programming masking bugs in system-owned data\n"
        "   - Silent exceptions on internal state access\n"
        "\n"
        "3. **Protocol/Contract Violations**:\n"
        "   - Missing required hookimpl decorators or specs\n"
        "   - Schema mismatch (output_schema != actual output types)\n"
        "   - Plugin interface violations (wrong return types, missing methods)\n"
        "   - Config validation gaps (Pydantic validators not enforcing constraints)\n"
        "   - Breaking plugin contracts (e.g., stateless transforms with state)\n"
        "\n"
        "4. **State Management Issues**:\n"
        "   - Race conditions in async code\n"
        "   - Shared mutable state in stateless plugins\n"
        "   - Missing synchronization on concurrent access\n"
        "   - Incomplete cleanup in context managers\n"
        "   - Resource leaks (unclosed connections, files, locks)\n"
        "\n"
        "5. **Error Handling Gaps**:\n"
        "   - External calls without try/except (API, file I/O, network)\n"
        "   - Row operations without error handling (their data can fail)\n"
        "   - Missing quarantine on validation failures\n"
        "   - Silent failures (empty except blocks, catch-all handlers)\n"
        "   - Error messages without actionable context\n"
        "\n"
        "6. **Validation Gaps**:\n"
        "   - Source input not validated against schemas\n"
        "   - Missing type checks at trust boundaries\n"
        "   - No bounds checking on numeric inputs\n"
        "   - Unchecked assumptions about data structure\n"
        "   - Missing null/None checks on optional fields\n"
        "\n"
        "7. **Integration Issues**:\n"
        "   - Mismatched async/sync boundaries\n"
        "   - Incorrect context usage (missing required context fields)\n"
        "   - DAG edge compatibility issues (schema mismatches)\n"
        "   - Plugin registration gaps (missing entry points)\n"
        "   - Configuration precedence violations\n"
        "\n"
        "8. **Observability Blind Spots**:\n"
        "   - Missing span creation for long operations\n"
        "   - No structured logging on critical paths\n"
        "   - Metrics not recorded for quota/rate tracking\n"
        "   - Error context lost across boundaries\n"
        "   - Missing retry attempt tracking\n"
        "\n"
        "9. **Performance/Resource Issues**:\n"
        "   - O(n²) algorithms where O(n log n) possible\n"
        "   - Redundant database queries (missing caching)\n"
        "   - Memory leaks (growing unbounded collections)\n"
        "   - Blocking I/O in async contexts\n"
        "   - Missing batch processing for bulk operations\n"
        "\n"
        "10. **Architectural Deviations**:\n"
        "    - CLAUDE.md standard violations (check against repository context)\n"
        "    - Backwards compatibility code (prohibited - see CLAUDE.md)\n"
        "    - Legacy shims or deprecated adapters\n"
        "    - Plugin ownership violations (treating plugins as untrusted)\n"
        "    - Canonical JSON violations (NaN/Infinity not rejected)\n"
        "\n"
        "Analysis Depth Checklist:\n"
        "- [ ] Read CLAUDE.md sections relevant to this file's subsystem\n"
        "- [ ] Check plugin protocol compliance (hookspec signatures)\n"
        "- [ ] Verify schema contracts match implementation\n"
        "- [ ] Trace data flow for audit trail completeness\n"
        "- [ ] Check error paths for quarantine vs crash decisions\n"
        "- [ ] Validate integration tests exist for edge cases\n"
        "- [ ] Look for untested error conditions\n"
        "- [ ] Check for missing type annotations\n"
        "\n"
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
    bugs_open_dir: Path | None,
    deduplicate: bool,
    max_retries: int = 3,
) -> dict[str, int]:
    """Run codex with retry logic, deduplication, and rate limiting. Returns stats."""
    if rate_limiter:
        await rate_limiter.acquire()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()
    status = "ok"
    note = ""
    gated_count = 0
    merged_count = 0

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

            # Deduplicate against existing bugs if requested
            if deduplicate and bugs_open_dir and bugs_open_dir.exists():
                merged_count = _deduplicate_and_merge(output_path, bugs_open_dir, repo_root)
                if merged_count > 0:
                    note = f"merged={merged_count}"
                elif gated_count > 0:
                    note = f"evidence_gate={gated_count}"
            elif gated_count > 0:
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

    return {"gated": gated_count, "merged": merged_count}


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
    bugs_open_dir: Path | None,
    deduplicate: bool,
) -> dict[str, int]:
    """Run analysis in batches. Returns statistics."""
    log_lock = asyncio.Lock()
    failed_files: list[tuple[Path, Exception]] = []
    total_merged = 0
    total_gated = 0

    # Setup rate limiter if requested
    rate_limiter = RateLimiter(rate=rate_limit, per_seconds=60.0) if rate_limit else None

    # Progress bar
    pbar = async_tqdm(total=len(files), desc="Analyzing files", unit="file")

    for batch in _chunked(files, batch_size):
        tasks: list[asyncio.Task[dict[str, int]]] = []
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
                        bugs_open_dir=bugs_open_dir,
                        deduplicate=deduplicate,
                    )
                )
            )

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for file_path, result in zip(batch_files, results, strict=False):
                if isinstance(result, Exception):
                    failed_files.append((file_path, result))
                elif isinstance(result, dict):
                    total_merged += result.get("merged", 0)
                    total_gated += result.get("gated", 0)
                pbar.update(1)

    pbar.close()

    # Report failures
    if failed_files:
        print(f"\n⚠️  {len(failed_files)} files failed:", file=sys.stderr)
        for path, exc in failed_files[:10]:
            print(f"  {path.relative_to(repo_root)}: {exc}", file=sys.stderr)
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more (see {log_path})", file=sys.stderr)

    # Report deduplication stats
    if deduplicate and total_merged > 0:
        print(f"\n🔗 {total_merged} bugs merged into existing reports in docs/bugs/open/")

    # Organize outputs by priority if requested
    if organize_by_priority:
        _organize_by_priority(output_dir)

    # Generate summary statistics
    summary = _generate_summary(output_dir)
    summary["merged"] = total_merged
    summary["gated"] = total_gated
    return summary


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


def _extract_file_references(text: str) -> set[str]:
    """Extract all file paths referenced in the text."""
    patterns = [
        r"\b([\w./-]+/[\w./-]+\.py):\d+",  # path/to/file.py:123
        r"\b(src/[\w./-]+\.py)\b",  # src/path/file.py
        r"`([\w./-]+\.py)`",  # `file.py`
    ]
    files = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            files.add(match.group(1))
    return files


def _calculate_bug_similarity(report1: str, report2: str) -> float:
    """Calculate similarity score between two bug reports (0.0 to 1.0)."""
    # Extract key sections
    summary1 = _extract_section(report1, "Summary").lower()
    summary2 = _extract_section(report2, "Summary").lower()
    evidence1 = _extract_section(report1, "Evidence").lower()
    evidence2 = _extract_section(report2, "Evidence").lower()

    # Extract file references
    files1 = _extract_file_references(report1)
    files2 = _extract_file_references(report2)

    # Calculate file overlap
    if files1 and files2:
        file_overlap = len(files1 & files2) / len(files1 | files2)
    else:
        file_overlap = 0.0

    # Calculate text similarity (simple word overlap)
    def word_similarity(text1: str, text2: str) -> float:
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)

    summary_sim = word_similarity(summary1, summary2)
    evidence_sim = word_similarity(evidence1, evidence2)

    # Weighted average: files matter most, then summary, then evidence
    return 0.5 * file_overlap + 0.3 * summary_sim + 0.2 * evidence_sim


def _find_similar_bug(report: str, bugs_dir: Path, threshold: float = 0.6) -> Path | None:
    """Search for similar bug in docs/bugs/open/. Returns path if found."""
    if not bugs_dir.exists():
        return None

    # Extract target file from the report to narrow search
    target_files = _extract_file_references(report)
    if not target_files:
        return None

    best_match: tuple[Path, float] | None = None

    # Search all bug files in open/
    for bug_file in bugs_dir.rglob("*.md"):
        # Skip README files
        if bug_file.name == "README.md":
            continue

        existing_text = bug_file.read_text(encoding="utf-8")
        similarity = _calculate_bug_similarity(report, existing_text)

        if similarity >= threshold and (best_match is None or similarity > best_match[1]):
            best_match = (bug_file, similarity)

    return best_match[0] if best_match else None


def _merge_bug_reports(existing_path: Path, new_report: str, repo_root: Path) -> str:
    """Merge new analysis into existing bug report. Returns log message."""
    existing_text = existing_path.read_text(encoding="utf-8")

    # Extract sections from new report
    new_evidence = _extract_section(new_report, "Evidence")
    new_root_cause = _extract_section(new_report, "Root Cause Hypothesis")

    # Add a verification section with the new analysis
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
    verification_section = (
        f"\n\n---\n\n## Re-verification ({timestamp})\n\n"
        f"**Status: RE-ANALYZED**\n\n"
        f"### New Analysis\n\n"
        f"Re-ran static analysis on {timestamp}. Key findings:\n\n"
        f"**Evidence:**\n{new_evidence}\n\n"
        f"**Root Cause:**\n{new_root_cause}\n"
    )

    # Append to existing bug
    updated_text = existing_text.rstrip() + verification_section
    existing_path.write_text(updated_text, encoding="utf-8")

    rel_path = existing_path.relative_to(repo_root) if repo_root else existing_path
    return f"Updated existing bug: {rel_path}"


def _deduplicate_and_merge(
    output_path: Path,
    bugs_open_dir: Path,
    repo_root: Path,
    similarity_threshold: float = 0.6,
) -> int:
    """
    Check generated reports against docs/bugs/open/ and merge duplicates.
    Returns count of bugs merged into existing reports.
    """
    if not output_path.exists():
        return 0

    text = output_path.read_text(encoding="utf-8")
    reports = []
    current = []
    for line in text.splitlines():
        if line.strip() == "---":
            reports.append("\n".join(current).strip())
            current = []
            continue
        current.append(line)
    if current:
        reports.append("\n".join(current).strip())

    merged_count = 0
    kept_reports = []

    for report in reports:
        if not report.strip():
            continue

        # Check if this is a "no bug found" report
        summary = _extract_section(report, "Summary")
        if "no concrete bug found" in summary.lower():
            continue  # Don't keep these

        # Look for similar existing bug
        similar_bug = _find_similar_bug(report, bugs_open_dir, similarity_threshold)

        if similar_bug:
            # Merge into existing bug
            _merge_bug_reports(similar_bug, report, repo_root)
            merged_count += 1
        else:
            # Keep as new bug
            kept_reports.append(report)

    # Rewrite output with only new (non-duplicate) bugs
    if kept_reports:
        new_text = "\n---\n".join(kept_reports).rstrip() + "\n"
        output_path.write_text(new_text, encoding="utf-8")
    elif output_path.exists():
        # All bugs were duplicates or "no bug found" - remove the file
        output_path.unlink()

    return merged_count


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

    total_bugs = sum(v for k, v in stats.items() if k not in ["no_bug", "merged", "gated", "unknown"])

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

    merged = stats.get("merged", 0)
    if merged > 0:
        print(f"\n🔗 Merged into existing bugs: {merged}")

    gated = stats.get("gated", 0)
    if gated > 0:
        print(f"\n⚠️  Downgraded (evidence gate): {gated}")

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


def _changed_files_on_branch(repo_root: Path, root_dir: Path, base_branch: str) -> list[Path]:
    """Get files changed on current branch vs base branch using merge-base."""
    # Find merge base
    merge_base_cmd = ["git", "merge-base", base_branch, "HEAD"]
    result = subprocess.run(merge_base_cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git merge-base failed for {base_branch}")
    merge_base = result.stdout.strip()

    # Get diff from merge base to HEAD
    try:
        root_rel = root_dir.relative_to(repo_root)
    except ValueError:
        root_rel = root_dir
    cmd = ["git", "diff", "--name-only", f"{merge_base}..HEAD", "--", str(root_rel)]
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


def _changed_files_in_range(repo_root: Path, root_dir: Path, commit_range: str) -> list[Path]:
    """Get files changed in commit range (e.g., 'abc123..def456')."""
    # Validate range format
    if ".." not in commit_range:
        raise ValueError(f"Invalid commit range format: {commit_range}. Expected format: 'START..END'")

    # Get diff for the range
    try:
        root_rel = root_dir.relative_to(repo_root)
    except ValueError:
        root_rel = root_dir
    cmd = ["git", "diff", "--name-only", commit_range, "--", str(root_rel)]
    result = subprocess.run(cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed for range {commit_range}")

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
    branch: str | None,
    commit_range: str | None,
    paths_from: Path | None,
    file_type: str,
) -> list[Path]:
    # Check mutual exclusivity of git filters
    git_filters = [changed_since, branch, commit_range]
    active_filters = [f for f in git_filters if f is not None]
    if len(active_filters) > 1:
        raise ValueError("Only one of --changed-since, --branch, or --commit-range can be used at a time")

    selected: set[Path] | None = None

    if changed_since:
        changed = set(_changed_files_since(repo_root, root_dir, changed_since))
        selected = changed if selected is None else selected & changed

    if branch:
        changed = set(_changed_files_on_branch(repo_root, root_dir, branch))
        selected = changed if selected is None else selected & changed

    if commit_range:
        changed = set(_changed_files_in_range(repo_root, root_dir, commit_range))
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

  # Scan files changed on current branch vs main
  %(prog)s --branch main

  # Scan files changed in a specific commit range
  %(prog)s --commit-range abc123..def456

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
        "--branch",
        default=None,
        help="Compare against base branch to get files changed on current branch (e.g. 'main').",
    )
    parser.add_argument(
        "--commit-range",
        default=None,
        help="Only scan files changed in commit range (e.g. 'abc123..def456').",
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
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Check generated bugs against docs/bugs/open/ and merge duplicates.",
    )
    parser.add_argument(
        "--bugs-dir",
        default="docs/bugs/open",
        help="Directory to search for existing bugs (default: docs/bugs/open).",
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
    bugs_open_dir = _resolve_path(repo_root, args.bugs_dir) if args.deduplicate else None

    # List files to scan
    paths_from = _resolve_path(repo_root, args.paths_from) if args.paths_from else None
    files = _list_files(
        root_dir=root_dir,
        repo_root=repo_root,
        changed_since=args.changed_since,
        branch=args.branch,
        commit_range=args.commit_range,
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
            bugs_open_dir=bugs_open_dir,
            deduplicate=args.deduplicate,
        )
    )

    # Print summary
    _print_summary(stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
