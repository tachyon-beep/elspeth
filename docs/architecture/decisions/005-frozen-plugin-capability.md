# ADR 005 – Frozen Plugin Capability (Strict Level Enforcement)

## Status

**Accepted** (2025-10-26)
**Implemented** (2025-10-26)

## Context

ADR-002 establishes trusted downgrade as the default behavior: plugins with HIGHER clearance can operate at LOWER pipeline levels (e.g., SECRET-cleared datasource operating at OFFICIAL level by filtering data appropriately).

However, some deployment scenarios require **strict level enforcement** where plugins refuse ALL operations below their declared level:

1. **Dedicated Classification Domains** – Infrastructure physically/logically separated by level (SECRET-only enclaves)
2. **Regulatory Mandates** – Compliance frameworks requiring explicit per-level certification without cross-level operation
3. **High-Assurance Systems** – Environments where filtering trust is insufficient (e.g., air-gapped networks)
4. **Organizational Policy** – Security policies mandating that SECRET datasources NEVER participate in non-SECRET pipelines

Currently, `BasePlugin.validate_can_operate_at_level()` is sealed (`@final` + `__init_subclass__`) and CANNOT be overridden, making strict enforcement impossible without framework changes.

## Decision

We will add **frozen plugin capability** via a **mandatory configuration parameter** rather than a customization hook. This approach:

- Maintains sealed method security (no override attack surface)
- Provides explicit, auditable configuration
- **Requires explicit security choice** (no default - security decisions must be intentional)
- ⚠️ **Breaking change**: All plugins MUST explicitly declare `allow_downgrade=True` or `allow_downgrade=False`

### Implementation: Configuration-Driven Approach

Add `allow_downgrade: bool` parameter to `BasePlugin.__init__()`:

```python
class BasePlugin(ABC):
    """Abstract base class for all Elspeth plugins with concrete security enforcement.

    Attributes:
        _security_level (SecurityLevel): Plugin's security clearance.
        _allow_downgrade (bool): Whether plugin can operate at lower levels (default: True).
    """

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        **kwargs: object
    ) -> None:
        """Initialize BasePlugin with mandatory security level and downgrade policy.

        Args:
            security_level: Plugin's security clearance (MANDATORY keyword-only argument).
            allow_downgrade: Whether plugin can operate at lower pipeline levels (MANDATORY - no default).
                - True: Trusted downgrade - plugin can filter to lower levels
                - False: Frozen plugin - must operate at exact declared level
            **kwargs: Additional keyword arguments passed to super().__init__().

        Raises:
            ValueError: If security_level is None.
            TypeError: If allow_downgrade not provided (no default - explicit choice required).

        Design Notes:
            - allow_downgrade is MANDATORY with no default (security-first: explicit > implicit)
            - allow_downgrade=True: ADR-002 trusted downgrade semantics
            - allow_downgrade=False: Frozen plugin behavior for strict deployments
            - Setting stored in private _allow_downgrade (read via property)
            - Breaking change from previous version that defaulted to True
        """
        if security_level is None:
            raise ValueError(
                f"{type(self).__name__}: security_level cannot be None (ADR-004 requirement)"
            )

        self._security_level = security_level
        self._allow_downgrade = allow_downgrade
        super().__init__(**kwargs)

    @property
    def allow_downgrade(self) -> bool:
        """Read-only property for downgrade permission.

        Returns:
            bool: Whether plugin can operate at lower pipeline levels.

        Example:
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
            >>> plugin.allow_downgrade
            False
        """
        return self._allow_downgrade

    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate plugin can operate at the given pipeline level (SEALED - cannot be overridden).

        Bell-LaPadula "no read up": Plugins cannot operate ABOVE their clearance.
        Frozen plugin extension: Plugins with allow_downgrade=False cannot operate BELOW their clearance.

        Args:
            operating_level: Pipeline operating level to validate against.

        Raises:
            SecurityValidationError: If plugin cannot operate at the given level.

        Validation Logic:
            1. Check insufficient clearance: operating_level > security_level → REJECT (always)
            2. Check frozen downgrade: operating_level < security_level AND not allow_downgrade → REJECT
            3. Otherwise: ALLOW (exact match or trusted downgrade)

        Example:
            >>> # Trusted downgrade (default)
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=True)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ✅ OK
            >>> plugin.validate_can_operate_at_level(SecurityLevel.TOP_SECRET)  # ❌ Raises

            >>> # Frozen plugin
            >>> frozen = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK (exact)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ❌ Raises (frozen)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.TOP_SECRET)  # ❌ Raises (insufficient)
        """
        # Check 1: Insufficient clearance (Bell-LaPadula "no read up")
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name}. "
                f"Insufficient clearance for higher classification (Bell-LaPadula MLS violation)."
            )

        # Check 2: Frozen plugin downgrade rejection
        if operating_level < self._security_level and not self._allow_downgrade:
            raise SecurityValidationError(
                f"{type(self).__name__} is frozen at {self._security_level.name} "
                f"(allow_downgrade=False). Cannot operate at lower level {operating_level.name}. "
                f"This plugin requires exact level matching and does not support trusted downgrade."
            )

        # Check 3: Valid operation (exact match or trusted downgrade)
        # No exception raised
```

