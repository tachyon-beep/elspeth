# RC4.2 UX Remediation — Wave 4 Nice-to-Have Subplan

Date: 2026-03-31
Status: Seed
Parent: `docs/plans/rc4.2-ux-remediation/2026-03-30-rc4.2-ux-implementation-plan.md`

---

## Scope

This subplan groups the P3 requirements that enhance the composer tooling and
introduce preview execution. None of these items block other work; they can be
implemented in any order once Wave 3 is complete.

Included requirements:

- `REQ-API-05` — clear source
- `REQ-API-06` — preview execution
- `REQ-API-08` — explain validation errors
- `REQ-API-09` — list available models

Primary surfaces:

- `CompositionState` mutation API
- composer tool definitions
- execution service (preview path)
- catalog/model discovery

---

## Goals

- Remove friction from common iterative editing patterns.
- Let users preview pipeline behaviour before committing to a full run.
- Improve the assistant's self-repair loop through richer error context and
  model discovery.

---

## Requirement Sketches

### REQ-API-05: Clear Source (TINY)

Add `CompositionState.without_source()` returning a new state with the source
removed. Expose as `clear_source` composer tool. Straightforward — mirrors
the existing `without_output()` pattern.

Files: `state.py` (new method), `tools.py` (new tool).

### REQ-API-06: Preview Execution (MEDIUM)

Two new tools: `preview_pipeline(max_rows?)` and
`preview_node_output(node_id, sample_rows)`.

Key constraints:

- Preview is explicitly non-destructive — no Landscape recording, no sink
  writes, no run record creation.
- Row limiting at source level (default 5 rows).
- Per-node output capture for full pipeline preview.
- The implementation plan recommends starting with source-only preview for v1:
  validate + run first N rows through source, return sample data. Full
  per-node preview deferred.

Risk: engine changes for preview mode. The v1 source-only approach avoids
engine coupling — it only needs to instantiate and run the source plugin,
which is already possible outside the orchestrator.

Files: `tools.py` (2 new tools), `execution/service.py` (preview path),
possibly engine changes for full preview.

### REQ-API-08: Explain Validation Errors (SMALL)

New discovery tool `explain_validation_error(error_text)` that maps common
error patterns to human-readable diagnoses with suggested fixes. Pattern
catalogue covers the ~8 error classes from `CompositionState.validate()` plus
common Stage 2 errors.

Implementation: a pattern-matching function over known error strings. No
external calls, no LLM involvement — this is a lookup table with regex
matching.

Files: `tools.py` (new tool + error pattern catalogue).

### REQ-API-09: List Models (SMALL)

New discovery tool `list_models(provider?)`. Returns available model IDs,
optionally filtered by provider. Implementation depends on configured
providers — may query LiteLLM's model list or return a curated static list
from config.

Open question: dynamic (query LiteLLM at runtime) vs static (curated list in
settings). Dynamic is more accurate but adds latency and a failure mode.
Recommend static list with an optional dynamic refresh.

Files: `tools.py` (new tool), possibly config additions for model list.

---

## Likely Decisions

- Start preview with source-only (no engine changes for v1).
- Use a static error pattern catalogue for explain, not LLM-generated
  explanations.
- Model listing from config with optional LiteLLM query.

---

## Dependencies

- Enhanced validation model (sub-plan 05) for richer error context in
  `explain_validation_error`.
- No hard blockers — all items are independently implementable.

---

## Open Questions

- Whether `preview_pipeline` should create a transient run record for
  observability, even if it's not persisted to Landscape.
- Whether `list_models` should validate that listed models are actually
  reachable (adds latency) or just return the configured list.
- Whether `clear_source` should also clear edges that reference the source's
  `on_success` target (cascading cleanup) or leave orphaned edges for the
  user/assistant to fix.

---

## Expansion Notes

When expanded into a full plan, include:

- preview execution architecture (source-only vs full per-node)
- error pattern catalogue content and matching strategy
- model list data source and refresh policy
- tool definitions with exact parameter and return shapes
