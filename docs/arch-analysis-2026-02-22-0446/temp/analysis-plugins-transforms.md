# Architecture Analysis: Transform Plugins

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Scope:** `src/elspeth/plugins/transforms/` (12 files) + `src/elspeth/plugins/transforms/azure/` (3 files)
**Confidence:** High

---

## Per-File Analysis

---

### 1. `field_mapper.py` — FieldMapper

**Purpose:** Renames, selects, and reorganizes row fields. Supports nested dotted-path source fields, rename-only mode, select-only mode (drop non-mapped fields), and strict mode (error on missing source fields). Propagates contract metadata (field lineage) through the rename operation.

**Key classes:**
- `FieldMapperConfig(TransformDataConfig)` — Pydantic config with `mapping: dict[str, str]`, `select_only: bool`, `strict: bool`, `validate_input: bool`. Has a model validator `_reject_duplicate_targets` that catches configurations where two source fields are mapped to the same target name.
- `FieldMapper(BaseTransform)` — `process()` applies mappings, calls `narrow_contract_to_output()` to propagate renamed field contracts, returns a new `PipelineRow` with updated contract.

**Dependencies:**
- `elspeth.contracts.contract_propagation.narrow_contract_to_output`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`
- `elspeth.plugins.sentinels.MISSING`
- `elspeth.plugins.utils.get_nested_field`

**Row processing pattern:** 1:1. One row in, one row out (with field transformations).

**External call boundaries:** None.

**Concerns:**
1. `assert cfg.schema_config is not None` is NOT present here (unlike web_scrape.py). Schema config absence would surface as a crash later — acceptable since it's Tier 1 code.
2. The `validate_input` config field is stored as `self.validate_input` (public attribute) but is never used in `process()`. The docstring says "Raises: ValidationError: If validate_input=True..." but there is no code path that actually performs validation. This is dead config that creates a false sense of security.
3. When `select_only=False`, the code does `copy.deepcopy(row.to_dict())` then applies mappings. For large rows with nested structures, this is an O(N) deep copy on every row. Acceptable for correctness, but notable.
4. The contract update path via `row.contract.resolve_name(source)` is called only when `source not in output` after the initial deepcopy. This branching logic is subtle and correctness depends on when the normalized vs original name appears in `output`.

---

### 2. `passthrough.py` — PassThrough

**Purpose:** Passes rows through unchanged (deep copy to prevent mutation). Used for testing, debugging pipeline wiring, or as a placeholder. Canonical no-op transform.

**Key classes:**
- `PassThroughConfig(TransformDataConfig)` — Only adds `validate_input: bool = False`.
- `PassThrough(BaseTransform)` — `process()` returns `TransformResult.success(PipelineRow(copy.deepcopy(row.to_dict()), row.contract))`.

**Dependencies:**
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** 1:1. Identity transform.

**External call boundaries:** None.

**Concerns:**
1. Same dead `validate_input` config field as FieldMapper — stored but never used in `process()`. The docstring promises "Raises: ValidationError: If validate_input=True" but no validation code exists.
2. Minor: `copy.deepcopy(row.to_dict())` on every row for a passthrough is a pure CPU/memory cost with no functional benefit. If the contract holds that transforms do not mutate rows in-place, the deepcopy is defensive programming. If the engine guarantees rows are not mutated after delivery, this is wasted work. Worth evaluating whether the deep copy is required or whether passing the existing PipelineRow through is safe.

---

### 3. `truncate.py` — Truncate

**Purpose:** Truncates string fields to configured maximum lengths, with an optional suffix (e.g., "...") appended when truncation occurs. Supports strict mode (error on missing configured field). Validates at init that suffix length does not consume the entire max_length allowance.

**Key classes:**
- `TruncateConfig(TransformDataConfig)` — `fields: dict[str, int]`, `suffix: str`, `strict: bool`.
- `Truncate(BaseTransform)` — `process()` iterates configured fields, checks type, truncates if over length.

**Dependencies:**
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** 1:1. Truncates in place (on a deepcopy).

**External call boundaries:** None.

**Concerns:**
1. Uses `type(value) is not str` which is the correct strict type check (rejects str subclasses). Consistent with the CLAUDE.md pattern of using `type()` over `isinstance()` for Tier 2 contract enforcement.
2. The normalized field name resolution logic (`if field_name in output: normalized_field_name = field_name; else: normalized_field_name = row.contract.resolve_name(field_name)`) is the same two-step pattern repeated across FieldMapper and Truncate. This is a candidate for extraction to a shared utility.
3. The contract is passed through unchanged (`PipelineRow(output, row.contract)`), which is correct — truncating a string does not change its type contract, only its value. No concern here.

---

### 4. `keyword_filter.py` — KeywordFilter

**Purpose:** Security transform that scans configured row fields for blocked content patterns (regex). Rows matching any pattern return `TransformResult.error()` (routed to `on_error` sink). Non-matching rows pass through unchanged. Implements partial ReDoS protection by detecting nested quantifiers in patterns at init time.

**Key classes:**
- `KeywordFilterConfig(TransformDataConfig)` — `fields: str | list[str]`, `blocked_patterns: list[str]`. Validators enforce non-empty fields and non-empty patterns.
- `KeywordFilter(BaseTransform)` — `determinism = Determinism.DETERMINISTIC`, `creates_tokens = False`. Compiles patterns at `__init__`, runs `_validate_regex_safety()` per pattern. `process()` calls `_get_fields_to_scan()` then iterates fields and patterns.

**Dependencies:**
- `re` (stdlib)
- `elspeth.contracts.Determinism`
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** 1:1. Pass-through or error routing — does not modify row data.

**External call boundaries:** None.

**Concerns:**
1. **ReDoS detection is explicitly incomplete** (acknowledged in comments). The `_NESTED_QUANTIFIER_RE` pattern documents four known gaps: `{n,}` brace quantifiers inside groups, nested group boundaries, alternation-based attacks, and overlapping character class repetition. The mitigation is `_MAX_PATTERN_LENGTH = 1000` and the assumption that patterns come from operator-authored config, not arbitrary user input. This is a reasonable documented trade-off, not a bug.
2. `_get_fields_to_scan()` method is duplicated identically in `AzureContentSafety` and `AzurePromptShield`. Strong candidate for extraction to a shared utility or mixin.
3. When `fields == "all"`, non-string fields are silently skipped. When `fields` is a specific list, non-string fields are also silently skipped (`if not isinstance(value, str): continue`). This is intentional (only string fields can be pattern-matched), but there is no audit record that a non-string configured field was skipped. A misconfigured `fields` list pointing at an int field would silently pass all rows through without scanning.

---

### 5. `json_explode.py` — JSONExplode

**Purpose:** Deaggregation transform. Takes one row with a JSON array field and expands it to N output rows, one per array element. The `creates_tokens = True` flag signals the engine to create new token IDs for each child row with parent linkage. Validates schema homogeneity across output rows. Handles heterogeneous-typed arrays by setting the output field contract type to `object`.

**Key classes:**
- `JSONExplodeConfig(DataPluginConfig)` — Note: extends `DataPluginConfig`, NOT `TransformDataConfig`, because JSONExplode has no `on_error` routing (type violations are intended to crash).
- `JSONExplode(BaseTransform)` — `creates_tokens = True`. Validates `array_field` is a list (raises `TypeError` for wrong types — intentional crash per trust model). Returns `TransformResult.success_multi()` with N `PipelineRow` objects.

**Dependencies:**
- `elspeth.contracts.contract_propagation.narrow_contract_to_output`
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.FieldContract, PipelineRow, SchemaContract`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.DataPluginConfig, PluginConfigError`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** 1:N. One row in, N rows out (N = length of array field).

**External call boundaries:** None.

**Concerns:**
1. Empty array returns `TransformResult.error()` rather than crash. The module docstring argues that type violations should crash, but an empty array is a value-level condition (type is correct: it is a list). This is the correct tier model decision: `[]` is a valid list, it's just operationally problematic, so it routes to error rather than crashing.
2. The contract update logic for heterogeneous types is non-trivial: it checks `len(item_types) > 1` across all array elements and patches the output contract field to `python_type=object`. This is careful and correct but the code is verbose. It is also built around `FieldContract` tuple immutability — reconstructing the entire fields tuple to patch one field is an ergonomic consequence of using frozen dataclasses for contracts.
3. Schema homogeneity check for `output_rows` (B3 comment) raises `ValueError` for non-uniform output schemas. This is technically unreachable for `json_explode` since `base` is the same dict for all rows and only `output_field`/`item_index` are added — the output schema will always be uniform. The check adds correctness confidence but is dead code in practice.
4. At `__init__`, JSONExplode raises `PluginConfigError` if `on_success` is in config. This is unusual guard logic — it prevents a config option being passed that belongs at the settings layer. The comment explains the rationale. No concern with the approach, but it is a unique pattern not seen in other transforms.

---

### 6. `batch_replicate.py` — BatchReplicate

**Purpose:** Batch-aware deaggregation transform. Receives N buffered rows as a list (triggered by aggregation count/timeout), replicates each by a field-specified number of copies, outputs M rows total (M = sum of copies). Demonstrates the `is_batch_aware = True` pattern. Enforces `max_copies` bound to prevent unbounded expansion.

**Key classes:**
- `BatchReplicateConfig(TransformDataConfig)` — `copies_field`, `default_copies`, `max_copies`, `include_copy_index`. Model validator ensures `default_copies <= max_copies`.
- `BatchReplicate(BaseTransform)` — `is_batch_aware = True`. `process()` signature takes `list[PipelineRow]` (marked `# type: ignore[override]`). Rows with invalid copies values are quarantined into `success_reason["metadata"]` rather than being returned separately — a notable design choice (see Concerns).

