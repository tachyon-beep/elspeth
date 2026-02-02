# Phase 4: Template Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Jinja2 templates to reference fields by either original or normalized names, resolving them at render time via SchemaContract, while maintaining audit trail integrity and development helper functionality.

**Architecture:** The `PromptTemplate` class will accept an optional `SchemaContract` that enables dual-name resolution. Templates can use `{{ row["'Amount USD'"] }}` (original) or `{{ row.amount_usd }}` (normalized) interchangeably. A `ContractAwareRow` wrapper provides the resolution layer, while `extract_jinja2_fields()` is enhanced to report both name forms.

**Tech Stack:** Python 3.11+, Jinja2 (existing), `SchemaContract` and `PipelineRow` from Phase 1-3, existing `PromptTemplate` infrastructure.

**Design Doc:** `docs/plans/2026-02-02-unified-schema-contracts-design.md`

**Depends On:** Phase 1 (Core Contracts), Phase 2 (Source Integration), Phase 3 (Transform/Sink Integration)

---

## Overview

Phase 4 enables "write what you mean" templates:

```
Current (normalized only):          Phase 4 (dual-name):
{{ row.amount_usd }}                {{ row["'Amount USD'"] }}  ← Original
{{ row["amount_usd"] }}             {{ row.amount_usd }}       ← Normalized
                                    Both resolve to same field!
```

Key changes:
1. **ContractAwareRow**: Wrapper class that intercepts Jinja2 attribute/item access
2. **PromptTemplate.with_contract()**: Factory for contract-aware rendering
3. **Enhanced field extraction**: Report original names alongside normalized
4. **Audit trail preservation**: Hash computed on normalized data (deterministic)

---

## Task 1: ContractAwareRow Wrapper

**Files:**
- Create: `src/elspeth/plugins/llm/contract_aware_row.py`
- Test: `tests/plugins/llm/test_contract_aware_row.py` (create new)

**Step 1.1: Write failing tests for ContractAwareRow**

```python
# tests/plugins/llm/test_contract_aware_row.py
"""Tests for ContractAwareRow - enables dual-name access in Jinja2 templates."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.llm.contract_aware_row import ContractAwareRow


class TestContractAwareRow:
    """Test dual-name access via ContractAwareRow."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
                FieldContract("simple", "simple", str, True, "declared"),
            ),
            locked=True,
        )

    @pytest.fixture
    def data(self) -> dict[str, object]:
        """Row data with normalized keys."""
        return {
            "amount_usd": 100,
            "customer_id": "C001",
            "simple": "value",
        }

    def test_access_by_normalized_name(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Access by normalized name works."""
        row = ContractAwareRow(data, contract)

        assert row["amount_usd"] == 100
        assert row["customer_id"] == "C001"

    def test_access_by_original_name(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Access by original name works."""
        row = ContractAwareRow(data, contract)

        assert row["'Amount USD'"] == 100
        assert row["Customer ID"] == "C001"

    def test_access_by_attribute(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Dot notation access works for normalized names."""
        row = ContractAwareRow(data, contract)

        assert row.amount_usd == 100
        assert row.customer_id == "C001"

    def test_contains_normalized(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """'in' operator works with normalized names."""
        row = ContractAwareRow(data, contract)

        assert "amount_usd" in row
        assert "customer_id" in row
        assert "nonexistent" not in row

    def test_contains_original(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """'in' operator works with original names."""
        row = ContractAwareRow(data, contract)

        assert "'Amount USD'" in row
        assert "Customer ID" in row

    def test_keys_returns_normalized(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """keys() returns normalized names for iteration."""
        row = ContractAwareRow(data, contract)

        keys = list(row.keys())

        assert "amount_usd" in keys
        assert "'Amount USD'" not in keys  # Normalized only

    def test_missing_field_raises_keyerror(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Unknown field raises KeyError."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(KeyError, match="nonexistent"):
            _ = row["nonexistent"]

    def test_missing_attr_raises_attributeerror(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Unknown attribute raises AttributeError."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(AttributeError, match="nonexistent"):
            _ = row.nonexistent

    def test_private_attr_raises_attributeerror(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Private attributes raise AttributeError (not delegated)."""
        row = ContractAwareRow(data, contract)

        with pytest.raises(AttributeError):
            _ = row._private

    def test_get_with_default(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """get() method supports default values."""
        row = ContractAwareRow(data, contract)

        assert row.get("amount_usd") == 100
        assert row.get("'Amount USD'") == 100
        assert row.get("nonexistent", "default") == "default"
        assert row.get("nonexistent") is None

    def test_iteration_yields_normalized_keys(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Iteration yields normalized keys."""
        row = ContractAwareRow(data, contract)

        keys = list(row)

        assert set(keys) == {"amount_usd", "customer_id", "simple"}
```

**Step 1.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_contract_aware_row.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.plugins.llm.contract_aware_row'`

**Step 1.3: Implement ContractAwareRow**

