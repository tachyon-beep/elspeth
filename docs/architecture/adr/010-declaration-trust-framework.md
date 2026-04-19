# ADR-010: Declaration-trust framework — generalized contract protocol for plugin declarations

**Date:** 2026-04-19
**Status:** Accepted
**Deciders:** John Morrissey (author); five-reviewer panel (solution-architect, systems-thinker, python-engineer, quality-engineer, security-architect) per session `/home/john/.claude/plans/elspeth-track-2-phase-2a-declaration-framework.review.json`
**Supersedes:** (partial, clause-level) — see "Supersession map" below
**Tags:** framework, declaration-contract, audit-evidence, tier-1, registry, audit-integrity
**Review date:** 2026-10-19 (six months from acceptance; ADR-010 §Consequences must be re-evaluated against observed 2B/2C experience by that date)
**Filigree epic:** <Track-2 epic ID filled in during Task 13; hard SLA 2026-07-18>

## Supersession map

This ADR amends (not replaces) the single-declaration pattern from 007/008/009:

| Prior clause | Status under ADR-010 |
|--------------|----------------------|
| ADR-007 §Decision 1-3 | Remain normative for `passes_through_input`. New declarations use the ADR-010 framework. |
| ADR-007 §Negative Consequences #2 (duplicated walkers) | Resolved by ADR-009 §Clause 1. ADR-010 does not re-visit. |
| ADR-008 §"cross-check applies per-row in executor" | Generalised — the ADR-010 dispatcher replaces direct executor calls. Scope per-row preserved. |
| ADR-008 §Explicit scope boundary | Normatively remains; ADR-010 provides the framework each future declaration adopts, but each new declaration still requires its own ADR. |
| ADR-009 §Clause 1 (shared propagation primitives) | Remains normative. ADR-010 does NOT include `static_check` in the 2A protocol — the walker refactor is deferred entirely to Phase 2B. |
| ADR-009 §Clause 2 (runtime cross-check batch path) | Remains normative. ADR-010's dispatcher preserves the single-token and batch-flush call sites. |
| ADR-009 §Clause 3 (empty-emission carve-out + 90-day SLA) | Remains normative. The Track 2 filigree epic (ref above) anchors the SLA. |
| ADR-009 §Clause 4 (invariant harness) | ADR-010 extends — harness iterates registered contracts and exercises every `negative_example`. |

## Context

ADRs 007, 008, and 009 established a single-declaration implementation of the "declare + statically trust + runtime-verify" pattern for `passes_through_input`. The pattern generalises: each plugin declaration the DAG validator trusts today (`creates_tokens`, `declared_output_fields`, `declared_required_fields`, `output_schema_config.mode`, source `guaranteed_fields`, sink `required_fields`) has the same gap ADR-008 closed for pass-through — static analysis trusts with no runtime backstop; mis-annotation silently corrupts Tier-1 audit data.

ADR-008 §Explicit scope boundary deferred the wider class. ADR-010 generalises the pattern into a framework that future declarations adopt in ~200 LOC per declaration, without duplicating the static/runtime/invariant trio.

**Rule-of-three satisfaction:** ADR-009 §Alternatives Considered #1 rejected "DeclarationContract protocol up front" as premature abstraction. ADR-010 satisfies rule-of-three by paper-sketching `DeclaredOutputFieldsContract` against the protocol during Task 0 (before Task 1 implementation) — if the sketch exposes protocol gaps, they are closed in Tasks 1–5. The protocol shape in 2A reflects what the sketch validated, plus what Phase 2B's `CreatesTokensContract` preview (Task 11) exercised.

## Decision

Three new framework primitives in L0 `contracts/`, one L2 dispatcher, migrations of the four existing Tier-1 exceptions into the decorator-registry pattern, and nominal AuditEvidence widening of `NodeStateGuard`.

### Decision 1 — `AuditEvidenceBase` nominal abstract base class

Replaces the bespoke `PluginContractViolation.to_audit_dict()` discriminator. Violation classes MUST inherit `AuditEvidenceBase` explicitly to contribute structured context via `NodeStateGuard.__exit__`. Nominal (not structural) because a `@runtime_checkable` Protocol with one method admits accidental duck-type matches — this was the Critical finding from the security review (spoofing audit evidence via incidental `to_audit_dict` methods on unrelated classes). CI scanner `enforce_audit_evidence_nominal.py` enforces at build time.

### Decision 2 — `@tier_1_error(reason=...)` factory decorator + frozen registry

Replaces the hand-maintained `TIER_1_ERRORS` tuple. Three safeguards beyond decoration-is-registration:
1. **Required `reason` kwarg** (justification is queryable; grep-visible; ADR-cross-referenceable).
2. **Module-prefix allowlist** — only `elspeth.contracts.*`, `elspeth.engine.*`, `elspeth.core.*` callers. Plugin authors cannot unilaterally elevate their exceptions to Tier-1.
3. **`freeze_tier_registry()`** — called at end of orchestrator bootstrap; registration after freeze raises `FrameworkBugError`.

