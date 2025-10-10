# ELSPETH Hardening Work Plan

This programme converts the ISS/IRAP-oriented review findings (see `CODE_REVIEW.md`) into actionable engineering packages. Sequencing favours security guardrails and supply-chain hygiene before documentation.

---
## WP1 – Spreadsheet/CSV Output Mitigation
**Objective:** Neutralise formula-injection vectors in Excel/CSV artifacts while preserving automation compatibility.

- **Scope**
  - Patch `ExcelResultSink`, `CsvResultSink`, and the CSV branch of `LocalBundleSink` to escape leading characters (`=`, `+`, `-`, `@`).
  - Provide an opt-out flag (e.g. `sanitize_formulas`, default `True`) and record the flag in manifest metadata.
  - Sanitation applies to CSV exports used outside Excel as well.
- **Implementation Steps**
  1. Introduce a helper in `plugins/outputs/_sanitize.py` with comprehensive tests (ASCII/Unicode, whitespace, already-escaped cases).
  2. Integrate helper into all relevant sinks; ensure artifact metadata reflects sanitisation state.
  3. Extend unit/integration coverage (`test_outputs_csv.py`, `test_outputs_excel.py`, `test_outputs_local_bundle.py`, scenarios) including downgrade tests when flag disabled.
  4. Document behaviour and override in README and `docs/end_to_end_scenarios.md`.
- **Validation**
  - Tests for helper and sinks; manual `make sample-suite` inspection.

---
## WP2 – Repository Sink Logging & Credential Guidance
**Objective:** Prevent accidental credential leakage and set least-privilege expectations for repo sinks.

- **Scope**
  - Refactor `_request` logging in GitHub/Azure DevOps sinks to use redacted summaries (never payload dumps).
  - Update dry-run logs to report file counts/sizes only.
  - Produce `docs/security.md` detailing minimum token scopes (GitHub `contents:write`, Azure DevOps minimal `Code` scope), SAS expiry guidance, and secret handling patterns.
- **Implementation Steps**
  1. Implement `_safe_summary` utilities; adjust logging sites and add regression tests (`tests/test_outputs_repo.py`).
  2. Document security expectations and link from README and checklist.
  3. Provide example CI secret wiring with least-privilege tokens.
- **Validation**
  - Tests assert absence of raw tokens; doc peer review.

---
## WP3 – Signed Artifact Key Handling
**Objective:** Modernise key handling and messaging without disclosing sensitive context.

- **Scope**
  - Ensure deprecation logging for legacy env fallback avoids naming the env variable or key.
  - Add `allow_legacy_env` toggle (default `True`) with warning recommending migration.
  - Document key storage (Key Vault/secret managers), rotation cadence, and exclusion from dotfiles.
- **Implementation Steps**
  1. Adjust logging/warnings; add tests verifying `caplog` lacks sensitive info.
  2. Update docs (`docs/security.md`) with rotation guidance and secret storage advice.
- **Validation**
  - Unit tests; doc review.

---
## WP4 – Expanded Validation & Scenario Coverage
**Objective:** Increase confidence in configuration guardrails and runtime behaviour.

- **Scope**
  - Extend `tests/test_validation_settings.py` to cover suite default sinks, repo/signed sinks, prompt pack middleware arrays, and classification downgrade checks (experiment `security_level` higher than sink should fail).
  - Validate config endpoints enforce `https://` (see WP6 secure mode).
  - Scenario 3 (new) in `tests/test_scenarios.py`: run suite with repository sink in dry-run mode, assert redaction and sanitisation flags in manifests.
- **Implementation Steps**
  1. Implement negative tests for security level downgrades and http endpoints.
  2. Add Scenario 3 and confirm `_last_payloads` redaction + manifest metadata propagation.
  3. Update `docs/end_to_end_scenarios.md` accordingly.
- **Validation**
  - New tests + scenario run in CI.

---
## WP5 – Operational Hardening Checklist
**Objective:** Provide operators with a concise, auditable security checklist.

- **Scope**
  - Create `docs/security_checklist.md` covering: secret management, minimal token scopes, SAS rotation, signing-key rotation cadence, log retention/SIEM forwarding, egress allow-list examples, umask/file permission guidance for local outputs.
  - Reference from README and security doc.
- **Implementation Steps**
  1. Draft checklist (include sample egress rules for OpenAI/Azure/DevOps hosts).
  2. Review with ops/security stakeholders.
- **Validation**
  - Doc review + sign-off.

---
## WP6 – Config Guardrails & Secure Mode
**Objective:** Fail-closed configurations for higher classifications / IRAP.

- **Scope**
  - Add `--secure-mode` CLI flag (or config switch) enforcing stricter validation: mandatory `security_level` on experiments/sinks, disallow certain sinks above thresholds unless whitelisted, require `https://` endpoints, optional host allow-lists.
  - Schema updates to reject insecure configs when secure mode enabled.
- **Implementation Steps**
  1. Extend schema definitions and validation helpers; integrate with CLI option.
  2. Add tests for secure mode success/failure cases.
  3. Document secure mode behaviour in README and security docs.