```python
# src/elspeth/plugins/llm/contract_aware_row.py
"""Contract-aware row wrapper for dual-name template access.

Enables Jinja2 templates to reference fields by either original or
normalized names, with O(1) resolution via SchemaContract.

This class is designed to be passed as the 'row' context variable
to Jinja2 templates, providing transparent name resolution.

Example:
    contract = SchemaContract(...)  # Has "'Amount USD'" -> "amount_usd"
    data = {"amount_usd": 100}
    row = ContractAwareRow(data, contract)

    # In template:
    {{ row["'Amount USD'"] }}  # Works - resolves to amount_usd
    {{ row.amount_usd }}       # Works - direct access
    {{ row["amount_usd"] }}    # Works - normalized name
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from elspeth.contracts.schema_contract import SchemaContract


class ContractAwareRow:
    """Row wrapper enabling dual-name access via SchemaContract.

    Intercepts __getitem__ and __getattr__ to resolve original or
    normalized field names to the underlying normalized data.

    Uses __slots__ for memory efficiency (no __dict__ per instance).
    This is important since we create one per row rendered.

    Attributes:
        _data: Underlying row data (normalized keys)
        _contract: Schema contract for name resolution
    """

    __slots__ = ("_data", "_contract")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        """Initialize ContractAwareRow.

        Args:
            data: Row data with normalized field names as keys
            contract: Schema contract for dual-name resolution
        """
        self._data = data
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        """Access field by original OR normalized name.

        Args:
            key: Field name (either form)

        Returns:
            Field value

        Raises:
            KeyError: If field not found in contract or data
        """
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    def __getattr__(self, key: str) -> Any:
        """Dot notation access: row.field_name.

        Only works for normalized names (Python identifiers).
        Original names with special characters must use bracket notation.

        Args:
            key: Normalized field name

        Returns:
            Field value

        Raises:
            AttributeError: If field not found or is private
        """
        # Private attributes should not be delegated
        if key.startswith("_"):
            raise AttributeError(key)

        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __contains__(self, key: str) -> bool:
        """Check if field exists (by either name form).

        Args:
            key: Field name (original or normalized)

        Returns:
            True if field exists in contract
        """
        try:
            self._contract.resolve_name(key)
            return True
        except KeyError:
            return False

    def __iter__(self) -> Iterator[str]:
        """Iterate over normalized field names.

        Yields:
            Normalized field names (for Jinja2 iteration)
        """
        return iter(self._data)

    def keys(self) -> list[str]:
        """Return normalized field names.

        Returns:
            List of normalized field names
        """
        return list(self._data.keys())

    def get(self, key: str, default: Any = None) -> Any:
        """Get field value with optional default.

        Supports dual-name resolution like __getitem__.

        Args:
            key: Field name (original or normalized)
            default: Value to return if field not found

        Returns:
            Field value or default
        """
        try:
            return self[key]
        except KeyError:
            return default

    @property
    def contract(self) -> SchemaContract:
        """Access the schema contract (for introspection)."""
        return self._contract

    def to_dict(self) -> dict[str, Any]:
        """Export raw data (normalized keys) for hashing.

        Returns:
            Copy of underlying data dict
        """
        return dict(self._data)
```

**Step 1.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_contract_aware_row.py -v
```

Expected: All tests PASS

**Step 1.5: Commit**

```bash
git add src/elspeth/plugins/llm/contract_aware_row.py tests/plugins/llm/test_contract_aware_row.py
git commit -m "feat(llm): add ContractAwareRow for dual-name template access

Wrapper class that enables Jinja2 templates to reference fields by
either original or normalized names via SchemaContract resolution.

- __getitem__ resolves both name forms
- __getattr__ for dot notation (normalized only)
- __contains__ for 'in' operator
- get() with default value support
- keys() and iteration return normalized names

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Jinja2 Template Integration Tests

**Files:**
- Test: `tests/plugins/llm/test_contract_aware_template.py` (create new)

**Step 2.1: Write failing tests for template rendering with contracts**

