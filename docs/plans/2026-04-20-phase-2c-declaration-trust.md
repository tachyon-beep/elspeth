# Phase 2C Declaration-Trust Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Land the paired Phase 2C boundary adopters, `SourceGuaranteedFieldsContract` and `SinkRequiredFieldsContract`, on the ADR-010 framework without losing row-level attribution, without regressing source/sink audit semantics, and without collapsing the existing sink transactional backstop into the new pre-write contract layer.

**Architecture:** Phase 2C should use the existing `boundary_check` dispatch surface, but the current placeholder boundary bundle is not yet sufficient for row-attributed production violations. The implementation should refine the boundary inputs around real source/sink execution seams, run boundary checks per row rather than per batch, preserve the sink’s two-layer architecture, and land both source and sink adopters together in one PR as required by ADR-010’s paired-landing rule.

**Tech Stack:** Python, pytest, Hypothesis, mypy, ruff, Filigree, ADR-010 declaration-contract registry/dispatcher, Landscape integration tests.

**Prerequisites:**
- Work on a branch/worktree that already contains the H2/N1/N3 boundary-dispatch framework landing in code.
- Prefer the explicit declaration-contract bootstrap import surface from the Phase 2B plan; if it has not landed yet, include that prerequisite in the 2C branch before adding the first boundary adopter.
- Treat ADR-010, the current source/sink executors, and the current Filigree tickets as potentially divergent sources; verify repo reality before writing code.

---

## Reality Anchors

These are the current repo facts the plan assumes:

1. The `boundary_check` dispatch site exists, but it is not wired into production source or sink execution yet.
   - `run_boundary_checks(...)` is present in [declaration_dispatch.py](/home/john/elspeth/src/elspeth/engine/executors/declaration_dispatch.py:226).
   - No production source or sink path currently calls it.

2. The current placeholder `BoundaryInputs` shape is good enough for H2 wiring but not yet good enough for production row-attributed contracts.
   - It currently carries `plugin`, `node_id`, `run_id`, `static_contract`, and `rows`, but no `row_id`, no `token_id`, and no contract context ([declaration_contracts.py](/home/john/elspeth/src/elspeth/contracts/declaration_contracts.py:294)).
   - `DeclarationContractViolation` requires `row_id` and `token_id` at construction time ([declaration_contracts.py](/home/john/elspeth/src/elspeth/contracts/declaration_contracts.py:476)).

3. Source-side boundary validation cannot run before identity exists if we want normal declaration-contract audit records.
   - Valid source rows exist first as `SourceRow` values in the orchestrator loop.
   - `RowProcessor.process_row()` creates the initial token, and `_record_source_and_start_traversal()` records the source node state afterward ([processor.py](/home/john/elspeth/src/elspeth/engine/processor.py:1446), [processor.py](/home/john/elspeth/src/elspeth/engine/processor.py:1389)).

4. Sink-side boundary validation must run before schema validation if we want correct attribution.
   - `SinkExecutor.write()` currently calls `_validate_sink_input(...)` before `sink.write(...)` ([sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py:397)).
   - `_validate_sink_input(...)` does schema validation first, then the inline transactional backstop. If the 2C layer 1 contract is called after that, missing required fields will still be attributed as a generic `PluginContractViolation`.

5. The sink’s inline Layer 2 transactional backstop already exists in code and must remain distinct from the new 2C contract.
   - `SinkTransactionalInvariantError` is already defined ([errors.py](/home/john/elspeth/src/elspeth/contracts/errors.py:856)).
   - `_validate_sink_input(...)` already documents the two-layer architecture ([sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py:172)).

6. Source guaranteed fields are not normalized onto a runtime source attribute today.
   - The DAG builder reads producer guarantees from raw schema config.
   - Sources hold schema state via `_schema_config` / `get_schema_contract()`, but `BaseSource` and `SourceProtocol` do not currently expose a runtime `declared_guaranteed_fields`-style attribute.

7. Boundary adopters must land together.
   - ADR-010’s paired-landing rule explicitly says `SourceGuaranteedFieldsContract` and `SinkRequiredFieldsContract` land in one commit/PR, not staggered boundary adopters ([adr/010-declaration-trust-framework.md](/home/john/elspeth/docs/architecture/adr/010-declaration-trust-framework.md:257)).

## Recommended Boundary Shape Decision

Before implementing either contract, make one narrow framework refinement:

**Recommendation:** keep a single `boundary_check` dispatch surface, but refine the boundary input shape to support row-level identity and contract context. Do not keep the current rows-only placeholder if it forces synthetic row identities or non-standard violation classes.

The minimum useful payload for a production boundary check is:

```python
@dataclass(frozen=True, slots=True)
class BoundaryInputs:
    plugin: Any
    node_id: str
    run_id: str
    row_id: str
    token_id: str
    static_contract: frozenset[str]
    row_data: Any
    row_contract: Any | None = None
```

