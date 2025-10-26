#!/usr/bin/env python3
r"""Fixture dependency analysis script for Phase 1.

Analyzes fixture definitions and usage across test suite to inform migration strategy.

Usage:
    python analyze_fixtures.py \\
        --test-dir tests \\
        --output FIXTURE_ANALYSIS.md

Outputs:
    - Fixture definitions (location, scope)
    - Fixture usage (which tests use which fixtures)
    - Dependency graph (fixtures depending on other fixtures)
    - Migration recommendations
"""

import argparse
import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FixtureDefinition:
    """Metadata for a fixture definition."""

    name: str
    file_path: str
    scope: str  # "function", "class", "module", "session"
    depends_on: list[str]  # Other fixtures this depends on
    line_number: int


@dataclass
class FixtureUsage:
    """Metadata for fixture usage in a test."""

    fixture_name: str
    test_file: str
    test_function: str
    line_number: int


class FixtureAnalyzer:
    """Analyze fixture definitions and usage."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.definitions: list[FixtureDefinition] = []
        self.usages: list[FixtureUsage] = []

    def analyze_file(self, file_path: Path) -> None:
        """Analyze fixtures in a single file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"WARNING: Could not parse {file_path}: {e}", file=sys.stderr)
            return

        rel_path = str(file_path.relative_to(self.test_dir.parent))

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check if this is a fixture
                is_fixture = False
                fixture_scope = "function"  # default

                for decorator in node.decorator_list:
                    # @pytest.fixture or @fixture
                    if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                        is_fixture = True
                    elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                        is_fixture = True
                    # @pytest.fixture(scope="session")
                    elif isinstance(decorator, ast.Call):
                        func = decorator.func
                        if (isinstance(func, ast.Name) and func.id == "fixture") or (
                            isinstance(func, ast.Attribute) and func.attr == "fixture"
                        ):
                            is_fixture = True
                            # Extract scope
                            for keyword in decorator.keywords:
                                if keyword.arg == "scope":
                                    if isinstance(keyword.value, ast.Constant) and isinstance(
                                        keyword.value.value, str
                                    ):
                                        fixture_scope = keyword.value.value

                if is_fixture:
                    # Get fixture dependencies (params)
                    depends_on = [arg.arg for arg in node.args.args if arg.arg not in ("self", "cls", "request")]

                    self.definitions.append(
                        FixtureDefinition(
                            name=node.name,
                            file_path=rel_path,
                            scope=fixture_scope,
                            depends_on=depends_on,
                            line_number=node.lineno,
                        )
                    )

                # Check if this is a test function using fixtures
                elif node.name.startswith("test_"):
                    # Extract fixture usage from function parameters
                    for arg in node.args.args:
                        if arg.arg not in ("self", "cls"):
                            self.usages.append(
                                FixtureUsage(
                                    fixture_name=arg.arg,
                                    test_file=rel_path,
                                    test_function=node.name,
                                    line_number=node.lineno,
                                )
                            )

    def analyze_all(self) -> None:
        """Analyze all test files."""
        test_files = sorted(self.test_dir.rglob("*.py"))
        print(f"Analyzing {len(test_files)} files for fixtures...")

        for file_path in test_files:
            self.analyze_file(file_path)

        print(f"Found {len(self.definitions)} fixture definitions and {len(self.usages)} fixture usages")

    def generate_markdown_report(self, output_path: Path) -> None:
        """Generate markdown fixture analysis report."""
        lines = ["# Fixture Analysis Report\n"]
        lines.append(f"**Test Directory**: {self.test_dir}\n")
        lines.append(f"**Total Fixtures**: {len(self.definitions)}\n")
        lines.append(f"**Total Usages**: {len(self.usages)}\n")
        lines.append("---\n")

        # Summary by scope
        scope_counts: defaultdict[str, int] = defaultdict(int)
        for fixture in self.definitions:
            scope_counts[fixture.scope] += 1

        lines.append("## Fixtures by Scope\n")
        for scope in ["session", "module", "class", "function"]:
            count = scope_counts.get(scope, 0)
            lines.append(f"- **{scope}**: {count}\n")
        lines.append("\n---\n")

        # Fixtures by file
        file_counts: defaultdict[str, int] = defaultdict(int)
        for fixture in self.definitions:
            file_counts[fixture.file_path] += 1

        lines.append("## Files with Most Fixtures\n")
        lines.append("| File | Fixture Count |\n")
        lines.append("|------|---------------|\n")
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        for file_path, count in sorted_files:
            lines.append(f"| {file_path} | {count} |\n")
        lines.append("\n---\n")

        # Most used fixtures
        usage_counts: defaultdict[str, int] = defaultdict(int)
        for usage in self.usages:
            usage_counts[usage.fixture_name] += 1

        lines.append("## Most Used Fixtures (Top 30)\n")
        lines.append("| Fixture | Usage Count | Definition |\n")
        lines.append("|---------|-------------|------------|\n")
        sorted_usages = sorted(usage_counts.items(), key=lambda x: x[1], reverse=True)[:30]

        for fixture_name, count in sorted_usages:
            # Find definition
            definition = next((f for f in self.definitions if f.name == fixture_name), None)
            def_loc = definition.file_path if definition else "Unknown"
            lines.append(f"| {fixture_name} | {count} | {def_loc} |\n")
        lines.append("\n---\n")

        # Fixture dependency chains
        lines.append("## Fixture Dependencies\n")
        lines.append("Fixtures that depend on other fixtures:\n\n")

        for fixture in self.definitions:
            if fixture.depends_on:
                lines.append(f"### {fixture.name}\n")
                lines.append(f"**Location**: {fixture.file_path}:{fixture.line_number}\n")
                lines.append(f"**Scope**: {fixture.scope}\n")
                lines.append(f"**Depends on**: {', '.join(fixture.depends_on)}\n\n")

        lines.append("---\n")

        # Migration recommendations
        lines.append("## Migration Recommendations\n")

        # Session fixtures should be global
        session_fixtures = [f for f in self.definitions if f.scope == "session"]
        if session_fixtures:
            lines.append("### Session Fixtures (Global)\n")
            lines.append("These fixtures should be in `tests/fixtures/conftest.py` (accessible from all tests):\n\n")
            for fixture in session_fixtures:
                usage_count = usage_counts.get(fixture.name, 0)
                lines.append(f"- `{fixture.name}` ({fixture.file_path}) - Used {usage_count} times\n")
            lines.append("\n")

        # Module fixtures should be local
        module_fixtures = [f for f in self.definitions if f.scope == "module"]
        if module_fixtures:
            lines.append("### Module Fixtures (Local)\n")
            lines.append("These fixtures should remain in category-specific conftest.py:\n\n")
            for fixture in module_fixtures:
                usage_count = usage_counts.get(fixture.name, 0)
                lines.append(f"- `{fixture.name}` ({fixture.file_path}) - Used {usage_count} times\n")
            lines.append("\n")

        # ADR-002 specific fixtures
        adr002_fixtures = [f for f in self.definitions if "adr002" in f.file_path.lower()]
        if adr002_fixtures:
            lines.append("### ADR-002 Fixtures\n")
            lines.append("These fixtures should be in `tests/fixtures/adr002_test_helpers.py`:\n\n")
            for fixture in adr002_fixtures:
                usage_count = usage_counts.get(fixture.name, 0)
                lines.append(f"- `{fixture.name}` ({fixture.file_path}) - Used {usage_count} times\n")
            lines.append("\n")

        # Unused fixtures
        used_fixture_names = set(usage_counts.keys())
        defined_fixture_names = set(f.name for f in self.definitions)
        unused = defined_fixture_names - used_fixture_names

        if unused:
            lines.append("### Potentially Unused Fixtures\n")
            lines.append("These fixtures are defined but not found in test parameters (may be used indirectly):\n\n")
            for fixture_name in sorted(unused):
                fixture_def = next(f for f in self.definitions if f.name == fixture_name)
                lines.append(f"- `{fixture_name}` ({fixture_def.file_path})\n")
            lines.append("\n")

        lines.append("---\n")

        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(lines), encoding="utf-8")
        print(f"Report written to {output_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze test fixtures")
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Test directory to analyze (default: tests)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output report path",
    )

    args = parser.parse_args()

    # Validate
    if not args.test_dir.exists():
        print(f"ERROR: Test directory not found: {args.test_dir}", file=sys.stderr)
        return 1

    # Run analysis
    analyzer = FixtureAnalyzer(args.test_dir)
    analyzer.analyze_all()
    analyzer.generate_markdown_report(args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
