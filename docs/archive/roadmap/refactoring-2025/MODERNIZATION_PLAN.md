# Elspeth Modernization Plan - Python 3.12 & Pydantic v2

**Date:** January 2025
**Target:** Python 3.12+ / Pydantic v2
**Status:** Planning Phase

---

## Executive Summary

Elspeth is currently on **Python 3.12** and **Pydantic v2**, but the codebase still uses many legacy patterns from earlier Python/Pydantic versions. This document outlines a comprehensive modernization strategy to adopt modern Python 3.12 features and Pydantic v2 patterns throughout the codebase.

### Key Metrics
- **Files with legacy type hints:** ~60 files
- **Dataclasses that could migrate to Pydantic:** ~31 classes
- **Existing Pydantic usage:** Minimal (DataFrameSchema only)

### Benefits
✅ **Type Safety:** Modern union syntax (`X | Y`) is more readable
✅ **Runtime Validation:** Pydantic models provide automatic validation
✅ **Performance:** Pydantic v2 is 5-50x faster than v1
✅ **Maintainability:** Consistent patterns across codebase
✅ **IDE Support:** Better autocomplete and type checking

---

## Phase 1: Type Hint Modernization

### 1.1 Legacy Type Hint Migration

**Pattern Changes:**
```python
# BEFORE (Python 3.9 style)
from typing import Dict, List, Optional, Union
def foo(x: Optional[Dict[str, List[int]]]) -> Union[str, int]:
    ...

# AFTER (Python 3.10+ style)
def foo(x: dict[str, list[int]] | None) -> str | int:
    ...
```

**Migration Rules:**
- `Dict[K, V]` → `dict[K, V]`
- `List[T]` → `list[T]`
- `Set[T]` → `set[T]`
- `Tuple[T, ...]` → `tuple[T, ...]`
- `Optional[T]` → `T | None`
- `Union[A, B]` → `A | B`

**Files to Update (~60 files):**
- All `src/elspeth/core/**/*.py`
- All `src/elspeth/plugins/**/*.py`
- All `src/elspeth/tools/**/*.py`
- All test files `tests/**/*.py`

**Keep as-is:**
- `Protocol`, `TypeVar`, `Generic`, `Literal`, `TypedDict` (no builtin equivalents)
- `Mapping`, `Sequence`, `Iterable` (ABCs for variance)
- `Callable` (no builtin equivalent)
- `Any` (special type)

### 1.2 Python 3.12 Specific Features

#### Type Parameter Syntax (PEP 695)
```python
# BEFORE
from typing import Generic, TypeVar
T = TypeVar('T')
class Registry(Generic[T]):
    ...

# AFTER (Python 3.12+)
class Registry[T]:
    ...
```

#### Type Aliases with `type` Statement
```python
# BEFORE
from typing import TypeAlias
PluginDict: TypeAlias = Dict[str, Any]

# AFTER (Python 3.12+)
type PluginDict = dict[str, Any]
```

**Candidates for Conversion:**
- `src/elspeth/core/registry/base.py` - `BasePluginRegistry[T]`
- Type aliases in `src/elspeth/core/base/types.py`

---

## Phase 2: Pydantic v2 Migration

### 2.1 Dataclass → Pydantic BaseModel Migration

**Benefits:**
- Runtime validation (catches config errors early)
- JSON schema generation (for API docs)
- Serialization/deserialization (`.model_dump()`, `.model_validate()`)
- Field validation (`@field_validator`, `@model_validator`)
- Immutability options (`frozen=True`)

**Migration Pattern:**
```python
# BEFORE (dataclass)
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ExperimentConfig:
    name: str
    temperature: float = 0.7
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None

# AFTER (Pydantic v2)
from pydantic import BaseModel, Field

class ExperimentConfig(BaseModel):
    name: str
    temperature: float = 0.7
    tags: list[str] = Field(default_factory=list)
    description: str | None = None

    model_config = ConfigDict(
        frozen=False,  # or True for immutability
        validate_assignment=True,
        extra='forbid',  # strict validation
    )
```

### 2.2 High-Value Conversion Candidates

**Priority 1: Configuration Models**
- ✅ `ExperimentConfig` - Already validated, add runtime checks
- ✅ `ExperimentSuite` - Suite configuration
- ✅ `PluginContext` - Security-critical, immutable candidate

**Priority 2: Data Transfer Objects**
- `Artifact` classes in `core/artifacts.py`
- `PromptTemplate` in `core/prompts/template.py`
- Configuration classes in `config.py`

**Priority 3: Internal Models**
- Registry response models
- Pipeline state models

**DO NOT Convert (Keep as dataclasses):**
- Protocol definitions (cannot be BaseModel)
- Classes with complex `__post_init__` logic
- Classes requiring structural subtyping
- Performance-critical hot-path classes (measure first!)

### 2.3 Pydantic v2 Pattern Updates

**Field Validators:**
```python
# BEFORE (Pydantic v1)
from pydantic import validator

class Config(BaseModel):
    @validator('temperature')
    def validate_temp(cls, v):
        if not 0 <= v <= 2:
            raise ValueError('Invalid')
        return v

# AFTER (Pydantic v2)
from pydantic import field_validator

class Config(BaseModel):
    @field_validator('temperature')
    @classmethod
    def validate_temp(cls, v: float) -> float:
        if not 0 <= v <= 2:
            raise ValueError('Invalid')
        return v
```

**Model Validators:**
```python
# BEFORE (Pydantic v1)
from pydantic import root_validator

class Config(BaseModel):
    @root_validator
    def validate_all(cls, values):
        ...

# AFTER (Pydantic v2)
from pydantic import model_validator

class Config(BaseModel):
    @model_validator(mode='after')
    def validate_all(self) -> 'Config':
        ...
```

