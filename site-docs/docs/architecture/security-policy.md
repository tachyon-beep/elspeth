# Elspeth Security Policy

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Status**: Active
**Classification**: OFFICIAL

---

## Executive Summary

Elspeth implements a **defense-in-depth security architecture** based on Bell-LaPadula Multi-Level Security (MLS) principles. This policy consolidates 7 Architecture Decision Records (ADRs 002, 002a, 002b, 003, 004, 005, 006) into a cohesive security framework for protecting classified data ranging from UNOFFICIAL to SECRET.

### Core Security Guarantees

1. **Mandatory Access Control (MAC)**: Pipeline-wide security level enforcement based on minimum clearance principle
2. **Immutable Classification**: Data classifications cannot be downgraded once assigned (high water mark)
3. **Plugin Validation**: All plugins undergo security clearance validation before data retrieval
4. **Fail-Fast Enforcement**: Security violations abort pipelines before data access
5. **Fail-Loud Invariants**: Critical security violations trigger emergency logging and platform termination
6. **Defense in Depth**: Multiple independent security layers (type system, runtime checks, policy enforcement, testing)

### Applicable Security Levels

Elspeth uses Australian Protective Security Policy Framework (PSPF) classifications:

| Level | Numeric | Description | Example Use Cases |
|-------|---------|-------------|-------------------|
| **UNOFFICIAL** | 0 | Publicly releasable information | Public datasets, test data, marketing content |
| **OFFICIAL** | 1 | Government/business information requiring basic protection | Internal reports, business analytics, operational data |
| **OFFICIAL SENSITIVE** | 2 | Information requiring additional safeguards | Personnel records, procurement data, sensitive research |
| **PROTECTED** | 3 | High-impact information requiring strong protection | Security assessments, commercial-in-confidence, privacy data |
| **SECRET** | 4 | Very high-impact information, substantial damage if disclosed | National security, classified research, intelligence data |

---

## Policy 1: Multi-Level Security (MLS) Enforcement

**Source**: ADR-002
**Status**: Mandatory
**Enforcement**: Compile-time (MyPy) + Runtime (suite_runner.py) + Test (CI)

### 1.1 Bell-LaPadula Access Control Model

Elspeth implements the **Bell-LaPadula "no read up, no write down"** security model with the following rules:

#### Rule 1: Simple Security Property ("No Read Up")

> A subject (plugin) at a given security level cannot READ information classified at a HIGHER level.

**Implementation**: Plugins with LOWER clearance cannot operate in pipelines with HIGHER operating levels.

**Example (REJECTION)**:
```yaml
# ❌ ABORTS: UNOFFICIAL datasource cannot operate in SECRET pipeline
datasource:
  type: csv_local
  security_level: UNOFFICIAL

transform:
  type: azure_openai
  security_level: SECRET

# Operating level = min(UNOFFICIAL, SECRET) = UNOFFICIAL
# Transform validation: UNOFFICIAL < SECRET → REJECT (insufficient clearance)
```

**Example (SUCCESS)**:
```yaml
# ✅ SUCCESS: SECRET datasource can operate in UNOFFICIAL pipeline (trusted downgrade)
datasource:
  type: azure_blob
  security_level: SECRET
  allow_downgrade: true  # Explicit opt-in for trusted downgrade

transform:
  type: mock_llm
  security_level: UNOFFICIAL

# Operating level = min(SECRET, UNOFFICIAL) = UNOFFICIAL
# Datasource validation: UNOFFICIAL < SECRET and allow_downgrade=true → ALLOW (filters data)
```

#### Rule 2: Star Property ("No Write Down")

> A subject (plugin) at a given security level cannot WRITE information to a LOWER classification level without explicit authorization.

**Implementation**: Data classifications can only INCREASE via explicit `with_uplifted_classification()` calls. Downgrade attempts raise `SecurityCriticalError`.

**Example (REJECTION)**:
```python
# ❌ CRITICAL ERROR: Classification downgrade violates invariant
secret_frame = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.SECRET)
result = secret_frame.with_uplifted_classification(SecurityLevel.UNOFFICIAL)
# → Raises SecurityCriticalError! Platform terminates immediately.
```

**Example (SUCCESS)**:
```python
# ✅ SUCCESS: Classification uplift is allowed (high water mark)
unofficial_frame = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.UNOFFICIAL)
result = unofficial_frame.with_uplifted_classification(SecurityLevel.SECRET)
# → Returns new frame with SECRET classification
```

### 1.2 Operating Level Computation

The **operating level** is the minimum security level across ALL pipeline components:

```python
operating_level = min(
    datasource.security_level,
    transform.security_level,
    sink1.security_level,
    sink2.security_level,
    # ... all other plugins
)
```

**Validation Sequence**:

1. **Pre-Execution Validation** (fail-fast, before data retrieval):
   - Collect all plugin security levels
   - Compute operating level as minimum
   - Validate each plugin can operate at computed level
   - ABORT pipeline if any validation fails

2. **Runtime Classification Checks**:
   - Datasource creates `ClassifiedDataFrame` with declared level
   - Transforms preserve or uplift classification (never downgrade)
   - Sinks verify input classification matches expectations

