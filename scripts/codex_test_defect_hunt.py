#!/usr/bin/env python3
"""Test quality defect scanner using Codex.

Scans test files for systematic quality issues like:
- Sleepy assertions (time.sleep in tests)
- Missing audit trail verification
- Fixture duplication
- Weak/incomplete assertions
- Missing property-based tests
- Misclassified tests
"""

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

from pyrate_limiter import Duration, Limiter, Rate
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from tqdm.asyncio import tqdm as async_tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

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


# === Constants ===
_MAX_RETRIES = 3
_RETRY_MIN_WAIT_S = 2
_RETRY_MAX_WAIT_S = 60
_RETRY_MULTIPLIER = 2
_STDERR_TRUNCATE_CHARS = 500


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


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
    for part in path.parts:
        if part in _EXCLUDE_DIRS:
            return True
        if part.endswith(".egg-info"):
            return True
    return path.suffix in _EXCLUDE_SUFFIXES


def _is_test_file(path: Path) -> bool:
    """Check if path is a test file."""
    return path.suffix == ".py" and path.name.startswith("test_")


def _build_test_quality_prompt(file_path: Path, template: str, context: str) -> str:
    return (
        "You are a test quality auditor analyzing test files for systematic defects.\n"
        f"Target file: {file_path}\n\n"
        "Instructions:\n"
        "- Use the test defect template below verbatim.\n"
        "- Fill in every section. If unknown, write 'Unknown'.\n"
        "- You MUST read the target test file completely before analyzing.\n"
        "- You SHOULD read the code under test to understand what's being tested.\n"
        "- You MAY read any other repo file to understand test context.\n"
        "- Report defects only if the primary fix belongs in the target test file.\n"
        "- If you find multiple distinct defects, output one full template per defect,\n"
        "  separated by a line with only '---'.\n"
        "- If you find no credible defect, output one template with Summary set to\n"
        f"  'No test defect found in {file_path}', Severity 'trivial', Priority 'P3',\n"
        "  and Root Cause Hypothesis 'No defect identified'.\n"
        "- Evidence MUST cite file paths and line numbers (e.g., 'tests/core/test_dag.py:123').\n"
        "- Evidence SHOULD include code snippets showing the actual defect.\n"
        "- Vague claims without evidence will be automatically downgraded to P3.\n\n"
        "Severity Guidelines:\n"
        "- P0 (Critical): Crashes, data corruption, security holes, missing audit trail recording\n"
        "- P1 (High): Flaky tests, missing edge cases for core logic, weak assertions on critical paths\n"
        "- P2 (Medium): Code quality issues, missing tests for error paths, fixture duplication\n"
        "- P3 (Low): Documentation, minor improvements, nice-to-have tests\n\n"
        "Test Quality Anti-Patterns to Check:\n"
        "\n"
        "1. **Sleepy Assertions**:\n"
        "   - Tests using time.sleep() for timing/synchronization\n"
        "   - Should mock time.monotonic() or use condition-based waits\n"
        "   - Causes flaky tests in slow CI environments\n"
        "   - Example: test waits 0.5s for aggregation timeout instead of mocking clock\n"
        "\n"
        "2. **Missing Audit Trail Verification** (CRITICAL for ELSPETH):\n"
        "   - Tests verify business logic but not Landscape recording\n"
        "   - SPECIFIC CHECKS REQUIRED:\n"
        "     a) node_states table: verify state, input_hash, output_hash, error fields\n"
        "     b) token_outcomes table: verify terminal_state matches expected (COMPLETED/ROUTED/QUARANTINED/etc.)\n"
        "     c) artifacts table: verify content_hash, payload_id, artifact_type\n"
        "     d) Hash integrity: verify hashes are deterministic and match canonical JSON\n"
        "     e) Lineage: verify parent_token_id, row_id relationships for forks/joins\n"
        "   - Missing verification that ALL operations are recorded (not just success paths)\n"
        "   - Missing verification of error recording in node_states.error field\n"
        "   - CLI/integration tests that don't query the audit database\n"
        "   - Tests that mock Landscape instead of verifying actual database writes\n"
        "\n"
        "3. **Fixture Duplication**:\n"
        "   - Same setup code repeated across 10+ test methods\n"
        "   - Inline class definitions (ListSource, CollectSink) duplicated\n"
        "   - Should use pytest fixtures or conftest.py\n"
        "   - 100+ lines of identical boilerplate per file\n"
        "\n"
        "4. **Weak/Incomplete Assertions**:\n"
        "   - Checking field exists without validating value (assert 'x' in obj)\n"
        "   - Vacuous assertions (assert len(rows) >= 0)\n"
        "   - Only checking success, not correctness\n"
        "   - Assertion-free tests (no assert statements)\n"
        "   - Substring matching on error messages instead of structured checks\n"
        "\n"
        "5. **Missing Tier 1 Corruption Tests** (CLAUDE.md: Three-Tier Trust Model):\n"
        "   - No tests verify crash on NULL in required fields\n"
        "   - No tests verify crash on invalid enum values\n"
        "   - No tests verify crash on wrong types in audit data\n"
        "   - No tests for checkpoint/Landscape data corruption\n"
        "   - Tier 1 'our data' must crash on anomalies, not coerce\n"
        "\n"
        "6. **Missing Property-Based Tests**:\n"
        "   - Hypothesis is in tech stack but unused\n"
        "   - Determinism claims without property tests (hash stability, ordering)\n"
        "   - Invariants tested with hand-written examples only\n"
        "   - Edge cases not systematically explored\n"
        "\n"
        "7. **Misclassified Tests**:\n"
        "   - Integration tests in unit test files (uses real DB, filesystem, plugins)\n"
        "   - Unit tests in integration test directories\n"
        "   - Contract tests that are really smoke tests\n"
        "   - Fuzz/property tests in regular test files (should be separate suite)\n"
        "\n"
        "8. **Bug-Hiding Defensive Patterns** (CLAUDE.md prohibition):\n"
        "   - Tests using hasattr(), isinstance(), .get() on system code\n"
        "   - Tests validating defensive patterns instead of letting bugs crash\n"
        "   - Protocol compliance checked at runtime instead of statically\n"
        "   - Example: if hasattr(plugin, 'close'): plugin.close() # WRONG\n"
        "\n"
        "9. **Missing Thread Safety Tests**:\n"
        "   - Code has locks/threading but no concurrency tests\n"
        "   - call_index, cache mutations, shared state untested under concurrent access\n"
        "   - Race conditions in audit trail recording\n"
        "\n"
        "10. **Infrastructure Gaps**:\n"
        "    - No shared fixtures for common setup\n"
        "    - No test data builders (magic numbers everywhere)\n"
        "    - No integration with actual database constraints\n"
        "    - Missing cleanup verification\n"
        "    - Tests accessing private attributes (_field) instead of public API\n"
        "\n"
        "11. **Missing Edge Cases**:\n"
        "    - No tests for NaN/Infinity rejection (CLAUDE.md requirement)\n"
        "    - No tests for empty inputs, None values, zero counts\n"
        "    - No tests for very large payloads\n"
        "    - No tests for Unicode/encoding issues\n"
        "    - No tests for error paths (exceptions, failures)\n"
        "\n"
        "12. **Incomplete Contract Coverage**:\n"
        "    - Plugin protocol methods untested\n"
        "    - Schema validation gaps\n"
        "    - Lifecycle hooks (on_start, on_complete, close) untested\n"
        "    - Error routing untested\n"
        "    - Batch-aware processing untested\n"
        "\n"
        "13. **Missing Recovery/Checkpoint Testing** (CRITICAL for ELSPETH):\n"
        "    - No tests verify checkpoint creation at correct intervals\n"
        "    - No tests verify recovery from checkpoint restores exact state\n"
        "    - No tests verify aggregation timeout age is preserved on resume\n"
        "    - No tests verify idempotency (running same data twice gives same result)\n"
        "    - No tests for checkpoint corruption detection\n"
        "    - No tests verify run_id, attempt counters after recovery\n"
        "    - Missing tests for partial batch recovery\n"
        "\n"
        "14. **Missing Negative Tests** (What Happens When Things Go Wrong?):\n"
        "    - No tests for database connection failures\n"
        "    - No tests for plugin exceptions during processing\n"
        "    - No tests for invalid configuration\n"
        "    - No tests for schema violations (wrong types, missing fields)\n"
        "    - No tests for external API failures (timeout, 500 errors, malformed responses)\n"
        "    - No tests for filesystem errors (disk full, permission denied)\n"
        "    - Missing quarantine verification (how are bad rows handled?)\n"
        "\n"
        "15. **Test Isolation Issues**:\n"
        "    - Tests depend on execution order (test_001, test_002 pattern)\n"
        "    - Tests share mutable state between test methods\n"
        "    - Tests leave database records that affect other tests\n"
        "    - Tests don't clean up created files/directories\n"
        "    - Tests use global singletons or class variables\n"
        "    - Integration tests don't use isolated database schemas/tables\n"
        "\n"
        "Analysis Depth Checklist:\n"
        "- [ ] Read CLAUDE.md sections on Auditability Standard and Three-Tier Trust Model\n"
        "- [ ] Read the target test file COMPLETELY before analyzing\n"
        "- [ ] Read the code under test to understand what SHOULD be tested\n"
        "- [ ] Check for sleepy assertions (time.sleep, asyncio.sleep in non-timeout tests)\n"
        "- [ ] Verify audit trail recording is tested with SPECIFIC checks (see anti-pattern #2)\n"
        "- [ ] Verify recovery/checkpoint testing exists (see anti-pattern #13)\n"
        "- [ ] Look for repeated setup code (fixture duplication)\n"
        "- [ ] Check assertion strength (presence vs correctness, vacuous assertions)\n"
        "- [ ] Verify Tier 1 corruption detection tests exist (crash on bad audit data)\n"
        "- [ ] Check if Hypothesis is used for property testing (it's in the tech stack)\n"
        "- [ ] Validate test classification (unit/integration/contract in correct directories)\n"
        "- [ ] Look for bug-hiding defensive patterns (hasattr, isinstance on system code)\n"
        "- [ ] Check for missing concurrency tests (locks, threading, race conditions)\n"
        "- [ ] Check for missing negative tests (what happens when things fail?)\n"
        "- [ ] Check for test isolation issues (execution order, shared state)\n"
        "- [ ] Provide SPECIFIC line numbers and code snippets in Evidence section\n"
        "\n"
        "Repository context (read-only):\n"
        f"{context}\n\n"
        "Test defect template:\n"
        f"{template}\n"
    )


