# Dependency Analysis

## Core Runtime Dependencies
- **azure-identity ≥1.15.0** – Supplies managed identity support for blob ingestion; monitor for credential escalation CVEs (`pyproject.toml:13`, `src/elspeth/datasources/blob_store.py:125`).[^dep-azure-identity-2025-10-12]
- **azure-storage-blob ≥12.19.0** – Handles data ingress and sink uploads; ensure TLS/certificate pinning is enforced at the platform layer (`pyproject.toml:14`, `src/elspeth/datasources/blob_store.py:200`).[^dep-azure-blob-2025-10-12]
- **openai ≥1.12.0** – Azure OpenAI SDK; lock to patched versions to mitigate request signing or logging vulnerabilities (`pyproject.toml:18`, `src/elspeth/plugins/llms/azure_openai.py:25`).[^dep-openai-2025-10-12]
- **requests ≥2.31.0** – Used by HTTP LLM clients, Azure Content Safety, and repository sinks; enable corporate CA bundles and proxy settings where required (`pyproject.toml:19`, `src/elspeth/plugins/llms/middleware.py:249`, `src/elspeth/plugins/outputs/repository.py:168`).[^dep-requests-2025-10-12]
- **jinja2 ≥3.1.0** – Prompt rendering engine; StrictUndefined mitigates template injection but stay current for sandbox fixes (`pyproject.toml:20`, `src/elspeth/core/prompts/engine.py:33`).[^dep-jinja-2025-10-12]
- **jsonschema ≥4.21.1** – Powers configuration validation; update promptly for schema parsing CVEs (`pyproject.toml:21`, `src/elspeth/core/validation.py:271`).[^dep-jsonschema-2025-10-12]
- **pandas ≥2.2.0 / scipy ≥1.10.0** – Data handling and statistical plugins; heavy dependencies that should be scanned for native library vulnerabilities (`pyproject.toml:16`, `pyproject.toml:22`, `src/elspeth/plugins/experiments/metrics.py:14`).[^dep-pandas-scipy-2025-10-12]
<!-- Update 2025-10-12: Concurrency and analytics features do not add new hard dependencies but rely on optional extras enumerated below; ensure patch cadence covers these optional stacks when enabled. -->

- **azureml-core ≥1.56.0** – Enables Azure ML telemetry middleware; only install where Azure ML runs are required (`pyproject.toml:35`, `src/elspeth/plugins/llms/middleware_azure.py:76`).[^dep-azureml-2025-10-12]
- **openpyxl ≥3.1** – Required for Excel sinks; include in hardened builds only when spreadsheets are necessary (`pyproject.toml:30`, `src/elspeth/plugins/outputs/excel.py:18`).[^dep-openpyxl-2025-10-12]
- **statsmodels / pingouin** – Advanced analytics extras (`pyproject.toml:42`, `pyproject.toml:48`); ensure reproducibility by pinning minor versions when accreditation relies on deterministic outputs.[^dep-stats-2025-10-12]
<!-- Update 2025-10-12: Matplotlib/seaborn are optional but required for PNG/HTML visual analytics sinks; install via `pip install matplotlib seaborn` or an internal extra when chart artifacts are needed (`src/elspeth/plugins/outputs/visual_report.py:66`). -->
<!-- Update 2025-10-12: Additional extras include `[stats-bayesian]`, `[stats-planning]`, `[stats-distribution]`, and `[sinks-excel]`, enabling Bayesian comparisons, power analysis, distribution drift detection, and Excel exports respectively (`pyproject.toml:46`, `pyproject.toml:50`, `pyproject.toml:54`). -->

### Update 2025-10-12: Optional Extras
- Document enabled extras in accreditation runbooks and patch cadence; omit analytics/visual stacks when unused to reduce surface.

## Tooling & Development
- **pytest / pytest-cov** – Test harness invoked by `make bootstrap` to ensure changes do not regress security controls (`pyproject.toml:26`, `scripts/bootstrap.sh:19`).[^dep-pytest-2025-10-12]
- **ruff / pytype** – Primary linting & type-check stack (`pyproject.toml:32`, `Makefile:15`); ruff covers style/formatting, pytype adds static type analysis.[^dep-formatting-2025-10-12]

## Risk Considerations
- Track vendor advisories for Azure SDKs and OpenAI libraries; patch windows should be documented in the accreditation runbook.[^dep-advisories-2025-10-12]
- For deployments without outbound internet, replace HTTP LLM clients with the mock client to avoid stalled requests (`src/elspeth/plugins/llms/mock.py:11`).[^dep-mock-2025-10-12]
- Use vulnerability scanning (e.g., `pip-audit`) against the resolved environment and record reports inside the accreditation artefact bundle.[^dep-pipaudit-2025-10-12]
- Consider vendoring or mirroring critical packages to internal repositories to prevent supply-chain attacks during accreditation review windows.[^dep-mirror-2025-10-12]

