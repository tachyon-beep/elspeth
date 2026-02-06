# Analysis: src/elspeth/plugins/llm/azure_batch.py

**Lines:** 1,261
**Role:** Azure OpenAI Batch API transform. Collects rows into batches, submits them as JSONL to Azure's async batch endpoint, checkpoints the batch ID for crash recovery, then polls for completion and distributes per-row results back. Implements a two-phase checkpoint pattern (submit then poll) using `BatchPendingError` as a control-flow signal.
**Key dependencies:** Imports from `elspeth.contracts` (BatchPendingError, CallStatus, CallType, TransformResult, SchemaContract, PipelineRow), `elspeth.plugins.base.BaseTransform`, `elspeth.plugins.context.PluginContext`, `elspeth.plugins.llm.templates.PromptTemplate`, `elspeth.plugins.llm.tracing`, `openai.AzureOpenAI` (lazy). Imported by plugin discovery/manager and `openrouter_batch.py` pattern.
**Analysis depth:** FULL

## Summary

The file is architecturally sound in its two-phase checkpoint design and its disciplined Tier 3 boundary validation of Azure API responses. However, it has several critical and warning-level issues: (1) the API key is exposed through the `azure_config` property and stored in checkpoint data that flows through audit recording, (2) Azure Batch API's `error_file_id` for partial failures is completely ignored meaning per-row error details from content filtering are silently lost, (3) the `hasattr` checkpoint API checks violate the project's prohibition on defensive patterns, and (4) `transforms_adds_fields` is not set despite the transform adding 9+ fields to every row. Confidence is HIGH -- findings are based on direct code evidence and Azure Batch API documentation semantics.

## Critical Findings

### [C1: LINE 1221-1232] API key exposed through `azure_config` property

**What:** The `azure_config` property returns a dict containing the raw `self._api_key` value. Any consumer of this property receives the plaintext secret. Additionally, the checkpoint data at line 675-683 stores `requests_by_id` which includes the full request bodies -- these flow through `ctx.record_call()` into the audit trail.

**Why it matters:** Per CLAUDE.md's secret handling rules, secrets must never be stored directly -- only HMAC fingerprints belong in the audit trail. If `azure_config` is ever serialized, logged, or recorded to the audit trail, the API key is persisted in plaintext. The `requests` dict in checkpoint data at line 682 includes full message bodies sent to Azure (which may contain PII from row data), and this is stored in the checkpoint which may be persisted to disk or database.

**Evidence:**
```python
# Line 1227-1232
@property
def azure_config(self) -> dict[str, Any]:
    return {
        "endpoint": self._endpoint,
        "api_key": self._api_key,  # PLAINTEXT SECRET
        "api_version": self._api_version,
        "provider": "azure_batch",
    }
```

### [C2: LINE 759-903] Missing `error_file_id` handling for partial batch failures

**What:** When a batch status is `"completed"`, the code only downloads `batch.output_file_id` (line 903). Azure Batch API also provides `batch.error_file_id` which contains per-row error details for rows that failed due to content filtering, rate limiting within the batch, or other per-request errors. These errors are distinct from the `"error"` field in the output JSONL -- the error file contains requests that were rejected before processing.

**Why it matters:** In production, Azure content filters regularly reject individual requests within a batch. Without downloading and processing `error_file_id`, those rows silently become "result not found" (line 1035-1045) with reason `"result_not_found"` rather than the actual Azure-provided error. The audit trail records an incorrect error reason, violating the attributability standard: "I don't know what happened" is never acceptable.

**Evidence:**
```python
# Line 903 - only output_file_id is downloaded
output_file_id = batch.output_file_id

# Line 1035-1045 - rows missing from output get generic error
output_row[f"{self._response_field}_error"] = {
    "reason": "result_not_found",  # WRONG - Azure likely filtered this request
    "custom_id": custom_id,
}
```
Azure Batch API docs specify that `error_file_id` contains a JSONL file with rows that could not be processed, with per-row error details. These are NOT included in `output_file_id`.

### [C3: LINE 916-918] Full JSONL output content stored in audit trail call record

**What:** The `response_data` for the file download call includes `output_content.text` -- the entire JSONL batch output. For a batch of 50 rows, each with a multi-paragraph LLM response, this could be megabytes of data stored as a single call record in the audit database.

**Why it matters:** This creates unbounded audit record sizes. The Landscape database was designed for structured metadata, not bulk data storage. For large batches with verbose responses, this will cause: (1) database bloat, (2) slow queries on the calls table, (3) potential SQLite or PostgreSQL row size limits being hit. The payload store exists specifically for this use case.

**Evidence:**
```python
# Line 914-919
ctx.record_call(
    ...
    response_data={
        "file_id": output_file_id,
        "content": output_content.text,  # ENTIRE BATCH OUTPUT
        "content_length": len(output_content.text),
    },
```

