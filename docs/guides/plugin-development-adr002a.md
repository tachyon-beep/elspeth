# Plugin Development Guide: ADR-002-A Trusted Container Model

**Target Audience**: Plugin developers implementing datasources, transforms, and sinks
**Security Level**: Required reading for all plugins handling SecureDataFrame
**Last Updated**: 2025-10-25 (ADR-002-A implementation)

---

## Overview

ADR-002-A establishes a **Trusted Container Model** that prevents classification laundering attacks. This guide shows you how to correctly create and transform `SecureDataFrame` instances in your plugins.

**Key Principle**: Only datasources can create `SecureDataFrame` instances from scratch. Plugins can only uplift existing frames, never relabel them.

---

## Quick Reference

| Operation | Datasource Pattern | Plugin Pattern | ❌ Anti-Pattern |
|-----------|-------------------|----------------|----------------|
| **Create Frame** | `create_from_datasource(df, level)` ✅ | Not allowed ❌ | `SecureDataFrame(df, level)` |
| **Transform Data** | N/A | `frame.data['col'] = ...` then `with_uplifted_security_level()` ✅ | Direct mutation without uplift |
| **Generate New Data** | N/A | `with_new_data(new_df)` then `with_uplifted_security_level()` ✅ | Create fresh frame |

---

## For Datasource Developers

### ✅ Correct Pattern: Using the Factory Method

Datasources are **trusted sources** that label data with correct classifications. Use `create_from_datasource()`:

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import SecureDataFrame
import pandas as pd

class MySecretDatasource(BasePlugin):
    """Datasource that loads SECRET data."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MySecretDatasource requires SECRET, got {operating_level.name}"
            )

    def load(self) -> pd.DataFrame:
        # Load your data
        raw_data = pd.DataFrame({"secret_column": ["classified1", "classified2"]})

        # ✅ CORRECT: Create SecureDataFrame via factory method
        classified_frame = SecureDataFrame.create_from_datasource(
            raw_data,
            SecurityLevel.SECRET  # Label with correct classification
        )

        # Return the underlying DataFrame (suite runner will wrap it)
        return classified_frame.data
```

### ❌ Anti-Pattern: Direct Construction (BLOCKED)

```python
def load(self) -> pd.DataFrame:
    raw_data = pd.DataFrame({"data": [1, 2, 3]})

    # ❌ BLOCKED: This will raise SecurityValidationError
    frame = SecureDataFrame(raw_data, SecurityLevel.SECRET)
    #       └─────────────────┬─────────────────┘
    #           Constructor protection blocks this!
```

**Error Message**:
```
SecurityValidationError: SecureDataFrame can only be created by datasources
using create_from_datasource(). Plugins must use with_uplifted_security_level()
to uplift existing frames or with_new_data() to generate new data.
This prevents classification laundering attacks (ADR-002-A).
```

---

## For Transform Plugin Developers

### Pattern 1: In-Place Data Mutation

When you modify `.data` in-place (same schema), uplift the classification:

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import SecureDataFrame

class MyTransformPlugin(BasePlugin):
    """Transform plugin that processes data."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # This plugin requires SECRET clearance

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MyTransformPlugin requires SECRET, got {operating_level.name}"
            )

    def transform(self, input_frame: SecureDataFrame) -> SecureDataFrame:
        # ✅ CORRECT: Mutate .data in-place
        input_frame.data["processed"] = True
        input_frame.data["transformed_value"] = input_frame.data["value"] * 2

        # ✅ CORRECT: Uplift classification to this plugin's security level
        output_frame = input_frame.with_uplifted_security_level(
            self.get_security_level()
        )

        return output_frame
```

**How `with_uplifted_security_level()` works**:
```python
# Uses max() operation - can NEVER downgrade
output_classification = max(input_frame.classification, new_level)

