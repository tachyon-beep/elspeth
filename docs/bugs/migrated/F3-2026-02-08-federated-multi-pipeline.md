## Summary

Pipeline-of-pipelines: one pipeline's sink feeds another pipeline's source, with end-to-end lineage across the entire chain. Enables real enterprise data flows (ETL -> enrichment -> classification -> routing -> archival).

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.4

## Target Model

- A 'federation' config defines a DAG of pipelines
- Pipeline sinks can be typed as 'feed' sinks that route to another pipeline's source
- Cross-pipeline lineage: 'this row in Pipeline B originated from row 42 in Pipeline A'
- Federation-level status: all child pipelines healthy, one failing, etc.
- Shared Landscape database across federated pipelines

## Cross-Pipeline Lineage

- Feed sinks record: (source_run_id, source_token_id, target_run_id, target_row_id)
- New Landscape table: `pipeline_feeds` linking runs across the federation
- `explain` command can trace across pipeline boundaries

## Execution Modes

- **Sequential**: Pipeline A completes, then Pipeline B starts
- **Streaming**: Pipeline A feeds Pipeline B in real-time (requires streaming mode)
- **Triggered**: Pipeline B starts when Pipeline A's sink has N rows

## Dependencies

- `w2q7.2` — Server mode (required)
- Parent: `w2q7` — ELSPETH-NEXT epic
