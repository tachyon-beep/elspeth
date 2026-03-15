# Round 5 — Final Dissent and Commitment: Iris (Integration Engineer)

## 1. Commitment

**I commit to the decided design.** No blocking concerns remain.

The 5-provenance × 2-validation model with 7 effective states, the 49-cell rule matrix, the 4-level severity system, and the governance overlay are all implementable as specified. My Round 4 integration specification (CLI, SARIF, exit codes, manifest, performance budget, determinism guarantee) was adopted substantially unchanged.

I have no minority report to file.

---

## 2. Implementation Readiness Assessment

The integration specification is **complete enough to build v0.1**. An implementer can start from the Round 4 spec and produce a working tool without design ambiguity on the core path. Below I flag clarifications that would prevent implementation questions — none are design disputes.

### 2.1 `strict.toml` — Completeness Review

The manifest as specified in Round 4 covers:

| Section | Status | Notes |
|---------|--------|-------|
| `[tool.strict]` version | ✅ Complete | `version = "0.1"` |
| `[tool.strict.topology]` | ✅ Complete | `tier_1`, `tier_2` module globs |
| `[tool.strict.rules.*]` | ✅ Complete | `blocking`, `precision_threshold` per rule |
| `[tool.strict.heuristics]` | ✅ Complete | `external_calls` pattern list |
| `[[tool.strict.exceptions]]` | ✅ Complete | Fingerprint, rule, file, decision_group, expires, review metadata |
| `coverage_mode` | ✅ Complete | Optional `"tracked"` mode for unmanifested file summary |

**Three fields need implementer clarification:**

#### 2.1.1 Topology glob semantics

The topology uses `"src/elspeth/core/landscape/*"` — but does this match recursively? An implementer needs to know:

- `"src/elspeth/core/landscape/*"` — files in directory only, or recursive?
- Recommendation: Use `**` for recursive (`"src/elspeth/core/landscape/**"`), `*` for single-level. Document in manifest schema. This follows `.gitignore` and `ruff` conventions.

#### 2.1.2 Topology overlap resolution

If a file matches both `tier_1` and `tier_2` globs (misconfiguration), what happens?

- Recommendation: **Exit 2 (tool error).** Overlapping topology is a manifest error, not an analysis question. The tool should refuse to run with ambiguous provenance declarations. Error message: `"strict.toml: file {path} matches both tier_1 and tier_2 topology — resolve overlap"`.

#### 2.1.3 Exception `[review]` sub-table — required vs optional fields

The Round 4 spec shows `trust_tier`, `decision_rationale`, and `reviewer` under `[tool.strict.exceptions.review]`. An implementer needs to know:

- **Required:** `decision_rationale` (the justification is the point)
- **Optional:** `reviewer`, `trust_tier` (useful metadata but not mechanically enforced)
- For UNCONDITIONAL cells (24/49): the tool should reject exception creation at parse time, not at analysis time. Error message: `"strict.toml: exception for {rule} on {provenance} is UNCONDITIONAL — no exceptions permitted"`.

### 2.2 SARIF Properties — Field Definitions for Implementers

All `sbe.*` properties are well-defined. One clarification needed:

#### 2.2.1 `sbe.provenanceSource` format

Round 4 examples show two styles:
- Method call: `"self._recorder.get_row_state()"` (for TIER_1 via Landscape read)
- Parameter: `"row parameter"` (for TIER_2 via transform context)

Implementers need a closed set of source formats. Recommendation:

| Source Type | Format | Example |
|-------------|--------|---------|
| Method call | `"{receiver}.{method}()"` | `"self._recorder.get_row_state()"` |
| Parameter | `"{param} parameter"` | `"row parameter"` |
| Decorator | `"@{decorator} on {function}"` | `"@external_boundary on fetch_data"` |
| Heuristic | `"heuristic: {pattern}"` | `"heuristic: requests.get"` |
| Topology | `"topology: {tier}"` | `"topology: tier_1"` |
| Default | `"unknown"` | `"unknown"` |

