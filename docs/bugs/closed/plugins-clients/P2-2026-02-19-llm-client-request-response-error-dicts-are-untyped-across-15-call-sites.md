## Summary

The audited LLM client constructs `request_data`, `response_data`, and `error` dicts as `dict[str, Any]` and passes them to `record_call()` for Landscape recording. These dicts have consistent, well-defined shapes but no type enforcement. The same shapes are constructed at 15+ call sites across `llm.py`, `azure_batch.py`, and multi-query transforms.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/plugins/clients/llm.py` — Lines 297, 336, 412
- File: `src/elspeth/plugins/llm/azure_batch.py` — Lines 554, 614, 624, 655, 665, 741, 785, 800, 978, 992

## Evidence

The same dict shapes are constructed repeatedly:

```python
# Request shape (llm.py:297)
request_data: dict[str, Any] = {
    "model": model,
    "messages": messages,
    "temperature": temperature,
    "provider": self._provider,
}

# Response shape (llm.py:412)
response_data = {
    "content": content,
    "model": response.model,
    "usage": usage.to_dict(),
    "raw_response": raw_response,
}

# Error shape (llm.py:336)
error = {
    "type": error_type,
    "message": str(e),
    "retryable": is_retryable,
}
```

These are system-owned structures (Tier 1 once recorded). A typo in a key name would silently produce a malformed audit record.

## Proposed Fix

Create frozen dataclasses in `contracts/call_data.py`:

```python
@dataclass(frozen=True, slots=True)
class LLMCallRequest:
    model: str
    messages: list[dict[str, str]]
    temperature: float
    provider: str
    max_tokens: int | None = None
    extra_kwargs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "provider": self.provider,
        }
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        result.update(self.extra_kwargs)
        return result

@dataclass(frozen=True, slots=True)
class LLMCallResponse:
    content: str
    model: str
    usage: TokenUsage  # Existing frozen dataclass, NOT dict[str, int]
    # Tier 3 provenance — raw SDK response for audit completeness.
    # Not further typed: structure is SDK-version-dependent.
    raw_response: dict[str, Any]

@dataclass(frozen=True, slots=True)
class LLMCallError:
    type: str
    message: str
    retryable: bool
```

Each provides explicit `to_dict()` for Landscape serialization. Never use `dataclasses.asdict()` — it deep-copies nested structures wastefully and doesn't handle conditional key omission.

## Affected Subsystems

- `plugins/clients/llm.py` — primary construction
- `plugins/llm/azure_batch.py` — batch variant construction
- `core/landscape/_call_recording.py` — consumption via `record_call()`

## Related Bugs

Part of a systemic pattern: 10 open bugs (all 2026-02-19) where `dict[str, Any]` crosses into the Landscape audit trail without type enforcement. Categorized as:

- **Category A** (this bug + 3 others): Plugin client call data → Landscape recording
- **Category B** (6 bugs): Engine internal state → Landscape recording

Precedent: `TokenUsage` frozen dataclass (`contracts/token_usage.py`, commit `dffe74a6`).

## Review Board Analysis (2026-02-19)

Four-agent review board assessed the proposed fix. Verdict: **Approve with changes**.

### Critical Design Changes Required

1. **Add `extra_kwargs` field** — `llm.py:297-303` spreads `**kwargs` into `request_data` (e.g., `tools`, `response_format`, `seed`). Dropping these silently loses audit data for tool-calling and structured-output pipelines.
2. **Use `TokenUsage` for `usage`**, not `dict[str, int]` — reuse the existing frozen dataclass; don't regress to an untyped dict for a field that already has a typed representation.
3. **Split error types: `LLMCallError` (not `CallError`)** — LLM errors carry `retryable: bool`, HTTP errors carry `status_code: int | None`. Collapsing both into one type either drops fields or forces misleading optionals. Name `LLMCallError` to match `ExternalCallCompleted` naming convention.
4. **Explicit `to_dict()`, never `dataclasses.asdict()`** — `to_dict()` must conditionally omit `None` fields (e.g., `max_tokens`) to preserve hash stability with existing audit records. `dataclasses.asdict()` deep-copies `raw_response` wastefully and doesn't support conditional omission.

### Hash Stability Risk (Critical)

`record_call()` calls `stable_hash(request_data)` → `canonical_json()` → `rfc8785.dumps()`. RFC 8785 is sensitive to key *presence* — `{"max_tokens": null}` and `{}` produce different hashes. The current code at `llm.py:304-305` omits `max_tokens` when `None`. `to_dict()` must exactly mirror this conditional inclusion, or every historical audit record's hash becomes unreproducible.

### record_call() Interface Design

Define a `CallData` protocol in `contracts/`:

```python
@runtime_checkable
class CallData(Protocol):
    def to_dict(self) -> dict[str, Any]: ...
```

Change `record_call()` to accept `CallData` instead of `dict[str, Any]`. The recorder calls `.to_dict()` internally. Raw `dict` callers are blocked because `dict` doesn't have `to_dict()`. This mirrors the `RuntimeRetryProtocol` pattern in `contracts/config/protocols.py`.

### Required Tests (before any production call site changes)

- **Hash stability regression**: construct same data as old dict AND new `to_dict()`, assert `stable_hash()` match
- **Construction + round-trip**: verify fields stored, `None` fields omitted, `extra_kwargs` expanded
- **Hypothesis property tests**: determinism of `stable_hash(req.to_dict())`
- **Integration**: record call via dataclass path, retrieve, verify `request_hash` matches

### Additional Cleanup

- Remove `copy.deepcopy(request_data)` at `llm.py:346` once `LLMCallRequest` is frozen — immutability makes the defensive copy dead code.
- ~15-20 test assertion sites in `test_audited_llm_client.py` will need updating (currently assert on dict keys).
