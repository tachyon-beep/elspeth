# Round 4 — Open Items Resolution: Iris (Integration Engineer)

## 1. Label Set: Defend the TIER_1/TIER_2 Distinction

Quinn argues that TIER_1 and TIER_2 are not AST-observable and should collapse to INTERNAL. This is technically correct and operationally wrong.

**The AST can't distinguish them — but the manifest already does.** The tool uses `@external_boundary` and `@validates_external` decorators to identify Tier 3 boundaries. Adding `@audit_data` (Tier 1) and `@pipeline_data` (Tier 2) — or manifest entries for the same — is architecturally identical. The information enters the tool the same way external boundaries do: through declarations, not inference. Quinn's "AST can't see it" argument applies equally to Tier 3 identification, which Quinn accepts. The objection is inconsistent.

**The developer experience argument is decisive.** Here is the same finding with INTERNAL vs. TIER_1:

```
# With INTERNAL (Quinn's model)
src/elspeth/engine/processor.py:142:8  SBE-T02  .get() with default on internal data
  │ Fabricates values instead of crashing on missing key.

# With TIER_1
src/elspeth/engine/processor.py:142:8  SBE-T02  .get() with default on audit data (Tier 1)
  │ Audit data must crash on anomaly — silent defaults are evidence tampering.
  │ provenance: TIER_1 via self._recorder.get_row_state() at :138

# With TIER_2
src/elspeth/engine/processor.py:156:8  SBE-T02  .get() with default on pipeline data (Tier 2)
  │ Pipeline data types are contracted — wrong type means upstream plugin bug.
  │ provenance: TIER_2 via row parameter (transform context)
```

The INTERNAL message tells the developer *what* is wrong. The TIER_1/TIER_2 messages tell them *why* it's wrong and *what to do about it*. Tier 1 violations mean "evidence tampering risk — crash immediately." Tier 2 violations mean "upstream contract violation — fix the bug, don't mask it." These are different developer actions:

- Tier 1: Remove the `.get()` entirely. Use direct key access. Any missing key is corruption.
- Tier 2: Remove the `.get()`. If the key can legitimately be absent, fix the upstream transform's `output_schema` to guarantee it or make it optional.

Collapsing to INTERNAL forces the developer to look up which tier applies and derive the action themselves. The tool has this information — withholding it is a UX failure.

**The severity argument reinforces this.** Tier 1 violations (audit trail corruption) are always ERROR. Tier 2 violations (contract masking) are ERROR in most cases but could be WARNING for patterns where the contract is ambiguous. A tool that can't distinguish them can't produce context-appropriate severity. Quinn's model would need to treat all INTERNAL findings at the higher severity (Tier 1), inflating false positives on Tier 2 code — exactly the noise problem the provenance model is designed to solve.

**The corpus cost is marginal.** TIER_1 and TIER_2 share the same verdict for 5 of 7 rules (both ERROR for `.get()`, `getattr`, broad except, silent pass, try/except around reads). They differ on 2 rules: `isinstance()` checks (ERROR on Tier 1 — implies uncertainty about our most trusted data; WARNING on Tier 2 — may be legitimate for polymorphic pipeline rows) and data reaching audit write (PASS for both, but different reasons). The additional corpus entries are ~10 samples, well within the budget.

**Verdict: Keep TIER_1 and TIER_2 as distinct labels.** The declaration cost is low (manifest entries for Landscape methods and pipeline data access patterns), the developer experience gain is high, and the corpus cost is marginal. Quinn's INTERNAL label can exist as a convenience alias in documentation — "INTERNAL means TIER_1 or TIER_2" — but the taint engine must track the distinction.

### Provenance Labels (Final Set)

| Label | Meaning | Assignment Mechanism |
|-------|---------|---------------------|
| `TIER_1` | Audit/Landscape data — full trust | `@audit_data` decorator, manifest entries for Landscape methods |
| `TIER_2` | Pipeline data — elevated trust | `@pipeline_data` decorator, transform `row` parameter, source output |
| `TIER_3` | External data — zero trust | `@external_boundary` decorator, heuristic list |
| `UNKNOWN` | Provenance not determinable | Default for untracked variables, function returns without annotation |
| `MIXED` | Container with values from different tiers | Dict/list/tuple construction with mixed-provenance values |

