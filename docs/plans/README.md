# ELSPETH Implementation Plans

This directory tracks implementation plans across all development phases.

## Directory Structure

```
docs/plans/
├── completed/          # 53 fully implemented plans (Phases 1-6 + features)
├── paused/            # Plans temporarily on hold
├── cancelled/         # Plans that were superseded or abandoned
├── *.md               # Active plans (in progress or ready to start)
└── README.md          # This file
```

## Active Plans (4)

| Plan | Status | Priority | Completion |
|------|--------|----------|------------|
| 2026-01-21-bug-fix-sprint.md | In Progress | P1 | 38% (55 of 143 bugs fixed) |
| 2026-01-20-world-class-test-regime.md | In Progress | P1 | 15% (1,690 → 2,650 tests) |
| 2026-01-12-phase7-advanced-features.md | Partial | P2 | 40% (fork infra done, A/B testing pending) |
| PLAN_STATUS_UPDATE_2026-01-22.md | Reference | N/A | Status reconciliation doc |

## Completed Plans (53)

### Recent Completions (2026-01-22)
- **AUD-001 Token Outcomes (Design + Implementation)** - Explicit outcome recording with partial unique index
- **AUD-002 Continue Routing** - Explicit continue decision recording (bug P1-2026-01-19 closed)
- **CI/CD & Docker Containerization** - Production-ready pipeline with 4 GitHub workflows

### Major Phases (Completed)
- **Phase 1:** Foundation (canonical JSON, DAG, config)
- **Phase 2:** Plugin system (pluggy, hookspecs, discovery)
- **Phase 3A:** Landscape (audit trail, 12 tables)
- **Phase 3B:** Engine (orchestrator, processor, retry)
- **Phase 4:** CLI and I/O (Typer, CSV/JSON/DB sources/sinks)
- **Phase 5:** Production hardening (checkpointing, rate limiting, retention)
- **Phase 6:** External calls (LLM integration, Azure, pooling)

### Feature Completions
See `completed/` directory for full list (49 historical + 4 recent = 53 total)

## Plan Lifecycle

```
Created → Active → In Progress → Paused/Cancelled/Completed
```

### Status Definitions

| Status | Meaning | Location |
|--------|---------|----------|
| **Active** | Ready to start, no blockers | Root directory |
| **In Progress** | Partially implemented | Root directory with % in header |
| **Paused** | On hold, may resume | `paused/` subdirectory |
| **Cancelled** | Superseded or abandoned | `cancelled/` subdirectory |
| **Completed** | Fully implemented and tested | `completed/` subdirectory |

### Moving Plans

When marking a plan complete:
1. Update plan header: `**Status:** ✅ IMPLEMENTED (YYYY-MM-DD)`
2. Add "Implementation Summary" section with evidence
3. Move to `completed/` directory: `git mv plan.md completed/`
4. Update this README

## Current Focus (2026-01-22)

**Primary:** Bug fixes (88 open - 29 P1, 40 P2, 19 P3)
**Secondary:** Test expansion (mutation testing at 80%+ target)
**Optional:** Phase 7 A/B testing (if needed for production use cases)

## Evidence-Based Status

All plan status updates verified against:
- Schema inspection (`schema.py`, migrations)
- Implementation presence (`grep` for APIs, patterns)
- Test coverage (`test_*.py` files)
- Bug directory (closed vs open)
- GitHub Actions workflows (CI/CD)

See `PLAN_STATUS_UPDATE_2026-01-22.md` for latest reconciliation methodology.
