"""BasePlugin Abstract Base Class (ADR-004: Mandatory BasePlugin Inheritance).

This module provides the foundational BasePlugin ABC that enforces security-critical
invariants through concrete, non-overridable methods (the "Security Bones" design).

Design Principles:
- **Nominal Typing**: Plugins MUST explicitly inherit from BasePlugin (not duck-typed)
- **Concrete Implementation**: Security methods provided by ABC (not abstract)
- **Dual Enforcement**: @final (static) + __init_subclass__ (runtime) prevents override
- **Constructor Contract**: security_level is mandatory, keyword-only parameter

Why Concrete Methods Over Abstract:
1. **Consistency**: All plugins use identical security logic (no variance)
2. **Security**: Can't accidentally break enforcement by wrong implementation
3. **Simplicity**: Plugins inherit security for free (no boilerplate)
4. **Maintainability**: Security logic lives in one place (BasePlugin)
5. **Trust Boundary**: Security enforcement isolated from plugin code

Related ADRs:
- ADR-002: Multi-Level Security Enforcement (requires isinstance checks)
- ADR-004: Mandatory BasePlugin Inheritance (this ABC enables ADR-002 validation)
"""

from abc import ABC
from typing import final

from elspeth.core.base.types import SecurityLevel
from elspeth.core.validation.base import SecurityValidationError


