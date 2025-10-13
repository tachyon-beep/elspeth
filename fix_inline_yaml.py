#!/usr/bin/env python3
"""Fix inline YAML in test files by adding determinism_level."""

import re
from pathlib import Path

def fix_yaml_in_file(file_path):
    """Add determinism_level to inline YAML configs in test files."""
    content = file_path.read_text(encoding='utf-8')
    original = content

    # Pattern: security_level: official (or OFFICIAL) without determinism_level nearby
    # We need to add determinism_level: guaranteed right after security_level

    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line has security_level and is within a YAML string
        if 'security_level:' in line and 'determinism_level' not in line:
            # Check if next line also has determinism_level
            next_has_det = (i + 1 < len(lines) and 'determinism_level' in lines[i + 1])

            if not next_has_det:
                # Extract indentation from current line
                indent_match = re.match(r'(\s*)', line)
                indent = indent_match.group(1) if indent_match else ''

                # Add determinism_level line after this one
                result.append(line)
                result.append(f'{indent}determinism_level: guaranteed')
                i += 1
                continue

        # Also handle security_level: official → OFFICIAL
        line = re.sub(r'security_level:\s+official\b', 'security_level: OFFICIAL', line)
        line = re.sub(r'security_level:\s+secret\b', 'security_level: SECRET', line)
        line = re.sub(r'security_level:\s+protected\b', 'security_level: PROTECTED', line)
        line = re.sub(r'security_level:\s+unofficial\b', 'security_level: UNOFFICIAL', line)

        result.append(line)
        i += 1

    content = '\n'.join(result)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ Fixed {file_path.name}")
        return True
    else:
        print(f"  Skipped {file_path.name}")
        return False

def main():
    """Process all test files with inline YAML."""
    test_files = [
        "tests/test_config.py",
        "tests/test_config_merge.py",
        "tests/test_config_suite.py",
        "tests/test_datasource_csv.py",
        "tests/test_datasource_blob_plugin.py",
        "tests/test_outputs_analytics_report.py",
        "tests/test_outputs_blob.py",
        "tests/test_outputs_csv.py",
        "tests/test_outputs_excel.py",
        "tests/test_outputs_local_bundle.py",
        "tests/test_outputs_zip.py",
        "tests/test_outputs_visual.py",
        "tests/test_sink_chaining.py",
        "tests/test_utilities_plugin_registry.py",
        "tests/test_validation_settings.py",
    ]

    updated = 0
    for file_name in test_files:
        file_path = Path(file_name)
        if file_path.exists():
            if fix_yaml_in_file(file_path):
                updated += 1

    print(f"\nFixed {updated}/{len(test_files)} files")

if __name__ == "__main__":
    main()