- **Validation**
  - Secure-mode tests + manual CLI run.

---
## WP7 – Supply-Chain & Dependency Hygiene
**Objective:** Strengthen provenance and vulnerability posture.

- **Scope**
  - Introduce dependency pinning (pip-tools/uv lockfile) and generate SBOM (CycloneDX).
  - Add `pip-audit` or `safety`, `bandit`, `ruff` (security rules), and `semgrep` pipelines to CI.
  - Integrate secret scanning (`gitleaks` or `detect-secrets`).
  - Consider Sigstore signing for release artifacts.
- **Implementation Steps**
  1. Create lockfiles; update CI to use them.
  2. Wire scanners into CI, failing on high severity findings.
  3. Document SBOM generation in contributor docs.
- **Validation**
  - CI passes with new gates; SBOM artefact stored.

---
## WP8 – Structured Logging & SIEM Integration
**Objective:** Produce auditable, machine-readable logs.

- **Scope**
  - Move orchestrator logging to JSON (standard fields: timestamp, run_id, experiment, `security_level`, sink, sanitisation flag).
  - Emit explicit WARN/ERROR for moderation skips, classification mismatches, repo failures.
  - Provide optional log forwarder hook/handler.
- **Implementation Steps**
  1. Implement logging adapter + tests ensuring sensitive fields excluded.
  2. Update sample suite to emit JSON logs and store CI artefact.
  3. Document SIEM integration guidance.
- **Validation**
  - Tests for struct log format; manual review of sample artefact.

---
## WP9 – Runtime & Egress Hardening
**Objective:** Limit blast radius in production deployments.

- **Scope**
  - Document runtime baseline: non-root container/VM, read-only FS where feasible, locked `/tmp`, pinned CA bundle.
  - Provide egress allow-list examples (NSG/firewall) for Azure/OpenAI/DevOps endpoints.
  - Enforce umask 0077 (or explicit permissions) for generated artifacts.
- **Implementation Steps**
  1. Update CLI/bootstrap scripts to set umask and note in docs.
  2. Add runtime hardening section to security docs.
- **Validation**
  - Manual verification; doc review.

---
## WP10 – Legacy Cleanup & Docs Refresh
**Objective:** Remove stale artefacts and keep documentation aligned.

- **Scope**
  - Remove/quarantine `old/` directory and outdated scripts; add CI check preventing regressions.
  - Update README to reference current CLI, secure mode, security docs.
- **Implementation Steps**
  1. Delete legacy files; add CI rule.
  2. Refresh README references.
- **Validation**
  - CI rule triggers if legacy assets reappear; doc review.

---
## WP11 – IRAP Pack (Threat Model & Control Matrix)
**Objective:** Prepare artefacts for IRAP/ISM assessors.

- **Scope**
  - Produce DFD + threat model (e.g., STRIDE) covering orchestrator workflow.
  - Create control matrix mapping guardrails (secure mode, sanitisation, logging, key mgmt, dependency checks) to ISM controls.
  - Reference new security docs/checklist.
- **Implementation Steps**
  1. Draft diagrams and matrix in `docs/security`.md or separate folder.
  2. Review with security officers.
- **Validation**
  - Document review; optional sign-off by compliance team.

---
## WP12 (Optional) – Output Moderation Plugin
**Objective:** Offer symmetry with input safeguards.

- **Scope**
  - Implement optional moderation plugin (Azure Content Safety / OpenAI Moderation) for post-run content, supporting mask/abort modes and logging.
  - Document usage and limitations.
- **Validation**
  - Unit tests + integration path in scenarios (optional).

---
## Programme Timeline (Indicative)
1. **Week 1:** WP1 + WP6 foundational schema changes, kick off WP7 tooling.
2. **Week 2:** Complete WP2 logging/docs, progress WP7 scanners, begin WP8 structured logging.
3. **Week 3:** WP3 key posture, WP4 validation/scenario work, progress WP9 runtime hardening.
4. **Week 4:** Finalise WP5 checklist, execute WP10 + WP11 documentation. Aim to tackle WP12 if capacity allows.

(Adjust per capacity; WP6 must land before releasing sanitised outputs.)

---
## Quality Gates
- CI must block on:
  - Formula sanitisation tests, classification downgrade tests, secure-mode validation cases.
  - `pip-audit`/`safety` high-severity findings, `bandit` high, secret-scanner hits.
  - Coverage ≥ 87% (including new modules).
- Structured JSON log artefact from sample suite stored in CI.
- Manual sign-off from security/ops on `docs/security.md` + checklist.

---
## Artefact & Documentation Deliverables
- `docs/security.md`, `docs/security_checklist.md`, updated `docs/end_to_end_scenarios.md`.
- SBOM output (CycloneDX JSON) stored under `dist/` or CI artefact.
- IRAP pack assets (DFD, threat model, control matrix) within `docs/security/irap/`.

---
## Dependencies & Coordination Notes
- WP1, WP6 share schema changes; schedule code reviews jointly.
- WP8 structured logging affects WP4 scenarios—coordinate to keep assertions stable.
- Document owners (docs/security) should sync with release notes once WPs close.