### Validation Status (Final Set)

| Status | Meaning | Transition |
|--------|---------|-----------|
| `RAW` | No validation applied | Initial state for TIER_3 and UNKNOWN |
| `STRUCTURALLY_VALIDATED` | Passed through `@validates_external` with structural verification | After validator with rejection path |

`VERIFIED` deferred to v1.0 (per Pyre's proposal — requires inter-procedural analysis). `RAW` is not applicable to TIER_1/TIER_2 (internal data is inherently trusted). `STRUCTURALLY_VALIDATED` is only applicable to TIER_3 and UNKNOWN (internal data doesn't pass through external validators).

This gives a working matrix of: 5 provenance labels × {RAW, STRUCTURALLY_VALIDATED} for TIER_3/UNKNOWN, no validation dimension for TIER_1/TIER_2/MIXED. Effective state space: TIER_1, TIER_2, TIER_3+RAW, TIER_3+SV, UNKNOWN+RAW, UNKNOWN+SV, MIXED = **7 states**.

---

## 2. Complete Rule × Provenance Matrix with Corpus Verdicts

### Rule Inventory

| Rule ID | Pattern | ACF | Description |
|---------|---------|-----|-------------|
| SBE-R01 | `.get("key", default)` | ACF-I1 | Dict `.get()` with default on typed data — fabricates values |
| SBE-R02 | `getattr(obj, "attr", default)` | ACF-I1 | Attribute access with default on annotated objects — hides missing attrs |
| SBE-R03 | `hasattr(obj, "attr")` | ACF-S3 | Unconditionally banned — swallows `@property` exceptions |
| SBE-R04 | Broad `except Exception/BaseException` | ACF-I3 | Without re-raise or specific handling — destroys audit trail |
| SBE-R05 | `try/except` wrapping Tier 1 reads | ACF-I3 | Prevents crash-on-corruption for audit data |
| SBE-R06 | `except` with bare `pass` | ACF-I3 | Silent exception swallowing — evidence destruction |
| SBE-R07 | `isinstance()` on internal data | ACF-S3 | Implies uncertainty about types we control |

### The Matrix

Each cell shows: **Severity** / SARIF level / Corpus verdict

#### SBE-R01: `.get("key", default)` on typed data

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | `.get()` with default on audit data (Tier 1) — fabricates values on corruption. Audit data must crash on missing key. |
| TIER_2 | ERROR | error | `true_positive` | `.get()` with default on pipeline data (Tier 2) — masks upstream contract violations. Pipeline types are guaranteed by source/transform contracts. |
| TIER_3+RAW | SUPPRESS | — | `true_negative` | (No finding — legitimate boundary handling for unvalidated external data.) |
| TIER_3+SV | SUPPRESS | — | `true_negative` | (No finding — validated external data, `.get()` is acceptable.) |
| UNKNOWN+RAW | WARN | warning | `true_positive_reduced` | `.get()` with default on unknown-provenance data — may fabricate values. Add provenance annotation or restructure access. |
| UNKNOWN+SV | INFO | note | `true_note` | `.get()` with default on validated data of unknown provenance. Review whether default is appropriate. |
| MIXED | WARN | warning | `true_positive_reduced` | `.get()` with default on mixed-provenance data ({tiers}) — container mixes trust tiers. Decompose access paths. |

#### SBE-R02: `getattr(obj, "attr", default)` on annotated objects

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | `getattr()` with default on audit object — hides missing attributes that indicate data corruption. |
| TIER_2 | ERROR | error | `true_positive` | `getattr()` with default on pipeline object — hides missing attributes that indicate upstream plugin bugs. |
| TIER_3+RAW | SUPPRESS | — | `true_negative` | (No finding — defensive access on external data is appropriate.) |
| TIER_3+SV | SUPPRESS | — | `true_negative` | (No finding — validated external data.) |
| UNKNOWN+RAW | WARN | warning | `true_positive_reduced` | `getattr()` with default on unknown-provenance object — may hide attribute bugs. Add provenance annotation. |
| UNKNOWN+SV | INFO | note | `true_note` | `getattr()` with default on validated object of unknown provenance. Review whether default masks a real absence. |
| MIXED | WARN | warning | `true_positive_reduced` | `getattr()` with default on mixed-provenance object — may hide attribute bugs in trusted components. |

