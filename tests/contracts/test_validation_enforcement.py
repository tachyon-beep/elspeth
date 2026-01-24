"""Test that plugins cannot skip validation."""

import pytest

from elspeth.contracts import PluginSchema
from elspeth.plugins.base import BaseTransform


class TestSchema(PluginSchema):
    """Test schema."""

    value: int


def test_transform_must_implement_validation() -> None:
    """Transforms that don't call _validate_self_consistency should fail."""

    class BadTransform(BaseTransform):
        """Transform that doesn't call _validate_self_consistency."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            # BUG: Didn't call _validate_self_consistency()

        def process(self, row, ctx):
            return row

    # This should raise RuntimeError at instantiation (validation not called)
    with pytest.raises(RuntimeError, match="did not call _validate_self_consistency"):
        BadTransform({})


def test_transform_with_validation_succeeds() -> None:
    """Transforms that implement validation should succeed."""

    class GoodTransform(BaseTransform):
        """Transform that correctly implements validation."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            self._validate_self_consistency()  # Correct!

        def _validate_self_consistency(self) -> None:
            """Implement abstract method."""
            self._validation_called = True  # Mark validation as complete
            # No additional validation needed for this test transform

        def process(self, row, ctx):
            return row

    # Should succeed
    transform = GoodTransform({})
    assert transform.input_schema is TestSchema


def test_transform_must_call_validation_not_just_implement() -> None:
    """CRITICAL: __init_subclass__ hook enforces validation is CALLED, not just implemented."""

    class LazyTransform(BaseTransform):
        """Transform that implements but never calls _validate_self_consistency."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            # BUG: Implemented the method but didn't call it!

        def _validate_self_consistency(self) -> None:
            """Method exists but is never invoked."""
            self._validation_called = True
            # Validation logic here would never execute

        def process(self, row, ctx):
            return row

    # Should fail at instantiation - __init_subclass__ hook detects missing call
    with pytest.raises(RuntimeError, match="did not call _validate_self_consistency"):
        LazyTransform({})


def test_transform_cannot_bypass_validation_via_super_skip() -> None:
    """CRITICAL: Plugins cannot bypass validation by skipping super().__init__().

    This test verifies that enforcement works even if a plugin tries
    to bypass the base class __init__.
    """

    class MaliciousTransform(BaseTransform):
        """Transform that tries to bypass validation."""

        def __init__(self, config: dict) -> None:
            # BUG: Doesn't call super().__init__(), tries to bypass validation
            self._config = config
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            # No _validate_self_consistency() call!

        def process(self, row, ctx):
            return row

    # Should still fail - __init_subclass__ hook catches this
    with pytest.raises(RuntimeError, match="did not call _validate_self_consistency"):
        MaliciousTransform({})


def test_transform_validation_survives_multiple_inheritance() -> None:
    """Validation enforcement survives multiple inheritance."""

    class Mixin:
        """Test mixin class."""

        def extra_method(self):
            pass

    class TransformWithMixin(Mixin, BaseTransform):
        """Transform with multiple inheritance."""

        def __init__(self, config: dict) -> None:
            super().__init__(config)
            self.input_schema = TestSchema
            self.output_schema = TestSchema
            # Forgot to call _validate_self_consistency()!

        def process(self, row, ctx):
            return row

    # Should fail - __init_subclass__ hook enforcement transcends multiple inheritance
    with pytest.raises(RuntimeError, match="did not call _validate_self_consistency"):
        TransformWithMixin({})
