# Field Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement field name normalization at source boundary to handle messy external CSV headers.

**Architecture:** New `field_normalization.py` utility module contains the algorithm. `TabularSourceDataConfig` extends `SourceDataConfig` with normalization options. Sources call resolution at start of `load()`.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, unicodedata, keyword module

**Design Doc:** `docs/plans/2026-01-29-field-normalization-design.md`

---

## Deployment Order Warning

⚠️ **CRITICAL**: Tasks 1-6 must be deployed together as an atomic unit. Partial deployment creates silent failures:
- Templates written against normalized names (e.g., `{{ row.user_id }}`) will fail at runtime if normalization isn't enabled
- The "Fixes that Fail" archetype - normalization creates new problems if templates reference old names

## Dependency Graph

```
Task 1 (normalize_field_name)
    ↓
Task 2 (Unicode/keyword tests) ─────────────────────────────────────────┐
    ↓                                                                   │
Task 3 (collision detection)                                            │
    ↓                                                                   │
Task 4 (resolve_field_names) ← Task 5 (TabularSourceDataConfig) uses    │
    ↓                              ↓                                    │
Task 6 (CSVSource) ← ─ ─ ─ ─ ─ ─ ─ ┘                                    │
    ↓                                                                   │
Task 7 (Template Validation) ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
    ↓
Task 8 (Full Test Suite)
    ↓
Task 9 (Azure Blob Source) [optional MVP+1]
    ↓
Task 10 (JSONSource) [MVP+1 - deferred]
```

---

## Task 1: Create Field Normalization Utility Module

**Files:**
- Create: `src/elspeth/plugins/sources/field_normalization.py`
- Test: `tests/plugins/sources/test_field_normalization.py`

### Step 1.1: Write failing test for basic normalization

```python
# tests/plugins/sources/test_field_normalization.py
"""Tests for field normalization algorithm."""

import pytest


class TestNormalizeFieldName:
    """Unit tests for normalize_field_name function."""

    def test_basic_normalization_spaces_to_underscore(self) -> None:
        """Spaces are replaced with underscores."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("User ID") == "user_id"

    def test_basic_normalization_lowercase(self) -> None:
        """Mixed case is lowercased."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("CaSE Study1 !!!! xx!") == "case_study1_xx"

    def test_special_chars_replaced(self) -> None:
        """Special characters become underscores, collapsed."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("data.field") == "data_field"
        assert normalize_field_name("amount$$$") == "amount"

    def test_leading_digit_prefixed(self) -> None:
        """Leading digits get underscore prefix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("123_field") == "_123_field"

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("  Amount  ") == "amount"

    def test_empty_result_raises_error(self) -> None:
        """Headers that normalize to empty raise ValueError."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        with pytest.raises(ValueError, match="normalizes to empty"):
            normalize_field_name("!!!")
```

### Step 1.2: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py -v`
Expected: FAIL with "No module named 'elspeth.plugins.sources.field_normalization'"

### Step 1.3: Write minimal implementation

```python
# src/elspeth/plugins/sources/field_normalization.py
"""Field name normalization for external data sources.

This module normalizes messy external headers (e.g., "CaSE Study1 !!!! xx!")
to valid Python identifiers (e.g., "case_study1_xx") at the source boundary.

Per ELSPETH's Three-Tier Trust Model, this is Tier 3 (external data) handling:
- Sources ARE allowed to normalize/coerce external data
- Transforms expect normalized names (no coercion downstream)
"""

from __future__ import annotations

import keyword
import re
import unicodedata

# Pre-compiled regex patterns (module level for efficiency)
_NON_IDENTIFIER_CHARS = re.compile(r"[^\w]+")
_CONSECUTIVE_UNDERSCORES = re.compile(r"_+")


def normalize_field_name(raw: str) -> str:
    """Normalize messy header to valid Python identifier.

    Rules applied in order:
    1. Unicode NFC normalization (canonical composition)
    2. Strip leading/trailing whitespace
    3. Lowercase
    4. Replace non-identifier chars with underscore
    5. Collapse consecutive underscores
    6. Strip leading/trailing underscores
    7. Prefix with underscore if starts with digit
    8. Append underscore if result is Python keyword
    9. Raise error if result is empty

    Args:
        raw: Original messy header name

    Returns:
        Valid Python identifier

    Raises:
        ValueError: If header normalizes to empty string
    """
    # Step 1: Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", raw)

    # Step 2: Strip whitespace
    normalized = normalized.strip()

    # Step 3: Lowercase
    normalized = normalized.lower()

    # Step 4: Replace non-identifier chars with underscore
    normalized = _NON_IDENTIFIER_CHARS.sub("_", normalized)

    # Step 5: Collapse consecutive underscores
    normalized = _CONSECUTIVE_UNDERSCORES.sub("_", normalized)

    # Step 6: Strip leading/trailing underscores
    normalized = normalized.strip("_")

    # Step 7: Prefix if starts with digit
    if normalized and normalized[0].isdigit():
        normalized = f"_{normalized}"

    # Step 8: Handle Python keywords
    if keyword.iskeyword(normalized):
        normalized = f"{normalized}_"

    # Step 9: Validate non-empty result
    if not normalized:
        raise ValueError(f"Header '{raw}' normalizes to empty string")

    # Defense-in-depth: verify result is valid identifier
    if not normalized.isidentifier():
        raise ValueError(
            f"Header '{raw}' normalized to '{normalized}' which is not a valid identifier. "
            f"This is a bug in the normalization algorithm."
        )

    return normalized
```

