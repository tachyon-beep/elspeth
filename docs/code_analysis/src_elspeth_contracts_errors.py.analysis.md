# Analysis: src/elspeth/contracts/errors.py

**Lines:** 803
**Role:** Error and reason schema contracts for the entire ELSPETH system. Defines TypedDict schemas for structured error/success payloads in the audit trail, exception classes for control flow and invariant violations, and schema contract violation types for external data handling. This is the error contract that all modules import from.
**Key dependencies:**
- Imports: `typing` (Any, Literal, NotRequired, TypedDict) -- no internal ELSPETH imports
- Imported by: `contracts/__init__.py`, `engine/processor.py`, `engine/executors.py`, `engine/coalesce_executor.py`, `engine/orchestrator/core.py`, `core/landscape/recorder.py`, `plugins/llm/azure_multi_query.py`, `plugins/llm/openrouter_multi_query.py`, `contracts/results.py`, `contracts/routing.py`, `contracts/schema_contract.py`, `contracts/contract_records.py`, plus extensive test coverage
**Analysis depth:** FULL

## Summary

This file is well-structured and follows the project's architectural principles rigorously. The TypedDict hierarchy provides compile-time structure for audit trail payloads while remaining JSON-serializable. The exception hierarchy correctly separates control flow (BatchPendingError), internal bugs (FrameworkBugError, OrchestrationInvariantError), plugin bugs (PluginContractViolation), and external data errors (ContractViolation hierarchy). I found one warning-level issue (backwards compatibility comment violating project policy), one design observation about the TransformErrorReason type growing very wide, and some minor items. Overall the file is sound.

## Warnings

### [34] CoalesceFailureReason contains backwards-compatibility alias field

**What:** The `branches_arrived` field is documented as "Alias for actual_branches (backwards compat)" -- this directly contradicts the project's No Legacy Code Policy stated in CLAUDE.md.

**Why it matters:** CLAUDE.md states: "Legacy code, backwards compatibility, and compatibility shims are strictly forbidden." Having two fields that represent the same data (`actual_branches` and `branches_arrived`) creates ambiguity for consumers and violates the stated policy. If both are populated, which is authoritative? If a consumer reads `branches_arrived` but not `actual_branches`, they may get stale data or vice versa.

**Evidence:**
```python
class CoalesceFailureReason(TypedDict, total=False):
    expected_branches: list[str]  # Branches expected to arrive
    actual_branches: list[str]  # Branches that actually arrived
    branches_arrived: list[str]  # Alias for actual_branches (backwards compat)
```

**Recommendation:** Remove `branches_arrived` entirely and update all call sites to use `actual_branches`. Search for consumers to ensure no code relies on the alias.

### [270-408] TransformErrorReason is a very wide TypedDict with ~40 optional fields

**What:** `TransformErrorReason` has one required field (`reason`) and approximately 37 optional `NotRequired` fields covering API errors, LLM responses, type validation, rate limiting, content filtering, and batch processing. This is a single flat type trying to serve every error scenario.

**Why it matters:** While TypedDict is intentionally used here for JSON serialization to the audit trail, the breadth means:
1. **No compile-time enforcement of field combinations.** A `reason: "missing_field"` error can include `batch_id`, `max_tokens`, `categories`, etc., all of which are semantically nonsensical for that error type. Type checkers will not flag this.
2. **Maintenance risk.** Every new LLM provider or error type adds more optional fields to this single type. At 40+ fields, it becomes difficult to know which fields are relevant for a given reason.
3. **Audit query complexity.** Consumers querying the audit trail must know which fields are populated for each reason category -- this is currently only documented in docstring prose.

**Evidence:** The type supports `usage: NotRequired[UsageStats | dict[str, int]]` -- the union with `dict[str, int]` weakens the typing benefit. Similarly `categories: NotRequired[list[str] | dict[str, dict[str, Any]]]` has two unrelated shapes in the same field. `errors: NotRequired[list[str | ErrorDetail]]` mixes strings and structured types.

**Recommendation:** This is an architectural observation, not a bug. For RC2 the current approach is pragmatic. Post-release, consider discriminated union subtypes keyed by `reason` category (e.g., `LLMErrorReason`, `FieldErrorReason`, `BatchErrorReason`) that share a common base.

### [377] `usage` field type allows unstructured dict alongside UsageStats

**What:** The `usage` field is typed as `NotRequired[UsageStats | dict[str, int]]`. The `dict[str, int]` branch allows arbitrary key-value pairs that bypass the `UsageStats` structure.

**Why it matters:** If a caller passes `{"arbitrary_key": 999}` as usage, it will type-check but produce audit records that don't conform to the expected schema. Consumers reading `usage` data will need to handle both shapes, undermining the value of having `UsageStats` defined.

**Evidence:**
```python
usage: NotRequired[UsageStats | dict[str, int]]
```

**Recommendation:** If there are callers that cannot produce `UsageStats`-shaped data, identify them and fix upstream. If all callers already produce conformant data, tighten the type to just `UsageStats`.

### [398-399] `categories` and `attacks` fields have very loose typing

