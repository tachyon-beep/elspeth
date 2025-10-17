**Quick wins (days)**

- Enforce retrieval endpoint validation (AUD-0002, Effort S, Risk ↓ High): Call the existing `validate_*_endpoint` functions from `_create_embedder` so embeddings cannot be sent to unapproved URLs.
- Add Azure Search allowlist checks (AUD-0003, Effort M, Risk ↓ High): Extend `approved_endpoints` with Azure Search patterns and guard `create_query_client` before client construction.
- Document and wire automated secret/vulnerability scans in CI (supports gates, Effort S, Risk ↓ Medium): Add gitleaks and pip-audit steps so future audits have artefacts.

**Deep work (weeks)**

- Repair determinism propagation and suite regressions (AUD-0001, Effort M, Risk ↓ High): Audit context inheritance, ensure sinks/metadata normalize casing, and make CLI defaults satisfy policy; keep pytest green with regression tests.
- Deliver deterministic build pipeline (AUD-0004, Effort M, Risk ↓ High): **Completed 2025-10-17** – locked requirements (`requirements*.lock`), reproducible bootstrap, `make sbom`, and `make audit`.
- Broaden retrieval hardening & observability (Effort M, Risk ↓ Medium): Add integration tests for secure-mode retrieval, cover namespace normalization, and emit telemetry on rejected endpoints to ease future forensics.
- Automate supply-chain artefact publication (Effort M, Risk ↓ Medium): Wire lock-sync + `make audit`/`make sbom` into CI and archive results per build.