**Dependencies:**
- `elspeth.contracts.errors.TransformSuccessReason`
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.FieldContract, PipelineRow, SchemaContract`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** N:M. N buffered rows in, M replicated rows out.

**External call boundaries:** None.

**Concerns:**
1. **Quarantined rows are buried in `success_reason["metadata"]`** rather than being returned as proper `TransformResult.error()` results. This means rows with invalid `copies` values disappear from the audit trail as distinct quarantined tokens — they are reported as metadata on a success result. This violates the principle that every row must reach a terminal state (COMPLETED, QUARANTINED, etc.). The `quarantined` list within the success_reason is not a Landscape-recorded entity, it's just JSON metadata in the audit record of the batch result token.
2. Uses `type(raw_copies) is not int` (correct strict check, rejects bool). Consistent.
3. Empty batch handling creates a synthetic `{"batch_empty": True}` row. This is a reasonable choice but it means the downstream pipeline receives a row that has no correspondence to any input row — it's an artifact token. The schema for this synthetic row (`SchemaContract(mode="OBSERVED", ...)`) is built inline, which is the same pattern as BatchStats.
4. `# type: ignore[override]` on `process()` is required because the batch signature differs from `BaseTransform.process()`. This suppresses mypy's method signature incompatibility check. A typed batch protocol/ABC would eliminate this.

---

### 7. `batch_stats.py` — BatchStats

**Purpose:** Batch-aware aggregation transform. Receives N buffered rows, computes aggregate statistics (count, sum, optional mean) over a configured numeric field. Optionally includes a `group_by` field value in output. Handles NaN/Infinity by skipping them (not crashing) with a count of skipped values. Guards against float overflow from summing many large-but-valid floats.

**Key classes:**
- `BatchStatsConfig(TransformDataConfig)` — `value_field: str`, `group_by: str | None`, `compute_mean: bool`.
- `BatchStats(BaseTransform)` — `is_batch_aware = True`. `process()` validates `value_field` type (crashes on wrong type per Tier 2 contract), skips NaN/Inf with counter, computes sum/mean.

**Dependencies:**
- `math` (stdlib)
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.FieldContract, PipelineRow, SchemaContract`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`

