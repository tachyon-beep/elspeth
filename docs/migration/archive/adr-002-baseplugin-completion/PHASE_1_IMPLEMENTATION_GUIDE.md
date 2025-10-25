# Phase 1: BasePlugin Implementation Guide

**Objective**: Ensure all 26 plugin classes inherit from BasePlugin ABC and pass security level to the base constructor

**Estimated Effort**: 2-3 hours
**Strategy**: Implement ONE class at a time, test after each

---

## Implementation Template

### Universal Pattern (All Plugins)

BasePlugin now provides the concrete `get_security_level()` and `validate_can_operate_at_level()` implementations. Each plugin only needs to:

```python
from elspeth.core.base.plugin import BasePlugin

class MyPlugin(BasePlugin):
    """Example plugin using BasePlugin security bones."""

    def __init__(self, *, security_level: SecurityLevel, **kwargs):
        super().__init__(security_level=security_level, **kwargs)
        # plugin-specific initialisation
        ...
```

`BasePlugin.__init__` raises if `security_level` is missing or `None`, so every concrete plugin must surface a `security_level` argument (or supply an explicit default before calling `super().__init__`).

---

## Execution Protocol

**FOR EACH PLUGIN CLASS:**

1. **Add `BasePlugin` to the inheritance list** (if not already present)
2. **Expose/propagate a `security_level` keyword argument** and call `super().__init__(security_level=security_level, ...)`
3. **Update docstring** to mention BasePlugin compliance (optional but recommended)
4. **Run tests**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k <ClassName>`
5. **Run mypy**: `mypy src/<path_to_file>.py`
6. **Commit**: `git add <file> && git commit -m "feat: Adopt BasePlugin ABC in <ClassName>"`
7. **Repeat** for next class

---

## Plugin Class Catalog (26 Total)

### Group 1: Datasources (4 classes, ~30 minutes)

#### 1.1 BaseCSVDataSource

**File**: `src/elspeth/plugins/nodes/sources/_csv_base.py`

**Location**: After `__init__` method, before `load()` method

**Code changes**:

1. Update the class signature (if needed) so it inherits from `BasePlugin`:
   ```python
   class BaseCSVDataSource(BasePlugin, DataSource):
       ...
   ```

2. Add a `security_level` keyword argument to `__init__` (it already exists) and make sure the first line calls the base constructor:
   ```python
   def __init__(..., security_level: SecurityLevel | None = None, ...):
       super().__init__(security_level=ensure_security_level(security_level))
       # existing initialisation continues...
   ```

   If the class already normalises `security_level`, pass the resolved value to `super().__init__` and keep assigning to local attributes as needed.

3. Remove any legacy assignments to `self.security_level` that would fight the read-only property (use the property returned by BasePlugin instead, or keep the local variable before calling `super().__init__`).

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k BaseCSVDataSource`

---

#### 1.2 CSVLocalDataSource

**File**: `src/elspeth/plugins/nodes/sources/csv_local.py`

**Notes**: Inherits from BaseCSVDataSource - methods inherited automatically if BaseCSVDataSource done first!

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k CSVLocalDataSource`

**Verification**:
```python
# Verify inheritance works
ds = CSVLocalDataSource(path="test.csv", retain_local=False, security_level=SecurityLevel.OFFICIAL)
assert hasattr(ds, "get_security_level")  # Inherited!
assert hasattr(ds, "validate_can_operate_at_level")  # Inherited!
```

---

#### 1.3 CSVBlobDataSource

**File**: `src/elspeth/plugins/nodes/sources/csv_blob.py`

**Notes**: Inherits from BaseCSVDataSource - methods inherited automatically!

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k CSVBlobDataSource`

---

#### 1.4 BlobDataSource

**File**: `src/elspeth/plugins/nodes/sources/blob.py`

**Notes**: Does NOT inherit from BaseCSVDataSource - ensure the class now inherits from `BasePlugin` and calls `super().__init__(security_level=...)` in its constructor. Remove any manual `self.security_level` assignments.

**Location**: After `__init__` method

**Code**: (Use universal template above, adjust class name in error message to "BlobDataSource")

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k BlobDataSource`

---

### Group 2: LLM Clients (6 classes, ~45 minutes)

#### 2.1 AzureOpenAIClient

**File**: `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`

**Location**: After `__init__` method, before `generate()` method

**Code**: (Use universal template)

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k AzureOpenAIClient`

---

#### 2.2 OpenAIHTTPClient

**File**: `src/elspeth/plugins/nodes/transforms/llm/openai_http.py`

**Location**: After `__init__` method

**Code**: (Use universal template)

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k OpenAIHTTPClient`

---

#### 2.3 MockLLMClient

**File**: `src/elspeth/plugins/nodes/transforms/llm/mock_llm.py`

**Location**: After `__init__` method

**Code**: (Use universal template)

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k MockLLMClient`

---

#### 2.4 StaticLLMClient

**File**: `src/elspeth/plugins/nodes/transforms/llm/static_llm.py`

**Location**: After `__init__` method

**Code**: (Use universal template)

