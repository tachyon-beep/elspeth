#!/usr/bin/env python3
"""Test migration script for Phase 2 execution.

Automates file movement and import path updates with git mv.

Usage:
    # Dry run (shows what would happen)
    python migrate_tests.py move \\
        --mapping FILE_MAPPING.yaml \\
        --dry-run

    # Execute moves
    python migrate_tests.py move \\
        --mapping FILE_MAPPING.yaml

    # Update import paths
    python migrate_tests.py update-imports \\
        --test-dir tests/

Mapping file format (YAML):
    moves:
      - old: tests/test_adr002_invariants.py
        new: tests/compliance/adr002/test_invariants.py
      - old: tests/test_outputs_csv.py
        new: tests/unit/plugins/nodes/sinks/csv/test_write.py
"""

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


@dataclass
class FileMove:
    """Represents a file move operation."""

    old_path: Path
    new_path: Path


class TestMigrator:
    """Automate test file migration with git mv."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.moves: list[FileMove] = []

    def load_mapping(self, mapping_path: Path) -> None:
        """Load file mapping from YAML."""
        if not mapping_path.exists():
            raise FileNotFoundError(f"Mapping file not found: {mapping_path}")

        data = yaml.safe_load(mapping_path.read_text())

        for move in data.get("moves", []):
            self.moves.append(
                FileMove(old_path=Path(move["old"]), new_path=Path(move["new"]))
            )

        print(f"Loaded {len(self.moves)} file moves from {mapping_path}")

    def execute_moves(self) -> int:
        """Execute file moves using git mv."""
        if self.dry_run:
            print("=== DRY RUN MODE ===")

        for move in self.moves:
            # Check old file exists
            if not move.old_path.exists():
                print(f"WARNING: Source file not found: {move.old_path}", file=sys.stderr)
                continue

            # Create target directory
            move.new_path.parent.mkdir(parents=True, exist_ok=True)

            # Execute git mv
            cmd = ["git", "mv", str(move.old_path), str(move.new_path)]

            if self.dry_run:
                print(f"Would execute: {' '.join(cmd)}")
            else:
                try:
                    result = subprocess.run(
                        cmd, check=True, capture_output=True, text=True
                    )
                    print(f"✓ Moved {move.old_path} → {move.new_path}")
                except subprocess.CalledProcessError as e:
                    print(f"ERROR moving {move.old_path}: {e.stderr}", file=sys.stderr)
                    return 1

        if self.dry_run:
            print(f"\nDry run complete. Would move {len(self.moves)} files.")
        else:
            print(f"\n✓ Successfully moved {len(self.moves)} files.")

        return 0


class ImportUpdater:
    """Update import paths after file moves."""

    def __init__(self, test_dir: Path, dry_run: bool = False):
        self.test_dir = test_dir
        self.dry_run = dry_run
        self.updates_count = 0

    def update_file(self, file_path: Path) -> None:
        """Update import paths in a single file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            original_content = content
        except UnicodeDecodeError:
            print(f"WARNING: Could not read {file_path}", file=sys.stderr)
            return

        # Parse AST to find imports
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            print(f"WARNING: Syntax error in {file_path}", file=sys.stderr)
            return

        # Track changes
        changes_made = False

        # Pattern 1: Relative imports → Absolute imports
        # from ..plugins.sinks.csv import CsvSink
        # → from elspeth.plugins.nodes.sinks.csv import CsvSink
        relative_import_pattern = re.compile(
            r"^from (\.\.[^\s]+) import (.+)$", re.MULTILINE
        )

        def replace_relative(match: re.Match) -> str:
            rel_path = match.group(1)
            imports = match.group(2)

            # Convert relative to absolute
            # .. = parent directory
            # Count dots to determine level
            dots = len(rel_path) - len(rel_path.lstrip("."))

            # Build absolute path
            parts = rel_path.lstrip(".").split(".")
            absolute_path = "elspeth." + ".".join(parts)

            return f"from {absolute_path} import {imports}"

        new_content = relative_import_pattern.sub(replace_relative, content)
        if new_content != content:
            changes_made = True
            content = new_content

        # Pattern 2: Update old plugin paths
        # from elspeth.plugins.sinks.csv → elspeth.plugins.nodes.sinks.csv
        old_plugin_pattern = re.compile(
            r"from elspeth\.plugins\.(sinks|sources|transforms)\.(\w+)",
            re.MULTILINE,
        )

        def replace_plugin_path(match: re.Match) -> str:
            plugin_type = match.group(1)  # sinks/sources/transforms
            module = match.group(2)

            # Update to nodes structure
            return f"from elspeth.plugins.nodes.{plugin_type}.{module}"

        new_content = old_plugin_pattern.sub(replace_plugin_path, content)
        if new_content != content:
            changes_made = True
            content = new_content

        # Pattern 3: Update conftest imports
        # Fixture imports may need updating after moves
        conftest_pattern = re.compile(
            r"from conftest import (.+)$", re.MULTILINE
        )

        def replace_conftest(match: re.Match) -> str:
            imports = match.group(1)
            # Check if we're in a subdirectory that needs parent conftest
            depth = len(file_path.relative_to(self.test_dir).parents) - 1
            if depth > 0:
                return f"from {'.' * depth}conftest import {imports}"
            return match.group(0)

        new_content = conftest_pattern.sub(replace_conftest, content)
        if new_content != content:
            changes_made = True
            content = new_content

        # Write changes
        if changes_made:
            if self.dry_run:
                print(f"Would update imports in: {file_path}")
            else:
                file_path.write_text(content, encoding="utf-8")
                print(f"✓ Updated imports in {file_path}")
                self.updates_count += 1

    def update_all(self) -> int:
        """Update import paths in all test files."""
        if self.dry_run:
            print("=== DRY RUN MODE ===")

        test_files = sorted(self.test_dir.rglob("test_*.py"))
        print(f"Checking {len(test_files)} test files for import updates...")

        for file_path in test_files:
            self.update_file(file_path)

        if self.dry_run:
            print(f"\nDry run complete. Would update imports in {self.updates_count} files.")
        else:
            print(f"\n✓ Updated imports in {self.updates_count} files.")

        return 0


def cmd_move(args: argparse.Namespace) -> int:
    """Execute file move command."""
    migrator = TestMigrator(dry_run=args.dry_run)
    migrator.load_mapping(args.mapping)
    return migrator.execute_moves()


def cmd_update_imports(args: argparse.Namespace) -> int:
    """Execute import update command."""
    if not args.test_dir.exists():
        print(f"ERROR: Test directory not found: {args.test_dir}", file=sys.stderr)
        return 1

    updater = ImportUpdater(args.test_dir, dry_run=args.dry_run)
    return updater.update_all()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate test files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without executing")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Move command
    move_parser = subparsers.add_parser("move", help="Move test files using git mv")
    move_parser.add_argument(
        "--mapping",
        type=Path,
        required=True,
        help="YAML file mapping old paths to new paths",
    )

    # Update imports command
    import_parser = subparsers.add_parser("update-imports", help="Update import paths")
    import_parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Test directory to update (default: tests)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "move":
        return cmd_move(args)
    elif args.command == "update-imports":
        return cmd_update_imports(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