## Warnings

### [W1: LINE 475, 492, 508] `hasattr` checks on PluginContext violate defensive programming prohibition

**What:** Three methods (`_get_checkpoint`, `_update_checkpoint`, `_clear_checkpoint`) use `hasattr(ctx, "get_checkpoint")` to check for checkpoint API availability before calling it. Per CLAUDE.md's prohibition on defensive programming patterns: "Do not use .get(), getattr(), hasattr(), isinstance(), or silent exception handling to suppress errors from nonexistent attributes."

**Why it matters:** `PluginContext` is system-owned code -- it defines `get_checkpoint`, `update_checkpoint`, and `clear_checkpoint` directly on the dataclass (lines 145-189 of context.py). If these methods ever disappeared, it would be a framework bug that should crash, not be caught. The `hasattr` checks hide potential integration failures.

**Evidence:**
```python
# Lines 475-479
def _get_checkpoint(self, ctx: PluginContext) -> dict[str, Any] | None:
    if not hasattr(ctx, "get_checkpoint"):  # PROHIBITED
        raise RuntimeError(...)
    return ctx.get_checkpoint()
```
The correct pattern per CLAUDE.md is to call `ctx.get_checkpoint()` directly. If the attribute doesn't exist, that's a bug to fix, not a symptom to suppress.

### [W2: LINE 733] `getattr(batch, "output_file_id", None)` defensive access

