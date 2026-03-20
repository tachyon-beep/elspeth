# Audit Provenance Boundary Enforcement — Design Spec

**Status:** Draft
**Bug:** `elspeth-7527dacf08`
**Date:** 2026-03-21

## Problem

External-call transforms (LLM, WebScrape) put audit provenance metadata directly into pipeline rows. This data exists solely for forensic reconstruction and has no downstream operational use. It belongs in the audit trail (Landscape `node_states.success_reason`), not in pipeline data that flows to sinks.

### Violations

1. **Redundancy** — provenance data exists in both the row and the audit trail.
2. **Divergent hashes** — WebScrape computes blob hashes differently from AuditedHTTPClient (`f"GET {url}".encode()` vs `canonical_json(HTTPCallRequest.to_dict()).encode()`). The row hash and the audit hash for the same request don't match. An auditor correlating `fetch_request_hash` in the row with `request_hash` in the calls table will find they diverge.
3. **Dual PayloadStore wiring** — WebScrape accesses PayloadStore directly from PluginContext to store blobs for row hashes, creating a second wiring path alongside the recorder path. The PluginContext path was broken until recently (orchestrator forgot to pass `payload_store`).
4. **Row bloat** — LLM transforms add 6 audit fields per row (multiplied by query count in multi-query mode). WebScrape adds 3.

### Root Cause

No enforced boundary between pipeline data (operational values that downstream transforms and sinks consume) and audit provenance (forensic metadata for `elspeth explain` reconstruction). Transforms defaulted to putting everything in the row because it was the easiest path.

## Principle

**Pipeline rows carry operational data. Audit provenance lives in the Landscape.**

The test for whether a field belongs in the row:

> Would a pipeline operator or downstream transform ever make a decision based on this value?

- `fetch_status = 403` → a gate might route forbidden pages to review → **row**
- `template_hash = abc123` → forensic reconstruction only → **audit trail**
- `rag_score = 0.85` → a gate might filter low-relevance rows → **row**
- `lookup_source = /path/to/config.yaml` → config provenance → **audit trail**

Provenance data goes into `success_reason["metadata"]` on `TransformResult.success()`, which the Landscape persists in `node_states`. Retrievable via `elspeth explain`.

## Field Inventory

### LLM Transforms — 6 Fields Move to Audit Trail

The code already labels these correctly as `LLM_AUDIT_SUFFIXES` in `plugins/transforms/llm/__init__.py`.

**Remove from pipeline rows:**

| Field | Content | Why audit-only |
|-------|---------|----------------|
| `{prefix}_template_hash` | SHA-256 of prompt template | Forensic — which template produced this output |
| `{prefix}_variables_hash` | SHA-256 of rendered variables | Forensic — what data was sent to the LLM |
| `{prefix}_template_source` | Config file path of template | Forensic — config provenance |
| `{prefix}_lookup_hash` | SHA-256 of lookup data | Forensic — reference data fingerprint |
| `{prefix}_lookup_source` | Config file path of lookup data | Forensic — config provenance |
| `{prefix}_system_prompt_source` | Config file path of system prompt | Forensic — config provenance |

**Keep in pipeline rows (operational):**

| Field | Content | Why operational |
|-------|---------|----------------|
| `{prefix}_usage` | Token usage dict | Downstream budgeting, cost routing |
| `{prefix}_model` | Model identifier | Multi-model routing, filtering |

**Migration:** Replace `populate_llm_metadata_fields()` (writes audit fields to row) with logic that writes audit fields to a dict returned to the caller for inclusion in `success_reason["metadata"]`. The function currently receives `output: dict` and mutates it — change it to return the audit metadata separately.

### WebScrape Transform — 3 Fields Move, 3 Stay

**Remove from pipeline rows:**

| Field | Content | Why audit-only |
|-------|---------|----------------|
| `fetch_request_hash` | Blob hash of HTTP request | Forensic — what was requested |
| `fetch_response_raw_hash` | Blob hash of raw response bytes | Forensic — what came back |
| `fetch_response_processed_hash` | Blob hash of post-extraction content | Forensic — what the transform produced |

