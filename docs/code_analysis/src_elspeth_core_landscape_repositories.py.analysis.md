# Analysis: src/elspeth/core/landscape/repositories.py

**Lines:** 579
**Role:** Repository layer that converts raw SQLAlchemy database rows into typed domain objects (dataclasses with enum fields). This is the seam between the database (strings) and the domain model (strict enums). Per the Data Manifesto, this is Tier 1 data -- invalid data must crash, never coerce silently.
**Key dependencies:** Imports all audit contract dataclasses from `elspeth.contracts.audit` and all enums from `elspeth.contracts.enums`. Consumed exclusively by `LandscapeRecorder` which instantiates repository objects and delegates row-to-object conversion to them.
**Analysis depth:** FULL

## Summary

This file is architecturally sound and correctly implements the Tier 1 trust model. The NodeStateRepository contains rigorous invariant validation with explicit crash-on-violation semantics. The repository pattern cleanly separates database access from domain model construction. There are no critical findings. The main concerns are around the `session` parameter pattern (passed to constructors but never used) and one edge case in the NodeStateRepository's discriminated union handling.

## Warnings

### [50-52, 79-80, 115-116, etc.] Unused `session` parameter in all repository constructors

**What:** Every repository class accepts a `session: Any` parameter in `__init__` and stores it as `self.session`, but this field is never read or used by any repository method. The `load()` methods take a row object directly and perform no database operations. In `recorder.py` (line 155-169), all repositories are instantiated with `None` as the session argument.

**Why it matters:** This is dead code that creates a misleading API contract. A reader would expect repositories to use their session for database operations, but they are purely stateless mapping functions. The `Any` type annotation hides the fact that `None` is the only value ever passed. This could lead a future developer to mistakenly add session-dependent logic to a repository, not realizing the session is always `None` in production.

**Evidence:**
```python
# In repositories.py (every repository):
class RunRepository:
    def __init__(self, session: Any) -> None:
        self.session = session  # Never read

# In recorder.py:
self._run_repo = RunRepository(None)  # Always None
```

### [86-93] `json.loads` import inside method body (NodeRepository.load)

**What:** The `NodeRepository.load` method imports `json` inside the method body (line 88) rather than at module level. This is the only repository that does this.

**Why it matters:** Minor inconsistency. The `json` module is lightweight and importing it at module level is standard practice. The function-level import suggests this was added as a quick fix rather than being part of the original design. It does not cause a bug, but it is inconsistent with the rest of the file and the project's style.

**Evidence:**
```python
def load(self, row: Any) -> Node:
    import json  # Why not at module level?
    schema_fields: list[dict[str, object]] | None = None
    if row.schema_fields_json is not None:
        schema_fields = json.loads(row.schema_fields_json)
```

### [86-93] `json.loads` on `schema_fields_json` without Tier 1 validation

**What:** When `row.schema_fields_json` is not None, it is parsed with `json.loads` but the result is not validated to be a list. The type annotation says `list[dict[str, object]] | None` but the actual parsed value could be any valid JSON type (string, number, dict, etc.). Per the Data Manifesto, Tier 1 data anomalies should crash.

**Why it matters:** If `schema_fields_json` contains valid JSON that is not a list (e.g., `"null"`, `"{}"`, `"42"`), it would be silently assigned to `schema_fields` with the wrong type, violating Tier 1 trust. The `Node` dataclass does not have a `__post_init__` check for this field's type.

**Evidence:**
```python
schema_fields: list[dict[str, object]] | None = None
if row.schema_fields_json is not None:
    schema_fields = json.loads(row.schema_fields_json)
    # No check: isinstance(schema_fields, list)
```

## Observations

### [266-408] NodeStateRepository is the most complex repository -- and well-implemented

**What:** The `NodeStateRepository.load` method implements a discriminated union with four variants, each with explicit invariant validation that crashes on violation. The validation logic (checking for NULL fields that should not be NULL and vice versa) is thorough and well-documented.

**Why it matters:** This is positive -- this is exactly how Tier 1 trust should be implemented. The crash-on-violation semantics ensure that audit trail corruption is detected immediately rather than propagating silently. The explicit messages identifying the violation type aid debugging.

### [405-408] Unreachable else branch is correctly implemented as defense-in-depth

**What:** The `else` branch at line 405-408 raises `ValueError` for unknown status values. Since `NodeStateStatus` is constructed from `row.status` on line 300 (which would already raise if the value is invalid), this branch is technically unreachable. However, including it is correct defensive practice per the CLAUDE.md guidance on Tier 1 trust.

### [475-520] TokenOutcomeRepository performs explicit Tier 1 validation on `is_terminal`

**What:** The `is_terminal` field is validated to be exactly 0 or 1 before conversion to bool. This prevents SQLite's loose typing from silently converting unexpected integer values (e.g., 2, -1) to truthy booleans.

**Why it matters:** This is a good pattern. SQLite stores booleans as integers and does not enforce a 0/1 constraint at the storage layer. Without this check, any non-zero integer would silently become `True`.

### [All repositories] Consistent pattern, easy to audit

**What:** All repositories follow the same pattern: `__init__` with session, `load()` with row, direct field mapping with enum conversion at specific fields. This consistency makes the code easy to audit and reduces the chance of a mapping error going unnoticed.

### [194-220] CallRepository correctly handles dual-parent context

**What:** The `Call` dataclass has `state_id` and `operation_id` as mutually exclusive parent pointers (XOR constraint). The repository correctly maps both fields from the database row without any special handling -- the XOR enforcement is at the database level.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Remove or refactor the unused `session` parameter from all repository constructors -- it is dead code that misleads readers. (2) Add type validation after `json.loads` in `NodeRepository.load` for `schema_fields_json` to crash on non-list values, consistent with Tier 1 trust. Both are low-effort fixes.
**Confidence:** HIGH -- The file is straightforward mapping code with clear patterns. The unused session parameter is verifiable by searching all call sites. The missing type validation is a gap against the stated Tier 1 policy.