### Example Usage

**Trusted Downgrade (Explicit - Most Common)**:
```python
class AzureDataSource(BasePlugin, DataSource):
    def __init__(self, *, security_level: SecurityLevel = SecurityLevel.SECRET):
        # MUST explicitly declare allow_downgrade (no default)
        super().__init__(security_level=security_level, allow_downgrade=True)

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        # Can operate at OFFICIAL, UNOFFICIAL if pipeline requires
        # Responsible for filtering SECRET-tagged blobs appropriately
        ...
```

**Frozen Plugin (Strict Level Enforcement)**:
```python
class DedicatedSecretDataSource(BasePlugin, DataSource):
    def __init__(self):
        # Explicit allow_downgrade=False → frozen behavior
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        # Will ONLY operate in SECRET pipelines
        # Pipeline construction fails if configured with lower-clearance components
        ...
```

## Consequences

### Benefits

1. **Explicit Security Choices** – ⚠️ **BREAKING CHANGE**: All plugins MUST explicitly declare `allow_downgrade` (no implicit defaults)
   - Security-first principle: Explicit > Implicit for security decisions
   - Code review friendly: Security posture visible at plugin construction
   - Prevents accidental misconfigurations from relying on defaults
2. **Sealed Method Security** – No new override surface (attack prevention)
3. **Minimal API Expansion** – Single boolean parameter + read-only property
4. **Type-Safe** – MyPy validates parameter usage at static analysis time
5. **Certification Friendly** – Auditors check constructor parameter, not complex override logic
6. **Clear Intent** – Plugin behavior is unambiguous from constructor signature

### Limitations / Trade-offs

1. **Reduced Flexibility for Frozen Plugins** – Cannot participate in mixed-classification pipelines
   - *Mitigation*: Use frozen plugins only in dedicated classification domains
   - *Alternative*: Configure separate pipelines per classification level

2. **Deployment Complexity** – Frozen plugins require exact level matching infrastructure
   - *Mitigation*: Document frozen plugin deployment patterns in operations guide
   - *Impact*: Acceptable for high-assurance environments requiring strict enforcement

3. **No Per-Operation Customization** – Configuration is static at instantiation time
   - *Mitigation*: This is intentional - prevents time-of-check to time-of-use (TOCTOU) vulnerabilities
   - *Alternative*: If dynamic behavior needed, configure separate plugin instances per level

### Implementation Impact

**Core Changes** (`src/elspeth/core/base/plugin.py`):
- ⚠️ **BREAKING**: Remove default from `allow_downgrade` parameter (`allow_downgrade: bool` with NO default)
- Add `_allow_downgrade` private field
- Add `allow_downgrade` read-only property
- Update validation logic to check frozen plugin constraint

**Migration Required** (ALL plugins):
- Every plugin MUST add `allow_downgrade=True` to `super().__init__()` call
- Pre-1.0: Breaking change is acceptable (fix-on-fail approach)
- Post-1.0: Would require deprecation cycle
- Update `validate_can_operate_at_level()` with frozen check (Check 2)
- Update docstrings with frozen plugin examples

**Test Coverage** (`tests/test_baseplugin_frozen.py` - NEW):
- Test default `allow_downgrade=True` (trusted downgrade scenarios)
- Test frozen `allow_downgrade=False` (exact match only scenarios)
- Test insufficient clearance rejection (always enforced)
- Test frozen rejection error messages
- Property-based tests with all SecurityLevel combinations
- Integration test with suite runner (frozen datasource + lower-clearance sink)

**Documentation Updates**:
- **ADR-002** (`docs/architecture/decisions/002-security-architecture.md`):
  - Remove "Future Work" designation from frozen plugin section
  - Replace hypothetical code with actual implementation
  - Remove "Implementation Options" (decision made)
  - Add "Current Implementation" with `allow_downgrade=False` pattern
