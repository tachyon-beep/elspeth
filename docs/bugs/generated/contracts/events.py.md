## Summary

`ExternalCallCompleted.to_dict()` deep-serializes `request_payload`, `response_payload`, and `token_usage`, then immediately serializes those same fields a second time via each DTO's own `to_dict()`, causing avoidable O(payload-size) CPU and peak-memory amplification on every external-call telemetry export.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: [src/elspeth/contracts/events.py](/home/john/elspeth/src/elspeth/contracts/events.py)
- Line(s): 410-428
- Function/Method: `ExternalCallCompleted.to_dict`

## Evidence

In [src/elspeth/contracts/events.py](/home/john/elspeth/src/elspeth/contracts/events.py#L410), `ExternalCallCompleted.to_dict()` first serializes the entire dataclass recursively:

```python
d: dict[str, Any] = _event_field_to_serializable(self)
if self.request_payload is not None:
    d["request_payload"] = self.request_payload.to_dict()
if self.response_payload is not None:
    d["response_payload"] = self.response_payload.to_dict()
if self.token_usage is not None:
    d["token_usage"] = self.token_usage.to_dict()
```

That first line already walks into the payload DTOs because `_event_field_to_serializable()` recurses into any dataclass and deep-copies leaf values ([src/elspeth/contracts/events.py](/home/john/elspeth/src/elspeth/contracts/events.py#L190-L204)). The three overridden assignments then serialize the same objects again.

This is not theoretical overhead: LLM telemetry explicitly captures the full raw provider response for audit completeness:

```python
# raw_response includes: all choices, finish_reason, tool_calls, logprobs, etc.
raw_response = response.model_dump()
response_dto = LLMCallResponse(..., raw_response=raw_response)
```

Evidence: [src/elspeth/plugins/infrastructure/clients/llm.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L506-L538).

HTTP telemetry also packages full response bodies into DTOs before export:

```python
response_dto = HTTPCallResponse(
    status_code=response.status_code,
    headers=...,
    body_size=len(response.content),
    body=response_body,
)
```

Evidence: [src/elspeth/plugins/infrastructure/clients/http.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L345-L351).

And exporters call `event.to_dict()` on every export path, so this redundant work happens once per exporter per event:

- Console: [src/elspeth/telemetry/exporters/console.py](/home/john/elspeth/src/elspeth/telemetry/exporters/console.py#L163)
- OTLP: [src/elspeth/telemetry/exporters/otlp.py](/home/john/elspeth/src/elspeth/telemetry/exporters/otlp.py#L81-L99)
- Datadog: [src/elspeth/telemetry/exporters/datadog.py](/home/john/elspeth/src/elspeth/telemetry/exporters/datadog.py#L312-L318)

What the code does:
- Recursively copies potentially large payload DTO contents once.
- Replaces those fields with DTO-aware serialization, doing the expensive work again.

What it should do:
- Build the event dict without pre-serializing the payload fields that will be handled specially.

## Root Cause Hypothesis

The override fixed the correctness issue that generic dataclass decomposition produced the wrong payload shape, but it reused the base recursive serializer for convenience instead of excluding the DTO-backed fields from that first pass. That preserves correctness but leaves a hidden double-walk/double-copy path for the heaviest telemetry events.

## Suggested Fix

Construct the dict manually for `ExternalCallCompleted` instead of starting from `_event_field_to_serializable(self)`, or teach the helper to skip known special fields.

Example shape:

```python
def to_dict(self) -> dict[str, Any]:
    return {
        "timestamp": copy.deepcopy(self.timestamp),
        "run_id": self.run_id,
        "call_type": self.call_type,
        "provider": self.provider,
        "status": self.status,
        "latency_ms": self.latency_ms,
        "state_id": self.state_id,
        "operation_id": self.operation_id,
        "token_id": self.token_id,
        "request_hash": self.request_hash,
        "response_hash": self.response_hash,
        "request_payload": None if self.request_payload is None else self.request_payload.to_dict(),
        "response_payload": None if self.response_payload is None else self.response_payload.to_dict(),
        "token_usage": None if self.token_usage is None else self.token_usage.to_dict(),
    }
```

A regression test should assert that `ExternalCallCompleted.to_dict()` does not invoke generic serialization on payload DTOs before the DTO override path.

## Impact

When telemetry is enabled at `full` granularity, every external LLM/HTTP call pays an unnecessary extra deep-copy/serialization cost proportional to payload size. For large `raw_response` or HTTP bodies, that inflates exporter latency and peak memory, increases queue pressure in `TelemetryManager`, and makes telemetry backpressure/drop behavior more likely even though the event content itself is valid.