```python
# tests/plugins/llm/test_contract_aware_template.py
"""Tests for Jinja2 template rendering with contract-aware row access."""

import pytest
from jinja2 import Environment, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.llm.contract_aware_row import ContractAwareRow


class TestJinja2Integration:
    """Test ContractAwareRow works correctly with Jinja2."""

    @pytest.fixture
    def env(self) -> SandboxedEnvironment:
        """Sandboxed Jinja2 environment."""
        return SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with various original names."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_name", "Customer Name", str, True, "declared"),
                FieldContract("order_id", "ORDER-ID", str, True, "declared"),
            ),
            locked=True,
        )

    @pytest.fixture
    def data(self) -> dict[str, object]:
        """Sample row data."""
        return {
            "amount_usd": 100,
            "customer_name": "Alice",
            "order_id": "ORD-001",
        }

    def test_render_with_normalized_dot_access(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with normalized dot access renders correctly."""
        row = ContractAwareRow(data, contract)
        template = env.from_string("Amount: {{ row.amount_usd }}")

        result = template.render(row=row)

        assert result == "Amount: 100"

    def test_render_with_normalized_bracket_access(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with normalized bracket access renders correctly."""
        row = ContractAwareRow(data, contract)
        template = env.from_string('Amount: {{ row["amount_usd"] }}')

        result = template.render(row=row)

        assert result == "Amount: 100"

    def test_render_with_original_bracket_access(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with original name bracket access renders correctly."""
        row = ContractAwareRow(data, contract)
        template = env.from_string("Amount: {{ row[\"'Amount USD'\"] }}")

        result = template.render(row=row)

        assert result == "Amount: 100"

    def test_render_mixed_access_styles(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template mixing access styles renders correctly."""
        row = ContractAwareRow(data, contract)
        template = env.from_string(
            "Customer {{ row.customer_name }} ordered {{ row[\"'Amount USD'\"] }} ({{ row[\"ORDER-ID\"] }})"
        )

        result = template.render(row=row)

        assert result == "Customer Alice ordered 100 (ORD-001)"

    def test_render_with_conditional(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with conditional on original name works."""
        row = ContractAwareRow(data, contract)
        template = env.from_string(
            "{% if row[\"'Amount USD'\"] > 50 %}High value{% else %}Low value{% endif %}"
        )

        result = template.render(row=row)

        assert result == "High value"

    def test_render_with_loop_over_keys(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template iterating over row keys yields normalized names."""
        row = ContractAwareRow(data, contract)
        template = env.from_string("{% for k in row %}{{ k }},{% endfor %}")

        result = template.render(row=row)

        # Order may vary, but should be normalized names
        assert "amount_usd" in result
        assert "'Amount USD'" not in result

    def test_render_with_in_operator(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with 'in' operator works with both name forms."""
        row = ContractAwareRow(data, contract)

        # Check normalized name
        template1 = env.from_string("{% if 'amount_usd' in row %}YES{% endif %}")
        assert template1.render(row=row) == "YES"

        # Check original name
        template2 = env.from_string("{% if \"'Amount USD'\" in row %}YES{% endif %}")
        assert template2.render(row=row) == "YES"

    def test_undefined_field_raises(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template accessing undefined field raises UndefinedError."""
        from jinja2 import UndefinedError

        row = ContractAwareRow(data, contract)
        template = env.from_string("{{ row.nonexistent }}")

        with pytest.raises(UndefinedError):
            template.render(row=row)

    def test_get_with_default_in_template(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template using get() with default works."""
        row = ContractAwareRow(data, contract)
        template = env.from_string("{{ row.get('nonexistent', 'N/A') }}")

        result = template.render(row=row)

        assert result == "N/A"

    def test_filter_on_resolved_value(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Jinja2 filters work on resolved values."""
        row = ContractAwareRow(data, contract)
        template = env.from_string("{{ row['Customer Name'] | upper }}")

        result = template.render(row=row)

        assert result == "ALICE"
```

**Step 2.2: Run tests to verify they pass**

These tests should pass with the ContractAwareRow implementation from Task 1.

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_contract_aware_template.py -v
```

Expected: All tests PASS

**Step 2.3: Commit**

```bash
git add tests/plugins/llm/test_contract_aware_template.py
git commit -m "test(llm): add Jinja2 integration tests for ContractAwareRow

Verify dual-name access works correctly with Jinja2:
- Dot notation (normalized only)
- Bracket notation (both forms)
- Mixed access styles
- Conditionals, loops, filters
- 'in' operator with both name forms
- get() with defaults

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: PromptTemplate Contract Support

**Files:**
- Modify: `src/elspeth/plugins/llm/templates.py`
- Test: `tests/plugins/llm/test_prompt_template_contract.py` (create new)

**Step 3.1: Write failing tests for contract-aware PromptTemplate**

```python
# tests/plugins/llm/test_prompt_template_contract.py
"""Tests for PromptTemplate with SchemaContract support."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.llm.templates import PromptTemplate, RenderedPrompt


class TestPromptTemplateWithContract:
    """Test PromptTemplate with contract-aware rendering."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_name", "Customer Name", str, True, "declared"),
            ),
            locked=True,
        )

    @pytest.fixture
    def data(self) -> dict[str, object]:
        """Sample row data."""
        return {
            "amount_usd": 100,
            "customer_name": "Alice",
        }

    def test_render_with_contract_normalized(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Contract-aware render works with normalized names."""
        template = PromptTemplate("Amount: {{ row.amount_usd }}")

        result = template.render(data, contract=contract)

        assert result == "Amount: 100"

    def test_render_with_contract_original(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Contract-aware render works with original names."""
        template = PromptTemplate("Amount: {{ row[\"'Amount USD'\"] }}")

        result = template.render(data, contract=contract)

        assert result == "Amount: 100"

    def test_render_without_contract_still_works(
        self, data: dict[str, object]
    ) -> None:
        """Render without contract works (backwards compatible)."""
        template = PromptTemplate("Amount: {{ row.amount_usd }}")

        result = template.render(data)  # No contract

        assert result == "Amount: 100"

    def test_render_with_metadata_preserves_hash_stability(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Hash is computed from normalized data (deterministic)."""
        template = PromptTemplate("{{ row.amount_usd }}")

        # Render with original name access
        result1 = template.render_with_metadata(data, contract=contract)

        # Render with normalized name access (same template different style)
        template2 = PromptTemplate("{{ row['amount_usd'] }}")
        result2 = template2.render_with_metadata(data, contract=contract)

        # Same data = same variables_hash
        assert result1.variables_hash == result2.variables_hash

    def test_render_with_metadata_includes_contract_hash(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Rendered metadata includes contract hash when provided."""
        template = PromptTemplate("{{ row.amount_usd }}")

        result = template.render_with_metadata(data, contract=contract)

        assert isinstance(result, RenderedPrompt)
        assert result.contract_hash is not None

    def test_render_with_metadata_no_contract_hash_when_none(
        self, data: dict[str, object]
    ) -> None:
        """Rendered metadata has no contract hash when contract not provided."""
        template = PromptTemplate("{{ row.amount_usd }}")

        result = template.render_with_metadata(data)  # No contract

        assert result.contract_hash is None

    def test_mixed_access_in_complex_template(
        self, data: dict[str, object], contract: SchemaContract
    ) -> None:
        """Complex template with mixed access styles works."""
        template = PromptTemplate("""
Customer: {{ row['Customer Name'] }}
Amount: {{ row.amount_usd }}
High value: {% if row["'Amount USD'"] > 50 %}YES{% else %}NO{% endif %}
""")

        result = template.render(data, contract=contract)

        assert "Customer: Alice" in result
        assert "Amount: 100" in result
        assert "High value: YES" in result

    def test_original_name_not_in_data_uses_contract(
        self, contract: SchemaContract
    ) -> None:
        """Original name access works even though data has normalized keys."""
        # Data has normalized keys only
        data = {"amount_usd": 100, "customer_name": "Bob"}

        template = PromptTemplate("{{ row[\"'Amount USD'\"] }}")

        # Without contract, this would fail
        result = template.render(data, contract=contract)

        assert result == "100"
```

