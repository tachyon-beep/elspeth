**Quick wins (days)**

- Enforce retrieval endpoint validation (AUD-0002, Effort S, Risk ↓ High): ✅ Validators wired into `_create_embedder`; regression tests in `tests/test_retrieval_service.py`.
- Add Azure Search allowlist checks (AUD-0003, Effort S, Risk ↓ High): ✅ Patterns added, validation enforced in `create_query_client`, runbook captured in `docs/operations/retrieval-endpoints.md`.
- ✅ Record security/vulnerability scan artefacts in CI (supports gates, Effort S, Risk ↓ Medium): `ci.yml` now prepares gitleaks JSON reports and uploads them alongside SBOM/pip-audit artefacts.

**Deep work (weeks)**

- ✅ Lift line coverage to ≥85% (AUD-0005, Effort S, Risk ↓ Medium): Added schema validation/regression coverage; `coverage.xml` now reports 85.0% line coverage.
- Automate supply-chain artefact publication (Effort M, Risk ↓ Medium): Wire lock-sync + `make audit`/`make sbom` into CI and archive results per build.
- Broaden retrieval observability (Effort M, Risk ↓ Medium): Extend integration checks for secure-mode retrieval and emit metrics on rejected endpoints to ease future incident response.