#### SBE-R03: `hasattr(obj, "attr")` — unconditionally banned

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | `hasattr()` on audit object — swallows all exceptions including `@property` errors. Use `try/except AttributeError` or explicit type check. |
| TIER_2 | ERROR | error | `true_positive` | `hasattr()` on pipeline object — swallows `@property` exceptions. Use `try/except AttributeError` or explicit type check. |
| TIER_3+RAW | ERROR | error | `true_positive` | `hasattr()` on external data — swallows `@property` exceptions. Use `try/except AttributeError` even at trust boundaries. |
| TIER_3+SV | ERROR | error | `true_positive` | `hasattr()` on validated external data — still banned. `hasattr()` swallows all exceptions regardless of validation status. |
| UNKNOWN+RAW | ERROR | error | `true_positive` | `hasattr()` — unconditionally banned. Swallows all exceptions from `@property` getters. |
| UNKNOWN+SV | ERROR | error | `true_positive` | `hasattr()` — unconditionally banned regardless of validation status. |
| MIXED | ERROR | error | `true_positive` | `hasattr()` — unconditionally banned on any provenance. |

Note: `hasattr()` is the only provenance-independent rule. Corpus verdicts are `true_positive` across all 7 states. This is correct — `hasattr()` has a fundamental language-level flaw (exception swallowing) that is dangerous regardless of data origin.

#### SBE-R04: Broad `except Exception/BaseException` without re-raise

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | Broad `except` around audit data access — destroys corruption evidence. Tier 1 anomalies must crash. |
| TIER_2 | ERROR | error | `true_positive` | Broad `except` around pipeline operation — masks upstream contract violations. Let plugin bugs crash. |
| TIER_3+RAW | SUPPRESS | — | `true_negative` | (No finding — broad exception handling at external boundary is defensive-in-depth.) |
| TIER_3+SV | INFO | note | `true_note` | Broad `except` after validation — review whether the validator already handles this error class. |
| UNKNOWN+RAW | WARN | warning | `true_positive_reduced` | Broad `except` on unknown-provenance operation — may mask corruption or contract violations. |
| UNKNOWN+SV | INFO | note | `true_note` | Broad `except` on validated unknown-provenance data. Review whether exception handling is appropriate post-validation. |
| MIXED | WARN | warning | `true_positive_reduced` | Broad `except` on mixed-provenance operation — may destroy audit evidence on Tier 1 components. |

#### SBE-R05: `try/except` wrapping Tier 1 reads

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | `try/except` around audit data read — prevents crash-on-corruption. Tier 1 reads must propagate exceptions. |
| TIER_2 | WARN | warning | `true_positive_reduced` | `try/except` around pipeline data read — may mask contract violations. Review whether this wrapping is intentional. |
| TIER_3+RAW | SUPPRESS | — | `true_negative` | (No finding — exception wrapping at external boundary is expected.) |
| TIER_3+SV | SUPPRESS | — | `true_negative` | (No finding — wrapping validated external operations is acceptable.) |
| UNKNOWN+RAW | WARN | warning | `true_positive_reduced` | `try/except` around read of unknown-provenance data — may prevent crash-on-corruption if data is Tier 1. |
| UNKNOWN+SV | SUPPRESS | — | `true_negative` | (No finding — validated data with exception wrapping is acceptable.) |
| MIXED | WARN | warning | `true_positive_reduced` | `try/except` around mixed-provenance read — may prevent crash-on-corruption for Tier 1 components. |

