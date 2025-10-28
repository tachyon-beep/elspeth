#!/usr/bin/env python3
r"""Duplicate test detection script for Phase 1 analysis.

Detects exact duplicates, functional duplicates, and overlapping test coverage.

Usage:
    python find_duplicates.py \
        --test-dir tests \
        --output DUPLICATES_ANALYSIS.md \
        --threshold 0.85

Outputs:
    - Exact duplicate test names
    - Functionally equivalent tests (same AST structure)
    - Tests with high code similarity
"""

import argparse
import ast
import difflib
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DuplicateGroup:
    """Group of duplicate/similar tests."""

    pattern: str  # "exact", "functional", "similar"
    similarity: float  # 0.0-1.0
    files: list[tuple[str, str]]  # [(file_path, function_name)]
    reason: str


class TestDeduplicator:
    """Detect duplicate and overlapping tests."""

    def __init__(self, test_dir: Path, threshold: float = 0.85):
        self.test_dir = test_dir
        self.threshold = threshold
        self.duplicates: list[DuplicateGroup] = []

    def get_function_ast(self, file_path: Path, func_name: str) -> ast.FunctionDef | None:
        """Extract AST for a specific function."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    return node
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"WARNING: Could not parse {file_path}: {e}", file=sys.stderr)

        return None

    def ast_to_string(self, node: ast.AST) -> str:
        """Convert AST to normalized string for comparison."""
        return ast.unparse(node)  # Available since Python 3.9

    def find_exact_duplicates(self) -> None:
        """Find tests with identical names across files."""
        test_names = defaultdict(list)

        for file_path in self.test_dir.rglob("test_*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(file_path))

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        rel_path = str(file_path.relative_to(self.test_dir.parent))
                        test_names[node.name].append((rel_path, node.name))
            except (SyntaxError, UnicodeDecodeError):
                continue

        # Find duplicates
        for test_name, occurrences in test_names.items():
            if len(occurrences) > 1:
                self.duplicates.append(
                    DuplicateGroup(
                        pattern="exact",
                        similarity=1.0,
                        files=occurrences,
                        reason=f"Test name '{test_name}' appears in {len(occurrences)} files",
                    )
                )

        print(f"Found {len([d for d in self.duplicates if d.pattern == 'exact'])} exact duplicate groups")

    def find_functional_duplicates(self) -> None:
        """Find tests with identical or very similar logic."""
        # Collect all test functions with their AST
        test_functions: dict[str, list[tuple[Path, str, str]]] = defaultdict(list)

        for file_path in self.test_dir.rglob("test_*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(file_path))

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        # Normalize AST (remove docstrings, comments)
                        ast_str = self.ast_to_string(node)
                        test_functions[ast_str].append((file_path, node.name, ast_str))
            except (SyntaxError, UnicodeDecodeError):
                continue

        # Find functional duplicates (same AST)
        for ast_str, occurrences in test_functions.items():
            if len(occurrences) > 1:
                files = [
                    (str(fp.relative_to(self.test_dir.parent)), fn) for fp, fn, _ in occurrences
                ]
                self.duplicates.append(
                    DuplicateGroup(
                        pattern="functional",
                        similarity=1.0,
                        files=files,
                        reason=f"Identical logic in {len(occurrences)} tests",
                    )
                )

        print(
            f"Found {len([d for d in self.duplicates if d.pattern == 'functional'])} "
            "functional duplicate groups"
        )

    def find_similar_tests(self) -> None:
        """Find tests with high code similarity (above threshold)."""
        # Collect all test functions with source code
        test_sources: list[tuple[Path, str, str]] = []

        for file_path in self.test_dir.rglob("test_*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(file_path))

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        func_source = ast.get_source_segment(content, node)
                        if func_source:
                            test_sources.append((file_path, node.name, func_source))
            except (SyntaxError, UnicodeDecodeError):
                continue

        # Compare pairs
        for i, (file1, name1, src1) in enumerate(test_sources):
            for file2, name2, src2 in test_sources[i + 1 :]:
                # Skip if same file
                if file1 == file2:
                    continue

                # Calculate similarity
                similarity = difflib.SequenceMatcher(None, src1, src2).ratio()

                if similarity >= self.threshold:
                    rel_path1 = str(file1.relative_to(self.test_dir.parent))
                    rel_path2 = str(file2.relative_to(self.test_dir.parent))

                    self.duplicates.append(
                        DuplicateGroup(
                            pattern="similar",
                            similarity=similarity,
                            files=[(rel_path1, name1), (rel_path2, name2)],
                            reason=f"{similarity:.1%} code similarity (threshold: {self.threshold:.1%})",
                        )
                    )

        print(
            f"Found {len([d for d in self.duplicates if d.pattern == 'similar'])} "
            "similar test groups"
        )

    def generate_markdown_report(self, output_path: Path) -> None:
        """Generate markdown duplicate analysis report."""
        lines = ["# Test Duplication Analysis\n"]
        lines.append(f"**Test Directory**: {self.test_dir}\n")
        lines.append(f"**Similarity Threshold**: {self.threshold:.1%}\n")
        lines.append(f"**Total Duplicate Groups Found**: {len(self.duplicates)}\n")
        lines.append("---\n")

        # Summary by pattern
        exact_count = len([d for d in self.duplicates if d.pattern == "exact"])
        functional_count = len([d for d in self.duplicates if d.pattern == "functional"])
        similar_count = len([d for d in self.duplicates if d.pattern == "similar"])

        lines.append("## Summary\n")
        lines.append(f"- **Exact duplicates** (same name): {exact_count}\n")
        lines.append(f"- **Functional duplicates** (same logic): {functional_count}\n")
        lines.append(f"- **Similar tests** (≥{self.threshold:.1%} similarity): {similar_count}\n")
        lines.append("\n---\n")

        # Exact duplicates
        if exact_count > 0:
            lines.append("## Exact Duplicates\n")
            lines.append("Tests with identical names across files.\n\n")

            for dup in [d for d in self.duplicates if d.pattern == "exact"]:
                lines.append(f"### {dup.reason}\n")
                lines.append(f"**Similarity**: {dup.similarity:.1%}\n\n")
                for file_path, func_name in dup.files:
                    lines.append(f"- `{file_path}::{func_name}`\n")
                lines.append("\n**Recommendation**: Keep one, delete others (review logic first)\n\n")
                lines.append("---\n")

        # Functional duplicates
        if functional_count > 0:
            lines.append("## Functional Duplicates\n")
            lines.append("Tests with identical or near-identical logic.\n\n")

            for dup in [d for d in self.duplicates if d.pattern == "functional"]:
                lines.append(f"### {dup.reason}\n")
                lines.append(f"**Similarity**: {dup.similarity:.1%}\n\n")
                for file_path, func_name in dup.files:
                    lines.append(f"- `{file_path}::{func_name}`\n")
                lines.append("\n**Recommendation**: Consolidate via parametrization or keep one\n\n")
                lines.append("---\n")

        # Similar tests
        if similar_count > 0:
            lines.append("## Similar Tests\n")
            lines.append(f"Tests with ≥{self.threshold:.1%} code similarity.\n\n")

            # Sort by similarity (highest first)
            similar_dups = sorted(
                [d for d in self.duplicates if d.pattern == "similar"],
                key=lambda x: x.similarity,
                reverse=True,
            )[:50]  # Top 50

            for dup in similar_dups:
                lines.append(f"### {dup.reason}\n")
                for file_path, func_name in dup.files:
                    lines.append(f"- `{file_path}::{func_name}`\n")
                lines.append(
                    "\n**Recommendation**: Review for consolidation opportunity\n\n"
                )
                lines.append("---\n")

        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(lines), encoding="utf-8")
        print(f"Report written to {output_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Find duplicate tests")
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
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Similarity threshold for similar tests (default: 0.85)",
    )

    args = parser.parse_args()

    # Validate
    if not args.test_dir.exists():
        print(f"ERROR: Test directory not found: {args.test_dir}", file=sys.stderr)
        return 1

    if not 0.0 <= args.threshold <= 1.0:
        print("ERROR: Threshold must be between 0.0 and 1.0", file=sys.stderr)
        return 1

    # Run analysis
    deduplicator = TestDeduplicator(args.test_dir, args.threshold)
    deduplicator.find_exact_duplicates()
    deduplicator.find_functional_duplicates()
    deduplicator.find_similar_tests()
    deduplicator.generate_markdown_report(args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