3. **Sink Chaining Validation**:
   - Each sink validates it can accept the output classification
   - Chained sinks (artifact pipeline) validate dependency classification compatibility

### 1.3 Bell-LaPadula Directionality: Data vs Plugin Operations

**CRITICAL DISTINCTION**: Data classifications and plugin operations move in OPPOSITE directions:

| Aspect | Direction | Enforcement | Example |
|--------|-----------|-------------|---------|
| **Data Classifications** | Can only INCREASE | `with_uplifted_classification()` | UNOFFICIAL → OFFICIAL → SECRET |
| **Plugin Operations** | Can only DECREASE | `allow_downgrade=True` | SECRET → OFFICIAL → UNOFFICIAL |

**Forbidden Operations**:
- ❌ UNOFFICIAL plugin operating at SECRET level (insufficient clearance)
- ❌ SECRET data downgrading to UNOFFICIAL (no write down)
- ❌ Frozen plugin (allow_downgrade=False) operating below declared level

**Allowed Operations**:
- ✅ SECRET plugin operating at UNOFFICIAL level (if allow_downgrade=True - trusted to filter)
- ✅ UNOFFICIAL data uplifted to SECRET (explicit via with_uplifted_classification())
- ✅ Frozen plugin operating at EXACT declared level only

### 1.4 Compliance Requirements

**Implementation Checklist**:
- [x] All plugins MUST declare `security_level` parameter
- [x] All plugins MUST declare `allow_downgrade` parameter (no default)
- [x] Operating level computed BEFORE data retrieval
- [x] Validation failures ABORT pipeline with `SecurityValidationError`
- [x] All components validated via `validate_can_operate_at_level()`
- [x] Pipeline execution logs include security level in audit trail

**Audit Evidence**:
- Security level computation: `src/elspeth/core/experiments/suite_runner.py:_compute_operating_level()`
- Validation enforcement: `src/elspeth/core/experiments/suite_runner.py:_validate_component_clearances()`
- Test coverage: `tests/test_adr002_*.py` (Bell-LaPadula scenarios)

---

## Policy 2: Trusted Container Model

**Source**: ADR-002a
**Status**: Mandatory
**Enforcement**: Compile-time (frozen dataclass) + Runtime (factory method) + Test (CI)

### 2.1 ClassifiedDataFrame Immutability

All classified data MUST be encapsulated in `ClassifiedDataFrame` containers with the following guarantees:

1. **Immutable Classification**: Security metadata cannot be modified after creation
2. **Datasource-Only Creation**: Only datasources can create fresh containers (prevents laundering)
3. **Content Mutability**: Data content CAN be modified (e.g., adding columns, filtering rows)
4. **Classification Propagation**: Transformations create new containers preserving/uplifting classification

### 2.2 Container Creation Rules

#### Rule 1: Datasource-Only Factory Method

```python
# ✅ ALLOWED: Datasource creating ClassifiedDataFrame
@dataclass(frozen=True)
class ClassifiedDataFrame:
    data: pd.DataFrame
    classification: SecurityLevel

    @classmethod
    def create_from_datasource(
        cls,
        data: pd.DataFrame,
        classification: SecurityLevel
    ) -> "ClassifiedDataFrame":
        """Factory method - ONLY datasources may call this."""
        return cls(data=data, classification=classification)
```

**Enforcement**: Code review + convention (future: decorator validation)

#### Rule 2: Transform Classification Preservation

```python
# ✅ ALLOWED: Transform preserving classification
def transform(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    processed_data = self._process(frame.data)
    # New container, SAME or HIGHER classification
    return ClassifiedDataFrame(
        data=processed_data,
        classification=frame.classification  # Preserved
    )
```

#### Rule 3: Explicit Uplift Only

```python
# ✅ ALLOWED: Explicit classification uplift
def transform(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
    processed_data = self._process(frame.data)
    plugin_level = self.get_security_level()
    target_level = max(frame.classification, plugin_level)
    return frame.with_uplifted_classification(target_level)
```

### 2.3 Attack Scenario Prevention

**Threat**: Classification Laundering Attack

A malicious plugin creates a "fresh" ClassifiedDataFrame with LOWER classification to bypass MLS controls:

```python
# ❌ PREVENTED: Malicious plugin laundering SECRET data as UNOFFICIAL
class MaliciousTransform(BasePlugin):
    def transform(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
        # Received SECRET frame
        assert frame.classification == SecurityLevel.SECRET

        # ATTACK: Create "fresh" frame with UNOFFICIAL classification
        # This would allow SECRET data to reach UNOFFICIAL sinks!
        laundered = ClassifiedDataFrame.create_from_datasource(
            frame.data,  # SECRET data
            SecurityLevel.UNOFFICIAL  # ❌ Laundered classification
        )
        return laundered
```

**Defense**:
- Factory method convention: ONLY datasources create containers
- Code review: Grep for `create_from_datasource` in transform code
- Future enhancement: Decorator validation or capability-based security

### 2.4 Compliance Requirements

**Implementation Checklist**:
- [x] ClassifiedDataFrame is a frozen dataclass (immutable fields)
- [x] Only datasources use `create_from_datasource()`
- [x] Transforms use existing containers or `with_uplifted_classification()`
- [x] No direct ClassifiedDataFrame() constructor calls outside core
- [x] Audit trail logs classification at each pipeline stage

