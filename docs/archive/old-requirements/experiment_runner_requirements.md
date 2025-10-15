# old/experiment_runner.py Requirements

## Module logger (old/experiment_runner.py:11)
- Functional requirements:
  - Expose a module-scoped logger via `logging.getLogger(__name__)` for consistent diagnostics within the runner.
- Non-functional requirements:
  - Reuse the caller’s logging configuration without reinitializing handlers.
  - Remain safe for concurrent use across threads.

## `ExperimentConfigSchema` (old/experiment_runner.py:15-22)
- Functional requirements:
  - Define a `TypedDict` capturing the canonical shape of experiment configuration metadata (`name`, `description`, `temperature`, `max_tokens`, `enabled`, `is_baseline`).
  - Serve as static typing aid for IDEs and type checkers without enforcing runtime behavior.
- Non-functional requirements:
  - Stay synchronized with the JSON schema declared in `CONFIG_SCHEMA` to avoid drift.
  - Remain importable without requiring runtime instantiation.

## `CONFIG_SCHEMA` (old/experiment_runner.py:24-37)
- Functional requirements:
  - Provide a JSON-schema-compliant dictionary describing experiment configuration validation rules.
  - Specify required properties (`name`, `temperature`, `max_tokens`, `enabled`) with correct type and bounds constraints.
  - Allow optional `is_baseline` boolean flag with validation.
- Non-functional requirements:
  - Maintain compatibility with `jsonschema.validate`.
  - Be easily extensible when new configuration fields are added (e.g., documented pattern for properties).

## `validate_config(config: dict)` (old/experiment_runner.py:39-43)
- Functional requirements:
  - Invoke `jsonschema.validate` using `CONFIG_SCHEMA` to enforce configuration shape and bounds.
  - Raise `jsonschema.ValidationError` when validation fails; succeed silently otherwise.
- Non-functional requirements:
  - Impose minimal overhead (no extra copies of the config).
  - Remain side-effect free and deterministic.

## `ExperimentConfig` class (old/experiment_runner.py:45-196)
- Functional requirements (class-level):
  - Represent a single experiment’s configuration, prompts, and derived metadata loaded from disk.
  - Enforce validation upon initialization and provide convenience accessors for core fields.
  - Support comparison and serialization utilities for tooling and reporting.
- Non-functional requirements (class-level):
  - Be resilient to partial configurations (apply defaults where appropriate).
  - Maintain backward compatibility with legacy code referencing attributes and methods.

### `__init__(self, folder_path: str)` (old/experiment_runner.py:49-116)
- Functional requirements:
  - Store `folder_path` and derived `folder_name`.
  - Read `config.json`, parse JSON, and retain as `self.config`.
  - Validate configuration using `validate_config`, translating `jsonschema.ValidationError` into `ValueError`.
  - Detect optional `configurations.yaml` file and set `has_custom_configurations`.
  - Load `system_prompt.md` and `user_prompt.md` contents into respective attributes.
  - Execute semantic validation via `self.validate()` and raise `ValueError` with aggregated messages if issues exist.
- Non-functional requirements:
  - Use UTF-8 encoding for file IO to support multilingual content.
  - Provide actionable error messages including the originating folder name.
  - Avoid modifying on-disk files (read-only initialization).

### `name` property (old/experiment_runner.py:118-120)
- Functional requirements:
  - Return `config["name"]` if present; otherwise fall back to `folder_name`.
- Non-functional requirements:
  - Access should be idempotent and O(1).

### `description` property (old/experiment_runner.py:122-124)
- Functional requirements:
  - Return the configured description string or empty string when absent.
- Non-functional requirements:
  - Guarantee a string return type for downstream formatters.

### `hypothesis` property (old/experiment_runner.py:126-128)
- Functional requirements:
  - Return hypothesis text; default to empty string.

### `author` property (old/experiment_runner.py:130-132)
- Functional requirements:
  - Return author name or `"unknown"` as default.

### `temperature` property (old/experiment_runner.py:134-136)
- Functional requirements:
  - Return configured float temperature; default to `0.0`.
  - Ensure compatibility with schema bounds (0–2).
- Non-functional requirements:
  - Avoid recalculations; direct config access only.

### `max_tokens` property (old/experiment_runner.py:138-140)
- Functional requirements:
  - Return configured integer max tokens; default to `300`.

