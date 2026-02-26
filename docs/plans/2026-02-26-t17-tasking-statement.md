# T17 Tasking Statement: Split PluginContext into Phase-Based Protocols

> **For Claude:** This is a tasking statement for executing a reviewed implementation plan.
> REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.
> Read each sub-plan file IN FULL before executing its tasks.

## Mission

Decompose the 19-field `PluginContext` god-object into 4 phase-based protocols (`SourceContext`, `TransformContext`, `SinkContext`, `LifecycleContext`), enforcing interface segregation across all plugins. The concrete `PluginContext` class stays — protocols narrow the read surface for plugins; executors keep the concrete type for mutation.

## Filigree References

| Item | ID | Status |
|------|----|--------|
| **This task** | `elspeth-rapid-c42eca` | `approved` → transition to `building` before starting |
| **Parent epic** | `elspeth-rapid-d7f75f` | RC3.3 Architectural Remediation (in_progress) |
| **Blocked by** | — | UNBLOCKED — no dependencies |
| **Blocks** | `elspeth-rapid-223c2f` | T22: Plugin registry pattern |

**Claim the task before starting:**
```bash
filigree update elspeth-rapid-c42eca --status=building
```

## Branch

Work on the current branch: `RC3.3-architectural-remediation`

## Plan Files (read these, they are the source of truth)

All plans are in `docs/plans/` and have been reviewed by a 4-agent panel (Architecture Critic, Systems Thinker, Quality Analyst, Reality Checker). Review findings are annotated inline with IDs like `[B1]`, `[W1]`, `[R1]`, `[N1]`.

| Phase | Plan File | Effort | Risk |
|-------|-----------|--------|------|
| Design | `2026-02-26-t17-plugincontext-protocol-split-design.md` | — | — |
| Master | `2026-02-26-t17-master-plan.md` | — | — |
| **Phase 0: Cleanup** | `2026-02-26-t17-phase0-cleanup.md` | S | Low |
| **Phase 1: Protocols** | `2026-02-26-t17-phase1-protocols.md` | M | Med |
| **Phase 2-3: Signatures & Plugins** | `2026-02-26-t17-phase2-3-signatures-plugins.md` | L | Med-High |
| **Phase 4: Engine** | `2026-02-26-t17-phase4-engine.md` | M | High |
| **Finishing** | `2026-02-26-t17-finishing.md` | L | Low |

## Execution Order

```text
Phase 0 ──→ Phase 1 ──→ Phase 2-3 ──→ Phase 4 ──→ Finishing
(cleanup)   (protocols)  (plugins)     (engine)    (tests+gate)
```

Each phase is a **commit boundary**. The full quality gate must pass before proceeding to the next phase.

### Phase 0: Remove Dead Fields (6 tasks)

Delete 4 dead fields (`plugin_name`, `llm_client`, `http_client`, `tracer`) and 2 unused methods (`start_span()`, `get()`) from `PluginContext`. Reduces surface from 19→15 fields.

**Key review finding [B1]:** Two contract test base fixtures pass `plugin_name="test"` and will break:
- `tests/unit/contracts/transform_contracts/test_transform_protocol.py:92`
- `tests/unit/contracts/source_contracts/test_source_protocol.py:67`

These MUST be fixed in Task 1 alongside the field removal.

**Commit message pattern:** `refactor(T17): Phase 0 — remove 4 dead fields + 2 unused methods from PluginContext`

### Phase 1: Define Protocols + Alignment Tests (7 tasks)

Create `contracts/contexts.py` with 4 `@runtime_checkable` Protocol classes. Write alignment tests modeled on `test_config_alignment.py`.

**Key review findings applied:**
- `[R1]` `LifecycleContext` includes `node_id` (set by orchestrator before `on_start()`, zero cost to include now)
- `[R2]` Discrimination tests use real minimal `@dataclass` objects, not just set arithmetic
- `[R3]` Field coverage tests use mechanical introspection (`__dataclass_fields__`) with bidirectional verification + explicit `EXECUTOR_ONLY_FIELDS` / `ENGINE_INTERNAL_METHODS` allowlists
- `[R4]` Engine-internal methods (`record_transform_error()`) documented in protocol module comment
- `[N7]` `isinstance()` only checks names — mypy is the real structural conformance guard

**Commit message pattern:** `refactor(T17): Phase 1 — define 4 phase-based context protocols + alignment tests`

### Phase 2-3: Update Plugin Signatures & Implementations (9 tasks + 1 sub-checkpoint)

Update plugin protocols, base classes, and all 19 concrete plugin implementations. This is the largest phase.

**Sub-checkpoint [W3]:** After Task 4 (simple transforms — 7 files, signature-only), commit separately before entering Tasks 5-6 (complex + LLM transforms with logic changes). This reduces blast radius if complex work stalls.

