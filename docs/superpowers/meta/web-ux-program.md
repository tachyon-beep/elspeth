# Web UX Composer MVP — Program of Work

**Created:** 2026-03-28
**Branch:** RC4.2-UX
**Parent Epic:** Semi-Autonomous Platform (`elspeth-rapid-ea33f5`)
**Status:** Planning complete, ready for execution

---

## Vision

A modular monolith web application for chat-first pipeline authoring. Users
describe data processing pipelines in natural language, a server-side LLM
composes them via tool calls, and users review, validate, and execute through
a React SPA. First increment towards the full Semi-Autonomous Platform.

---

## Document Hierarchy

```
Layer 1 — Main Spec + Main Plan (architecture-level)
  │
  ├── Layer 2 — Sub-Specs + Sub-Plans (per-phase, 6 each)
  │     │
  │     └── Layer 3 — Task-Plans (per-task within large sub-plans, as needed)
  │           Only created for sub-plans >1000 lines
  │           Decomposed at execution time, not upfront
  │
  └── Reviews — Seam reviews, panel reviews, re-reviews
```

**Decomposition rule:** Sub-plans exceeding 1000 lines must be broken into
task-level plans matching the internal seams of their parent sub-plan.

---

## Main Documents

| Type | Path | Lines | Purpose |
|------|------|-------|---------|
| Main Spec | `specs/2026-03-28-web-ux-composer-mvp-design.md` | 649 | Architecture, data model, API surface, UX, project structure |
| Main Plan | `plans/2026-03-28-web-ux-composer-mvp.md` | 1,707 | Phase overview, file map, review findings, warnings |

---

## Sub-Specs (Layer 2)

| # | Phase | Path | Lines | Scope |
|---|-------|------|-------|-------|
| 1 | Foundation | `specs/2026-03-28-web-ux-sub1-foundation-design.md` | 204 | Plugin manager extraction, WebSettings, app factory, CLI, `[webui]` extra |
| 2 | Auth & Sessions | `specs/2026-03-28-web-ux-sub2-auth-sessions-design.md` | 852 | AuthProvider protocol, 3 providers, session persistence, CRUD API, file upload |
| 3 | Catalog | `specs/2026-03-28-web-ux-sub3-catalog-design.md` | 166 | CatalogService wrapping PluginManager, catalog REST API |
| 4 | Composer | `specs/2026-03-28-web-ux-sub4-composer-design.md` | 692 | CompositionState, LLM tool-use loop, YAML generator, HTTP error shapes |
| 5 | Execution | `specs/2026-03-28-web-ux-sub5-execution-design.md` | 447 | Dry-run validation, background execution, thread safety, WebSocket progress |
| 6 | Frontend | `specs/2026-03-28-web-ux-sub6-frontend-design.md` | 508 | React SPA, chat, inspector, accessibility, empty states, error messages |

**Total sub-spec lines:** 2,869

---

## Sub-Plans (Layer 2)

| # | Phase | Path | Lines | Tasks | Needs L3 Decomposition? |
|---|-------|------|-------|-------|------------------------|
| 1 | Foundation | `plans/2026-03-28-web-ux-sub1-foundation.md` | 880 | 4 | No |
| 2 | Auth & Sessions | `plans/2026-03-28-web-ux-sub2-auth-sessions.md` | 4,021 | 12+ | **Yes** |
| 3 | Catalog | `plans/2026-03-28-web-ux-sub3-catalog.md` | 804 | 2 | No |
| 4 | Composer | `plans/2026-03-28-web-ux-sub4-composer.md` | 3,635 | 8+ | **Yes** |
| 5 | Execution | `plans/2026-03-28-web-ux-sub5-execution.md` | 2,784 | 8+ | **Yes** |
| 6 | Frontend | `plans/2026-03-28-web-ux-sub6-frontend.md` | 3,717 | 15+ | **Yes** |

**Total sub-plan lines:** 15,841

---

## Dependency Graph