#### SBE-R06: `except` with bare `pass`

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | Silent `pass` in except block handling audit data — evidence destruction. Exceptions on Tier 1 data must propagate. |
| TIER_2 | ERROR | error | `true_positive` | Silent `pass` in except block handling pipeline data — swallows contract violations silently. |
| TIER_3+RAW | WARN | warning | `true_positive_reduced` | Silent `pass` in except block at external boundary — error is swallowed without recording. At minimum, log the failure. |
| TIER_3+SV | WARN | warning | `true_positive_reduced` | Silent `pass` in except block after validation — post-validation errors should be recorded, not swallowed. |
| UNKNOWN+RAW | ERROR | error | `true_positive` | Silent `pass` in except block — errors silently swallowed. Cannot verify provenance; treat as potential evidence destruction. |
| UNKNOWN+SV | WARN | warning | `true_positive_reduced` | Silent `pass` after validation — error swallowed without recording. |
| MIXED | ERROR | error | `true_positive` | Silent `pass` in except block handling mixed-provenance data — may destroy audit evidence. |

Note: SBE-R06 differs from R04 in severity at Tier 3. A broad `except` at Tier 3 is sometimes legitimate (boundary handling). A bare `pass` inside that `except` is never best practice even at boundaries — at minimum, the failure should be logged or the row quarantined. Hence WARN rather than SUPPRESS for Tier 3.

#### SBE-R07: `isinstance()` on internal data

| Provenance | Severity | SARIF level | Corpus verdict | Message template |
|-----------|----------|-------------|----------------|-----------------|
| TIER_1 | ERROR | error | `true_positive` | `isinstance()` check on audit data — implies type uncertainty about our most trusted data. Audit types are invariant. |
| TIER_2 | WARN | warning | `true_positive_reduced` | `isinstance()` check on pipeline data — may be legitimate for polymorphic rows. Review whether type is truly uncertain. |
| TIER_3+RAW | SUPPRESS | — | `true_negative` | (No finding — type checking external data is proper boundary validation.) |
| TIER_3+SV | SUPPRESS | — | `true_negative` | (No finding — additional type checks after validation are defensive-in-depth.) |
| UNKNOWN+RAW | WARN | warning | `true_positive_reduced` | `isinstance()` on unknown-provenance data — may indicate missing provenance annotation rather than legitimate uncertainty. |
| UNKNOWN+SV | SUPPRESS | — | `true_negative` | (No finding — `isinstance()` on validated data is redundant but harmless.) |
| MIXED | WARN | warning | `true_positive_reduced` | `isinstance()` on mixed-provenance data — review whether container should be decomposed by tier. |

### Corpus Sample Budget

Using Quinn's per-verdict sample counts:

| Verdict | Samples per cell | Cells | Total samples |
|---------|-----------------|-------|---------------|
| `true_positive` (ERROR) | 5 | 20 | 100 |
| `true_positive_reduced` (WARN) | 3 TP + 2 TN | 16 | 80 |
| `true_note` (INFO) | 2 | 7 | 14 |
| `true_negative` (SUPPRESS) | 3 | 16 | 48 |
| **Total** | | **59 cells** | **~242 samples** |

This is higher than Quinn's Round 3 estimate of 100-140 because the TIER_1/TIER_2 distinction adds cells. However, 25 of those cells (all SBE-R03 `hasattr` variants) share identical samples — `hasattr` is `true_positive` everywhere and the same sample code works across provenance labels. Effective unique samples: **~180**, which is manageable for a golden corpus.

### SARIF `properties` Fields per Finding

Every SARIF result carries these properties:

```json
{
  "properties": {
    "sbe.provenance": "TIER_1",
    "sbe.provenanceSource": "self._recorder.get_row_state()",
    "sbe.provenanceSourceLine": 138,
    "sbe.validationStatus": "RAW",
    "sbe.validatedBy": null,
    "sbe.validatedAtLine": null,
    "sbe.corpusVerdict": "true_positive",
    "sbe.decisionGroup": null,
    "sbe.ruleBlocking": true
  }
}
```

When a `decision_group` exception covers the finding:

```json
{
  "properties": {
    "sbe.provenance": "TIER_2",
    "sbe.provenanceSource": "row parameter",
    "sbe.provenanceSourceLine": null,
    "sbe.validationStatus": "RAW",
    "sbe.corpusVerdict": "true_positive",
    "sbe.decisionGroup": "sparse-token-lookup",
    "sbe.decisionGroupExpiry": "2026-09-01",
    "sbe.ruleBlocking": false,
    "sbe.suppressedByFingerprint": "a1b2c3d4"
  }
}
```

### Diagnostic Metrics in SARIF