**Audit Evidence**:
- Container implementation: `src/elspeth/core/security/classified_data.py`
- Test coverage: `tests/test_classified_dataframe.py`
- Code review checklist: No `create_from_datasource()` in `src/elspeth/plugins/nodes/transforms/`

---

## Policy 3: Immutable Security Policy Metadata

**Source**: ADR-002b
**Status**: Mandatory
**Enforcement**: Compile-time (code review) + Registry (schema validation) + CI (lint rules)

### 3.1 Author-Owned Security Policy

Security policy metadata is **immutable, author-owned, and signed**. Operators cannot override security policy through configuration, environment variables, or runtime hooks.

#### Rule 1: Immutable Policy Fields

The following fields are defined **solely in plugin code** by the author:
- `security_level`: Plugin's security clearance
- `allow_downgrade`: Whether plugin can operate at lower levels
- Future policy fields: `max_operating_level`, compliance tags, etc.

**Forbidden**: Configuration-driven policy overrides

```yaml
# ❌ FORBIDDEN: Cannot override security policy via config
datasource:
  type: azure_blob
  security_level: PROTECTED  # ❌ REJECTED by registry
  allow_downgrade: false     # ❌ REJECTED by registry
```

**Correct**: Policy defined in code only

```python
# ✅ CORRECT: Policy hard-coded by plugin author
class AzureBlobDatasource(BasePlugin):
    def __init__(self, *, config_path: str, profile: str):
        # Policy is hard-coded, NOT configurable
        super().__init__(
            security_level=SecurityLevel.PROTECTED,
            allow_downgrade=True  # Author's decision
        )
        # ... rest of initialization
```

#### Rule 2: Registry Enforcement

Plugin registries **reject registration schemas** that expose policy fields as configurable parameters.

**Factory Implementation**:
```python
def create_azure_blob_datasource(opts: dict, ctx: PluginContext) -> AzureBlobDatasource:
    """Factory ignores security policy fields from config."""
    # Strip security policy fields if present (defensive)
    safe_opts = {k: v for k, v in opts.items()
                 if k not in ("security_level", "allow_downgrade")}

    # Plugin sets policy internally
    return AzureBlobDatasource(**safe_opts)
```

**Registry Schema**:
```python
AZURE_BLOB_SCHEMA = {
    "type": "object",
    "properties": {
        "config_path": {"type": "string"},
        "profile": {"type": "string"},
        # ❌ NO security_level or allow_downgrade properties
    },
    "required": ["config_path", "profile"]
}
```

#### Rule 3: Signature Attestation

Published plugins include policy metadata in the signing manifest. Security review verifies the implementation matches declared policy prior to signing.

**Signing Manifest**:
```json
{
  "plugin": "AzureBlobDatasource",
  "version": "1.2.0",
  "security_policy": {
    "security_level": "PROTECTED",
    "allow_downgrade": true,
    "policy_hash": "sha256:abc123..."
  },
  "signature": "..."
}
```

**Verification Process**:
1. Security team reviews plugin code
2. Extracts declared policy (`security_level`, `allow_downgrade`)
3. Verifies policy matches security requirements
4. Signs plugin with attested policy metadata
5. Runtime validates signature matches running code

### 3.2 Frozen vs Trusted Downgrade Selection

Authors choose security policy **explicitly at development time**, not configuration time:

| Author Choice | Policy Declaration | Operator Selection |
|---------------|-------------------|-------------------|
| **Trusted Downgrade** | `allow_downgrade=True` in code | Use this plugin for mixed-classification workflows |
| **Frozen** | `allow_downgrade=False` in code | Use this plugin ONLY for dedicated classification domains |

**Operator Workflow**:
```yaml
# Operator selects the RIGHT PLUGIN, not the right configuration
datasource:
  type: azure_blob_trusted  # allow_downgrade=True (hard-coded)

# OR

datasource:
  type: azure_blob_frozen   # allow_downgrade=False (hard-coded)
```

### 3.3 Attack Scenario Prevention

**Threat**: Configuration-driven security downgrade

An operator (malicious or misconfigured) attempts to override security policy via YAML:

```yaml
# ATTACK: Try to override frozen plugin to allow downgrade
datasource:
  type: dedicated_secret_source  # Author set allow_downgrade=False
  allow_downgrade: true          # ❌ ATTACKER attempts override
```

**Defense**:
1. **Registry**: Rejects schema with policy fields → Plugin won't register
2. **Factory**: Strips policy fields from opts → Override ignored
3. **Plugin**: Hard-coded policy in `__init__` → Immutable
4. **CI Lint**: Detects policy fields in YAML → Build fails

**Result**: Attack prevented at 4 independent layers.

### 3.4 Compliance Requirements

**Implementation Checklist**:
- [x] All plugins define policy in `__init__`, not from parameters
- [x] Registry schemas exclude `security_level` and `allow_downgrade`
- [x] Factory functions strip policy fields from configuration
- [x] CI lint rules detect policy fields in YAML configs
- [x] Signing manifests include attested policy metadata
- [x] Security review process validates policy before signing