**Row processing pattern:** N:1. N buffered rows in, 1 aggregate statistics row out.

**External call boundaries:** None.

**Concerns:**
1. **`group_by` homogeneity enforcement crashes on heterogeneous values** (`raise ValueError(...)`). Per trust model, this is a Tier 2 contract violation (group_by values should be homogeneous within a batch — it's the pipeline's job to ensure this via trigger configuration). Crashing is the correct response. No concern.
2. The `group_by` field collision guard (`if self._group_by is not None and self._group_by in result: raise ValueError(...)`) runs before `rows[0][self._group_by]` access. This is correct ordering but the check itself has a subtle bug: `result` at that point always contains `{"count": ..., "sum": ..., "batch_size": ...}` and conditionally `"mean"` and `"skipped_non_finite"`. The check `if self._group_by in result` will fire if group_by is set to "count", "sum", "batch_size", "mean", or "skipped_non_finite". This is correct collision detection.
3. `# type: ignore[override]` on `process()` — same issue as BatchReplicate. A typed batch ABC would eliminate this.
4. Empty batch handling produces `{"count": 0, "sum": 0, "mean": None, "batch_empty": True}`. Using `None` for mean in an empty batch is reasonable. The `mean` field type in the output contract will be `object` (OBSERVED mode), so downstream consumers must handle `None` values.
5. The output contract is always built fresh from `result` keys using `SchemaContract(mode="OBSERVED", ...)`. This means every aggregation result loses provenance (no original_name, no inferred type beyond `object`). This is an acceptable trade-off for aggregations since the schema is fundamentally new, but the loss of type information may require downstream transforms to use OBSERVED schema mode.

---

### 8. `field_collision.py` — Utility module

**Purpose:** Utility function for detecting field name collisions. Provides `detect_field_collisions(existing_fields, new_fields)` which returns a sorted list of colliding names, or `None` if no collision.

**Key functions:**
- `detect_field_collisions(existing_fields: set[str], new_fields: Iterable[str]) -> list[str] | None`

**Dependencies:** None (pure Python, only `__future__.annotations` and `collections.abc.Iterable`).

**Row processing pattern:** N/A — utility function, not a transform.

**External call boundaries:** None.

**Concerns:**
1. This module is a two-function utility. It is not a transform despite living in the transforms directory. This is mildly confusing placement. Would fit better in `elspeth/plugins/utils.py` alongside `get_nested_field`. However, it is used by the TransformExecutor and declared_output_fields system, so keeping it adjacent to the transform interface makes some sense.
2. The function returns `None` for no collisions and a list for collisions (instead of an empty list vs non-empty list). The caller must check `if result is not None` rather than `if result`. Minor API ergonomics concern — `None` vs `[]` return values are both falsy, but the typing forces an explicit None check.

---

### 9. `web_scrape.py` — WebScrapeTransform

**Purpose:** Row-enrichment transform that fetches a URL from a row field, extracts page content (HTML to markdown/text/raw), computes a fingerprint for change detection, and stores raw/processed payloads in the PayloadStore. Implements SSRF prevention via `validate_url_for_ssrf()` and IP pinning via `SSRFSafeRequest`. Records all HTTP calls via `AuditedHTTPClient`. Designed for compliance monitoring.

**Key classes:**
- `WebScrapeHTTPConfig(BaseModel)` — `abuse_contact`, `scraping_reason`, `timeout`. Has `extra="forbid"`.
- `WebScrapeConfig(TransformDataConfig)` — `url_field`, `content_field`, `fingerprint_field`, `format`, `fingerprint_mode`, `strip_elements`, `http: WebScrapeHTTPConfig`.
- `WebScrapeTransform(BaseTransform)` — `determinism = Determinism.EXTERNAL_CALL`. `process()` validates URL, fetches, extracts, fingerprints, stores payloads, enriches row. `_fetch_url()` handles HTTP error mapping to `WebScrapeError` subtypes.