# Examples:
# OFFICIAL + SECRET uplift → SECRET
# SECRET + SECRET uplift → SECRET
# SECRET + OFFICIAL attempt → SECRET (max() prevents downgrade)
```

### Pattern 2: Generating New Data (LLMs, Aggregations)

When you generate an entirely new DataFrame (different schema):

```python
class MyLLMPlugin(BasePlugin):
    """LLM plugin that generates new data."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET  # LLM trained on SECRET data

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MyLLMPlugin requires SECRET, got {operating_level.name}"
            )

    def generate(self, input_frame: SecureDataFrame) -> SecureDataFrame:
        # Generate completely new DataFrame (different columns)
        llm_output = self.llm_client.generate(
            prompt=input_frame.data["prompt"].tolist()
        )
        new_df = pd.DataFrame({"output": llm_output})

        # ✅ CORRECT: Use with_new_data() to preserve input classification
        output_frame = input_frame.with_new_data(new_df)

        # ✅ CORRECT: Then uplift to this plugin's security level
        final_frame = output_frame.with_uplifted_security_level(
            self.get_security_level()
        )

        return final_frame
```

### ❌ Anti-Pattern: Creating Fresh Frames (BLOCKED - Classification Laundering)

```python
def transform(self, input_frame: SecureDataFrame) -> SecureDataFrame:
    result = input_frame.data.copy()
    result["processed"] = True

    # ❌ BLOCKED: This is classification laundering!
    # Malicious plugin could relabel SECRET as OFFICIAL
    output_frame = SecureDataFrame(result, SecurityLevel.OFFICIAL)
    #              └─────────────────┬─────────────────┘
    #                  Constructor protection blocks this!

    return output_frame
```

**Why this is blocked**: Even if you're not malicious, this pattern allows attackers to bypass classification uplifting. ADR-002-A prevents this at the framework level.

---

## For Sink Developers

Sinks typically receive `SecureDataFrame` and validate access:

```python
class MySecretSink(BasePlugin):
    """Sink that writes SECRET data."""

    def get_security_level(self) -> SecurityLevel:
        return SecurityLevel.SECRET

    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        if operating_level < SecurityLevel.SECRET:
            raise SecurityValidationError(
                f"MySecretSink requires SECRET, got {operating_level.name}"
            )

    def write(self, results: dict, *, metadata: dict | None = None) -> None:
        # If results contain SecureDataFrame, validate access
        if isinstance(results.get("data"), SecureDataFrame):
            classified_data = results["data"]

            # ✅ OPTIONAL: Runtime failsafe (start-time validation is primary)
            classified_data.validate_compatible_with(self)

        # Write data
        self.write_to_storage(results)
```

**Note**: `validate_compatible_with()` is a **runtime failsafe**. Start-time validation (ADR-002) is the primary defense. This provides defense-in-depth.

---

## Migration Guide

If you have existing code using direct construction:

### Before (Old Pattern):
```python
df = pd.DataFrame({"data": [1, 2, 3]})
frame = SecureDataFrame(df, SecurityLevel.SECRET)  # ❌ Now blocked
```

### After (New Pattern):

**In Datasources**:
```python
df = pd.DataFrame({"data": [1, 2, 3]})
frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)  # ✅
```

**In Plugins** (should never have been doing this):
```python
# If you were creating frames in plugins, you need to redesign:
# Option 1: Use with_new_data() on existing frame
output_frame = input_frame.with_new_data(new_df).with_uplifted_security_level(level)

# Option 2: If this is really a datasource, move to datasource pattern
```

---

## Testing Your Plugin

### Test Pattern: Datasource

```python
import pytest
from elspeth.core.security.classified_data import SecureDataFrame
from elspeth.core.base.types import SecurityLevel

def test_my_datasource_creates_frame_correctly():
    """Verify datasource uses correct factory pattern."""
    datasource = MySecretDatasource()

    # Load data
    frame_data = datasource.load()

    # Verify data structure (frame.data is returned)
    assert isinstance(frame_data, pd.DataFrame)
    assert "secret_column" in frame_data.columns
```

### Test Pattern: Transform Plugin

```python
def test_my_transform_uplifts_classification():
    """Verify plugin correctly uplifts classification."""
    # Create test input via datasource factory
    input_df = pd.DataFrame({"value": [1, 2, 3]})
    input_frame = SecureDataFrame.create_from_datasource(
        input_df, SecurityLevel.OFFICIAL
    )

    # Transform
    plugin = MyTransformPlugin()
    output_frame = plugin.transform(input_frame)

    # Verify uplifting occurred
    assert output_frame.classification == SecurityLevel.SECRET
    assert "processed" in output_frame.data.columns
```

### Test Pattern: Verify Constructor Protection

```python
def test_plugin_cannot_create_frame_directly():
    """Verify plugins cannot bypass constructor protection."""
    from elspeth.core.validation.base import SecurityValidationError

    df = pd.DataFrame({"data": [1, 2, 3]})

    # Attempt direct construction (simulates attack)
    with pytest.raises(SecurityValidationError) as exc_info:
        frame = SecureDataFrame(df, SecurityLevel.OFFICIAL)

    # Verify error message explains correct pattern
    assert "datasource" in str(exc_info.value).lower()
    assert "create_from_datasource" in str(exc_info.value)
```

---

## Common Mistakes

### Mistake 1: Forgetting to Uplift

```python
# ❌ WRONG: Transform data but don't uplift
def transform(self, input_frame: SecureDataFrame) -> SecureDataFrame:
    input_frame.data["processed"] = True
    return input_frame  # Classification not uplifted!
```

**Fix**: Always call `with_uplifted_security_level()` after transformation:
```python
# ✅ CORRECT
def transform(self, input_frame: SecureDataFrame) -> SecureDataFrame:
    input_frame.data["processed"] = True
    return input_frame.with_uplifted_security_level(self.get_security_level())
```

### Mistake 2: Trying to Downgrade

```python
# This doesn't work - max() prevents downgrade
secret_frame = SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
result = secret_frame.with_uplifted_security_level(SecurityLevel.OFFICIAL)
# result.classification is still SECRET (max(SECRET, OFFICIAL) = SECRET)
```

**This is intentional** - you cannot downgrade classifications. Once data is SECRET, it stays SECRET.

### Mistake 3: Using Constructor in Test Fixtures

```python
# ❌ WRONG: Direct construction in test
@pytest.fixture
def sample_frame():
    df = pd.DataFrame({"data": [1, 2, 3]})
    return SecureDataFrame(df, SecurityLevel.SECRET)  # Blocked!
```

**Fix**: Use factory method in tests too:
```python
# ✅ CORRECT
@pytest.fixture
def sample_frame():
    df = pd.DataFrame({"data": [1, 2, 3]})
    return SecureDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
```

---

## Security Properties Guaranteed

If you follow these patterns, you get these security guarantees:

1. ✅ **No Classification Laundering**: Plugins cannot relabel data with arbitrary classifications
2. ✅ **Automatic Uplifting**: Data passing through high-security components automatically uplifted
3. ✅ **Immutable Classifications**: Once uplifted, cannot be downgraded
4. ✅ **Clear Audit Trail**: All classification changes via `with_uplifted_security_level()` are traceable

---

## FAQ

**Q: Why can't I just create SecureDataFrame directly?**
A: This prevents classification laundering attacks where malicious plugins relabel SECRET data as OFFICIAL. Only datasources (trusted sources) can create frames.

**Q: What if I'm writing a test and need a SecureDataFrame?**
A: Use `SecureDataFrame.create_from_datasource()` in your test fixtures, just like datasources do.

**Q: Can I downgrade a classification?**
A: No, and this is intentional. `with_uplifted_security_level()` uses `max()` operation. Once data is SECRET, it stays SECRET.

**Q: What if my plugin generates entirely new data?**
A: Use `with_new_data(new_df)` to preserve the input classification, then call `with_uplifted_security_level()` to uplift to your plugin's level.

**Q: Why does the error mention "ADR-002-A"?**
A: ADR-002-A is the architectural decision record that established this trusted container model. It's referenced for audit trail purposes.

---

## Related Documentation

- **ADR-002**: Suite-level security enforcement
- **ADR-002-A**: Trusted container model specification
- **Threat Model**: `docs/security/adr-002-threat-model.md` (T4 - Classification Mislabeling)
- **API Reference**: `src/elspeth/core/security/secure_data.py` (implementation)

---

**Questions?** Review the test files for examples:
- `tests/test_adr002a_invariants.py` - Security invariant tests showing correct patterns
- `tests/test_adr002_suite_integration.py` - End-to-end integration tests with full datasource → plugin → sink flow