### Step 1.4: Run test to verify it passes

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py -v`
Expected: PASS (6 tests)

### Step 1.5: Commit

```bash
git add src/elspeth/plugins/sources/field_normalization.py tests/plugins/sources/test_field_normalization.py
git commit -m "feat(sources): add field normalization algorithm

Normalizes messy external headers to valid Python identifiers at source
boundary. Handles Unicode, special chars, leading digits, and keywords."
```

---

## Task 2: Add Unicode and Keyword Tests (P0 Coverage)

**Files:**
- Modify: `tests/plugins/sources/test_field_normalization.py`

### Step 2.1: Write failing tests for Unicode edge cases

Add to `TestNormalizeFieldName` class:

```python
    def test_unicode_bom_stripped(self) -> None:
        """BOM character at start is stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("\ufeffid") == "id"

    def test_zero_width_chars_stripped(self) -> None:
        """Zero-width characters are stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("id\u200b") == "id"

    def test_emoji_stripped(self) -> None:
        """Emoji characters are stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("Status 🔥") == "status"

    def test_python_keyword_gets_suffix(self) -> None:
        """Python keywords get underscore suffix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("class") == "class_"
        assert normalize_field_name("for") == "for_"
        assert normalize_field_name("import") == "import_"

    def test_header_normalizing_to_keyword_gets_suffix(self) -> None:
        """Headers that normalize to keywords also get suffix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("CLASS") == "class_"
        assert normalize_field_name("For ") == "for_"

    def test_accented_chars_preserved(self) -> None:
        """Accented characters are valid identifiers (PEP 3131)."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("café") == "café"
        assert normalize_field_name("naïve") == "naïve"
```

### Step 2.2: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py -v`
Expected: PASS (all tests - algorithm already handles these)

### Step 2.3: Commit

```bash
git add tests/plugins/sources/test_field_normalization.py
git commit -m "test(sources): add P0 Unicode and keyword normalization tests

Covers BOM, zero-width chars, emoji, Python keywords, and accented chars."
```

---

## Task 3: Add Collision Detection Functions

**Files:**
- Modify: `src/elspeth/plugins/sources/field_normalization.py`
- Modify: `tests/plugins/sources/test_field_normalization.py`

### Step 3.1: Write failing tests for collision detection

Add new test class:

```python
class TestCollisionDetection:
    """Tests for collision detection functions."""

    def test_no_collision_passes(self) -> None:
        """No collision when all normalized names are unique."""
        from elspeth.plugins.sources.field_normalization import check_normalization_collisions

        raw = ["User ID", "Amount", "Date"]
        normalized = ["user_id", "amount", "date"]
        # Should not raise
        check_normalization_collisions(raw, normalized)

    def test_two_way_collision_raises(self) -> None:
        """Two headers normalizing to same value raises error."""
        from elspeth.plugins.sources.field_normalization import check_normalization_collisions

        raw = ["Case Study 1", "case-study-1"]
        normalized = ["case_study_1", "case_study_1"]

        with pytest.raises(ValueError, match="collision") as exc_info:
            check_normalization_collisions(raw, normalized)

        # Error should mention both original headers
        assert "Case Study 1" in str(exc_info.value)
        assert "case-study-1" in str(exc_info.value)

    def test_three_way_collision_lists_all(self) -> None:
        """Three+ headers colliding lists all of them."""
        from elspeth.plugins.sources.field_normalization import check_normalization_collisions

        raw = ["A B", "a-b", "A  B"]
        normalized = ["a_b", "a_b", "a_b"]

        with pytest.raises(ValueError, match="collision") as exc_info:
            check_normalization_collisions(raw, normalized)

        error = str(exc_info.value)
        assert "A B" in error
        assert "a-b" in error
        assert "A  B" in error


class TestMappingCollisionDetection:
    """Tests for field_mapping collision detection."""

    def test_no_collision_passes(self) -> None:
        """No collision when mapping targets are unique."""
        from elspeth.plugins.sources.field_normalization import check_mapping_collisions

        mapping = {"user_id": "uid", "amount": "amt"}
        headers = ["user_id", "amount", "date"]
        final = ["uid", "amt", "date"]
        # Should not raise
        check_mapping_collisions(headers, final, mapping)

    def test_mapping_collision_raises(self) -> None:
        """Mapping two fields to same target raises error."""
        from elspeth.plugins.sources.field_normalization import check_mapping_collisions

        mapping = {"a": "x", "b": "x"}
        headers = ["a", "b", "c"]
        final = ["x", "x", "c"]

        with pytest.raises(ValueError, match="collision") as exc_info:
            check_mapping_collisions(headers, final, mapping)

        error = str(exc_info.value)
        assert "'a'" in error
        assert "'b'" in error
        assert "'x'" in error
```

### Step 3.2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py::TestCollisionDetection -v`
Expected: FAIL with "cannot import name 'check_normalization_collisions'"

### Step 3.3: Implement collision detection functions

Add to `field_normalization.py`:

