"""Tests for scripts/cicd/enforce_contract_manifest.py.

Covers the four failure modes the scanner exists to catch:

- ``MC1`` extra-registration: a call site without a manifest entry.
- ``MC1`` unresolved: a registration whose contract name cannot be derived
  statically (the engineer used an indirect reference or non-class call).
- ``MC2`` missing-registration: a manifest entry with no call site.
- Manifest-shape failures: malformed frozenset literals crash cleanly.

Tests build a synthetic source tree in ``tmp_path`` so the scanner exercises
its real filesystem walk + AST parse + manifest-extract path.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from scripts.cicd.enforce_contract_manifest import (
    RULE_ID_EXTRA,
    RULE_ID_MISSING,
    Allowlist,
    AllowlistEntry,
    Finding,
    compute_findings,
    extract_manifest,
    scan_source_tree,
)

# ---------------------------------------------------------------------------
# Synthetic project-root factory
# ---------------------------------------------------------------------------


def _write_manifest(root: Path, members: list[str]) -> Path:
    """Write a declaration_contracts.py-style manifest file and return its path."""
    manifest_path = root / "declaration_contracts.py"
    members_repr = ", ".join(repr(m) for m in members)
    manifest_path.write_text(
        textwrap.dedent(
            f"""\
            from __future__ import annotations

            EXPECTED_CONTRACTS: frozenset[str] = frozenset({{{members_repr}}})
            """
        )
    )
    return manifest_path


def _write_registration(root: Path, filename: str, class_name: str, contract_name: str) -> Path:
    """Write a module that defines ``class_name`` with ``name=contract_name`` and registers it."""
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            f"""\
            from __future__ import annotations

            from declaration_contracts import register_declaration_contract


            class {class_name}:
                name = {contract_name!r}
                payload_schema = dict

                def applies_to(self, plugin):
                    return False

                def runtime_check(self, inputs, outputs):
                    pass

                @classmethod
                def negative_example(cls):
                    raise NotImplementedError


            register_declaration_contract({class_name}())
            """
        )
    )
    return path


# ---------------------------------------------------------------------------
# Manifest extraction
# ---------------------------------------------------------------------------


class TestManifestExtraction:
    """extract_manifest parses EXPECTED_CONTRACTS literally and records line numbers."""

    def test_single_entry_extracted(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["passes_through_input"])
        members, assign_line = extract_manifest(manifest)
        assert members == {"passes_through_input": 3}
        assert assign_line == 3

    def test_multiple_entries_extracted(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["a", "b", "c"])
        members, _ = extract_manifest(manifest)
        assert set(members.keys()) == {"a", "b", "c"}

    def test_tuple_form_accepted(self, tmp_path: Path) -> None:
        """``frozenset(("a", "b"))`` is equally valid."""
        manifest_path = tmp_path / "declaration_contracts.py"
        manifest_path.write_text('EXPECTED_CONTRACTS: frozenset[str] = frozenset(("a", "b"))\n')
        members, _ = extract_manifest(manifest_path)
        assert set(members.keys()) == {"a", "b"}

    def test_missing_symbol_exits(self, tmp_path: Path) -> None:
        """No EXPECTED_CONTRACTS symbol → fatal error."""
        manifest_path = tmp_path / "declaration_contracts.py"
        manifest_path.write_text("SOMETHING_ELSE = 1\n")
        with pytest.raises(SystemExit) as exc_info:
            extract_manifest(manifest_path)
        assert exc_info.value.code == 1

    def test_non_string_member_exits(self, tmp_path: Path) -> None:
        """A non-string literal in the frozenset is fatal."""
        manifest_path = tmp_path / "declaration_contracts.py"
        manifest_path.write_text("EXPECTED_CONTRACTS: frozenset = frozenset({'ok', 42})\n")
        with pytest.raises(SystemExit):
            extract_manifest(manifest_path)

    def test_duplicate_entry_exits(self, tmp_path: Path) -> None:
        """Two identical string literals in the set literal are caught."""
        manifest_path = tmp_path / "declaration_contracts.py"
        # Note: a Python set literal would deduplicate at runtime, but the AST
        # preserves both elements so the scanner can refuse ambiguous input.
        manifest_path.write_text("EXPECTED_CONTRACTS = frozenset({'dup', 'dup'})\n")
        with pytest.raises(SystemExit):
            extract_manifest(manifest_path)


# ---------------------------------------------------------------------------
# Scan + finding computation
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Manifest and registrations aligned → no findings."""

    def test_single_contract_no_findings(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["passes_through_input"])
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        members, assign_line = extract_manifest(manifest)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        assert findings == []


