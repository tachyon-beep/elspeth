# ADR-002 Orchestrator Security Model - Clarification

**Document Purpose**: Clarifies the correct "minimum clearance envelope" model for ADR-002 implementation
**Date**: 2025-10-25
**Related**: `adr-002-implementation-gap.md`

---

## The Correct Security Model

### Minimum Clearance Envelope (Not "Datasource Blocks Low Sink")

**How it actually works:**

1. **Plugin Declaration Phase**: At job start, orchestrator asks all cryptographically signed plugins: "What's your security level?"

   ```python
   plugin_responses = {
       'datasource': 'SECRET',      # High security
       'llm_client': 'SECRET',      # High security
       'sink_prod': 'SECRET',       # High security
       'sink_debug': 'UNOFFICIAL'   # Low security - ONE bad actor
   }
   ```

2. **Orchestrator Operating Level Computation**: Orchestrator looks at all responses and says "I'm operating at the MINIMUM level"

   ```python
   orchestrator.operating_level = min(plugin_responses.values())
   # => 'UNOFFICIAL' (because of sink_debug)
   ```

3. **Start-Time Validation (MUST block)**: BEFORE any data retrieval, orchestrator asks each component: "Can you operate at UNOFFICIAL?"

   ```python
   for component_name, required_level in plugin_responses.items():
       if required_level > orchestrator.operating_level:
           raise SecurityError(
               f"Component '{component_name}' requires {required_level} "
               f"but orchestrator operating at {orchestrator.operating_level}. "
               f"Job CANNOT start."
           )

   # Result: Job fails because datasource, llm_client, and sink_prod ALL require SECRET
   # but orchestrator is at UNOFFICIAL
   ```

4. **Runtime Validation (Defense in Depth)**: Even if job somehow starts, **each plugin is responsible for its own behavior**

   ```python
   class SecretDataSource:
       security_level = SecurityLevel.SECRET

       def get_data(self, orchestrator_context):
           # Runtime check: Should NEVER come up if start-time validation works
           # BUT: If someone tricks the orchestrator, plugins still protect themselves
           if orchestrator_context.operating_level < self.security_level:
               raise SecurityError(
                   f"Datasource requires {self.security_level}, "
                   f"orchestrator operating at {orchestrator_context.operating_level}. "
                   f"REFUSING to hand over data (defense in depth failsafe)."
               )
           return self._actual_classified_data
   ```

---

## Key Principles

### 1. Orchestrator Operates at Minimum (Clearance Envelope)

**Mental model**: The orchestrator is like a "clearance envelope". It operates at the LOWEST clearance level among all participants.