Seren's Layer 3 diagnostic metrics appear as SARIF `run.properties`, not per-result:

```json
{
  "runs": [{
    "properties": {
      "sbe.diagnostics": {
        "suppressionRate": {"R01": 0.12, "R03": 0.0, "R04": 0.08},
        "violationVelocity": null,
        "validatorConcentration": {
          "validate_api_response": 8,
          "validate_row_schema": 3
        },
        "exceptionAgeDistribution": {
          "0-30d": 4, "30-90d": 12, "90-180d": 3, ">180d": 1
        },
        "activeExceptions": 20,
        "staleExceptions": 2
      }
    }
  }]
}
```

Velocity requires historical data (multiple runs) and is `null` on first run. This keeps diagnostics visible in SARIF-consuming tools without polluting per-finding data.

---

## 3. Integration Mapping (Complete Specification)

### CLI Modes

#### `strict check <path>` — Human-readable analysis

```
$ strict check src/elspeth/

GATE: 3 blocking findings, 2 advisory findings
  src/elspeth/core/landscape/exporter.py:142:8  SBE-R01  ERROR
    .get() with default on audit data (Tier 1)
    │ row_state.get("last_seen", None)
    │ provenance: TIER_1 via self._recorder.get_row_state() at :138
    │ Audit data must crash on anomaly — silent defaults are evidence tampering.

  src/elspeth/engine/retry.py:89:4  SBE-R04  ERROR
    Broad except around audit data access
    │ except Exception:
    │ provenance: TIER_1 via checkpoint_data at :82
    │ Tier 1 anomalies must crash — broad except destroys corruption evidence.

  src/elspeth/engine/processor.py:201:12  SBE-R03  ERROR
    hasattr() — unconditionally banned
    │ hasattr(transform, "batch_size")
    │ Swallows all exceptions from @property getters. Use try/except AttributeError.

  src/elspeth/engine/processor.py:156:8  SBE-R01  WARNING
    .get() with default on mixed-provenance data (TIER_1 + TIER_3)
    │ combined.get("metadata", {})
    │ provenance: MIXED (TIER_3 from api_response :150 + TIER_1 from audit_state :152)
    │ Container mixes trust tiers. Decompose access paths.

  src/elspeth/plugins/transforms/llm.py:94:12  SBE-R04  NOTE
    Broad except after validation
    │ except Exception:
    │ provenance: TIER_3 (validated by validate_response at :88)
    │ Review whether the validator already handles this error class.

HEALTH: suppression rate 8% (R01: 12%, R03: 0%, R04: 8%)
  ⚠ validator concentration: validate_api_response() covers 8 distinct flows
  ⚠ 2 allowlist entries expire within 14 days
  2 stale fingerprints (code changed since exception was created)

Exit code: 1 (blocking findings present)
```

**Output ordering:** Findings sorted by severity (ERROR → WARNING → NOTE), then by file path. Health summary always appears after findings. Stale fingerprint warnings appear in health section.

**Colour scheme (terminal):** ERROR = red, WARNING = yellow, NOTE = dim/grey, provenance lines = cyan, health warnings = yellow with `⚠` prefix.

#### `strict check --sarif <path>` — SARIF 2.1.0 output