```python
def check_normalization_collisions(raw_headers: list[str], normalized_headers: list[str]) -> None:
    """Check for collisions after normalization.

    Args:
        raw_headers: Original header names
        normalized_headers: Normalized header names (same order)

    Raises:
        ValueError: If multiple raw headers normalize to same value,
                   with ALL colliding headers and their positions listed
    """
    seen: dict[str, list[tuple[int, str]]] = {}

    for i, (raw, norm) in enumerate(zip(raw_headers, normalized_headers, strict=True)):
        seen.setdefault(norm, []).append((i, raw))

    collisions = {norm: sources for norm, sources in seen.items() if len(sources) > 1}

    if collisions:
        details = []
        for norm, sources in sorted(collisions.items()):
            source_desc = ", ".join(f"column {i} ('{raw}')" for i, raw in sources)
            details.append(f"  '{norm}' ← {source_desc}")

        raise ValueError(f"Field name collision after normalization:\n" + "\n".join(details))


def check_mapping_collisions(
    pre_mapping: list[str],
    post_mapping: list[str],
    field_mapping: dict[str, str],
) -> None:
    """Check for collisions created by field_mapping.

    Args:
        pre_mapping: Headers before mapping applied
        post_mapping: Headers after mapping applied
        field_mapping: The mapping that was applied

    Raises:
        ValueError: If mapping causes multiple fields to have same final name
    """
    if len(post_mapping) != len(set(post_mapping)):
        # Find which mapping entries caused collision
        target_counts: dict[str, list[str]] = {}
        for source, target in field_mapping.items():
            target_counts.setdefault(target, []).append(source)

        collisions = {t: s for t, s in target_counts.items() if len(s) > 1}

        if collisions:
            details = [
                f"  '{target}' ← {', '.join(repr(s) for s in sources)}"
                for target, sources in sorted(collisions.items())
            ]
            raise ValueError(f"field_mapping creates collision:\n" + "\n".join(details))
```

### Step 3.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py -v`
Expected: PASS (all tests)

### Step 3.5: Commit

```bash
git add src/elspeth/plugins/sources/field_normalization.py tests/plugins/sources/test_field_normalization.py
git commit -m "feat(sources): add collision detection for field normalization

Detects both normalization collisions (multiple headers → same name) and
mapping collisions (field_mapping creates duplicates). Error messages
list ALL colliding fields with positions."
```

---

## Task 4: Add FieldResolution Dataclass and resolve_field_names Function

**Files:**
- Modify: `src/elspeth/plugins/sources/field_normalization.py`
- Modify: `tests/plugins/sources/test_field_normalization.py`

### Step 4.1: Write failing tests for field resolution

Add new test class:

```python
class TestResolveFieldNames:
    """Tests for the complete field resolution flow."""

    def test_normalize_only(self) -> None:
        """Resolution with normalize_fields=True, no mapping."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        raw_headers = ["User ID", "Amount $"]
        result = resolve_field_names(
            raw_headers=raw_headers,
            normalize_fields=True,
            field_mapping=None,
            columns=None,
        )

        assert result.final_headers == ["user_id", "amount"]
        assert result.resolution_mapping == {
            "User ID": "user_id",
            "Amount $": "amount",
        }

    def test_normalize_with_mapping(self) -> None:
        """Resolution with normalize + mapping override."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        raw_headers = ["User ID", "Amount $"]
        result = resolve_field_names(
            raw_headers=raw_headers,
            normalize_fields=True,
            field_mapping={"user_id": "uid"},
            columns=None,
        )

        assert result.final_headers == ["uid", "amount"]
        assert result.resolution_mapping == {
            "User ID": "uid",
            "Amount $": "amount",
        }

    def test_columns_mode(self) -> None:
        """Resolution with explicit columns (headerless mode)."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        result = resolve_field_names(
            raw_headers=None,
            normalize_fields=False,
            field_mapping=None,
            columns=["id", "name", "amount"],
        )

        assert result.final_headers == ["id", "name", "amount"]
        assert result.resolution_mapping == {
            "id": "id",
            "name": "name",
            "amount": "amount",
        }

    def test_columns_with_mapping(self) -> None:
        """Resolution with columns + mapping override."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        result = resolve_field_names(
            raw_headers=None,
            normalize_fields=False,
            field_mapping={"id": "customer_id"},
            columns=["id", "name"],
        )

        assert result.final_headers == ["customer_id", "name"]
        assert result.resolution_mapping == {
            "id": "customer_id",
            "name": "name",
        }

    def test_no_normalization_passthrough(self) -> None:
        """Without normalize_fields, headers pass through unchanged."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        raw_headers = ["User ID", "Amount $"]
        result = resolve_field_names(
            raw_headers=raw_headers,
            normalize_fields=False,
            field_mapping=None,
            columns=None,
        )

        assert result.final_headers == ["User ID", "Amount $"]
        assert result.resolution_mapping == {
            "User ID": "User ID",
            "Amount $": "Amount $",
        }

    def test_mapping_key_not_found_raises(self) -> None:
        """Mapping key not in headers raises helpful error."""
        from elspeth.plugins.sources.field_normalization import resolve_field_names

        with pytest.raises(ValueError, match="not found") as exc_info:
            resolve_field_names(
                raw_headers=["user_id", "amount"],
                normalize_fields=True,
                field_mapping={"nonexistent": "x"},
                columns=None,
            )

        error = str(exc_info.value)
        assert "nonexistent" in error
        assert "user_id" in error  # Shows available headers
```