**Audit Evidence**:
- Plugin implementation: Hard-coded policy in `super().__init__()`
- Registry schemas: No policy fields in JSON schemas
- CI lint: `.github/workflows/config-lint.yml`
- Signing manifest: `manifests/plugins/*.json`

---

## Policy 4: Plugin Security Architecture

**Source**: ADR-003, ADR-004
**Status**: Mandatory
**Enforcement**: Compile-time (ABC inheritance, MyPy) + Runtime (registry, isinstance()) + Test (CI)

### 4.1 Mandatory BasePlugin Inheritance ("Security Bones")

All plugins MUST explicitly inherit from `BasePlugin` ABC to participate in security validation.

#### Rule 1: Nominal Typing Requirement

```python
from abc import ABC, abstractmethod

class BasePlugin(ABC):
    """Abstract base class with concrete security enforcement ("security bones")."""

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,  # MANDATORY, no default
        **kwargs
    ):
        """Initialize plugin with security parameters.

        Args:
            security_level: Plugin's security clearance (MANDATORY).
            allow_downgrade: Whether plugin can operate at lower levels (MANDATORY).
                - True: Trusted downgrade (can filter to lower levels)
                - False: Frozen plugin (exact level matching only)

        Raises:
            TypeError: If allow_downgrade not provided (no default).
            ValueError: If security_level is None.
        """
        if security_level is None:
            raise ValueError("security_level cannot be None (ADR-004)")

        self._security_level = security_level
        self._allow_downgrade = allow_downgrade
        super().__init__(**kwargs)

    @property
    def security_level(self) -> SecurityLevel:
        """Read-only security level property."""
        return self._security_level

    @property
    def allow_downgrade(self) -> bool:
        """Read-only downgrade permission property."""
        return self._allow_downgrade

    @final  # Cannot be overridden - sealed for security
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        """Validate plugin can operate at pipeline level (SEALED - security enforcement).

        Raises:
            SecurityValidationError: If plugin cannot operate at given level.
        """
        # Check 1: Insufficient clearance (Bell-LaPadula "no read up")
        if operating_level > self._security_level:
            raise SecurityValidationError(
                f"{type(self).__name__} has clearance {self._security_level.name}, "
                f"but pipeline requires {operating_level.name}. Insufficient clearance."
            )

        # Check 2: Frozen plugin downgrade rejection
        if operating_level < self._security_level and not self._allow_downgrade:
            raise SecurityValidationError(
                f"{type(self).__name__} is frozen at {self._security_level.name} "
                f"(allow_downgrade=False). Cannot operate at lower level {operating_level.name}."
            )

        # Check 3: Valid operation (exact match or trusted downgrade)
```

**Why Sealed Methods (@final)?**

Preventing override attacks:
```python
# ❌ PREVENTED: Malicious override bypassing security
class MaliciousPlugin(BasePlugin):
    # This override will FAIL due to @final + __init_subclass__ enforcement
    def validate_can_operate_at_level(self, operating_level: SecurityLevel) -> None:
        pass  # ❌ Bypass attempt - blocked by @final decorator
```

#### Rule 2: Central Plugin Type Registry

All plugin types MUST be registered in `PLUGIN_TYPE_REGISTRY` to ensure security validation coverage.

```python
# src/elspeth/core/base/plugin_types.py
PLUGIN_TYPE_REGISTRY = {
    "llm_client": {"type": "singleton", "protocol": "LLMClient"},
    "llm_middlewares": {"type": "list", "protocol": "LLMMiddleware"},
    "row_plugins": {"type": "list", "protocol": "RowExperimentPlugin"},
    "aggregator_plugins": {"type": "list", "protocol": "AggregationExperimentPlugin"},
    "validation_plugins": {"type": "list", "protocol": "ValidationPlugin"},
    "early_stop_plugins": {"type": "list", "protocol": "EarlyStopPlugin"},
}

def collect_all_plugins(runner) -> list[BasePlugin]:
    """Collect all plugins using registry (ensures completeness)."""
    plugins = []
    for attr_name, config in PLUGIN_TYPE_REGISTRY.items():
        attr = getattr(runner, attr_name, None)
        if attr is None:
            continue

        if config["type"] == "singleton":
            if isinstance(attr, BasePlugin):
                plugins.append(attr)
        elif config["type"] == "list":
            plugins.extend([p for p in attr if isinstance(p, BasePlugin)])

    return plugins
```

**Registry Completeness Test**:
```python
def test_plugin_registry_complete():
    """SECURITY: Verify all plugin types registered."""
    runner_attrs = [
        a for a in dir(ExperimentRunner)
        if (a.endswith('_plugins') or a.endswith('_middlewares') or a.endswith('_client'))
        and not a.startswith('_')
    ]

    registered = set(PLUGIN_TYPE_REGISTRY.keys())
    missing = set(runner_attrs) - registered

    assert not missing, (
        f"SECURITY: {missing} exist in ExperimentRunner but NOT in registry. "
        f"Will bypass ADR-002 validation!"
    )
```

### 4.2 Defense Matrix

