# src/elspeth/plugins/llm/openrouter_multi_query.py
"""OpenRouter Multi-Query LLM transform for case study x criteria evaluation.

Executes multiple LLM queries per row via OpenRouter's HTTP API,
merging all results into a single output row with all-or-nothing error handling.

Uses HTTP-based communication (AuditedHTTPClient) rather than SDK-based
communication like the Azure variant.
"""

from __future__ import annotations

import json
from threading import Lock
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import Field, field_validator

from elspeth.contracts import Determinism, TransformResult
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.clients.http import AuditedHTTPClient
from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.multi_query import CaseStudyConfig, CriterionConfig, QuerySpec
from elspeth.plugins.llm.openrouter import OpenRouterConfig
from elspeth.plugins.llm.templates import PromptTemplate, TemplateError
from elspeth.plugins.pooling import CapacityError, PooledExecutor, is_capacity_error
from elspeth.plugins.schema_factory import create_schema_from_config

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class OpenRouterMultiQueryConfig(OpenRouterConfig):
    """Configuration for OpenRouter multi-query LLM transform.

    Extends OpenRouterConfig with:
    - case_studies: List of case study definitions
    - criteria: List of criterion definitions
    - output_mapping: JSON field -> row column suffix mapping
    - response_format: Expected LLM output format (json)

    The cross-product of case_studies x criteria defines all queries.

    Example:
        transforms:
          - plugin: openrouter_multi_query_llm
            options:
              model: "anthropic/claude-3-opus"
              api_key: "${OPENROUTER_API_KEY}"
              template: |
                Case: {{ input_1 }}, {{ input_2 }}
                Criterion: {{ criterion.name }}
              case_studies:
                - name: cs1
                  input_fields: [cs1_bg, cs1_sym]
                - name: cs2
                  input_fields: [cs2_bg, cs2_sym]
              criteria:
                - name: diagnosis
                  code: DIAG
                - name: treatment
                  code: TREAT
              response_format: json
              output_mapping:
                score: score
                rationale: rationale
              pool_size: 4
              schema:
                fields: dynamic
    """

    case_studies: list[CaseStudyConfig] = Field(
        ...,
        description="Case study definitions",
        min_length=1,
    )
    criteria: list[CriterionConfig] = Field(
        ...,
        description="Criterion definitions",
        min_length=1,
    )
    output_mapping: dict[str, str] = Field(
        ...,
        description="JSON field -> row column suffix mapping",
    )
    response_format: str = Field(
        "json",
        description="Expected response format",
    )

    @field_validator("output_mapping")
    @classmethod
    def validate_output_mapping_not_empty(cls, v: dict[str, str]) -> dict[str, str]:
        """Ensure at least one output mapping."""
        if not v:
            raise ValueError("output_mapping cannot be empty")
        return v

    def expand_queries(self) -> list[QuerySpec]:
        """Expand config into QuerySpec list (case_studies x criteria).

        Returns:
            List of QuerySpec, one per (case_study, criterion) pair
        """
        specs: list[QuerySpec] = []

        for case_study in self.case_studies:
            for criterion in self.criteria:
                spec = QuerySpec(
                    case_study_name=case_study.name,
                    criterion_name=criterion.name,
                    input_fields=case_study.input_fields,
                    output_prefix=f"{case_study.name}_{criterion.name}",
                    criterion_data=criterion.to_template_data(),
                    case_study_data=case_study.to_template_data(),
                )
                specs.append(spec)

        return specs


# Resolve forward references for Pydantic (CaseStudyConfig, CriterionConfig)
OpenRouterMultiQueryConfig.model_rebuild()


