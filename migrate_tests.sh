#!/bin/bash
# Migrate test files to use determinism_level and PSPF security levels

set -e

echo "Migrating test files..."
echo "======================="

# Function to migrate a single file
migrate_file() {
    local file="$1"
    local temp_file=$(mktemp)
    local changed=0

    # Step 1: Update security level strings to PSPF uppercase
    # "security_level": "official" → "security_level": "OFFICIAL"
    sed -E 's/("security_level"\s*:\s*")(official)(")/\1OFFICIAL\3/g' "$file" > "$temp_file"
    if ! cmp -s "$file" "$temp_file"; then changed=1; fi
    mv "$temp_file" "$file"

    # "security_level": "secret" → "security_level": "SECRET"
    sed -E 's/("security_level"\s*:\s*")(secret)(")/\1SECRET\3/g' "$file" > "$temp_file"
    if ! cmp -s "$file" "$temp_file"; then changed=1; fi
    mv "$temp_file" "$file"

    # "security_level": "protected" → "security_level": "PROTECTED"
    sed -E 's/("security_level"\s*:\s*")(protected)(")/\1PROTECTED\3/g' "$file" > "$temp_file"
    if ! cmp -s "$file" "$temp_file"; then changed=1; fi
    mv "$temp_file" "$file"

    # "security_level": "unofficial" → "security_level": "UNOFFICIAL"
    sed -E 's/("security_level"\s*:\s*")(unofficial)(")/\1UNOFFICIAL\3/g' "$file" > "$temp_file"
    if ! cmp -s "$file" "$temp_file"; then changed=1; fi
    mv "$temp_file" "$file"

    # Step 2: Add determinism_level after security_level in dict literals
    # Pattern: {"security_level": "OFFICIAL"} → {"security_level": "OFFICIAL", "determinism_level": "guaranteed"}
    # This pattern looks for dictionaries with security_level and adds determinism_level if missing

    python3 <<'EOF'
import re
import sys

file_path = sys.argv[1]
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original = content

# Pattern to match dict entries with security_level but no determinism_level on same line
# This is a simplified approach - looks for inline dicts like {"security_level": "X"}
# and adds determinism_level after security_level

def add_determinism(match):
    """Add determinism_level to dict if not already present."""
    full_text = match.group(0)

    # Skip if determinism_level already present
    if 'determinism_level' in full_text:
        return full_text

    # Find security_level and add determinism_level after it
    pattern = r'("security_level"\s*:\s*"[A-Z_]+")(\s*,|\s*\})'

    def insert_determinism(m):
        security_part = m.group(1)
        ending = m.group(2)

        if ending.strip() == '}':
            # At end of dict, add comma before determinism_level
            return f'{security_part}, "determinism_level": "guaranteed"{ending}'
        else:
            # In middle of dict, add after comma
            return f'{security_part}, "determinism_level": "guaranteed"{ending}'

    return re.sub(pattern, insert_determinism, full_text)

# Match inline dictionaries containing security_level
# Pattern: {..."security_level": "X"...}
content = re.sub(r'\{[^{}]*"security_level"[^{}]*\}', add_determinism, content)

if content != original:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    sys.exit(42)  # Signal that file was modified
else:
    sys.exit(0)
EOF

    if [ $? -eq 42 ]; then
        changed=1
    fi

    if [ $changed -eq 1 ]; then
        echo "✓ Migrated $(basename $file)"
        return 1
    else
        echo "  Skipped $(basename $file) (no changes)"
        return 0
    fi
}

# Process all test files
migrated_count=0
total_count=0

for test_file in tests/test_*.py; do
    if [ -f "$test_file" ]; then
        total_count=$((total_count + 1))
        if migrate_file "$test_file" "$1"; then
            :  # No change
        else
            migrated_count=$((migrated_count + 1))
        fi
    fi
done

echo "======================="
echo "Migrated $migrated_count/$total_count files"