- ✅ Low-security components happy in high-security envelope (they just won't see classified data)
- ❌ High-security components refuse to participate in low-security envelope

**NOT**: "High-security datasource blocks low-security sink"
**YES**: "Orchestrator operates at minimum; high-security components refuse low-envelope"

### 2. All Components Validate, Not Just Datasource

**Mental model**: Every component with security requirements validates independently.

```python
# WRONG: Only datasource validates
if datasource.security_level > pipeline_min:
    raise SecurityError("Datasource can't operate")

# CORRECT: ALL components validate
for component in all_components:
    if component.security_level > orchestrator.operating_level:
        raise SecurityError(f"{component} can't operate at {orchestrator.operating_level}")
```

### 3. Defense in Depth: Start-Time + Runtime

**Start-time validation (PRIMARY)**:
- Orchestrator computes operating level
- Validates ALL components can operate at that level
- Job **fails to start** if any component requires higher level
- This **MUST** catch all misconfigurations

**Runtime validation (FAILSAFE)**:
- Each plugin independently validates when handling data
- Should **NEVER** trigger if start-time validation works correctly
- Protects against: "What if someone tricks the orchestrator into starting?"
- Plugins responsible for their own security, don't trust orchestrator alone

**As user emphasized**: Runtime validation should never come up because start-time MUST block it. But if someone finds a way to trick the orchestrator, plugins still protect themselves.

---

## Implementation: Three Helper Methods

### Method 1: `_collect_plugin_security_levels()`

**Purpose**: Ask all signed plugins for their security levels

**Returns**: `dict[str, str]` mapping component names to levels
```python
{
    'datasource': 'SECRET',
    'llm_client': 'SECRET',
    'sink_exp1_0': 'SECRET',
    'sink_exp2_0': 'UNOFFICIAL',
    'middleware_0': 'OFFICIAL'
}
```

### Method 2: `_compute_orchestrator_operating_level()`

**Purpose**: Compute `min(all plugin levels)` - orchestrator's operating level

**Returns**: `str` - minimum level (e.g., `'UNOFFICIAL'`)

### Method 3: `_validate_components_at_operating_level()`

**Purpose**: Validate ALL components can operate at orchestrator's level (start-time check)

**Raises**: `SecurityError` if ANY component requires higher than operating level

**This is the MUST BLOCK validation**: Job fails to start if misconfigured.

---

## Integration Point in suite_runner.py

**After line 310** (after DataFrame validation, before middleware notification):

```python
# Line 310 (existing)
ctx = SuiteExecutionContext(
    results={},
    baseline_payload=None,
    baseline_experiment=self.suite.baseline,
)

# NEW: ADR-002 orchestrator operating level enforcement
plugin_security_levels = self._collect_plugin_security_levels(
    suite=self.suite,
    defaults=defaults,
    sink_factory=sink_factory,
)

# Orchestrator operates at minimum (clearance envelope model)
orchestrator_operating_level = self._compute_orchestrator_operating_level(
    plugin_security_levels
)

# FAIL-FAST: Validate ALL components can operate at orchestrator's level
self._validate_components_at_operating_level(
    plugin_security_levels,
    orchestrator_operating_level
)

# Set operating level in context for runtime validation (defense in depth)
ctx.orchestrator_operating_level = orchestrator_operating_level

# Line 311 (existing continues)
notified_middlewares: dict[int, Any] = {}
```

---

## Test Example: Correct Behavior

```python
def test_adr002_secret_datasource_unofficial_sink_fails_at_start():
    """Start-time validation MUST block misconfig before data retrieval."""

    suite = ExperimentSuite(
        datasource_config={
            "security_level": "secret",  # HIGH
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                sink_defs=[{
                    "security_level": "unofficial"  # LOW - misconfigured
                }]
            )
        ]
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="secret"),
    )

    # Expected flow:
    # 1. Orchestrator collects levels: {datasource: SECRET, llm: SECRET, sink: UNOFFICIAL}
    # 2. Orchestrator computes operating level: min(...) = UNOFFICIAL
    # 3. Orchestrator validates components:
    #    - datasource requires SECRET but orchestrator at UNOFFICIAL → FAIL
    #    - llm requires SECRET but orchestrator at UNOFFICIAL → FAIL
    #    - sink requires UNOFFICIAL, orchestrator at UNOFFICIAL → OK
    # 4. Job FAILS TO START (before any data retrieval)

    with pytest.raises(SecurityError, match="requires SECRET but orchestrator operating at UNOFFICIAL"):
        runner.run(dataframe, defaults)
```

---

## Runtime Validation Example (Failsafe)

**In datasource plugin implementation:**

```python
class CSVDataSource:
    def __init__(self, path: str, security_level: str, context: PluginContext):
        self.path = path
        self.security_level = SecurityLevel.from_string(security_level)
        self.context = context

    def get_data(self) -> pd.DataFrame:
        """Retrieve data with runtime security validation (failsafe)."""

        # DEFENSE IN DEPTH: Runtime validation
        # Should NEVER trigger if start-time validation worked
        # But protects against orchestrator being tricked
        orchestrator_level = getattr(self.context, 'orchestrator_operating_level', None)
        if orchestrator_level:
            orch_level = SecurityLevel.from_string(orchestrator_level)
            if self.security_level > orch_level:
                raise SecurityError(
                    f"RUNTIME FAILSAFE: Datasource requires {self.security_level.value}, "
                    f"but orchestrator operating at {orch_level.value}. "
                    f"Refusing to hand over data. "
                    f"(This should have been caught at start-time - possible security bypass attempt)"
                )

        # Normal data retrieval
        return pd.read_csv(self.path)
```

**As user emphasized**: This runtime check should NEVER fire if start-time validation is working. It's a failsafe for "what if someone tricks the orchestrator?"

---

## Error Messages

### Start-Time (Primary Enforcement)

```
SecurityError: Component 'datasource' requires SECRET but orchestrator operating at UNOFFICIAL.
Job cannot start - remove low-security component or create separate pipeline.
ADR-002 fail-fast enforcement.
```

### Runtime (Failsafe - Should Never Happen)

```
SecurityError: RUNTIME FAILSAFE: Datasource requires SECRET but orchestrator operating at UNOFFICIAL.
Refusing to hand over data.
This should have been caught at start-time - possible security bypass attempt.
ADR-002 defense-in-depth enforcement.
```

---

## Summary: What's Different from Original Spec

| Original Spec (WRONG) | Correct Model |
|----------------------|---------------|
| "Datasource validates if pipeline has low sink" | "Orchestrator operates at minimum, ALL high components refuse low envelope" |
| "Only datasource validated" | "ALL components with security requirements validated" |
| Single validation point | Defense in depth: start-time (PRIMARY) + runtime (FAILSAFE) |
| `_validate_datasource_security()` | `_validate_components_at_operating_level()` (validates ALL) |
| Datasource-centric logic | Orchestrator clearance envelope model |

---

**Implementation Priority**: HIGH - This is the correct interpretation of ADR-002 and must be implemented before certification.

**Estimated Effort**: Same as original spec (4-6 hours) - same complexity, just correct model.
