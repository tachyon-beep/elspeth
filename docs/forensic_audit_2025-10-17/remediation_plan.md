**Quick wins (days)**

- Enforce retrieval endpoint validation (AUD-0002, Effort S, Risk ↓ High): ✅ Called validators from `_create_embedder`; tests added in `tests/test_retrieval_service.py`.
- Add Azure Search allowlist checks (AUD-0003, Effort M, Risk ↓ High): ✅ Added patterns, enforced validation in `create_query_client`, and documented runbook in `docs/operations/retrieval-endpoints.md`.
- Document and wire automated secret/vulnerability scans in CI (supports gates, Effort S, Risk ↓ Medium): Add gitleaks and pip-audit steps so future audits have artefacts.

**Deep work (weeks)**

- Repair determinism propagation and suite regressions (AUD-0001, Effort M, Risk ↓ High): Audit context inheritance, ensure sinks/metadata normalize casing, and make CLI defaults satisfy policy; keep pytest green with regression tests.
- Deliver deterministic build pipeline (AUD-0004, Effort M, Risk ↓ High): **Completed 2025-10-17** – locked requirements (`requirements*.lock`), reproducible bootstrap, `make sbom`, and `make audit`.
- Broaden retrieval hardening & observability (Effort M, Risk ↓ Medium): Add integration tests for secure-mode retrieval, cover namespace normalization, and emit telemetry on rejected endpoints to ease future forensics.
- Automate supply-chain artefact publication (Effort M, Risk ↓ Medium): Wire lock-sync + `make audit`/`make sbom` into CI and archive results per build.
