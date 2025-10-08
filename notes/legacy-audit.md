# Legacy Code Audit

## old/main.py
- Handles Azure ML context detection (`Run.get_context`) and logs metrics to Azure.
- Loads prompts from files, applies validation and prompt formatting helpers.
- Implements rate limiting, cost tracking, and audit logging (via `AuditLogger`).
- Supports single experiment execution and experiment suite execution, including checkpointing and early-stop heuristics.
- Integrates with Azure DevOps archiver, prompt shields, output managers, and safety managers.
- Provides CLI argument parsing (Azure OpenAI credentials, experiment paths, output options).
- Collects environment metadata, archives outputs (zip, Excel), and uploads to DevOps.
- Maintains detailed failure logging, retries with backoff, and output persistence (successful/failed CSVs, Excel reports).

## old/experiment_runner.py
- Discovers experiments from directory structure, loading `config.json`, prompt files, and optional configuration overrides.
- Validates experiment configs (schema, temperature/token bounds) and identifies baseline experiments.
- Manages preflight checks (API call estimates, cost estimates, warnings for high temp/tokens).
- Provides helper to create experiment templates, copy prompts/config from baseline.
- Logs metrics to Azure ML, exports configuration summaries, and compares experiments vs baseline.
- Estimates costs per experiment using rough token assumptions.

## old/experiment_stats.py
- Offers statistical analysis across experiments (baseline detection, score extraction).
- Provides Bayesian comparison, Cliff's delta, Krippendorff's alpha, ordinal regression, power analysis.
- Implements multiple comparisons corrections (Bonferroni, FDR) and practical significance assessments.
- Generates recommendations, effect sizes, and distribution shift metrics.
- Depends on numpy/pandas/scipy and optional libs (sklearn, pingouin, pymc3, krippendorff, statsmodels).

## Key Behaviors to Migrate
- Prompt pack management, including validation and templating.
- Experiment suite orchestration with baseline selection, preflight, retries, and checkpointing.
- Safety/validation hooks (prompt shields, validators) and audit logging.
- Cost tracking, rate limiting, and Azure telemetry (Run logging).
- Output archiving (CSV, Excel, zip, DevOps uploads) and environment capture.
- Statistical reporting and experiment comparison against baseline.

## Proposed Mapping to New Architecture
- **Prompt Packs / Validation** → Extend `ExperimentConfig` loader and experiment plugins to support reusable prompt bundles and validators; use row plugins for validation failures.
- **Experiment Suite Orchestration** → `ExperimentSuiteRunner` enhanced with baseline controls, retries, checkpoint plugins, and per-experiment plugin stacks.
- **Safety & Audit Hooks** → Model prompt shield/safety checks as row plugins or wrappers around the LLM client; integrate audit logging via aggregation plugins or sinks.
- **Cost/Rate Management** → Implemented via `CostTracker` and `RateLimiter` plugins (already in place) with provider-specific configs.
- **Output Archiving** → Introduce sinks for CSV/Excel/zip/DevOps; environment capture and DevOps upload can be separate sink plugins.
- **Statistical Analysis** → Port `experiment_stats.py` functions into aggregation plugins that compute scores/effect sizes and feed summary sinks.
- **Azure Telemetry** → Optional plugin or sink that logs metrics back to Azure ML Run when context exists.
