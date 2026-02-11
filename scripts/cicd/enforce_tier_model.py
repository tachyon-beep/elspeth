#!/usr/bin/env python3
"""
Tier Model Enforcement Tool

AST-based static analysis that detects defensive programming patterns that
violate the three-tier trust model and fails CI unless explicitly allowlisted.

Enforces ELSPETH's data manifesto (see CLAUDE.md):
- Tier 1 (Audit Database): Full trust - crash on any anomaly
- Tier 2 (Pipeline Data): Elevated trust - expect types, wrap operations on values
- Tier 3 (External Data): Zero trust - validate at boundary, coerce where possible

Usage:
    python scripts/cicd/enforce_tier_model.py check --root src
    python scripts/cicd/enforce_tier_model.py check --root src --allowlist config/cicd/enforce_tier_model
    python scripts/cicd/enforce_tier_model.py check --root src --allowlist config/cicd/enforce_tier_model.yaml
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# =============================================================================
# Data Structures
# =============================================================================


def _add_one_month(today: date) -> date:
    """Return a date one month after today, clamped to month length."""
    if today.month == 12:
        year = today.year + 1
        month = 1
    else:
        year = today.year
        month = today.month + 1
    day = min(today.day, monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class Finding:
    """A detected violation of the no-bug-hiding policy."""

    rule_id: str
    file_path: str
    line: int
    col: int
    symbol_context: tuple[str, ...]  # e.g., ("ClassName", "method_name")
    fingerprint: str
    code_snippet: str
    message: str

    @property
    def canonical_key(self) -> str:
        """Generate the canonical key for allowlist matching."""
        symbol_part = ":".join(self.symbol_context) if self.symbol_context else "_module_"
        return f"{self.file_path}:{self.rule_id}:{symbol_part}:fp={self.fingerprint}"

    def suggested_allowlist_entry(self) -> dict[str, Any]:
        """Generate a suggested allowlist entry for this finding."""
        today = datetime.now(UTC).date()
        return {
            "key": self.canonical_key,
            "owner": "<your-name>",
            "reason": "<explain why this is at a trust boundary>",
            "safety": "<explain how failures are handled>",
            "expires": _add_one_month(today).isoformat(),
        }


@dataclass
class AllowlistEntry:
    """A single allowlist entry permitting a specific finding."""

    key: str
    owner: str
    reason: str
    safety: str
    expires: date | None
    matched: bool = field(default=False, compare=False)
    source_file: str = field(default="", compare=False)


@dataclass
class PerFileRule:
    """A per-file rule that whitelists all patterns of specified rules for a file/directory."""

    pattern: str  # Glob pattern like "plugins/llm/*" or exact path like "mcp/server.py"
    rules: list[str]  # List of rule IDs like ["R1", "R4", "R6"]
    reason: str
    expires: date | None
    matched_count: int = field(default=0, compare=False)
    source_file: str = field(default="", compare=False)

    def matches(self, file_path: str, rule_id: str) -> bool:
        """Check if this per-file rule matches a finding."""
        import fnmatch

        if rule_id not in self.rules:
            return False
        # Match against file path (supports glob patterns)
        return fnmatch.fnmatch(file_path, self.pattern)


@dataclass
class Allowlist:
    """Parsed allowlist configuration."""

    entries: list[AllowlistEntry]
    per_file_rules: list[PerFileRule] = field(default_factory=list)
    fail_on_stale: bool = True
    fail_on_expired: bool = True

    def match(self, finding: Finding) -> AllowlistEntry | PerFileRule | None:
        """Check if a finding is covered by an allowlist entry or per-file rule.

        Per-file rules are checked first (more general), then specific entries.
        """
        # Check per-file rules first
        for rule in self.per_file_rules:
            if rule.matches(finding.file_path, finding.rule_id):
                rule.matched_count += 1
                return rule

        # Check specific entries
        for entry in self.entries:
            if entry.key == finding.canonical_key:
                entry.matched = True
                return entry
        return None

    def get_stale_entries(self) -> list[AllowlistEntry]:
        """Return entries that didn't match any finding."""
        return [e for e in self.entries if not e.matched]

    def get_expired_entries(self) -> list[AllowlistEntry]:
        """Return entries that have expired."""
        today = datetime.now(UTC).date()
        return [e for e in self.entries if e.expires and e.expires < today]

    def get_expired_file_rules(self) -> list[PerFileRule]:
        """Return per-file rules that have expired."""
        today = datetime.now(UTC).date()
        return [r for r in self.per_file_rules if r.expires and r.expires < today]

    def get_unused_file_rules(self) -> list[PerFileRule]:
        """Return per-file rules that didn't match any finding."""
        return [r for r in self.per_file_rules if r.matched_count == 0]