**Config Class:**
```python
# BEFORE (Pydantic v1)
class Config(BaseModel):
    class Config:
        frozen = True

# AFTER (Pydantic v2)
from pydantic import ConfigDict

class Config(BaseModel):
    model_config = ConfigDict(frozen=True)
```

**Audit Required:**
- Search for `@validator` → replace with `@field_validator`
- Search for `@root_validator` → replace with `@model_validator`
- Search for `class Config:` inside models → replace with `model_config = ConfigDict(...)`

---

## Phase 3: Additional Modernizations

### 3.1 Match Statement (Python 3.10+)

```python
# BEFORE
if security_level == "public":
    return 0
elif security_level == "internal":
    return 1
elif security_level == "confidential":
    return 2
else:
    return 3

# AFTER (Python 3.10+)
match security_level:
    case "public":
        return 0
    case "internal":
        return 1
    case "confidential":
        return 2
    case _:
        return 3
```

**Candidates:**
- Security level resolution logic
- Plugin type dispatching
- Configuration merging logic

### 3.2 Structural Pattern Matching for Validation

```python
# Complex validation patterns
match config:
    case {"type": "csv", "path": str(p)} if Path(p).exists():
        return load_csv(p)
    case {"type": "blob", "container": str(c), "blob": str(b)}:
        return load_blob(c, b)
    case _:
        raise ValueError("Invalid config")
```

### 3.3 Exception Groups (Python 3.11+)

```python
# For collecting multiple validation errors
errors = []
if not name:
    errors.append(ValueError("Name required"))
if temperature < 0:
    errors.append(ValueError("Temp must be positive"))

if errors:
    raise ExceptionGroup("Validation failed", errors)
```

### 3.4 Performance Improvements

**Slots for Frequent Objects:**
```python
# Add __slots__ to frequently instantiated classes
class PluginContext:
    __slots__ = ('security_level', 'provenance', 'plugin_kind', 'plugin_name')

    def __init__(self, ...):
        ...
```

**Cached Properties:**
```python
from functools import cached_property

class ExperimentConfig:
    @cached_property
    def estimated_cost(self) -> dict[str, float]:
        # Expensive calculation, cached after first access
        ...
```

---

## Phase 4: Implementation Strategy

### Step 1: Type Hint Migration (Low Risk)
**Duration:** 2-4 hours
**Files:** ~60 files
**Risk:** Low (purely syntactic)

1. Create automated script to replace type hints
2. Run on all Python files
3. Run test suite to verify
4. Run mypy to verify type checking still works

### Step 2: Pydantic Migration - Configuration Models (Medium Risk)
**Duration:** 4-6 hours
**Files:** ~5 core config classes
**Risk:** Medium (behavior changes)

1. Convert `ExperimentConfig` to Pydantic
2. Convert `ExperimentSuite` to Pydantic
3. Update all usages
4. Add validation tests
5. Run full test suite

### Step 3: Pydantic Migration - DTOs (Medium Risk)
**Duration:** 6-8 hours
**Files:** ~10 data classes
**Risk:** Medium

1. Convert artifact classes
2. Convert prompt template classes
3. Update serialization code
4. Run full test suite

### Step 4: Python 3.12 Features (Low Risk)
**Duration:** 2-3 hours
**Files:** ~5 files
**Risk:** Low

1. Migrate `BasePluginRegistry[T]` to new syntax
2. Convert type aliases to `type` statement
3. Test generic type inference

### Step 5: Advanced Features (Optional)
**Duration:** 4-6 hours
**Risk:** Low-Medium

1. Add match statements where beneficial
2. Add `__slots__` to hot-path classes
3. Profile and optimize

---

## Phase 5: Quality Assurance

### Testing Strategy
1. **Unit Tests:** All existing tests must pass
2. **Type Checking:** `mypy` must pass with no new errors
3. **Linting:** `ruff` must pass
4. **Integration Tests:** Run sample suite end-to-end
5. **Performance Tests:** No regression in execution time

### Rollback Plan
- All changes in feature branch
- Atomic commits per phase
- Can rollback to any phase if issues found

### Success Criteria
✅ All tests passing (536+)
✅ No type checking errors
✅ No linting errors
✅ Test coverage maintained at 87%+
✅ No performance regressions
✅ Documentation updated

---

## Estimated Timeline

| Phase | Duration | Complexity | Risk |
|-------|----------|------------|------|
| Type Hint Migration | 2-4 hours | Low | Low |
| Pydantic Config Models | 4-6 hours | Medium | Medium |
| Pydantic DTOs | 6-8 hours | Medium | Medium |
| Python 3.12 Features | 2-3 hours | Low | Low |
| Advanced Features | 4-6 hours | Medium | Low-Medium |
| **Total** | **18-27 hours** | - | - |

---

## Decision Log

### Decisions Made
- ✅ Migrate all type hints to modern syntax
- ✅ Use Pydantic v2 for configuration models
- ✅ Keep protocols as dataclasses/protocols
- ✅ Use match statements where it improves readability

### Decisions Deferred
- ⏸️ Exception groups (wait for real use case)
- ⏸️ `__slots__` optimization (profile first)
- ⏸️ Structural pattern matching for validation (assess after Pydantic migration)

### Decisions Against
- ❌ Convert all dataclasses to Pydantic (overkill for simple DTOs)
- ❌ Use experimental typing features (stick to stable features)

---

## References

- [PEP 585: Type Hinting Generics In Standard Collections](https://peps.python.org/pep-0585/)
- [PEP 604: Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
- [PEP 695: Type Parameter Syntax](https://peps.python.org/pep-0695/)
- [Pydantic v2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
- [Python 3.12 Release Notes](https://docs.python.org/3/whatsnew/3.12.html)