This is a display concern, not a correctness concern — SARIF consumers that parse `sbe.provenanceSource` programmatically need a stable format. The `sbe.provenance` enum field is the machine-readable version; `provenanceSource` is human-readable context.

#### 2.2.2 `sbe.provenanceSourceLine` nullability

`sbe.provenanceSourceLine` is `null` when provenance comes from topology or parameter context (no specific line). This is correct. Implementers should emit the field with `null` value, not omit it — SARIF consumers benefit from a stable schema.

### 2.3 Pre-commit Edge Cases

#### 2.3.1 Partial staging (`git add -p`)

Pre-commit hooks receive the **staged version** of files (pre-commit stashes unstaged changes). `strict` analyses what it receives — no special handling needed. The staged version is a valid Python file or it isn't (exit 2 on parse failure).

One subtlety: fingerprints computed on the staged version may differ from fingerprints in `strict.toml` if the exception was created against a different version of the file. This is covered by the stale-fingerprint detection already specified — the health section reports `"2 stale fingerprints (code changed since exception was created)"`. No additional pre-commit logic needed.

#### 2.3.2 Renamed files

Pre-commit passes renamed files with their new path. Exception entries in `strict.toml` use file paths. A renamed file won't match its old exception entries — the findings reappear.

This is **correct behaviour**. File renames should trigger re-evaluation of exceptions. The operator either:
1. Updates the exception `file` field to the new path, or
2. Removes the exception if the rename changes the provenance context

Automatic path migration is explicitly not desired — it would silently carry exceptions across architectural boundaries (e.g., moving a file from `core/` to `plugins/` changes its trust tier).

#### 2.3.3 New untracked files

Pre-commit only runs on staged files. Untracked files are invisible to the hook. This is standard pre-commit behaviour and requires no special handling.

#### 2.3.4 Non-Python staged files

The `.pre-commit-config.yaml` entry specifies `types: [python]`. Pre-commit filters by file type before invoking the hook. Non-Python files never reach `strict`. No special handling needed.

### 2.4 Missing from Spec (Non-blocking, v0.1 Implementation Notes)

These are implementation details not design decisions. Documenting them here saves the implementer from having to derive them:

#### 2.4.1 Fingerprint algorithm

The spec says "hash of normalised AST context" but doesn't specify the algorithm. Recommendation: SHA-256 of `"{rule_id}:{file_path}:{normalized_ast_node}"` where `normalized_ast_node` strips comments and normalizes whitespace. Truncate to first 12 hex chars for display (collision probability negligible at codebase scale). This is an implementation detail — changing the algorithm invalidates existing exceptions, so document it in the manifest schema version.

#### 2.4.2 `--changed-only` file discovery

In CI, `--changed-only` needs a base ref. Recommendation: `--changed-only` defaults to `git diff --name-only HEAD~1` for CI, `git diff --cached --name-only` for pre-commit. Allow `--base-ref <ref>` override for PR-based workflows (`git diff --name-only origin/main...HEAD`).

#### 2.4.3 SARIF `invocations` array

The spec says "no timestamps in SARIF output." The SARIF 2.1.0 schema expects an `invocations` array with execution metadata. Recommendation: Include `invocations` with `executionSuccessful` and `exitCode` but omit `startTimeUtc`/`endTimeUtc`. This satisfies SARIF validators without breaking determinism.

---

## 3. Summary

| Question | Answer |
|----------|--------|
| Can I commit to the decided design? | **Yes, unconditionally.** |
| Minority report? | **None.** |
| Is the spec complete enough to build? | **Yes.** Three manifest clarifications (glob semantics, overlap resolution, review field requirements) and two SARIF clarifications (provenanceSource format, invocations array) should be documented before implementation starts, but none require design changes. |
| Pre-commit edge cases? | **All covered** by existing mechanisms (stale fingerprint detection, standard pre-commit file filtering). Renamed-file exception migration is deliberately manual. |
| What should an implementer build first? | The taint engine (AST two-pass with 7 effective states) and the 49-cell rule matrix. Integration layers (CLI, SARIF, manifest) are well-specified and can be built in parallel by a second implementer. |
