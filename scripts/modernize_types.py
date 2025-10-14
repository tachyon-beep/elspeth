#!/usr/bin/env python3
"""
Automated type hint modernization script for Python 3.10+

Converts legacy typing imports to modern builtin equivalents:
- Dict[K, V] → dict[K, V]
- List[T] → list[T]
- Set[T] → set[T]
- Tuple[T, ...] → tuple[T, ...]
- Optional[T] → T | None
- Union[A, B, C] → A | B | C

Usage:
    python scripts/modernize_types.py [--dry-run] [--path src/]
"""

import argparse
import re
from pathlib import Path
from typing import NamedTuple


class Replacement(NamedTuple):
    """A single replacement operation."""

    pattern: re.Pattern
    replacement: str
    description: str


# Type replacements (order matters!)
REPLACEMENTS = [
    # Optional[X] → X | None (must come before Union)
    Replacement(
        pattern=re.compile(r'\bOptional\[([^\]]+)\]'),
        replacement=r'\1 | None',
        description="Optional[T] → T | None",
    ),
    # Union[A, B, ...] → A | B | ...
    Replacement(
        pattern=re.compile(r'\bUnion\[([^\]]+)\]'),
        replacement=lambda m: ' | '.join(t.strip() for t in m.group(1).split(',')),
        description="Union[A, B] → A | B",
    ),
    # Dict[K, V] → dict[K, V]
    Replacement(
        pattern=re.compile(r'\bDict\['),
        replacement='dict[',
        description="Dict[ → dict[",
    ),
    # List[T] → list[T]
    Replacement(
        pattern=re.compile(r'\bList\['),
        replacement='list[',
        description="List[ → list[",
    ),
    # Set[T] → set[T]
    Replacement(
        pattern=re.compile(r'\bSet\['),
        replacement='set[',
        description="Set[ → set[",
    ),
    # Tuple[T, ...] → tuple[T, ...]
    Replacement(
        pattern=re.compile(r'\bTuple\['),
        replacement='tuple[',
        description="Tuple[ → tuple[",
    ),
]


def modernize_imports(content: str) -> str:
    """Remove unused legacy type imports and clean up import statements."""
    lines = content.split('\n')
    new_lines = []

    for line in lines:
        # Check if this is a typing import line
        if line.strip().startswith('from typing import'):
            # Extract imported names
            import_match = re.match(r'from typing import (.+)', line)
            if not import_match:
                new_lines.append(line)
                continue

            imports_str = import_match.group(1)

            # Parse imports (handle multiline later if needed)
            imports = [imp.strip() for imp in imports_str.split(',')]

            # Remove legacy types that are now builtins
            legacy_types = {'Dict', 'List', 'Set', 'Tuple', 'Optional', 'Union'}
            filtered_imports = [imp for imp in imports if imp not in legacy_types]

            # Reconstruct import line
            if filtered_imports:
                new_line = f"from typing import {', '.join(filtered_imports)}"
                new_lines.append(new_line)
            # If no imports left, skip the line entirely
        else:
            new_lines.append(line)

    return '\n'.join(new_lines)


def modernize_type_hints(content: str) -> tuple[str, int]:
    """Apply all type hint modernizations."""
    changes = 0
    result = content

    # Apply each replacement
    for replacement in REPLACEMENTS:
        if callable(replacement.replacement):
            # For complex replacements (like Union)
            matches = list(replacement.pattern.finditer(result))
            if matches:
                changes += len(matches)
                result = replacement.pattern.sub(replacement.replacement, result)
        else:
            # Simple string replacement
            count = len(replacement.pattern.findall(result))
            if count > 0:
                changes += count
                result = replacement.pattern.sub(replacement.replacement, result)

    return result, changes


def process_file(file_path: Path, dry_run: bool = False) -> tuple[int, bool]:
    """Process a single Python file.

    Returns:
        (num_changes, success)
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content

        # Step 1: Modernize type hints
        content, changes = modernize_type_hints(content)

        # Step 2: Clean up imports
        if changes > 0:
            content = modernize_imports(content)

        # Write back if changes were made
        if content != original_content:
            if not dry_run:
                file_path.write_text(content, encoding='utf-8')
                print(f"✓ {file_path}: {changes} changes")
            else:
                print(f"[DRY RUN] {file_path}: {changes} changes")
            return changes, True
        return 0, True

    except Exception as e:
        print(f"✗ {file_path}: ERROR - {e}")
        return 0, False


def main():
    parser = argparse.ArgumentParser(description="Modernize Python type hints")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files',
    )
    parser.add_argument(
        '--path',
        type=Path,
        default=Path('src/elspeth'),
        help='Path to directory to process (default: src/elspeth)',
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Elspeth Type Hint Modernization")
    print("=" * 60)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be modified")
        print()

    # Find all Python files
    python_files = list(args.path.rglob('*.py'))
    print(f"Found {len(python_files)} Python files in {args.path}")
    print()

    # Process each file
    total_changes = 0
    files_modified = 0
    files_failed = 0

    for file_path in sorted(python_files):
        changes, success = process_file(file_path, dry_run=args.dry_run)
        if changes > 0:
            total_changes += changes
            files_modified += 1
        if not success:
            files_failed += 1

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Files processed:  {len(python_files)}")
    print(f"Files modified:   {files_modified}")
    print(f"Files failed:     {files_failed}")
    print(f"Total changes:    {total_changes}")
    print()

    if args.dry_run:
        print("Run without --dry-run to apply changes")
    else:
        print("✓ Type hint modernization complete!")
        print()
        print("Next steps:")
        print("1. Run tests: python -m pytest")
        print("2. Run type checker: mypy src/elspeth")
        print("3. Run linter: ruff check src/")

    return 0 if files_failed == 0 else 1


if __name__ == '__main__':
    exit(main())
