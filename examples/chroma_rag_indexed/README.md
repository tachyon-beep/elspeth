# ChromaDB RAG with Automated Indexing

This example demonstrates the full RAG ingestion story in ELSPETH:

1. **Indexing pipeline** (`index_pipeline.yaml`): Reads documents from CSV and writes them to a ChromaDB collection via `ChromaSink`.
2. **Query pipeline** (`query_pipeline.yaml`): Uses `depends_on` to run the indexing pipeline first, a commencement gate to verify the collection is populated, then retrieves context via RAG for each question.

## Usage

Run the query pipeline — it automatically indexes the corpus first:

    elspeth run --settings examples/chroma_rag_indexed/query_pipeline.yaml --execute

The indexing pipeline runs as a dependency before the query pipeline starts.

## What Happens

1. `depends_on` triggers `index_pipeline.yaml`
2. CSV source reads `documents.csv` (10 science/health documents)
3. `ChromaSink` writes documents into ChromaDB collection `science-facts-indexed` (overwriting duplicates)
4. Commencement gate checks `collections['science-facts-indexed']['count'] > 0`
5. RAG retrieval transform's readiness check verifies collection has documents
6. Questions from `questions.csv` are augmented with retrieved context
7. Results written to `output/results.jsonl`

If the commencement gate fails (e.g., indexing produced no documents), the query pipeline aborts with a `CommencementGateFailedError` before processing any questions.

## Files

- `documents.csv` — Reference corpus (10 documents)
- `questions.csv` — Questions to answer (5 questions)
- `index_pipeline.yaml` — CSV to ChromaSink indexing pipeline
- `query_pipeline.yaml` — depends_on + gate + RAG retrieval query pipeline
- `chroma_data/` — Persistent ChromaDB store (created on first run)
- `runs/audit.db` — Landscape audit trail (shared by both pipelines)
- `output/results.jsonl` — Retrieved context results