### `enabled` property (old/experiment_runner.py:142-144)
- Functional requirements:
  - Return boolean flag indicating if experiment is active; default `True`.

### `is_baseline` property (old/experiment_runner.py:146-148)
- Functional requirements:
  - Return baseline flag; default `False`.

### `tags` property (old/experiment_runner.py:150-152)
- Functional requirements:
  - Return configured list of tags; default empty list.
- Non-functional requirements:
  - Guarantee a list instance (not `None`) to ease iteration.

### `expected_outcome` property (old/experiment_runner.py:154-156)
- Functional requirements:
  - Return expected outcome string; default empty string.

### `estimated_cost` property (old/experiment_runner.py:158-181)
- Functional requirements:
  - Estimate experiment cost using hard-coded assumptions (cost per 1k tokens, average token counts, number of requests).
  - Return dictionary with input, output, total cost estimates, and total request count.
- Non-functional requirements:
  - Keep calculation deterministic and repeatable for reporting.
  - Allow future customization by adjusting local constants without changing signature.

### `validate(self) -> List[str]` (old/experiment_runner.py:183-207)
- Functional requirements:
  - Verify critical files (`config.json`, `system_prompt.md`, `user_prompt.md`) exist and are non-empty.
  - Confirm temperature and max token values fall within acceptable ranges.
  - Ensure prompt contents are not blank.
  - Return a list of human-readable error messages without raising.
- Non-functional requirements:
  - Avoid expensive IO beyond necessary stat/read operations.
  - Provide stable ordering of errors for consistent test assertions.

### `stable_hash(text: str)` static method (old/experiment_runner.py:210-214)
- Functional requirements:
  - Produce deterministic MD5 hash (8 hex chars) for provided text.
  - Serve as utility for comparing prompt variations.
- Non-functional requirements:
  - Avoid raising for empty strings (hash empty string).
  - Keep output short for UI/log usage.

### `differs_from(self, other: 'ExperimentConfig')` (old/experiment_runner.py:216-247)
- Functional requirements:
  - Compare key configuration values (`temperature`, `max_tokens`) and prompt contents between two configs.
  - Return dict summarizing differences, including hash/length metadata for prompt mismatches.
- Non-functional requirements:
  - Handle missing attributes gracefully (assume comparable objects).
  - Avoid loading prompts multiple times (use cached attributes).

### `to_dict(self)` (old/experiment_runner.py:249-268)
- Functional requirements:
  - Serialize core metadata into dictionary for export (name, folder, description, hypothesis, author, temperature, max tokens, enabled flag, baseline flag, tags, expected outcome, estimated cost).
- Non-functional requirements:
  - Ensure resulting dict is JSON-serializable (convert nested structures appropriately).
  - Keep method side-effect free.

## `ExperimentCheckpoint` import (old/experiment_runner.py:271)
- Functional requirements:
  - Provide compatibility hook for checkpoint handling (even if unused locally).
- Non-functional requirements:
  - Import should succeed when package is installed; failure should surface early for missing dependencies.

## `ExperimentSuite` class (old/experiment_runner.py:273-458)
- Functional requirements (class-level):
  - Manage discovery, validation, ordering, and reporting of multiple experiment configurations.
  - Integrate with optional Azure ML run logging.
- Non-functional requirements (class-level):
  - Support operation even when Azure ML or the filesystem structure is absent.
  - Maintain compatibility with legacy tooling expecting similar behavior.

### `__init__(self, experiments_root: str, azure_run=None)` (old/experiment_runner.py:277-302)
- Functional requirements:
  - Store experiments root path and Azure run handles.
  - Determine if running under Azure ML (`self.is_azure_ml`).
  - Discover experiments by invoking `_discover_experiments`.
  - When Azure ML is available, log experiment count and per-experiment metadata via `azure_run.log` and `log_row`.
- Non-functional requirements:
  - Avoid raising when experiment discovery encounters problems (handled downstream).
  - Keep Azure logging optional and best-effort; do not fail suite creation if logging fails.

### `_discover_experiments(self)` (old/experiment_runner.py:304-360)
- Functional requirements:
  - Enumerate directories under `experiments_root`, ignoring non-directories and hidden folders.
  - Instantiate `ExperimentConfig` for each folder, append enabled experiments to list, and log load success/failure.
  - Enforce baseline uniqueness by warning on zero or multiple baselines and disabling extra baseline flags.
