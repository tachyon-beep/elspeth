#!/bin/bash
# Close bugs that are lost (experimental features, unclear impact)
# Generated from triage report 2026-01-24

set -e

BUGS_DIR="docs/bugs"
PENDING="$BUGS_DIR/pending"
CLOSED="$BUGS_DIR/closed"

echo "Closing 8 LOST bugs (experimental features, unclear impact)..."

bugs_lost=(
    "P2-2026-01-21-pooling-ordering-metadata-dropped.md"
    "P2-2026-01-21-pooling-throttle-dispatch-burst.md"
    "P2-2026-01-21-verifier-missing-payload-hidden.md"
    "P2-2026-01-22-trigger-type-priority-misreports-first-fire.md"
    "P3-2026-01-21-aggregation-defensive-empty-output.md"
    "P3-2026-01-21-pooling-concurrent-execute-batch-mixes-results.md"
    "P3-2026-01-21-pooling-delay-invariant-not-validated.md"
    "P3-2026-01-21-pooling-missing-pool-stats.md"
    "P3-2026-01-21-verifier-ignore-order-hides-drift.md"
)

for bug in "${bugs_lost[@]}"; do
    if [ -f "$PENDING/$bug" ]; then
        echo "  Closing LOST: $bug"

        # Add resolution marker
        cat >> "$PENDING/$bug" <<EOF

## Resolution

**Status:** Closed - Lost
**Date:** 2026-01-24
**Reason:** Affects experimental/optional features (pooling, verifier) or unclear production impact. Insufficient evidence to prioritize over critical bugs.
**Note:** May revisit if these features become production-critical.
EOF

        mv "$PENDING/$bug" "$CLOSED/$bug"
    else
        echo "  WARNING: Not found: $bug"
    fi
done

echo "✓ LOST closure complete: 8+ bugs moved to closed/"