async def _run_codex_once(
    *,
    file_path: Path,
    output_path: Path,
    model: str | None,
    prompt: str,
    repo_root: Path,
    file_display: str,
    output_display: str,
) -> None:
    """Run codex exec once. Raises on failure. Does not handle retries or logging."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    # Create subprocess with stdout/stderr capture for diagnostics
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=repo_root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _stdout, stderr = await process.communicate()

        if process.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace")
            # Truncate stderr for log readability
            if len(stderr_text) > _STDERR_TRUNCATE_CHARS:
                stderr_text = stderr_text[:_STDERR_TRUNCATE_CHARS] + "... (truncated)"

            raise RuntimeError(f"codex exec failed for {file_display} with code {process.returncode}\nstderr: {stderr_text}")

    finally:
        # Ensure subprocess cleanup if still running
        if process.returncode is None:
            process.terminate()
            await process.wait()


async def _run_codex_with_retry_and_logging(
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
    rate_limiter: Limiter | None,
) -> dict[str, int]:
    """Run codex with retry logic, rate limiting, evidence gate, and logging. Returns stats."""
    if rate_limiter:
        rate_limiter.try_acquire("codex_api")

    start_time = time.monotonic()
    status = "ok"
    note = ""
    gated_count = 0

    # Create retry decorator dynamically
    retry_decorator = retry(
        stop=stop_after_attempt(_MAX_RETRIES),
        wait=wait_exponential(multiplier=_RETRY_MULTIPLIER, min=_RETRY_MIN_WAIT_S, max=_RETRY_MAX_WAIT_S),
        retry=retry_if_exception_type((RuntimeError, asyncio.TimeoutError)),
        reraise=True,
    )

    try:
        # Apply retry decorator to the function call
        await retry_decorator(_run_codex_once)(
            file_path=file_path,
            output_path=output_path,
            model=model,
            prompt=prompt,
            repo_root=repo_root,
            file_display=file_display,
            output_display=output_display,
        )

        # Apply evidence gate after successful completion
        gated_count = _apply_evidence_gate(output_path)
        if gated_count > 0:
            note = f"evidence_gate={gated_count}"

    except Exception as exc:
        status = "failed"
        note = str(exc)[:200]  # Truncate long error messages
        raise

    finally:
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

    return {"gated": gated_count}


def _chunked(paths: list[Path], size: int) -> list[list[Path]]:
    """Split paths into chunks of at most `size` elements for batched processing."""
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
) -> dict[str, int]:
    """Run analysis in batches. Returns statistics."""
    log_lock = asyncio.Lock()
    failed_files: list[tuple[Path, Exception]] = []
    total_gated = 0

    # Use pyrate-limiter for rate limiting
    rate_limiter = Limiter(Rate(rate_limit, Duration.MINUTE)) if rate_limit else None
    pbar = async_tqdm(total=len(files), desc="Analyzing test files", unit="file")

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

            prompt = _build_test_quality_prompt(file_path, prompt_template, context)
            batch_files.append(file_path)
            tasks.append(
                asyncio.create_task(
                    _run_codex_with_retry_and_logging(
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
            for file_path, result in zip(batch_files, results, strict=True):
                if isinstance(result, Exception):
                    failed_files.append((file_path, result))
                elif isinstance(result, dict):
                    total_gated += result.get("gated", 0)
                pbar.update(1)

    pbar.close()

    if failed_files:
        print(f"\n⚠️  {len(failed_files)} files failed:", file=sys.stderr)
        for path, exc in failed_files[:10]:
            print(f"  {path.relative_to(repo_root)}: {exc}", file=sys.stderr)
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more (see {log_path})", file=sys.stderr)

    summary = _generate_summary(output_dir)
    summary["gated"] = total_gated
    return summary


def _ensure_log_file(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists() and log_path.stat().st_size > 0:
        return
    header = (
        "# Codex Test Defect Hunt Log\n\n"
        "| Timestamp (UTC) | Status | File | Output | Model | Duration_s | Note |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
    )
    log_path.write_text(header, encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "\\n").replace("\r", "")


def _load_context(repo_root: Path, extra_files: list[str] | None = None) -> str:
    """Load context from CLAUDE.md and optional extra files for agent prompts.

    Returns concatenated content of CLAUDE.md and any additional context files,
    separated by headers showing filename.
    """
    parts = []

    claude_md = repo_root / "CLAUDE.md"
    if claude_md.exists():
        parts.append(f"--- CLAUDE.md ---\n{claude_md.read_text(encoding='utf-8')}")

    if extra_files:
        for filename in extra_files:
            path = repo_root / filename
            if path.exists():
                parts.append(f"--- {filename} ---\n{path.read_text(encoding='utf-8')}")
            else:
                print(f"Warning: Context file not found: {filename}", file=sys.stderr)

    return "\n\n".join(parts)


def _extract_section(report: str, heading: str) -> str:
    """Extract content from a markdown section with the given heading.

    Returns the text between `## {heading}` and the next `##` heading.
    """
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
    """Replace content in a markdown section with the given heading.

    Keeps the heading line, replaces everything until the next heading with new_lines.
    """
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
    ]
    return any(re.search(pattern, evidence, re.IGNORECASE) for pattern in patterns)


def _evidence_quality_score(evidence: str) -> int:
    """Score evidence quality 0-3 based on specificity."""
    score = 0
    if _has_file_line_evidence(evidence):
        score += 1
    if re.search(r"```python", evidence, re.IGNORECASE):
        score += 1
    if len(evidence) > 100:
        score += 1
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

        if quality == 0:
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
        elif quality == 1:
            gated_count += 1
            severity = _extract_section(report, "Severity")
            # Use word boundaries to avoid false positives like "The P0 ticket"
            if re.search(r"\bP[01]\b", severity):
                report = _replace_section(
                    report,
                    "Severity",
                    ["", "- Severity: minor", "- Priority: P2 (downgraded: minimal evidence)"],
                )

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


def _generate_summary(output_dir: Path) -> dict[str, int]:
    """Parse all outputs and count defects by priority."""
    stats: Counter[str] = Counter()

    for md_file in output_dir.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")

        if "No test defect found" in text:
            stats["no_defect"] += 1
        else:
            priority = _priority_from_report(text)
            stats[priority] += 1

    return dict(stats)


def _write_run_metadata(
    *,
    output_dir: Path,
    repo_root: Path,
    start_time: str,
    end_time: str,
    duration_s: float,
    files_scanned: int,
    model: str | None,
    batch_size: int,
    rate_limit: int | None,
    git_commit: str,
) -> None:
    """Write run metadata file for triage tracking."""
    metadata_path = output_dir / "RUN_METADATA.md"
    content = f"""# Test Quality Audit Run Metadata