`errors.TIER_1_ERRORS` is a module `__getattr__` returning the live `tuple(tier_registry._REGISTRY)` — not a snapshot. Call sites doing `from elspeth.contracts.errors import TIER_1_ERRORS` at import time see the tuple at the moment of access (caveat: Python's `from X import Y` binds the local name to the value produced, which for a module `__getattr__` is a fresh call — the `except TIER_1_ERRORS:` clause evaluates the name `TIER_1_ERRORS` on each `except` entry, not at import, so this works correctly).

### Decision 3 — `DeclarationContract` protocol + frozen registry

Runtime-checkable protocol carrying:
- `name: str`
- `applies_to(plugin) -> bool`
- `runtime_check(inputs, outputs) -> None`
- `payload_schema: type[TypedDict]` (secrets scrubbed before audit serialization)
- `negative_example() -> tuple[RuntimeCheckInputs, RuntimeCheckOutputs]` (classmethod; harness asserts it fires the contract's violation)

`static_check` is NOT in the 2A protocol. Walker refactor is fully Phase 2B scope — designing a `static_check` shape without a second real walker-aware declaration would be premature abstraction (the ADR-009 §Alternatives #1 concern). Phase 2B's first declaration will validate the walker-side extension.

Registry freezes at bootstrap; orchestrator asserts `len(registered_declaration_contracts()) >= 1` at the same point (non-empty invariant — prevents silent runtime VAL disable, which was reviewer B9's concern).

`DeclarationContractViolation` inherits `AuditEvidenceBase`, deep-freezes its payload in `__init__`, and runs `scrub_payload_for_audit` before returning `to_audit_dict`.

## Consequences

### Positive

- Phase 2B (transform-level declaration VALs) and Phase 2C (boundary VALs) each become ~200-LOC PRs that register a new contract; no executor, validator, or harness plumbing.
- Registry-driven invariant harness exercises every contract uniformly. New declaration = new contract = automatic invariant coverage.
- `negative_example()` requirement closes the dormant-`runtime_check` failure mode — a silently-returning `runtime_check` fails CI immediately.
- Audit evidence is contract-orthogonal. A future non-plugin Tier-1 exception (e.g., checkpoint-integrity violation) can contribute structured context without subclassing `PluginContractViolation`.
- TIER_1 registration is greppable at the class declaration site, requires a `reason`, and rejects plugin-module callers.
- Secret-scrubbing on payload serialization closes the audit-legal-record-as-secret-leak vector (reviewer F-4) defensively, independent of per-contract author discipline.

### Negative

- Indirection cost: per-row check path routes through `run_runtime_checks` iterating the registry. Negligible today (one registered contract; `applies_to` short-circuits). Task 12 benchmarks establish a dispatcher-overhead budget; the ADR-008 25 µs / 50 µs gate still applies to the total.
- Registration ordering: contracts register on module import. A test clearing the registry must re-import the modules or use the snapshot-restore pattern demonstrated in `test_framework_accepts_second_contract.py`. `_clear_registry_for_tests` raises in production.
- Nominal AuditEvidenceBase requires author discipline: new audit-evidence classes MUST inherit explicitly. CI scanner is the backstop.
- The v0 empty-emission carve-out (ADR-009 §Clause 3) still stands; ADR-010 does not tighten it. The 90-day SLA trigger (2026-07-18) remains the safeguard for moving to `can_drop_rows` before the next `passes_through_input` transform with external calls registers.

### Neutral

- `PassThroughContractViolation` continues to exist as a dedicated subclass with its 9-key payload; it co-exists with the generic `DeclarationContractViolation` to preserve triage SQL that filters on `exception_type = 'PassThroughContractViolation'`. New contracts may reuse the generic form or introduce their own subclass.
- Reversibility: the framework is additive — removing it would require unpicking all decorator usages and re-introducing the hand-written `TIER_1_ERRORS` tuple. Non-trivial but not destructive. Review date 2026-10-19 is the formal reversibility checkpoint.

## Alternatives Considered

### Alternative 1: leave the pattern as a template, re-type per declaration

Phase 2B/2C engineers copy ADR-008's pattern and implement `_cross_check_<declaration>` ad-hoc. Each copy drifts. The duplicate L1/L3 walker issue ADR-009 closed would recur at scale — across declarations instead of layers. The registry is the structural fix.

### Alternative 2: generate contracts from declarative YAML

A YAML schema enumerates declarations; a code-generator produces stubs. Rejected for the same reason ADR-007 §Alternative 1 rejected AST auto-detect: magic is inappropriate for audit-grade code. The generated contract becomes the source of truth but the declaration author doesn't read it.

### Alternative 3: `AuditEvidence` as a structural `@runtime_checkable` Protocol

Rejected. The five-reviewer panel's security review identified this as a Critical Spoofing (STRIDE S) finding: any class exposing `to_audit_dict()` would satisfy the structural protocol, including accidental matches from third-party libraries, test helpers, or unrelated plugin code. Nominal `AuditEvidenceBase` requires explicit author declaration and closes the spoofing vector.

### Alternative 4: defer the entire `DeclarationContract` protocol to Phase 2B

Considered seriously in review. Rejected because: (a) the nominal `AuditEvidenceBase` widening and `@tier_1_error` decorator have immediate cleanup value independent of the protocol; (b) Task 0's paper-sketch pre-flight validates the protocol shape before code is written, satisfying rule-of-three; (c) Task 11's `CreatesTokensContract` preview proves the shape works for the first real 2B case. The remaining residual risk (protocol reshape in 2B) is bounded by the small 2A protocol surface.

## References

- Plan: `/home/john/.claude/plans/elspeth-track-2-phase-2a-declaration-framework.md`
- Reviewer verdicts: `.review.json` alongside the plan file (5-reviewer panel, 2026-04-19)
- Predecessor ADRs: 007 (pass-through propagation), 008 (runtime cross-check), 009 (pathway fusion)
- Successor ADRs (Phase 2B/2C): each declaration gets its own ADR per §Supersession map ADR-008 reference
- CLAUDE.md §Three-Tier Trust Model, §Plugin Ownership, §Frozen Dataclass Immutability, §Defensive Programming Forbidden
- Track 2 filigree epic: <ID filled in during Task 13>; ADR-009 §Clause 3 SLA hard trigger 2026-07-18