### Step 4.2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py::TestResolveFieldNames -v`
Expected: FAIL with "cannot import name 'resolve_field_names'"

### Step 4.3: Implement resolve_field_names

Add to `field_normalization.py`:

```python
from dataclasses import dataclass


@dataclass
class FieldResolution:
    """Result of field name resolution.

    Attributes:
        final_headers: List of final field names to use
        resolution_mapping: Mapping from original → final names (for audit trail)
    """

    final_headers: list[str]
    resolution_mapping: dict[str, str]


def resolve_field_names(
    *,
    raw_headers: list[str] | None,
    normalize_fields: bool,
    field_mapping: dict[str, str] | None,
    columns: list[str] | None,
) -> FieldResolution:
    """Resolve final field names from raw headers and config.

    Args:
        raw_headers: Headers from file, or None if using columns config
        normalize_fields: Whether to apply normalization algorithm
        field_mapping: Optional mapping overrides (keys are effective names)
        columns: Explicit column names for headerless mode

    Returns:
        FieldResolution with final headers and audit mapping

    Raises:
        ValueError: On collision, invalid mapping key, or configuration error
    """
    # Determine source of headers
    if columns is not None:
        # Headerless mode - use explicit columns
        original_names = columns
        effective_headers = list(columns)
    elif raw_headers is not None:
        original_names = raw_headers
        if normalize_fields:
            effective_headers = [normalize_field_name(h) for h in raw_headers]
            check_normalization_collisions(raw_headers, effective_headers)
        else:
            effective_headers = list(raw_headers)
    else:
        raise ValueError("Either raw_headers or columns must be provided")

    # Apply field mapping if provided
    if field_mapping:
        # Validate all mapping keys exist
        available = set(effective_headers)
        missing = set(field_mapping.keys()) - available
        if missing:
            raise ValueError(
                f"field_mapping keys not found in headers: {sorted(missing)}. "
                f"Available: {sorted(available)}"
            )

        # Apply mapping
        final_headers = [field_mapping.get(h, h) for h in effective_headers]

        # Check for collisions after mapping
        check_mapping_collisions(effective_headers, final_headers, field_mapping)
    else:
        final_headers = effective_headers

    # Build resolution mapping for audit trail
    resolution_mapping = dict(zip(original_names, final_headers, strict=True))

    return FieldResolution(
        final_headers=final_headers,
        resolution_mapping=resolution_mapping,
    )
```

### Step 4.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py -v`
Expected: PASS (all tests)

### Step 4.5: Commit

```bash
git add src/elspeth/plugins/sources/field_normalization.py tests/plugins/sources/test_field_normalization.py
git commit -m "feat(sources): add resolve_field_names for complete field resolution

Combines normalization, collision detection, and mapping into single
entry point. Returns FieldResolution with final_headers and
resolution_mapping for audit trail."
```

---

## Task 5: Create TabularSourceDataConfig

**Files:**
- Modify: `src/elspeth/plugins/config_base.py`
- Create: `tests/plugins/config/test_tabular_source_config.py`

### Step 5.1: Write failing tests for config validation

```python
# tests/plugins/config/test_tabular_source_config.py
"""Tests for TabularSourceDataConfig validation."""

import pytest

from elspeth.plugins.config_base import PluginConfigError


class TestTabularSourceDataConfigValidation:
    """Tests for field normalization config option validation."""

    def test_normalize_with_columns_raises(self) -> None:
        """normalize_fields=True with columns raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="cannot be used with columns"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "columns": ["a", "b"],
                "normalize_fields": True,
            })

    def test_mapping_without_normalize_or_columns_raises(self) -> None:
        """field_mapping without normalize_fields or columns raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="requires normalize_fields"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "field_mapping": {"a": "b"},
            })

    def test_columns_with_python_keyword_raises(self) -> None:
        """columns entry that is Python keyword raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="Python keyword"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "columns": ["id", "class", "name"],
            })

    def test_columns_with_invalid_identifier_raises(self) -> None:
        """columns entry that is invalid identifier raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="valid identifier"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "columns": ["id", "123_bad", "name"],
            })

    def test_columns_with_duplicates_raises(self) -> None:
        """columns with duplicate entries raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="[Dd]uplicate"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "columns": ["id", "name", "id"],
            })

    def test_field_mapping_value_is_keyword_raises(self) -> None:
        """field_mapping value that is Python keyword raises error."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        with pytest.raises(ValueError, match="Python keyword"):
            TabularSourceDataConfig.from_dict({
                "path": "/tmp/test.csv",
                "schema": {"fields": "dynamic"},
                "on_validation_failure": "quarantine",
                "normalize_fields": True,
                "field_mapping": {"user_id": "class"},
            })

    def test_valid_config_with_normalize_fields(self) -> None:
        """Valid config with normalize_fields passes."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict({
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })
        assert cfg.normalize_fields is True
        assert cfg.field_mapping is None
        assert cfg.columns is None

    def test_valid_config_with_columns(self) -> None:
        """Valid config with columns passes."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict({
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "columns": ["id", "name", "amount"],
        })
        assert cfg.columns == ["id", "name", "amount"]
        assert cfg.normalize_fields is False

    def test_valid_config_with_normalize_and_mapping(self) -> None:
        """Valid config with normalize_fields + field_mapping passes."""
        from elspeth.plugins.config_base import TabularSourceDataConfig

        cfg = TabularSourceDataConfig.from_dict({
            "path": "/tmp/test.csv",
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
            "field_mapping": {"user_id": "uid"},
        })
        assert cfg.normalize_fields is True
        assert cfg.field_mapping == {"user_id": "uid"}
```