## Execution Details

- **Start Time (UTC):** {start_time}
- **End Time (UTC):** {end_time}
- **Duration:** {duration_s:.1f}s
- **Git Commit:** {git_commit}

## Scan Parameters

- **Files Scanned:** {files_scanned}
- **Model:** {model or "default (from codex config)"}
- **Batch Size:** {batch_size}
- **Rate Limit:** {rate_limit if rate_limit else "none"}

## Output Structure

```
{output_dir.relative_to(repo_root)}/
├── RUN_METADATA.md          # This file
├── SUMMARY.md               # Statistics and triage dashboard
├── FINDINGS_INDEX.md        # Table of all findings
├── <test-path>.py.md        # Individual finding reports
└── ...
```

## Triage Workflow

1. Review `SUMMARY.md` for overview
2. Triage high-priority findings first (P0, P1)
3. Use `FINDINGS_INDEX.md` to track triage status
4. Update individual finding files with triage decisions

---
Generated by: `scripts/codex_test_defect_hunt.py`
"""
    metadata_path.write_text(content, encoding="utf-8")


def _write_summary_file(
    *,
    output_dir: Path,
    stats: dict[str, int],
    total_files: int,
) -> None:
    """Write summary statistics file for triage dashboard."""
    summary_path = output_dir / "SUMMARY.md"

    total_defects = sum(v for k, v in stats.items() if k not in ["no_defect", "gated", "unknown"])
    no_defect_count = stats.get("no_defect", 0)
    gated = stats.get("gated", 0)
    unknown = stats.get("unknown", 0)

    # Build priority breakdown
    priority_lines = []
    for priority in ["P0", "P1", "P2", "P3"]:
        count = stats.get(priority, 0)
        if count > 0:
            bar = "█" * min(count, 40)
            priority_lines.append(f"- **{priority}**: {count:3d} {bar}")

    content = f"""# Test Quality Audit Summary

