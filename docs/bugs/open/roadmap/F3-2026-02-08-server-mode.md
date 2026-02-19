## Summary

Transform ELSPETH from on-demand CLI execution into a persistent service with REST + WebSocket API. Foundational for streaming, web frontend, multi-tenant access, and federated pipelines.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.2

## Current Model
- `elspeth run`: starts, processes, exits
- `elspeth explain`: separate process, opens DB read-only, exits
- `elspeth-mcp`: separate process for analysis, stateless

## Target Model
- `elspeth serve`: persistent API server
- Pipelines submitted via API (REST + WebSocket), not just CLI
- Multiple pipelines queued, scheduled, or running concurrently
- Landscape stays open for continuous writes and reads
- CLI commands become thin clients to the server API

## Core Architecture Changes

### API Layer
- FastAPI or Litestar with REST + WebSocket endpoints
- OpenAPI spec auto-generated from typed endpoints
- Authentication (ties into RBAC feature)

### Pipeline Lifecycle Management
- Pipeline submission queue
- Concurrent execution (multiple orchestrators, separate DB transactions)
- Pipeline scheduling (cron-like for recurring)
- Graceful drain: stop accepting, finish in-flight, shut down

### Process Model
- Single server managing multiple pipeline runs
- Worker pool for execution (process or thread based)
- Health check endpoint for container orchestration
- Metrics endpoint (Prometheus/OpenTelemetry)

### CLI Becomes a Client
- `elspeth run` → submit to server, stream events back
- `elspeth explain` → query server API
- New: `elspeth serve --port 8080 --workers 4`

## Blocks

- `w2q7.1` — Visual pipeline designer
- `w2q7.3` — Streaming mode
- `w2q7.4` — Federated pipelines
- `w2q7.6` — Multi-tenant RBAC

## Dependencies

- Parent: `w2q7` — ELSPETH-NEXT epic
