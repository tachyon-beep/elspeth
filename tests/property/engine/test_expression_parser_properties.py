# tests/property/engine/test_expression_parser_properties.py
"""Property-based tests for expression parser security and correctness.

These tests verify the fundamental security and correctness properties
of ELSPETH's expression parser:

Security Properties:
- Forbidden constructs always raise ExpressionSecurityError
- Syntax errors always raise ExpressionSyntaxError
- No code execution beyond the whitelist

Correctness Properties:
- is_boolean_expression() correctly classifies expressions
- Evaluation is deterministic
- Comparison operators produce boolean results
"""

from __future__ import annotations

import keyword
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from elspeth.engine.expression_parser import (
    ExpressionParser,
    ExpressionSecurityError,
    ExpressionSyntaxError,
)

# =============================================================================
# Strategies for generating expressions
# =============================================================================

# Valid field names (alphanumeric, starting with letter)
field_names = st.text(
    min_size=1,
    max_size=15,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
).filter(lambda s: s[0].isalpha() and s not in ("row", "True", "False", "None"))

# Safe string literals (no problematic escapes)
safe_strings = st.text(
    min_size=0,
    max_size=20,
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="'\"\\\n\r\t",
    ),
)

# Numeric values
numeric_values = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)

# Comparison operators
comparison_ops = st.sampled_from(["==", "!=", "<", ">", "<=", ">=", "in", "not in"])

# Boolean operators
boolean_ops = st.sampled_from(["and", "or"])


@st.composite
def field_access_expressions(draw: st.DrawFn) -> str:
    """Generate valid field access expressions like row['field']."""
    field = draw(field_names)
    return f"row['{field}']"


@st.composite
def comparison_expressions(draw: st.DrawFn) -> str:
    """Generate valid comparison expressions."""
    field = draw(field_names)
    op = draw(comparison_ops)

    if op in ("in", "not in"):
        # Membership checks need a list
        values = draw(st.lists(st.integers(min_value=-100, max_value=100), min_size=1, max_size=5))
        return f"row['{field}'] {op} {values}"
    else:
        # Other comparisons with numeric value
        value = draw(numeric_values)
        return f"row['{field}'] {op} {value}"


@st.composite
def boolean_compound_expressions(draw: st.DrawFn) -> str:
    """Generate compound boolean expressions."""
    expr1 = draw(comparison_expressions())
    expr2 = draw(comparison_expressions())
    bool_op = draw(boolean_ops)
    return f"({expr1}) {bool_op} ({expr2})"


@st.composite
def ternary_expressions(draw: st.DrawFn) -> str:
    """Generate ternary expressions."""
    condition = draw(comparison_expressions())
    true_val = draw(st.sampled_from(["True", "'yes'", "1"]))
    false_val = draw(st.sampled_from(["False", "'no'", "0"]))
    return f"{true_val} if {condition} else {false_val}"


# =============================================================================
# Security Property Tests
# =============================================================================