# =============================================================================
# Rule Definitions
# =============================================================================

RULES = {
    "R1": {
        "name": "dict.get",
        "description": "dict.get() usage can hide missing key bugs",
        "remediation": "Access dict keys directly (dict[key]) and fix the schema/contract if KeyError occurs",
    },
    "R2": {
        "name": "getattr",
        "description": "getattr() with default can hide missing attribute bugs",
        "remediation": "Access attributes directly (obj.attr) and fix the type/contract if AttributeError occurs",
    },
    "R3": {
        "name": "hasattr",
        "description": "hasattr() can hide missing attribute bugs by branching around them",
        "remediation": "Use protocols, enums, or fix the type contract instead of runtime attribute checking",
    },
    "R4": {
        "name": "broad-except",
        "description": "Broad exception handling can suppress bugs",
        "remediation": "Catch specific exceptions, or re-raise after logging/quarantining",
    },
    "R5": {
        "name": "isinstance",
        "description": "isinstance() checks can mask contract violations outside explicit trust boundaries",
        "remediation": "Validate at Tier-3 boundaries or rely on contracts; do not use isinstance to hide bugs",
    },
    "R6": {
        "name": "silent-except",
        "description": "Exception handling that swallows errors without re-raise or explicit error result",
        "remediation": "Raise the exception or return an explicit error/quarantine result",
    },
    "R7": {
        "name": "contextlib.suppress",
        "description": "contextlib.suppress() silently ignores exceptions",
        "remediation": "Handle exceptions explicitly or allow them to raise",
    },
    "R8": {
        "name": "dict.setdefault",
        "description": "dict.setdefault() hides missing-key bugs by mutating defaults",
        "remediation": "Access keys directly and fix the schema/contract if KeyError occurs",
    },
    "R9": {
        "name": "dict.pop-default",
        "description": "dict.pop(key, default) hides missing-key bugs with implicit defaults",
        "remediation": "Access keys directly and fix the schema/contract if KeyError occurs",
    },
}


# =============================================================================
# AST Visitor
# =============================================================================