### Step 5.2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/plugins/config/test_tabular_source_config.py -v`
Expected: FAIL with "cannot import name 'TabularSourceDataConfig'"

### Step 5.3: Implement TabularSourceDataConfig

Add to `config_base.py` after `SourceDataConfig`:

```python
from typing import Self  # Add to existing imports at top of file

from elspeth.plugins.sources.field_normalization import validate_field_names  # Import helper


class TabularSourceDataConfig(SourceDataConfig):
    """Config for sources that read tabular external data with headers.

    Extends SourceDataConfig with field normalization options:
    - columns: Explicit column names for headerless files
    - normalize_fields: Auto-normalize messy headers to identifiers
    - field_mapping: Override specific normalized names

    See docs/plans/2026-01-29-field-normalization-design.md for full specification.
    """

    columns: list[str] | None = None
    normalize_fields: bool = False
    field_mapping: dict[str, str] | None = None

    @model_validator(mode="after")
    def _validate_normalization_options(self) -> Self:
        """Validate field normalization option interactions."""
        # normalize_fields + columns is invalid
        if self.columns is not None and self.normalize_fields:
            raise ValueError(
                "normalize_fields cannot be used with columns config. "
                "The columns config already provides clean names."
            )

        # field_mapping requires normalize_fields or columns
        if self.field_mapping is not None and not self.normalize_fields and self.columns is None:
            raise ValueError(
                "field_mapping requires normalize_fields: true or columns config"
            )

        # Validate columns entries are valid identifiers and not keywords
        if self.columns is not None:
            validate_field_names(self.columns, "columns")

        # Validate field_mapping values are valid identifiers and not keywords
        if self.field_mapping is not None:
            validate_field_names(list(self.field_mapping.values()), "field_mapping values")

        return self
```

**Also add validate_field_names to field_normalization.py:**

```python
def validate_field_names(names: list[str], context: str) -> None:
    """Validate field names are valid identifiers and not keywords.

    Args:
        names: List of field names to validate
        context: Description for error messages (e.g., "columns", "field_mapping values")

    Raises:
        ValueError: If any name is invalid
    """
    seen: set[str] = set()
    for i, name in enumerate(names):
        if not name.isidentifier():
            raise ValueError(f"{context}[{i}] '{name}' is not a valid Python identifier")
        if keyword.iskeyword(name):
            raise ValueError(f"{context}[{i}] '{name}' is a Python keyword")
        if name in seen:
            raise ValueError(f"Duplicate field name '{name}' in {context}")
        seen.add(name)
```

### Step 5.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/config/test_tabular_source_config.py -v`
Expected: PASS (all tests)

### Step 5.5: Commit

```bash
git add src/elspeth/plugins/config_base.py src/elspeth/plugins/sources/field_normalization.py tests/plugins/config/test_tabular_source_config.py
git commit -m "feat(config): add TabularSourceDataConfig with normalization options

Adds columns, normalize_fields, and field_mapping config options with
Pydantic validation for option interactions, Python keyword detection,
and duplicate checking. Validation helper imported from field_normalization."
```

---

## Task 6: Update CSVSource to Use Field Normalization

**Files:**
- Modify: `src/elspeth/plugins/sources/csv_source.py`
- Modify: `tests/plugins/sources/test_csv_source.py`

### Step 6.1: Write failing integration tests

Add new test class to `test_csv_source.py`:

```python
class TestCSVSourceFieldNormalization:
    """Integration tests for CSV source with field normalization."""

    @pytest.fixture
    def ctx(self) -> PluginContext:
        """Create a minimal plugin context."""
        return PluginContext(run_id="test-run", config={})

    def test_normalize_fields_transforms_headers(self, tmp_path: Path, ctx: PluginContext) -> None:
        """normalize_fields=True transforms messy headers to identifiers."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "messy.csv"
        csv_file.write_text("User ID,Amount $,Data.Field\n1,100,foo\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        rows = list(source.load(ctx))
        assert len(rows) == 1
        row = rows[0].row
        assert row == {"user_id": "1", "amount": "100", "data_field": "foo"}

    def test_normalize_with_mapping_overrides(self, tmp_path: Path, ctx: PluginContext) -> None:
        """field_mapping overrides normalized names."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "messy.csv"
        csv_file.write_text("User ID,Amount\n1,100\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
            "field_mapping": {"user_id": "uid"},
        })

        rows = list(source.load(ctx))
        assert len(rows) == 1
        assert rows[0].row == {"uid": "1", "amount": "100"}

    def test_columns_mode_headerless_file(self, tmp_path: Path, ctx: PluginContext) -> None:
        """columns config works with headerless CSV."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "headerless.csv"
        csv_file.write_text("1,alice,100\n2,bob,200\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "columns": ["id", "name", "amount"],
        })

        rows = list(source.load(ctx))
        assert len(rows) == 2
        assert rows[0].row == {"id": "1", "name": "alice", "amount": "100"}
        assert rows[1].row == {"id": "2", "name": "bob", "amount": "200"}

    def test_collision_raises_at_load(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Header collision detected at load() start."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "collision.csv"
        csv_file.write_text("User ID,user-id,data\n1,2,3\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        with pytest.raises(ValueError, match="collision"):
            list(source.load(ctx))

    def test_field_resolution_stored_for_audit(self, tmp_path: Path, ctx: PluginContext) -> None:
        """field_resolution is stored on source for audit trail."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "messy.csv"
        csv_file.write_text("User ID,Amount\n1,100\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
            "field_mapping": {"user_id": "uid"},
        })

        # Must call load() to trigger resolution
        list(source.load(ctx))

        assert hasattr(source, "_field_resolution")
        assert source._field_resolution == {
            "User ID": "uid",
            "Amount": "amount",
        }

    # P0 Tests - Added per review board requirements

    def test_empty_csv_file_returns_no_rows(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Empty CSV file returns no rows without error."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        rows = list(source.load(ctx))
        assert len(rows) == 0

    def test_header_only_csv_returns_no_rows(self, tmp_path: Path, ctx: PluginContext) -> None:
        """CSV with only headers returns no rows."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "header_only.csv"
        csv_file.write_text("User ID,Amount\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        rows = list(source.load(ctx))
        assert len(rows) == 0

    def test_columns_fewer_than_data_raises(self, tmp_path: Path, ctx: PluginContext) -> None:
        """columns config with fewer columns than data raises clear error."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "wide.csv"
        csv_file.write_text("1,alice,100,extra\n")  # 4 values

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "columns": ["id", "name", "amount"],  # Only 3 columns
        })

        with pytest.raises(ValueError, match="column.*count.*mismatch|expected.*3.*got.*4"):
            list(source.load(ctx))

    def test_columns_more_than_data_raises(self, tmp_path: Path, ctx: PluginContext) -> None:
        """columns config with more columns than data raises clear error."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "narrow.csv"
        csv_file.write_text("1,alice\n")  # 2 values

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "columns": ["id", "name", "amount"],  # 3 columns
        })

        with pytest.raises(ValueError, match="column.*count.*mismatch|expected.*3.*got.*2"):
            list(source.load(ctx))

    def test_audit_trail_contains_resolution_mapping(self, tmp_path: Path, ctx: PluginContext) -> None:
        """Audit trail includes complete field resolution mapping."""
        from elspeth.plugins.sources.csv_source import CSVSource

        csv_file = tmp_path / "audit.csv"
        csv_file.write_text("CaSE Study1 !!!! xx!,Amount $\nfoo,100\n")

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        list(source.load(ctx))

        # Verify the resolution mapping is available for audit
        assert source._field_resolution is not None
        assert "CaSE Study1 !!!! xx!" in source._field_resolution
        assert source._field_resolution["CaSE Study1 !!!! xx!"] == "case_study1_xx"
        assert source._field_resolution["Amount $"] == "amount"
```