Full SARIF 2.1.0 document written to stdout. Structure:

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "strict",
        "version": "0.1.0",
        "rules": [
          {
            "id": "SBE-R01",
            "name": "DictGetWithDefault",
            "shortDescription": {"text": ".get() with default on typed data"},
            "fullDescription": {"text": "Detects dict.get(key, default) on data where missing keys indicate corruption or contract violation, not expected absence."},
            "defaultConfiguration": {"level": "error"},
            "properties": {"precision": 0.88, "sampleCount": 127}
          }
        ]
      }
    },
    "results": [],
    "properties": {
      "sbe.diagnostics": {}
    }
  }]
}
```

Each result uses the provenance-specific `message.text` from the matrix above. `level` maps directly from the matrix severity column. `properties` carry provenance metadata as specified in Section 2.

#### `strict check --stdin` — Agent mode

Reads a single file from stdin. File path provided via `--file-path` flag (required — needed for manifest lookup and finding locations).

```
$ cat src/elspeth/engine/processor.py | strict check --stdin --file-path src/elspeth/engine/processor.py
```

Output format is SARIF by default in `--stdin` mode (structured data for agent consumption). Human-readable output available via `--stdin --format=text`.

**Rationale:** Agent mode is consumed by LLM agents that parse structured output. SARIF is the natural format. The `--file-path` is required because stdin has no path metadata, and the manifest uses file paths for exception lookup.

**Agent self-check workflow:** An agent writes code, pipes it through `strict check --stdin`, parses the SARIF output, and either fixes violations or explains why an exception is warranted. The `sbe.provenance` and `sbe.corpusVerdict` fields give the agent enough context to determine whether a finding is legitimate or requires an exception.

#### `strict check --watch <path>` — (v0.2, deferred)

Watches for file changes, re-analyses on save. Deferred because the core analysis must be stable before adding filesystem watch complexity.

### Exit Codes

| Code | Meaning | Condition |
|------|---------|-----------|
| **0** | Clean | No findings at any severity above SUPPRESS |
| **1** | Blocking findings | At least one ERROR or WARNING finding (not covered by exception) |
| **2** | Tool error | Analysis could not complete: invalid manifest, parse failure, internal error |
| **3** | Advisory only | INFO/NOTE findings present, no ERROR/WARNING findings |

**Why exit code 2 for tool errors:** The CI gate must distinguish "code is clean" (0), "code has violations" (1), and "analysis didn't run" (2). Without exit code 2, a broken manifest or a Python parse error would silently pass the gate (exit 0 by default), which is a security gap. Exit code 2 should be treated as a CI failure — the gate didn't run, so no assurance was provided.

**Exit code 3 rationale:** Advisory-only findings (INFO/NOTE) should not block CI or pre-commit, but the CI pipeline should know they exist. Exit code 3 allows pipelines to optionally surface advisories (e.g., post them as PR annotations) without failing the build. A pipeline that only checks `exit 0` will treat advisories as a pass. A pipeline that checks `exit 0 || exit 3` can distinguish "clean" from "clean with notes."

**Exit code precedence:** If both blocking and advisory findings exist, exit 1 (blocking takes priority). If only advisories exist, exit 3. If no findings, exit 0. If tool error, exit 2 regardless of findings.

### Pre-commit Hook Integration

#### `.pre-commit-config.yaml` entry

```yaml
repos:
  - repo: https://github.com/elspeth-project/strict
    rev: v0.1.0
    hooks:
      - id: strict
        name: Semantic boundary check
        entry: strict check
        language: python
        types: [python]
        # Only check staged files (pre-commit default)
        # Uses strict.toml from repo root for manifest
```

#### Severity gating in pre-commit

Pre-commit hooks have a binary outcome: pass or fail. The mapping:

| Exit code | Pre-commit result | Developer sees |
|-----------|-------------------|----------------|
| 0 | Pass | Nothing (silent success) |
| 1 | **Fail** | Blocking findings printed to terminal |
| 2 | **Fail** | Error message: "strict: analysis failed — check manifest" |
| 3 | Pass | Advisory findings printed to terminal (visible but non-blocking) |

**Pre-commit uses the same severity mapping as CI.** ERROR and WARNING block; INFO and NOTE pass. There is no separate "pre-commit severity level" configuration — the manifest controls severity, and severity controls blocking. This is deliberate: if a finding blocks CI, it should also block pre-commit. Allowing different thresholds creates a gap where developers commit code that CI will reject, wasting a push-and-wait cycle.

#### Files not in the manifest

When `strict check` encounters a Python file that has no manifest entries (no decorators, no heuristic matches, no declared trust topology for its module):

1. **All variables default to `UNKNOWN` provenance.** This is the existing default — no manifest entry required for analysis to run.
2. **`UNKNOWN` provenance findings fire at reduced severity** (WARN or INFO per the matrix). These are not blocking unless the rule is provenance-independent (SBE-R03 `hasattr` — always ERROR).
3. **No special "unmanifested file" warning.** The tool analyses what it can. Files without provenance information produce UNKNOWN-provenance findings, which is the correct conservative behaviour. An explicit warning for every unmanifested file would produce noise proportional to codebase size minus manifest size — exactly the volume problem we're trying to avoid.

**Exception:** If `strict.toml` declares `coverage_mode = "tracked"` (optional), the tool emits a single summary line: "N files analysed without provenance information. Consider adding manifest entries for improved precision." This is informational, not a finding. It does not affect exit codes.

### Manifest Structure (`strict.toml`)

```toml
[tool.strict]
version = "0.1"

