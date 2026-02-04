#!/usr/bin/env python3
"""Fix all test transforms to return dicts instead of PipelineRow objects."""

import re
from pathlib import Path

# Find all test files
test_files = list(Path("tests/engine").glob("test_*.py"))

for filepath in test_files:
    content = filepath.read_text()
    original = content

    # Fix pattern 1: return TransformResult.success(row, ...) where row is the parameter
    # This needs to become: return TransformResult.success(row.to_dict(), ...)
    content = re.sub(
        r'return TransformResult\.success\(row,',
        r'return TransformResult.success(row.to_dict(),',
        content
    )

    # Fix pattern 2: return TransformResult.success(row) at end of line
    content = re.sub(
        r'return TransformResult\.success\(row\)$',
        r'return TransformResult.success(row.to_dict())',
        content,
        flags=re.MULTILINE
    )

    # Fix pattern 3: Update process signature from Any to PipelineRow
    content = re.sub(
        r'def process\(self, row: Any,',
        r'def process(self, row: PipelineRow,',
        content
    )

    if content != original:
        filepath.write_text(content)
        print(f"Fixed: {filepath.name}")

print("Done!")
