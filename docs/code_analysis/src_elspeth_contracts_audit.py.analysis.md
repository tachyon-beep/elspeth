# Analysis: src/elspeth/contracts/audit.py

**Lines:** 685
**Role:** Audit record type definitions. Defines the dataclasses and types that represent audit trail records -- row states, node states, operations, outcomes, and all other Landscape table records. These are the Tier 1 ("full trust") data contracts between the recorder, repository layer, and consumers of audit data. Per the Data Manifesto, any anomaly in these types must crash the system immediately.
**Key dependencies:**
- Imports: `dataclasses`, `datetime`, `typing`, `elspeth.contracts.enums` (all enum types)
- Imported by: `contracts/__init__.py` (re-exports everything), `core/landscape/repositories.py` (all types for DB->domain conversion), `core/landscape/recorder.py` (via contracts init), `contracts/checkpoint.py`, plus test files for node states, checkpoint contracts, batch audit, gate executor, sink executor, orchestrator audit, aggregation audit, etc.
**Analysis depth:** FULL

## Summary

This file is the authoritative definition of what the "legal record" looks like in ELSPETH. It is well-designed with clear Tier 1 trust enforcement: enum validation via `_validate_enum()`, `__post_init__` validators on critical dataclasses, frozen dataclasses for immutable state variants, and a discriminated union for NodeState. I found one warning-level issue (NonCanonicalMetadata states invariants in its docstring but does not enforce them), one design inconsistency (Operation uses Literal strings instead of enums), and several observations. Overall the file is sound and faithful to the architectural principles.

## Warnings

### [481-546] NonCanonicalMetadata declares invariants but does not enforce them

**What:** The `NonCanonicalMetadata` frozen dataclass documents three invariants in its docstring:
1. "repr_value is never empty (captures what we saw)"
2. "type_name must be a valid Python type name"
3. "canonical_error explains why canonical serialization failed"

However, there is no `__post_init__` method that validates any of these invariants. An empty `repr_value=""`, empty `type_name=""`, or empty `canonical_error=""` would be accepted without error.

**Why it matters:** This type is used when external data fails canonicalization -- it captures forensic metadata for the audit trail. If `repr_value` is empty, the audit record for a quarantined row would have no indication of what the original data looked like. Per the Tier 1 trust model, the audit trail must be pristine -- garbage metadata defeats the purpose of recording non-canonical data. The `from_error()` factory method naturally produces non-empty values (via `repr(data)`, `type(data).__name__`, `str(error)`), but direct construction bypasses this.

**Evidence:**
```python
@dataclass(frozen=True)
class NonCanonicalMetadata:
    """...
    Invariants:
    - repr_value is never empty (captures what we saw)
    - type_name must be a valid Python type name
    - canonical_error explains why canonical serialization failed
    """
    repr_value: str
    type_name: str
    canonical_error: str
    # No __post_init__ to validate invariants
```

**Recommendation:** Add a `__post_init__` method that validates at minimum that `repr_value`, `type_name`, and `canonical_error` are non-empty strings. This is consistent with the Checkpoint dataclass (lines 399-408) which validates its invariants in `__post_init__`.

### [601-651] Operation uses Literal strings for status instead of enums

**What:** The `Operation` dataclass uses `Literal["source_load", "sink_write"]` for `operation_type` and `Literal["open", "completed", "failed", "pending"]` for `status`. Every other audit dataclass that has status fields uses proper enum types with `_validate_enum()` in `__post_init__`.

**Why it matters:** This creates an inconsistency in the Tier 1 trust model:
- `Run.status` uses `RunStatus` enum with `_validate_enum()` -- crash on bad data
- `Batch.status` uses `BatchStatus` enum with `_validate_enum()` -- crash on bad data
- `Operation.status` uses `Literal[...]` -- no runtime validation at all

The `Operation` dataclass has no `__post_init__` method. A string like `"invalid_status"` would be accepted at the Python level (Literal types are only enforced by type checkers, not at runtime). If the database somehow contained an invalid status, the Operation dataclass would happily store it without crashing, violating the "crash on garbage" principle.

Additionally, `Operation.to_dict()` serializes `status` as a plain string. While the other audit types rely on `str(Enum)` behavior (the enums inherit from `str`), Operation's status is already a string, so this works -- but it means the database could contain any string value without a matching enum member to constrain it.

**Evidence:**
```python
@dataclass(frozen=True, slots=True)
class Operation:
    operation_type: Literal["source_load", "sink_write"]
    status: Literal["open", "completed", "failed", "pending"]
    # No __post_init__ - no runtime validation
```

