# Analysis: src/elspeth/contracts/schema_contract.py

**Lines:** 705
**Role:** Schema contract definitions -- defines how pipeline data schemas are validated and propagated. Contains FieldContract (immutable field metadata), SchemaContract (per-node schema with O(1) name resolution), and PipelineRow (row wrapper enabling dual-name access and immutability).
**Key dependencies:**
- Imports from: `contracts.errors` (ContractViolation, ContractMergeError, etc.), `contracts.type_normalization` (normalize_type_for_contract), `core.canonical` (canonical_json, lazy import)
- Imported by: 41+ files across the codebase -- executors, processors, all transform plugins, all source plugins, identity module, contract propagation, contract builder, etc. This is one of the most widely depended-upon modules in the system.
**Analysis depth:** FULL

## Summary

This file is architecturally sound and follows the project's trust model rigorously. The immutable-by-default design (frozen dataclasses, MappingProxyType) is well-implemented. However, there are two warnings worth addressing: the `_by_original` index silently drops entries on original_name collisions, and the `version_hash` uses a truncated 64-bit SHA-256 which, while extremely unlikely to collide in practice, weakens the checkpoint integrity guarantee the code relies upon. No critical findings. The code demonstrates careful defensive design aligned with Tier 1 audit requirements.

## Warnings

### [115] _by_original index silently overwrites on original_name collision

**What:** The `_by_original` index is built as `{fc.original_name: fc.normalized_name for fc in self.fields}`. If two FieldContracts share the same `original_name` but different `normalized_name`s, the last one silently wins. The `__post_init__` validates uniqueness of `normalized_name` but not `original_name`.

**Why it matters:** This can happen in practice when field normalization produces distinct normalized names from identical original names (unlikely but possible with custom normalization), or more plausibly when a transform creates fields with `original_name=name` (as `contract_propagation.py` does at line 62). If two inferred fields happen to share an original name, `resolve_name(original)` would resolve to only one of them, silently making the other inaccessible by original name. The `__getitem__` fallback for FLEXIBLE/OBSERVED mode mitigates this somewhat since the data dict is keyed by normalized name, but any code relying on original name resolution would get wrong results.

**Evidence:**
```python
# Line 115: Last writer wins, no collision detection
by_orig = {fc.original_name: fc.normalized_name for fc in self.fields}
```
Compare with the normalized name uniqueness check at lines 109-112, which properly validates. The asymmetry suggests this was an oversight.

### [313] version_hash truncated to 64 bits weakens integrity guarantee

**What:** `version_hash()` returns `hashlib.sha256(content.encode()).hexdigest()[:16]` -- a 16 hex character (64-bit) truncation. This hash is used in `PipelineRow.to_checkpoint_format()` as the sole key linking rows to their contracts in the `contract_registry`.

**Why it matters:** The `from_checkpoint()` method at line 387-394 relies on this hash to verify integrity: "checkpoint may be corrupted or from different version." With 64-bit truncation, the collision resistance is approximately 2^32 (birthday bound) rather than SHA-256's 2^128. In a high-throughput system creating many distinct contracts (e.g., across many pipeline runs with evolving schemas), collision probability increases. A collision would either: (a) match the wrong contract silently at checkpoint restore, or (b) pass the integrity check on corrupted data. For the audit integrity standards this project demands ("hashes survive payload deletion - integrity is always verifiable"), 64 bits is below best practice. 128 bits (32 hex chars) would be more appropriate.

**Evidence:**
```python
# Line 313
return hashlib.sha256(content.encode()).hexdigest()[:16]

# Line 387-394: Integrity verification relies entirely on this hash
expected_hash = data["version_hash"]
actual_hash = contract.version_hash()
if actual_hash != expected_hash:
    raise ValueError("Contract integrity violation: hash mismatch...")
```

### [234-260] validate() does not check for None on required fields when value IS present

