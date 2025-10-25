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
        >>> ds.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK
        >>> ds.validate_can_operate_at_level(SecurityLevel.UNOFFICIAL)  # ❌ Raises

    Attributes:
        _security_level (SecurityLevel): Plugin's security clearance (private storage).

    Properties:
        security_level (SecurityLevel): Read-only access to security clearance.

    Methods:
        get_security_level() -> SecurityLevel: Returns plugin's security clearance.
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
        sealed_methods = ("get_security_level", "validate_can_operate_at_level")

        for method_name in sealed_methods:
            if method_name in cls.__dict__:
                raise TypeError(
                    f"{cls.__name__} may not override {method_name} (ADR-004 security invariant). "
                    f"Security enforcement is provided by BasePlugin and cannot be customized. "
                    f"If you need custom security logic, please consult the architecture team."
                )

    def __init__(self, *, security_level: SecurityLevel, **kwargs: object) -> None:
        """Initialize BasePlugin with mandatory security level.

        Args:
            security_level: Plugin's security clearance (MANDATORY keyword-only argument).
            **kwargs: Additional keyword arguments passed to super().__init__().

        Raises:
            ValueError: If security_level is None.

        Design Notes:
            - security_level is keyword-only (forces explicit declaration)
            - Stored in private _security_level (discourages direct access)
            - Public access via .security_level property (read-only)
            - **kwargs allows cooperative multiple inheritance
        """
        if security_level is None:
            raise ValueError(f"{type(self).__name__}: security_level cannot be None (ADR-004 requirement)")

        self._security_level = security_level
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only property for security level (convenience accessor).

        This property allows convenient access to the security level in factory methods
        and other contexts where self.security_level is more readable than self.get_security_level().

        Returns:
            SecurityLevel: Plugin's security clearance.

        Example:
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET)
            >>> plugin.security_level  # ✅ Convenient access
            SecurityLevel.SECRET
            >>> plugin.security_level = SecurityLevel.UNOFFICIAL  # ❌ AttributeError (read-only)
        """
        return self._security_level

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
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate that plugin can operate at the given security level (SEALED).

        Bell-LaPadula Multi-Level Security (MLS) enforcement:
        - Plugin with HIGHER clearance can operate at LOWER level (declassification allowed)
        - Plugin with LOWER clearance CANNOT operate at HIGHER level (security violation)

        Args:
            operating_level: Security level of the pipeline/suite.

        Raises:
            SecurityValidationError: If operating_level < plugin's declared security_level.

        Design Notes:
            - This implements the "no write-up" rule from Bell-LaPadula MLS
            - Plugins refuse to participate in pipelines below their clearance
            - Fail-fast: Validation happens BEFORE any data processing

        Example:
            >>> plugin = MyPlugin(security_level=SecurityLevel.SECRET)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.SECRET)  # ✅ OK
            >>> plugin.validate_can_operate_at_level(SecurityLevel.TOP_SECRET)  # ✅ OK (upgrade)
            >>> plugin.validate_can_operate_at_level(SecurityLevel.OFFICIAL)  # ❌ Raises
        """
        if operating_level < self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} requires security level {self._security_level.name} "
                f"but pipeline operates at {operating_level.name}. "
                f"Cannot downgrade security clearance (Bell-LaPadula MLS violation)."
            )


__all__ = ["BasePlugin"]
