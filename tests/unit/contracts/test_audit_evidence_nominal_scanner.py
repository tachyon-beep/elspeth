"""CI scanner: any class defining to_audit_dict must inherit AuditEvidenceBase."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the enforcer via sys.executable with cwd set to the project root.

    Mirrors the pattern in test_enforce_composer_exception_channel.py:17-35.
    Using sys.executable ensures the same interpreter as the test runner;
    setting cwd to the project root makes the script importable.
    """
    return subprocess.run(
        [
            sys.executable,
            "scripts/cicd/enforce_audit_evidence_nominal.py",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[3]),  # project root
    )


def test_scanner_accepts_compliant_tree(tmp_path: Path) -> None:
    # Compliant tree: only AuditEvidenceBase subclasses define to_audit_dict.
    good = tmp_path / "good.py"
    good.write_text(
        "from elspeth.contracts.audit_evidence import AuditEvidenceBase\n"
        "class Ok(AuditEvidenceBase, RuntimeError):\n"
        "    def to_audit_dict(self): return {}\n"
    )
    # Use an empty allowlist dir so stale-entry detection is a no-op in this
    # test (no entries to be stale), which lets fail_on_stale=true remain
    # honoured without false positives from the real allowlist files.
    allowlist_dir = tmp_path / "allowlist"
    allowlist_dir.mkdir()
    result = _run(["check", "--root", str(tmp_path), "--allowlist", str(allowlist_dir)])
    assert result.returncode == 0, result.stdout + result.stderr


def test_scanner_flags_non_compliant_class(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("class Mimic(RuntimeError):\n    def to_audit_dict(self): return {}\n")
    # Use an empty allowlist dir so stale-entry detection is a no-op in this
    # test (no entries to be stale), which lets fail_on_stale=true remain
    # honoured without false positives from the real allowlist files.
    allowlist_dir = tmp_path / "allowlist"
    allowlist_dir.mkdir()
    result = _run(["check", "--root", str(tmp_path), "--allowlist", str(allowlist_dir)])
    assert result.returncode != 0
    assert "to_audit_dict" in result.stdout
    assert "Mimic" in result.stdout