**Keep in pipeline rows (operational):**

| Field | Content | Why operational |
|-------|---------|----------------|
| `fetch_status` | HTTP status code | Gate routing (403 → review, 200 → proceed) |
| `fetch_url_final` | Final URL after redirects | Deduplication, operator visibility |
| `fetch_url_final_ip` | Resolved IP address | SSRF forensics, operational visibility |

**Migration:** WebScrape stops calling `payload_store.store()` directly. The request/response blob hashes come from the `Call` object that `recorder.record_call()` already returns (currently discarded by `AuditedHTTPClient`). The processed-content blob is stored via `recorder.store_payload()` (new method). All three hashes go into `success_reason["metadata"]`.

### RAG Transform — No Changes

All 4 fields (`rag_context`, `rag_score`, `rag_count`, `rag_sources`) are operational data consumed by downstream LLM transforms. No audit provenance in rows.

## PayloadStore Architecture Fix

### Remove `payload_store` from PluginContext

With hash fields out of rows, no transform needs direct PayloadStore access. Remove:

- `payload_store: PayloadStore | None` from `PluginContext` dataclass (`contracts/plugin_context.py:84`)
- `payload_store` property from `LifecycleContext` protocol (`contracts/contexts.py:199`)
- `payload_store=payload_store` from orchestrator's `PluginContext` construction (`engine/orchestrator/core.py:1489`)

### Surface `Call` return from AuditedHTTPClient

`AuditedHTTPClient._record_and_emit()` currently returns `None` and discards the `Call` object from `recorder.record_call()`. Change it to return the `Call` object.

`get_ssrf_safe()` currently returns `tuple[httpx.Response, str]`. Change to return `tuple[httpx.Response, str, Call]` on the success path. The `Call` contains `request_ref` and `response_ref` (payload store hashes).

**Error path:** `get_ssrf_safe()` also calls `record_call()` in the error branch before re-raising. The `Call` is only available on the success path. This is correct — WebScrape only needs hashes when the fetch succeeds.

**Replay/verifier compatibility:** Check whether `replayer.py` and `verifier.py` implement `get_ssrf_safe()`. If they do, they must also return a `Call` (or a compatible object with `request_ref`/`response_ref`). If they don't implement it, no changes needed.

### Add `recorder.store_payload()`

New method on `LandscapeRecorder`:

```python
def store_payload(self, content: bytes, *, purpose: str) -> str:
    """Store a transform-produced artifact in the payload store.

    For blobs that have no corresponding external call record — e.g.,
    post-extraction processed content. The purpose label documents why
    this blob exists in the store.

    Args:
        content: Raw bytes to store.
        purpose: Semantic label (e.g., "processed_content", "extracted_markdown").

    Returns:
        SHA-256 hex digest of stored content.
    """
```

This is a thin wrapper around `PayloadStore.store()` with a mandatory `purpose` parameter. The purpose is NOT persisted in a separate table — it exists to force callers to name what they're storing, preventing the method from becoming a general-purpose escape hatch.

**Scope constraint:** If `store_payload()` appears in more than 2-3 transforms, the Shifting the Burden archetype is reforming and the design needs revisiting. This is documented in code comments.

## Enforcement

### 1. AGENTS.md Boundary Documentation

Create `src/elspeth/plugins/transforms/AGENTS.md` documenting the pipeline-data vs audit-provenance boundary:

- The decision test ("would a pipeline operator make a decision based on this?")
- Examples of each category
- Where audit provenance goes (`success_reason["metadata"]`)
- Where operational data goes (output row via `declared_output_fields`)

### 2. CI Naming Convention Check

Extend the existing tier model enforcer (or add a lightweight check): fields matching `*_hash`, `*_source`, `*_ref` patterns in `declared_output_fields` trigger a warning. Not a hard block — there could be legitimate operational hashes (e.g., `content_fingerprint`) — but a flag that forces justification via allowlist entry.

### 3. Self-Documenting Audit Suffix Constants

