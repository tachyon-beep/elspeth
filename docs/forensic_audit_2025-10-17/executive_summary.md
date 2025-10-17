**Executive Summary**

Decision: **REJECT** (confidence: Highly likely). The platform cannot be accepted into service while core quality and security controls are failing.

**Key Blockers**
- Automated regression suite is red with six high-signal failures covering CLI determinism enforcement, suite runner behavior, and embeddings namespace handling; this invalidates the release baseline (`test_results.txt:71-112`).
- Retrieval embedders bypass the service allowlist and can exfiltrate prompts or embeddings to arbitrary endpoints because `_create_embedder` never invokes endpoint validators before instantiating OpenAI/Azure clients (`src/elspeth/retrieval/service.py:46-66`, `src/elspeth/retrieval/embedding.py:54-74`).
- Azure Search vector retrieval accepts any URL without allowlisting, so classified data could be sent to hostile infrastructure if configuration drifts (`src/elspeth/retrieval/providers.py:147-190`).
- Runtime dependencies are only lower-bounded (`>=`) and bootstrap continuously upgrades to latest releases, making builds non-deterministic and vulnerable to upstream breakage (`pyproject.toml:12-34`, `scripts/bootstrap.sh:16-17`).

**Supporting Observations**
- Retry/cost telemetry is surfaced when LLM attempts exhaust, giving operations contextual warnings for investigation (`src/elspeth/core/experiments/runner.py:661-682`).
- Documentation and onboarding remain strong (quick start, security playbooks, and logging standards in `README.md:1-140`), which will help once blocking issues are resolved.
- Line coverage remains high at 89.9% with branch coverage 67.4%, indicating broad unit and integration exercise once regressions are fixed (`coverage.xml:2`).
- Dependency lockfiles and reproducible bootstrap commands (`requirements.lock`, `requirements-dev.lock`, `scripts/bootstrap.sh`) now exist, enabling consistent env recreation alongside SBOM (`make sbom`) and audit (`make audit`) routines.
- Retrieval components now enforce endpoint allowlists for Azure OpenAI embeddings and Azure Cognitive Search clients, with runbooks under `docs/operations/retrieval-endpoints.md`.

**Implications**
- The failing tests expose correctness and policy regressions (determinism metadata, namespace normalization) that likely surfaced after recent refactors; accepting the code now would push known defects into production pipelines.
- Missing endpoint validation breaks a foundational control required for MF-4 External Service Approval and could lead directly to data leakage in mission-critical environments.
- Non-deterministic builds undermine reproducibility and security attestations; operations could not guarantee identical binaries or audit compliance across environments.

Focus remediation on restoring the automated suite, reinstating endpoint guardrails across retrieval components, and freezing dependency versions before reconsidering AIS readiness.
