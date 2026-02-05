# Analysis: src/elspeth/plugins/llm/templates.py

**Lines:** 246
**Role:** Jinja2-based prompt templating with audit trail support. Provides `PromptTemplate` class that renders Jinja2 templates in a sandboxed environment, produces cryptographic hashes of the template, variables, rendered output, lookup data, and schema contract for audit traceability. Also provides `RenderedPrompt` dataclass for carrying rendered prompts with metadata, and `TemplateError` for error wrapping.
**Key dependencies:** Imports from `jinja2` (SandboxedEnvironment, StrictUndefined, TemplateSyntaxError, UndefinedError, SecurityError), `elspeth.core.canonical` (canonical_json), `elspeth.contracts.schema_contract` (PipelineRow, SchemaContract). Imported by all LLM transforms: `base.py`, `azure.py`, `azure_multi_query.py`, `openrouter_batch.py`, `openrouter.py`, `openrouter_multi_query.py`.
**Analysis depth:** FULL

## Summary
This is a clean, well-designed module. The sandboxed Jinja2 environment with StrictUndefined is the correct security posture for user-defined prompts. The audit hashing strategy (template, variables, rendered output, lookup, contract) provides excellent traceability. The only substantive concerns are: (1) a subtle inconsistency in how lookup_data=None vs lookup_data={} is handled for the template context vs the hash, and (2) the contract_hash computation accesses `fc.python_type.__name__` which could fail for certain edge-case types. The code is production-ready.

## Critical Findings

None.

## Warnings

### [106] lookup_data None-to-empty-dict conversion loses semantic distinction in template context

**What:** Line 106: `self._lookup_data = lookup_data if lookup_data is not None else {}`. When `lookup_data` is `None`, the template context gets an empty dict `{}` for `lookup`. When `lookup_data` is explicitly `{}`, the template context also gets `{}`. The hash correctly distinguishes them (line 108: `None` if lookup_data is `None`, hash of `{}` if lookup_data is `{}`). However, from the template's perspective, `{{ lookup }}` evaluates to `{}` in both cases, so a template checking `{% if lookup %}` will behave identically.

**Why it matters:** This is a minor audit concern. The `lookup_hash` correctly records `None` vs a hash, but the template rendering does not distinguish these cases. A template author might write `{% if lookup %}` expecting it to detect "no lookup configured," but it would be truthy (an empty dict) even when lookup was not configured. This edge case is unlikely to cause issues in practice since most templates access specific keys like `{{ lookup.key }}` which would raise UndefinedError via StrictUndefined regardless.

**Evidence:** Lines 104-108:
```python
self._lookup_data = lookup_data if lookup_data is not None else {}
self._lookup_source = lookup_source
self._lookup_hash = _sha256(canonical_json(lookup_data)) if lookup_data is not None else None
```

### [220-234] contract_hash accesses python_type.__name__ which assumes standard types

**What:** Line 228 accesses `fc.python_type.__name__` for each field contract when computing the contract hash. If `python_type` is set to a non-standard type (e.g., `None`, a generic like `list[int]`), `.__name__` may fail or produce unexpected results. For `list[int]`, `__name__` is not defined on generic aliases in older Python versions.

**Why it matters:** If a schema contract contains generic types or `None` as a python_type value, the contract hash computation would raise an `AttributeError`, which would propagate as an uncaught exception since this code is inside `render_with_metadata()` but outside the `try/except TemplateError` handler. The error would crash the row processing.

**Evidence:** Line 228:
```python
"t": fc.python_type.__name__,
```
In `openrouter_batch.py` line 497, the contract is built with `python_type=object`, which has `.__name__ == "object"` -- safe. But other code paths may set different types. For example, `type(None).__name__` is `"NoneType"` which is fine, but `typing.Optional[str].__name__` would fail.

## Observations

### [110-119] SandboxedEnvironment with StrictUndefined -- correct security posture

**What:** The template environment uses `SandboxedEnvironment` (prevents access to dangerous operations like `os.system`) and `StrictUndefined` (raises on missing variables rather than silently producing empty strings). `autoescape=False` is correct for prompts (no HTML context).

**Why it matters:** This is exactly right. Sandboxing prevents template injection attacks. StrictUndefined catches configuration errors (wrong field names) at render time rather than producing silently incorrect prompts.

### [40-42] _sha256 helper is simple and correct

**What:** `_sha256` takes a string, encodes as UTF-8, and returns the hex digest. No salt or HMAC -- this is correct for content-addressable hashing where the goal is deterministic deduplication, not security.

### [162-163] PipelineRow wrapping for dual-name access

**What:** When a contract is provided, the row dict is wrapped in a `PipelineRow` instance. This enables templates to use both normalized names (`{{ row.customer_id }}`) and original names (`{{ row["Customer ID"] }}`). This is a thoughtful feature for usability.

### [173-180] Exception wrapping in render()

**What:** `UndefinedError`, `SecurityError`, and general `Exception` are all caught and re-raised as `TemplateError`. This provides a clean error boundary -- callers only need to catch `TemplateError`. The exception chaining (`from e`) preserves the original traceback.

### [209-212] canonical_json failure handling for variables_hash

**What:** `canonical_json(row)` can raise `ValueError` for NaN/Infinity and `TypeError` for non-serializable types. These are caught and re-raised as `TemplateError`, which is correct -- per the Tier 2 trust model, type-valid data can still cause operation failures, and template rendering is an operation on their data.

### [25-37] RenderedPrompt is a well-designed frozen dataclass

**What:** The `RenderedPrompt` dataclass is frozen (immutable) and carries all audit metadata needed for the full lineage chain: template hash, variables hash, rendered hash, template source path, lookup hash, lookup source path, and contract hash. This gives the audit trail everything needed to answer "what prompt was sent and why?"

### Module is importable with no side effects

**What:** The module has no module-level side effects. The Jinja2 environment is created per-instance in `__init__`, not as a module global. This is correct for multi-instance usage (different templates per transform instance).

## Verdict
**Status:** SOUND
**Recommended action:** Minor improvements: (1) Consider adding a guard on `fc.python_type.__name__` to handle edge-case types gracefully, or document the constraint that `python_type` must have `__name__`. (2) Consider using `getattr(fc.python_type, '__name__', str(fc.python_type))` as a defensive fallback for the contract hash computation -- though this is borderline given CLAUDE.md's prohibition on defensive patterns. The correct fix may be to ensure `FieldContract.python_type` is always a concrete type with `__name__`, enforced at the FieldContract level.
**Confidence:** HIGH -- the module is small, focused, and thoroughly readable. All code paths are covered by the analysis.
