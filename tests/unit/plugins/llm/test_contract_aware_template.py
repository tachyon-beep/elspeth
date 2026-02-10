"""Tests for Jinja2 template rendering with contract-aware row access."""

import pytest
from jinja2 import StrictUndefined, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from elspeth.contracts.schema_contract import SchemaContract
from elspeth.testing import make_field, make_row


class TestJinja2Integration:
    """Test PipelineRow works correctly with Jinja2."""

    @pytest.fixture
    def env(self) -> SandboxedEnvironment:
        """Sandboxed Jinja2 environment with strict undefined."""
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
                make_field("amount_usd", int, original_name="'Amount USD'", required=True, source="declared"),
                make_field("customer_name", str, original_name="Customer Name", required=True, source="declared"),
                make_field("order_id", str, original_name="ORDER-ID", required=True, source="declared"),
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
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)
        template = env.from_string('Customer {{ row.customer_name }} ordered {{ row["\'Amount USD\'"] }} ({{ row["ORDER-ID"] }})')

        result = template.render(row=row)

        assert result == "Customer Alice ordered 100 (ORD-001)"

    def test_render_with_conditional(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template with conditional on original name works."""
        row = make_row(data, contract=contract)
        template = env.from_string("{% if row[\"'Amount USD'\"] > 50 %}High value{% else %}Low value{% endif %}")

        result = template.render(row=row)

        assert result == "High value"

    def test_render_with_loop_over_keys(
        self,
        env: SandboxedEnvironment,
        data: dict[str, object],
        contract: SchemaContract,
    ) -> None:
        """Template iterating over row keys yields normalized names."""
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)

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
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)
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
        row = make_row(data, contract=contract)
        template = env.from_string("{{ row['Customer Name'] | upper }}")

        result = template.render(row=row)

        assert result == "ALICE"
