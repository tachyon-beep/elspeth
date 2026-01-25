#!/bin/bash
# Promote pending bugs to open
# Generated from triage report 2026-01-24

set -e

BUGS_DIR="docs/bugs"
PENDING="$BUGS_DIR/pending"
OPEN="$BUGS_DIR/open"

echo "Promoting 18 pending bugs to open..."

# P1 bugs to promote
bugs_p1=(
    "P1-2026-01-20-cli-explain-is-placeholder.md"
    "P1-2026-01-21-aggregation-passthrough-failure-buffered.md"
    "P1-2026-01-21-aggregation-single-skips-downstream.md"
    "P1-2026-01-21-call-index-collisions-across-clients.md"
    "P1-2026-01-21-http-auth-headers-dropped-request-hash.md"
    "P1-2026-01-21-http-response-truncation-audit-loss.md"
    "P1-2026-01-21-llm-response-partial-recording.md"
    "P1-2026-01-21-replay-request-hash-collisions.md"
    "P1-2026-01-21-token-outcome-group-id-mismatch.md"
    "P1-2026-01-22-aggregation-condition-trigger-missing-row-context.md"
    "P1-2026-01-22-aggregation-timeout-idle-never-fires.md"
)

# P2 bugs to promote
bugs_p2=(
    "P2-2026-01-19-exporter-missing-config-in-export.md"
    "P2-2026-01-19-exporter-n-plus-one-queries.md"
    "P2-2026-01-19-plugin-gate-graph-mismatch.md"
    "P2-2026-01-21-aggregation-coalesce-context-dropped.md"
    "P2-2026-01-21-aggregation-config-gates-skipped.md"
    "P2-2026-01-21-boolean-classifier-boolop-mismatch.md"
    "P2-2026-01-21-expression-slice-accepted-runtime-failure.md"
)

for bug in "${bugs_p1[@]}" "${bugs_p2[@]}"; do
    if [ -f "$PENDING/$bug" ]; then
        echo "  Promoting: $bug"
        mv "$PENDING/$bug" "$OPEN/$bug"
    else
        echo "  WARNING: Not found: $bug"
    fi
done

echo "✓ Promotion complete: 18 bugs moved to open/"
echo ""
echo "Next steps:"
echo "  1. Run 02-close-obe-bugs.sh to close OBE bugs"
echo "  2. Run 03-close-lost-bugs.sh to close lost bugs"