class TestMC1ExtraRegistration:
    """MC1: a register call whose contract name is absent from the manifest."""

    def test_extra_registered_contract_detected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["passes_through_input"])
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        _write_registration(
            tmp_path,
            "ghost.py",
            "GhostContract",
            "ghost_not_in_manifest",
        )
        members, assign_line = extract_manifest(manifest)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        assert len(findings) == 1
        assert findings[0].rule_id == RULE_ID_EXTRA
        assert findings[0].contract_name == "ghost_not_in_manifest"
        assert "ghost.py" in findings[0].file_path

    def test_unresolved_call_becomes_mc1(self, tmp_path: Path) -> None:
        """register_declaration_contract(variable) cannot resolve statically → MC1 unresolved."""
        manifest = _write_manifest(tmp_path, ["passes_through_input"])
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        (tmp_path / "indirect.py").write_text(
            textwrap.dedent(
                """\
                from declaration_contracts import register_declaration_contract


                def _build():
                    class _Hidden:
                        name = "hidden"
                        payload_schema = dict

                        def applies_to(self, plugin): return False
                        def runtime_check(self, inputs, outputs): pass

                        @classmethod
                        def negative_example(cls):
                            raise NotImplementedError
                    return _Hidden()


                _inst = _build()
                register_declaration_contract(_inst)
                """
            )
        )
        members, assign_line = extract_manifest(manifest)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        unresolved = [f for f in findings if f.rule_id == RULE_ID_EXTRA and "unresolved" in f.contract_name]
        assert len(unresolved) == 1, f"expected one unresolved finding, got {findings!r}"
        assert "indirect.py" in unresolved[0].file_path

    def test_class_without_name_attr_flagged(self, tmp_path: Path) -> None:
        """``register_declaration_contract(X())`` where X has no ``name = "..."`` → MC1 unresolved."""
        manifest = _write_manifest(tmp_path, ["passes_through_input"])
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        (tmp_path / "nameless.py").write_text(
            textwrap.dedent(
                """\
                from declaration_contracts import register_declaration_contract


                class Nameless:
                    pass


                register_declaration_contract(Nameless())
                """
            )
        )
        members, assign_line = extract_manifest(manifest)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        unresolved = [f for f in findings if "unresolved" in f.contract_name]
        assert len(unresolved) == 1


class TestMC2MissingRegistration:
    """MC2: a manifest entry with no corresponding call site."""

    def test_missing_registration_detected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["passes_through_input", "never_registered"])
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        members, assign_line = extract_manifest(manifest)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        assert len(findings) == 1
        assert findings[0].rule_id == RULE_ID_MISSING
        assert findings[0].contract_name == "never_registered"
        assert findings[0].file_path == "declaration_contracts.py"

    def test_empty_registry_yields_mc2_for_every_entry(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, ["a", "b", "c"])
        members, assign_line = extract_manifest(manifest)
        # No registration modules written — registrations is empty.
        registrations = scan_source_tree(tmp_path, tmp_path, manifest)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        assert {f.contract_name for f in findings} == {"a", "b", "c"}
        assert all(f.rule_id == RULE_ID_MISSING for f in findings)


class TestManifestFileIsSkipped:
    """The manifest file must not be scanned for registration call sites.

    The declaration_contracts module defines ``register_declaration_contract``
    itself. A naive scan could false-positive on the function *definition*.
    """

    def test_manifest_file_not_scanned(self, tmp_path: Path) -> None:
        # Write a manifest file that ALSO contains a fake register call, just
        # to confirm scan_source_tree skips it.
        manifest_path = tmp_path / "declaration_contracts.py"
        manifest_path.write_text(
            textwrap.dedent(
                """\
                from __future__ import annotations

                EXPECTED_CONTRACTS: frozenset[str] = frozenset({"passes_through_input"})


                class Bogus:
                    name = "bogus_in_manifest_file"


                # This call would create a false positive if the manifest file were scanned.
                register_declaration_contract(Bogus())
                """
            )
        )
        # Add a real registration elsewhere.
        _write_registration(
            tmp_path,
            "pass_through.py",
            "PassThroughContract",
            "passes_through_input",
        )
        members, assign_line = extract_manifest(manifest_path)
        registrations = scan_source_tree(tmp_path, tmp_path, manifest_path)
        findings = compute_findings(members, registrations, "declaration_contracts.py", assign_line)
        assert findings == [], f"expected no findings; got {findings!r}"


# ---------------------------------------------------------------------------
# Allowlist matching
# ---------------------------------------------------------------------------


class TestAllowlist:
    """Allowlist entries suppress findings by canonical_key."""

    def test_allowlist_suppresses_matching_finding(self) -> None:
        finding = Finding(
            rule_id=RULE_ID_EXTRA,
            file_path="pkg/ghost.py",
            line=10,
            contract_name="ghost_not_in_manifest",
            detail="",
        )
        entry = AllowlistEntry(
            key=finding.canonical_key,
            owner="test",
            reason="transitional",
            task="elspeth-xxx",
            expires=None,
        )
        allowlist = Allowlist(entries=[entry])
        matched = allowlist.match(finding)
        assert matched is entry
        assert entry.matched is True

    def test_allowlist_miss_returns_none(self) -> None:
        finding = Finding(
            rule_id=RULE_ID_EXTRA,
            file_path="pkg/ghost.py",
            line=10,
            contract_name="ghost_not_in_manifest",
            detail="",
        )
        allowlist = Allowlist(entries=[])
        assert allowlist.match(finding) is None


# ---------------------------------------------------------------------------
# Live-repo sanity check: the scanner passes on the actual codebase.
# ---------------------------------------------------------------------------


class TestLiveRepo:
    """The committed manifest and registrations are in sync."""

    def test_scanner_passes_on_live_repo(self) -> None:
        """End-to-end check — mirrors what CI runs.

        This is a VAL-style test: it exercises the scanner against the real
        source tree and manifest. If this fails in a PR, the scanner caught
        drift introduced by the PR.
        """
        repo_root = Path(__file__).resolve().parents[4]
        source_root = repo_root / "src" / "elspeth"
        manifest_file = repo_root / "src" / "elspeth" / "contracts" / "declaration_contracts.py"

        assert source_root.is_dir()
        assert manifest_file.is_file()

        members, assign_line = extract_manifest(manifest_file)
        registrations = scan_source_tree(source_root, repo_root, manifest_file)
        findings = compute_findings(
            members,
            registrations,
            str(manifest_file.relative_to(repo_root)),
            assign_line,
        )
        assert findings == [], f"Contract-manifest drift detected in the live repo. Findings: {findings!r}"
