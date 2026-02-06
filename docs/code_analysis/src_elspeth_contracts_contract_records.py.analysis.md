# Analysis: src/elspeth/contracts/contract_records.py

**Lines:** 284
**Role:** Audit record types for schema contracts. Bridges `SchemaContract` (runtime) to Landscape storage (JSON serialization). Defines `FieldAuditRecord`, `ContractAuditRecord`, and `ValidationErrorWithContract`. Implements the serialize/deserialize cycle with integrity hash verification. This module is the Tier 1 audit trail integration point for schema contracts.
**Key dependencies:** `json` (stdlib), `datetime` (stdlib), `elspeth.contracts.errors` (ContractViolation subtypes), `elspeth.contracts.schema_contract` (FieldContract, SchemaContract -- TYPE_CHECKING only), `elspeth.core.canonical` (canonical_json -- lazy import in `to_json()`). Imported by `contracts/__init__.py`, checkpoint tests, contract audit integration tests.
**Analysis depth:** FULL

## Summary

This module correctly implements the serialize-deserialize-verify pattern for audit trail integrity. The hash verification in `to_schema_contract()` is a proper Tier 1 safeguard. The most significant finding is a type map divergence: `TYPE_MAP` in this file includes `datetime` and `object` types, which `ALLOWED_CONTRACT_TYPES` in `type_normalization.py` does NOT include. This means a `FieldContract` with `python_type=object` (the "any" type) will serialize and deserialize correctly through `ContractAuditRecord`, but `normalize_type_for_contract()` will never produce `object` as an output. The `datetime` type IS in both maps, so that is consistent. The `object` divergence is not a bug because `object` fields come from config declarations (not inference), but it represents a subtle maintenance hazard.

## Critical Findings

### [32-40] TYPE_MAP diverges from ALLOWED_CONTRACT_TYPES and duplicates SchemaContract.from_checkpoint type_map

**What:** There are three separate type maps that must stay synchronized:
1. `contract_records.py` line 32: `TYPE_MAP` -- has `{int, str, float, bool, NoneType, datetime, object}`
2. `schema_contract.py` line 357: `type_map` (local to `from_checkpoint()`) -- has `{int, str, float, bool, NoneType, datetime, object}`
3. `type_normalization.py` line 22: `ALLOWED_CONTRACT_TYPES` -- has `{int, str, float, bool, NoneType, datetime}` (NO `object`)
4. `schema_contract.py` line 31: `VALID_FIELD_TYPES` -- has `{int, str, float, bool, NoneType, datetime, object}`

The `object` type is present in maps 1, 2, and 4 but absent from map 3. This is intentionally correct (`object` is a declared "any" type that bypasses inference), but having three independent type maps that must be manually kept in sync is a DRY violation that will cause bugs if any one is updated without the others.

**Why it matters:** If a developer adds a new type (e.g., `Decimal`) to one map but not the others, the system will silently accept data during inference but crash during deserialization, or vice versa. The `SchemaContract.from_checkpoint()` and `ContractAuditRecord.to_schema_contract()` must both handle the same types, and currently they independently define identical maps. A single authoritative type registry should exist.

**Evidence:**
```python
# contract_records.py:32 (this file)
TYPE_MAP: dict[str, type] = {
    "int": int, "str": str, "float": float, "bool": bool,
    "NoneType": type(None), "datetime": datetime, "object": object,
}

# schema_contract.py:357 (separate identical definition)
type_map: dict[str, type] = {
    "int": int, "str": str, "float": float, "bool": bool,
    "NoneType": type(None), "datetime": datetime, "object": object,
}
```

## Warnings

### [154-179] `from_json()` uses `json.loads()` not `canonical_json` for deserialization

**What:** `to_json()` (line 135) uses `canonical_json()` for deterministic serialization, but `from_json()` (line 155) uses standard `json.loads()` for deserialization. This is correct behavior (canonical serialization, standard deserialization), but creates an asymmetry that could confuse a maintainer into thinking `from_json()` should also use a canonical path.