# Trust topology — which modules contain which tiers
[tool.strict.topology]
tier_1 = [
    "src/elspeth/core/landscape/*",
    "src/elspeth/core/checkpoint/*",
]
tier_2 = [
    "src/elspeth/engine/*",
    "src/elspeth/plugins/*",
]
# Tier 3 is identified by decorators + heuristic list — no manifest entry needed

# Rule configuration
[tool.strict.rules.SBE-R01]
blocking = true
precision_threshold = 0.88

[tool.strict.rules.SBE-R03]
blocking = true
precision_threshold = 0.99

# Heuristic list for external boundary detection
[tool.strict.heuristics]
external_calls = [
    "requests.*",
    "httpx.*",
    "aiohttp.*",
    "urllib.request.*",
    "json.loads",
    "yaml.safe_load",
    "yaml.unsafe_load",
    "ast.parse",
    "subprocess.*",
]

# Exception entries
[[tool.strict.exceptions]]
fingerprint = "a1b2c3d4e5f6"
rule = "SBE-R01"
file = "src/elspeth/core/landscape/exporter.py"
decision_group = "sparse-token-lookup"
expires = "2026-09-01"

[tool.strict.exceptions.review]
trust_tier = "tier2"
decision_rationale = "Sparse token lookup — not all rows have tokens in batch export"
reviewer = "john"
```

### SARIF Integration Points

#### GitHub Code Scanning

SARIF upload to GitHub Code Scanning is the primary CI integration:

```yaml
# .github/workflows/strict.yml
- name: Run strict
  run: strict check --sarif src/elspeth/ > strict-results.sarif
  continue-on-error: true

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: strict-results.sarif
```

GitHub maps SARIF `level` to annotation severity: `error` → Error annotation, `warning` → Warning annotation, `note` → Notice annotation. The provenance-specific `message.text` appears directly in PR annotations, giving developers context-appropriate messages without leaving the PR view.

#### VS Code / IDE Integration

SARIF files can be consumed by the SARIF Viewer extension for VS Code. The `sbe.*` properties appear in the "Properties" panel when a finding is selected. The `provenanceSource` and `provenanceSourceLine` fields enable navigation to the provenance origin — the developer can jump from the finding to the line where the variable received its provenance label.

### Configuration Precedence for Manifest

When multiple manifest sources exist:

1. `--config <path>` CLI flag (explicit)
2. `strict.toml` in current directory
3. `pyproject.toml` `[tool.strict]` section
4. Walk up directory tree for `strict.toml` (monorepo support)

The first match wins. No merging across sources — this prevents surprising behaviour from layered configs where an exception in one file is overridden by absence in another.

### Performance Budget

| Mode | Target | Rationale |
|------|--------|-----------|
| Pre-commit (single file) | <200ms | Must be imperceptible in commit workflow |
| CI (full codebase, ~100 files) | <5s | Must not dominate CI pipeline time |
| Agent `--stdin` (single file) | <100ms | Agent self-check in inner loop — latency matters |

The two-pass AST analysis (symbol collection + rule evaluation) is linear in file size. The dominant cost is `ast.parse()`, which is already used by linters like ruff. The manifest lookup is a hash table read. Performance should be well within budget for stdlib-only analysis.

### Determinism Guarantee

**Byte-identical output for byte-identical input.** The tool's output (SARIF or human-readable) must be deterministic:

- Same source file + same manifest + same tool version → identical output
- No timestamps in SARIF output (SARIF schema allows but does not require `invocations[].startTimeUtc`)
- Finding order: sorted by file path, then line number, then column, then rule ID
- Exception matching: deterministic fingerprint algorithm (hash of normalised AST context)
- No randomness anywhere in the analysis pipeline

This is a self-hosting requirement: the tool must pass its own determinism test as part of the golden corpus.