- **ADR-004** (`docs/architecture/decisions/004-mandatory-baseplugin-inheritance.md`):
  - Update BasePlugin specification to include `allow_downgrade` parameter
  - Add frozen plugin example to sealed method section
- **Plugin Development Guide** (`docs/development/plugin-authoring.md`):
  - Add "Frozen Plugins" section with use cases
  - Document `allow_downgrade=False` pattern
  - Add certification notes for frozen plugins

**Migration Impact**: **ZERO** ✅
- Backwards compatible (default behavior unchanged)
- No existing plugin changes required
- New capability opt-in via explicit parameter

**Certification Impact**:
- **Default Plugins**: Certification unchanged (trusted downgrade verified as before)
- **Frozen Plugins**: Certification must verify:
  1. Constructor correctly sets `allow_downgrade=False`
  2. Plugin implementation safe to operate at single level only
  3. No inadvertent cross-level data leakage
  4. Deployment infrastructure supports exact level matching

## Test Specification

### Unit Tests (`tests/test_baseplugin_frozen.py`)

```python
"""Frozen Plugin Capability Tests (ADR-005)."""

import pytest
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError


class MockPlugin(BasePlugin):
    """Mock plugin for testing frozen capability."""

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool = True
    ):
        super().__init__(
            security_level=security_level,
            allow_downgrade=allow_downgrade
        )


class TestDefaultTrustedDowngrade:
    """Test default allow_downgrade=True behavior (ADR-002 semantics)."""

    def test_default_parameter_is_true(self):
        """Default allow_downgrade parameter is True (backwards compatible)."""
        plugin = MockPlugin(security_level=SecurityLevel.SECRET)
        assert plugin.allow_downgrade is True

    def test_trusted_downgrade_to_lower_level(self):
        """SECRET plugin can operate at OFFICIAL level (trusted downgrade)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True
        )
        # Should not raise
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_trusted_downgrade_to_lowest_level(self):
        """SECRET plugin can operate at UNOFFICIAL level (trusted downgrade)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=True
        )
        # Should not raise
        plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

    def test_exact_match_allowed(self):
        """Plugin can operate at exact declared level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=True
        )
        # Should not raise
        plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

    def test_insufficient_clearance_rejected(self):
        """Plugin cannot operate ABOVE its clearance (Bell-LaPadula)."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=True
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        assert "Insufficient clearance" in str(exc_info.value)
        assert "OFFICIAL" in str(exc_info.value)
        assert "SECRET" in str(exc_info.value)


class TestFrozenPlugin:
    """Test allow_downgrade=False behavior (frozen plugins)."""

    def test_frozen_property_reflects_parameter(self):
        """allow_downgrade property reflects constructor parameter."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        assert plugin.allow_downgrade is False

    def test_frozen_exact_match_allowed(self):
        """Frozen plugin can operate at exact declared level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        # Should not raise (exact match)
        plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

    def test_frozen_downgrade_rejected(self):
        """Frozen plugin cannot operate at lower level."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)

        error_msg = str(exc_info.value)
        assert "frozen at SECRET" in error_msg
        assert "allow_downgrade=False" in error_msg
        assert "OFFICIAL" in error_msg

    def test_frozen_two_level_downgrade_rejected(self):
        """Frozen plugin cannot operate two levels below."""
        plugin = MockPlugin(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)

        assert "frozen at SECRET" in str(exc_info.value)

    def test_frozen_insufficient_clearance_rejected(self):
        """Frozen plugin still enforces insufficient clearance check."""
        plugin = MockPlugin(
            security_level=SecurityLevel.OFFICIAL,
            allow_downgrade=False
        )
        with pytest.raises(SecurityValidationError) as exc_info:
            plugin.validate_can_operate_at_level(SecurityLevel.SECRET)

        # Should get insufficient clearance error, not frozen error
        assert "Insufficient clearance" in str(exc_info.value)


class TestPropertyBased:
    """Property-based tests covering all SecurityLevel combinations."""

    @pytest.mark.parametrize("plugin_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    @pytest.mark.parametrize("operating_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    def test_trusted_downgrade_matrix(self, plugin_level, operating_level):
        """Trusted downgrade: plugin can operate at same or lower level."""
        plugin = MockPlugin(security_level=plugin_level, allow_downgrade=True)

        if operating_level <= plugin_level:
            # Should succeed (same level or downgrade)
            plugin.validate_can_operate_at_level(operating_level)
        else:
            # Should fail (insufficient clearance)
            with pytest.raises(SecurityValidationError):
                plugin.validate_can_operate_at_level(operating_level)

    @pytest.mark.parametrize("plugin_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    @pytest.mark.parametrize("operating_level", [
        SecurityLevel.UNOFFICIAL,
        SecurityLevel.OFFICIAL,
        SecurityLevel.SECRET,
    ])
    def test_frozen_matrix(self, plugin_level, operating_level):
        """Frozen: plugin can ONLY operate at exact level."""
        plugin = MockPlugin(security_level=plugin_level, allow_downgrade=False)

        if operating_level == plugin_level:
            # Should succeed (exact match)
            plugin.validate_can_operate_at_level(operating_level)
        else:
            # Should fail (frozen downgrade or insufficient clearance)
            with pytest.raises(SecurityValidationError):
                plugin.validate_can_operate_at_level(operating_level)
```

