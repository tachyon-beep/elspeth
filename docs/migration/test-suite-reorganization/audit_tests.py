#!/usr/bin/env python3
"""Test suite audit script for Phase 1 analysis.

Extracts metadata from all test files to inform reorganization decisions.

Usage:
    python scripts/audit_tests.py \\
        --test-dir tests \\
        --output docs/migration/test-suite-reorganization/TEST_AUDIT_REPORT.md \\
        --format markdown

Outputs:
    - File sizes, test counts, import dependencies
    - Fixture usage analysis
    - Duration estimates
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class TestFileMetadata:
    """Metadata for a single test file."""

    path: str
    size_bytes: int
    line_count: int
    test_function_count: int
    test_class_count: int
    fixture_count: int
    imports: list[str]
    fixtures_used: list[str]
    has_parametrize: bool
    has_slow_marker: bool


class TestAuditor:
    """Audit test files and extract metadata."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.metadata: list[TestFileMetadata] = []

    def audit_file(self, file_path: Path) -> TestFileMetadata:
        """Extract metadata from a single test file."""
        # Read file
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Parse AST
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            print(f"WARNING: Syntax error in {file_path}: {e}", file=sys.stderr)
            return TestFileMetadata(
                path=str(file_path.relative_to(self.test_dir.parent)),
                size_bytes=file_path.stat().st_size,
                line_count=len(lines),
                test_function_count=0,
                test_class_count=0,
                fixture_count=0,
                imports=[],
                fixtures_used=[],
                has_parametrize=False,
                has_slow_marker=False,
            )

        # Extract metadata
        test_functions = []
        test_classes = []
        fixtures = []
        imports = []
        fixtures_used = set()
        has_parametrize = False
        has_slow_marker = False

        for node in ast.walk(tree):
            # Test functions
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith("test_"):
                    test_functions.append(node.name)
                    # Check for fixture usage (function parameters)
                    for arg in node.args.args:
                        if arg.arg not in ("self", "cls"):
                            fixtures_used.add(arg.arg)
                # Fixtures
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                        fixtures.append(node.name)
                    elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                        fixtures.append(node.name)
                    elif isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Name) and decorator.func.id == "parametrize":
                            has_parametrize = True
                        elif isinstance(decorator.func, ast.Attribute):
                            if decorator.func.attr == "parametrize":
                                has_parametrize = True
                            elif decorator.func.attr == "slow":
                                has_slow_marker = True

            # Test classes
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("Test"):
                    test_classes.append(node.name)

            # Imports
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        return TestFileMetadata(
            path=str(file_path.relative_to(self.test_dir.parent)),
            size_bytes=file_path.stat().st_size,
            line_count=len(lines),
            test_function_count=len(test_functions),
            test_class_count=len(test_classes),
            fixture_count=len(fixtures),
            imports=sorted(set(imports)),
            fixtures_used=sorted(fixtures_used),
            has_parametrize=has_parametrize,
            has_slow_marker=has_slow_marker,
        )

    def audit_all(self) -> None:
        """Audit all test files in test directory."""
        test_files = sorted(self.test_dir.rglob("test_*.py"))
        print(f"Found {len(test_files)} test files to audit...")

        for file_path in test_files:
            metadata = self.audit_file(file_path)
            self.metadata.append(metadata)

        print(f"Audited {len(self.metadata)} test files.")

    def generate_markdown_report(self, output_path: Path) -> None:
        """Generate markdown audit report."""
        lines = ["# Test Suite Audit Report\n"]
        lines.append(f"**Generated**: {Path.cwd()}\n")
        lines.append(f"**Test Directory**: {self.test_dir}\n")
        lines.append(f"**Total Test Files**: {len(self.metadata)}\n")
        lines.append("---\n")

        # Summary statistics
        total_tests = sum(m.test_function_count for m in self.metadata)
        total_classes = sum(m.test_class_count for m in self.metadata)
        total_fixtures = sum(m.fixture_count for m in self.metadata)
        total_lines = sum(m.line_count for m in self.metadata)
        total_size = sum(m.size_bytes for m in self.metadata)
        parametrized_count = sum(1 for m in self.metadata if m.has_parametrize)
        slow_count = sum(1 for m in self.metadata if m.has_slow_marker)

        lines.append("## Summary Statistics\n")
        lines.append(f"- **Total test functions**: {total_tests}\n")
        lines.append(f"- **Total test classes**: {total_classes}\n")
        lines.append(f"- **Total fixtures**: {total_fixtures}\n")
        lines.append(f"- **Total lines of code**: {total_lines:,}\n")
        lines.append(f"- **Total size**: {total_size / 1024:.1f} KB\n")
        lines.append(f"- **Files with parametrize**: {parametrized_count}\n")
        lines.append(f"- **Files with slow marker**: {slow_count}\n")
        lines.append("\n---\n")

        # Largest files
        lines.append("## Largest Test Files (Top 20)\n")
        lines.append("| File | Lines | Tests | Size (KB) |\n")
        lines.append("|------|-------|-------|----------|\n")
        sorted_by_lines = sorted(self.metadata, key=lambda m: m.line_count, reverse=True)[:20]
        for meta in sorted_by_lines:
            lines.append(
                f"| {meta.path} | {meta.line_count} | {meta.test_function_count} | "
                f"{meta.size_bytes / 1024:.1f} |\n"
            )
        lines.append("\n---\n")

        # Files with most tests
        lines.append("## Files with Most Tests (Top 20)\n")
        lines.append("| File | Tests | Lines | Classes |\n")
        lines.append("|------|-------|-------|----------|\n")
        sorted_by_tests = sorted(self.metadata, key=lambda m: m.test_function_count, reverse=True)[:20]
        for meta in sorted_by_tests:
            lines.append(
                f"| {meta.path} | {meta.test_function_count} | {meta.line_count} | "
                f"{meta.test_class_count} |\n"
            )
        lines.append("\n---\n")

        # Most common imports
        import_counts = defaultdict(int)
        for meta in self.metadata:
            for imp in meta.imports:
                import_counts[imp] += 1

        lines.append("## Most Common Imports (Top 30)\n")
        lines.append("| Import | File Count |\n")
        lines.append("|--------|------------|\n")
        sorted_imports = sorted(import_counts.items(), key=lambda x: x[1], reverse=True)[:30]
        for imp, count in sorted_imports:
            lines.append(f"| {imp} | {count} |\n")
        lines.append("\n---\n")

        # Most used fixtures
        fixture_usage_counts = defaultdict(int)
        for meta in self.metadata:
            for fixture in meta.fixtures_used:
                fixture_usage_counts[fixture] += 1

        lines.append("## Most Used Fixtures (Top 30)\n")
        lines.append("| Fixture | Usage Count |\n")
        lines.append("|---------|-------------|\n")
        sorted_fixtures = sorted(fixture_usage_counts.items(), key=lambda x: x[1], reverse=True)[:30]
        for fixture, count in sorted_fixtures:
            lines.append(f"| {fixture} | {count} |\n")
        lines.append("\n---\n")

        # Files by directory
        dir_counts = defaultdict(lambda: {"files": 0, "tests": 0, "lines": 0})
        for meta in self.metadata:
            dir_path = str(Path(meta.path).parent)
            dir_counts[dir_path]["files"] += 1
            dir_counts[dir_path]["tests"] += meta.test_function_count
            dir_counts[dir_path]["lines"] += meta.line_count

        lines.append("## Test Files by Directory\n")
        lines.append("| Directory | Files | Tests | Lines |\n")
        lines.append("|-----------|-------|-------|-------|\n")
        sorted_dirs = sorted(dir_counts.items(), key=lambda x: x[1]["files"], reverse=True)
        for dir_path, counts in sorted_dirs:
            lines.append(
                f"| {dir_path} | {counts['files']} | {counts['tests']} | {counts['lines']} |\n"
            )
        lines.append("\n---\n")

        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(lines), encoding="utf-8")
        print(f"Report written to {output_path}")

    def generate_json_report(self, output_path: Path) -> None:
        """Generate JSON audit report."""
        data = {
            "test_dir": str(self.test_dir),
            "total_files": len(self.metadata),
            "files": [asdict(m) for m in self.metadata],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"JSON report written to {output_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Audit test suite files")
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Test directory to audit (default: tests)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output report path",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    # Validate test directory
    if not args.test_dir.exists():
        print(f"ERROR: Test directory not found: {args.test_dir}", file=sys.stderr)
        return 1

    # Run audit
    auditor = TestAuditor(args.test_dir)
    auditor.audit_all()

    # Generate report
    if args.format == "markdown":
        auditor.generate_markdown_report(args.output)
    elif args.format == "json":
        auditor.generate_json_report(args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