Compare with:
```python
@dataclass
class Batch:
    status: BatchStatus  # Strict: enum only
    def __post_init__(self) -> None:
        _validate_enum(self.status, BatchStatus, "status")
```

**Recommendation:** Create `OperationType` and `OperationStatus` enums in `contracts/enums.py`, update `Operation` to use them, and add `__post_init__` validation. This aligns Operation with every other audit type and ensures runtime Tier 1 crash behavior on invalid data.

## Observations

### [31-39] `_validate_enum` silently passes `None` values

**What:** The `_validate_enum` function skips validation when `value is None`:
```python
def _validate_enum(value: object, enum_type: type, field_name: str) -> None:
    if value is not None and not isinstance(value, enum_type):
        raise TypeError(...)
```

**Why it matters:** This is correct for fields typed as `SomeEnum | None` (like `Run.export_status`), but it means that if a required enum field receives `None`, the validation will pass silently. For example, `Run.status` is typed as `RunStatus` (not optional), but if constructed with `status=None`, `_validate_enum` would not raise -- the `None` check would skip validation entirely.

In practice, this is mitigated because:
1. The type annotations on the dataclass fields would flag `None` in type checking
2. The repository layer constructs these objects with `RunStatus(row.status)` which would crash on `None` input
3. `None` for a required field would likely cause crashes downstream

**Recommendation:** Low priority. The current behavior is intentional for nullable fields. The risk of `None` leaking into required fields is mitigated by upstream construction patterns. For defense-in-depth, required enum fields could have separate validation that rejects `None`, but this is not necessary given the current construction patterns.

### [130-141] Token dataclass has no `run_id` field

**What:** The `Token` dataclass does not include a `run_id` field. The `tokens` database table also has no `run_id` column -- tokens are linked to runs indirectly through `row_id -> rows.run_id`.

**Why it matters:** This is architecturally correct (tokens belong to rows, rows belong to runs), but it means that given a `Token` object alone, you cannot determine which run it belongs to without a join. Every other major audit type (`Row`, `Node`, `Edge`, `Batch`, `TokenOutcome`, `Operation`, `SecretResolution`) has a direct `run_id` field.

This is an observation, not a bug -- the database schema enforces the relationship through foreign keys. However, it means code that needs to filter tokens by run must join through the `rows` table, which is slightly less efficient.

**Recommendation:** No action needed. The schema is consistent and the indirect relationship is appropriate for the data model.

### [153-254] NodeState discriminated union is well-designed

**What:** The four NodeState variants (`NodeStateOpen`, `NodeStatePending`, `NodeStateCompleted`, `NodeStateFailed`) are frozen dataclasses with `Literal` status types, forming a proper discriminated union. Each variant has exactly the fields appropriate for its lifecycle stage.

**Why it matters:** This is a positive finding. The design ensures that:
- Open states cannot have output hashes or completion timestamps
- Completed states must have output hashes and completion timestamps
- Failed states may have output hashes (partial output before failure)
- The union type `NodeState = NodeStateOpen | NodeStatePending | NodeStateCompleted | NodeStateFailed` enables exhaustive pattern matching

The repository layer (NodeStateRepository) further validates these invariants at load time.

**Recommendation:** No action needed. This is exemplary discriminated union design.

### [258-288] Call dataclass documents XOR constraint but does not validate it

**What:** The `Call` dataclass documents that `state_id` and `operation_id` have an XOR relationship ("exactly one must be set"), but the `__post_init__` method only validates enum fields, not the XOR constraint.

**Why it matters:** The XOR constraint is enforced at the database level via a CHECK constraint:
```sql
(state_id IS NOT NULL AND operation_id IS NULL) OR
(state_id IS NULL AND operation_id IS NOT NULL)
```

However, code that constructs `Call` objects directly (not from DB) could create invalid instances where both or neither are set. This would only be caught when attempting to insert into the database.

**Recommendation:** Low priority. The database constraint provides the authoritative enforcement. Adding validation to `__post_init__` would provide earlier feedback but is redundant with the DB constraint. The recorder methods `record_call()` and `record_operation_call()` already enforce this by construction (one passes `state_id`, the other passes `operation_id`).

### [330-349] Batch.trigger_type uses str instead of TriggerType enum

**What:** The `Batch` dataclass declares `trigger_type: str | None` instead of `TriggerType | None`. The `TriggerType` enum exists in `contracts/enums.py` with values `count`, `timeout`, `condition`, `end_of_source`, `manual`.

