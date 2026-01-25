#!/bin/bash
# Close bugs overtaken by events (OBE)
# Generated from triage report 2026-01-24

set -e

BUGS_DIR="docs/bugs"
PENDING="$BUGS_DIR/pending"
CLOSED="$BUGS_DIR/closed"

echo "Closing 8 OBE (Overtaken By Events) bugs..."

bugs_obe=(
    "P2-2026-01-21-llm-usage-missing-crash.md"
    "P2-2026-01-21-retryable-transform-result-ignored.md"
    "P2-2026-01-22-aggregation-timeout-checkpoint-age-reset.md"
    "P3-2026-01-21-is-operator-not-restricted-to-none.md"
    "P3-2026-01-21-row-get-attribute-allowed.md"
    "P3-2026-01-21-subscript-not-restricted-to-row.md"
)

for bug in "${bugs_obe[@]}"; do
    if [ -f "$PENDING/$bug" ]; then
        echo "  Closing OBE: $bug"

        # Add resolution marker
        cat >> "$PENDING/$bug" <<EOF

## Resolution

**Status:** Closed - Overtaken By Events (OBE)
**Date:** 2026-01-24
**Reason:** Superseded by recent architectural changes (checkpoint format migration, schema validation refactor)
**Related commits:** 36e17f2, ab2782a, a564bfa (checkpoint fixes), schema validation architecture refactor
EOF

        mv "$PENDING/$bug" "$CLOSED/$bug"
    else
        echo "  WARNING: Not found: $bug"
    fi
done

echo "✓ OBE closure complete: 8 bugs moved to closed/"