**What:** `categories: NotRequired[list[str] | dict[str, dict[str, Any]]]` -- this field serves two unrelated shapes. `attacks: NotRequired[dict[str, bool]]` is loosely documented.

**Why it matters:** The `categories` field is used for both "list of content safety category names" and "Azure Content Safety detailed severity/threshold map." These are fundamentally different structures that happen to share a field name. This makes it difficult for audit trail consumers to parse and query.

**Evidence:**
```python
categories: NotRequired[list[str] | dict[str, dict[str, Any]]]  # List of names OR detailed severity/threshold map
attacks: NotRequired[dict[str, bool]]  # Prompt shield attack flags (user_prompt_attack, document_attack)
```

**Recommendation:** If the two shapes always correlate with different `reason` values, this is acceptable for now but would benefit from documentation mapping `reason` values to their expected field shapes.

## Observations

### [22] CoalesceFailureReason uses `total=False` making all fields optional

**What:** The `CoalesceFailureReason` TypedDict is defined with `total=False`, meaning every field including `failure_reason` is optional. This means an empty dict `{}` is a valid `CoalesceFailureReason` at the type level.

**Why it matters:** Unlike `TransformErrorReason` which has a required `reason` field, `CoalesceFailureReason` has no required fields. This means a coalesce failure could be recorded with no information at all and still pass type checking. The audit trail for fork/join failures is particularly important for debugging complex DAG flows.

**Evidence:**
```python
class CoalesceFailureReason(TypedDict, total=False):
    failure_reason: str  # Why coalesce failed (e.g., "late_arrival_after_merge")
```

**Recommendation:** Consider whether `failure_reason` should be required (remove `total=False` and mark other fields with `NotRequired`), similar to how `TransformErrorReason` has a required `reason` field.

### [79-82] RoutingReason discriminated union relies on field presence, not a discriminator field

**What:** `RoutingReason = ConfigGateReason | PluginGateReason` uses structural discrimination -- consumers must check for the presence of `"condition"` vs `"rule"` to determine the variant.

**Why it matters:** This is a valid Python pattern but fragile. If a future gate type has both `"condition"` and `"rule"` fields, or neither, the discrimination breaks. The comment acknowledges this ("field presence distinguishes variants") but there is no enforcement.

**Recommendation:** Low priority. The current two-variant union is manageable. If a third gate type is added, consider adding an explicit `"type"` discriminator field.

### [456-479] BatchPendingError carries mutable state as exception attributes

**What:** `BatchPendingError` stores `checkpoint: dict[str, Any] | None` as an attribute. This dict is mutable and shared between the raiser and catcher.

**Why it matters:** If the catcher modifies `checkpoint` (e.g., adding keys before persisting), and the exception is caught at multiple levels (executor catches, then re-raises, orchestrator catches), the intermediate modifications would be visible to all handlers. This is not a bug in the current code path (the exception is caught and handled at specific levels), but it is a latent risk if control flow changes.

**Recommendation:** Low priority. The current usage appears safe. If defense-in-depth is desired, the checkpoint could be deep-copied at construction time, but this would add overhead for no current benefit.

### [540-555] PluginContractViolation inherits from RuntimeError instead of Exception

**What:** `PluginContractViolation` inherits from `RuntimeError` while all other custom exceptions inherit from `Exception`.

**Why it matters:** This is a minor inconsistency. `RuntimeError` is a subclass of `Exception` so all `except Exception` handlers will still catch it. However, any code using `except RuntimeError` to catch "generic runtime errors" would also catch plugin contract violations, which may not be the intent. The choice is documented as intentional (no comment explaining why), but the inconsistency is worth noting.

**Recommendation:** Not actionable unless there is a specific reason `RuntimeError` was chosen over `Exception`. The distinction has no practical impact on current code.

### [598-610] ContractViolation.to_error_reason returns untyped dict

**What:** The `to_error_reason()` method returns `dict[str, Any]`, not `TransformErrorReason`. This means the result doesn't carry type information linking it back to the TypedDict schema.

**Why it matters:** Callers who use `to_error_reason()` to build error payloads lose type checking. The returned dict will have `"reason": "contract_violation"` which is a valid `TransformErrorCategory`, but the additional fields (`violation_type`, `field`, `original_field`) are not declared in `TransformErrorReason`.

**Recommendation:** The `TransformErrorReason` TypedDict doesn't include violation-specific fields like `violation_type` and `original_field`. Either expand `TransformErrorReason` to include these or accept the type gap. This is a minor typing gap, not a runtime issue, since the dict is serialized to JSON for the audit trail.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Remove the backwards-compatibility `branches_arrived` field from `CoalesceFailureReason` per the No Legacy Code Policy. The other findings are design observations that do not require immediate action for RC2 but should be tracked for post-release cleanup. The `usage` field union type (Warning [377]) should be tightened if all current callers already produce `UsageStats`-shaped data.
**Confidence:** HIGH -- The file has zero internal dependencies (pure typing module), clear structure, extensive test coverage (evidenced by the large number of test imports), and well-documented type schemas. The warnings are genuine but non-critical for RC2 stability.