| Failure Mode | Layer 1 (ABC) | Layer 2 (Registry) | Layer 3 (Test) | Outcome |
|--------------|---------------|-------------------|----------------|---------|
| Accidental class with matching methods | ✅ **CATCHES** | - | - | Rejected (no inheritance) |
| New plugin type, forgot to register | - | ❌ Misses | ✅ **CATCHES** | Test fails |
| New plugin type, forgot both | ✅ **CATCHES** | ❌ Misses | ✅ **CATCHES** | Test fails + rejected |
| Malicious override of sealed method | ✅ **CATCHES** | - | - | `@final` blocks override |
| Correct implementation | ✅ Passes | ✅ Passes | ✅ Passes | Works ✅ |

**Result**: No single point of failure. Multiple independent defenses.

### 4.3 Compliance Requirements

**Implementation Checklist**:
- [x] All plugins inherit from BasePlugin ABC
- [x] All plugins call `super().__init__(security_level=..., allow_downgrade=...)`
- [x] No plugins override `validate_can_operate_at_level()` (sealed)
- [x] All plugin types registered in PLUGIN_TYPE_REGISTRY
- [x] Registry completeness test passes in CI

**Audit Evidence**:
- ABC definition: `src/elspeth/core/base/plugin.py`
- Registry: `src/elspeth/core/base/plugin_types.py`
- Test coverage: `tests/test_plugin_registry.py::test_plugin_registry_complete`

---

## Policy 5: Frozen Plugin Capability

**Source**: ADR-005
**Status**: Mandatory (Explicit Choice Required)
**Enforcement**: Compile-time (no default parameter) + Runtime (validation) + Test (CI)

### 5.1 Trusted Downgrade vs Frozen Plugins

Elspeth supports two security postures via the `allow_downgrade` parameter:

| Posture | `allow_downgrade` | Behavior | Use Cases |
|---------|-------------------|----------|-----------|
| **Trusted Downgrade** | `True` | Plugin can operate at SAME or LOWER levels | General-purpose plugins, cloud environments, mixed-classification workflows |
| **Frozen Plugin** | `False` | Plugin can ONLY operate at EXACT declared level | Dedicated classification domains, regulatory compliance, air-gapped networks |

⚠️ **BREAKING CHANGE**: `allow_downgrade` has NO default value. All plugins MUST explicitly declare their security posture.

### 5.2 Trusted Downgrade Pattern (allow_downgrade=True)

**Scenario**: Cloud-based datasource handles data at multiple classification levels

```python
class AzureBlobDataSource(BasePlugin, DataSource):
    def __init__(self, *, security_level: SecurityLevel = SecurityLevel.SECRET):
        # Explicit allow_downgrade=True → trusted downgrade enabled
        super().__init__(security_level=security_level, allow_downgrade=True)

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        # Can operate at OFFICIAL, UNOFFICIAL if pipeline requires
        # Responsible for filtering SECRET-tagged blobs appropriately
        operating_level = context.security_level

        if operating_level < SecurityLevel.SECRET:
            # Filter blobs to only include data at operating_level or below
            filtered_data = self._filter_by_classification(operating_level)
        else:
            # Load all data (including SECRET)
            filtered_data = self._load_all_data()

        return ClassifiedDataFrame.create_from_datasource(
            filtered_data,
            operating_level
        )
```

**Validation**:
- ✅ Operates at SECRET level: `validate_can_operate_at_level(SECRET)` → PASS
- ✅ Operates at OFFICIAL level: `validate_can_operate_at_level(OFFICIAL)` → PASS (trusted downgrade)
- ✅ Operates at UNOFFICIAL level: `validate_can_operate_at_level(UNOFFICIAL)` → PASS (trusted downgrade)
- ❌ Operates at higher level: Not possible (SECRET is highest)

### 5.3 Frozen Plugin Pattern (allow_downgrade=False)

**Scenario**: Dedicated SECRET-only infrastructure (air-gapped, regulatory compliance)

```python
class DedicatedSecretDataSource(BasePlugin, DataSource):
    def __init__(self):
        # Explicit allow_downgrade=False → frozen at SECRET level
        super().__init__(
            security_level=SecurityLevel.SECRET,
            allow_downgrade=False
        )

    def load_data(self, context: PluginContext) -> ClassifiedDataFrame:
        # Will ONLY operate in SECRET pipelines
        # Pipeline construction fails if configured with lower-clearance components
        return ClassifiedDataFrame.create_from_datasource(
            self._load_secret_data(),
            SecurityLevel.SECRET
        )
```

**Validation**:
- ✅ Operates at SECRET level: `validate_can_operate_at_level(SECRET)` → PASS (exact match)
- ❌ Operates at OFFICIAL level: `validate_can_operate_at_level(OFFICIAL)` → FAIL (frozen, cannot downgrade)
- ❌ Operates at UNOFFICIAL level: `validate_can_operate_at_level(UNOFFICIAL)` → FAIL (frozen, cannot downgrade)

**Error Message**:
```
SecurityValidationError: DedicatedSecretDataSource is frozen at SECRET
(allow_downgrade=False). Cannot operate at lower level OFFICIAL.
This plugin requires exact level matching and does not support trusted downgrade.
```

### 5.4 Compliance Requirements

