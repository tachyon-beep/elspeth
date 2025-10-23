# Security Middleware Demos – Classified Material & PII Shield

These companion demos walk through the two defensive middleware plugins shipped with
Elspeth: `classified_material` for classification markings, and `pii_shield` for personal
information detection. Use this guide to understand their capabilities, tune severity
thresholds, and validate behaviour with the provided test prompts.

## Getting Started

Add both middleware to your suite profile (for example, the
`master-example` profile described in [MASTER_EXAMPLE.md](MASTER_EXAMPLE.md)):

```yaml
llm:
  middleware:
    - plugin: classified_material
      on_violation: abort
      include_defaults: true
    - plugin: pii_shield
      on_violation: abort
      include_defaults: true
```

✅ Both middleware ship with safe defaults. The sections below highlight the knobs you can
turn for production deployments.

---

## 1. Classified Material Middleware (`classified_material`)

### Highlights

- **Unicode + homoglyph normalization** stops lookalike characters (`SECRET`, `SЕCRЕT`).
- **Fuzzy matching** catches spacing/punctuation variants (`A.U.S.T.E.O`, `TopSecret//AUSTEO`).
- **Severity scoring** classifies detections as HIGH/MEDIUM/LOW with configurable thresholds.
- **False-positive dampers** ignore code fences/backticks and require context for ambiguous terms.
- **Expanded catalogue** covers 42 high-signal markings (PSPF, SCI, NATO, FVEY) + optional LOW set.

### Hardened configuration

```yaml
llm:
  middleware:
    - plugin: classified_material
      include_defaults: true
      include_optional: true          # Include OFFICIAL: Sensitive etc.
      fuzzy_matching: true            # Catch spacing/punctuation variants
      severity_scoring: true
      min_severity: HIGH              # Block only HIGH severity
      check_code_fences: true         # Skip code blocks
      require_allcaps_confidence: false
      on_violation: abort
```

### Logging mode (non-blocking)

```yaml
- plugin: classified_material
  include_defaults: true
  severity_scoring: true
  min_severity: LOW
  on_violation: log
  channel: security.classification.audit
```

### Demo prompts

| Scenario | Input | Expected Outcome |
| --- | --- | --- |
| Banner structure | `TOP SECRET // AUSTEO // NOFORN` | Raises `ValueError` with severity=HIGH and matched literals (`TOP SECRET`, `AUSTEO`, `NOFORN`). |
| Fuzzy detection | `Document is marked A.U.S.T.E.O for Australian eyes only` | Raises `ValueError` (regex:austeo, regex:eyes_only). |
| Homoglyph defense | `This is SЕCRЕT information` (Cyrillic Е) | Raises `ValueError` after normalization. |
| Code fence suppression | Prompt containing ```` ```yaml\nclassification: SECRET\n``` ```` | Passes because `check_code_fences=true` suppresses matches. |
| Severity filtering | With `min_severity: MEDIUM`, `CONFIDENTIAL` triggers, but `OFFICIAL: Sensitive` (LOW) does not. |

### Performance notes

The middleware adds roughly 20 % overhead in security-critical pipelines (Unicode
normalization, regex matching, dampers). For smaller suites this is negligible; for high
throughput, enable only the features you need.

---

## 2. PII Shield Middleware (`pii_shield`)

### Highlights

- **Checksum validation** for TFN, ABN, ACN, Medicare, credit cards, BSB.
- **Severity scoring** (HIGH/MEDIUM/LOW) to control escalation paths.
- **Context boosting** requires strong tokens near matches (`tax file`, `medicare`).
- **Context suppression** ignores code fences, inline backticks, URLs, hex strings.
- **Deterministic pseudonyms** (SHA-256 + salt) enable privacy-preserving sharing.
- **Blind review mode** routes HIGH/MEDIUM findings without blocking execution.

### Production baseline

```yaml
llm:
  middleware:
    - plugin: pii_shield
      include_defaults: true
      severity_scoring: true
      min_severity: HIGH
      checksum_validation: true
      context_boosting: true
      context_suppression: true
      blind_review_mode: false
      redaction_salt_env: PII_SALT        # Export secret salt for pseudonyms
      on_violation: abort
```

### Blind review mode

```yaml
- plugin: pii_shield
  include_defaults: true
  severity_scoring: true
  min_severity: MEDIUM
  checksum_validation: true
  context_boosting: true
  context_suppression: true
  blind_review_mode: true
  on_violation: log
  channel: security.pii.blind_review
```

### Demo prompts

| Scenario | Input | Expected Outcome |
| --- | --- | --- |
| Checksum match | `Applicant TFN is 123 456 782` | Raises `ValueError` with severity=HIGH (`tfn_au`). |
| Checksum fail | `Invoice #123 456 789` | Passes because checksum fails. |
| Context boosting | With boosting enabled, `tax file number 123 456 782` triggers; the number alone does not. |
| ABN validation | `Company ABN: 51 824 753 556` | Raises `ValueError` (`abn_au`). |
| BSB combo | `BSB 062-001, Account 12345678` | Raises `ValueError` (`bsb_au`, `bsb_account_combo`). |
| Pseudonyms | With `redaction_salt`, email becomes `EMAIL#…` and is deterministic across prompts. |
| Blind review | With `blind_review_mode: true`, findings are logged to the configured channel with structured JSON routing payload. |

### Pattern catalogue (default)

- **Australian government**: TFN, ABN, ACN, ARBN, Medicare, BSB, AU passport, AU driver’s licence.
- **US/UK identity**: SSN, US passport, UK passport.
- **Contact**: Email, AU/US phone, AU mobile.
- **Financial**: Credit card (Luhn), BSB+account combination.
- **Network**: IP address (LOW severity).

### Performance notes

Checksum validation and context heuristics add ~15–20 % overhead. Disable features you do
not need in low-risk environments to minimise latency.

---

## Test Harness Tips

- Use `python -m pytest tests/security/test_middleware.py -k classified_material` to run
  classification tests, and `-k pii_shield` for PII coverage.
- Enable `LOG_LEVEL=INFO` while experimenting to capture structured log outputs.
- Review the middleware sections in `MASTER_EXAMPLE.md` for a full suite configuration
  combining these middleware with analytics sinks and signed bundles.