## Added 2025-10-12 – Transitive Dependency Considerations
- **Azure SDK stack** – `azureml-core` pulls in `azure-storage-blob`, `msrest`, and `adlfs`; verify that CI images patch these transitives in lockstep and document minimum versions in accreditation plans (`pyproject.toml:35`, `src/elspeth/plugins/llms/middleware_azure.py:180`).[^dep-azure-stack-2025-10-12]
- **Analytics extras** – Installing `[stats-agreement]` adds `pingouin`, `scikit-learn`, and `statsmodels`; when unused, omit the extra to reduce attack surface. If required, capture hashes of wheels used during accreditation runs (`pyproject.toml:44`, `src/elspeth/plugins/experiments/metrics.py:37`).[^dep-analytics-extras-2025-10-12]
- **Visualization packages** – Optional guidance recommends `matplotlib`/`seaborn` for report charts; when deployed, ensure font backends and native libraries are vetted or constrained to headless environments (`docs/reporting-and-suite-management.md:12`).[^dep-visual-packages-2025-10-12]

## Update History
- 2025-10-12 – Noted extended extras (stats, sinks) and documented transitive dependency risks tied to telemetry and analytics features.
- 2025-10-12 – Update 2025-10-12: Added optional extras guidance, tooling notes, and cross-references for analytics/visual dependencies.

[^dep-azure-identity-2025-10-12]: Update 2025-10-12: Managed identity dependency linked to docs/architecture/security-controls.md (Update 2025-10-12: Managed Identity).
[^dep-azure-blob-2025-10-12]: Update 2025-10-12: Blob SDK usage referenced in docs/architecture/threat-surfaces.md (Update 2025-10-12: Storage Interfaces).
[^dep-openai-2025-10-12]: Update 2025-10-12: OpenAI SDK considerations mapped to docs/architecture/threat-surfaces.md (Update 2025-10-12: LLM Providers).
[^dep-requests-2025-10-12]: Update 2025-10-12: Requests usage tied to docs/architecture/threat-surfaces.md (Update 2025-10-12: Service Abuse).
[^dep-jinja-2025-10-12]: Update 2025-10-12: Prompt rendering dependency relates to docs/architecture/security-controls.md (Update 2025-10-12: Prompt Hygiene).
[^dep-jsonschema-2025-10-12]: Update 2025-10-12: Schema validation dependency linked to docs/architecture/configuration-security.md (Update 2025-10-12: Loader Safeguards).
[^dep-pandas-scipy-2025-10-12]: Update 2025-10-12: Analytics dependency cross-referenced in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Baseline Evaluation).
[^dep-azureml-2025-10-12]: Update 2025-10-12: Azure ML dependency aligns with docs/architecture/audit-logging.md (Update 2025-10-12: Azure Telemetry).
[^dep-openpyxl-2025-10-12]: Update 2025-10-12: Excel dependency related to docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation).
[^dep-stats-2025-10-12]: Update 2025-10-12: Analytics extras referenced in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline).
[^dep-pytest-2025-10-12]: Update 2025-10-12: Tooling dependency tied to docs/README.md (testing guidance).
[^dep-formatting-2025-10-12]: Update 2025-10-12: Ruff enforces style/formatting while pytype adds static analysis; see CONTRIBUTING (if available).
[^dep-advisories-2025-10-12]: Update 2025-10-12: Advisory tracking recommendation supports docs/architecture/threat-surfaces.md.
[^dep-mock-2025-10-12]: Update 2025-10-12: Mock client usage described in docs/architecture/threat-surfaces.md (Update 2025-10-12: Service Abuse).
[^dep-pipaudit-2025-10-12]: Update 2025-10-12: Vulnerability scanning recommendation recorded for accreditation artefacts.
[^dep-mirror-2025-10-12]: Update 2025-10-12: Mirroring guidance aligns with supply-chain recommendations in docs/architecture/threat-surfaces.md (Update 2025-10-12: Plugin Catalogue).
[^dep-azure-stack-2025-10-12]: Update 2025-10-12: Azure SDK stack dependencies emphasised for telemetry features.
[^dep-analytics-extras-2025-10-12]: Update 2025-10-12: Analytics extras cross-referenced in docs/architecture/component-diagram.md (Update 2025-10-12: Analytics Sinks).
[^dep-visual-packages-2025-10-12]: Update 2025-10-12: Visual package guidance tied to docs/reporting-and-suite-management.md (Update 2025-10-12: Visual Analytics Sink).
