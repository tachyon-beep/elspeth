# old/main.py Requirements

## `SRC_DIR` bootstrap (old/main.py:39-41)
- Functional requirements:
  - Resolve the absolute path to a sibling `src/` directory at module import time.
  - Append that absolute path to `sys.path` only if the directory exists and is not already present.
  - Ensure subsequent relative imports (e.g., local dev packages) succeed when running the file directly.
- Non-functional requirements:
  - Operation must be idempotent and platform agnostic (support POSIX/Windows paths).
  - Avoid polluting `sys.path` with non-existent or duplicate entries.
  - Prevent side effects when the file is imported as part of a packaged module without a local `src/`.

## `StatsAnalyzer` import fallback (old/main.py:32-36)
- Functional requirements:
  - Attempt to import `StatsAnalyzer` from the refactored `dmp.stats` package.
  - Fall back to `experiment_stats.StatsAnalyzer` automatically when the packaged analyzer is unavailable.
  - Expose the resolved `StatsAnalyzer` symbol for downstream consumers without requiring call-site changes.
- Non-functional requirements:
  - Perform the resolution once at import time to prevent redundant imports.
  - Keep failure handling quiet (no stack traces) when the fallback path is used.
  - Maintain compatibility during rollout where either implementation may be present.

## Logging configuration and `logger` (old/main.py:82-84)
- Functional requirements:
  - Configure global logging defaults to at least INFO level once per process using `logging.basicConfig`.
  - Expose a module-specific logger named after `__name__` for downstream diagnostic use.
  - Provide consistent logging behavior for all helper functions in the module.
- Non-functional requirements:
  - Respect existing logging handlers/formatters (do not override if already configured by caller).
  - Ensure logger usage is thread-safe and low-overhead (lazy formatting where possible).
  - Maintain compatibility with both CLI and library invocations.

## Azure ML context detection (`azure_run`, `is_azure_ml`, old/main.py:87-93)
- Functional requirements:
  - Attempt to import `azureml.core.Run` and obtain the current run context at import time.
  - Populate `azure_run` with the context object when available; default to `None` otherwise.
  - Set `is_azure_ml` to `True` only when the context type differs from `InteractiveRun`.
  - Swallow import/runtime errors and fall back gracefully when Azure ML is unavailable.
- Non-functional requirements:
  - Perform detection exactly once per process to avoid import overhead.
  - Keep behavior silent in non-Azure environments (no noisy stack traces).
  - Ensure values are safe to reuse across threads and later reassignment if needed.

## Global orchestration handles (`safety_manager`, `audit_logger`, `devops_archiver`, old/main.py:103-105)
- Functional requirements:
  - Provide module-level hooks for safety screening, audit logging, and DevOps archiving used by suite execution.
  - Initialize `audit_logger` immediately via `AuditLogger()` so audit events are capture-ready.
  - Default `safety_manager` and `devops_archiver` to `None` until setup logic assigns proper instances.
- Non-functional requirements:
  - Globals must be safe for concurrent read access and reassignment during runtime configuration.
  - Avoid performing heavy initialization at import time beyond constructing `AuditLogger`.
  - Expose a clear “unset” state (`None`) to downstream consumers without triggering errors.

## `rate_limiter` and `safe_rate_limit` (old/main.py:107-114)
- Functional requirements:
  - Maintain a module-level `rate_limiter` reference initialised to `None` until CLI wiring completes.
  - Provide `safe_rate_limit()` that raises a `RuntimeError` if called before initialization.
  - Invoke `rate_limiter.wait()` to enforce throttling when available.
- Non-functional requirements:
  - Ensure thread-safe read access when used across parallel experiment runners.
  - Emit actionable error messaging to help operators fix missing initialization.
  - Introduce no busy waiting or blocking unless mandated by the limiter implementation.

## `LLMQueryError` (old/main.py:115-117)
- Functional requirements:
  - Define a custom exception subclass of `Exception` for signaling prompt/config retrieval issues.
  - Allow callers to catch and distinguish LLM input errors from generic failures.
- Non-functional requirements:
  - Keep the class lightweight with no additional state or dependencies.
  - Preserve backwards compatibility for legacy handlers expecting this exception type.

## Compatibility wrapper functions (old/main.py:119-138)
- Covered symbols: `load_configurations`, `validate_text_field`, `validate_context`, `validate_category`, `retry_with_backoff`.
- Functional requirements:
  - Lazily import the corresponding implementations from the refactored package (`dmp.*`) at call time.
  - Pass through all arguments unchanged and return the delegated result.
  - Preserve legacy function signatures and expected exceptions for callers.
- Non-functional requirements:
  - Avoid introducing circular import issues by keeping imports inside function bodies.
  - Maintain minimal overhead during invocation (direct pass-through).
  - Remain stable even if the underlying package reorganizes, by aligning names accurately.

## `cost_tracker` singleton (old/main.py:143-147)
- Functional requirements:
  - Instantiate `CostTracker` at module load to provide a default cost accounting object.
  - Allow downstream routines to read or replace the tracker (see `run_experiment_suite`).
- Non-functional requirements:
  - Ensure the singleton is reusable across multiple experiment runs without residual state conflicts.
  - Support thread-safe access when used by concurrent tasks reporting costs.