class TierModelVisitor(ast.NodeVisitor):
    """AST visitor that detects bug-hiding patterns."""

    def __init__(self, file_path: str, source_lines: list[str]) -> None:
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: list[Finding] = []
        self.symbol_stack: list[str] = []
        self.path_stack: list[str] = []

    def _get_code_snippet(self, lineno: int) -> str:
        """Get the source line for a given line number."""
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return "<source unavailable>"

    def _fingerprint_node(self, rule_id: str, node: ast.AST) -> str:
        """Generate a stable fingerprint for a finding.

        The fingerprint is based on:
        - rule_id (ensures distinctness across rules)
        - AST path (field/index path from root, stable across formatting)
        - AST dump without line/column attributes
        """
        ast_path = "/".join(self.path_stack)
        node_dump = ast.dump(node, include_attributes=False, annotate_fields=True)
        payload = f"{rule_id}|{ast_path}|{node_dump}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _add_finding(self, rule_id: str, node: ast.expr | ast.stmt | ast.ExceptHandler, message: str) -> None:
        """Record a finding."""
        self.findings.append(
            Finding(
                rule_id=rule_id,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                symbol_context=tuple(self.symbol_stack),
                fingerprint=self._fingerprint_node(rule_id, node),
                code_snippet=self._get_code_snippet(node.lineno),
                message=message,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context."""
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function context."""
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function context."""
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def _is_default_return_value(self, value: ast.expr | None) -> bool:
        """True if return value is a silent default (None, empty container, empty string, zero)."""
        if value is None:
            return True
        if isinstance(value, ast.Constant):
            return value.value in (None, "", 0, 0.0, False)
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return len(value.elts) == 0
        if isinstance(value, ast.Dict):
            return len(value.keys) == 0
        return False

    def _handler_is_silent(self, node: ast.ExceptHandler) -> bool:
        """Return True if the except handler swallows errors without re-raise or explicit return."""
        has_raise = any(isinstance(child, ast.Raise) for child in ast.walk(node))
        if has_raise:
            return False

        returns: list[ast.Return] = [child for child in ast.walk(node) if isinstance(child, ast.Return)]
        if returns:
            # If all returns are silent defaults, treat as swallow.
            return all(self._is_default_return_value(ret.value) for ret in returns)

        # No raise, no return: likely swallow (even if logging).
        return True

    def visit_Call(self, node: ast.Call) -> None:
        """Detect R1 (dict.get), R2 (getattr), R3 (hasattr), R5 (isinstance), R8/R9 defaults."""
        # R1: dict.get() - Call(func=Attribute(attr="get"))
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            # This catches any .get() call - we can't know types statically
            # but dict.get() is the common bug-hiding case
            self._add_finding(
                "R1",
                node,
                f"Potential dict.get() usage: {self._get_code_snippet(node.lineno)}",
            )

        # R8: dict.setdefault() - mutating default on missing key
        if isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault":
            self._add_finding(
                "R8",
                node,
                f"dict.setdefault() hides missing keys: {self._get_code_snippet(node.lineno)}",
            )

        # R9: dict.pop(key, default) - implicit default on missing key
        if isinstance(node.func, ast.Attribute) and node.func.attr == "pop" and (len(node.args) >= 2 or node.keywords):
            self._add_finding(
                "R9",
                node,
                f"dict.pop() with default hides missing keys: {self._get_code_snippet(node.lineno)}",
            )

        # R2: getattr() - Call(func=Name("getattr"))
        # Only flag if there's a default argument (3 args)
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and (len(node.args) >= 3 or node.keywords):
            self._add_finding(
                "R2",
                node,
                f"getattr() with default hides AttributeError: {self._get_code_snippet(node.lineno)}",
            )

        # R3: hasattr() - Call(func=Name("hasattr"))
        if isinstance(node.func, ast.Name) and node.func.id == "hasattr":
            self._add_finding(
                "R3",
                node,
                f"hasattr() branches around missing attributes: {self._get_code_snippet(node.lineno)}",
            )

        # R5: isinstance() - runtime type checks can mask contract violations
        if isinstance(node.func, ast.Name) and node.func.id == "isinstance":
            self._add_finding(
                "R5",
                node,
                f"isinstance() used: {self._get_code_snippet(node.lineno)}",
            )

        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        """Detect R7: contextlib.suppress usage."""
        for item in node.items:
            ctx_expr = item.context_expr
            if isinstance(ctx_expr, ast.Call):
                func = ctx_expr.func
                if (isinstance(func, ast.Name) and func.id == "suppress") or (isinstance(func, ast.Attribute) and func.attr == "suppress"):
                    self._add_finding(
                        "R7",
                        node,
                        f"contextlib.suppress() used: {self._get_code_snippet(node.lineno)}",
                    )
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        """Detect R7: contextlib.suppress usage in async context managers."""
        for item in node.items:
            ctx_expr = item.context_expr
            if isinstance(ctx_expr, ast.Call):
                func = ctx_expr.func
                if (isinstance(func, ast.Name) and func.id == "suppress") or (isinstance(func, ast.Attribute) and func.attr == "suppress"):
                    self._add_finding(
                        "R7",
                        node,
                        f"contextlib.suppress() used: {self._get_code_snippet(node.lineno)}",
                    )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Detect R4: broad exception suppression."""
        # Check for bare except or except Exception
        is_broad = False
        if node.type is None:
            # bare except:
            is_broad = True
        elif isinstance(node.type, ast.Name) and node.type.id in (
            "Exception",
            "BaseException",
        ):
            is_broad = True
        elif isinstance(node.type, ast.Tuple):
            # except (Exception, ...):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name) and elt.id in (
                    "Exception",
                    "BaseException",
                ):
                    is_broad = True
                    break

        if is_broad:
            # Check if the handler re-raises
            has_reraise = False
            for child in ast.walk(node):
                if isinstance(child, ast.Raise):
                    has_reraise = True
                    break

            if not has_reraise:
                self._add_finding(
                    "R4",
                    node,
                    f"Broad exception caught without re-raise: {self._get_code_snippet(node.lineno)}",
                )

        # R6: specific exception swallowed without re-raise or explicit return
        if not is_broad and self._handler_is_silent(node):
            self._add_finding(
                "R6",
                node,
                f"Exception swallowed without re-raise or explicit error: {self._get_code_snippet(node.lineno)}",
            )

        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        """Visit a node, tracking AST path for stable fingerprints."""
        for field_name, value in ast.iter_fields(node):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        self.path_stack.append(f"{field_name}[{index}]")
                        self.visit(item)
                        self.path_stack.pop()
            elif isinstance(value, ast.AST):
                self.path_stack.append(field_name)
                self.visit(value)
                self.path_stack.pop()


# =============================================================================
# File Scanning
# =============================================================================


def scan_file(file_path: Path, root: Path) -> list[Finding]:
    """Scan a single Python file for bug-hiding patterns."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Could not read {file_path}: {e}", file=sys.stderr)
        return []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        print(f"Warning: Syntax error in {file_path}: {e}", file=sys.stderr)
        return []

    source_lines = source.splitlines()
    relative_path = str(file_path.relative_to(root))

    visitor = TierModelVisitor(relative_path, source_lines)
    visitor.visit(tree)
    return visitor.findings


def scan_directory(
    root: Path,
    exclude_patterns: list[str] | None = None,
) -> list[Finding]:
    """Scan all Python files in a directory tree."""
    exclude_patterns = exclude_patterns or []
    findings: list[Finding] = []

    for py_file in root.rglob("*.py"):
        # Check exclusions
        relative = py_file.relative_to(root)
        skip = False
        for pattern in exclude_patterns:
            if relative.match(pattern) or str(relative).startswith(pattern.rstrip("*/")):
                skip = True
                break
        if skip:
            continue

        findings.extend(scan_file(py_file, root))

    return findings


# =============================================================================
# Allowlist Handling
# =============================================================================


def _parse_allow_hits(data: dict[str, Any], source_file: str = "") -> list[AllowlistEntry]:
    """Parse allow_hits entries from a YAML data dict."""
    entries: list[AllowlistEntry] = []
    for item in data.get("allow_hits", []):
        expires_str = item.get("expires")
        expires_date = None
        if expires_str:
            try:
                expires_date = datetime.strptime(expires_str, "%Y-%m-%d").replace(tzinfo=UTC).date()
            except ValueError:
                print(
                    f"Warning: Invalid date format for expires: {expires_str}",
                    file=sys.stderr,
                )

        entries.append(
            AllowlistEntry(
                key=item["key"],
                owner=item.get("owner", "unknown"),
                reason=item.get("reason", ""),
                safety=item.get("safety", ""),
                expires=expires_date,
                source_file=source_file,
            )
        )
    return entries


def _parse_per_file_rules(data: dict[str, Any], source_file: str = "") -> list[PerFileRule]:
    """Parse per_file_rules entries from a YAML data dict."""
    per_file_rules: list[PerFileRule] = []
    for item in data.get("per_file_rules", []):
        expires_str = item.get("expires")
        expires_date = None
        if expires_str:
            try:
                expires_date = datetime.strptime(expires_str, "%Y-%m-%d").replace(tzinfo=UTC).date()
            except ValueError:
                print(
                    f"Warning: Invalid date format for per_file_rules expires: {expires_str}",
                    file=sys.stderr,
                )

        per_file_rules.append(
            PerFileRule(
                pattern=item["pattern"],
                rules=item.get("rules", []),
                reason=item.get("reason", ""),
                expires=expires_date,
                source_file=source_file,
            )
        )
    return per_file_rules


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Load and return a YAML file as a dict, exiting on parse error."""
    try:
        with path.open() as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in allowlist {path}: {e}", file=sys.stderr)
        sys.exit(1)


def load_allowlist_from_directory(directory: Path) -> Allowlist:
    """Load allowlist from a directory of per-module YAML files.

    Expected structure:
        directory/
            _defaults.yaml   — version and defaults section
            core.yaml         — per_file_rules + allow_hits for core/*
            plugins.yaml      — per_file_rules + allow_hits for plugins/*
            ...
    """
    # Load defaults
    defaults_path = directory / "_defaults.yaml"
    if defaults_path.exists():
        defaults_data = _load_yaml_file(defaults_path)
        defaults = defaults_data.get("defaults", {})
    else:
        defaults = {}

    # Glob all YAML files except _defaults.yaml, sorted by filename
    yaml_files = sorted(f for f in directory.glob("*.yaml") if f.name != "_defaults.yaml")

    all_entries: list[AllowlistEntry] = []
    all_per_file_rules: list[PerFileRule] = []

    for yaml_file in yaml_files:
        data = _load_yaml_file(yaml_file)
        all_entries.extend(_parse_allow_hits(data, source_file=yaml_file.name))
        all_per_file_rules.extend(_parse_per_file_rules(data, source_file=yaml_file.name))

    return Allowlist(
        entries=all_entries,
        per_file_rules=all_per_file_rules,
        fail_on_stale=defaults.get("fail_on_stale", True),
        fail_on_expired=defaults.get("fail_on_expired", True),
    )


def load_allowlist(path: Path) -> Allowlist:
    """Load and parse the allowlist from a YAML file or directory of YAML files."""
    if path.is_dir():
        return load_allowlist_from_directory(path)

    if not path.exists():
        return Allowlist(entries=[])

    data = _load_yaml_file(path)
    defaults = data.get("defaults", {})

    return Allowlist(
        entries=_parse_allow_hits(data),
        per_file_rules=_parse_per_file_rules(data),
        fail_on_stale=defaults.get("fail_on_stale", True),
        fail_on_expired=defaults.get("fail_on_expired", True),
    )


# =============================================================================
# Reporting
# =============================================================================


def _suggest_module_file(finding: Finding, allowlist_path: Path) -> str:
    """Suggest the appropriate module YAML file for a finding.

    Maps the finding's file path to the per-module YAML file name.
    Only meaningful when allowlist_path is a directory.
    """
    if not allowlist_path.is_dir():
        return str(allowlist_path)

    file_path = finding.file_path
    # Bare filenames (no /) like cli.py, cli_helpers.py → cli.yaml
    if "/" not in file_path:
        stem = file_path.removesuffix(".py")
        if stem.startswith("cli"):
            return str(allowlist_path / "cli.yaml")
        return str(allowlist_path / f"{stem}.yaml")

    # First path segment determines module file
    module = file_path.split("/", 1)[0]
    return str(allowlist_path / f"{module}.yaml")


def format_finding_text(finding: Finding) -> str:
    """Format a finding for text output."""
    rule = RULES.get(finding.rule_id, {})
    lines = [
        f"\n{finding.file_path}:{finding.line}:{finding.col}",
        f"  Rule: {finding.rule_id} - {rule.get('name', 'unknown')}",
        f"  Code: {finding.code_snippet}",
        f"  Context: {'.'.join(finding.symbol_context) if finding.symbol_context else '<module>'}",
        f"  Issue: {rule.get('description', finding.message)}",
        f"  Fix: {rule.get('remediation', 'Review and fix the underlying issue')}",
        f"  Allowlist key: {finding.canonical_key}",
    ]
    return "\n".join(lines)


def format_stale_entry_text(entry: AllowlistEntry) -> str:
    """Format a stale allowlist entry for text output."""
    base = f"\n  Key: {entry.key}\n  Owner: {entry.owner}\n  Reason: {entry.reason}"
    if entry.source_file:
        base += f"\n  Source: {entry.source_file}"
    return base


def format_expired_entry_text(entry: AllowlistEntry) -> str:
    """Format an expired allowlist entry for text output."""
    return f"\n  Key: {entry.key}\n  Owner: {entry.owner}\n  Expired: {entry.expires}"


def report_json(
    violations: list[Finding],
    stale_entries: list[AllowlistEntry],
    expired_entries: list[AllowlistEntry],
    expired_file_rules: list[PerFileRule] | None = None,
    unused_file_rules: list[PerFileRule] | None = None,
) -> str:
    """Generate JSON report."""
    result: dict[str, Any] = {
        "violations": [
            {
                "rule_id": f.rule_id,
                "file": f.file_path,
                "line": f.line,
                "col": f.col,
                "context": list(f.symbol_context),
                "fingerprint": f.fingerprint,
                "code": f.code_snippet,
                "message": f.message,
                "key": f.canonical_key,
            }
            for f in violations
        ],
        "stale_allowlist_entries": [{"key": e.key, "owner": e.owner, "reason": e.reason} for e in stale_entries],
        "expired_allowlist_entries": [{"key": e.key, "owner": e.owner, "expires": str(e.expires)} for e in expired_entries],
    }
    if expired_file_rules:
        result["expired_file_rules"] = [
            {"pattern": r.pattern, "rules": r.rules, "reason": r.reason, "expires": str(r.expires)} for r in expired_file_rules
        ]
    if unused_file_rules:
        result["unused_file_rules"] = [{"pattern": r.pattern, "rules": r.rules, "reason": r.reason} for r in unused_file_rules]
    return json.dumps(result, indent=2)


# =============================================================================
# CLI
# =============================================================================


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="No Bug-Hiding Enforcement Tool - detect defensive patterns that mask bugs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # check subcommand
    check_parser = subparsers.add_parser("check", help="Check for bug-hiding patterns")
    check_parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="Root directory to scan",
    )
    check_parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Path to allowlist YAML file or directory of YAML files",
    )
    check_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob patterns to exclude (can be specified multiple times)",
    )
    check_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    check_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Specific files to check (from pre-commit). If empty, scans --root directory.",
    )

    args = parser.parse_args()

    if args.command == "check":
        return run_check(args)

    return 0