**Why it matters:** This is inconsistent with the pattern used for every other enum field in the audit types. The comment says "TriggerType enum value" acknowledging the enum exists, but the field uses `str`. This means no runtime validation for `trigger_type` -- any string would be accepted.

**Evidence:**
```python
@dataclass
class Batch:
    status: BatchStatus  # Strict: enum only (validated in __post_init__)
    trigger_type: str | None = None  # TriggerType enum value (count, time, end_of_source, manual)
```

**Recommendation:** Change to `trigger_type: TriggerType | None = None` and add `_validate_enum(self.trigger_type, TriggerType, "trigger_type")` to `__post_init__`. This aligns with the Tier 1 trust model.

### [370-408] Checkpoint validates hash fields but not format_version range

**What:** The `Checkpoint.__post_init__` validates that `upstream_topology_hash` and `checkpoint_node_config_hash` are non-empty, but does not validate that `format_version` (when not None) is a positive integer or within a valid range.

**Why it matters:** The `CheckpointManager` validates format version compatibility when loading checkpoints, so this is not a gap in practice. However, a negative `format_version` or zero would pass the dataclass validation and only be caught later during compatibility checking.

**Recommendation:** Low priority. The checkpoint manager provides adequate validation at the usage site.

### [568-598] TokenOutcome.is_terminal is redundant with RowOutcome.is_terminal property

**What:** `TokenOutcome` stores `is_terminal: bool` as a separate field, but `RowOutcome` enum already has an `is_terminal` property (`return self != RowOutcome.BUFFERED`). The recorder sets `is_terminal = outcome.is_terminal` at recording time.

**Why it matters:** This is intentional denormalization for the audit trail -- recording the terminal status explicitly rather than deriving it ensures the audit record is self-contained and does not depend on enum definitions at query time. The `__post_init__` validation that `is_terminal` is strictly `bool` (not just truthy) is correct and important since SQLite stores booleans as integers.

**Recommendation:** No action needed. The denormalization is a correct design choice for audit trail integrity.

### [508-521] NonCanonicalMetadata.to_dict uses dunder-style keys

**What:** The `to_dict()` method uses keys `__repr__`, `__type__`, `__canonical_error__` which resemble Python dunder attributes.

**Why it matters:** These keys are used in JSON serialization for the audit trail. The dunder naming convention could confuse tools that give special meaning to double-underscore prefixed keys. However, the comment says this matches "current inline dict structure for backwards compatibility with existing audit data" -- though the backwards compatibility comment technically violates the No Legacy Code Policy.

**Recommendation:** Low priority. The dunder-style keys are established in the audit trail schema. Changing them would require audit trail migration. The "backwards compatibility" comment should be rephrased since the project has no backwards compatibility policy -- these are simply the canonical key names.

### [654-685] SecretResolution has no __post_init__ validation

**What:** The `SecretResolution` frozen dataclass has no validation in `__post_init__`. It stores sensitive audit information (vault URLs, secret names, HMAC fingerprints) without validating that required fields are non-empty.

**Why it matters:** A `SecretResolution` with empty `fingerprint=""` or empty `env_var_name=""` would be accepted, producing an audit record that fails to prove which secret was used. For a system designed for "high-stakes accountability," the secret audit trail should validate its own integrity.

**Recommendation:** Add `__post_init__` validation that `resolution_id`, `run_id`, `env_var_name`, `source`, and `fingerprint` are non-empty strings.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. Add `__post_init__` validation to `NonCanonicalMetadata` for documented invariants (Warning).
2. Create enums for `Operation.status` and `Operation.operation_type` to align with the Tier 1 trust model, or at minimum add `__post_init__` runtime validation (Warning).
3. Change `Batch.trigger_type` from `str | None` to `TriggerType | None` (Observation).
4. Add `__post_init__` validation to `SecretResolution` for non-empty required fields (Observation).
5. Rephrase "backwards compatibility" comment in `NonCanonicalMetadata.to_dict()` (Observation).

Items 1 and 2 are the most important -- they represent gaps in the Tier 1 "crash on garbage" principle that the rest of the file consistently enforces.

**Confidence:** HIGH -- The file is well-structured with clear patterns. The warnings are genuine inconsistencies against the established pattern in the same file, not speculative concerns. The repository layer and recorder provide additional validation layers, but the contract types themselves should be self-validating per the Data Manifesto.