**What:** In the validation loop, line 234 `elif fc.normalized_name in row:` only triggers when the field exists in the row. Lines 244-245 skip type checking when `value is None and not fc.required`. But there is no check for the case where a required field IS present in the row but its value is `None`. A required field with value `None` would be type-checked against its `python_type`, which would produce a TypeMismatchViolation (e.g., expected `int`, got `NoneType`), which is correct but the error message would be misleading -- it says "type mismatch" rather than "required field cannot be None."

**Why it matters:** The behavior is technically correct (a required int field shouldn't be None), but the error message gives a "type mismatch" violation rather than a semantically clearer "required field is None" violation. For audit trail clarity and debuggability, this distinction matters.

**Evidence:**
```python
# Line 244-245: Only skips for optional (not required) fields
if value is None and not fc.required:
    continue
# Falls through to type check at line 251 for required fields with None
# This gives TypeMismatchViolation("expected int, got NoneType")
# rather than a more descriptive error
```

## Observations

### [96-100] Mutable dict fields on frozen dataclass -- correct but subtle pattern

**What:** `_by_normalized` and `_by_original` are defined with `field(default_factory=dict)` on a frozen dataclass, then populated via `object.__setattr__()` in `__post_init__`. They are excluded from `repr`, `compare`, and `hash`. This pattern is correct and widely used, but bypassing `frozen` protection via `object.__setattr__` is inherently subtle. The fields ARE mutable after construction (nothing prevents external code from doing `contract._by_normalized["foo"] = bar`).

**Why it matters:** Low risk since the codebase follows disciplined access patterns, but the mutability of these internal lookup dicts means a careless caller could corrupt the O(1) invariant. The `fields` tuple is truly immutable, so the source of truth is safe.

### [165-204] with_field() creates new SchemaContract per inferred field

**What:** Each call to `with_field()` creates a new `SchemaContract` with all existing fields plus the new one. For a source with N new fields in the first row, this creates N intermediate SchemaContract instances.

**Why it matters:** For typical schemas (10-100 fields), this is fine. For extremely wide schemas (thousands of columns, e.g., some genomics or IoT datasets), this creates quadratic allocation (N SchemaContracts, each with O(N) fields). The immutable design is correct for audit safety but has this performance characteristic. Not a production concern for expected use cases.

### [639-670] __copy__ and __deepcopy__ properly handle MappingProxyType

**What:** Both methods correctly handle the MappingProxyType that would otherwise fail with copy/pickle. The contract is shared by reference (frozen=True makes this safe). This is well-implemented.

### [672-705] PipelineRow checkpoint uses version_hash as sole contract reference

**What:** `to_checkpoint_format()` stores `contract_version` (the truncated hash) rather than the full contract. `from_checkpoint()` looks up the contract from a `contract_registry` keyed by this hash. This is architecturally efficient (contracts stored once per node, not per row) but couples checkpoint correctness to the hash quality concern noted above.

### [29-41] VALID_FIELD_TYPES includes `object` but ALLOWED_CONTRACT_TYPES does not

**What:** `VALID_FIELD_TYPES` in this file includes `object` (for 'any' type fields), but `ALLOWED_CONTRACT_TYPES` in `type_normalization.py` does not. This means `normalize_type_for_contract()` will raise `TypeError` if passed an object-typed value that isn't one of the primitives, while `FieldContract.__post_init__` accepts `object` as a valid `python_type`. This is intentionally asymmetric: `object` is a declared type (from config), not an inferred type (from values). The two frozensets serve different purposes. This is correct but the naming overlap could confuse maintainers.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The `_by_original` collision issue (W1) should be addressed with either uniqueness validation or a documented policy for collision handling. The version_hash truncation (W2) should be lengthened to at least 128 bits given the audit integrity requirements. Neither is critical -- both would require specific circumstances to manifest -- but both weaken guarantees the system claims to provide.
**Confidence:** HIGH -- Full read of the file plus all dependencies, consumers, and the trust model documentation. The findings are based on concrete code analysis, not speculation.
