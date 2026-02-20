## Summary

Web-based DAG editor with live execution. Users drag-and-drop nodes, connect them visually, and hit 'play' to see results stream through the DAG in real time.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.1

## Core Capabilities

### Pipeline Design Surface
- Node palette populated from plugin discovery (sources, transforms, gates, sinks)
- Drag-and-drop node placement on canvas
- Visual edge routing with labels (continue, route_to_sink, fork paths)
- Node configuration panels (renders plugin config schema as form fields)
- Live schema contract validation as edges are connected
- Serialize/deserialize to YAML (roundtrip with existing settings.yaml format)

### Live Execution
- 'Play' button triggers pipeline execution via backend API
- WebSocket streaming of execution events (reuse existing event bus from core/events.py)
- Real-time token flow visualization with status colors
- Row-level drill-down: click a token to see its current state

### Landscape Integration
- After execution, full explain/lineage available in the same UI
- Link to MCP analysis tools
- Visual diff between runs

## Technology Considerations (TBD)
- Frontend: React vs Svelte vs HTMX
- DAG rendering: React Flow, D3, or Cytoscape.js
- Backend: FastAPI or Litestar for WebSocket support

## Dependencies

- `w2q7.2` — Server mode (required)
- Parent: `w2q7` — ELSPETH-NEXT epic
