#!/usr/bin/env python3
"""Migrate test files to use determinism_level and PSPF security levels."""

import re
from pathlib import Path

# Security level mapping: lowercase → PSPF uppercase
SECURITY_MAPPING = {
    "unofficial": "UNOFFICIAL",
    "official": "OFFICIAL",
    "official_sensitive": "OFFICIAL_SENSITIVE",
    "protected": "PROTECTED",
    "secret": "SECRET",
    "internal": "OFFICIAL",  # Legacy mapping
    "confidential": "PROTECTED",  # Legacy mapping
    "public": "UNOFFICIAL",  # Legacy mapping
}


def migrate_security_levels(content):
    """Replace lowercase security levels with PSPF uppercase."""
    for old, new in SECURITY_MAPPING.items():
        # Match: "security_level": "old" or 'security_level': 'old'
        content = re.sub(rf'("security_level"\s*:\s*")[{old}](")', rf"\1{new}\2", content)
        content = re.sub(rf"('security_level'\s*:\s*')[{old}](')", rf"\1{new}\2", content)
    return content


def add_determinism_level(content):
    """Add determinism_level after security_level where missing."""

    # Pattern 1: Dictionary literals with security_level but no determinism_level
    # Example: {"security_level": "OFFICIAL"}  → {"security_level": "OFFICIAL", "determinism_level": "guaranteed"}

    def replace_dict(match):
        """Add determinism_level to dict if not present."""
        full_match = match.group(0)

        # Skip if determinism_level already present
        if "determinism_level" in full_match:
            return full_match

        # Find the security_level entry
        sec_pattern = r'["\']security_level["\']\s*:\s*["\']([A-Z_]+)["\']'
        sec_match = re.search(sec_pattern, full_match)

        if not sec_match:
            return full_match

        security_val = sec_match.group(1)

        # Determine determinism level (default to guaranteed for most cases)
        determinism_val = "guaranteed"

        # Insert determinism_level after security_level
        insertion_point = sec_match.end()

        # Check if there's a comma after security_level
        after_sec = full_match[insertion_point : insertion_point + 5]
        if "," not in after_sec:
            # Need to add comma before determinism_level
            new_dict = full_match[:insertion_point] + f', "determinism_level": "{determinism_val}"' + full_match[insertion_point:]
        else:
            # Insert after the comma
            comma_pos = full_match.index(",", insertion_point)
            new_dict = full_match[: comma_pos + 1] + f' "determinism_level": "{determinism_val}",' + full_match[comma_pos + 1 :]

        return new_dict

    # Match dictionary literals containing security_level
    # This is a simplified pattern - may need refinement
    content = re.sub(r'\{[^{}]*["\']security_level["\'][^{}]*\}', replace_dict, content, flags=re.MULTILINE)

    return content


def migrate_file(file_path):
    """Migrate a single test file."""
    content = file_path.read_text(encoding="utf-8")
    original = content

    # Step 1: Migrate security levels to PSPF
    content = migrate_security_levels(content)

    # Step 2: Add determinism_level where missing
    content = add_determinism_level(content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        print(f"✓ Migrated {file_path.relative_to(Path.cwd())}")
        return True
    else:
        print(f"  Skipped {file_path.relative_to(Path.cwd())} (no changes)")
        return False


def main():
    """Migrate all test files."""
    tests_dir = Path(__file__).parent / "tests"
    test_files = list(tests_dir.glob("test_*.py"))

    print(f"Found {len(test_files)} test files")
    print("=" * 60)

    migrated_count = 0
    for test_file in sorted(test_files):
        if migrate_file(test_file):
            migrated_count += 1

    print("=" * 60)
    print(f"Migrated {migrated_count}/{len(test_files)} files")


if __name__ == "__main__":
    main()