**Step 3.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_prompt_template_contract.py -v
```

Expected: FAIL (PromptTemplate.render doesn't accept contract parameter)

**Step 3.3: Update PromptTemplate to support contracts**

In `src/elspeth/plugins/llm/templates.py`, update the class:

First, add import at top:

```python
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.plugins.llm.contract_aware_row import ContractAwareRow
```

Update the `RenderedPrompt` dataclass to add contract_hash field:

```python
@dataclass(frozen=True)
class RenderedPrompt:
    """A rendered prompt with audit metadata."""

    prompt: str
    template_hash: str
    variables_hash: str
    rendered_hash: str
    # File sources for audit trail
    template_source: str | None = None
    lookup_hash: str | None = None
    lookup_source: str | None = None
    # Contract hash for Phase 4+ (dual-name templates)
    contract_hash: str | None = None
```

Update the `render` method:

```python
def render(
    self,
    row: dict[str, Any],
    *,
    contract: SchemaContract | None = None,
) -> str:
    """Render template with row data.

    Args:
        row: Row data (accessed as row.* in template)
        contract: Optional schema contract for dual-name resolution.
            If provided, templates can use original names like
            {{ row["'Amount USD'"] }} in addition to normalized names.

    Returns:
        Rendered prompt string

    Raises:
        TemplateError: If rendering fails (undefined variable, sandbox violation, etc.)
    """
    # Wrap row for dual-name access if contract provided
    if contract is not None:
        row_context: Any = ContractAwareRow(row, contract)
    else:
        row_context = row

    # Build context with namespaced data
    context: dict[str, Any] = {
        "row": row_context,
        "lookup": self._lookup_data,
    }

    try:
        return self._template.render(**context)
    except UndefinedError as e:
        raise TemplateError(f"Undefined variable: {e}") from e
    except SecurityError as e:
        raise TemplateError(f"Sandbox violation: {e}") from e
    except Exception as e:
        raise TemplateError(f"Template rendering failed: {e}") from e
```

Update the `render_with_metadata` method:

```python
def render_with_metadata(
    self,
    row: dict[str, Any],
    *,
    contract: SchemaContract | None = None,
) -> RenderedPrompt:
    """Render template and return with audit metadata.

    Args:
        row: Row data (accessed as row.* in template)
        contract: Optional schema contract for dual-name resolution

    Returns:
        RenderedPrompt with prompt string and all hashes

    Raises:
        TemplateError: If rendering fails or row contains non-canonicalizable values
            (e.g., NaN, Infinity)
    """
    prompt = self.render(row, contract=contract)

    # Compute variables hash using canonical JSON (row data only)
    # Always hash the raw row data (normalized keys) for determinism
    try:
        variables_hash = _sha256(canonical_json(row))
    except (ValueError, TypeError) as e:
        raise TemplateError(f"Cannot compute variables hash: {e}") from e

    # Compute rendered prompt hash
    rendered_hash = _sha256(prompt)

    # Compute contract hash if provided
    contract_hash: str | None = None
    if contract is not None:
        # Hash the contract definition for audit trail
        contract_hash = _sha256(
            canonical_json({
                "mode": contract.mode,
                "fields": [
                    {
                        "n": fc.normalized_name,
                        "o": fc.original_name,
                        "t": fc.python_type.__name__,
                    }
                    for fc in sorted(contract.fields, key=lambda f: f.normalized_name)
                ],
            })
        )

    return RenderedPrompt(
        prompt=prompt,
        template_hash=self._template_hash,
        variables_hash=variables_hash,
        rendered_hash=rendered_hash,
        template_source=self._template_source,
        lookup_hash=self._lookup_hash,
        lookup_source=self._lookup_source,
        contract_hash=contract_hash,
    )