**Dependencies:**
- `httpx`
- `elspeth.contracts.Determinism`
- `elspeth.contracts.contract_propagation.narrow_contract_to_output`
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.core.security.web` (SSRFBlockedError, SSRFSafeRequest, validate_url_for_ssrf, NetworkError)
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.clients.http.AuditedHTTPClient`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.results.TransformResult`
- `elspeth.plugins.schema_factory.create_schema_from_config`
- `elspeth.plugins.transforms.web_scrape_errors.*`
- `elspeth.plugins.transforms.web_scrape_extraction.extract_content`
- `elspeth.plugins.transforms.web_scrape_fingerprint.compute_fingerprint`

**Row processing pattern:** 1:1. One URL row in, one enriched row out (or error result).

**External call boundaries:**
- **HTTP fetch** (primary Tier 3 boundary): `client.get_ssrf_safe(safe_request, ...)` returns `httpx.Response`. Status code is validated immediately after. The response body (`response.text`) is passed to `extract_content()` wrapped in a try/except that returns `TransformResult.error()` on failure. This is correct Tier 3 handling.
- **Payload store writes**: `ctx.payload_store.store(...)` — these are our system, not external. No wrapping required.

**Concerns:**
1. **`assert ctx.payload_store is not None`** (line 250) and **`assert ctx.rate_limit_registry is not None`** and **`assert ctx.landscape is not None`** and **`assert ctx.state_id is not None`** (lines 295-297). Per CLAUDE.md, `assert` on system-owned objects is acceptable — these are guaranteed by the engine executor. However, using `assert` means these checks are stripped in optimized mode (`python -O`). If this is ever run with `-O`, the crash on `None` will be a `AttributeError` on the next line rather than a clear message. Consider raising `RuntimeError` explicitly instead of `assert` for clearer failure messages.
2. **`assert cfg.schema_config is not None`** (line 170). Same concern as above.
3. The `_fetch_url` method imports `web_scrape_errors.SSRFBlockedError` locally (line 348) inside the `except` clause to re-raise it as a different exception type. This is a local re-import creating a shadow name (`WSSRFBlockedError`) because the module-level import alias from `web_scrape_errors` is `SSRFBlockedError` but the caught exception is `elspeth.core.security.web.SSRFBlockedError`. The two classes have the same name but are different types. This is a naming collision that is resolved by the local import alias. It is functional but fragile — it would be cleaner to use distinct names at import time.
4. The comment "Field collision check already done before fetch — no need to re-check here" (line 246) refers to collision detection done by the TransformExecutor before calling `process()`. This is a cross-boundary assumption documented only in a comment. If the executor ever changes this behavior, the transform silently overwrites fields.
5. **No validation of `response.text` content type or size** before passing to `extract_content()`. A server returning a 200 with a 500MB binary response will be passed to BeautifulSoup without size-gating. The `AuditedHTTPClient` may enforce timeouts, but there's no response body size limit.

---

### 10. `web_scrape_errors.py` — Error hierarchy

**Purpose:** Error class hierarchy for the web scrape transform. Provides a `WebScrapeError` base class with a `retryable: bool` property, and concrete subclasses for each error condition.

**Key classes:**
- `WebScrapeError(Exception)` — base, has `retryable` flag
- Retryable: `RateLimitError`, `NetworkError`, `ServerError`, `TimeoutError`
- Non-retryable: `NotFoundError`, `ForbiddenError`, `UnauthorizedError`, `SSLError`, `InvalidURLError`, `ParseError`, `SSRFBlockedError`, `ResponseTooLargeError`, `ConversionTimeoutError`

**Dependencies:** None (pure Python).

**Concerns:**
1. `TimeoutError` shadows Python's built-in `TimeoutError`. Within the module this is not a problem, but any code that does `from web_scrape_errors import *` or that catches `TimeoutError` expecting the built-in would be affected. Consider renaming to `WebScrapeTimeoutError` for clarity and to avoid the shadowing.
2. `ResponseTooLargeError` and `ConversionTimeoutError` are defined but there is no code in `web_scrape.py` that raises them. These error types are defined in anticipation of future features (size limiting, conversion timeouts) but are currently dead code.
3. `SSLError` is also defined but `web_scrape.py` never raises it — `httpx` SSL errors would be caught by the broad `httpx.ConnectError` handler and re-raised as `NetworkError`. So `SSLError` is dead code.
4. The error hierarchy is admirably clean. The `retryable` attribute on the base class is a better design than checking `isinstance(e, RetryableError)` — callers can use `e.retryable` without a type test.

---

### 11. `web_scrape_extraction.py` — Content extraction utility

**Purpose:** Converts HTML to markdown, text, or raw format. Uses `BeautifulSoup` for HTML parsing and tag stripping, `html2text` for markdown conversion.

**Key functions:**
- `extract_content(html: str, format: str, strip_elements: list[str] | None) -> str`

**Dependencies:**
- `html2text` (third-party)
- `bs4.BeautifulSoup` (third-party)

**External call boundaries:** None (pure in-process processing of already-fetched HTML).

**Concerns:**
1. **No size limiting.** If `html` is 100MB, `BeautifulSoup(html, "html.parser")` will parse it entirely in memory. This can cause OOM on malicious or unexpectedly large pages. Should add a `max_bytes` parameter or validate size before parsing.
2. The `format` parameter is a plain `str` with no runtime validation in this function — invalid values like `"json"` fall through to the `raise ValueError(f"Unknown format: {format}")` at the bottom only after parsing the HTML and attempting BeautifulSoup. Validation should occur at the top before any processing. (The config-level `WebScrapeConfig.format` field is a `str` with default `"markdown"` and no `Literal` constraint — validation is only at config parse time if the field had a validator.)
3. **Unsandboxed Jinja2 is listed as a cross-cutting concern in project memory, but this file uses `html2text` and `BeautifulSoup`, not Jinja2.** No Jinja2 concern here.
4. `html2text.HTML2Text()` settings are hardcoded (`ignore_links=False`, `body_width=0`, etc.). These are reasonable defaults for compliance monitoring but are not configurable. Not a bug.

---

### 12. `web_scrape_fingerprint.py` — Fingerprinting utility

**Purpose:** Computes SHA-256 fingerprints of page content for change detection. Two modes: `"content"` (normalizes whitespace first) and `"full"` (raw content as-is). A `"structure"` mode is defined but raises `NotImplementedError`.

**Key functions:**
- `normalize_for_fingerprint(content: str) -> str` — collapses whitespace to single spaces, strips.
- `compute_fingerprint(content: str, mode: str) -> str` — returns 64-char SHA-256 hex digest.

**Dependencies:**
- `hashlib` (stdlib)
- `re` (stdlib)

**Concerns:**
1. **`"structure"` mode raises `NotImplementedError`** with the note "defer to later task". This mode is accepted by `WebScrapeConfig.fingerprint_mode` (which has no `Literal` constraint) and will fail at runtime when a row is processed. Should either be removed or enforced as a config validation error at init time. Currently a latent runtime crash for any pipeline configured with `fingerprint_mode: structure`.
2. SHA-256 is appropriate for change detection. Using `hashlib` directly is correct — no concern with algorithm or implementation.

---

### 13. `azure/content_safety.py` — AzureContentSafety

**Purpose:** Security transform that calls Azure Content Safety API to detect harmful content (hate, violence, sexual, self-harm). Uses `BatchTransformMixin` for concurrent row processing with FIFO output ordering via a worker pool. Configurable severity thresholds (0-6) per category. Fails CLOSED: missing fields, unknown API categories, and malformed responses all return `TransformResult.error()`. API key passed via config (expected to be an environment variable reference like `${AZURE_CONTENT_SAFETY_KEY}`).

**Key classes:**
- `ContentSafetyThresholds(BaseModel)` — Per-category int thresholds, `extra="forbid"`.
- `AzureContentSafetyConfig(TransformDataConfig)` — `endpoint`, `api_key`, `fields`, `thresholds`, `max_capacity_retry_seconds`.
- `AzureContentSafety(BaseTransform, BatchTransformMixin)` — Uses worker pool pattern via `BatchTransformMixin`. `process()` raises `NotImplementedError` — callers must use `accept()`. `_analyze_content()` makes the API call and validates the response immediately at the Tier 3 boundary.

**Dependencies:**
- `httpx`
- `threading.Lock`
- `elspeth.contracts.Determinism`
- `elspeth.contracts.plugin_context.PluginContext`
- `elspeth.contracts.schema_contract.PipelineRow`
- `elspeth.plugins.base.BaseTransform`
- `elspeth.plugins.batching.BatchTransformMixin, OutputPort`
- `elspeth.plugins.config_base.TransformDataConfig`
- `elspeth.plugins.pooling.CapacityError, is_capacity_error`
- `elspeth.plugins.results.TransformResult`
- `elspeth.plugins.schema_factory.create_schema_from_config`
- `elspeth.plugins.transforms.azure.errors.MalformedResponseError`
- `elspeth.core.landscape.recorder.LandscapeRecorder` (TYPE_CHECKING)

**Row processing pattern:** 1:1 (concurrent, FIFO). One row in, one row out (pass-through or error). The `BatchTransformMixin` enables concurrency within the single-row semantic.

**External call boundaries:**
- **Azure Content Safety API** (Tier 3): `http_client.post(url, json={"text": text})`. Response validated immediately:
  - JSON parse in try/except raising `MalformedResponseError`
  - `data["categoriesAnalysis"]` key access wrapped in `except (KeyError, TypeError)`
  - Each category's `severity` validated as `int` in [0,6]
  - All 4 expected categories verified present (fail CLOSED if any missing)
  - Unknown categories raise `ValueError` (fail CLOSED)
  This is exemplary Tier 3 boundary handling.

**Concerns:**
1. **`_http_clients: dict[str, Any]`** — The type annotation uses `Any` instead of `AuditedHTTPClient`. The comment says "AuditedHTTPClient instances" but the type is erased. The import is deferred inside `_get_http_client()` to avoid circular import. This means `mypy` cannot verify operations on the cached clients. A `TYPE_CHECKING` import of `AuditedHTTPClient` and proper annotation would fix this without incurring the circular import at runtime.
2. **`_limiter: Any`** — Same pattern: type annotation erased to `Any`. Comment says "RateLimiter | NoOpLimiter | None" but the concrete types are not imported at the module level.
3. **`_recorder: LandscapeRecorder | None`** initialized to `None` and populated in `on_start()`. The `accept()` method also sets it on first row (`if self._recorder is None and ctx.landscape is not None: self._recorder = ctx.landscape`). This dual-initialization path (on_start OR first accept) is defensive code — the engine should guarantee `on_start()` is called before `accept()`. The second path exists "just in case." Per the CLAUDE.md prohibition on defensive programming on system-owned code, this `if self._recorder is None` check in `accept()` is a defensive pattern that should be removed in favor of trusting the engine calling contract.
4. **`assert self._recorder is not None`** in `_get_http_client()` — strips in optimized mode. Same as web_scrape.py concern. Consider `RuntimeError` instead.
5. The `_EXPECTED_CATEGORIES` set is defined as a local variable inside `_analyze_content()` rather than as a module-level constant. This is a minor style issue — it is re-created on every call.
6. `_get_fields_to_scan()` is duplicated identically in `KeywordFilter`, `AzureContentSafety`, and `AzurePromptShield`. Three copies of the same 6-line method.

---

### 14. `azure/prompt_shield.py` — AzurePromptShield

**Purpose:** Security transform that calls Azure Prompt Shield API to detect jailbreak attempts (user prompt attacks) and prompt injection (document attacks). Binary detection — no thresholds. Uses `BatchTransformMixin` for concurrent row processing. Configurable `analysis_type` to avoid double API cost when only one analysis path is needed. Validates bool types strictly in response parsing (null or string would fail-open on a bool check).

**Key classes:**
- `AzurePromptShieldConfig(TransformDataConfig)` — `endpoint`, `api_key`, `fields`, `analysis_type` (pattern-constrained string), `max_capacity_retry_seconds`.
- `AzurePromptShield(BaseTransform, BatchTransformMixin)` — Structurally identical to `AzureContentSafety` except for the API call and response parsing in `_analyze_prompt()`.

**Dependencies:** (Identical to `AzureContentSafety` — same imports, same patterns.)

**Row processing pattern:** 1:1 (concurrent, FIFO).

**External call boundaries:**
- **Azure Prompt Shield API** (Tier 3): `http_client.post(url, json=request_body)`. Response validated immediately:
  - JSON parse in try/except raising `MalformedResponseError`
  - `userPromptAnalysis` must be `dict` (not None, not list)
  - `attackDetected` must be strict `bool` (not truthy/falsy — prevents null-is-falsy fail-open)
  - `documentsAnalysis` must be list with exactly 1 entry
  - Each document's `attackDetected` must be strict `bool`
  This is exemplary Tier 3 handling with particularly careful bool type checking.

**Concerns:**
1. **Structural near-duplication with `AzureContentSafety`**: `__init__`, `on_start`, `connect_output`, `accept`, `process`, `_process_row`, `_get_http_client`, `_get_fields_to_scan`, and `close` are effectively identical between the two classes, with only the API endpoint URL and response parsing differing. Approximately 150-200 lines of structural duplication.
2. **`_http_clients: dict[str, Any]`** and **`_limiter: Any`** — same type-erasure concerns as `AzureContentSafety`.
3. **Defensive `if self._recorder is None`** in `accept()` — same concern as `AzureContentSafety`. Should be removed.
4. **`_get_fields_to_scan()` triple duplication** — same as `AzureContentSafety` concern.
5. **`data.get("userPromptAnalysis") if isinstance(data, dict) else None`** — the `isinstance(data, dict)` check after JSON parsing is defensive programming on external data. This is legitimate (Tier 3 data), but it could be more direct: if `data` is not a dict after `response.json()`, it should raise `MalformedResponseError` immediately rather than assigning `None` and then failing the `isinstance(user_prompt_analysis, dict)` check one line later. The two-step approach works but the intent is clearer with an upfront type guard.

---

### 15. `azure/errors.py` — Shared error types

**Purpose:** Provides `MalformedResponseError` as a shared error type for Azure transform plugins.

**Key classes:**
- `MalformedResponseError(Exception)` — No fields, used as a semantic error type to distinguish "bad JSON/structure from Azure API" from network errors.

**Dependencies:** None.

**Concerns:** None. This is minimal, well-placed, and correctly scoped to the azure/ subpackage.

---

## Overall Analysis

---

### 1. Transform Type Distribution

| Type | Count | Plugins |
|------|-------|---------|
| Row Transform (1:1, no external call) | 5 | PassThrough, Truncate, KeywordFilter, FieldMapper, FieldCollision (utility) |
| Row Transform (1:1, external HTTP call) | 3 | WebScrapeTransform, AzureContentSafety, AzurePromptShield |
| Deaggregation (1:N) | 1 | JSONExplode |
| Batch Transform (N:M, replication) | 1 | BatchReplicate |
| Batch Transform (N:1, aggregation) | 1 | BatchStats |

Pure row transforms dominate (5 of 11 plugins). Three plugins make external HTTP calls. Two plugins use the batch-aware pattern. One plugin handles 1:N expansion. The distribution is well-balanced for a general-purpose framework.

---

### 2. Web Scrape Cluster — 4 Files

The web scrape functionality is split across four files:

| File | Responsibility |
|------|---------------|
| `web_scrape.py` | Main transform class, orchestration, SSRF, HTTP, row enrichment |
| `web_scrape_errors.py` | Error class hierarchy (retryable vs non-retryable) |
| `web_scrape_extraction.py` | HTML → markdown/text/raw conversion utility |
| `web_scrape_fingerprint.py` | SHA-256 fingerprinting utility |

**Verdict: Good separation.** Each module has a single clear responsibility. The separation is not fragmentation — `web_scrape.py` would be significantly longer without it (~400 lines currently vs. ~600+ if merged). The error hierarchy in `web_scrape_errors.py` is particularly well-structured (clean retryable flag pattern). The utility modules (`extraction`, `fingerprint`) are independently testable.

The only organizational concern is that `web_scrape_errors.py` contains error types that are defined but never raised (`SSLError`, `ResponseTooLargeError`, `ConversionTimeoutError`), suggesting anticipation of future features. These should either be implemented or removed per the no-legacy-code policy.

---

### 3. Azure Safety Transforms

Both `AzureContentSafety` and `AzurePromptShield` use the `BatchTransformMixin` pattern which provides:
- A worker pool for concurrent API calls
- A `RowReorderBuffer` for FIFO output ordering despite out-of-order completion
- Backpressure via `max_pending` (blocks `accept()` when buffer is full)
- `CapacityError` signaling for worker-level retry on 429/503/529

**Content Safety flow:**
1. `accept(row, ctx)` → `accept_row(row, ctx, self._process_row)`
2. Worker calls `_process_row(row, ctx)` → `_process_single_with_state(row, state_id)`
3. `_get_fields_to_scan(row)` → iterate fields
4. `_analyze_content(text, state_id)` → Azure API via `AuditedHTTPClient`
5. Immediate Tier 3 validation of response: JSON parse → structure check → category validation → severity range check → completeness check
6. `_check_thresholds(analysis)` → severity > threshold = `TransformResult.error()`
7. Pass → `TransformResult.success(row)` (row unchanged)

**Prompt Shield flow:** Structurally identical. API response validation additionally enforces strict `bool` types on `attackDetected` fields (preventing null/truthy false-positives in either direction).

**Audit trail:** Both use `AuditedHTTPClient` which automatically records to the Landscape. The per-state_id client cache ensures `(state_id, call_index)` uniqueness even across worker-pool retries.

**Security posture:** Both transforms are fail-closed: missing configured fields, non-string values, unknown API categories (content safety), malformed responses, and absent categories all produce `TransformResult.error()` rather than passing the row through.

---

### 4. Batch Transforms

`BatchReplicate` and `BatchStats` both use `is_batch_aware = True`. The engine buffers rows until a trigger fires (count or timeout), then calls `process(rows: list[PipelineRow], ctx)`.

- **BatchReplicate (N:M):** Replicates rows based on a field value. Each copy gets a `copy_index`. Rows with invalid copies values are quarantined inside `success_reason["metadata"]` rather than as separate error results — this is the significant design concern (see Concern #1 under BatchReplicate).
- **BatchStats (N:1):** Aggregates rows into a single statistics row. Clean N:1 reduction. The output schema is always freshly constructed (OBSERVED mode, all fields typed as `object`).

Both use `# type: ignore[override]` on `process()` to accommodate the `list[PipelineRow]` vs `PipelineRow` signature difference. Both handle empty batches with a synthetic result row containing `batch_empty: True`.

