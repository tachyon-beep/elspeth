#!/bin/bash
# Fix all test files that have PipelineRow issues

echo "Fixing all test files for PipelineRow migration..."

# Run tests to find all failures
/home/john/elspeth-rapid/.venv/bin/python -m pytest tests/engine/ --tb=no -q 2>&1 | grep "FAILED" | awk '{print $1}' | cut -d: -f1 | sort -u > /tmp/failing_files.txt

echo "Found $(wc -l < /tmp/failing_files.txt) failing test files"
cat /tmp/failing_files.txt

# For each file, check if it needs PipelineRow migration
while read -r file; do
    if [ -f "$file" ]; then
        echo "Checking $file..."

        # Check if file has the helper already
        if grep -q "_make_pipeline_row\|_make_contract" "$file"; then
            echo "  ✓ Already has helper function"
        else
            echo "  ✗ Missing helper function - needs migration"
        fi
    fi
done < /tmp/failing_files.txt
