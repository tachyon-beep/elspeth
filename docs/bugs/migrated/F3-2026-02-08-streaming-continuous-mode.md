## Summary

Enable pipelines that run indefinitely, consuming from streaming sources (Kafka, webhooks, SSE, file watchers, message queues) with continuous audit recording.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.3

## Current Limitation

Pipelines assume finite sources: `source.load()` yields all rows, orchestrator processes them, run completes. Aggregation timeout limitation acknowledged in CLAUDE.md.

## Target Model

- Sources can be infinite (never signal completion)
- Tokens flow continuously through the DAG
- Aggregation timeouts fire on real wall-clock time
- Runs have 'streaming' status (distinct from 'running')
- Graceful drain: signal source to stop, flush in-flight, complete

## New Source Types

- Kafka consumer (consumer group, offset management, exactly-once)
- Webhook receiver (HTTP endpoint as source rows)
- File watcher (inotify/polling)
- SSE/WebSocket client
- Polling source (API every N seconds)

## Engine Changes

- Unbounded orchestrator run loop
- Backpressure / flow control
- Windowed aggregations (tumbling, sliding, session)
- Exactly-once via checkpoint
- Heartbeat rows for idle timeout triggering

## Dependencies

- `w2q7.2` — Server mode (required — streaming pipelines are long-lived)
- Parent: `w2q7` — ELSPETH-NEXT epic
