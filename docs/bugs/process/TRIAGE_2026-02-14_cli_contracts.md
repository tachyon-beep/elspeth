# Bug Triage: CLI + CLI-Helpers + Contracts — 2026-02-14

## Scope

Static analysis sweep produced 29 bug reports across three folders:
- `docs/bugs/open/cli/` (4 bugs)
- `docs/bugs/open/cli-helpers/` (1 bug)
- `docs/bugs/open/contracts/` (24 bugs)

All 29 were validated against source code. All are real findings (none false-positive).

## Triage Decisions

### Merges

| Merged Into | Deleted | Rationale |
|-------------|---------|-----------|
| `contractbuilder-process-first-row-crashes-on-dict-list-values-in-json-sources` | `schema-contract-with-field-crashes-on-nested-json-values` | Same root cause: `normalize_type_for_contract()` rejects dict/list, and both `ContractBuilder.process_first_row()` and `SchemaContract.with_field()` call it without fallback. Same fix location. |

### Closures

| Bug | Disposition |
|-----|-------------|
| `typing-whitelist-py-claims-to-be-the-exhaustive-soft-typing-whitelist` | Won't fix. Dead code — no consumers, real enforcement is in `config/cicd/contracts-whitelist.yaml`. Delete the file as a cleanup chore. Moved to `docs/bugs/closed/contracts/`. |

### Priority Upgrades (to P1)

| Bug | Original | New | Rationale |
|-----|----------|-----|-----------|
| `create-contract-from-config-can-build-an-internally-inconsistent-contract-mode-f` | P2 | P1 | FIXED contract starting unlocked is a silent enforcement failure. `locked = config.mode == "fixed"` uses raw input while mode is normalized to uppercase — non-canonical casing silently breaks schema strictness. |
| `update-checkpoint-does-not-actually-update-the-active-restored-checkpoint-path-s` | P2 | P1 | Checkpoint correctness is critical for resume. `update_checkpoint()` writes to `_checkpoint` but `get_checkpoint()` reads from `_batch_checkpoints[node_id]` first — updates invisible to readers after restore. |

### Priority Downgrades

| Bug | Original | New | Rationale |
|-----|----------|-----|-----------|
| `purge-retention-days-accepts-nonpositive-values` (cli) | P1 | P2 | Mitigated by `--yes` confirmation prompt and `--dry-run` option. |
| `normalize-type-for-contract-misclassifies-numpy-bytes-values-as-str` | P1 | P2 | Narrow practical impact — uncommon for sources to produce `np.bytes_` values. |
| `operation-contract-accepts-impossible-lifecycle-states` | P1 | P2 | Defense-in-depth for Tier 1 DB corruption; lifecycle states set by our own code paths, not an active failure mode. |
| `plugincontext-record-call-can-emit-the-wrong-token-id-in-telemetry` | P1 | P2 | Affects telemetry (ephemeral), not Landscape audit trail (Tier 1 source of truth). |
| `sanitized-url-types-can-be-constructed-with-secrets` | P1 | P2 | System-owned types, all callers are our code. Hardening, not a current vulnerability. |
| `secretresolution-has-no-runtime-validation-at-all` | P1 | P2 | Same rationale as Operation — defense-in-depth, only constructed from our own paths. |
| `tokeninfos-pipelinerow-annotations-are-not-runtime-resolvable` | P2 | P3 | Nothing in production calls `get_type_hints(TokenInfo)`. Introspection tooling only. |

## Final Counts (all three folders)

| Priority | Count |
|----------|-------|
| P1 | 13 |
| P2 | 12 |
| P3 | 2 |
| Closed | 1 |
| **Total open** | **27** |

## Cross-Cutting Patterns Observed

### 1. Asymmetric invariant enforcement
Success paths are well-validated (e.g., `TransformResult` checks `success_reason`), but error/failure paths are under-validated. This is a systemic gap across contracts.

**Affected bugs:** TransformResult error invariants, Operation lifecycle, ContractAuditRecord enum validation.

### 2. Type inference vs type compatibility disconnect
`normalize_type_for_contract()` is strict (rejects dict/list/unsupported types), but callers in contract propagation and contract building handle this inconsistently — some fall back to `object`, some skip, some crash. The Annotated-type unwrapping gap in `data.py._types_compatible()` is another facet of this.

**Affected bugs:** ContractBuilder dict/list crash, propagate_contract field drops, check_compatibility Annotated rejection, _get_python_type union collapse, unsupported annotation downgrade.

### 3. Tier 1 hardening gaps in audit dataclasses
Several audit dataclasses (`Operation`, `SecretResolution`) lack the `__post_init__` invariant validation that peer types (`Run`, `Node`, `Batch`, `TokenOutcome`) already have. These are individually low-risk (our code writes correct values) but collectively represent incomplete defense-in-depth for the audit trail.

**Affected bugs:** Operation lifecycle, SecretResolution, ContractAuditRecord.

### 4. Config boundary truthiness
`SchemaConfig.from_dict()` uses truthiness coercion on `required` field, which inverts boolean semantics for string values like `"false"`. This is a Tier 3 boundary where we should validate strictly.

### Fix Priority Recommendation

For maximum impact, fix these first:
1. **TransformResult error invariants** (#13) — writes partial Tier 1 data before crashing
2. **propagate_contract field drops** (#8) — contract/data divergence in FIXED mode
3. **check_compatibility Annotated rejection** (#1) — blocks valid pipeline construction
4. **TypeMismatchViolation value leakage** (#14) — contradicts own documented contract
5. **create_contract_from_config locked** (#15) — silent FIXED mode degradation
