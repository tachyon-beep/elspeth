#!/bin/bash
# Create subsystem directory structure
# Generated from triage report 2026-01-24

set -e

BUGS_DIR="docs/bugs"
OPEN="$BUGS_DIR/open"

echo "Creating subsystem directory structure..."

# Create by-subsystem organization
mkdir -p "$OPEN/by-subsystem"

subsystems=(
    "core-landscape"
    "core-dag"
    "core-canonical"
    "core-config"
    "engine-orchestrator"
    "engine-coalesce"
    "engine-executors"
    "engine-tokens"
    "engine-retry"
    "engine-schema-validation"
    "engine-spans"
    "plugins-sources"
    "plugins-transforms"
    "plugins-gates"
    "plugins-aggregations"
    "plugins-sinks"
    "llm-azure-batch"
    "llm-http"
    "llm-replay"
    "cli"
    "tui"
    "cross-cutting-auditability"
    "cross-cutting-type-coercion"
    "cross-cutting-performance"
    "cross-cutting-config"
)

for subsystem in "${subsystems[@]}"; do
    mkdir -p "$OPEN/by-subsystem/$subsystem"
    echo "  Created: by-subsystem/$subsystem/"
done

# Create by-priority organization
mkdir -p "$OPEN/by-priority"

priorities=("P0-critical" "P1-high" "P2-medium" "P3-low")

for priority in "${priorities[@]}"; do
    mkdir -p "$OPEN/by-priority/$priority"
    echo "  Created: by-priority/$priority/"
done

echo "✓ Directory structure created"
echo ""
echo "Next step: Run 05-create-symlinks.sh to populate with symlinks"