## Overview

| Metric | Count |
|--------|-------|
| **Total Files Scanned** | {total_files} |
| **Test Defects Found** | {total_defects} |
| **Clean Test Files** | {no_defect_count} |
| **Downgraded (Evidence Gate)** | {gated} |
| **Unknown Priority** | {unknown} |

## Priority Breakdown

{chr(10).join(priority_lines) if priority_lines else "No defects found."}

## Triage Status

- [ ] Review all P0 findings (critical)
- [ ] Review all P1 findings (high)
- [ ] Triage P2 findings (medium)
- [ ] Triage P3 findings (low)

## Next Steps

1. Open `FINDINGS_INDEX.md` to see all findings in table format
2. Start with P0/P1 findings
3. For each finding:
   - Review the evidence
   - Verify the defect is real (not hallucinated)
   - Create GitHub issue or fix immediately
   - Update finding file with triage decision

---
Last updated: {_utc_now()}
"""
    summary_path.write_text(content, encoding="utf-8")


def _write_findings_index(
    *,
    output_dir: Path,
    repo_root: Path,
) -> None:
    """Write findings index with table of all reports for easy triage."""
    findings: list[dict[str, str]] = []

    for md_file in sorted(output_dir.rglob("*.md")):
        # Skip metadata files
        if md_file.name in ["RUN_METADATA.md", "SUMMARY.md", "FINDINGS_INDEX.md"]:
            continue

        text = md_file.read_text(encoding="utf-8")

        # Extract summary (first non-heading line after ## Summary)
        summary = "No summary found"
        lines = text.splitlines()
        in_summary = False
        for line in lines:
            if line.strip() == "## Summary":
                in_summary = True
                continue
            if in_summary:
                if line.strip().startswith("## "):
                    break
                if line.strip() and not line.strip().startswith("-"):
                    summary = line.strip()[:100]  # Truncate long summaries
                    break

        # Extract priority
        priority = _priority_from_report(text)

        # Check if it's a "no defect" report
        is_clean = "No test defect found" in text

        findings.append(
            {
                "file": str(md_file.relative_to(output_dir)),
                "test_file": str(md_file.relative_to(output_dir).with_suffix("").with_suffix("")),
                "priority": priority if not is_clean else "clean",
                "summary": summary,
                "status": "pending",  # For manual triage updates
            }
        )

    # Sort by priority (P0 > P1 > P2 > P3 > clean)
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "unknown": 4, "clean": 5}
    findings.sort(key=lambda f: (priority_order.get(f["priority"], 99), f["test_file"]))

    # Build table
    index_path = output_dir / "FINDINGS_INDEX.md"
    content = f"""# Test Quality Findings Index