### Step 6.2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py::TestCSVSourceFieldNormalization -v`
Expected: FAIL with "Extra inputs are not permitted" (CSVSource doesn't accept normalize_fields yet)

### Step 6.3: Update CSVSourceConfig and CSVSource

Update `csv_source.py`:

```python
# Change import
from elspeth.plugins.config_base import TabularSourceDataConfig

# Change config class to inherit from TabularSourceDataConfig
class CSVSourceConfig(TabularSourceDataConfig):
    """Configuration for CSV source plugin.

    Inherits from TabularSourceDataConfig, which provides:
    - schema and on_validation_failure (from SourceDataConfig)
    - columns, normalize_fields, field_mapping (field normalization)
    """

    delimiter: str = ","
    encoding: str = "utf-8"
    skip_rows: int = 0


# In CSVSource.__init__, store config for use in load():
class CSVSource(BaseSource):
    # ... existing code ...

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = CSVSourceConfig.from_dict(config)

        self._path = cfg.resolved_path()
        self._delimiter = cfg.delimiter
        self._encoding = cfg.encoding
        self._skip_rows = cfg.skip_rows

        # Store normalization config for use in load()
        self._columns = cfg.columns
        self._normalize_fields = cfg.normalize_fields
        self._field_mapping = cfg.field_mapping

        # Field resolution computed at load() time
        self._field_resolution: dict[str, str] | None = None

        # ... rest of existing __init__ ...
```

Update `load()` method to use field resolution:

```python
from elspeth.plugins.sources.field_normalization import resolve_field_names

def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    """Load rows from CSV file with optional field normalization."""
    if not self._path.exists():
        raise FileNotFoundError(f"CSV file not found: {self._path}")

    with open(self._path, encoding=self._encoding, newline="") as f:
        for _ in range(self._skip_rows):
            next(f, None)

        reader = csv.reader(f, delimiter=self._delimiter)

        # Determine headers based on config
        if self._columns is not None:
            # Headerless mode - use explicit columns
            raw_headers = None
        else:
            # Read header row from file
            try:
                raw_headers = next(reader)
            except StopIteration:
                return  # Empty file

        # Resolve field names (normalization + mapping)
        resolution = resolve_field_names(
            raw_headers=raw_headers,
            normalize_fields=self._normalize_fields,
            field_mapping=self._field_mapping,
            columns=self._columns,
        )
        headers = resolution.final_headers
        self._field_resolution = resolution.resolution_mapping

        # Yield rows with resolved headers
        expected_count = len(headers)
        for row_num, values in enumerate(reader, start=1):
            # Validate column count in headerless mode
            if self._columns is not None and len(values) != expected_count:
                raise ValueError(
                    f"Row {row_num}: column count mismatch - "
                    f"expected {expected_count}, got {len(values)}"
                )
            row = dict(zip(headers, values, strict=False))
            yield SourceRow(row=row, source_meta={"row_number": row_num})
```

### Step 6.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py -v`
Expected: PASS (all tests including existing ones)

### Step 6.5: Commit

```bash
git add src/elspeth/plugins/sources/csv_source.py tests/plugins/sources/test_csv_source.py
git commit -m "feat(csv): integrate field normalization into CSVSource

CSVSourceConfig now inherits TabularSourceDataConfig. Field resolution
happens at start of load(), storing resolution_mapping for audit trail.
Column count validation added for headerless mode."
```

---

## Task 7: Add Template Field Validation to LLM Transforms

**CRITICAL**: This task prevents the "Fixes that Fail" archetype where normalization silently breaks templates.

**Files:**
- Modify: `src/elspeth/plugins/llm/base.py`
- Create: `tests/plugins/llm/test_template_field_validation.py`

### Step 7.1: Write failing test for template validation

```python
# tests/plugins/llm/test_template_field_validation.py
"""Tests for template field validation against schema."""

import pytest

from elspeth.plugins.config_base import PluginConfigError


class TestTemplateFieldValidation:
    """Tests that template field references are validated against schema."""

    def test_template_references_guaranteed_field_passes(self) -> None:
        """Template referencing a guaranteed field passes validation."""
        from elspeth.plugins.llm.base import LLMConfig

        # This should not raise - template references 'user_id' which is guaranteed
        config = LLMConfig.from_dict({
            "model": "gpt-4",
            "template": "Hello {{ row.user_id }}",
            "required_input_fields": ["user_id"],
            "schema": {
                "fields": {
                    "user_id": {"type": "string"},
                },
                "guaranteed_fields": ["user_id"],
            },
        })
        assert config.template == "Hello {{ row.user_id }}"

    def test_template_references_non_guaranteed_field_raises(self) -> None:
        """Template referencing field not in guaranteed_fields raises error."""
        from elspeth.plugins.llm.base import LLMConfig

        # Template references 'customer_name' but it's not in guaranteed_fields
        with pytest.raises(ValueError, match="customer_name.*not guaranteed"):
            LLMConfig.from_dict({
                "model": "gpt-4",
                "template": "Hello {{ row.customer_name }}",
                "required_input_fields": ["customer_name"],
                "schema": {
                    "fields": {
                        "customer_id": {"type": "string"},
                    },
                    "guaranteed_fields": ["customer_id"],
                },
            })

    def test_template_references_unnormalized_name_suggests_fix(self) -> None:
        """Error message suggests normalized name when template uses old name."""
        from elspeth.plugins.llm.base import LLMConfig

        # Template uses "User ID" (unnormalized) but schema has "user_id" (normalized)
        with pytest.raises(ValueError) as exc_info:
            LLMConfig.from_dict({
                "model": "gpt-4",
                "template": "Hello {{ row['User ID'] }}",
                "required_input_fields": ["User ID"],  # User incorrectly declared old name
                "schema": {
                    "fields": {
                        "user_id": {"type": "string"},  # Normalized name
                    },
                    "guaranteed_fields": ["user_id"],
                },
            })

        error = str(exc_info.value)
        # Should suggest the normalized name
        assert "user_id" in error.lower() or "normalized" in error.lower()

    def test_dynamic_schema_skips_validation(self) -> None:
        """Templates with dynamic schema skip field validation."""
        from elspeth.plugins.llm.base import LLMConfig

        # Dynamic schema = accept any fields, no validation
        config = LLMConfig.from_dict({
            "model": "gpt-4",
            "template": "Hello {{ row.anything_goes }}",
            "required_input_fields": ["anything_goes"],
            "schema": {"fields": "dynamic"},
        })
        assert config.template == "Hello {{ row.anything_goes }}"

    def test_template_with_multiple_fields_validates_all(self) -> None:
        """All template field references are validated."""
        from elspeth.plugins.llm.base import LLMConfig

        # Template references both 'name' (guaranteed) and 'missing' (not guaranteed)
        with pytest.raises(ValueError, match="missing.*not guaranteed"):
            LLMConfig.from_dict({
                "model": "gpt-4",
                "template": "Hello {{ row.name }}, your ID is {{ row.missing }}",
                "required_input_fields": ["name", "missing"],
                "schema": {
                    "fields": {
                        "name": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    "guaranteed_fields": ["name", "id"],
                },
            })
```

### Step 7.2: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_template_field_validation.py -v`
Expected: FAIL with assertion errors (validation doesn't exist yet)

### Step 7.3: Add template validation to LLMConfig

Modify `src/elspeth/plugins/llm/base.py` - add a new model validator:

```python
@model_validator(mode="after")
def _validate_template_fields_against_schema(self) -> LLMConfig:
    """Validate template field references exist in schema's guaranteed_fields.

    This prevents the "Fixes that Fail" archetype where:
    1. Source normalizes headers (e.g., "User ID" → "user_id")
    2. Template still references old name (e.g., {{ row['User ID'] }})
    3. Runtime fails silently or with confusing KeyError

    By validating at config time, we catch template/schema mismatches early.
    """
    # Skip validation for dynamic schema
    if self.schema_config is None:
        return self
    if self.schema_config.fields == "dynamic":
        return self

    # Get guaranteed fields from schema
    guaranteed = set(self.schema_config.guaranteed_fields or [])
    if not guaranteed:
        # No guaranteed fields declared - can't validate
        return self

    # Get fields referenced in template
    from elspeth.core.templates import extract_jinja2_fields
    template_fields = extract_jinja2_fields(self.template)

    # Check each template field is guaranteed
    missing = template_fields - guaranteed
    if missing:
        # Try to provide helpful suggestions for normalized names
        suggestions = []
        for field in sorted(missing):
            # Check if a normalized version exists in guaranteed
            from elspeth.plugins.sources.field_normalization import normalize_field_name
            try:
                normalized = normalize_field_name(field)
                if normalized in guaranteed:
                    suggestions.append(f"  '{field}' → did you mean '{normalized}'?")
                else:
                    suggestions.append(f"  '{field}' - not in guaranteed_fields")
            except ValueError:
                suggestions.append(f"  '{field}' - not in guaranteed_fields")

        raise ValueError(
            f"Template references fields not guaranteed by schema:\n"
            + "\n".join(suggestions)
            + f"\n\nGuaranteed fields: {sorted(guaranteed)}"
        )

    return self
```

### Step 7.4: Run tests to verify they pass

Run: `.venv/bin/python -m pytest tests/plugins/llm/test_template_field_validation.py -v`
Expected: PASS (all tests)

### Step 7.5: Commit

```bash
git add src/elspeth/plugins/llm/base.py tests/plugins/llm/test_template_field_validation.py
git commit -m "feat(llm): add template field validation against schema

Validates at config time that template field references ({{ row.field }})
exist in schema's guaranteed_fields. Prevents 'Fixes that Fail' archetype
where normalization breaks templates referencing old field names.

Provides helpful suggestions when normalized name is available."
```

---

## Task 8: Run Full Test Suite and Type Check

**Files:** None (verification only)

### Step 8.1: Run full test suite

Run: `.venv/bin/python -m pytest tests/ -v --tb=short`
Expected: PASS (all tests)

### Step 8.2: Run type checker

Run: `.venv/bin/python -m mypy src/elspeth/plugins/sources/field_normalization.py src/elspeth/plugins/config_base.py src/elspeth/plugins/llm/base.py`
Expected: PASS (no type errors)

### Step 8.3: Run linter

Run: `.venv/bin/python -m ruff check src/elspeth/plugins/sources/field_normalization.py src/elspeth/plugins/config_base.py src/elspeth/plugins/llm/base.py`
Expected: PASS (no lint errors)

### Step 8.4: Commit any fixes if needed

```bash
git add -A
git commit -m "fix: address type/lint issues from full test run"
```

---

## Task 9: Update Azure Blob Source (If Time Permits)

**Files:**
- Modify: `src/elspeth/plugins/azure/blob_source.py`
- Test: `tests/plugins/azure/test_blob_source.py`

This task follows the same pattern as Task 6. The Azure blob source reads CSV data from Azure Blob Storage and should support the same normalization options.

### Step 9.1: Update config class to inherit TabularSourceDataConfig

### Step 9.2: Apply field resolution when reading CSV data

### Step 9.3: Add integration tests

### Step 9.4: Commit

---

## Task 10: Update JSONSource (MVP+1 - DEFERRED)

**Status:** DEFERRED to MVP+1

**Rationale:** JSON normalization has design gaps that need resolution:
- CSV has a header row processed once; JSON normalizes per-row (performance)
- JSON objects can have inconsistent keys across rows (validation complexity)
- Need to decide: validate key consistency, or normalize opportunistically?

**When to implement:** After CSV normalization is proven in production and we have real-world JSON requirements.

**Files (when ready):**
- Modify: `src/elspeth/plugins/sources/json_source.py`
- Modify: `tests/plugins/sources/test_json_source.py`

---

## Summary

| Task | Description | Commits | Status |
|------|-------------|---------|--------|
| 1 | Create field_normalization.py with core algorithm | 1 | MVP |
| 2 | Add P0 Unicode and keyword tests | 1 | MVP |
| 3 | Add collision detection functions | 1 | MVP |
| 4 | Add resolve_field_names function | 1 | MVP |
| 5 | Create TabularSourceDataConfig | 1 | MVP |
| 6 | Update CSVSource with P0 tests | 1 | MVP |
| 7 | Add template field validation (CRITICAL) | 1 | MVP |
| 8 | Full test suite verification | 0-1 | MVP |
| 9 | Update Azure Blob Source | 1 | Optional |
| 10 | Update JSONSource | 1 | **DEFERRED** |

**Total MVP: ~7-8 commits**

---

## Post-Implementation

After completing all MVP tasks:

1. Update the design doc status to "Implemented"
2. Close any related bug tracking issues
3. Document JSON normalization requirements for MVP+1 planning