```
Sub-Plan 1 (Foundation)         ← start here
  ├── Sub-Plan 2 (Auth & Sessions)
  │     ├── Sub-Plan 4 (Composer)  ← also needs Sub-Plan 3
  │     │     └── Sub-Plan 5 (Execution) ← also needs Sub-Plan 2
  │     │           └── Sub-Plan 6 (Frontend) ← needs all of 2-5
  └── Sub-Plan 3 (Catalog)        ← can run parallel with Sub-Plan 2
```

**Parallel opportunities:**
- Sub-Plans 1→2 and 1→3 can run in parallel after Phase 1 completes
- Sub-Plan 4 requires both 2 and 3

---

## Review History

### Round 1 — Initial Plan Review (5 reviewers)

| Reviewer | Focus | Findings |
|----------|-------|----------|
| Architecture Critic | Module boundaries, extraction path, DI | 2 blocking, 4 recommendations |
| Systems Thinker | Feedback loops, thread safety, archetypes | 3 blocking, 6 warnings |
| Python Engineer | Async/sync, protocols, frozen dataclasses | 5 critical, 5 warnings |
| Quality Engineer | Test pyramid, edge cases, security | 1 blocking, 6 warnings |
| UX Specialist | Layout, composing indicator, accessibility | 1 critical, 4 major |

**Result:** 8 blocking issues identified and fixed in the main plan.

### Round 2 — Seam Review (5 reviewers)

Cross-spec interface analysis after sub-specs were written.

**Result:** 18 seam issues found (7 critical, 11 high). All 18 fixed in specs.

### Round 3 — Re-Review (5 reviewers)

Verification pass after seam fixes applied.

**Result:** 18/18 original issues confirmed resolved. 6 new issues (R1-R6)
found and fixed. Spec-plan drift identified — plan sync in progress.

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Modular monolith (not microservices) | Single deployable for v1; Protocol interfaces designed for later extraction |
| Server-side LLM composer | Backend owns the tool loop; model can't bypass platform controls |
| FastAPI lifespan for async services | Python 3.12+ compatible; ProgressBroadcaster needs `get_running_loop()` |
| SQLAlchemy Core (not ORM) | Consistent with existing Landscape; SQLite dev / Postgres prod |
| WebSocket auth via query parameter | Browser WebSocket API doesn't support custom headers; close code 4001 for auth failure |
| Indeterminate progress bar | Engine doesn't know total row count in advance; counters provide signal |
| CompositionState as frozen dataclass | Domain model authority in `composer/state.py`; `to_dict()` for serialisation |
| 404 for IDOR (not 403) | Prevents leaking resource existence |

---

## Known Deferred Items

These are documented decisions to defer, not forgotten gaps:

| Item | Deferred To | Reason |
|------|-------------|--------|
| Governance tiers | v2 | No users yet; validation gate is sufficient for MVP |
| Live preview execution | v2 | Dry-run validation is the MVP preview |
| Graph editing | v2 | Chat-first is the primary interaction |
| Multi-tenant isolation | v2 | Single-tenant target (2-5 users) |
| Redis Streams telemetry | v2 | In-process WebSocket forwarding for v1 |
| Temporal workflows | v2 | SessionService is the integration point |
| Frontend tests | v1.1 | W17 — add Vitest + React Testing Library |
| Stage 2 validation persistence | v1.1 | Frontend-only gate for now; matters for governance |
| Stuck run reaper | v1.1 | `_on_pipeline_done` callback is the v1 safety net |

---

## Execution Status

| Phase | Status | Notes |
|-------|--------|-------|
| 1. Foundation | Ready to execute | 880 lines, 4 tasks, synced with spec |
| 2. Auth & Sessions | Plans synced, needs L3 decomposition | 4,021 lines, 12+ tasks |
| 3. Catalog | Ready to execute (after Phase 1) | 804 lines, 2 tasks, synced with spec |
| 4. Composer | Plans synced, needs L3 decomposition | 3,635 lines, 8+ tasks |
| 5. Execution | Plans synced, needs L3 decomposition | 2,784 lines, 8+ tasks |
| 6. Frontend | Plans synced, needs L3 decomposition | 3,717 lines, 15+ tasks |

**Next action:** Execute Sub-Plan 1 (Foundation).