class BasePlugin(ABC):
    """Abstract base class for all Elspeth plugins with concrete security enforcement.

    This ABC provides "security bones" - concrete, non-overridable methods that implement
    security-critical invariants. Plugins inherit security enforcement without implementing it.

    **CRITICAL DESIGN**: This is an ABC (not a Protocol) to enforce nominal typing.
    Plugins MUST explicitly declare inheritance:

        class MyPlugin(BasePlugin):  # ← Explicit inheritance required
            def __init__(self, *, security_level: SecurityLevel, ...):
                super().__init__(security_level=security_level)

    **Why ABC Over Protocol**:
    - isinstance(plugin, BasePlugin) requires explicit inheritance (nominal typing)
    - Protocol would accept any duck-typed class with matching methods (structural typing)
    - ADR-002 validation requires nominal typing to prevent bypass attacks

    **Sealed Methods** (cannot be overridden by subclasses):
    - get_security_level() - Returns plugin's security clearance
    - validate_can_operate_at_level() - Enforces security level constraints

    **Constructor Contract**:
    - security_level must be provided as keyword-only argument
    - security_level cannot be None
    - Subclasses MUST call super().__init__(security_level=...)

    **Runtime Enforcement**:
    __init_subclass__ hook prevents subclasses from overriding sealed methods.
    Attempting to override raises TypeError at class definition time.

    Example:
        >>> class MyDatasource(BasePlugin):
        ...     def __init__(self, *, security_level: SecurityLevel):
        ...         super().__init__(security_level=security_level)
        ...
        >>> ds = MyDatasource(security_level=SecurityLevel.SECRET)
        >>> ds.get_security_level()
        SecurityLevel.SECRET
        >>> ds.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK (exact)
        >>> ds.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ✅ OK (trusted downgrade)

    Example (Frozen Plugin - ADR-005):
        >>> class FrozenDatasource(BasePlugin):
        ...     def __init__(self):
        ...         super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=False)
        ...
        >>> frozen = FrozenDatasource()
        >>> frozen.get_security_level()
        SecurityLevel.SECRET
        >>> frozen.allow_downgrade
        False
        >>> frozen.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK (exact)
        >>> frozen.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ❌ Raises (frozen)

    Attributes:
        _security_level (SecurityLevel): Plugin's security clearance (private storage).
        _allow_downgrade (bool): Whether plugin can operate at lower levels (private storage).

    Properties:
        security_level (SecurityLevel): Read-only access to security clearance.
        allow_downgrade (bool): Read-only access to downgrade permission.

    Methods:
        get_security_level() -> SecurityLevel: Returns plugin's declared clearance.
        get_effective_level() -> SecurityLevel: Returns pipeline operating level (effective level).
        validate_can_operate_at_level(SecurityLevel) -> None: Validates operating level.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Runtime enforcement: prevent subclasses from overriding security methods.

        This hook runs when a subclass of BasePlugin is DEFINED (not instantiated).
        It inspects the subclass's __dict__ to detect if any sealed methods were overridden.

        If a sealed method is found in the subclass, raises TypeError immediately,
        preventing the class from being defined.

        Args:
            **kwargs: Standard __init_subclass__ keyword arguments.

        Raises:
            TypeError: If subclass attempts to override a sealed security method.

        Note:
            This is runtime enforcement complementing @final (static type checking).
            MyPy catches overrides at type-check time, this catches them at runtime.
        """
        super().__init_subclass__(**kwargs)

        # Sealed methods that cannot be overridden (ADR-004 security invariants)
        sealed_methods = ("get_security_level", "get_effective_level", "validate_can_operate_at_level")

        for method_name in sealed_methods:
            if method_name in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} may not override {method_name} (ADR-004 security invariant). "
                    f"Security enforcement is provided by BasePlugin and cannot be customized. "
                    f"If you need custom security logic, please consult the architecture team."
                )

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
                - True: Trusted downgrade - plugin can filter/downgrade to lower levels
                - False: Frozen plugin - must operate at exact declared level (ADR-005)
                - ⚠️ NO DEFAULT: Explicit security choice required (security-first principle)
            **kwargs: Additional keyword arguments passed to super().__init__().

        Raises:
            ValueError: If security_level is None.
            TypeError: If allow_downgrade not provided (no default - explicit choice required).

        Design Notes:
            - security_level is keyword-only (forces explicit declaration)
            - allow_downgrade is keyword-only with NO DEFAULT (security-first: explicit > implicit)
            - ⚠️ BREAKING CHANGE from previous version that defaulted to True
            - Stored in private fields (discourages direct access)
            - Public access via properties (read-only)
            - **kwargs allows cooperative multiple inheritance

        Example:
            >>> # Trusted downgrade (EXPLICIT - required)
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=True)
            >>> plugin.allow_downgrade
            True

            >>> # Frozen: Strict level enforcement (ADR-005)
            >>> frozen = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
            >>> frozen.allow_downgrade
            False

            >>> # ERROR: Missing allow_downgrade (no default)
            >>> bad = MyPlugin(security_level=SecurityLevel.SECRET)  # TypeError!
        """
        if security_level is None:
            raise ValueError(f"{type(self).__name__}: security_level cannot be None (ADR-004 requirement)")

        self._security_level = security_level
        self._allow_downgrade = allow_downgrade
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only property for security level (convenience accessor).

        This property allows convenient access to the security level in factory methods
        and other contexts where self.security_level is more readable than self.get_security_level().

        Returns:
            SecurityLevel: Plugin's security clearance.

        Example:
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=True)
            >>> plugin.security_level  # ✅ Convenient access
            SecurityLevel.SECRET
            >>> plugin.security_level = SecurityLevel.UNOFFICIAL  # ❌ AttributeError (read-only)
        """
        return self._security_level

    @property
    def allow_downgrade(self) -> bool:
        """Read-only property for downgrade permission (ADR-005).

        This property indicates whether the plugin can operate at pipeline levels
        LOWER than its declared security clearance.

        Returns:
            bool: Whether plugin can operate at lower pipeline levels.
                - True: Trusted downgrade - can filter/downgrade data to lower levels
                - False: Frozen plugin - must operate at exact declared level only

        Design Notes:
            - MANDATORY parameter (no default - explicit security choice required per ADR-005)
            - Set to True for trusted downgrade (standard behavior per ADR-002)
            - Set to False for frozen plugins (strict enforcement per ADR-005)
            - Read-only to prevent runtime modification (prevents TOCTOU attacks)

        Example:
            >>> # Trusted downgrade (explicit - most common)
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=True)
            >>> plugin.allow_downgrade
            True

            >>> # Frozen plugin (explicit - strict enforcement)
            >>> frozen = MyPlugin(security_level=SecurityLevel.SECRET, allow_downgrade=False)
            >>> frozen.allow_downgrade
            False
        """
        return self._allow_downgrade

    @final
    def get_security_level(self) -> SecurityLevel:
        """Return the plugin's declared security level (SEALED - cannot be overridden).

        This method is marked @final to prevent subclasses from overriding it.
        MyPy will flag any override attempts at type-check time.
        Additionally, __init_subclass__ will raise TypeError at class definition time.

        Returns:
            SecurityLevel: Plugin's security clearance.

        Design Notes:
            - @final provides static enforcement (MyPy catches at type-check time)
            - __init_subclass__ provides runtime enforcement (raises TypeError at class definition)
            - Dual enforcement ensures security method cannot be tampered with

        Example:
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET)
            >>> plugin.get_security_level()
            SecurityLevel.SECRET
        """
        return self._security_level

    @final
    def get_effective_level(self) -> SecurityLevel:
        """Return the pipeline operating level (effective security level - SEALED).

        This method provides plugin authors with controlled access to the pipeline's
        computed operating level (minimum clearance envelope). Plugins should use this
        level for security-aware decisions (filtering, conditional processing, audit logging).

        **Operating Level vs Security Level**:
        - security_level: Plugin's declared clearance (what it CAN handle)
        - operating_level: Pipeline's effective level (what it SHOULD produce)

        **Example Scenarios**:
        - SECRET datasource in UNOFFICIAL pipeline → effective_level = UNOFFICIAL
          (datasource must filter to only retrieve UNOFFICIAL data)
        - OFFICIAL transform in OFFICIAL pipeline → effective_level = OFFICIAL
          (exact match - no filtering needed)

        **Fail-Fast Behavior**:
        This method raises RuntimeError if operating_level has not been set. In a
        high-security system, we want LOUD CATASTROPHIC FAILURE rather than graceful
        degradation. If you see this error, it means the plugin is being used before
        pipeline validation has completed (programming error, not user error).

        Returns:
            SecurityLevel: Pipeline operating level.

        Raises:
            RuntimeError: If operating_level not set (pre-validation state or missing context).
                This indicates a programming error - plugins should only access effective
                level AFTER validation completes.

        Design Notes:
            - @final prevents plugin override (consistent access pattern)
            - Read-only access (context is frozen)
            - Fail-fast on missing operating_level (no graceful degradation in high-security system)
            - Plugin must still pass validate_can_operate_at_level() before execution

        Correct Usage Patterns:
            ✅ Filter data based on effective level (datasource optimization)
            ✅ Conditional processing (skip expensive operations at lower levels)
            ✅ Audit logging with effective level context
            ✅ Performance optimization (different algorithms per level)

        Anti-Patterns (DO NOT):
            ❌ Bypass filtering based on effective level (still must filter correctly)
            ❌ Assume effective_level == data classification (data may be uplifted)
            ❌ Skip validation based on effective level (validation is mandatory)

        Example:
            >>> # SECRET datasource operating at UNOFFICIAL level
            >>> plugin = MyDatasource(security_level=SecurityLevel.SECRET, allow_downgrade=True)
            >>> # After suite_runner sets operating_level in context
            >>> plugin.get_effective_level()  # Returns UNOFFICIAL (from context)
            >>> plugin.get_security_level()   # Returns SECRET (declared clearance)

            >>> # Pre-validation (operating_level not yet set)
            >>> plugin.get_effective_level()  # RuntimeError! Fail loudly.

        See Also:
            ADR-002 "Exposing Operating Level to Plugins" section for certification requirements.
        """
        # Access context via duck-typing (apply_plugin_context attaches plugin_context)
        context = getattr(self, 'plugin_context', None)

        if context is None:
            raise RuntimeError(
                f"{type(self).__name__}.get_effective_level() called before plugin_context attached. "
                f"This is a programming error - plugins must not call get_effective_level() during "
                f"construction. Context attachment happens during pipeline initialization."
            )

        if context.operating_level is None:
            raise RuntimeError(
                f"{type(self).__name__}.get_effective_level() called before pipeline validation. "
                f"This is a programming error - plugins must not call get_effective_level() before "
                f"ExperimentSuiteRunner._validate_experiment_security() completes. "
                f"Operating level is computed during validation and propagated via _propagate_operating_level()."
            )

        # Type narrowing: After None check above, MyPy knows operating_level is SecurityLevel
        operating_level: SecurityLevel = context.operating_level
        return operating_level

    @final
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate that plugin can operate at the given security level (SEALED).

        Bell-LaPadula Multi-Level Security (MLS) enforcement with optional frozen behavior:
        - Plugin with HIGHER clearance can operate at LOWER level (trusted downgrade, ADR-002)
        - Plugin with LOWER clearance CANNOT operate at HIGHER level (insufficient clearance)
        - Frozen plugin (allow_downgrade=False) CANNOT operate at LOWER level (strict enforcement, ADR-005)

        Args:
            operating_level: Security level of the pipeline/suite.

        Raises:
            SecurityValidationError: If insufficient clearance OR frozen downgrade violation.

        Validation Logic:
            1. Check insufficient clearance: operating_level > security_level → REJECT (always)
            2. Check frozen downgrade: operating_level < security_level AND not allow_downgrade → REJECT
            3. Otherwise: ALLOW (exact match or trusted downgrade)

        Design Notes:
            - Check 1 implements Bell-LaPadula "no read up" rule
            - Check 2 implements ADR-005 frozen plugin capability
            - allow_downgrade parameter is MANDATORY (no default, explicit security choice)
            - Fail-fast: Validation happens BEFORE any data processing

        Example (Trusted Downgrade - allow_downgrade=True):
            >>> plugin = MyPlugin(security_level=SecurityLevel.PROTECTED, allow_downgrade=True)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ✅ OK (trusted downgrade)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.PROTECTED)  # ✅ OK (exact match)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.SECRET)  # ❌ Raises (insufficient clearance)

        Example (Frozen Plugin - allow_downgrade=False):
            >>> frozen = MyPlugin(security_level=SecurityLevel.PROTECTED, allow_downgrade=False)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.PROTECTED)  # ✅ OK (exact match only)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ❌ Raises (frozen, no downgrade)
            >>> frozen.validate_can_operate_at_level(SecurityLevel.SECRET)  # ❌ Raises (insufficient clearance)
        """
        # Check 1: Insufficient clearance (Bell-LaPadula "no read up")
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name}. "
                f"Insufficient clearance for higher classification (Bell-LaPadula MLS violation)."
            )

        # Check 2: Frozen plugin downgrade rejection (ADR-005)
        if operating_level < self._security_level and not self._allow_downgrade:
            raise SecurityValidationError(
                f"{type(self).__name__} is frozen at {self._security_level.name} "
                f"(allow_downgrade=False). Cannot operate at lower level {operating_level.name}. "
                f"This plugin requires exact level matching and does not support trusted downgrade."
            )


__all__ = ["BasePlugin"]