**Test**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k StaticLLMClient`

---

#### 2.5-2.6 Middleware (if they have security_level attribute)

**Files**: Check `src/elspeth/plugins/nodes/transforms/llm/middleware/*.py`

**Note**: Only add if middleware classes have `security_level` attribute. Most middleware likely doesn't - verify first.

---

### Group 3: Sinks (16 classes, ~90 minutes)

**Pattern**: All sinks follow same pattern. List of likely sink classes:

1. CSVFileSink
2. ExcelSink
3. JSONSink
4. MarkdownSink
5. SignedBundleSink
6. RepositorySink
7. ... (total 16)

**Location for all**: After `__init__` method, before `write()` method

**Code for all**: (Use universal template, adjust class name)

**Test each**: `pytest tests/test_adr002_baseplugin_compliance.py -v -k <SinkClassName>`

**Batch execution strategy**:
```bash
# Find all sink files
ls src/elspeth/plugins/nodes/sinks/*.py

# For each sink file:
# 1. Add methods
# 2. Test
# 3. Commit

# Example for CSVFileSink:
# Edit src/elspeth/plugins/nodes/sinks/csv_file.py
pytest tests/test_adr002_baseplugin_compliance.py -v -k CSVFileSink
git add src/elspeth/plugins/nodes/sinks/csv_file.py
git commit -m "feat: Add BasePlugin protocol to CSVFileSink"

# Repeat for next sink...
```

---

## Progress Tracking

Use TodoWrite to track completion:

```python
# After completing each group:
TodoWrite([
    {"content": "Group 1: Datasources (4/4)", "status": "completed", "activeForm": "Completed datasources"},
    {"content": "Group 2: LLM Clients (6/6)", "status": "completed", "activeForm": "Completed LLM clients"},
    {"content": "Group 3: Sinks (16/16)", "status": "in_progress", "activeForm": "Adding BasePlugin to sinks"},
])
```

---

## Common Issues & Solutions

### Issue 1: self.security_level doesn't exist

**Symptom**: `AttributeError: 'PluginClass' object has no attribute 'security_level'`

**Solution**: This plugin doesn't store security_level as attribute. Need to:
1. Add `security_level` parameter to `__init__`
2. Store as `self.security_level = ensure_security_level(security_level)`
3. Then add BasePlugin methods

**Example**:
```python
# Before:
class SomePlugin:
    def __init__(self, ...):
        # No security_level parameter!
        pass

# After:
class SomePlugin:
    def __init__(self, ..., security_level: SecurityLevel | None = None):
        self.security_level = ensure_security_level(security_level)
        # Now BasePlugin methods can use self.security_level
```

---

### Issue 2: MyPy complains about SecurityLevel import

**Symptom**: `error: Cannot find implementation or library stub for module named 'elspeth.core.base.types'`

**Solution**: Add import at top of file:
```python
from elspeth.core.base.types import SecurityLevel
```

---

### Issue 3: Tests fail with "unexpected method"

**Symptom**: Characterization test fails: `assert not hasattr(ds, "get_security_level")` → AssertionError

**Solution**: This is GOOD! It means implementation is working. Update test to reflect new reality:
```python
# OLD (characterization):
assert not hasattr(ds, "get_security_level")

# NEW (after implementation):
assert hasattr(ds, "get_security_level")  # Now implemented!
```

---

## Verification Checklist (Per Class)

After adding methods to each class:

- [ ] Code compiles (no syntax errors)
- [ ] MyPy clean: `mypy src/<path>/<file>.py`
- [ ] Ruff clean: `ruff check src/<path>/<file>.py`
- [ ] Tests pass: `pytest tests/test_adr002_baseplugin_compliance.py -v -k <ClassName>`
- [ ] Method returns correct type (SecurityLevel)
- [ ] Method raises SecurityValidationError when appropriate
- [ ] Commit made with descriptive message

---

## Final Verification (All 26 Classes)

After completing all classes:

```bash
# Run full test suite
pytest tests/test_adr002_baseplugin_compliance.py -v

# Expected results:
# - Category 1 (Characterization): Some FAIL (methods now exist!)
# - Category 2 (Security bug): Some FAIL (validation now runs!)
# - Category 3 (Security properties): All PASS (xfail removed!)
# - Category 4 (Integration): All PASS (xfail removed!)

# Run MyPy on all changed files
mypy src/elspeth/plugins/

# Run Ruff
ruff check src/elspeth/plugins/

# Run FULL test suite (verify no regressions)
pytest tests/ -v
```

---

## Exit Criteria

- ✅ All 26 plugin classes expose `get_security_level()` via BasePlugin inheritance
- ✅ All 26 plugin classes expose `validate_can_operate_at_level()` via BasePlugin inheritance
- ✅ All security property tests (Category 3) PASS
- ✅ All integration tests (Category 4) PASS
- ✅ MyPy clean across all plugin files
- ✅ Ruff clean across all plugin files
- ✅ 26 commits (one per class) OR 3-4 commits (one per group)

---

**Next Phase**: [PHASE_2_VALIDATION_CLEANUP.md](./PHASE_2_VALIDATION_CLEANUP.md)