This plan assumes `run_boundary_checks(...)` will be invoked once per row, not once per batch, on both source and sink paths. That keeps the standard `DeclarationContractViolation` shape honest and avoids inventing aggregate row identities.

If the implementation team concludes the single refined bundle is still too awkward, split it into `SourceBoundaryInputs` and `SinkBoundaryInputs` in the same PR. Do not leave the placeholder shape half-refined.

## Task 0: Verify Prerequisites and Reconcile Board vs Workspace

**Files:**
- Read: `docs/architecture/adr/010-declaration-trust-framework.md`
- Read: `src/elspeth/contracts/declaration_contracts.py`
- Read: `src/elspeth/engine/executors/declaration_dispatch.py`
- Read: `src/elspeth/engine/processor.py`
- Read: `src/elspeth/engine/executors/sink.py`
- Test: `tests/unit/engine/test_declaration_dispatch.py`
- Test: `tests/unit/engine/test_orchestrator_registry_bootstrap.py`

**Step 1: Run framework smoke tests first**

Run:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/unit/engine/test_declaration_dispatch.py \
  tests/unit/engine/test_orchestrator_registry_bootstrap.py
```

**Expected result:** all tests pass before any 2C work starts.

**Step 2: Reconcile tracked siblings with current code**

- Confirm whether `elspeth-5fc876138d` should already be closed, since the `SinkTransactionalInvariantError` class and sink-layer comments are present in code.
- Confirm whether the explicit contract bootstrap from the 2B plan has landed. If not, make it a prerequisite task in this branch.
- Confirm the current state of `elspeth-425047a599` and `elspeth-60890a7388`; if the code already satisfies their acceptance criteria, update Filigree before starting the 2C paired adopter PR.

**Definition of Done:**
- [ ] The branch proves boundary dispatch infrastructure is present and green.
- [ ] Filigree drift that would confuse 2C implementation is identified up front.
- [ ] The paired landing will not be blocked by already-landed-but-open prerequisites.

## Task 1: Refine Boundary Inputs Around Row-Level Identity

This task should land before either adopter contract body is written.

**Files:**
- Modify: `src/elspeth/contracts/declaration_contracts.py`
- Modify: `src/elspeth/engine/executors/declaration_dispatch.py`
- Modify: `tests/unit/engine/test_declaration_dispatch.py`
- Create: `tests/unit/engine/test_boundary_dispatch_inputs.py`

**Implementation goals:**
- Refine the boundary bundle to carry real row identity.
- Keep `run_boundary_checks(...)` as the public wrapper.
- Preserve the shared `_dispatch(...)` helper and per-site registry behavior.

**Recommended implementation:**
- Add `row_id` and `token_id` to `BoundaryInputs`.
- Replace the plural placeholder with either `row_data` + `row_contract`, or keep `rows` only if it is always a one-element tuple and still carries separate identity fields.
- Update the boundary bundle docstrings so they describe the actual 2C call posture, not the H2 placeholder.

**Tests to write first:**
- Boundary bundle rejects missing identity fields.
- `run_boundary_checks(...)` dispatches only contracts marked for `boundary_check`.
- Existing non-boundary contracts remain unaffected.

Run:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/unit/engine/test_declaration_dispatch.py \
  tests/unit/engine/test_boundary_dispatch_inputs.py
```

**Definition of Done:**
- [ ] The boundary input shape can support normal `DeclarationContractViolation` construction.
- [ ] The boundary site remains a single dispatcher surface.
- [ ] The refined shape is documented as production truth, not placeholder speculation.

## Task 2: Normalize Source Guarantees Onto a Runtime Attribute

Phase 2C should not make `SourceGuaranteedFieldsContract` reach into private source internals or raw config dicts.

**Files:**
- Modify: `src/elspeth/plugins/infrastructure/base.py`
- Modify: `src/elspeth/contracts/plugin_protocols.py`
- Modify: `src/elspeth/plugins/sources/text_source.py`
- Modify: relevant concrete source plugins that set `_schema_config`
- Create: `tests/unit/plugins/sources/test_declared_guaranteed_fields.py`

**Recommendation:**

Add a runtime source attribute parallel to sink required fields:

```python
declared_guaranteed_fields: frozenset[str] = frozenset()
```

Populate it at source construction time from the source’s effective schema-config guarantees, after any source-specific schema rewrites such as the TextSource observed-mode heuristic.

**Why this matters:**
- The DAG builder can keep using raw config.
- The runtime contract gets a stable, attribute-based surface.
- The source contract body stays simple and does not need plugin-specific knowledge.

