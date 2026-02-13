# ELSPETH Implementation Plans

This directory tracks implementation plans across all development phases.

## Directory Structure

```
docs/plans/
├── paused/                      # 2 plans temporarily on hold
├── completed/                   # 131 fully implemented plans
│   └── plugin-refactor/         # 28 plans from the plugin refactor work
├── cancelled/                   # 1 cancelled plan
├── superseded/                  # 4 superseded plans
│   └── schema-validation-attempts-jan24/
├── *.md                         # Active plans at root level
└── README.md                    # This file
```

## Active Plans (3)

Plans at the root level, either in progress or queued for current sprint:

| Plan | Description | Status |
|------|-------------|--------|
| `RC3-remediation.md` | RC-3 remaining remediation (18 items from original 75+) | Active |
| `2026-02-02-whitelist-reduction.md` | Tier model whitelist reduction | In progress |
| `2026-02-13-contract-propagation-complex-fields.md` | Preserve dict/list fields in propagated contracts | Queued |
| `2026-02-01-nodeinfo-typed-config.md` | Type NodeInfo.config with discriminated union | Queued |

## Paused Plans (2)

Plans temporarily on hold:

- `paused/2026-01-12-phase7-advanced-features.md` — Fork infra done (40%), A/B testing not started (60%)
- `paused/2026-01-20-world-class-test-regime.md` — Largely superseded by test suite v2, but mutation testing targets not fully met

## Completed Plans (148)

### Summary
- **120 plans** directly in `completed/`
- **28 plans** in `completed/plugin-refactor/`

### Major Phases (All Completed)
- **Phase 1:** Foundation (canonical JSON, DAG, config)
- **Phase 2:** Plugin system (pluggy, hookspecs, discovery)
- **Phase 3A:** Landscape (audit trail, 12 tables)
- **Phase 3B:** Engine (orchestrator, processor, retry)
- **Phase 4:** CLI and I/O (Typer, CSV/JSON/DB sources/sinks)
- **Phase 5:** Production hardening (checkpointing, rate limiting, retention)
- **Phase 6:** External calls (LLM integration, Azure, pooling)

See `completed/` directory for full list.

## Superseded Plans (4)

Plans replaced by better approaches or overtaken by events:

- `superseded/RC2-remediation.md` — 75+ item plan; ~57 resolved piecemeal, remainder carried to RC3-remediation.md
- `superseded/2026-01-26-recorder-refactoring.md` — Recorder refactor done via different approach
- `superseded/2026-02-06-quarantine-sink-dag-exclusion.md` — Replaced by multipath edges approach
- `superseded/schema-validation-attempts-jan24/` — 14 schema validation attempts that led to current design

## Cancelled Plans (1)

- `cancelled/2026-01-12-phase6-external-calls.md`

## Plan Lifecycle

```
Created → In Progress → Paused/Cancelled/Completed/Superseded
```

### Status Definitions

| Status | Meaning | Location |
|--------|---------|----------|
| **Active** | Currently being worked on or queued | Root level (`*.md`) |
| **Paused** | On hold, may resume | `paused/` subdirectory |
| **Cancelled** | Abandoned, not implemented | `cancelled/` subdirectory |
| **Superseded** | Replaced by a better approach | `superseded/` subdirectory |
| **Completed** | Fully implemented and tested | `completed/` subdirectory |

### Moving Plans

When marking a plan complete:
1. Update plan header: `**Status:** IMPLEMENTED (YYYY-MM-DD)`
2. Add "Implementation Summary" section with evidence
3. Move to `completed/` directory: `git mv plan.md completed/`

## Evidence-Based Status

All plan status updates verified against:
- Schema inspection (`schema.py`, migrations)
- Implementation presence (`grep` for APIs, patterns)
- Test coverage (`test_*.py` files)
- Bug directory (closed vs open)
- GitHub Actions workflows (CI/CD)