### Integration Tests (`tests/test_adr002_suite_integration.py` - additions)

```python
def test_frozen_datasource_exact_match():
    """Frozen datasource succeeds when all components at same level."""
    # All components at SECRET level
    datasource = create_frozen_datasource(SecurityLevel.SECRET)
    transform = create_transform(SecurityLevel.SECRET)
    sink = create_sink(SecurityLevel.SECRET)

    suite = ExperimentSuite(
        datasource=datasource,
        transforms=[transform],
        sinks=[sink]
    )

    # Should succeed - operating_level = min(SECRET, SECRET, SECRET) = SECRET
    # Frozen datasource operates at exact declared level
    suite.run()


def test_frozen_datasource_rejects_lower_level_sink():
    """Frozen datasource aborts when sink has lower clearance."""
    # Frozen SECRET datasource + OFFICIAL sink
    datasource = create_frozen_datasource(SecurityLevel.SECRET)
    sink = create_sink(SecurityLevel.OFFICIAL)

    suite = ExperimentSuite(
        datasource=datasource,
        sinks=[sink]
    )

    # Operating level = min(SECRET frozen, OFFICIAL) = OFFICIAL
    # Frozen datasource validation: OFFICIAL < SECRET and not allow_downgrade → REJECT
    with pytest.raises(SecurityValidationError) as exc_info:
        suite.run()

    error_msg = str(exc_info.value)
    assert "frozen at SECRET" in error_msg
    assert "allow_downgrade=False" in error_msg


def test_frozen_sink_accepts_higher_level_datasource():
    """Frozen sink succeeds when datasource has higher clearance."""
    # SECRET datasource (trusted downgrade) + Frozen OFFICIAL sink
    datasource = create_datasource(SecurityLevel.SECRET, allow_downgrade=True)
    sink = create_frozen_sink(SecurityLevel.OFFICIAL)

    suite = ExperimentSuite(
        datasource=datasource,
        sinks=[sink]
    )

    # Operating level = min(SECRET, OFFICIAL frozen) = OFFICIAL
    # Datasource validation: OFFICIAL < SECRET and allow_downgrade → ALLOW (filters)
    # Frozen sink validation: OFFICIAL == OFFICIAL → ALLOW (exact match)
    suite.run()  # Should succeed
```

## Timeline

**Phase 1: Core Implementation** (1-2 hours)
- Update `BasePlugin.__init__()` with `allow_downgrade` parameter
- Add `allow_downgrade` property
- Update `validate_can_operate_at_level()` with frozen check
- Update docstrings

**Phase 2: Test Coverage** (2-3 hours)
- Create `tests/test_baseplugin_frozen.py` with unit tests
- Add integration tests to `tests/test_adr002_suite_integration.py`
- Run mutation testing on frozen validation logic
- Achieve 100% coverage on frozen code paths

**Phase 3: Documentation** (1-2 hours)
- Remove "Future Work" from ADR-002, update with implemented solution
- Update ADR-004 BasePlugin specification
- Add frozen plugin section to plugin development guide
- Update certification checklist

**Phase 4: Verification** (30 minutes)
- Run full test suite (`make test`)
- Run type checking (`make lint`)
- Verify backwards compatibility (existing tests pass unchanged)

**Total Estimated Effort**: 5-8 hours

## Related Documents

- [ADR-002](002-security-architecture.md) – Multi-Level Security Enforcement (trusted downgrade default)
- [ADR-004](004-mandatory-baseplugin-inheritance.md) – Mandatory BasePlugin Inheritance (sealed methods)
- `docs/development/plugin-authoring.md` – Plugin development guide
- `tests/test_baseplugin_frozen.py` – Frozen plugin test suite (NEW)

---

**Proposed**: 2025-10-26
**Author(s)**: Architecture Team
