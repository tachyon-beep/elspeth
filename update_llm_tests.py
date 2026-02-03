#!/usr/bin/env python3
"""Script to update LLM test files for PipelineRow migration."""

import re
import sys
from pathlib import Path

# Helper function template to add
HELPER_FUNCTION = '''

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
    return PipelineRow(data, contract)'''


def needs_pipeline_row_import(content: str) -> bool:
    """Check if file needs PipelineRow imports."""
    return 'PipelineRow' not in content and ('\.accept\(' in content or '\.process\(' in content)


def add_imports(content: str) -> str:
    """Add necessary imports if not present."""
    if 'from elspeth.contracts.schema_contract import' in content:
        # Already has schema_contract import, check if it has all needed classes
        if 'PipelineRow' not in content:
            # Add to existing import
            pattern = r'(from elspeth\.contracts\.schema_contract import [^\n]+)'
            match = re.search(pattern, content)
            if match:
                existing_import = match.group(1)
                if 'PipelineRow' not in existing_import:
                    # Add PipelineRow to the import
                    if not existing_import.endswith(')'):
                        # Single line import
                        new_import = existing_import.rstrip() + ', PipelineRow'
                        if 'FieldContract' not in existing_import:
                            new_import += ', FieldContract'
                        if 'SchemaContract' not in existing_import:
                            new_import += ', SchemaContract'
                        content = content.replace(existing_import, new_import)
        return content

    # No schema_contract import yet, add it
    # Find where to insert (after other elspeth.contracts imports)
    lines = content.split('\n')
    insert_index = None

    for i, line in enumerate(lines):
        if line.startswith('from elspeth.contracts import'):
            insert_index = i + 1
            break

    if insert_index is None:
        # Look for any import from elspeth
        for i, line in enumerate(lines):
            if 'from elspeth.' in line or 'import elspeth' in line:
                insert_index = i + 1
                break

    if insert_index:
        import_line = 'from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract'
        lines.insert(insert_index, import_line)
        return '\n'.join(lines)

    return content


def add_helper_function(content: str) -> str:
    """Add _make_pipeline_row helper function if not present."""
    if '_make_pipeline_row' in content:
        return content

    # Find the end of imports and add helper function
    lines = content.split('\n')

    # Find last import line
    last_import_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            last_import_idx = i
        elif line.strip() and not line.startswith('#') and last_import_idx > 0:
            # Found first non-import, non-comment line after imports
            break

    # Insert helper function after imports
    lines.insert(last_import_idx + 1, HELPER_FUNCTION)
    return '\n'.join(lines)


def update_process_calls(content: str) -> str:
    """Update .process() calls to use _make_pipeline_row()."""
    # Pattern: transform.process({"...": "..."}, ctx)
    # Replace with: transform.process(_make_pipeline_row({"...": "..."}), ctx)

    # Match .process( followed by a dict literal
    pattern = r'\.process\(\s*(\{[^}]+\})\s*,'
    replacement = r'.process(_make_pipeline_row(\1),'
    content = re.sub(pattern, replacement, content)

    return content


def update_accept_calls(content: str) -> str:
    """Update .accept() calls to use _make_pipeline_row()."""
    # Pattern: transform.accept({"...": "..."}, ctx)
    # Replace with: transform.accept(_make_pipeline_row({"...": "..."}), ctx)

    # Only wrap dict literals, not variables
    # Match .accept( followed by a dict literal starting with {
    pattern = r'\.accept\(\s*(\{[^}]+\})\s*,'
    replacement = r'.accept(_make_pipeline_row(\1),'
    content = re.sub(pattern, replacement, content)

    return content


def process_file(file_path: Path) -> bool:
    """Process a single test file. Returns True if modified."""
    content = file_path.read_text()
    original_content = content

    # Check if file needs updating
    has_process_calls = '.process(' in content
    has_accept_calls = '.accept(' in content

    if not (has_process_calls or has_accept_calls):
        return False

    # Check if already updated
    if '_make_pipeline_row' in content:
        print(f"  {file_path.name}: Already updated")
        return False

    # Add imports if needed
    if 'PipelineRow' not in content:
        content = add_imports(content)

    # Add helper function
    content = add_helper_function(content)

    # Update calls
    if has_process_calls:
        content = update_process_calls(content)
    if has_accept_calls:
        content = update_accept_calls(content)

    # Only write if changed
    if content != original_content:
        file_path.write_text(content)
        print(f"  {file_path.name}: Updated")
        return True

    return False


def main():
    """Main entry point."""
    test_dirs = [
        Path("/home/john/elspeth-rapid/tests/plugins/llm"),
        Path("/home/john/elspeth-rapid/tests/unit/plugins/llm"),
    ]

    files_to_process = []
    for test_dir in test_dirs:
        if test_dir.exists():
            files_to_process.extend(test_dir.glob("test_*.py"))

    print(f"Found {len(files_to_process)} test files")

    modified_count = 0
    for file_path in sorted(files_to_process):
        try:
            if process_file(file_path):
                modified_count += 1
        except Exception as e:
            print(f"  {file_path.name}: ERROR - {e}")
            import traceback
            traceback.print_exc()

    print(f"\nModified {modified_count} files")


if __name__ == "__main__":
    main()