**Tests to write first:**
- Fixed/flexible/observed sources populate the attribute from effective guarantees.
- TextSource’s heuristic rewrite is reflected in the runtime attribute.
- Sources with no explicit guarantees expose an empty set.

Run:

```bash
PYTHONPATH=src uv run pytest -q tests/unit/plugins/sources/test_declared_guaranteed_fields.py
```

**Definition of Done:**
- [ ] `BaseSource` / `SourceProtocol` expose a runtime guarantee attribute.
- [ ] Source runtime declarations are derived after any source-specific config rewrite.
- [ ] Future source boundary contracts no longer need to read private `_schema_config` state.

## Task 3: ADR and Implementation for `SourceGuaranteedFieldsContract`

This contract should land in the same PR as Task 4, but its ADR and tests can be developed in parallel once Task 1 and Task 2 are done.

**Files:**
- Create: `docs/architecture/adr/016-source-guaranteed-fields-contract.md`
- Create: `src/elspeth/engine/executors/source_guaranteed_fields.py`
- Modify: `src/elspeth/contracts/errors.py`
- Modify: `src/elspeth/engine/processor.py`
- Modify: `src/elspeth/engine/executors/declaration_contract_bootstrap.py`
- Modify: `tests/invariants/test_contract_negative_examples_fire.py`
- Create: `tests/unit/engine/test_source_guaranteed_fields_contract.py`
- Create: `tests/integration/audit/test_source_guaranteed_fields_roundtrip.py`

**ADR decisions to record:**
- `SourceGuaranteedFieldsViolation` should be Tier 1. A source that lies about guaranteed fields poisons downstream propagation and audit lineage.
- The runtime observation should be the intersection of emitted row payload keys and the emitted row contract fields, not payload keys alone.
- The contract should apply only to valid source rows, never quarantined rows.
- Resume runs should not re-run source boundary validation, because the source boundary was already crossed in the original run.

**Suggested runtime invariant:**

```python
runtime_contract_fields = frozenset(fc.normalized_name for fc in inputs.row_contract.fields)
runtime_payload_fields = frozenset(inputs.row_data.keys())
runtime_observed = runtime_contract_fields & runtime_payload_fields
missing = inputs.static_contract - runtime_observed
```

**Call-site recommendation:**
- Do not run this in the orchestrator loop before token creation.
- Create the token first in `RowProcessor.process_row()`, then run the boundary check using real `row_id` and `token_id`, then record the source node state as `COMPLETED` or `FAILED` depending on the outcome.
- Refactor `_record_source_and_start_traversal()` or add a guarded helper so source-boundary failures still produce a source node state rather than disappearing before audit recording.

**Red tests:**
- Valid source row payload lacks a declared guaranteed field -> `SourceGuaranteedFieldsViolation`.
- Source row payload contains the key but the emitted contract omits it -> violation.
- Quarantined source rows do not invoke the contract.
- Resume path does not invoke the contract.

Run:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/unit/engine/test_source_guaranteed_fields_contract.py \
  tests/integration/audit/test_source_guaranteed_fields_roundtrip.py
```

**Definition of Done:**
- [ ] ADR-016 lands and states the violation class, payload schema, and source-side call posture.
- [ ] Source boundary violations are row-attributed and source-node-attributed in Landscape.
- [ ] Valid source rows proceed unchanged when the guarantee contract passes.

## Task 4: ADR and Implementation for `SinkRequiredFieldsContract`

This contract must be implemented together with Task 3 in the same PR.

**Files:**
- Create: `docs/architecture/adr/017-sink-required-fields-contract.md`
- Create: `src/elspeth/engine/executors/sink_required_fields.py`
- Modify: `src/elspeth/engine/executors/sink.py`
- Modify: `src/elspeth/engine/executors/declaration_contract_bootstrap.py`
- Modify: `tests/invariants/test_contract_negative_examples_fire.py`
- Create: `tests/unit/engine/test_sink_required_fields_contract.py`
- Create: `tests/integration/audit/test_sink_required_fields_roundtrip.py`

**ADR decisions to record:**
- `SinkRequiredFieldsViolation` should be Tier 1, as the framework-owned Layer 1 intent validation.
- Layer 1 and Layer 2 must stay distinct:
  - Layer 1: `SinkRequiredFieldsViolation` via boundary dispatch.
  - Layer 2: `SinkTransactionalInvariantError` via the existing inline backstop.
- The contract should run for both primary sink writes and failsink writes, because failsinks are still sink boundaries and the current Layer 2 backstop already covers both paths.

**Recommended call posture:**
- Run `run_boundary_checks(...)` per token/row before `_validate_sink_input(...)` in both:
  - the primary sink path in `SinkExecutor.write()`
  - the failsink path before `failsink.write(...)`
- Keep `_validate_sink_input(...)` in place as the Layer 2 backstop.
- Do not delete the inline transactional assertion.

**Why call it before `_validate_sink_input(...)`:**
- If the row is missing a sink-required field, `input_schema.model_validate(...)` can otherwise raise first and mask the declaration-contract attribution.
- Layer 1 must own missing-required-field attribution; Layer 2 remains the “state diverged before commit” backstop.

**Suggested contract surface:**
- Use the sink’s existing `declared_required_fields`.
- Prefer row payload membership as the primary predicate, with optional row-contract context only for richer error messaging.

**Red tests:**
- Primary sink path: missing required field -> `SinkRequiredFieldsViolation` before schema validation.
- Failsink path: enriched row missing a failsink-required field -> `SinkRequiredFieldsViolation`.
- Divergence case after Layer 1 passes still reaches `SinkTransactionalInvariantError` from the inline backstop.

Run:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/unit/engine/test_sink_required_fields_contract.py \
  tests/integration/audit/test_sink_required_fields_roundtrip.py
```

