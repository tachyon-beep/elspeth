# Transforms — Pipeline Data vs Audit Provenance

## The Decision Test

> Would a pipeline operator or downstream transform ever make a decision based on this value?

- **Yes** → Output row field (via `declared_output_fields`)
- **No** → Audit trail (via `success_reason["metadata"]`)

## Examples

| Field | Location | Why |
|-------|----------|-----|
| `fetch_status = 403` | Row | A gate might route forbidden pages to review |
| `llm_response_model = "gpt-4"` | Row | Multi-model routing, cost filtering |
| `llm_response_usage` | Row | Budget tracking, cost routing |
| `template_hash = abc123` | Audit | Forensic reconstruction only |
| `variables_hash` | Audit | Forensic reconstruction only |
| `fetch_request_hash` | Audit | Blob reference for forensic recovery |

## Where Audit Provenance Goes

```python
return TransformResult.success(
    PipelineRow(output, contract),
    success_reason={
        "action": "enriched",
        "metadata": {
            "template_hash": rendered.template_hash,
            "variables_hash": rendered.variables_hash,
            # ... other provenance fields
        },
    },
)
```

Persisted in `node_states.success_reason_json`. Retrievable via `elspeth explain`.

## Blob Storage

Transforms that produce processed content (not from an external call) store blobs
via `recorder.store_payload(content, purpose="descriptive_label")`.

Request/response blobs from external calls are already stored by `AuditedHTTPClient`
via `recorder.record_call()`. Access hashes from the returned `Call` object:
`call.request_ref`, `call.response_ref`.

**Scope constraint:** If `recorder.store_payload()` appears in more than 2-3
transforms, the Shifting the Burden archetype is reforming and the design needs
revisiting.

## Constants

Each transform with audit-only fields defines a constant tuple:
- `LLM_AUDIT_SUFFIXES` in `plugins/transforms/llm/__init__.py`
- `WEBSCRAPE_AUDIT_FIELDS` in `plugins/transforms/web_scrape.py`
