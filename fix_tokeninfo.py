#!/usr/bin/env python3
"""Fix TokenInfo constructions to use PipelineRow."""

import re

files = [
    "tests/engine/test_transform_executor.py",
    "tests/engine/test_transform_error_routing.py",
]

for filepath in files:
    with open(filepath) as f:
        content = f.read()

    original = content

    # Fix: row_data={"..."} -> row_data=PipelineRow({"..."}, _make_contract())
    content = re.sub(
        r'row_data=(\{[^}]+\})',
        r'row_data=PipelineRow(\1, _make_contract())',
        content
    )

    # Fix: data=token.row_data, -> data=token.row_data.to_dict(),
    content = content.replace(
        "data=token.row_data,",
        "data=token.row_data.to_dict(),"
    )

    # Fix transform signatures: row: dict[str, Any] -> row: PipelineRow
    content = re.sub(
        r'def process\(self, row: dict\[str, Any\]',
        r'def process(self, row: PipelineRow',
        content
    )

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Fixed: {filepath}")
    else:
        print(f"No changes: {filepath}")
