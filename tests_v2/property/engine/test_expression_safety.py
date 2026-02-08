# tests_v2/property/engine/test_expression_safety.py
"""Property-based tests for ExpressionParser injection rejection.

The ExpressionParser uses a whitelist-based AST approach to safely evaluate
gate conditions. These tests verify that ALL injections are rejected,
not just the specific attack vectors we've thought of.

Security model:
- Only allowed: row['field'], row.get(), comparisons, boolean ops,
  arithmetic, literals, membership tests, ternary expressions
- Forbidden: function calls (except row.get), lambda, comprehensions,
  assignment expressions, await/yield, f-strings, attribute access,
  names other than row/True/False/None

Properties tested:
1. All forbidden AST constructs are rejected
2. Valid expressions always parse successfully
3. Evaluation is deterministic
4. Generated attack patterns are caught
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from elspeth.engine.expression_parser import (
    ExpressionEvaluationError,
    ExpressionParser,
    ExpressionSecurityError,
    ExpressionSyntaxError,
)

# =============================================================================
# Strategies for generating expressions
# =============================================================================

# Valid field names (simple identifiers)
field_names = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
).filter(lambda s: s[0].isalpha() or s[0] == "_")

# Valid string literals for use in expressions
string_literals = st.text(min_size=0, max_size=30, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
    blacklist_characters="'\"\\",
))

# Valid integer literals
int_literals = st.integers(min_value=-10000, max_value=10000)

# Valid float literals
float_literals = st.floats(
    min_value=-10000.0, max_value=10000.0,
    allow_nan=False, allow_infinity=False,
)

# Comparison operators
comparison_ops = st.sampled_from(["==", "!=", "<", ">", "<=", ">="])

# Boolean operators
boolean_ops = st.sampled_from(["and", "or"])

# Arithmetic operators
arithmetic_ops = st.sampled_from(["+", "-", "*"])

# Known injection patterns that MUST be rejected
injection_patterns = st.sampled_from([
    # Function calls
    "print('hacked')",
    "__import__('os').system('rm -rf /')",
    "eval('1+1')",
    "exec('import os')",
    "open('/etc/passwd').read()",
    "getattr(row, '__class__')",
    "type(row)",
    "dir(row)",
    "vars(row)",
    "globals()",
    "locals()",
    "compile('code', 'f', 'exec')",
    "breakpoint()",
    # Lambda
    "lambda: True",
    "(lambda x: x)(row)",
    # Comprehensions
    "[x for x in range(10)]",
    "{x: x for x in range(10)}",
    "{x for x in range(10)}",
    "(x for x in range(10))",
    # Assignment expressions
    "(x := 1)",
    # F-strings
    "f'{row}'",
    "f\"{'hello'}\"",
    # Attribute access (except row.get)
    "row.__class__",
    "row.__dict__",
    "row.__module__",
    "row.items()",
    "row.keys()",
    "row.values()",
    "row.pop('key')",
    "row.update({'evil': True})",
    # Forbidden names
    "os",
    "sys",
    "builtins",
    "__builtins__",
    "subprocess",
    # Starred expressions
    "*row",
    # Yield/await
    # (these are syntax errors in expression mode, but we test them)
])

# Additional injection patterns using name manipulation
name_injection_patterns = st.sampled_from([
    "chr(65)",
    "ord('A')",
    "len(row)",
    "list(row)",
    "dict(row)",
    "str(row)",
    "int(row['field'])",
    "float(row['field'])",
    "bool(row['field'])",
    "tuple(row)",
    "set(row)",
    "sorted(row)",
    "reversed(row)",
    "enumerate(row)",
    "zip(row, row)",
    "map(str, row)",
    "filter(None, row)",
    "sum([1, 2, 3])",
    "max(1, 2)",
    "min(1, 2)",
    "abs(-1)",
    "round(1.5)",
    "hex(255)",
    "oct(255)",
    "bin(255)",
])


# =============================================================================
# Injection Rejection Properties
# =============================================================================


class TestInjectionRejectionProperties:
    """Property tests verifying all injections are rejected."""

    @given(pattern=injection_patterns)
    @settings(max_examples=100)
    def test_known_injection_patterns_rejected(self, pattern: str) -> None:
        """Property: All known injection patterns are rejected.

        Every pattern in this list must raise ExpressionSecurityError
        or ExpressionSyntaxError - never succeed.
        """
        with pytest.raises((ExpressionSecurityError, ExpressionSyntaxError)):
            ExpressionParser(pattern)

    @given(pattern=name_injection_patterns)
    @settings(max_examples=100)
    def test_name_injection_patterns_rejected(self, pattern: str) -> None:
        """Property: Function call injections via built-in names are rejected."""
        with pytest.raises((ExpressionSecurityError, ExpressionSyntaxError)):
            ExpressionParser(pattern)

    @given(
        name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    )
    @settings(max_examples=100)
    def test_arbitrary_names_rejected(self, name: str) -> None:
        """Property: Arbitrary names (not row/True/False/None) are rejected.

        Only 'row', 'True', 'False', and 'None' are allowed as names.
        """
        assume(name not in ("row", "True", "False", "None"))

        with pytest.raises((ExpressionSecurityError, ExpressionSyntaxError)):
            ExpressionParser(name)

    @given(
        attr=st.text(min_size=1, max_size=15, alphabet=st.characters(whitelist_categories=("L",))),
    )
    @settings(max_examples=50)
    def test_arbitrary_row_attributes_rejected(self, attr: str) -> None:
        """Property: Arbitrary attribute access on row is rejected (only .get allowed).

        Note: Python keywords (True, False, None, etc.) cause syntax errors
        when used as attributes, so we accept both error types.
        """
        assume(attr != "get")

        expr = f"row.{attr}"
        with pytest.raises((ExpressionSecurityError, ExpressionSyntaxError)):
            ExpressionParser(expr)

    @given(
        func_name=st.sampled_from(["eval", "exec", "compile", "open", "print", "input", "exit", "quit"]),
        arg=string_literals,
    )
    @settings(max_examples=50)
    def test_function_calls_rejected(self, func_name: str, arg: str) -> None:
        """Property: Arbitrary function calls are always rejected."""
        expr = f"{func_name}('{arg}')"
        with pytest.raises((ExpressionSecurityError, ExpressionSyntaxError)):
            ExpressionParser(expr)


# =============================================================================
# Valid Expression Properties
# =============================================================================


class TestValidExpressionProperties:
    """Property tests verifying valid expressions are accepted."""

    @given(field=field_names, value=string_literals)
    @settings(max_examples=100)
    def test_field_comparison_accepted(self, field: str, value: str) -> None:
        """Property: row['field'] == 'value' is always accepted."""
        expr = f"row['{field}'] == '{value}'"
        parser = ExpressionParser(expr)
        assert parser.expression == expr

    @given(field=field_names, value=int_literals)
    @settings(max_examples=100)
    def test_field_numeric_comparison_accepted(self, field: str, value: int) -> None:
        """Property: row['field'] > N is always accepted."""
        expr = f"row['{field}'] > {value}"
        parser = ExpressionParser(expr)
        assert parser.expression == expr

    @given(
        field1=field_names,
        op1=comparison_ops,
        val1=int_literals,
        bool_op=boolean_ops,
        field2=field_names,
        op2=comparison_ops,
        val2=int_literals,
    )
    @settings(max_examples=100)
    def test_compound_boolean_expressions_accepted(
        self, field1: str, op1: str, val1: int, bool_op: str,
        field2: str, op2: str, val2: int,
    ) -> None:
        """Property: Compound boolean expressions are accepted."""
        assume(field1 != field2)  # Make expression more interesting
        expr = f"row['{field1}'] {op1} {val1} {bool_op} row['{field2}'] {op2} {val2}"
        parser = ExpressionParser(expr)
        assert parser.expression == expr

    @given(field=field_names, default=string_literals)
    @settings(max_examples=50)
    def test_row_get_with_default_accepted(self, field: str, default: str) -> None:
        """Property: row.get('field', 'default') is always accepted."""
        expr = f"row.get('{field}', '{default}')"
        parser = ExpressionParser(expr)
        assert parser.expression == expr

    @given(field=field_names)
    @settings(max_examples=50)
    def test_none_comparison_accepted(self, field: str) -> None:
        """Property: row['field'] is None / is not None are accepted."""
        for pattern in [f"row['{field}'] is None", f"row['{field}'] is not None"]:
            parser = ExpressionParser(pattern)
            assert parser.expression == pattern

    @given(
        field=field_names,
        items=st.lists(string_literals, min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_membership_test_accepted(self, field: str, items: list[str]) -> None:
        """Property: row['field'] in [...] is accepted."""
        items_str = ", ".join(f"'{item}'" for item in items)
        expr = f"row['{field}'] in [{items_str}]"
        parser = ExpressionParser(expr)
        assert parser.expression == expr

    def test_literal_true_accepted(self) -> None:
        """Property: Bare True is accepted (for always-match gates)."""
        parser = ExpressionParser("True")
        assert parser.evaluate({}) is True

    def test_literal_false_accepted(self) -> None:
        """Property: Bare False is accepted (for never-match gates)."""
        parser = ExpressionParser("False")
        assert parser.evaluate({}) is False

    @given(
        field=field_names,
        op=arithmetic_ops,
        value=int_literals,
        cmp_op=comparison_ops,
        threshold=int_literals,
    )
    @settings(max_examples=50)
    def test_arithmetic_in_comparison_accepted(
        self, field: str, op: str, value: int, cmp_op: str, threshold: int,
    ) -> None:
        """Property: Arithmetic within comparisons is accepted."""
        expr = f"row['{field}'] {op} {value} {cmp_op} {threshold}"
        parser = ExpressionParser(expr)
        assert parser.expression == expr


# =============================================================================
# Evaluation Determinism Properties
# =============================================================================


class TestEvaluationDeterminismProperties:
    """Property tests verifying evaluation is deterministic."""

    @given(
        field=field_names,
        value=int_literals,
        threshold=int_literals,
    )
    @settings(max_examples=100)
    def test_evaluation_is_deterministic(self, field: str, value: int, threshold: int) -> None:
        """Property: Same expression + same row = same result, always."""
        expr = f"row['{field}'] > {threshold}"
        parser = ExpressionParser(expr)
        row = {field: value}

        result1 = parser.evaluate(row)
        result2 = parser.evaluate(row)
        result3 = parser.evaluate(row)

        assert result1 == result2 == result3, "Evaluation is non-deterministic!"

    @given(field=field_names)
    @settings(max_examples=50)
    def test_missing_field_raises_evaluation_error(self, field: str) -> None:
        """Property: Missing field raises ExpressionEvaluationError, not KeyError."""
        assume(field != "other_field")
        expr = f"row['{field}']"
        parser = ExpressionParser(expr)

        with pytest.raises(ExpressionEvaluationError):
            parser.evaluate({"other_field": 1})

    @given(field=field_names, default=st.one_of(string_literals, int_literals, st.none()))
    @settings(max_examples=50)
    def test_row_get_returns_default_for_missing(self, field: str, default: Any) -> None:
        """Property: row.get(field, default) returns default when field is missing."""
        assume(field != "existing")
        if isinstance(default, str):
            expr = f"row.get('{field}', '{default}')"
        elif default is None:
            expr = f"row.get('{field}', None)"
        else:
            expr = f"row.get('{field}', {default})"

        parser = ExpressionParser(expr)
        result = parser.evaluate({"existing": 1})

        assert result == default


# =============================================================================
# Boolean Expression Detection Properties
# =============================================================================


class TestBooleanExpressionDetectionProperties:
    """Property tests for is_boolean_expression() classification."""

    @given(field=field_names, value=int_literals, op=comparison_ops)
    @settings(max_examples=50)
    def test_comparisons_detected_as_boolean(self, field: str, value: int, op: str) -> None:
        """Property: Comparison expressions are always classified as boolean."""
        expr = f"row['{field}'] {op} {value}"
        parser = ExpressionParser(expr)
        assert parser.is_boolean_expression() is True

    @given(field=field_names)
    @settings(max_examples=20)
    def test_field_access_not_boolean(self, field: str) -> None:
        """Property: Bare field access is not boolean."""
        expr = f"row['{field}']"
        parser = ExpressionParser(expr)
        assert parser.is_boolean_expression() is False

    def test_not_expression_is_boolean(self) -> None:
        """Property: not row['x'] is boolean."""
        parser = ExpressionParser("not row['x']")
        assert parser.is_boolean_expression() is True

    def test_true_literal_is_boolean(self) -> None:
        """Property: True literal is boolean."""
        parser = ExpressionParser("True")
        assert parser.is_boolean_expression() is True

    def test_false_literal_is_boolean(self) -> None:
        """Property: False literal is boolean."""
        parser = ExpressionParser("False")
        assert parser.is_boolean_expression() is True