**Implementation Checklist**:
- [x] All plugins explicitly set `allow_downgrade=True` or `allow_downgrade=False`
- [x] No plugins rely on default value (TypeError if omitted)
- [x] Frozen plugins documented in deployment guide
- [x] Infrastructure supports exact level matching for frozen plugins

**Audit Evidence**:
- Validation logic: `src/elspeth/core/base/plugin.py:validate_can_operate_at_level()`
- Test coverage: `tests/test_baseplugin_frozen.py`
- Configuration examples: `docs/user-guide/configuration.md`

---

## Policy 6: Security-Critical Exception Policy

**Source**: ADR-006
**Status**: Mandatory
**Enforcement**: Static Analysis (Ruff, MyPy) + Pre-Commit (AST parsing) + CI (grep-based) + Code Review

### 6.1 Dual-Exception Model

Elspeth distinguishes between **expected security boundaries** and **impossible security invariant violations**:

```
Exception
├── SecurityValidationError  ✅ Catchable - Expected boundaries
└── SecurityCriticalError    🚨 Policy-forbidden - Invariant violations
```

| Exception | Purpose | Catchability | Use Cases |
|-----------|---------|--------------|-----------|
| **SecurityValidationError** | Expected security boundaries | ✅ May be caught in production | Start-time validation failures, clearance mismatches, permission denied |
| **SecurityCriticalError** | Impossible invariant violations | ❌ MUST NOT be caught in production (tests only)*  | Classification downgrades, metadata tampering, container boundary violations |

\* **Allowable scope**: Only unit/integration tests (under `tests/`) or generated scaffolding specifically tagged for auditing may catch this exception. All first-party production modules (`src/`) are linted to reject catches, and glue code (e.g., orchestration notebooks, Airflow DAGs) must either live under `tests/` or opt into the same lint rule set to guarantee enforcement.

### 6.2 SecurityValidationError (Expected Boundaries)

**Use for expected security validation failures** where graceful error handling is appropriate:

```python
# Expected validation failure - user misconfigured pipeline
def _validate_component_clearances(self, operating_level: SecurityLevel) -> None:
    """Validate all components can operate at computed level."""
    try:
        self.datasource.validate_can_operate_at_level(operating_level)
    except Exception as e:
        raise SecurityValidationError(  # ✅ Expected, catchable
            f"ADR-002 Start-Time Validation Failed: Datasource cannot operate "
            f"at {operating_level.name} level: {e}"
        ) from e
```

**Production code MAY catch this**:
```python
try:
    suite.run()
except SecurityValidationError as e:
    logger.error(f"Pipeline validation failed: {e}")
    notify_admin(f"Invalid pipeline configuration: {e}")
    # Graceful degradation, notify user, etc.
```

### 6.3 SecurityCriticalError (Invariant Violations)

**Use for "should never happen" scenarios** indicating bugs or attacks:

```python
def with_uplifted_classification(self, new_level: SecurityLevel) -> ClassifiedDataFrame:
    """Uplift classification (high water mark principle).

    Raises:
        SecurityCriticalError: If downgrade attempted (CRITICAL - platform terminates).
    """
    if new_level < self.classification:
        # This should NEVER happen - indicates bug or attack
        raise SecurityCriticalError(  # 🚨 Platform terminates
            f"CRITICAL: Classification downgrade from {self.classification.name} "
            f"to {new_level.name} violates high water mark invariant (ADR-002-A)",
            evidence={
                "current_level": self.classification.name,
                "attempted_level": new_level.name,
                "data_shape": self.data.shape,
            },
            cve_id="CVE-ADR-002-A-004",
            classification_level=self.classification,
        )

    return ClassifiedDataFrame(self.data, new_level)
```

**Production code MUST NOT catch this** (policy-enforced):
```python
# ❌ FORBIDDEN in production code (src/)
try:
    result = classified.with_uplifted_classification(level)
except SecurityCriticalError:  # ❌ Policy violation - blocked by CI
    pass  # ❌ Execution continues with compromised state
```

**Tests MAY catch this** (verification):
```python
# ✅ ALLOWED in tests (tests/)
def test_classification_downgrade_raises_critical_error():
    """Verify downgrade attempts raise SecurityCriticalError."""
    classified = ClassifiedDataFrame.create_from_datasource(df, SecurityLevel.SECRET)

    with pytest.raises(SecurityCriticalError) as exc_info:
        classified.with_uplifted_classification(SecurityLevel.UNOFFICIAL)  # Downgrade!

    assert "downgrade" in str(exc_info.value).lower()
    assert exc_info.value.cve_id == "CVE-ADR-002-A-004"
```

### 6.4 Emergency Logging

`SecurityCriticalError` automatically logs to multiple channels BEFORE propagating:

```python
class SecurityCriticalError(Exception):
    def __init__(self, message: str, *, evidence: dict, cve_id: str, ...):
        super().__init__(message)
        self.evidence = evidence
        self.cve_id = cve_id

        # Emergency logging BEFORE exception propagates
        self._log_critical_security_event(message, evidence, cve_id)

    def _log_critical_security_event(self, ...):
        """Log to multiple channels for redundancy."""
        # 1. stderr - always visible (container logs)
        print(f"🚨 CRITICAL SECURITY ERROR - PLATFORM TERMINATING 🚨", file=sys.stderr)
        print(json.dumps(event, indent=2), file=sys.stderr)

        # 2. Audit logger (structured JSON for SIEM)
        logger.critical(json.dumps(event))

        # 3. Security event stream (Azure Monitor, Splunk, etc.)
        # ...
```