Keep `LLM_AUDIT_SUFFIXES` as the pattern. WebScrape should define its own `WEBSCRAPE_AUDIT_FIELDS` constant. These tuples are the single source of truth for "which fields are audit-only" per transform, making the boundary visible in the code.

## Testing Strategy

### Unit Tests

For each transform with moved fields:
- Assert audit fields are **absent** from `result.row.to_dict()`
- Assert audit fields are **present** in `result.success_reason["metadata"]`
- Assert operational fields remain in the output row

### Integration Test

End-to-end pipeline with ChaosLLM and WebScrape (via ChaosWeb):
- Verify output CSV contains only operational fields
- Query Landscape `node_states` to confirm provenance metadata is persisted
- Verify `elspeth explain` retrieves the provenance for a given row

### Regression Pin Updates

Update existing tests that assert on `fetch_request_hash` or `template_hash` in output rows. These should now assert absence from rows and presence in success_reason.

### Example Pipeline Updates

- `chaosweb/settings.yaml` — remove hash fields from sink schemas
- `chaosllm_sentiment/` — verify output doesn't change (audit fields weren't in fixed schemas)
- Verify all example pipelines still pass

## Affected Files

### Source Changes

| File | Change |
|------|--------|
| `plugins/transforms/llm/__init__.py` | Move audit fields from `populate_llm_metadata_fields()` to success_reason return |
| `plugins/transforms/llm/transform.py` | Include audit metadata in `success_reason["metadata"]` |
| `plugins/transforms/llm/openrouter_batch.py` | Same pattern |
| `plugins/transforms/llm/azure_batch.py` | Same pattern |
| `plugins/transforms/web_scrape.py` | Remove direct `payload_store` access, use `Call` return + `recorder.store_payload()` |
| `plugins/infrastructure/clients/http.py` | `_record_and_emit()` returns `Call`; `get_ssrf_safe()` returns `Call` on success |
| `core/landscape/recorder.py` | Add `store_payload(content, *, purpose)` method |
| `contracts/plugin_context.py` | Remove `payload_store` field |
| `contracts/contexts.py` | Remove `payload_store` property from `LifecycleContext` protocol |
| `engine/orchestrator/core.py` | Remove `payload_store=` from `PluginContext` construction |

### Test Changes

| File | Change |
|------|--------|
| `tests/unit/plugins/transforms/test_web_scrape.py` | Assert hashes in success_reason, not row |
| `tests/unit/plugins/transforms/test_web_scrape_security.py` | Same |
| `tests/unit/plugins/llm/test_transform.py` | Assert audit suffixes in success_reason, not row |
| `tests/unit/plugins/llm/test_azure_multi_query.py` | Same |
| `tests/unit/plugins/llm/test_openrouter_batch.py` | Same |

### Documentation

| File | Change |
|------|--------|
| `src/elspeth/plugins/transforms/AGENTS.md` | New — boundary rule documentation |
| `examples/chaosweb/settings.yaml` | Remove hash fields from sink schemas |

## Implementation Notes

### Multi-Query LLM Complexity

Multi-query LLM transforms produce audit fields per query (e.g., `category_template_hash`, `sentiment_template_hash`). The `LLM_AUDIT_SUFFIXES` tuple defines which suffixes are audit-only. The migration must handle the prefix-per-query pattern — iterate over query specs and move all `{query_prefix}{audit_suffix}` fields.

### `declared_output_fields` Shrinkage

Removing audit fields from rows means `declared_output_fields` shrinks. This affects:
- `_output_schema_config` (guaranteed_fields will be smaller)
- Output schema construction (fewer fields declared)
- DAG edge validation (downstream required_input_fields must not reference removed fields)

Verify no downstream transform or sink has `required_input_fields` referencing the removed audit fields. If any do, that's a configuration bug (depending on audit data as pipeline input) and should be fixed in the pipeline config, not preserved.

### Backward Compatibility

None. CLAUDE.md: "WE HAVE NO USERS YET. Deferring breaking changes until we do is the opposite of what we want." Delete the fields from rows completely. No deprecation warnings, no compatibility shims.