- Non-functional requirements:
  - Provide deterministic ordering by sorting directory names.
  - Continue processing even when individual experiments fail to load (soft failure).
  - Limit log noise; warnings for issues, info for successes.

### `get_baseline(self)` (old/experiment_runner.py:362-375)
- Functional requirements:
  - Return the first experiment flagged as baseline.
  - If none flagged, default to first experiment and log info.
  - Return `None` when no experiments exist.
- Non-functional requirements:
  - Avoid modifying experiment flags except where necessary during discovery.
  - Keep selection deterministic for reproducibility.

### `preflight_check(self, row_count: int = 100)` (old/experiment_runner.py:377-418)
- Functional requirements:
  - Validate suite readiness by checking baseline presence, duplicate names, and suspicious parameter values.
  - Estimate API call volume and execution time based on experiments and provided row count.
  - Aggregate total estimated cost across experiments.
  - Return dict indicating readiness, issues, warnings, baseline, experiment list, and computed metrics.
- Non-functional requirements:
  - Ensure calculations remain inexpensive (no API calls).
  - Provide conservative estimates to aid planning.
  - Keep warnings informative but non-blocking.

### `get_execution_order(self)` (old/experiment_runner.py:420-433)
- Functional requirements:
  - Determine execution order by placing baseline first and sorting remaining experiments by `max_tokens` then `temperature`.
  - Return ordered list of `ExperimentConfig` instances.
- Non-functional requirements:
  - Provide stable sorting to guarantee reproducible runs.
  - Leave original experiment list unmodified.

### `log_metrics(self, exp_name: str, metrics: Dict[str, Any])` (old/experiment_runner.py:435-443)
- Functional requirements:
  - When running under Azure ML, iterate numeric metrics and log each using `<experiment>_<metric>` naming.
  - Silently skip logging when Azure ML is not active.
- Non-functional requirements:
  - Avoid logging non-numeric values to prevent Azure schema issues.
  - Keep function resilient to Azure logging failures (best-effort).

### `log_experiment_comparison(self, baseline: ExperimentConfig, variant: ExperimentConfig)` (old/experiment_runner.py:445-472)
- Functional requirements:
  - Compare variant against baseline using `differs_from`.
  - Log differences as Azure table (`log_table`) and individual metrics (`log`) when Azure ML is active.
  - Handle both numeric and non-numeric differences appropriately.
- Non-functional requirements:
  - Skip execution entirely when Azure ML is inactive to avoid unnecessary overhead.
  - Prevent exceptions when variant lacks comparable fields (graceful logging).

### `export_configuration(self, output_file: str)` (old/experiment_runner.py:474-500)
- Functional requirements:
  - Generate export payload with suite metadata (count, baseline, timestamp) and experiment list via `to_dict`.
  - Write to YAML when filename ends with `.yaml`; otherwise emit JSON with indentation.
  - Log summary of export operation.
- Non-functional requirements:
  - Ensure output encoding is UTF-8.
  - Avoid mutating experiment state during serialization.
  - Guarantee output directories exist or raise meaningful errors upstream.

### `create_experiment_template(self, name: str, base_experiment: Optional[str] = None)` (old/experiment_runner.py:502-560)
- Functional requirements:
  - Create a new experiment directory under `experiments_root`, failing when it already exists.
  - Determine template source: specified base, baseline, or default scaffolding.
  - Copy prompts from base experiment when available; otherwise create stub prompt files.
  - Write `config.json` with appropriately adjusted metadata (e.g., disabled by default, new `created_date`).
  - Return path to newly created experiment folder.
- Non-functional requirements:
  - Use UTF-8 encoding and maintain JSON formatting with indentation.
  - Avoid copying state that should differ (e.g., reset `is_baseline`, disable experiment).
  - Provide meaningful log entries for auditing template creation.

### `get_summary(self)` (old/experiment_runner.py:562-583)
- Functional requirements:
  - Summarize suite by counting experiments, identifying baseline, and listing core metrics (temperature, max tokens, baseline flag, tags, estimated cost) for each.
  - Compute total estimated cost aggregate.
  - Return a dictionary fit for serialization or reporting.
- Non-functional requirements:
  - Keep computation lightweight (no file IO).
  - Ensure summary remains consistent with individual experiment properties.
