#!/usr/bin/env bash
# =============================================================================
# ChromaDB RAG Retrieval Example
#
# Seeds a local ChromaDB collection with science/health reference documents,
# then runs an ELSPETH pipeline that enriches question rows with relevant
# context retrieved from the collection.
#
# Prerequisites:
#   uv pip install -e ".[rag]"    # Installs chromadb
#
# Usage:
#   ./examples/chroma_rag/run.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Clean previous run artifacts
rm -rf examples/chroma_rag/chroma_data
rm -f examples/chroma_rag/runs/audit.db examples/chroma_rag/runs/audit.db-wal examples/chroma_rag/runs/audit.db-shm
rm -f examples/chroma_rag/output/results.jsonl examples/chroma_rag/output/quarantined.jsonl

echo "=== ChromaDB RAG Retrieval Example ==="
echo ""

# --- Seed ChromaDB ---
echo "Seeding ChromaDB collection with reference documents..."
.venv/bin/python examples/chroma_rag/seed_collection.py
echo ""

# --- Run Pipeline ---
echo "Running ELSPETH pipeline with RAG retrieval..."
echo ""
.venv/bin/elspeth run --settings examples/chroma_rag/settings.yaml --execute

echo ""
echo "=== Pipeline Complete ==="
echo ""

# Show output
if [ -f examples/chroma_rag/output/results.jsonl ]; then
    echo "Output (examples/chroma_rag/output/results.jsonl):"
    echo "---"
    head -3 examples/chroma_rag/output/results.jsonl | python3 -m json.tool 2>/dev/null || head -3 examples/chroma_rag/output/results.jsonl
    echo "---"
    LINES=$(wc -l < examples/chroma_rag/output/results.jsonl)
    echo "($LINES rows written)"
fi

if [ -f examples/chroma_rag/output/quarantined.jsonl ]; then
    QLINES=$(wc -l < examples/chroma_rag/output/quarantined.jsonl)
    if [ "$QLINES" -gt 0 ]; then
        echo ""
        echo "Quarantined rows: $QLINES (see examples/chroma_rag/output/quarantined.jsonl)"
    fi
fi

echo ""
echo "Done. Audit trail: examples/chroma_rag/runs/audit.db"
