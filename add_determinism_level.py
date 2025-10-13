#!/usr/bin/env python3
"""Add determinism_level to all test files where security_level exists but determinism_level doesn't."""

import re
from pathlib import Path

def add_determinism_to_dict_literals(content):
    """Add determinism_level to dict literals containing security_level."""

    lines = content.split('\n')
    result = []

    for line in lines:
        # Skip if determinism_level already present on this line
        if 'determinism_level' in line:
            result.append(line)
            continue

        # Skip if no security_level on this line
        if 'security_level' not in line:
            result.append(line)
            continue

        # Pattern: Look for dictionary entries with security_level
        # Add determinism_level after security_level

        # Match: {"security_level": "OFFICIAL"}
        # Replace with: {"security_level": "OFFICIAL", "determinism_level": "guaranteed"}

        # Pattern 1: security_level at end of dict (before })
        pattern1 = r'("security_level"\s*:\s*"[A-Z_]+")(\s*\})'
        if re.search(pattern1, line):
            line = re.sub(pattern1, r'\1, "determinism_level": "guaranteed"\2', line)
            result.append(line)
            continue

        # Pattern 2: security_level in middle of dict (followed by comma)
        pattern2 = r'("security_level"\s*:\s*"[A-Z_]+")(\s*,)'
        if re.search(pattern2, line):
            line = re.sub(pattern2, r'\1, "determinism_level": "guaranteed"\2', line)
            result.append(line)
            continue

        # Pattern 3: PluginContext construction
        # PluginContext(plugin_name="suite", plugin_kind="suite", security_level="secret")
        # → PluginContext(plugin_name="suite", plugin_kind="suite", security_level="SECRET", determinism_level="none")
        pattern3 = r'(PluginContext\([^)]*security_level=["\'][^"\']+["\'])(\))'
        if re.search(pattern3, line):
            line = re.sub(pattern3, r'\1, determinism_level="none"\2', line)
            result.append(line)
            continue

        result.append(line)

    return '\n'.join(result)

def migrate_file(file_path):
    """Migrate a single test file."""
    content = file_path.read_text(encoding='utf-8')
    original = content

    # Add determinism_level to dict literals
    content = add_determinism_to_dict_literals(content)

    # Also handle lowercase "secret" that wasn't caught
    content = content.replace('security_level="secret"', 'security_level="SECRET"')
    content = content.replace("security_level='secret'", "security_level='SECRET'")

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ Updated {file_path.name}")
        return True
    else:
        print(f"  Skipped {file_path.name}")
        return False

def main():
    """Process all test files."""
    tests_dir = Path("tests")
    test_files = sorted(tests_dir.glob("test_*.py"))

    updated = 0
    for test_file in test_files:
        if migrate_file(test_file):
            updated += 1

    print(f"\nUpdated {updated}/{len(test_files)} files")

if __name__ == "__main__":
    main()