---

### 5. Shared Patterns

The following patterns appear consistently across transforms:

| Pattern | Files | Notes |
|---------|-------|-------|
| `TransformDataConfig.from_dict(config)` at init | All | Standard Pydantic config parsing |
| `copy.deepcopy(row.to_dict())` before mutation | PassThrough, Truncate, FieldMapper, BatchReplicate | Prevents in-place mutation of input row |
| `type(x) is not int/str` (strict type check, rejects bool) | Truncate, BatchReplicate, BatchStats | Correct Tier 2 enforcement |
| `_get_fields_to_scan(row)` supporting `"all"` or list | KeywordFilter, AzureContentSafety, AzurePromptShield | Triplicated |
| `narrow_contract_to_output()` for contract propagation | FieldMapper, JSONExplode, WebScrapeTransform | Missing from Truncate (acceptable — schema unchanged) |
| `self.declared_output_fields = frozenset(...)` | JSONExplode, BatchReplicate, WebScrapeTransform | For TransformExecutor collision detection |
| `assert ctx.X is not None` guards | WebScrapeTransform, AzureContentSafety | Use RuntimeError instead |
| `validate_input: bool` stored but unused | FieldMapper, PassThrough | Dead config field |
| `close()` returning `pass` | All simple transforms | Correct for stateless transforms |
| Empty batch → synthetic `{"batch_empty": True}` row | BatchReplicate, BatchStats | Consistent sentinel pattern |
| `is_batch_aware = True` + `# type: ignore[override]` | BatchReplicate, BatchStats | Typed batch protocol would eliminate this |