class OpenRouterMultiQueryLLMTransform(BaseTransform):
    """LLM transform that executes case_studies x criteria queries per row via OpenRouter.

    For each row, expands the cross-product of case studies and criteria
    into individual LLM queries. All queries run in parallel (up to pool_size),
    with all-or-nothing error semantics (if any query fails, the row fails).

    Uses HTTP-based communication via AuditedHTTPClient, unlike the Azure
    variant which uses the OpenAI SDK.

    Configuration example:
        transforms:
          - plugin: openrouter_multi_query_llm
            options:
              model: "anthropic/claude-3-opus"
              api_key: "${OPENROUTER_API_KEY}"
              template: |
                Case: {{ row.input_1 }}, {{ row.input_2 }}
                Criterion: {{ row.criterion.name }}
              case_studies:
                - name: cs1
                  input_fields: [cs1_bg, cs1_sym, cs1_hist]
                - name: cs2
                  input_fields: [cs2_bg, cs2_sym, cs2_hist]
              criteria:
                - name: diagnosis
                  code: DIAG
                - name: treatment
                  code: TREAT
              response_format: json
              output_mapping:
                score: score
                rationale: rationale
              pool_size: 4
              schema:
                fields: dynamic

    Output fields per query:
        {case_study}_{criterion}_{json_field} for each output_mapping entry
        Plus metadata: _usage, _template_hash, _model
    """

    name = "openrouter_multi_query_llm"
    is_batch_aware = True
    creates_tokens = False  # Does not create new tokens (1 row in -> 1 row out)
    determinism: Determinism = Determinism.NON_DETERMINISTIC
    plugin_version = "1.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize transform with multi-query configuration."""
        super().__init__(config)

        # Parse config
        cfg = OpenRouterMultiQueryConfig.from_dict(config)

        # Store OpenRouter connection settings
        self._api_key = cfg.api_key
        self._base_url = cfg.base_url
        self._timeout = cfg.timeout_seconds
        self._model = cfg.model

        # Store template settings
        self._template = PromptTemplate(
            cfg.template,
            template_source=cfg.template_source,
            lookup_data=cfg.lookup,
            lookup_source=cfg.lookup_source,
        )
        self._system_prompt = cfg.system_prompt
        self._system_prompt_source = cfg.system_prompt_source
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_tokens
        self._on_error = cfg.on_error

        # Multi-query specific settings
        self._output_mapping = cfg.output_mapping
        self._response_format = cfg.response_format

        # Pre-expand query specs (case_studies x criteria)
        self._query_specs: list[QuerySpec] = cfg.expand_queries()

        # Schema from config
        assert cfg.schema_config is not None
        schema = create_schema_from_config(
            cfg.schema_config,
            f"{self.name}Schema",
            allow_coercion=False,
        )
        self.input_schema = schema
        self.output_schema = schema

        # Pooled execution setup
        if cfg.pool_config is not None:
            self._executor: PooledExecutor | None = PooledExecutor(cfg.pool_config)
        else:
            self._executor = None

        # Client caching (same pattern as OpenRouterLLMTransform)
        self._recorder: LandscapeRecorder | None = None
        self._http_clients: dict[str, AuditedHTTPClient] = {}
        self._http_clients_lock = Lock()

    def on_start(self, ctx: PluginContext) -> None:
        """Capture recorder reference for pooled execution."""
        self._recorder = ctx.landscape

    def _get_http_client(self, state_id: str) -> AuditedHTTPClient:
        """Get or create HTTP client for a state_id.

        Clients are cached to preserve call_index across retries.
        This ensures uniqueness of (state_id, call_index) even when
        the pooled executor retries after CapacityError.

        Thread-safe: multiple workers can call this concurrently.
        """
        with self._http_clients_lock:
            if state_id not in self._http_clients:
                if self._recorder is None:
                    raise RuntimeError("OpenRouter multi-query transform requires recorder. Ensure on_start was called.")
                self._http_clients[state_id] = AuditedHTTPClient(
                    recorder=self._recorder,
                    state_id=state_id,
                    timeout=self._timeout,
                    base_url=self._base_url,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "HTTP-Referer": "https://github.com/elspeth-rapid",  # Required by OpenRouter
                    },
                )
            return self._http_clients[state_id]

    def _process_single_query(
        self,
        row: dict[str, Any],
        spec: QuerySpec,
        state_id: str,
    ) -> TransformResult:
        """Process a single query (one case_study x criterion pair) via HTTP.

        Args:
            row: Full input row
            spec: Query specification with input field mapping
            state_id: State ID for audit trail

        Returns:
            TransformResult with mapped output fields

        Raises:
            CapacityError: On rate limit (429/503/529) for pooled retry
        """
        # 1. Build synthetic row for PromptTemplate
        # Templates use {{ row.input_1 }}, {{ row.criterion }}, {{ row.original }}, {{ lookup }}
        # This preserves PromptTemplate's audit metadata (template_hash, variables_hash)
        synthetic_row = spec.build_template_context(row)
        # synthetic_row now contains: input_1, input_2, ..., criterion, row (original)

        # 2. Render template using PromptTemplate (preserves audit metadata)
        # THEIR DATA - wrap in try/catch
        try:
            rendered = self._template.render_with_metadata(synthetic_row)
        except TemplateError as e:
            return TransformResult.error(
                {
                    "reason": "template_rendering_failed",
                    "error": str(e),
                    "query": spec.output_prefix,
                    "template_hash": self._template.template_hash,
                }
            )

        # 3. Build messages
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": rendered.prompt})

        # 4. Build HTTP request body
        request_body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens:
            request_body["max_tokens"] = self._max_tokens

        # 5. Get HTTP client
        http_client = self._get_http_client(state_id)

        # 6. Call OpenRouter API (EXTERNAL - wrap, raise CapacityError for retry)
        try:
            response = http_client.post(
                "/chat/completions",
                json=request_body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Check for capacity error (429/503/529)
            if is_capacity_error(e.response.status_code):
                raise CapacityError(e.response.status_code, str(e)) from e
            # Non-capacity HTTP error
            return TransformResult.error(
                {
                    "reason": "api_call_failed",
                    "error": str(e),
                    "query": spec.output_prefix,
                },
                retryable=False,
            )
        except httpx.RequestError as e:
            return TransformResult.error(
                {
                    "reason": "api_call_failed",
                    "error": str(e),
                    "query": spec.output_prefix,
                },
                retryable=False,
            )

        # 7. Parse JSON response from HTTP (EXTERNAL DATA - wrap)
        try:
            data = response.json()
        except (ValueError, TypeError) as e:
            return TransformResult.error(
                {
                    "reason": "invalid_json_response",
                    "error": f"Response is not valid JSON: {e}",
                    "query": spec.output_prefix,
                    "content_type": response.headers.get("content-type", "unknown"),
                    "body_preview": response.text[:500] if response.text else None,
                },
                retryable=False,
            )

        # 8. Extract content from OpenRouter response (EXTERNAL DATA - wrap)
        try:
            choices = data["choices"]
            if not choices:
                return TransformResult.error(
                    {
                        "reason": "empty_choices",
                        "query": spec.output_prefix,
                        "response": data,
                    },
                    retryable=False,
                )
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            return TransformResult.error(
                {
                    "reason": "malformed_response",
                    "error": f"{type(e).__name__}: {e}",
                    "query": spec.output_prefix,
                    "response_keys": list(data.keys()) if isinstance(data, dict) else None,
                },
                retryable=False,
            )

        usage = data.get("usage", {})

        # 9. Parse LLM response content as JSON (THEIR DATA - wrap)
        # Strip markdown code blocks if present (common LLM behavior)
        content_str = content.strip()
        if content_str.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = content_str.find("\n")
            if first_newline != -1:
                content_str = content_str[first_newline + 1 :]
            # Remove closing fence
            if content_str.endswith("```"):
                content_str = content_str[:-3].strip()

        try:
            parsed = json.loads(content_str)
        except json.JSONDecodeError as e:
            return TransformResult.error(
                {
                    "reason": "json_parse_failed",
                    "error": str(e),
                    "query": spec.output_prefix,
                    "raw_response": content[:500] if content else None,  # Truncate for audit
                }
            )

        # Validate JSON type is object (EXTERNAL DATA - validate structure)
        if not isinstance(parsed, dict):
            return TransformResult.error(
                {
                    "reason": "invalid_json_type",
                    "expected": "object",
                    "actual": type(parsed).__name__,
                    "query": spec.output_prefix,
                    "raw_response": content[:500] if content else None,
                }
            )

        # 10. Map output fields
        output: dict[str, Any] = {}
        for json_field, suffix in self._output_mapping.items():
            output_key = f"{spec.output_prefix}_{suffix}"
            if json_field not in parsed:
                return TransformResult.error(
                    {
                        "reason": "missing_output_field",
                        "field": json_field,
                        "query": spec.output_prefix,
                    }
                )
            output[output_key] = parsed[json_field]

        # 11. Add metadata for audit trail
        output[f"{spec.output_prefix}_usage"] = usage
        output[f"{spec.output_prefix}_model"] = data.get("model", self._model)
        # Template metadata for reproducibility
        output[f"{spec.output_prefix}_template_hash"] = rendered.template_hash
        output[f"{spec.output_prefix}_variables_hash"] = rendered.variables_hash
        output[f"{spec.output_prefix}_template_source"] = rendered.template_source
        output[f"{spec.output_prefix}_lookup_hash"] = rendered.lookup_hash
        output[f"{spec.output_prefix}_lookup_source"] = rendered.lookup_source
        output[f"{spec.output_prefix}_system_prompt_source"] = self._system_prompt_source

        return TransformResult.success(output)

    def process(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Process row(s) with all queries in parallel.

        For single row: executes all (case_study x criterion) queries,
        merges results into one output row.

        For batch: processes each row independently (batch of multi-query rows).
        """
        # Batch dispatch
        if isinstance(row, list):
            return self._process_batch(row, ctx)

        # Single row processing
        return self._process_single_row(row, ctx)

    def _process_single_row_internal(
        self,
        row: dict[str, Any],
        state_id: str,
    ) -> TransformResult:
        """Internal row processing with explicit state_id.

        Used by both single-row and batch processing paths.

        Args:
            row: Input row with all case study fields
            state_id: State ID for audit trail

        Returns:
            TransformResult with all query results merged, or error
        """
        # Execute all queries (parallel or sequential)
        if self._executor is not None:
            results = self._execute_queries_parallel(row, state_id)
        else:
            results = self._execute_queries_sequential(row, state_id)

        # Check for failures (all-or-nothing for this row)
        failed = [(spec, r) for spec, r in zip(self._query_specs, results, strict=True) if r.status != "success"]
        if failed:
            return TransformResult.error(
                {
                    "reason": "query_failed",
                    "failed_queries": [{"query": spec.output_prefix, "error": r.reason} for spec, r in failed],
                    "succeeded_count": len(results) - len(failed),
                    "total_count": len(results),
                }
            )

        # Merge all results into output row
        output = dict(row)
        for result in results:
            # Check for row presence: successful results should always have a row,
            # but TransformResult supports multi-output scenarios where row may be
            # None even on success. This check is defensive for that edge case.
            if result.row is not None:
                output.update(result.row)

        return TransformResult.success(output)

    def _process_single_row(
        self,
        row: dict[str, Any],
        ctx: PluginContext,
    ) -> TransformResult:
        """Process a single row with all queries in parallel.

        Executes all (case_study x criterion) queries for this row.
        All-or-nothing: if any query fails, the entire row fails.

        Args:
            row: Input row with all case study fields
            ctx: Plugin context with landscape and state_id

        Returns:
            TransformResult with all query results merged, or error
        """
        if ctx.landscape is None or ctx.state_id is None:
            raise RuntimeError("Multi-query transform requires landscape recorder and state_id.")

        # Capture recorder for pooled execution
        if self._recorder is None:
            self._recorder = ctx.landscape

        try:
            return self._process_single_row_internal(row, ctx.state_id)
        finally:
            # Clean up cached clients for this state_id
            with self._http_clients_lock:
                self._http_clients.pop(ctx.state_id, None)

    def _execute_queries_parallel(
        self,
        row: dict[str, Any],
        state_id: str,
    ) -> list[TransformResult]:
        """Execute queries in parallel via PooledExecutor with AIMD retry.

        Uses PooledExecutor.execute_batch() to get:
        - Automatic retry on capacity errors with AIMD backoff
        - Timeout after max_capacity_retry_seconds
        - Proper audit trail for all retry attempts

        Args:
            row: The input row data
            state_id: State ID for audit trail (shared across all queries for this row)

        Returns:
            List of TransformResults in query spec order
        """
        from elspeth.plugins.pooling.executor import RowContext

        # Type narrowing - caller ensures executor is not None
        assert self._executor is not None

        # Build RowContext for each query
        # All queries share the same state_id (FK constraint)
        # Uniqueness comes from call_index allocated by recorder
        contexts = [
            RowContext(
                row={"original_row": row, "spec": spec},
                state_id=state_id,
                row_index=i,
            )
            for i, spec in enumerate(self._query_specs)
        ]

        # Execute all queries with retry support
        # PooledExecutor handles capacity errors with AIMD backoff
        results = self._executor.execute_batch(
            contexts=contexts,
            process_fn=lambda work, work_state_id: self._process_single_query(
                work["original_row"],
                work["spec"],
                work_state_id,
            ),
        )

        return results

    def _execute_queries_sequential(
        self,
        row: dict[str, Any],
        state_id: str,
    ) -> list[TransformResult]:
        """Execute queries sequentially (fallback when no executor).

        Without PooledExecutor, capacity errors are not retried - they immediately
        fail the query. This is acceptable for the fallback path.

        Args:
            row: The input row data
            state_id: State ID for audit trail

        Returns:
            List of TransformResults in query spec order
        """
        results: list[TransformResult] = []

        for spec in self._query_specs:
            try:
                result = self._process_single_query(row, spec, state_id)
            except CapacityError as e:
                # No retry in sequential mode - fail immediately
                result = TransformResult.error(
                    {
                        "reason": "rate_limited",
                        "error": str(e),
                        "query": spec.output_prefix,
                    }
                )
            results.append(result)

        return results

    def _process_batch(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Process batch of rows with concurrent row processing.

        All (rows x queries) are executed in parallel up to pool_size limit.
        Failed rows get _error marker while successful rows continue.

        With pool_size=100 and 10 queries/row, processes 10 rows simultaneously
        instead of sequentially (full pool utilization).

        Args:
            rows: List of input rows
            ctx: Plugin context with landscape and state_id

        Returns:
            TransformResult.success_multi with all row results, or
            TransformResult.success for empty batch
        """
        if not rows:
            return TransformResult.success({"batch_empty": True, "row_count": 0})

        if ctx.landscape is None or ctx.state_id is None:
            raise RuntimeError("Batch processing requires landscape recorder and state_id.")

        if self._recorder is None:
            self._recorder = ctx.landscape

        # Fast path: No pooled executor, process sequentially
        if self._executor is None:
            try:
                return self._process_batch_sequential(rows, ctx)
            finally:
                # Clean up batch client after all rows processed
                with self._http_clients_lock:
                    self._http_clients.pop(ctx.state_id, None)

        # Concurrent row processing using PooledExecutor
        try:
            output_rows = self._process_batch_concurrent(rows, ctx)
        finally:
            # Clean up batch client after all rows processed
            with self._http_clients_lock:
                self._http_clients.pop(ctx.state_id, None)

        return TransformResult.success_multi(output_rows)

    def _process_batch_sequential(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Sequential batch processing (fallback when no executor).

        Args:
            rows: List of input rows
            ctx: Plugin context

        Returns:
            TransformResult with all rows processed
        """
        if ctx.state_id is None:
            raise ValueError("state_id is required for batch processing")

        output_rows: list[dict[str, Any]] = []

        for row in rows:
            result = self._process_single_row_internal(row, ctx.state_id)

            if result.status == "success" and result.row is not None:
                output_rows.append(result.row)
            else:
                # Row failed - include original with error marker
                error_row = dict(row)
                error_row["_error"] = result.reason
                output_rows.append(error_row)

        return TransformResult.success_multi(output_rows)

    def _process_batch_concurrent(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> list[dict[str, Any]]:
        """Concurrent batch processing via PooledExecutor.

        Flattens (N rows x M queries) into single work list, executes in parallel,
        then groups results back by row and checks atomicity.

        Args:
            rows: List of input rows
            ctx: Plugin context with state_id

        Returns:
            List of output rows (success or error)
        """
        from elspeth.plugins.pooling.executor import RowContext

        if self._executor is None:
            raise RuntimeError("executor not initialized - call on_start() first")
        if ctx.state_id is None:
            raise ValueError("state_id is required for batch processing")

        queries_per_row = len(self._query_specs)

        # Flatten: (N rows x M queries) -> single work list
        # All queries share ctx.state_id (FK constraint to node_states)
        # Uniqueness comes from call_index in AuditedHTTPClient
        contexts = []
        for row_idx, row in enumerate(rows):
            for query_idx, spec in enumerate(self._query_specs):
                work_idx = row_idx * queries_per_row + query_idx
                contexts.append(
                    RowContext(
                        row={
                            "original_row": row,
                            "spec": spec,
                            "row_idx": row_idx,  # Track which row this belongs to
                        },
                        state_id=ctx.state_id,  # Shared state_id (satisfies FK)
                        row_index=work_idx,
                    )
                )

        # Execute all queries for all rows with AIMD retry
        # All queries share one HTTP client (no memory leak)
        all_results = self._executor.execute_batch(
            contexts=contexts,
            process_fn=lambda work, work_state_id: self._process_single_query(
                work["original_row"],
                work["spec"],
                work_state_id,
            ),
        )

        # Group results back by row (M queries per row)
        output_rows: list[dict[str, Any]] = []

        for row_idx, original_row in enumerate(rows):
            start = row_idx * queries_per_row
            end = start + queries_per_row
            row_results = all_results[start:end]

            # Check atomicity: all-or-nothing per row
            failed = [r for r in row_results if r.status != "success"]

            if failed:
                # ANY query failed → row fails
                error_row = dict(original_row)
                error_row["_error"] = {
                    "reason": "query_failed",
                    "failed_queries": [
                        {
                            "query": self._query_specs[i].output_prefix,
                            "error": r.reason,
                        }
                        for i, r in enumerate(row_results)
                        if r.status != "success"
                    ],
                    "succeeded_count": len(row_results) - len(failed),
                    "total_count": len(row_results),
                }
                output_rows.append(error_row)
            else:
                # ALL queries succeeded → merge outputs
                output = dict(original_row)
                for result in row_results:
                    if result.row is not None:
                        output.update(result.row)
                output_rows.append(output)

        return output_rows

    def close(self) -> None:
        """Release resources."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)
        self._recorder = None
        with self._http_clients_lock:
            self._http_clients.clear()
