# Project Plan: “Get Elspeth to Green”

## 1. Objectives
- Restore a green automated test suite that enforces determinism and security policies.
- Reinstate endpoint allowlisting across all retrieval components.
- Deliver deterministic, auditable builds with SBOM and vulnerability scan artefacts.
- Embed the quality gates (tests, coverage, secrets, SBOM, reproducible builds) into CI with persistent evidence.

## 2. Scope & Assumptions
- Scope covers application code in `src/elspeth/`, configurations in `config/`, and CI automation.
- No net-new product features; all changes are stabilisation and governance.
- Dedicated engineering squad (4 FTEs) available; security engineering reviews scheduled weekly.
- External dependencies (Azure, OpenAI) remain accessible for validation tests.

## 3. Milestone Timeline (target: 4 weeks)
| Week | Milestone | Exit Criteria |
| ---- | --------- | ------------- |
| 1 | M1 – Test Suite Stabilised | `python -m pytest` green locally, determinism metadata restored, embeddings namespace normalised. |
| 2 | M2 – Endpoint Guardrails Restored | All retrieval paths enforce allowlists; new tests cover pass/fail cases; security sign-off recorded. |
| 3 | M3 – Supply Chain Locked | Requirements locked, bootstrap deterministic, SBOM + pip-audit commands available; governance docs updated. ✅ |
| 4 | M4 – Green Gates & Evidence | CI runs tests/coverage/secrets/SBOM; documentation updated; AIS packet regenerated showing PASS. |

## 4. Workstreams & Tasks

### Workstream A: Test Suite Recovery (Lead: QA Eng)
1. Analyse regression failures (`test_results.txt:71-112`), draft remediation PR. ✅  
2. Reinstate determinism defaults in CLI & suite runner (`src/elspeth/cli.py`, `src/elspeth/core/experiments/suite_runner.py`). ✅  
3. Normalise sink namespace casing (`src/elspeth/plugins/nodes/sinks/embeddings_store.py`). ✅  
4. Fix utility registry determinism inheritance (`src/elspeth/plugins/utilities`). ✅  
5. Extend tests to prevent regressions; run `python -m pytest --maxfail=1 --disable-warnings`. ✅  
**Deliverables:** Green pytest report, updated tests, changelog entry. ✅

### Workstream B: Endpoint Hardening (Lead: Security Eng)
1. Integrate `validate_azure_openai_endpoint` in `_create_embedder` (`src/elspeth/retrieval/service.py`). ✅  
2. Add Azure Search patterns to `APPROVED_PATTERNS` and enforce validation in `create_query_client` (`src/elspeth/retrieval/providers.py`). ✅  
3. Implement regression tests covering allowlist success/failure paths (`tests/test_retrieval_service.py`, `tests/test_retrieval_providers.py`, `tests/test_security_approved_endpoints.py`). ✅  
4. Document runbooks for rejected endpoints (`docs/operations/retrieval-endpoints.md`). ✅  
**Deliverables:** Hardened retrieval code, passing tests, runbook & audit references.

### Workstream C: Deterministic Supply Chain (Lead: DevOps)
1. Generate pinned requirement files (e.g., `requirements.lock`, `requirements-dev.lock`) via pip-compile with hashes. ✅  
2. Update `scripts/bootstrap.sh` and Make targets to consume locks using `python -m piptools sync` without ad-hoc upgrades. ✅  
3. Configure SBOM generation (`make sbom` using CycloneDX) & vulnerability scans (`make audit` via `pip-audit`); retain artefacts. ✅  
4. Draft supply-chain policy and add to `docs/operations/dependency-governance.md`. ✅  
**Deliverables:** Lockfiles checked in, bootstrap updated, SBOM (`sbom.json`) and audit workflows documented. ✅

### Workstream D: Quality Gates Automation (Lead: Platform Eng)
1. Extend CI to run pytest, coverage, gitleaks, pip-audit, SBOM generation; publish reports. ✅  
2. Fail CI on gate regression; upload evidence to artefact store. ✅  
3. Update contributor docs with gate expectations and local commands. ✅ (`README.md`, `docs/operations/dependency-governance.md`)  
4. Schedule weekly gate health dashboard review.  
**Deliverables:** Updated CI configuration, documentation, dashboard link (dashboard scheduling outstanding).

### Workstream E: Final Verification & Documentation (Lead: Release Manager)
1. Execute full validation in clean venv: pytest, coverage, lint, mypy.  
2. Regenerate `docs/forensic_audit_2025-10-17/*` with PASS statuses and attach artefacts.  
3. Conduct go/no-go review with Security + Platform leads; record minutes.  
4. Prepare AIS submission packet (executive summary, gates table, findings resolution notes, SBOM).  
**Deliverables:** Updated audit docs, approval minutes, signed AIS packet.

## 5. Dependencies & Risks
- **Dependency:** Availability of security approval for endpoint patterns (risk: medium) — Mitigation: Engage security early in Week 1.  
- **Risk:** Hidden downstream regressions after determinism fixes — Mitigation: broaden regression tests, run sample suite (`make sample-suite`) before PR merges.  
- **Risk:** Tooling instability with new lockfiles — Mitigation: pilot on feature branch, coordinate with all engineers before merge.  
- **Risk:** CI time increase from additional scans — Mitigation: parallelise jobs, cache virtualenvs.

## 6. Communication Plan
- Stand-up (daily) focusing on blocker removal.  
- Weekly steering sync with Security, QA, Platform leads (minutes stored in `docs/meetings/`).  
- Progress tracker maintained in issue board with swimlanes per workstream.  
- Final readiness review at end of Week 4 with sign-off recorded in `docs/forensic_audit_2025-10-17/`.

## 7. Acceptance Criteria
- All readiness gates (tests, coverage ≥85%, secrets, SBOM, reproducible build) show PASS with artefacts. *(Coverage now 85.0% line / 71.7% branch.)*  
- Findings AUD-0001 through AUD-0004 closed with verified fixes and regression tests.  
- CI remains green across two consecutive mainline builds post-merge.  
- AIS packet approved by Security and Platform stakeholders.