---

### 6. Trust Tier Compliance

| Transform | Tier 2 Compliance (no coercion on row values) | External Call Boundary (Tier 3) |
|-----------|----------------------------------------------|--------------------------------|
| FieldMapper | COMPLIANT — crashes on wrong type in `_reject_duplicate_targets`; missing fields return error | N/A |
| PassThrough | COMPLIANT — no type operations | N/A |
| Truncate | COMPLIANT — `type(value) is not str` returns error | N/A |
| KeywordFilter | COMPLIANT — skips non-string fields silently (see Concern #3) | N/A |
| JSONExplode | COMPLIANT — raises TypeError on non-list (intentional crash) | N/A |
| BatchReplicate | COMPLIANT — raises TypeError on non-int copies_field | N/A |
| BatchStats | COMPLIANT — raises TypeError on non-numeric value_field | N/A |
| WebScrapeTransform | COMPLIANT | COMPLIANT — response wrapped in try/except, status validated immediately |
| AzureContentSafety | COMPLIANT | COMPLIANT — exemplary boundary validation |
| AzurePromptShield | COMPLIANT | COMPLIANT — exemplary boundary validation with strict bool checking |

**Overall Tier compliance: Good.** The main gap is that `KeywordFilter`, `AzureContentSafety`, and `AzurePromptShield` silently skip non-string values for configured (non-"all") fields without recording the skip in the audit trail.

---

### 7. Code Duplication

#### HIGH PRIORITY — `_get_fields_to_scan()` (3 copies)

Identical 6-line method in `KeywordFilter`, `AzureContentSafety`, and `AzurePromptShield`:

```python
def _get_fields_to_scan(self, row: PipelineRow) -> list[str]:
    if self._fields == "all":
        return [field_name for field_name in row if isinstance(row[field_name], str)]
    elif isinstance(self._fields, str):
        return [self._fields]
    else:
        return self._fields
```

Should be extracted to `elspeth/plugins/utils.py` as `get_fields_to_scan(fields_config, row)`.

#### HIGH PRIORITY — `AzureContentSafety` / `AzurePromptShield` structural duplication (~200 lines)

The two Azure transforms share identical implementations of: `__init__` structure, `on_start`, `connect_output`, `accept`, `process`, `_process_row`, `_get_http_client`, `_get_fields_to_scan`, `close`. Only `_analyze_content` vs `_analyze_prompt` and their config classes differ.

Recommended remediation: Extract a `BaseAzureSecurityTransform(BaseTransform, BatchTransformMixin)` abstract base class with the shared infrastructure. Concrete subclasses override `_analyze(text, state_id, token_id) -> dict[str, Any]` and implement the check logic. This reduces the azure/ package from ~400 lines of structural duplication to ~100 lines of shared base + ~100 lines per concrete class.

#### MEDIUM PRIORITY — Normalized field name resolution (2 copies)

```python
if field_name in output:
    normalized_field_name = field_name
else:
    normalized_field_name = row.contract.resolve_name(field_name)
```

Appears in `Truncate.process()` and `FieldMapper.process()`. Should be a utility function `resolve_normalized_field_name(row, field_name, output)`.

#### LOW PRIORITY — Empty batch sentinel pattern (2 copies)

`BatchReplicate` and `BatchStats` both produce a synthetic `{"batch_empty": True}` row with a fresh `SchemaContract(mode="OBSERVED", ...)`. This could be a shared utility function.

#### LOW PRIORITY — `validate_input` dead config field (2 copies)

`PassThrough` and `FieldMapper` both declare `validate_input: bool` that is stored but never used in `process()`. Either implement the validation or remove the config field.

---

### 8. Concerns and Recommendations — Ranked by Severity

#### SEVERITY 1 — Bug: BatchReplicate quarantined rows not audited as distinct terminal tokens

**Location:** `batch_replicate.py`, `process()` method, `quarantined` list handling.

**Issue:** When a row in a batch has an invalid `copies` value (< 1 or > max_copies), it is added to the local `quarantined` list and reported as `success_reason["metadata"]["quarantined"]`. This means:
- The quarantined row's data is embedded in the JSON of a SUCCESS result
- The row is not recorded as a separate QUARANTINED token in the Landscape
- The audit trail shows "batch processed with 2 quarantined rows" but cannot answer "which input rows were quarantined and why"
- The `quarantined_count` and `quarantined` list in `success_reason` are not linked to input row IDs

This violates the ELSPETH requirement that every row reaches exactly one terminal state. The fix requires returning a mixed result that includes both the successful replicated rows AND individual error results for quarantined rows, or returning an error result per invalid row that the engine routes separately. However, the batch transform API (`TransformResult.success_multi()`) returns a single result for the batch — individual quarantine recording may require engine-level support.

#### SEVERITY 2 — Design gap: `assert` statements stripped in optimized mode

**Locations:** `web_scrape.py` (4 asserts), `azure/content_safety.py` (1 assert in `_get_http_client`).

**Issue:** `assert ctx.payload_store is not None`, `assert ctx.rate_limit_registry is not None`, etc. are stripped when Python is run with `-O`. This converts a clear error into an `AttributeError` on `None` with no context message.

**Recommendation:** Replace all `assert` guards on context fields with explicit `RuntimeError` raises:
```python
if ctx.payload_store is None:
    raise RuntimeError("payload_store is required for WebScrapeTransform. Ensure transform is executed through the engine.")
```

#### SEVERITY 3 — Design: AzureContentSafety / AzurePromptShield structural duplication

**Locations:** `azure/content_safety.py`, `azure/prompt_shield.py`.

**Issue:** ~200 lines of structural duplication between the two Azure transforms. Infrastructure code (`__init__`, `on_start`, `connect_output`, `accept`, `process`, `_process_row`, `_get_http_client`, `close`) is identical. Changes to the shared infrastructure must be applied twice.

**Recommendation:** Extract `BaseAzureSecurityTransform` abstract base class.

#### SEVERITY 4 — Latent crash: `fingerprint_mode: "structure"` accepted in config but raises NotImplementedError at runtime

**Location:** `web_scrape_fingerprint.py`, `compute_fingerprint()`.

**Issue:** `"structure"` is a recognized mode value (not filtered at config validation) but raises `NotImplementedError` when a row is processed. Any pipeline configured with `fingerprint_mode: structure` will crash on the first row.

**Recommendation:** Either implement structure mode or add a `Literal["content", "full"]` type annotation and Pydantic validator on `WebScrapeConfig.fingerprint_mode` to reject `"structure"` at config load time with a clear message.

#### SEVERITY 5 — Unused error types in `web_scrape_errors.py`

**Locations:** `web_scrape_errors.py`: `SSLError`, `ResponseTooLargeError`, `ConversionTimeoutError`.

**Issue:** Three error classes are defined but never raised. They represent anticipated future features (SSL validation, response size limiting, conversion timeouts). Per the no-legacy-code policy, dead code should be removed.

**Recommendation:** Delete `SSLError`, `ResponseTooLargeError`, and `ConversionTimeoutError` until the corresponding features are implemented. Additionally delete `TimeoutError` (which shadows Python's built-in) and consolidate its use cases into `NetworkError`.

#### SEVERITY 6 — `_get_fields_to_scan()` triplicated

**Locations:** `keyword_filter.py`, `azure/content_safety.py`, `azure/prompt_shield.py`.

**Recommendation:** Extract to `elspeth/plugins/utils.py`:
```python
def get_fields_to_scan(fields_config: str | list[str], row: PipelineRow) -> list[str]:
    if fields_config == "all":
        return [f for f in row if isinstance(row[f], str)]
    elif isinstance(fields_config, str):
        return [fields_config]
    else:
        return fields_config
```

#### SEVERITY 7 — Silent skip of non-string configured fields in security transforms

**Locations:** `keyword_filter.py` (line ~171: `if not isinstance(value, str): continue`), `azure/content_safety.py` and `azure/prompt_shield.py` (similar non-string field skip in `_process_single_with_state`).

**Issue:** When `fields` is an explicit list (not `"all"`) and a configured field exists but is not a string, `KeywordFilter` silently skips it. The row passes through as if it had been scanned. For a security transform, this is a fail-open path — a field containing non-string data (e.g., an int that should have been a string, indicating a schema bug upstream) bypasses the security check.

**Note:** `AzureContentSafety` and `AzurePromptShield` handle this correctly: they return `TransformResult.error()` for non-string configured fields (fail CLOSED). `KeywordFilter` does not — it silently continues. This asymmetry should be resolved.

**Recommendation:** In `KeywordFilter.process()`, change the non-string handling for explicitly-configured fields:
```python
if not isinstance(value, str):
    return TransformResult.error({
        "reason": "non_string_field",
        "field": field_name,
        "actual_type": type(value).__name__,
    }, retryable=False)
```

#### SEVERITY 8 — Defensive `if self._recorder is None` in Azure transforms' `accept()` method

**Locations:** `azure/content_safety.py` line ~261, `azure/prompt_shield.py` line ~232.

**Issue:** Both transforms check `if self._recorder is None and ctx.landscape is not None: self._recorder = ctx.landscape` inside `accept()`. This is a defensive fallback for when `on_start()` is not called before `accept()`. Per CLAUDE.md, defensive programming on system-owned code is prohibited — the engine is responsible for calling `on_start()` before the first `accept()`. This check is papering over a potential engine lifecycle bug.

**Recommendation:** Remove the defensive recorder capture from `accept()`. If `on_start()` is not called first, the `RuntimeError("PromptShield requires recorder for audited calls.")` in `_get_http_client()` will fire, which is the correct crash behavior.

#### SEVERITY 9 — `validate_input` config field stored but never used

**Locations:** `passthrough.py`, `field_mapper.py`.

**Issue:** Both transforms declare `validate_input: bool = False` in their config and store it as `self.validate_input`, but the `process()` method never uses it. The docstrings claim "Raises: ValidationError: If validate_input=True" but there is no such code path. This is dead config and misleading documentation.

**Recommendation:** Either implement input validation against `self.input_schema` when `validate_input=True`, or remove the config field entirely.

#### SEVERITY 10 — `WebScrapeConfig.format` is `str` without a `Literal` type constraint

**Locations:** `web_scrape.py`, `web_scrape_extraction.py`.

**Issue:** `WebScrapeConfig.format: str = "markdown"` accepts any string at config load time. Invalid values (e.g., `"json"`) are only rejected at runtime inside `extract_content()` after HTML parsing has already occurred. The same applies to `fingerprint_mode`.

**Recommendation:** Use `Literal["markdown", "text", "raw"]` for `format` and `Literal["content", "full"]` for `fingerprint_mode` (removing `"structure"` per Severity 4 above).

---

### 9. Confidence Assessment

**High.** All 15 files were read in full. The analysis is based on direct code inspection rather than inference. The concerns are supported by specific line-level observations. The duplicate code patterns are confirmed by direct comparison between files. The trust tier compliance assessment is grounded in the CLAUDE.md rules and explicit code paths.

The only area of lower certainty is the `BatchReplicate` quarantine concern (Severity 1): understanding exactly how the engine records batch results and whether there is existing Landscape support for "sub-row quarantine within a batch" would require reading the batch executor and orchestrator. The concern is identified from the transform code alone.