Total findings: {len(findings)}

## Triage Table

| Priority | Test File | Summary | Status | Report |
|----------|-----------|---------|--------|--------|
"""

    for finding in findings:
        # Skip "clean" reports for triage focus
        if finding["priority"] == "clean":
            continue

        content += (
            f"| {finding['priority']} | `{finding['test_file']}` | "
            f"{finding['summary']} | {finding['status']} | [{finding['file']}]({finding['file']}) |\n"
        )

    content += f"""

## Clean Test Files ({sum(1 for f in findings if f["priority"] == "clean")})

"""

    clean_files = [f for f in findings if f["priority"] == "clean"]
    if clean_files:
        content += "| Test File |\n|-----------|\n"
        for finding in clean_files:
            content += f"| `{finding['test_file']}` |\n"
    else:
        content += "_No clean test files found._\n"

    content += (
        """

## Triage Status Legend

- **pending**: Not yet reviewed
- **confirmed**: Defect verified, issue created
- **invalid**: False positive, not a real defect
- **duplicate**: Already tracked elsewhere
- **fixed**: Defect fixed

---
Last updated: """
        + _utc_now()
        + "\n"
    )

    index_path.write_text(content, encoding="utf-8")


def _print_summary(stats: dict[str, int]) -> None:
    """Print formatted summary statistics to stdout."""
    print("\n" + "=" * 60)
    print("📊 Test Quality Audit Summary")
    print("=" * 60)

    total_defects = sum(v for k, v in stats.items() if k not in ["no_defect", "gated", "unknown"])

    if total_defects > 0:
        print(f"\n🔍 Test Defects Found: {total_defects}")
        for priority in ["P0", "P1", "P2", "P3"]:
            count = stats.get(priority, 0)
            if count > 0:
                bar = "█" * min(count, 40)
                print(f"  {priority}: {count:3d} {bar}")

    no_defect_count = stats.get("no_defect", 0)
    if no_defect_count > 0:
        print(f"\n✅ Clean Test Files: {no_defect_count}")

    gated = stats.get("gated", 0)
    if gated > 0:
        print(f"\n⚠️  Downgraded (evidence gate): {gated}")

    unknown = stats.get("unknown", 0)
    if unknown > 0:
        print(f"\n❓ Unknown Priority: {unknown}")

    print("=" * 60 + "\n")


def _get_git_commit(repo_root: Path) -> str:
    """Get current git commit hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _list_test_files(
    *,
    root_dir: Path,
) -> list[Path]:
    """List all test files under root_dir."""
    selected = {path for path in root_dir.rglob("test_*.py") if path.is_file() and not _is_cache_path(path)}
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
        description="Run Codex test quality audits on test files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan all test files
  %(prog)s

  # Scan specific test directory
  %(prog)s --root tests/core

  # Dry run to see what would be scanned
  %(prog)s --dry-run

  # Use rate limiting
  %(prog)s --rate-limit 30
        """,
    )
    parser.add_argument(
        "--root",
        default="tests",
        help="Root directory to scan for test files (default: tests).",
    )
    parser.add_argument(
        "--template",
        default="docs/quality-audit/TEST_DEFECT_TEMPLATE.md",
        help="Test defect template path.",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/quality-audit/findings-codex",
        help="Directory to write defect reports.",
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
        "--skip-existing",
        action="store_true",
        help="Skip files that already have an output report.",
    )
    parser.add_argument(
        "--context-files",
        nargs="+",
        default=None,
        help="Additional context files beyond CLAUDE.md.",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=None,
        help="Max requests per minute (e.g., 30 for API quota management).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which files would be scanned without running analysis.",
    )

    args = parser.parse_args()

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
    log_path = _resolve_path(repo_root, "docs/quality-audit/TEST_DEFECT_LOG.md")

    # List test files
    files = _list_test_files(root_dir=root_dir)

    if not files:
        print(f"No test files found under {root_dir}", file=sys.stderr)
        return 1

    # Dry run mode
    if args.dry_run:
        print(f"Would analyze {len(files)} test files:")
        for f in files[:20]:
            print(f"  {f.relative_to(repo_root)}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        return 0

    # Get git commit for metadata
    git_commit = _get_git_commit(repo_root)

    # Load template and context
    template_text = template_path.read_text(encoding="utf-8")
    context_text = _load_context(repo_root, extra_files=args.context_files)
    _ensure_log_file(log_path)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track execution time
    start_time = _utc_now()
    start_monotonic = time.monotonic()

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
        )
    )

    # Track completion time
    end_time = _utc_now()
    duration_s = time.monotonic() - start_monotonic

    # Write structured output files for triage
    _write_run_metadata(
        output_dir=output_dir,
        repo_root=repo_root,
        start_time=start_time,
        end_time=end_time,
        duration_s=duration_s,
        files_scanned=len(files),
        model=args.model,
        batch_size=args.batch_size,
        rate_limit=args.rate_limit,
        git_commit=git_commit,
    )

    _write_summary_file(
        output_dir=output_dir,
        stats=stats,
        total_files=len(files),
    )

    _write_findings_index(
        output_dir=output_dir,
        repo_root=repo_root,
    )

    # Print summary to stdout for immediate feedback
    _print_summary(stats)

    # Tell user where to find the results
    print(f"📁 Detailed results written to: {output_dir.relative_to(repo_root)}/")
    print("   - RUN_METADATA.md: Run details and parameters")
    print("   - SUMMARY.md: Triage dashboard and statistics")
    print("   - FINDINGS_INDEX.md: Sortable table of all findings")
    print("   - TEST_DEFECT_LOG.md: Execution log")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
