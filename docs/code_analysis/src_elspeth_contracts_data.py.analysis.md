# Analysis: src/elspeth/contracts/data.py

**Lines:** 280
**Role:** Pydantic-based schema system for plugins. Defines `PluginSchema` (the base class for plugin input/output schemas), `SchemaValidationError`, `CompatibilityResult`, and the `check_compatibility()` / `validate_row()` functions. This is the older Pydantic-based schema layer (pre-SchemaContract) that still serves as the foundation for plugin schema declarations and static compatibility checking between producers and consumers.
**Key dependencies:** `pydantic` (BaseModel, ConfigDict, ValidationError), `types` (UnionType), `typing` (Union, get_args, get_origin). Imported by `contracts/__init__.py`, `transform_contract.py`, test files. Used in DAG static analysis and plugin schema declarations.
**Analysis depth:** FULL

## Summary

This module is competently written with proper handling of Python's complex type annotation system. The `check_compatibility()` function correctly handles strict vs non-strict coercion semantics per the Data Manifesto. One critical concern: the `_types_compatible()` function does not handle `list[X]`, `dict[X, Y]`, or other generic container types, meaning schema compatibility checks silently pass for structurally different container types. A secondary concern involves `_type_name()` using `hasattr()` which is prohibited by project conventions. The recursive type matching logic is correct but has no depth limit.

## Critical Findings

### [235-280] `_types_compatible()` does not handle generic container types

**What:** The function handles exact matches, `Any`, numeric coercion (int->float), and Union types, but has no logic for generic types like `list[str]` vs `list[int]`, `dict[str, Any]` vs `dict[str, int]`, or `list[str]` vs `list[float]`. When comparing `list[str]` to `list[int]`, neither the exact match (`list[str] != list[int]`) nor any other branch matches, so the function returns `False`. However, if a producer outputs `list` (bare) and a consumer expects `list[str]` (parameterized), these are different `get_origin()` patterns and the comparison falls through to `return False` without checking structural compatibility.

**Why it matters:** If a transform declares `output_schema` with `results: list[dict[str, Any]]` and a downstream consumer expects `results: list[dict[str, str]]`, the compatibility check will report them as incompatible even though at runtime Pydantic would coerce the values. More critically, if bare `list` vs `list[str]` appears, the check gives a false negative. This affects DAG validation at pipeline compile time -- users could get spurious incompatibility errors or (worse) no error when there should be one.

**Evidence:**
```python
def _types_compatible(actual, expected, *, consumer_strict=False):
    if actual == expected:
        return True
    if expected is Any:
        return True
    if expected is float and actual is int:
        return not consumer_strict
    if _is_union_type(expected):
        # ... handles Union
    return False  # No generic type handling (list[X], dict[X,Y], etc.)
```

## Warnings

### [224] `_type_name()` uses `hasattr()` which is prohibited

**What:** Line 224 uses `hasattr(t, "__name__")` which the CLAUDE.md explicitly prohibits under "PROHIBITION ON DEFENSIVE PROGRAMMING PATTERNS."

**Why it matters:** Per project conventions, `hasattr()` is a bug-hiding pattern. The function should use direct attribute access. In practice, this is a display utility that produces human-readable type names, so the risk is low, but it violates the project's stated conventions. The `hasattr` here is checking Python type objects -- standard types always have `__name__`, but generic aliases from `typing` module may not. This is one of the legitimate boundary cases (framework introspection), but it should be documented as such.

**Evidence:**
```python
def _type_name(t: Any) -> str:
    origin = get_origin(t)
    if origin is not None:
        return str(t)
    if hasattr(t, "__name__"):  # Prohibited pattern
        return str(t.__name__)
    return str(t)
```

### [164] Direct dict key access on `model_config` assumes key presence

**What:** Line 164 accesses `consumer_schema.model_config["strict"]` and line 196 accesses `consumer_schema.model_config["extra"]` directly. The inline comments acknowledge this is intentional per Tier 1 trust model (all schemas inherit from `PluginSchema` which sets these).

**Why it matters:** This is actually correct per the project's conventions -- if `model_config` is missing these keys, it means `PluginSchema` base class is broken, which should crash. The comments explain the rationale. However, if a third-party Pydantic model is ever passed to `check_compatibility()` (not a `PluginSchema` subclass), these would `KeyError` without a clear error message explaining why. The type signature accepts `type[PluginSchema]` which prevents this at the type level but not at runtime.

**Evidence:**
```python
consumer_strict = consumer_schema.model_config["strict"]  # Line 164
consumer_forbids_extras = consumer_schema.model_config["extra"] == "forbid"  # Line 196
```

### [273-278] Recursive union compatibility check has no depth guard

**What:** `_types_compatible()` calls itself recursively when handling nested Union types. If a pathological type annotation creates deeply nested Unions (e.g., `Union[Union[Union[..., None], None], None]`), this could recurse deeply.

**Why it matters:** In practice, Python's type system rarely produces deeply nested Unions -- `typing.get_args()` flattens most of them. The risk is theoretical but worth noting. No practical depth limit is needed for current usage, but if ELSPETH ever processes schemas from external/untrusted sources, this could be exploited.

**Evidence:**
```python
if _is_union_type(actual):
    actual_args = get_args(actual)
    return all(
        any(_types_compatible(a, e, consumer_strict=consumer_strict) for e in expected_args)
        for a in actual_args
    )
```

## Observations

### [28-60] PluginSchema base class is well-configured

The `ConfigDict` settings (`extra="ignore"`, `strict=False`, `frozen=False`) are appropriate for the Tier 2/3 trust boundary. The `from_row()` and `to_row()` convenience methods are clean and use Pydantic's own validation.

### [62-74] SchemaValidationError is a plain class, not a dataclass or exception

`SchemaValidationError` is a regular class with `__init__`, `__str__`, and `__repr__`. It is not an exception (not raised, just collected into lists). This is correct for its usage pattern in `validate_row()` which returns a list of errors.

### [107-131] CompatibilityResult has a useful `error_message` property

The formatted error message aggregates all compatibility issues into a human-readable string. This is used in DAG validation output and provides good developer experience.

### [229-232] `_is_union_type` correctly handles both old and new Union syntax

Handles both `typing.Union[X, Y]` (where `get_origin()` returns `Union`) and `X | Y` (where it's a `types.UnionType`). This is important for Python 3.10+ compatibility.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) The missing generic container type handling in `_types_compatible()` should be evaluated -- determine if any current or planned schemas use `list[X]`, `dict[X,Y]`, etc. and if so, add structural compatibility checking. (2) Replace `hasattr()` on line 224 with a try/except or explicit type check per project conventions. (3) Document the container-type gap as a known limitation if it is not addressed.
**Confidence:** HIGH -- the code is straightforward, well-commented, and the Pydantic integration is standard. The generic type gap is a real limitation but may not affect current usage since most plugin schemas use primitive types.
