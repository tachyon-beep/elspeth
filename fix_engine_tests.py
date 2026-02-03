#!/usr/bin/env python3
"""Batch fix engine test files for PipelineRow migration."""

import re
import sys
from pathlib import Path

HELPER_CODE = '''

def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED schema for testing.

    Helper to wrap test dicts in PipelineRow with flexible schema.
    Uses object type for all fields since OBSERVED mode accepts any type.
    """
    fields = tuple(
        FieldContract(
            normalized_name=key,
            original_name=key,
            python_type=object,
            required=False,
            source="observed",
        )
        for key in data.keys()
    )
    contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
    return PipelineRow(data, contract)
'''

def add_imports_and_helper(content: str) -> str:
    """Add PipelineRow imports and helper if not present."""
    # Check if already has PipelineRow import
    if 'from elspeth.contracts.schema_contract import' in content and 'PipelineRow' in content:
        # Already has import, check if helper exists
        if '_make_pipeline_row' not in content:
            # Add helper after imports section
            lines = content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.startswith('#') and not line.startswith('from') and not line.startswith('import'):
                    insert_idx = i
                    break
            lines.insert(insert_idx, HELPER_CODE)
            return '\n'.join(lines)
        return content

    # Need to add import
    if 'from elspeth.contracts.schema import SchemaConfig' in content:
        content = content.replace(
            'from elspeth.contracts.schema import SchemaConfig',
            'from elspeth.contracts.schema import SchemaConfig\nfrom elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract'
        )
    elif 'from elspeth.contracts import' in content:
        # Add after first contracts import
        content = re.sub(
            r'(from elspeth\.contracts import [^\n]+)',
            r'\1\nfrom elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract',
            content,
            count=1
        )

    # Add helper
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.startswith('#') and not line.startswith('from') and not line.startswith('import'):
            insert_idx = i
            break
    lines.insert(insert_idx, HELPER_CODE)
    return '\n'.join(lines)

def fix_tokeninfo_creations(content: str) -> str:
    """Fix TokenInfo row_data assignments."""
    # Pattern 1: row_data={...} with indentation
    content = re.sub(
        r'(\s+row_data=)\{',
        r'\1_make_pipeline_row({',
        content
    )

    # Close the parentheses
    content = re.sub(
        r'row_data=_make_pipeline_row\((\{[^}]+\})\),',
        r'row_data=_make_pipeline_row(\1),',
        content
    )

    return content

def fix_recorder_calls(content: str) -> str:
    """Fix recorder.create_row() calls with token.row_data."""
    content = re.sub(
        r'data=token\.row_data,',
        r'data=token.row_data.to_dict(),',
        content
    )
    return content

def fix_row_data_assertions(content: str) -> str:
    """Fix assertions comparing row_data to dict."""
    # Pattern: assert token.row_data == {
    content = re.sub(
        r'assert\s+(\w+\.row_data)\s*==\s*\{',
        r'assert \1.to_dict() == {',
        content
    )
    return content

def process_file(filepath: Path) -> bool:
    """Process a single test file. Returns True if changes were made."""
    try:
        content = filepath.read_text()
        original = content

        # Apply fixes
        content = add_imports_and_helper(content)
        content = fix_tokeninfo_creations(content)
        content = fix_recorder_calls(content)
        content = fix_row_data_assertions(content)

        if content != original:
            filepath.write_text(content)
            print(f"✓ Fixed {filepath.name}")
            return True
        else:
            print(f"- No changes needed for {filepath.name}")
            return False
    except Exception as e:
        print(f"✗ Error processing {filepath.name}: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_engine_tests.py <test_file1> <test_file2> ...")
        sys.exit(1)

    files = [Path(f) for f in sys.argv[1:]]
    changed = 0

    for filepath in files:
        if filepath.exists() and filepath.suffix == '.py':
            if process_file(filepath):
                changed += 1
        else:
            print(f"✗ Not found or not a Python file: {filepath}")

    print(f"\n{changed}/{len(files)} files modified")

if __name__ == "__main__":
    main()