**Why it matters:** This is actually fine -- `json.loads()` correctly deserializes any valid JSON, including canonically-formatted JSON. The asymmetry is intentional: canonicalization is only needed for deterministic hashing on the write side. However, there is no integrity check in `from_json()` itself. The hash verification only happens in `to_schema_contract()`, meaning `from_json()` will happily load corrupted JSON without detecting it. If a caller uses `from_json()` without subsequently calling `to_schema_contract()`, the corruption goes undetected.

**Evidence:**
```python
def to_json(self) -> str:
    from elspeth.core.canonical import canonical_json
    # ...
    return canonical_json(data)  # Canonical serialization

@classmethod
def from_json(cls, json_str: str) -> ContractAuditRecord:
    data = json.loads(json_str)  # Standard deserialization -- no hash check
    # ...
```

### [181-222] `to_schema_contract()` hash verification uses `version_hash()` which computes canonical_json

**What:** The integrity verification in `to_schema_contract()` calls `contract.version_hash()` which internally calls `canonical_json()`. This means the verification path has a dependency on `elspeth.core.canonical`, making it potentially fragile if the canonical serialization format changes between versions.

**Why it matters:** If the canonical JSON library (`rfc8785`) changes its output format, or if the normalization logic in `_normalize_for_canonical()` changes, then hash verification will fail for all previously-stored contracts even if the data is not corrupted. This is partially by design (any change is detected), but it means schema version upgrades must include a re-hash migration step. This is not documented.

**Evidence:**
```python
def to_schema_contract(self) -> SchemaContract:
    # ...
    actual_hash = contract.version_hash()  # Calls canonical_json internally
    if actual_hash != self.version_hash:
        raise ValueError("Contract integrity violation: hash mismatch.")
```

### [246-284] `from_violation()` uses isinstance chain instead of dispatch

**What:** `ValidationErrorWithContract.from_violation()` uses an isinstance chain (`TypeMismatchViolation`, `MissingFieldViolation`, `ExtraFieldViolation`) with a catch-all `else: raise ValueError`. This means adding a new `ContractViolation` subclass requires updating this method.

**Why it matters:** If a new violation type is added (e.g., `FormatViolation`, `RangeViolation`), this factory method will raise `ValueError("Unknown violation type")` instead of handling it. The method should be kept in sync with the violation class hierarchy. Currently there are exactly three violation types and this matches, but it is a fragile coupling.

**Evidence:**
```python
if isinstance(violation, TypeMismatchViolation):
    # ...
elif isinstance(violation, MissingFieldViolation):
    # ...
elif isinstance(violation, ExtraFieldViolation):
    # ...
else:
    raise ValueError(f"Unknown violation type: {type(violation).__name__}")
```

## Observations

### [43-96] FieldAuditRecord is clean and minimal

Frozen dataclass with slots, correct serialization via `to_dict()`, and a proper `from_field_contract()` factory. The `python_type` is stored as a string (`fc.python_type.__name__`) which is correct for JSON storage.

### [99-133] ContractAuditRecord.from_contract() captures version_hash at creation time

The `version_hash` is computed from the contract at creation time and stored as a field, not recomputed lazily. This is correct for Tier 1 integrity -- the hash at the time of recording is the ground truth.

### [135-152] to_json() lazy imports canonical_json

The lazy import of `canonical_json` from `elspeth.core.canonical` maintains the contracts leaf module boundary. This is the correct pattern per the project's dependency management.

### [225-244] ValidationErrorWithContract captures both normalized and original field names

This dual-name tracking is consistent with the project's header normalization design. Both names are preserved for audit trail reconstruction.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Extract the duplicated type maps (`TYPE_MAP` in this file, `type_map` in `SchemaContract.from_checkpoint()`, `VALID_FIELD_TYPES` in `schema_contract.py`, `ALLOWED_CONTRACT_TYPES` in `type_normalization.py`) into a single authoritative registry. This is a DRY violation with real maintenance risk. (2) Consider adding a hash verification step to `from_json()` or documenting that callers must use `to_schema_contract()` for integrity-verified deserialization. (3) Document the canonical JSON version coupling (hash invalidation on format changes) for migration planning.
**Confidence:** HIGH -- the serialization logic is straightforward, the integrity verification is correct, and the concerns are about maintenance practices rather than correctness bugs.
