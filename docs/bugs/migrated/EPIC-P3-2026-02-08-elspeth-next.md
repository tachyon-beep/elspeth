## Summary

ELSPETH-NEXT: Enterprise database and visual pipeline designer. Next-generation capabilities representing a substantial architectural evolution, moving from CLI-driven audit pipeline framework toward an enterprise platform.

## Severity

- Severity: low
- Priority: P3
- Type: epic
- Status: open
- Bead ID: elspeth-rapid-w2q7

## Two Pillars

### 1. Enterprise Database Tier
Replace SQLite-as-default with a credible enterprise database story:
- SQLCipher for encrypted-at-rest audit trails (drop-in, FIPS 140-3 path)
- Embedded PostgreSQL via pgserver for full RDBMS without sysadmin overhead
- Three-tier strategy: SQLCipher (lightweight) -> pgserver (intermediate) -> external PostgreSQL (production)

### 2. Visual Pipeline Designer (Web Frontend)
Web-based DAG editor supporting interactive pipeline design and live execution:
- Drag-and-drop node placement
- Visual edge routing with conditional labels
- Live schema contract validation as nodes are connected
- Play button for live execution with streaming results
- Real-time token flow visualization through the DAG

## Architectural Implications

- Engine currently assumes CLI-driven batch execution — web frontend needs long-running server with WebSocket streaming
- DAG construction currently happens at startup from YAML — visual design means runtime DAG modification
- Plugin discovery needs to expose metadata (config schemas, contracts) to frontend
- Schema contract validation (currently at compile time) needs incremental mode
- Landscape recorder needs concurrent read access from frontend during pipeline execution

## Non-Goals (for now)

- Multi-user collaborative editing
- Cloud-hosted SaaS version
- Plugin marketplace
- Mobile interface

## Children

| ID | Feature | Priority |
|----|---------|----------|
| w2q7.1 | Visual pipeline designer | P3 |
| w2q7.2 | Server mode (API layer) | P3 |
| w2q7.3 | Streaming / continuous mode | P3 |
| w2q7.4 | Federated multi-pipeline orchestration | P3 |
| w2q7.5 | Time-travel replay engine | P3 |
| w2q7.6 | Multi-tenant RBAC | P3 |
| w2q7.7 | Sandboxed plugin SDK | P3 |

## Blocks

- `6c2` — Tier Model Whitelist Reduction (P2 epic)
- `gjd` — SQL query linting (P3)
- `xys7` — True Idle timeout (P3)
- `0984` — Config submodules (P4)
- `3m6` — AWS Secrets Manager (P4)
- `ande` — Schema contracts enhancements (P4)
- `ipwc` — Mid-chain aggregation (P4)
- `ya3x` — Branch-specific transforms (P4)
