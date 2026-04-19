"""CI scanner: any class defining to_audit_dict must inherit AuditEvidenceBase."""

from __future__ import annotations

import subprocess


def test_scanner_accepts_compliant_tree(tmp_path, monkeypatch) -> None:
    # Compliant tree: only AuditEvidenceBase subclasses define to_audit_dict.
    good = tmp_path / "good.py"
    good.write_text(
        "from elspeth.contracts.audit_evidence import AuditEvidenceBase\n"
        "class Ok(AuditEvidenceBase, RuntimeError):\n"
        "    def to_audit_dict(self): return {}\n"
    )
    result = subprocess.run(
        [".venv/bin/python", "scripts/cicd/enforce_audit_evidence_nominal.py", "check", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_scanner_flags_non_compliant_class(tmp_path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("class Mimic(RuntimeError):\n    def to_audit_dict(self): return {}\n")
    result = subprocess.run(
        [".venv/bin/python", "scripts/cicd/enforce_audit_evidence_nominal.py", "check", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "to_audit_dict" in result.stdout
    assert "Mimic" in result.stdout
