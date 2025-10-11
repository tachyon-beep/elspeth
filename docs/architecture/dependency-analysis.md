# Dependency Analysis

## Core Runtime Dependencies
- **azure-identity ≥1.15.0** – Supplies managed identity support for blob ingestion; monitor for credential escalation CVEs (`pyproject.toml:13`, `src/elspeth/datasources/blob_store.py:125`).
- **azure-storage-blob ≥12.19.0** – Handles data ingress and sink uploads; ensure TLS/certificate pinning is enforced at the platform layer (`pyproject.toml:14`, `src/elspeth/datasources/blob_store.py:200`).
- **openai ≥1.12.0** – Azure OpenAI SDK; lock to patched versions to mitigate request signing or logging vulnerabilities (`pyproject.toml:18`, `src/elspeth/plugins/llms/azure_openai.py:25`).
- **requests ≥2.31.0** – Used by HTTP LLM clients, Azure Content Safety, and repository sinks; enable corporate CA bundles and proxy settings where required (`pyproject.toml:19`, `src/elspeth/plugins/llms/middleware.py:249`, `src/elspeth/plugins/outputs/repository.py:168`).
- **jinja2 ≥3.1.0** – Prompt rendering engine; StrictUndefined mitigates template injection but stay current for sandbox fixes (`pyproject.toml:20`, `src/elspeth/core/prompts/engine.py:33`).
- **jsonschema ≥4.21.1** – Powers configuration validation; update promptly for schema parsing CVEs (`pyproject.toml:21`, `src/elspeth/core/validation.py:271`).
- **pandas ≥2.2.0 / scipy ≥1.10.0** – Data handling and statistical plugins; heavy dependencies that should be scanned for native library vulnerabilities (`pyproject.toml:16`, `pyproject.toml:22`, `src/elspeth/plugins/experiments/metrics.py:14`).
<!-- UPDATE 2025-10-12: Concurrency and analytics features do not add new hard dependencies but rely on optional extras enumerated below; ensure patch cadence covers these optional stacks when enabled. -->

## Optional Extras
- **azureml-core ≥1.56.0** – Enables Azure ML telemetry middleware; only install where Azure ML runs are required (`pyproject.toml:35`, `src/elspeth/plugins/llms/middleware_azure.py:76`).
- **openpyxl ≥3.1** – Required for Excel sinks; include in hardened builds only when spreadsheets are necessary (`pyproject.toml:30`, `src/elspeth/plugins/outputs/excel.py:18`).
- **statsmodels / pingouin** – Advanced analytics extras (`pyproject.toml:42`, `pyproject.toml:48`); ensure reproducibility by pinning minor versions when accreditation relies on deterministic outputs.
<!-- UPDATE 2025-10-12: Matplotlib/seaborn are optional but required for PNG/HTML visual analytics sinks; install via `pip install matplotlib seaborn` or an internal extra when chart artifacts are needed (`src/elspeth/plugins/outputs/visual_report.py:66`). -->
<!-- UPDATE 2025-10-12: Additional extras include `[stats-bayesian]`, `[stats-planning]`, `[stats-distribution]`, and `[sinks-excel]`, enabling Bayesian comparisons, power analysis, distribution drift detection, and Excel exports respectively (`pyproject.toml:46`, `pyproject.toml:50`, `pyproject.toml:54`). -->

## Tooling & Development
- **pytest / pytest-cov** – Test harness invoked by `make bootstrap` to ensure changes do not regress security controls (`pyproject.toml:26`, `scripts/bootstrap.sh:19`).
- **black / isort** – Formatting tools, keeping code reviews deterministic (`pyproject.toml:32`, `Makefile:15`).

## Risk Considerations
- Track vendor advisories for Azure SDKs and OpenAI libraries; patch windows should be documented in the accreditation runbook.
- For deployments without outbound internet, replace HTTP LLM clients with the mock client to avoid stalled requests (`src/elspeth/plugins/llms/mock.py:11`).
- Use vulnerability scanning (e.g., `pip-audit`) against the resolved environment and record reports inside the accreditation artefact bundle.
- Consider vendoring or mirroring critical packages to internal repositories to prevent supply-chain attacks during accreditation review windows.

## Added 2025-10-12 – Transitive Dependency Considerations
- **Azure SDK stack** – `azureml-core` pulls in `azure-storage-blob`, `msrest`, and `adlfs`; verify that CI images patch these transitives in lockstep and document minimum versions in accreditation plans (`pyproject.toml:35`, `src/elspeth/plugins/llms/middleware_azure.py:180`).
- **Analytics extras** – Installing `[stats-agreement]` adds `pingouin`, `scikit-learn`, and `statsmodels`; when unused, omit the extra to reduce attack surface. If required, capture hashes of wheels used during accreditation runs (`pyproject.toml:44`, `src/elspeth/plugins/experiments/metrics.py:37`).
- **Visualization packages** – Optional guidance recommends `matplotlib`/`seaborn` for report charts; when deployed, ensure font backends and native libraries are vetted or constrained to headless environments (`docs/reporting-and-suite-management.md:12`).

## Update History
- 2025-10-12 – Noted extended extras (stats, sinks) and documented transitive dependency risks tied to telemetry and analytics features.