**Definition of Done:**
- [ ] ADR-017 lands and states the two-layer sink architecture explicitly.
- [ ] Layer 1 is invoked before schema validation and before external sink I/O.
- [ ] Primary sink and failsink paths are both covered.
- [ ] Layer 2 remains intact and distinguishable in audit records.

## Task 5: Paired-Landing Verification and Filigree Cleanup

**Files:**
- Modify: `tests/invariants/test_contract_negative_examples_fire.py`
- Modify: `tests/integration/audit/test_declaration_contract_landscape_roundtrip.py`
- Modify: `tests/unit/engine/test_orchestrator_registry_bootstrap.py`
- Modify: `tests/performance/benchmarks/test_cross_check_overhead.py`
- Modify: `docs/architecture/adr/010-declaration-trust-framework.md` only if adoption-state text needs factual updates
- Modify: relevant Filigree issues with close notes and dependency cleanup

**Verification checklist:**
- Both 2C contracts are in `EXPECTED_CONTRACT_SITES` under `boundary_check`.
- Both contracts have `negative_example()` and `positive_example_does_not_apply()`.
- Both contracts have end-to-end Landscape round-trip coverage.
- Source boundary checks are skipped on resume.
- Sink boundary checks run on primary and failsink paths.
- The benchmark still passes with the two new boundary adopters registered.

Run:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/invariants/test_contract_negative_examples_fire.py \
  tests/unit/engine/test_orchestrator_registry_bootstrap.py \
  tests/integration/audit/test_declaration_contract_landscape_roundtrip.py \
  tests/performance/benchmarks/test_cross_check_overhead.py
```

Then run:

```bash
uv run ruff check src tests
uv run mypy src
```

**Definition of Done:**
- [ ] Both 2C adopters land together and are mechanically registered.
- [ ] The invariant harness and Landscape round-trip tests both cover them.
- [ ] Filigree reflects the paired landing and no longer treats the source/sink contracts as separate pending boundary subtypes.

## Recommended Landing Order

1. Task 0: verify prerequisites and reconcile board/workspace drift.
2. Task 1: refine boundary inputs around row-level identity.
3. Task 2: normalize source guarantees onto a runtime attribute.
4. Task 3 and Task 4: land `SourceGuaranteedFieldsContract` and `SinkRequiredFieldsContract` together in one PR.
5. Task 5: cross-cutting verification, adoption-state updates, and Filigree cleanup.

## Risks and Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Boundary bundle stays rows-only and cannot support standard declaration-violation identity | Refine boundary inputs before writing adopter bodies; do not fake row IDs. |
| Source boundary validation runs before token creation and loses audit attribution | Run source boundary checks after token creation and integrate them with source node-state recording. |
| Sink required-field failures are still attributed as schema validation bugs | Invoke Layer 1 boundary checks before `_validate_sink_input(...)`. |
| Layer 1 and Layer 2 sink checks collapse back into one signal | Keep `SinkRequiredFieldsViolation` and `SinkTransactionalInvariantError` distinct and test both paths. |
| Failsink path drifts from primary sink path | Run boundary checks in both primary and failsink write flows. |
| Source runtime guarantees drift from DAG-view guarantees | Normalize source guarantees into a runtime attribute after any source-specific schema rewrite. |
| Resume path accidentally re-validates source boundary conditions | Add explicit resume-path regression tests and document that source boundary validation is single-run only. |

## Execution Notes

- Land both 2C adopters in one PR. The paired-landing rule is architectural, not cosmetic.
- Keep each adopter self-contained inside that PR: ADR, violation class, contract module, call-site wiring, manifest update, negative-example coverage, round-trip test, and Filigree note.
- If boundary-shape refinement grows beyond the “identity + contract context” change, pause and amend ADR-010 explicitly rather than letting the production code become the de facto spec.