def run_check(args: argparse.Namespace) -> int:
    """Run the check command."""
    root = args.root.resolve()

    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    # Load allowlist
    allowlist_path = args.allowlist
    if allowlist_path is None:
        # Default: prefer directory, fall back to single file
        repo_root = Path(__file__).parent.parent.parent
        dir_path = repo_root / "config" / "cicd" / "enforce_tier_model"
        file_path = repo_root / "config" / "cicd" / "enforce_tier_model.yaml"
        allowlist_path = dir_path if dir_path.is_dir() else file_path

    allowlist = load_allowlist(allowlist_path)

    # Scan for findings - either specific files or whole directory
    if args.files:
        # Pre-commit mode: only scan the provided files that are under root
        all_findings = []
        for file_path in args.files:
            resolved = file_path.resolve()
            # Only scan files that are under the root directory
            try:
                resolved.relative_to(root)
                all_findings.extend(scan_file(resolved, root))
            except ValueError:
                # File is not under root, skip it
                pass
    else:
        # Full directory scan mode
        all_findings = scan_directory(root, args.exclude)

    # Filter out allowlisted findings
    violations: list[Finding] = []
    for finding in all_findings:
        if allowlist.match(finding) is None:
            violations.append(finding)

    # Check for stale/expired allowlist entries (only in full-scan mode)
    # In file-specific mode (pre-commit), we only scan a subset of files,
    # so most allowlist entries won't match - that's expected, not stale.
    if args.files:
        stale_entries: list[AllowlistEntry] = []
        expired_entries: list[AllowlistEntry] = []
        expired_file_rules: list[PerFileRule] = []
        unused_file_rules: list[PerFileRule] = []
    else:
        stale_entries = allowlist.get_stale_entries() if allowlist.fail_on_stale else []
        expired_entries = allowlist.get_expired_entries() if allowlist.fail_on_expired else []
        expired_file_rules = allowlist.get_expired_file_rules() if allowlist.fail_on_expired else []
        unused_file_rules = allowlist.get_unused_file_rules() if allowlist.fail_on_stale else []

    # Report results
    # Include unused_file_rules in error condition - stale per-file rules should fail
    # the same way stale explicit entries do when fail_on_stale is enabled
    has_errors = bool(violations or stale_entries or expired_entries or expired_file_rules or unused_file_rules)

    if args.format == "json":
        print(report_json(violations, stale_entries, expired_entries, expired_file_rules, unused_file_rules))
    else:
        # Text format
        if violations:
            print(f"\n{'=' * 60}")
            print(f"VIOLATIONS FOUND: {len(violations)}")
            print("=" * 60)
            for v in violations:
                print(format_finding_text(v))

        if stale_entries:
            print(f"\n{'=' * 60}")
            print(f"STALE ALLOWLIST ENTRIES: {len(stale_entries)}")
            print("(These entries don't match any code - remove them)")
            print("=" * 60)
            for e in stale_entries:
                print(format_stale_entry_text(e))

        if expired_entries:
            print(f"\n{'=' * 60}")
            print(f"EXPIRED ALLOWLIST ENTRIES: {len(expired_entries)}")
            print("(These entries have passed their expiration date)")
            print("=" * 60)
            for e in expired_entries:
                print(format_expired_entry_text(e))

        if expired_file_rules:
            print(f"\n{'=' * 60}")
            print(f"EXPIRED PER-FILE RULES: {len(expired_file_rules)}")
            print("(These rules have passed their expiration date)")
            print("=" * 60)
            for r in expired_file_rules:
                print(f"\n  Pattern: {r.pattern}")
                print(f"  Rules: {r.rules}")
                print(f"  Reason: {r.reason}")
                print(f"  Expired: {r.expires}")

        if unused_file_rules:
            print(f"\n{'=' * 60}")
            print(f"UNUSED PER-FILE RULES: {len(unused_file_rules)}")
            print("(These rules didn't match any code - consider removing)")
            print("=" * 60)
            for r in unused_file_rules:
                print(f"\n  Pattern: {r.pattern}")
                print(f"  Rules: {r.rules}")
                print(f"  Reason: {r.reason}")

        if has_errors:
            print(f"\n{'=' * 60}")
            print("CHECK FAILED")
            print("=" * 60)
            if violations:
                target = _suggest_module_file(violations[0], allowlist_path)
                print(f"\nTo allowlist a violation, add an entry to {target}")
                print("Example entry:")
                if violations:
                    import pprint

                    pprint.pprint(violations[0].suggested_allowlist_entry())
        else:
            print("\nNo bug-hiding patterns detected. Check passed.")

    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