## `load_prompts` (old/main.py:149-181)
- Functional requirements:
  - Determine prompt directory relative to the current file’s location.
  - Delegate prompt loading to `dmp.prompts.load_prompts_default`.
  - Convert file-not-found or validation issues into `LLMQueryError` while logging errors.
  - Log 100-character previews of both system and user prompts (sanitized for newline visibility).
  - Return a tuple `(system_prompt, user_prompt)` on success.
- Non-functional requirements:
  - Avoid exposing full prompt contents to logs for security/privacy.
  - Handle UTF-8 content consistently and fail gracefully on encoding issues.
  - Keep IO operations performant and idempotent for repeated invocations.

## `parse_score` shim (old/main.py:183-186)
- Functional requirements:
  - Provide backwards-compatible function that delegates to `dmp.validators.parse_score`.
  - Return the same tuple output and propagate exceptions identically to the delegated function.
- Non-functional requirements:
  - Keep wrapper overhead negligible.
  - Serve as a transitional alias to support legacy imports during refactor rollout.

## `format_user_prompt` (old/main.py:188-207)
- Functional requirements:
  - Accept prompt text, case study data, summaries, titles, service summary, criteria, descriptions, and guidance.
  - Delegate formatting to `dmp.prompts.format_user_prompt` with equivalent arguments.
  - Ensure resulting prompt respects new templating engine while matching historical interface.
- Non-functional requirements:
  - Avoid duplicating formatting logic locally to prevent drift.
  - Maintain compatibility if underlying function adds optional parameters (use keyword passing).

## `query_llm` (old/main.py:214-283)
- Functional requirements:
  - Accept an `AzureOpenAI` client, deployment name, prompts, processed row data, config tuple, token/temperature settings, optional experiment name, optional `LLMClient`, and optional cost tracker.
  - Instantiate a shared `LLMClient` when one is not provided, wiring in global `rate_limiter` and `audit_logger`.
  - Extract per-case-study data via `extract_case_study_data` and invoke `get_all_scores_with_tokens` for each.
  - Aggregate token usage, capture raw responses, and build a result dictionary containing IDs, contexts, rationales placeholders, raw outputs, and scores for both case studies.
  - Maintain result schema compatibility with legacy exporters and `StatsAnalyzer`.
- Non-functional requirements:
  - Operate without mutating inputs; support idempotent re-invocation.
  - Remain tolerant to partial token metadata (default zero counts).
  - Avoid blocking longer than necessary; rely on the rate limiter for pacing.
  - Ensure audit logging occurs via the injected `audit_logger` within delegated calls.

## `run_single_experiment_with_config` (old/main.py:287-310)
- Functional requirements:
  - Serve as a thin wrapper around `dmp.runner.execute_single_experiment_with_config`.
  - Forward dataframe, CLI args, Azure client, experiment configuration, rate limiter, and helper hooks (processing, querying, early-stop, configuration loader, Azure context flags).
  - Return the execution results exactly as provided by the delegated function.
- Non-functional requirements:
  - Keep import of the delegated function inside the wrapper to minimize import-time costs.
  - Preserve signature fidelity for callers relying on legacy entry points.

## `run_single_experiment` (old/main.py:314-364)
- Functional requirements:
  - Log single-experiment mode activation.
  - Load prompts and configuration once per invocation.
  - Initialize an `AzureOpenAI` client using CLI-provided credentials and API settings.
  - Create a per-call rate limiter with concurrency 1 for the specified deployment and wrap it with an `LLMClient`.
  - Iterate rows in the provided dataframe, preprocess each with `process_data`, query the LLM via `query_llm`, collect successes, and record failures with IDs, error messages, and timestamps.
  - Pass the module-level `cost_tracker` into `query_llm` so per-row usage metrics are captured.
  - Persist results through `save_single_experiment_results` and return a dictionary keyed by `"default"` containing successful results.
- Non-functional requirements:
  - Continue processing remaining rows after individual failures (no hard abort).
  - Keep logging informative yet free of sensitive data (no secrets or entire prompts).
  - Ensure timestamps are ISO 8601 formatted for downstream auditing.
  - Maintain deterministic order of processing to simplify comparisons/tests.

## `run_experiment_suite` (old/main.py:368-398)
- Functional requirements:
  - Build an `AzureOpenAI` client with provided credentials.
  - Construct an execution context via `build_context`, injecting Azure run information, audit logger, safety manager, and archiver.
  - Replace the module-level `cost_tracker` with the tracker from the context, and stash it on `args` for downstream consumers.
  - Delegate multi-experiment execution to `execute_experiment_suite`, passing hooks for processing, querying, early-stopping, configuration loading, and the single-experiment fallback.
  - Return the suite execution report unchanged.
- Non-functional requirements:
  - Avoid leaking earlier tracker state by overwriting atomically.
  - Support re-entrancy when running multiple suites sequentially within one process.
  - Remain thread-safe for read access to globals (context creation itself is single-threaded).

## `main` (old/main.py:402-405)
- Functional requirements:
  - Import `dmp.cli.main` lazily and delegate execution when invoked.
  - Ensure CLI exit codes and behavior mirror the packaged CLI entry point.
- Non-functional requirements:
  - Avoid side effects beyond delegation, keeping function safe for reuse in other launchers.
  - Keep import inside the function to minimize module load time.

## `if __name__ == "__main__": main()` guard (old/main.py:407-408)
- Functional requirements:
  - Trigger CLI execution only when the file is invoked directly (not when imported).
- Non-functional requirements:
  - Prevent accidental execution during unit tests or library imports.
  - Maintain compatibility with tooling that inspects modules without running them.