class TestSecurityProperties:
    """Property tests for expression parser security."""

    @given(field=field_names, value=numeric_values)
    @settings(max_examples=200)
    def test_valid_comparison_always_parses(self, field: str, value: float | int) -> None:
        """Property: Valid comparisons parse without security error."""
        expr = f"row['{field}'] == {value}"
        parser = ExpressionParser(expr)  # Should not raise
        assert parser.expression == expr

    @given(expr=comparison_expressions())
    @settings(max_examples=200)
    def test_generated_comparisons_are_valid(self, expr: str) -> None:
        """Property: Generated comparison expressions are valid."""
        parser = ExpressionParser(expr)  # Should not raise
        assert parser.expression == expr

    @given(expr=boolean_compound_expressions())
    @settings(max_examples=100)
    def test_generated_compounds_are_valid(self, expr: str) -> None:
        """Property: Generated compound boolean expressions are valid."""
        parser = ExpressionParser(expr)  # Should not raise
        assert parser.expression == expr

    # Forbidden constructs

    @given(func_name=st.sampled_from(["eval", "exec", "open", "print", "len", "str", "int"]))
    @settings(max_examples=20)
    def test_function_calls_rejected(self, func_name: str) -> None:
        """Property: Function calls (except row.get) are rejected."""
        expr = f"{func_name}(row['x'])"
        with pytest.raises(ExpressionSecurityError):
            ExpressionParser(expr)

    @given(
        import_style=st.sampled_from(
            [
                "__import__('os')",
                "__builtins__",
            ]
        )
    )
    @settings(max_examples=10)
    def test_import_attempts_rejected(self, import_style: str) -> None:
        """Property: Import attempts are rejected."""
        with pytest.raises(ExpressionSecurityError):
            ExpressionParser(import_style)

    @given(name=st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L",))))
    @settings(max_examples=100)
    def test_arbitrary_names_rejected(self, name: str) -> None:
        """Property: Arbitrary names (not row/True/False/None) are rejected."""
        # Skip allowed names and Python keywords (keywords cause SyntaxError, not SecurityError)
        if name in ("row", "True", "False", "None") or keyword.iskeyword(name):
            assume(False)
            return

        expr = f"{name} == 1"
        with pytest.raises(ExpressionSecurityError, match="Forbidden name"):
            ExpressionParser(expr)

    def test_lambda_rejected(self) -> None:
        """Property: Lambda expressions are rejected."""
        with pytest.raises(ExpressionSecurityError):
            ExpressionParser("(lambda: row['x'])()")

    def test_comprehension_rejected(self) -> None:
        """Property: List comprehensions are rejected."""
        with pytest.raises(ExpressionSecurityError):
            ExpressionParser("[x for x in [1,2,3]]")

    def test_attribute_access_rejected(self) -> None:
        """Property: Attribute access (except row.get) is rejected."""
        with pytest.raises(ExpressionSecurityError):
            ExpressionParser("row.__class__")


class TestSyntaxErrorProperties:
    """Property tests for syntax error handling."""

    @given(garbage=st.text(min_size=1, max_size=20).filter(lambda s: not s.isalnum()))
    @settings(max_examples=50)
    def test_garbage_input_rejected_gracefully(self, garbage: str) -> None:
        """Property: Garbage input is rejected with appropriate error type.

        Non-alphanumeric input should be rejected, but the specific error type
        depends on whether the string is syntactically valid Python:
        - Invalid Python syntax → ExpressionSyntaxError (e.g., '{{{{')
        - Valid syntax but forbidden constructs → ExpressionSecurityError (e.g., '_')

        Both outcomes are correct rejection behavior.
        """
        try:
            ExpressionParser(garbage)
        except (ExpressionSyntaxError, ExpressionSecurityError):
            pass  # Expected - garbage rejected appropriately
        except Exception as e:
            # Unexpected exception type indicates a bug
            pytest.fail(f"Garbage '{garbage}' raised unexpected {type(e).__name__}: {e}")

    def test_unclosed_bracket_raises_syntax_error(self) -> None:
        """Property: Unclosed bracket is syntax error."""
        with pytest.raises(ExpressionSyntaxError):
            ExpressionParser("row['field'")

    def test_invalid_operator_raises_syntax_error(self) -> None:
        """Property: Invalid operator is syntax error."""
        with pytest.raises(ExpressionSyntaxError):
            ExpressionParser("row['x'] === 1")  # JavaScript-style ===


# =============================================================================
# Boolean Classification Property Tests
# =============================================================================


class TestBooleanClassificationProperties:
    """Property tests for is_boolean_expression()."""

    @given(expr=comparison_expressions())
    @settings(max_examples=200)
    def test_comparisons_are_boolean(self, expr: str) -> None:
        """Property: Comparison expressions are classified as boolean."""
        parser = ExpressionParser(expr)
        assert parser.is_boolean_expression(), f"Comparison '{expr}' should be classified as boolean"

    @given(field=field_names)
    @settings(max_examples=100)
    def test_field_access_is_not_boolean(self, field: str) -> None:
        """Property: Field access alone is NOT classified as boolean."""
        expr = f"row['{field}']"
        parser = ExpressionParser(expr)
        assert not parser.is_boolean_expression(), f"Field access '{expr}' should NOT be classified as boolean"

    @given(field=field_names, num=numeric_values)
    @settings(max_examples=100)
    def test_arithmetic_is_not_boolean(self, field: str, num: float | int) -> None:
        """Property: Arithmetic expressions are NOT classified as boolean."""
        expr = f"row['{field}'] + {num}"
        parser = ExpressionParser(expr)
        assert not parser.is_boolean_expression(), f"Arithmetic '{expr}' should NOT be classified as boolean"

    @given(expr=boolean_compound_expressions())
    @settings(max_examples=100)
    def test_compound_boolean_is_boolean(self, expr: str) -> None:
        """Property: Compound boolean expressions are classified as boolean."""
        parser = ExpressionParser(expr)
        assert parser.is_boolean_expression(), f"Compound boolean '{expr}' should be classified as boolean"

    def test_unary_not_is_boolean(self) -> None:
        """Property: Unary not expressions are boolean."""
        parser = ExpressionParser("not row['flag']")
        assert parser.is_boolean_expression()

    def test_true_false_literals_are_boolean(self) -> None:
        """Property: True/False literals are boolean."""
        assert ExpressionParser("True").is_boolean_expression()
        assert ExpressionParser("False").is_boolean_expression()

    def test_ternary_with_boolean_branches_is_boolean(self) -> None:
        """Property: Ternary with boolean branches is boolean."""
        parser = ExpressionParser("True if row['x'] > 0 else False")
        assert parser.is_boolean_expression()

    def test_ternary_with_non_boolean_branches_is_not_boolean(self) -> None:
        """Property: Ternary with non-boolean branches is NOT boolean."""
        parser = ExpressionParser("1 if row['x'] > 0 else 0")
        assert not parser.is_boolean_expression()


# =============================================================================
# Evaluation Property Tests
# =============================================================================


class TestEvaluationProperties:
    """Property tests for expression evaluation."""

    @given(field=field_names, value=st.integers(min_value=-100, max_value=100))
    @settings(max_examples=200)
    def test_evaluation_is_deterministic(self, field: str, value: int) -> None:
        """Property: Evaluating same expression with same row twice gives same result."""
        expr = f"row['{field}'] == {value}"
        parser = ExpressionParser(expr)
        row = {field: value}

        result1 = parser.evaluate(row)
        result2 = parser.evaluate(row)

        assert result1 == result2, "Evaluation is not deterministic"

    @given(
        field=field_names,
        row_value=st.integers(min_value=-100, max_value=100),
        compare_value=st.integers(min_value=-100, max_value=100),
    )
    @settings(max_examples=200)
    def test_comparison_returns_boolean(self, field: str, row_value: int, compare_value: int) -> None:
        """Property: Comparison expressions return actual boolean."""
        expr = f"row['{field}'] == {compare_value}"
        parser = ExpressionParser(expr)
        row = {field: row_value}

        result = parser.evaluate(row)

        assert isinstance(result, bool), f"Comparison returned {type(result)}, not bool"
        assert result == (row_value == compare_value)

    @given(
        field=field_names,
        value=st.integers(min_value=-100, max_value=100),
        threshold=st.integers(min_value=-100, max_value=100),
    )
    @settings(max_examples=200)
    def test_less_than_comparison_correct(self, field: str, value: int, threshold: int) -> None:
        """Property: Less-than comparison produces correct result."""
        expr = f"row['{field}'] < {threshold}"
        parser = ExpressionParser(expr)
        row = {field: value}

        result = parser.evaluate(row)
        expected = value < threshold

        assert result == expected, f"row['{field}'] < {threshold} with value={value}: got {result}, expected {expected}"

    @given(field=field_names, default=st.integers(min_value=-100, max_value=100))
    @settings(max_examples=100)
    def test_row_get_with_default(self, field: str, default: int) -> None:
        """Property: row.get() with default returns default for missing key."""
        expr = f"row.get('{field}', {default})"
        parser = ExpressionParser(expr)
        row: dict[str, Any] = {}  # Empty row

        result = parser.evaluate(row)

        assert result == default, f"row.get('{field}', {default}) on empty row returned {result}"

    @given(field=field_names)
    @settings(max_examples=100)
    def test_row_get_without_default_returns_none(self, field: str) -> None:
        """Property: row.get() without default returns None for missing key."""
        expr = f"row.get('{field}')"
        parser = ExpressionParser(expr)
        row: dict[str, Any] = {}

        result = parser.evaluate(row)

        assert result is None, f"row.get('{field}') on empty row returned {result}, not None"

    @given(
        field=field_names,
        value=st.integers(min_value=1, max_value=100),
        values_list=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_membership_check_correct(self, field: str, value: int, values_list: list[int]) -> None:
        """Property: Membership check produces correct result."""
        expr = f"row['{field}'] in {values_list}"
        parser = ExpressionParser(expr)
        row = {field: value}

        result = parser.evaluate(row)
        expected = value in values_list

        assert result == expected, f"{value} in {values_list}: got {result}, expected {expected}"


class TestRowGetProperties:
    """Property tests specifically for row.get() behavior."""

    @given(field=field_names)
    @settings(max_examples=50)
    def test_row_get_call_is_valid(self, field: str) -> None:
        """Property: row.get('field') is a valid expression."""
        expr = f"row.get('{field}')"
        parser = ExpressionParser(expr)  # Should not raise
        assert parser.expression == expr

    @given(field=field_names, default=st.integers())
    @settings(max_examples=50)
    def test_row_get_with_default_is_valid(self, field: str, default: int) -> None:
        """Property: row.get('field', default) is a valid expression."""
        expr = f"row.get('{field}', {default})"
        parser = ExpressionParser(expr)  # Should not raise
        assert parser.expression == expr

    def test_row_get_zero_args_rejected(self) -> None:
        """Property: row.get() with no args is rejected."""
        with pytest.raises(ExpressionSecurityError, match="1 or 2 arguments"):
            ExpressionParser("row.get()")

    def test_row_get_three_args_rejected(self) -> None:
        """Property: row.get() with 3 args is rejected."""
        with pytest.raises(ExpressionSecurityError, match="1 or 2 arguments"):
            ExpressionParser("row.get('a', 1, 2)")

    def test_bare_row_get_rejected(self) -> None:
        """Property: Bare row.get without call is rejected."""
        with pytest.raises(ExpressionSecurityError, match=r"Bare 'row\.get'"):
            ExpressionParser("row.get")