```

**Step 3.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_prompt_template_contract.py -v
```

Expected: All tests PASS

**Step 3.5: Run existing template tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_templates.py -v
```

Expected: All tests PASS

**Step 3.6: Commit**

```bash
git add src/elspeth/plugins/llm/templates.py tests/plugins/llm/test_prompt_template_contract.py
git commit -m "feat(llm): add contract support to PromptTemplate

render() and render_with_metadata() now accept optional contract.
When contract provided, templates can use original names:
  {{ row[\"'Amount USD'\"] }}  # Resolves via contract

RenderedPrompt includes contract_hash for audit trail.
Backwards compatible - contract is optional.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Enhanced Field Extraction with Original Names

**Files:**
- Modify: `src/elspeth/core/templates.py`
- Test: `tests/core/test_template_extraction_dual.py` (create new)

**Step 4.1: Write failing tests for dual-name extraction**

```python
# tests/core/test_template_extraction_dual.py
"""Tests for extracting fields with original name annotation."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.templates import (
    extract_jinja2_fields,
    extract_jinja2_fields_with_names,
)


class TestExtractWithNames:
    """Test field extraction with original name resolution."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
                FieldContract("simple", "simple", str, True, "declared"),
            ),
            locked=True,
        )

    def test_extract_returns_normalized_and_original(
        self, contract: SchemaContract
    ) -> None:
        """Extraction with contract returns both name forms."""
        template = "{{ row.amount_usd }} and {{ row[\"'Amount USD'\"] }}"

        result = extract_jinja2_fields_with_names(template, contract)

        # Should report the field once with both names
        assert "amount_usd" in result
        assert result["amount_usd"]["original"] == "'Amount USD'"
        assert result["amount_usd"]["normalized"] == "amount_usd"

    def test_extract_resolves_original_to_normalized(
        self, contract: SchemaContract
    ) -> None:
        """Original name references resolve to normalized."""
        template = "{{ row[\"Customer ID\"] }}"

        result = extract_jinja2_fields_with_names(template, contract)

        assert "customer_id" in result
        assert result["customer_id"]["original"] == "Customer ID"

    def test_extract_deduplicates_same_field(
        self, contract: SchemaContract
    ) -> None:
        """Same field accessed both ways is deduplicated."""
        template = "{{ row.amount_usd }} {{ row[\"'Amount USD'\"] }}"

        result = extract_jinja2_fields_with_names(template, contract)

        # Only one entry for the field
        assert len(result) == 1
        assert "amount_usd" in result

    def test_extract_reports_unknown_field(
        self, contract: SchemaContract
    ) -> None:
        """Unknown field is reported with normalized as original."""
        template = "{{ row.unknown_field }}"

        result = extract_jinja2_fields_with_names(template, contract)

        # Unknown field - original equals what was written
        assert "unknown_field" in result
        assert result["unknown_field"]["original"] == "unknown_field"
        assert result["unknown_field"]["resolved"] is False

    def test_extract_without_contract_returns_as_written(self) -> None:
        """Without contract, returns field names as written."""
        template = "{{ row.field_name }}"

        result = extract_jinja2_fields_with_names(template)  # No contract

        assert "field_name" in result
        assert result["field_name"]["original"] == "field_name"
        assert result["field_name"]["resolved"] is False

    def test_extract_mixed_known_unknown(
        self, contract: SchemaContract
    ) -> None:
        """Mix of known and unknown fields works."""
        template = "{{ row.amount_usd }} {{ row.unknown }}"

        result = extract_jinja2_fields_with_names(template, contract)

        assert "amount_usd" in result
        assert result["amount_usd"]["resolved"] is True

        assert "unknown" in result
        assert result["unknown"]["resolved"] is False

    def test_extract_original_name_only(
        self, contract: SchemaContract
    ) -> None:
        """Template using only original names."""
        template = "{{ row[\"'Amount USD'\"] }} {{ row[\"Customer ID\"] }}"

        result = extract_jinja2_fields_with_names(template, contract)

        assert "amount_usd" in result  # Resolved to normalized
        assert "customer_id" in result
        assert len(result) == 2
```

**Step 4.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/test_template_extraction_dual.py -v
```

Expected: FAIL (`extract_jinja2_fields_with_names` doesn't exist)

**Step 4.3: Implement extract_jinja2_fields_with_names**

Add to `src/elspeth/core/templates.py`:

First, add import:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import SchemaContract
```

Then add the new function:

```python
def extract_jinja2_fields_with_names(
    template_string: str,
    contract: "SchemaContract | None" = None,
    namespace: str = "row",
) -> dict[str, dict[str, str | bool]]:
    """Extract field names with original/normalized name resolution.

    Enhanced version of extract_jinja2_fields that:
    - Reports both original and normalized names when contract provided
    - Resolves original names to their normalized form
    - Indicates whether resolution was successful

    This helps developers understand which fields their templates need
    and see both name forms for documentation/debugging.

    Args:
        template_string: Jinja2 template to parse
        contract: Optional SchemaContract for name resolution
        namespace: Variable name to search for (default: "row")

    Returns:
        Dict mapping normalized_name -> {
            "normalized": str,  # Normalized name (key)
            "original": str,    # Original name (or same as normalized if unknown)
            "resolved": bool,   # True if found in contract
        }

    Examples:
        >>> # Without contract
        >>> extract_jinja2_fields_with_names("{{ row.field }}")
        {'field': {'normalized': 'field', 'original': 'field', 'resolved': False}}

        >>> # With contract (has "'Amount USD'" -> "amount_usd")
        >>> extract_jinja2_fields_with_names(
        ...     "{{ row[\"'Amount USD'\"] }}",
        ...     contract=contract,
        ... )
        {'amount_usd': {'normalized': 'amount_usd', 'original': "'Amount USD'", 'resolved': True}}
    """
    # First, extract all field references as-written
    raw_fields = extract_jinja2_fields(template_string, namespace)

    result: dict[str, dict[str, str | bool]] = {}

    for field_as_written in raw_fields:
        if contract is not None:
            # Try to resolve via contract
            try:
                normalized = contract.resolve_name(field_as_written)
                fc = contract.get_field(normalized)
                original = fc.original_name if fc else field_as_written
                result[normalized] = {
                    "normalized": normalized,
                    "original": original,
                    "resolved": True,
                }
            except KeyError:
                # Not in contract - report as-is
                result[field_as_written] = {
                    "normalized": field_as_written,
                    "original": field_as_written,
                    "resolved": False,
                }
        else:
            # No contract - report as-is
            result[field_as_written] = {
                "normalized": field_as_written,
                "original": field_as_written,
                "resolved": False,
            }

    return result
```

**Step 4.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/test_template_extraction_dual.py -v
```

Expected: All tests PASS

**Step 4.5: Run existing extraction tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/core/test_templates.py -v
```

Expected: All tests PASS

**Step 4.6: Commit**

```bash
git add src/elspeth/core/templates.py tests/core/test_template_extraction_dual.py
git commit -m "feat(templates): add extract_jinja2_fields_with_names

Enhanced field extraction that resolves original/normalized names:
- Reports both name forms when contract provided
- Deduplicates same field accessed both ways
- Indicates whether resolution was successful
- Backwards compatible (contract optional)

Helps developers see which source headers their templates reference.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: LLM Transform Integration

**Files:**
- Modify: `src/elspeth/plugins/llm/base.py`
- Test: `tests/plugins/llm/test_llm_transform_contract.py` (create new)

**Step 5.1: Write failing tests for LLM transform with contract**

```python
# tests/plugins/llm/test_llm_transform_contract.py
"""Tests for LLM transform contract integration."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from elspeth.contracts import TransformResult
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.plugins.llm.base import BaseLLMTransform


class MockLLMTransform(BaseLLMTransform):
    """Test LLM transform."""

    name = "mock_llm"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._mock_response = "mocked response"

    async def _execute_llm_call(
        self,
        prompt: str,
        ctx: Any,
    ) -> str:
        return self._mock_response


class TestLLMTransformContract:
    """Test LLM transform with contract-aware templates."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("product_name", "Product Name", str, True, "declared"),
                FieldContract("description", "DESCRIPTION", str, True, "declared"),
            ),
            locked=True,
        )

    @pytest.fixture
    def data(self) -> dict[str, object]:
        """Sample row data."""
        return {
            "product_name": "Widget",
            "description": "A useful widget",
        }

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Mock plugin context."""
        ctx = MagicMock()
        ctx.run_id = "test-run"
        return ctx

    @pytest.mark.asyncio
    async def test_process_with_pipeline_row(
        self,
        data: dict[str, object],
        contract: SchemaContract,
        mock_context: MagicMock,
    ) -> None:
        """Process accepts PipelineRow and uses contract for template."""
        transform = MockLLMTransform({
            "model": "test-model",
            "template": "Analyze: {{ row[\"Product Name\"] }}",
            "required_input_fields": ["product_name"],
        })

        pipeline_row = PipelineRow(data, contract)
        result = await transform.process(pipeline_row, mock_context)

        assert result.is_success
        # Template should have resolved "Product Name" to "product_name"

    @pytest.mark.asyncio
    async def test_process_with_dict_no_contract(
        self,
        data: dict[str, object],
        mock_context: MagicMock,
    ) -> None:
        """Process with plain dict works (backwards compatible)."""
        transform = MockLLMTransform({
            "model": "test-model",
            "template": "Analyze: {{ row.product_name }}",
            "required_input_fields": ["product_name"],
        })

        result = await transform.process(data, mock_context)

        assert result.is_success

    @pytest.mark.asyncio
    async def test_result_has_contract_when_input_has_contract(
        self,
        data: dict[str, object],
        contract: SchemaContract,
        mock_context: MagicMock,
    ) -> None:
        """TransformResult includes contract when input is PipelineRow."""
        transform = MockLLMTransform({
            "model": "test-model",
            "template": "{{ row.product_name }}",
            "required_input_fields": ["product_name"],
            "response_field": "llm_result",
        })

        pipeline_row = PipelineRow(data, contract)
        result = await transform.process(pipeline_row, mock_context)

        assert result.is_success
        # Result should have a contract (propagated/updated)
        assert result.contract is not None
```

**Step 5.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_llm_transform_contract.py -v
```

Expected: FAIL (process doesn't handle PipelineRow or propagate contracts)

**Step 5.3: Update BaseLLMTransform to support contracts**

In `src/elspeth/plugins/llm/base.py`, update the `process` method:

First, add imports:

```python
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.contracts.contract_propagation import propagate_contract
```

Then update the `process` method signature and implementation:

```python
async def process(
    self,
    row: dict[str, Any] | PipelineRow,
    ctx: PluginContext,
) -> TransformResult:
    """Process a row through the LLM transform.

    Args:
        row: Input row (dict or PipelineRow with contract)
        ctx: Plugin context

    Returns:
        TransformResult with LLM response added to row
    """
    # Extract contract if input is PipelineRow
    input_contract: SchemaContract | None = None
    if isinstance(row, PipelineRow):
        input_contract = row.contract
        row_data = row.to_dict()
    else:
        row_data = row

    # Render template with contract for dual-name access
    try:
        rendered = self._template.render_with_metadata(
            row_data,
            contract=input_contract,
        )
    except TemplateError as e:
        return TransformResult.error(
            reason={"error": "template_error", "message": str(e)},
            retryable=False,
        )

    # Execute LLM call
    try:
        response = await self._execute_llm_call(rendered.prompt, ctx)
    except Exception as e:
        return TransformResult.error(
            reason={"error": "llm_error", "message": str(e)},
            retryable=True,
        )

    # Build output row
    output_row = dict(row_data)
    output_row[self._response_field] = response

    # Add audit metadata
    output_row[f"{self._response_field}_template_hash"] = rendered.template_hash
    output_row[f"{self._response_field}_variables_hash"] = rendered.variables_hash
    if rendered.template_source:
        output_row[f"{self._response_field}_template_source"] = rendered.template_source

    # Propagate contract if present
    output_contract: SchemaContract | None = None
    if input_contract is not None:
        output_contract = propagate_contract(
            input_contract=input_contract,
            output_row=output_row,
            transform_adds_fields=True,  # LLM transforms add response field
        )

    return TransformResult.success(
        row=output_row,
        success_reason={"action": "llm_processed", "model": self._model},
        contract=output_contract,
    )
```

**Step 5.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/llm/test_llm_transform_contract.py -v
```

Expected: All tests PASS

**Step 5.5: Run existing LLM tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/plugins/llm/ -v --ignore=tests/plugins/llm/test_azure_multi_query_llm.py
```

Expected: All tests PASS

**Step 5.6: Commit**

```bash
git add src/elspeth/plugins/llm/base.py tests/plugins/llm/test_llm_transform_contract.py
git commit -m "feat(llm): integrate contract support in BaseLLMTransform

process() now accepts PipelineRow and uses contract for template:
- Dual-name template access via ContractAwareRow
- Contract propagated through to TransformResult
- Backwards compatible with plain dict input

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Module Exports

**Files:**
- Modify: `src/elspeth/plugins/llm/__init__.py`
- Modify: `src/elspeth/core/templates.py` (update __all__)

**Step 6.1: Update LLM module exports**

Add to `src/elspeth/plugins/llm/__init__.py`:

```python
from elspeth.plugins.llm.contract_aware_row import ContractAwareRow
```

Update `__all__`:

```python
__all__ = [
    # ... existing exports ...
    "ContractAwareRow",
]
```

**Step 6.2: Update templates module exports**

Add to `src/elspeth/core/templates.py` (create __all__ if not present):

```python
__all__ = [
    "extract_jinja2_fields",
    "extract_jinja2_fields_with_details",
    "extract_jinja2_fields_with_names",
]
```

**Step 6.3: Run type checker**

```bash
.venv/bin/python -m mypy src/elspeth/plugins/llm/ src/elspeth/core/templates.py
```

Expected: No errors

**Step 6.4: Run linter**

```bash
.venv/bin/python -m ruff check src/elspeth/plugins/llm/ src/elspeth/core/templates.py
```

Expected: No errors

**Step 6.5: Commit**

```bash
git add src/elspeth/plugins/llm/__init__.py src/elspeth/core/templates.py
git commit -m "feat: export Phase 4 template resolver utilities

Add to exports:
- ContractAwareRow (llm module)
- extract_jinja2_fields_with_names (templates module)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Integration Test - Full Pipeline

**Files:**
- Test: `tests/integration/test_template_resolver_integration.py` (create new)

**Step 7.1: Write integration test**

```python
# tests/integration/test_template_resolver_integration.py
"""Integration tests for template resolver with full pipeline flow."""

from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import MagicMock

import pytest

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.llm.templates import PromptTemplate
from elspeth.plugins.sources.csv_source import CSVSource


class MockContext:
    """Minimal context for integration testing."""

    def __init__(self) -> None:
        self.run_id = "test-run"
        self.validation_errors: list[dict[str, Any]] = []

    def record_validation_error(self, **kwargs: Any) -> None:
        self.validation_errors.append(dict(kwargs))


class TestTemplateResolverIntegration:
    """End-to-end tests for template resolver."""

    def test_source_to_template_dual_name(self, tmp_path: Path) -> None:
        """Template can use original names from source headers."""
        # Create CSV with messy headers
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            'Product Name',PRICE_USD
            Widget,100
        """))

        # Load with normalization
        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        rows = list(source.load(ctx))
        source_row = rows[0]

        # Get contract from source
        contract = source.get_schema_contract()
        assert contract is not None

        # Create template using ORIGINAL names
        template = PromptTemplate(
            "Product: {{ row[\"'Product Name'\"] }}, Price: {{ row[\"PRICE_USD\"] }}"
        )

        # Render with contract - should resolve original names
        result = template.render(source_row.row, contract=contract)

        assert "Product: Widget" in result
        assert "Price: 100" in result

    def test_pipeline_row_template_access(self, tmp_path: Path) -> None:
        """PipelineRow works directly in templates."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            Customer Name,Order Total
            Alice,250
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        rows = list(source.load(ctx))
        pipeline_row = rows[0].to_pipeline_row()

        # Access both ways
        assert pipeline_row["Customer Name"] == "Alice"  # Original
        assert pipeline_row.customer_name == "Alice"     # Normalized
        assert pipeline_row["customer_name"] == "Alice"  # Normalized bracket

    def test_hash_stability_across_access_styles(self, tmp_path: Path) -> None:
        """Same data hashes the same regardless of template access style."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            Original Header
            value
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        rows = list(source.load(ctx))
        row_data = rows[0].row
        contract = source.get_schema_contract()

        # Two templates accessing same field differently
        template1 = PromptTemplate("{{ row.original_header }}")
        template2 = PromptTemplate("{{ row[\"Original Header\"] }}")

        result1 = template1.render_with_metadata(row_data, contract=contract)
        result2 = template2.render_with_metadata(row_data, contract=contract)

        # Same output
        assert result1.prompt == result2.prompt

        # Same variables hash (based on normalized data)
        assert result1.variables_hash == result2.variables_hash

    def test_field_extraction_reports_both_names(self, tmp_path: Path) -> None:
        """Field extraction helper shows original names."""
        from elspeth.core.templates import extract_jinja2_fields_with_names

        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            'Messy Header!!'
            value
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        list(source.load(ctx))
        contract = source.get_schema_contract()

        # Template uses normalized name
        template = "{{ row.messy_header }}"
        result = extract_jinja2_fields_with_names(template, contract)

        assert "messy_header" in result
        assert result["messy_header"]["original"] == "'Messy Header!!'"
        assert result["messy_header"]["resolved"] is True

    def test_complex_template_with_conditionals(self, tmp_path: Path) -> None:
        """Complex template with conditionals works with dual names."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            Amount USD,Status
            150,active
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        rows = list(source.load(ctx))
        contract = source.get_schema_contract()

        template = PromptTemplate("""
{% if row["Amount USD"] | int > 100 %}
High value order from {{ row.status }} customer
{% else %}
Regular order
{% endif %}
""".strip())

        result = template.render(rows[0].row, contract=contract)

        assert "High value order" in result
        assert "active customer" in result
```

**Step 7.2: Run integration tests**

```bash
.venv/bin/python -m pytest tests/integration/test_template_resolver_integration.py -v
```

Expected: All tests PASS

**Step 7.3: Commit**

```bash
git add tests/integration/test_template_resolver_integration.py
git commit -m "test(integration): add template resolver integration tests

End-to-end tests for:
- Source → Template dual-name flow
- PipelineRow direct template access
- Hash stability across access styles
- Field extraction with original names
- Complex templates with conditionals

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update Beads and Sync

**Step 8.1: Update beads issue**

```bash
bd close elspeth-rapid-XXX  # Replace with actual issue ID
bd sync
```

---

## Summary

Phase 4 implementation enables dual-name template access:

| Component | Purpose |
|-----------|---------|
| `ContractAwareRow` | Wrapper for dual-name Jinja2 access |
| `PromptTemplate.render(contract=)` | Contract-aware rendering |
| `extract_jinja2_fields_with_names()` | Report both name forms |
| `BaseLLMTransform` integration | Contract propagation in LLM transforms |
| `RenderedPrompt.contract_hash` | Audit trail for contract used |

**Key patterns:**
- Templates can use `{{ row["'Amount USD'"] }}` (original) or `{{ row.amount_usd }}` (normalized)
- Contract resolution is O(1) via precomputed indices
- Hashes computed from normalized data for determinism
- Backwards compatible - contract is always optional

**Usage example:**

```python
# Source creates contract with original names
source = CSVSource({"path": "data.csv", "normalize_fields": True, ...})
rows = source.load(ctx)
contract = source.get_schema_contract()

# Template can use either name form
template = PromptTemplate("""
Customer: {{ row["Customer Name"] }}  # Original
Amount: {{ row.amount_usd }}          # Normalized
""")

# Render with contract enables dual-name resolution
result = template.render(row, contract=contract)
```

**Next:** Phase 5 records contracts in Landscape audit schema.