**Key review findings applied:**
- `[W1]` Before removing defensive fallbacks in `prompt_shield.py`/`content_safety.py`, audit tests for any that call `process()`/`accept()` without `on_start()` — those tests will break
- `[W2]` `blob_sink._resolve_display_headers_if_needed` (accesses `ctx.landscape`) added to the helper list for Task 7
- `[N3]` `web_scrape.py` refactor moves crash from row-time to start-time (strictly better, but behavioral change — verify integration tests cover `on_start()`)
- `[R6]` `payload_store` is not wired in orchestrator `PluginContext` constructions (pre-existing issue — T17 surfaces it earlier)

**Commit message pattern (2 commits):**
1. `refactor(T17): Phase 2-3 checkpoint — narrow simple transform signatures`
2. `refactor(T17): Phase 2-3 — narrow all plugin signatures to phase-based protocols`

### Phase 4: Update Engine Layer (6 tasks)

Verify executors/orchestrator/processor compatibility. Executors keep `PluginContext` (concrete) for mutation. This phase is primarily verification — minimal code changes expected.

**Key note [R4]:** `record_transform_error()` is called by executors and processor but is intentionally absent from all protocols. It's engine-internal.

**Commit message pattern:** `refactor(T17): Phase 4 — verify engine layer compatibility with protocol-typed plugins`

### Finishing: Test Updates + Verification Gate (8 tasks)

Update test infrastructure, run full verification, close ticket.

**Key review finding [R5]:** When fixing `_TestablePluginContext` subclass signatures, use exact signature match — do NOT use `**kwargs: object` (creates permanent mypy blind spot).

**Commit message patterns:**
1. `test(T17): update test infrastructure for protocol-typed context`
2. `docs(T17): document protocol split in ARCHITECTURE.md`

**Close the ticket:**
```bash
filigree close elspeth-rapid-c42eca --reason="T17 PluginContext protocol split complete. 4 phase-based protocols defined in contracts/contexts.py. All 19 plugins narrowed. Full suite passes."
```

## Quality Gate (run after every phase)

```bash
.venv/bin/python -m pytest tests/ -x --timeout=120    # All tests pass
.venv/bin/python -m mypy src/                          # Type checking clean
.venv/bin/python -m ruff check src/                    # Linting clean
.venv/bin/python -m scripts.check_contracts            # Config contracts pass
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
```

**All 5 checks must pass before proceeding to the next phase or committing.**

## Key Design Constraints (non-negotiable)

1. **Concrete `PluginContext` stays.** Executors mutate it. Protocols are read-only views.
2. **`record_call()` implementation stays on concrete class.** Protocols expose the method signature only.
3. **`on_start()`/`on_complete()` → `LifecycleContext`** (wider). `process()`/`write()`/`load()` → narrower phase context.
4. **Executors keep accepting `PluginContext`** (concrete) — they write to it.
5. **~444 test constructions don't change** — concrete class satisfies all 4 protocols.
6. **No defensive programming patterns** — if `on_start()` wasn't called, let it crash (CLAUDE.md).
7. **No legacy code / backwards compat** — this is pre-1.0.

## What NOT To Do

- Do NOT create gate plugins (hard prohibition — see MEMORY.md)
- Do NOT add `**kwargs` to test subclass overrides (use exact signatures) [R5]
- Do NOT add defensive fallbacks for missing `on_start()` calls [W1]
- Do NOT use hardcoded string lists in coverage tests (use `__dataclass_fields__` introspection) [R3]
- Do NOT run git commands from subagents (hard prohibition — see MEMORY.md)
- Do NOT stash or revert files without asking (hard prohibition)

## Stopping Points

If you encounter unexpected state at any point, STOP and report. Safe stopping points between phases:

| After | State | Safe to stop? |
|-------|-------|---------------|
| Phase 0 | Dead fields removed, surface reduced | Yes — clean, no protocols yet |
| Phase 1 | Protocols defined + tested, no plugins changed | Yes — purely additive |
| Phase 2-3 (sub-checkpoint) | Simple transforms narrowed | Yes — 7 low-risk files committed |
| Phase 2-3 (full) | All 19 plugins narrowed | Yes — most value delivered |
| Phase 4 | Engine verified compatible | Yes — ready for test cleanup |
| Finishing | Everything done | Close ticket |

## Session Boundaries

This plan is designed for multi-session execution. Each phase can be a separate session. If starting a new session mid-plan:

1. Run `filigree show elspeth-rapid-c42eca` to check status
2. Run `git log --oneline -5` to see what phases are already committed
3. Run the quality gate to verify current state is green
4. Read the next phase's plan file IN FULL before starting
5. Continue from the next uncommitted phase