**What:** When recording the batch status check call, `output_file_id` is accessed via `getattr(batch, "output_file_id", None)`. The Azure OpenAI SDK `Batch` object always has `output_file_id` as a field (it's `None` when not completed). This is defensive programming against the SDK's own type contract.

**Why it matters:** Per CLAUDE.md, `getattr()` with defaults is prohibited when it hides bugs. The Azure SDK's `Batch` type always has `output_file_id`. If the SDK ever removed this field, it would be a breaking SDK change that should crash visibly, not silently record `None`.

**Evidence:**
```python
# Line 733
"output_file_id": getattr(batch, "output_file_id", None),
```

### [W3: LINE 788] `hasattr(batch, "errors")` defensive access for batch error details

**What:** When handling a failed batch, the code uses `hasattr(batch, "errors")` to defensively check for error details. Similar to W2, this is defensive programming against the Azure SDK's type contract.

**Why it matters:** The Azure SDK `Batch` object defines `errors` as a field. If the SDK changed, we should crash rather than silently skip error recording. Skipping error details on a failed batch means the audit trail may not record WHY the batch failed.

**Evidence:**
```python
# Line 788
if hasattr(batch, "errors") and batch.errors:
    error_info["errors"] = [...]
```

### [W4: NO LINE] `transforms_adds_fields` not set to `True`

**What:** This transform adds 9+ fields to every output row (response content, usage, model, template_hash, variables_hash, template_source, lookup_hash, lookup_source, system_prompt_source, and potentially error fields). However, it does not set `transforms_adds_fields = True` on the class. The base class defaults to `False`.

**Why it matters:** The `transforms_adds_fields` flag (P1-2026-02-05) controls whether the engine records an evolved contract to the audit trail. Without this flag, the audit trail contract will not reflect the LLM-added fields, potentially causing downstream contract validation failures or incomplete lineage information. Other LLM transforms in the codebase also don't set this, suggesting a systemic gap.

**Evidence:** The class only sets:
```python
name = "azure_batch_llm"
is_batch_aware = True
determinism: Determinism = Determinism.NON_DETERMINISTIC
```
Missing: `transforms_adds_fields: bool = True`

### [W5: LINE 1198-1212] Dead code: unreachable `else` branch in contract construction

**What:** Line 1184 checks `if not output_rows:` and returns an error. Then line 1198 checks `if output_rows:` which is always true at that point (we already returned if empty). The `else` branch at line 1211 setting `output_contract = None` is unreachable.

**Why it matters:** Dead code obscures intent and is a maintenance hazard. A future developer might think the `else` branch is reachable and make changes that depend on `output_contract` being `None`.

**Evidence:**
```python
# Line 1184-1191
if not output_rows:
    return TransformResult.error(...)  # RETURNS HERE

# Line 1198 - always True at this point
if output_rows:
    ...
else:
    output_contract = None  # UNREACHABLE
```

### [W6: LINE 1196-1210] Output contract uses `object` for all field types

**What:** The inferred output contract sets `python_type=object` for all fields. This effectively disables type checking for the entire output schema.

**Why it matters:** Downstream transforms relying on contract type information will see `object` for every field, defeating the purpose of schema contracts. The comment "Use object for dynamic typing" suggests this is intentional, but it undermines the contract system's value for batch transform outputs.

**Evidence:**
```python
# Line 1200-1208
fields = tuple(
    FieldContract(
        normalized_name=key,
        original_name=key,
        python_type=object,  # No type information preserved
        required=False,
        source="inferred",
    )
    for key in first_row
)
```

### [W7: LINE 597] Full JSONL request content stored in audit call record

**What:** Similar to C3, the file upload audit record at line 597 includes the full JSONL content (`"content": jsonl_content`). For a batch of 50 rows with verbose prompts, this could be hundreds of kilobytes in a single call record.

**Why it matters:** Same as C3 -- unbounded audit record sizes. The JSONL content includes rendered prompts which may contain sensitive data from input rows, and this is all stored in the calls table.

**Evidence:**
```python
# Line 593-599
upload_request = {
    "operation": "files.create",
    ...
    "content": jsonl_content,  # ENTIRE BATCH INPUT
    "content_size": len(jsonl_content),
}
```

### [W8: LINE 851] `submitted_at` accessed without `.get()` inconsistently

**What:** In the "still processing" branch (line 851), `submitted_at_str` is accessed as `checkpoint["submitted_at"]` (direct access, will crash if missing). In other branches (lines 761, 794, 816), it uses `checkpoint.get("submitted_at")`. The inconsistency means the timeout branch would crash on a corrupt checkpoint while the completed/failed/cancelled branches would silently use `latency_ms=0.0`.

**Why it matters:** Per the Three-Tier Trust Model, checkpoint data is Tier 1 (our data). The direct access at line 851 is actually the CORRECT pattern (crash on corruption). The `.get()` at lines 761, 794, 816 is the incorrect pattern -- if our checkpoint is missing `submitted_at`, something is catastrophically wrong and we should crash, not silently record 0.0ms latency.

**Evidence:**
```python
# Line 851 - CORRECT (crash on missing)
submitted_at_str = checkpoint["submitted_at"]

# Line 761 - WRONG (silent default)
submitted_at_str = checkpoint.get("submitted_at")
```

## Observations

### [O1: LINE 376] `isinstance` check on `row` parameter for batch/single dispatch

The `process()` method uses `isinstance(row, list)` to distinguish batch from single-row invocation. This is a legitimate pattern since the method signature uses a union type (`PipelineRow | list[PipelineRow]`), but the type annotation could be tightened. The `@overload` decorator would make the contract clearer.

### [O2: LINE 900] Template errors deserialized from checkpoint may lose tuple types

`template_errors` is stored in checkpoint as `list[tuple[int, str]]`, but JSON serialization converts tuples to lists. If the checkpoint is ever serialized to JSON and deserialized, `template_errors` will become `list[list[int, str]]`. The code at line 1012 (`{idx for idx, _ in template_errors}`) would still work due to iterable unpacking, but the type annotation would be incorrect.

### [O3: LINE 402] `result.status == "success"` uses string literal comparison

The status check uses string comparison rather than pattern matching or an enum. This is consistent with `TransformResult`'s `Literal["success", "error"]` type, but string comparisons are fragile. A typo like `"sucess"` would silently evaluate to False.

### [O4: NO LINE] No use of shared `validate_json_object_response` from validation.py

The `azure_multi_query.py` sibling uses the shared validation utility `validate_json_object_response` from `validation.py`, but `azure_batch.py` implements its own inline Tier 3 boundary validation (lines 946-994). This is not necessarily a bug -- the batch response format differs from real-time (JSONL vs single JSON object). However, the per-row response body validation (lines 1082-1119) is validating the same Azure `choices[0].message.content` structure that the shared validator could partially handle.

### [O5: LINE 586] JSONL construction doesn't include trailing newline

The JSONL spec requires each line to be a valid JSON value, separated by newlines. Line 586 uses `"\n".join(...)` which means there's no trailing newline. Most JSONL parsers accept this, but some strict implementations require a trailing newline. Azure's batch API accepts both formats, so this is cosmetic.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Three items require immediate attention before production use:
1. (C2) Implement `error_file_id` download and processing for partial batch failures -- this is the most impactful issue as it causes silent data loss.
2. (C1) Remove or secure the `azure_config` property that exposes the API key, and audit checkpoint data for secret leakage.
3. (C3/W7) Route bulk JSONL content through the payload store rather than inline in call records.

Secondary items: remove `hasattr` checks (W1), set `transforms_adds_fields = True` (W4), fix inconsistent checkpoint access patterns (W8), remove dead code (W5).

**Confidence:** HIGH -- Findings are based on direct code analysis cross-referenced with Azure Batch API semantics and ELSPETH's documented trust model. The `error_file_id` gap is particularly well-documented in Azure's API reference.
