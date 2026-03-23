#!/usr/bin/env bash
# =============================================================================
# ChromaDB RAG + OpenRouter LLM Q&A Example
#
# Two-stage pipeline:
#   1. RAG retrieval: enriches each question with relevant context from ChromaDB
#   2. LLM answering: sends question + context to OpenRouter for grounded answers
#
# Prerequisites:
#   uv pip install -e ".[rag,llm]"
#   OPENROUTER_API_KEY set in .env
#
# Usage:
#   ./examples/chroma_rag_qa/run.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Clean previous run artifacts
rm -rf examples/chroma_rag_qa/chroma_data
rm -f examples/chroma_rag_qa/runs/audit.db examples/chroma_rag_qa/runs/audit.db-wal examples/chroma_rag_qa/runs/audit.db-shm
rm -f examples/chroma_rag_qa/output/results.jsonl examples/chroma_rag_qa/output/quarantined.jsonl

echo "=== ChromaDB RAG + OpenRouter LLM Q&A Example ==="
echo ""

# --- Seed ChromaDB ---
echo "Seeding ChromaDB collection with reference documents..."
.venv/bin/python examples/chroma_rag_qa/seed_collection.py
echo ""

# --- Run Pipeline ---
echo "Running RAG retrieval → LLM answering pipeline..."
echo ""
.venv/bin/elspeth run --settings examples/chroma_rag_qa/settings.yaml --execute

echo ""
echo "=== Pipeline Complete ==="
echo ""

# Show output
if [ -f examples/chroma_rag_qa/output/results.jsonl ]; then
    LINES=$(wc -l < examples/chroma_rag_qa/output/results.jsonl)
    echo "Output: $LINES rows written to examples/chroma_rag_qa/output/results.jsonl"
    echo ""
    echo "Sample output (first row, formatted):"
    echo "---"
    head -1 examples/chroma_rag_qa/output/results.jsonl | python3 -c "
import json, sys, textwrap
row = json.loads(sys.stdin.read())
print(f\"Question: {row['question']}\")
print(f\"RAG Score: {row.get('sci__rag_score', 'N/A')}\")
print(f\"RAG Chunks: {row.get('sci__rag_count', 'N/A')}\")
print(f\"LLM Answer: {row.get('llm_answer', 'N/A')}\")
" 2>/dev/null || head -1 examples/chroma_rag_qa/output/results.jsonl
    echo "---"
fi

if [ -f examples/chroma_rag_qa/output/quarantined.jsonl ]; then
    QLINES=$(wc -l < examples/chroma_rag_qa/output/quarantined.jsonl)
    if [ "$QLINES" -gt 0 ]; then
        echo ""
        echo "Quarantined rows: $QLINES (see examples/chroma_rag_qa/output/quarantined.jsonl)"
    fi
fi

echo ""
echo "Done. Audit trail: examples/chroma_rag_qa/runs/audit.db"
