# Schema & Preflight Validation Plan

## Goals
- Enforce fail-fast validation across configuration layers (global settings, prompt packs, suite defaults, per-experiment configs).
- Provide declarative schemas for datasource, sink, LLM, and plugin option payloads so every plugin can assert its requirements before execution.
- Surface preflight readiness signals (baseline presence, duplicate names, estimated usage) before any row processing begins.

## Legacy Reference
- `old/experiment_runner.py` validated experiment configs via JSON schema, enforced prompt presence, detected baseline issues, and logged warnings/issues prior to execution (`old/experiment_runner.py:16`, `old/experiment_runner.py:211`).
- Old CLI refused to run when configs failed validation, matching the project’s “fail fast” principle.

## Validation Surface Areas & Tooling
- Use `jsonschema` for declarative checks (legacy already depended on it), wrapped in helper utilities for consistent error reporting.

1. **Global Settings (`config/settings.yaml`)**
   - Validate presence/type of `datasource`, `llm`, `sinks`, `prompt_packs`, `suite_defaults`.
   - Resolve plugin definitions and validate their option schemas before instantiating objects.
   - Ensure prompt packs reference valid fields/criteria and that suite defaults do not conflict.

2. **Experiment Suite**
   - Validate each experiment folder (config JSON shape, prompt files present, optional overrides). Reuse or extend `ExperimentConfig` dataclass to run schema checks pre-load.
   - Detect duplicates and baseline requirements, raise errors instead of warnings when invariants break.
   - Compute preflight estimates (API calls, cost, concurrency) and allow operators to opt into warnings vs. hard failures via config.

3. **Plugin Schema Definitions**
   - For each plugin type (datasource, LLM, sink, row/agg/baseline/statistics plugins) define JSON schemas describing required options.
   - Registries expose a `validate(options)` hook invoked before instantiation. Missing required keys or invalid values raise immediately.
   - Provide helper decorators/utilities for plugin authors to declare schemas to keep validation consistent.
   - Standardise optional error-handling behaviour (`on_error: "abort" | "skip"`) so any plugin that consumes data (datasource, sink, metrics/statistics) can opt into skipping bad rows; default is `abort`.

4. **Prompt Packs & Middleware**
   - Confirm prompt packs supply both `system` and `user` prompts; validate criteria definitions (names, templates) and plugin references the pack introduces.
   - Middleware definitions checked for required options (e.g., Azure environment requiring `azureml-core`).

## Execution Flow
1. CLI loads settings → run `SettingsValidator` that:
   - Validates YAML structure against schema.
   - Runs plugin option validation for datasource, llm, sinks, suite defaults.
2. Suite mode → `ExperimentSuiteValidator` loads experiment metadata (without instantiating LLM/sinks yet), validates configs/prompts, builds preflight report.
3. If any errors (missing files, invalid values, duplicate names, missing baseline), raise `ConfigurationError` and abort.
4. Warnings (e.g., high temperature/tokens) reported but do not block run unless strict mode is enabled.
5. After validation passes, instantiate plugins and proceed with execution.

## Implementation Steps
1. Introduce `src/elspeth/core/validation/settings.py` and `src/elspeth/core/validation/suite.py` with reusable validators and error types backed by `jsonschema` helpers.
2. Define schemas for settings, prompt packs, suite defaults, and per-experiment configs (reuse legacy schema definitions where possible).
3. Extend plugin registries (`src/elspeth/core/registries/__init__.py`, `src/elspeth/core/experiments/plugin_registry.py`, etc.) to store option schemas and validate before instantiation.
4. Update CLI to run validation before orchestrator/suite runner invocation; present aggregated error messages when multiple config issues are detected.
5. Port preflight calculations into new validator, capturing issues/warnings in a structured object.
6. Write unit tests covering:
   - Invalid plugin option detection (missing required field).
   - Experiment folder missing prompts/config.
   - Duplicate experiment names or missing baseline raising errors.
   - Successful validation path resulting in telemetry logging via middleware (tying into Azure logging for parity).
<!-- UPDATE 2025-10-12: Validation module, plugin schemas, and CLI integration have been implemented (`src/elspeth/core/validation/settings.py` and `src/elspeth/core/validation/suite.py`, `src/elspeth/core/registries/__init__.py`, `src/elspeth/cli.py:131`). Tests reside in `tests/test_validation_settings.py` and `tests/test_validation_suite.py`. -->

## Notes
- Keep validation pure: no network/file side effects beyond reading config/prompts. Plugin instantiation should happen only after validation succeeds.
- Surface actionable error messages; include file paths and experiment names to speed remediation.
- Consider adding CLI flag `--strict-warnings` to elevate warnings to errors when desired.

## Integration Details
- **Validation module**: expose `validate_settings(path, profile) -> ValidationReport` and `validate_suite(suite_root, defaults) -> SuiteReport` consumed by CLI before orchestrator invocation.
- **ValidationReport**: structure with `errors`/`warnings` plus helper `raise_if_errors()`; CLI prints warnings but aborts on errors.
- **Plugin registry**: store `(schema, factory)` tuples; `create_*` first validates options via `jsonschema.validate` and raises `ConfigurationError` on failure.
- **Suite runner**: accept preflight report from validator; pass summary to Azure middleware for logging and reuse row estimates for concurrency planning.
- **Error types**: define `ConfigurationError` (fatal) and `PreflightWarning`. Aggregated errors should include context (plugin name, experiment folder, field).
- **Plugin error policy**: validation ensures `on_error` options are recognised; runtime should honour policy (abort or skip) when schema validation fails per record, including in intermediary analytics plugins.

## Test Strategy & Migration Steps
- **Unit Tests**: new suites under `tests/test_validation_settings.py`, `tests/test_validation_suite.py`, and plugin-specific tests that assert option schema enforcement.
- **Regression**: replicate legacy failure scenarios (missing prompts, invalid temperature, duplicate experiments) and ensure new validators raise matching `ConfigurationError` messages.
- **Integration**: extend CLI tests (`tests/test_cli_suite.py`) to confirm the CLI aborts early on invalid configuration and reports warnings when applicable.
- **Telemetry Parity**: verify Azure middleware receives preflight warnings/errors for logging by injecting validation reports in tests.
- **Rollout**: implement validators behind feature flag if needed, but default to “on” to uphold fail-fast principle; update documentation and sample configs to highlight required fields.
<!-- UPDATE 2025-10-12: Validators are enabled by default; documentation updates live in `docs/architecture/configuration-security.md` and README configuration overview. -->

## Update History
- 2025-10-12 – Confirmed validation plan execution and linked to implementation/test locations.