**Audit Event Structure**:
```json
{
  "timestamp": "2025-10-26T10:30:15.123456+00:00",
  "severity": "CRITICAL",
  "event_type": "SECURITY_CRITICAL_ERROR",
  "event_class": "INVARIANT_VIOLATION",
  "cve_id": "CVE-ADR-002-A-004",
  "classification_level": "SECRET",
  "message": "CRITICAL: Classification downgrade from SECRET to UNOFFICIAL...",
  "evidence": {
    "current_level": "SECRET",
    "attempted_level": "UNOFFICIAL",
    "data_shape": [100, 5]
  },
  "process_id": 12345,
  "traceback": "..."
}
```

### 6.5 Policy Enforcement Layers

**Layer 1: Ruff Linting (Fast Feedback)**

```toml
# pyproject.toml
[tool.ruff.lint]
extend-select = ["TRY"]  # Exception handling best practices

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["TRY302"]  # Allow catching SecurityCriticalError in tests
```

**Layer 2: Pre-Commit Hook (Prevents Commits)**

```bash
# .pre-commit-config.yaml runs AST-based script
python scripts/check_security_exception_policy.py src/**/*.py
```

Script detects:
- Direct catches: `except SecurityCriticalError:`
- Aliased catches: `except SCE:` (where SCE is imported)
- Tuple catches: `except (ValueError, SecurityCriticalError):`
- Warns on broad catches: `except Exception:`, `except:`

**Layer 3: CI/CD (Blocks Merges)**

```yaml
# .github/workflows/security-policy.yml
- name: Check for forbidden SecurityCriticalError catches
  run: |
    VIOLATIONS=$(grep -rn "except.*SecurityCriticalError" src/ || true)
    if [ -n "$VIOLATIONS" ]; then
      echo "❌ POLICY VIOLATION: SecurityCriticalError caught in production!"
      exit 1
    fi
```

**Layer 4: Code Review (Human Verification)**

Pull request checklist:
- [ ] No `SecurityCriticalError` catches in production code (src/)
- [ ] Test code properly validates invariant violations
- [ ] Security-critical paths have defensive checks

### 6.6 Compliance Requirements

**Implementation Checklist**:
- [x] `SecurityCriticalError` defined with emergency logging
- [x] Production code (src/) contains zero SecurityCriticalError catches
- [x] Test code (tests/) validates invariant violations raise SecurityCriticalError
- [x] Pre-commit hook blocks forbidden catches
- [x] CI enforces policy on all branches

**Audit Evidence**:
- Exception definition: `src/elspeth/core/security/exceptions.py`
- Policy script: `scripts/check_security_exception_policy.py`
- CI workflow: `.github/workflows/security-policy.yml`
- Test coverage: `tests/test_security_critical_exceptions.py`

---

## Policy Enforcement Summary

### Defense-in-Depth Layers

| Layer | Technology | Enforcement Point | Prevents |
|-------|-----------|-------------------|----------|
| **Type System** | MyPy, ABC inheritance | Compile-time (IDE, CI) | Accidental protocol compliance, type errors |
| **Runtime Checks** | `isinstance()`, sealed methods | Execution-time | Bypass via duck typing, malicious overrides |
| **Registry** | PLUGIN_TYPE_REGISTRY | Pipeline construction | Missing plugin types in validation |
| **Testing** | pytest, assertions | CI (merge gate) | Registry incompleteness, missing test coverage |
| **Static Analysis** | Ruff, custom AST parsers | Pre-commit, CI | Policy violations, broad exception catches |
| **Code Review** | Human review, checklists | PR approval | Logic errors, subtle security issues |

### Audit Trail Requirements

All security-relevant events MUST be logged to structured audit logs (`logs/run_*.jsonl`):

**Logged Events**:
1. Security level computation for each pipeline
2. Component clearance validation results (pass/fail)
3. Classification uplift operations (`with_uplifted_classification` calls)
4. Security validation failures (SecurityValidationError)
5. **CRITICAL**: Security invariant violations (SecurityCriticalError - emergency logging)
6. Plugin instantiation with security parameters
7. **Reproducibility bundle creation** (ADR-014 - tamper-evident archives for audit)

**Audit Log Format**:
```json
{
  "timestamp": "2025-10-26T10:30:15.123456+00:00",
  "run_id": "abc123...",
  "event_type": "SECURITY_VALIDATION",
  "security_level": "OFFICIAL",
  "component": "AzureBlobDataSource",
  "validation_result": "PASS",
  "details": {}
}
```

---

## Compliance Mapping

### Regulatory Framework Alignment

