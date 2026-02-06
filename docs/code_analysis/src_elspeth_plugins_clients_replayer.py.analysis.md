# Analysis: src/elspeth/plugins/clients/replayer.py

**Lines:** 255
**Role:** Call replayer for replay mode. Returns previously recorded external call responses from the audit trail instead of making live calls. Matches calls by canonical request hash with sequence indexing for duplicate requests. Used for deterministic re-execution and testing.
**Key dependencies:** json, collections.defaultdict, elspeth.contracts (CallStatus), elspeth.core.canonical (stable_hash), LandscapeRecorder (TYPE_CHECKING). Imported by: __init__.py (re-exported as CallReplayer, ReplayedCall, ReplayMissError)
**Analysis depth:** FULL

## Summary

The replayer is well-designed with clear error handling for missing calls and missing payloads. The sequence counter mechanism correctly handles duplicate request hashes. The cache implementation is functional but has a thread safety gap noted in the docstring. The trust model is correctly applied -- recorded data from our audit trail is treated as Tier 1 (trusted). The biggest concern is the unbounded cache with no eviction, and the lack of a mechanism to distinguish between "call was an error with a response" and "call was an error without a response." Overall a sound implementation with minor issues.

## Critical Findings

None.

## Warnings

### [107-110, 127-130] Thread safety documented but not enforced
**What:** The class docstring states "If used across threads, external synchronization may be needed for the cache" but provides no synchronization mechanism. Both `_cache` (dict) and `_sequence_counters` (defaultdict) are read and written in `replay()` without any locking.
**Why it matters:** The `PluginContext` holds clients that are used by the engine's processor, which can process rows in a thread pool. If two threads call `replay()` concurrently for the same request:
1. Both read `_sequence_counters[key]` as 0.
2. Both set `_sequence_counters[key]` to 1.
3. Both look up `sequence_index=0` from the database.
4. Both cache the same result.
5. The second distinct response (sequence_index=1) is never retrieved.
This would silently return the wrong response for the second replay of a duplicate request, causing the pipeline to produce incorrect results with the wrong recorded data attributed to a token. The audit trail would not reflect this -- it would show a successful replay but with data from the wrong sequence.
**Evidence:** `replayer.py:173-174`: `sequence_index = self._sequence_counters[sequence_key]` followed by `self._sequence_counters[sequence_key] = sequence_index + 1` -- classic read-modify-write race condition.

### [127-130] Unbounded cache with no eviction
**What:** The `_cache` dict grows without bound. Every replayed call is cached forever (until `clear_cache()` is explicitly called). The cache stores the full response_data dict, latency, error data, and call_id for every unique `(call_type, request_hash, sequence_index)` tuple.
**Why it matters:** In a pipeline with thousands of rows, each making multiple external calls, the cache could accumulate significant memory. If response payloads are large (e.g., LLM responses with full `raw_response` dicts), this could cause memory pressure. There is no size limit, no LRU eviction, and no option to disable caching. However, in replay mode, each unique call is typically looked up once, so the practical impact depends on the ratio of unique calls to duplicate calls.
**Evidence:** `replayer.py:127-130`: `self._cache: dict[tuple[str, str, int], tuple[dict[str, Any], float | None, bool, dict[str, Any] | None, str]] = {}` -- unbounded dict.

### [206-207] `json.loads` on `call.error_json` without validation
**What:** When the recorded call has `error_json`, it is parsed with `json.loads(call.error_json)` at line 207. This data comes from the audit trail (Tier 1), so per the trust model it should be trusted. However, `json.loads` can produce any JSON type (list, str, int, None), while `error_data` is typed as `dict[str, Any] | None`. If the error_json was somehow stored as a JSON array or string, the caller would receive a non-dict type.
**Why it matters:** The `error_data` field of `ReplayedCall` is typed as `dict[str, Any] | None`. A non-dict value would violate the type contract. Per the trust model, Tier 1 data corruption should crash -- but `json.loads` will happily return a list. The caller may then fail in unexpected ways when trying to access dict methods on the result.
**Evidence:** `replayer.py:207`: `error_data = json.loads(call.error_json)` -- no type assertion that result is dict.

## Observations

### [215-216] Correct handling of response_expected vs response_data
**What:** The replayer correctly distinguishes between "call had no response" (error calls where response_hash is None) and "call had a response but it was purged" (response_hash is set but payload store returns None). The `ReplayPayloadMissingError` is only raised when a response was expected but is missing.
**Why it matters:** This is a well-designed pattern that avoids conflating "never had data" with "data was lost." It correctly allows replay of error calls that legitimately had no response body.

### [219-221] Empty dict default for calls that never had a response
**What:** When `response_data is None` after passing the "response expected" check, it defaults to `{}`. This handles error calls where no response was recorded.
**Why it matters:** The empty dict is a reasonable default, but it means the caller cannot distinguish "response was an empty dict" from "no response was recorded." For replay purposes this is unlikely to matter since the caller is primarily interested in whether the original call was an error (checked via `was_error`).

### [240-250] `clear_cache()` correctly resets both cache and sequence counters
**What:** The method clears both `_cache` and reinitializes `_sequence_counters` as a new defaultdict.
**Why it matters:** Good design -- ensures that after clearing, the next replay starts from sequence_index 0 for all requests. If only the cache were cleared but counters retained, subsequent replays would skip to the wrong sequence index.

### [127-130] Cache key/value tuple is complex and unnamed
**What:** The cache stores `tuple[dict[str, Any], float | None, bool, dict[str, Any] | None, str]` as values. This is a 5-element tuple with no named fields.
**Why it matters:** Minor readability concern. A named tuple or small dataclass would make the cache entry self-documenting. Currently, accessing `self._cache[key]` requires remembering the positional meaning of each tuple element.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add a threading.Lock around `_sequence_counters` and `_cache` access in `replay()`, or document that the replayer must be used single-threaded. (2) Add a type assertion after `json.loads(call.error_json)` to crash on non-dict error_json (per Tier 1 trust model). (3) Consider replacing the cache value tuple with a named type for readability.
**Confidence:** HIGH -- Full read of all 255 lines, recorder APIs verified, trust model implications analyzed.