| Framework | Requirement | Elspeth Control | Evidence |
|-----------|-------------|-----------------|----------|
| **PSPF (Australia)** | Classification-based access control | Bell-LaPadula MLS (Policy 1) | ADR-002, suite_runner.py |
| **NIST SP 800-53** | AC-3 Access Enforcement | Mandatory plugin validation (Policy 3) | ADR-003, plugin_types.py |
| **ISO 27001** | A.9.4.1 Information access restriction | Operating level computation (Policy 1.2) | suite_runner.py:_compute_operating_level() |
| **Common Criteria** | FDP_IFC.1 Subset information flow control | Immutable classification (Policy 2) | ADR-002a, classified_data.py |
| **GDPR** | Article 32 Security of processing | Defense-in-depth (All Policies) | Full ADR suite (002-006) |
| **HIPAA** | §164.312(b) Audit controls | Reproducibility bundles with tamper-evident signatures | ADR-014, reproducibility_bundle.py |
| **PCI-DSS** | Requirement 10.2 Audit trail for security events | JSONL audit logs + signed reproducibility archives | ADR-014, logs/run_*.jsonl |
| **PSPF (Australia)** | Recordkeeping and audit | Mandatory reproducibility bundle in production mode | ADR-014, config/templates/production_suite.yaml |

### Certification Checklist

For security certification/accreditation, verify:

**Policy 1: MLS Enforcement**
- [ ] Operating level computed as min(all components)
- [ ] Validation performed BEFORE data retrieval
- [ ] All Bell-LaPadula rules enforced (no read up, no write down)
- [ ] Test coverage includes all SecurityLevel combinations

**Policy 2: Trusted Container**
- [ ] ClassifiedDataFrame is frozen dataclass
- [ ] Only datasources use `create_from_datasource()`
- [ ] Code review confirms no classification laundering
- [ ] Test coverage validates immutability

**Policy 3: Plugin Security**
- [ ] All plugins inherit BasePlugin ABC
- [ ] Plugin registry complete (test passes)
- [ ] Sealed methods cannot be overridden (@final)
- [ ] MyPy strict mode enforced

**Policy 4: Frozen Plugins**
- [ ] All plugins explicitly declare `allow_downgrade`
- [ ] Frozen plugins documented in deployment guide
- [ ] Infrastructure supports exact level matching
- [ ] Test coverage includes frozen scenarios

**Policy 5: Exception Policy**
- [ ] SecurityCriticalError defined with emergency logging
- [ ] Production code has zero forbidden catches (CI enforced)
- [ ] Pre-commit hook blocks policy violations
- [ ] Test coverage validates invariant violations

---

## Related Documentation

### Architecture Decision Records (ADRs)

- **[ADR-001: Design Philosophy](adrs.md#adr-001-design-philosophy)** - Security-first principles, fail-closed approach
- **[ADR-002: Multi-Level Security](adrs.md#adr-002-multi-level-security)** - Bell-LaPadula MLS model (full text)
- **[ADR-002a: Trusted Container Model](adrs.md#adr-002a-trusted-container-model)** - ClassifiedDataFrame immutability
- **[ADR-002b: Immutable Security Policy Metadata](adrs.md#adr-002b-immutable-security-policy-metadata)** - Author-owned policy, no config overrides
- **[ADR-003: Plugin Type Registry](adrs.md#adr-003-plugin-type-registry)** - Central registry for validation coverage
- **[ADR-004: Mandatory BasePlugin Inheritance](adrs.md#adr-004-mandatory-baseplugin-inheritance)** - Security bones design
- **[ADR-005: Frozen Plugin Capability](adrs.md#adr-005-frozen-plugin-capability)** - Strict level enforcement
- **[ADR-006: Security-Critical Exception Policy](adrs.md#adr-006-security-critical-exception-policy)** - Fail-loud invariants
- **[ADR-014: Tamper-Evident Reproducibility Bundle](adrs.md#adr-014-tamper-evident-reproducibility-bundle)** - Audit trail and compliance

### User Guides

- **[Security Model](../user-guide/security-model.md)** - Practical guide with worked examples
- **[Configuration](../user-guide/configuration.md)** - Security parameter reference

### Development Guides

- **[Architecture Overview](overview.md)** - System architecture with security components
- **[Execution Flow](execution-flow.md)** - Security checkpoint mapping

### Compliance Documents (Repository)

- `docs/compliance/incident-response.md` - Security incident response procedures
- `docs/compliance/CONTROL_INVENTORY.md` - Security control traceability
- `docs/compliance/TRACEABILITY_MATRIX.md` - Requirement-to-control mapping

---

## Document Metadata

**Effective Date**: 2025-10-26
**Review Cycle**: Quarterly
**Next Review**: 2026-01-26
**Document Owner**: Security Team
**Approvers**: Architecture Team, Security Team
**Classification**: OFFICIAL

**Change History**:
- 2025-10-26: Initial consolidated policy (v1.0) - Combined ADRs 002, 002a, 003, 004, 005, 006
- 2025-10-26: Added Policy 3 (ADR-002b) - Immutable Security Policy Metadata (v1.1)
- 2025-10-26: Added ADR-014 compliance mapping - Reproducibility bundles for audit (v1.2)

---

**🔒 This policy is MANDATORY for all Elspeth deployments handling classified data.**

For questions or clarifications, consult the [ADR Catalogue](adrs.md) or contact the Security Team.
