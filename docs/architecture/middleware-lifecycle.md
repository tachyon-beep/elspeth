# Middleware Lifecycle Management

**Status:** Implementation Reference
**Last Updated:** January 2025
**Related:** [plugin-catalogue.md](plugin-catalogue.md), [plugin-security-model.md](plugin-security-model.md)

---

## Overview

Middleware in Elspeth provides **request/response interception** and **suite-level observability** for LLM interactions. Understanding middleware lifecycle—especially instance sharing and state management—is critical for building robust middleware plugins.

This document explains:
1. How middleware instances are created and cached
2. When lifecycle hooks are called
3. State management best practices
4. Common pitfalls and how to avoid them

---

## Middleware Lifecycle Stages

### 1. Definition & Registration

Middleware is defined in configuration at three levels:

```yaml
# Suite defaults (lowest priority)
defaults:
  llm_middleware_defs:
    - name: audit_logger
      options:
        log_level: "INFO"

# Prompt pack (middle priority)
prompt_packs:
  classification:
    llm_middlewares:
      - name: prompt_shield
        options:
          block_pii: true

# Experiment config (highest priority)
experiments:
  - name: experiment_1
    llm_middleware_defs:
      - name: cost_tracker
        options:
          budget: 100.0
```

These definitions are **merged** (concatenated) to form the final middleware chain for each experiment.

### 2. Instantiation & Caching

**Key Insight:** Middlewares are **cached and reused** across experiments within a suite.

#### Caching Strategy

Middleware instances are cached using a **fingerprint** composed of:

```python
# From suite_runner.py:241
identifier = f"{name}:{json.dumps(defn.get('options', {}), sort_keys=True)}:{parent_context.security_level}"
```

**Fingerprint Components:**
- `name`: Middleware plugin name (e.g., "audit_logger")
- `options`: Middleware options (JSON-serialized with sorted keys for stability)
- `security_level`: Parent experiment context security level

**Cache Behavior:**

```python
# From suite_runner.py:242-244
if identifier not in self._shared_middlewares:
    self._shared_middlewares[identifier] = create_middleware(defn, parent_context=parent_context)
instances.append(self._shared_middlewares[identifier])
```

- **Same fingerprint → Same instance** (reused across experiments)
- **Different fingerprint → New instance** (created and cached)

#### Example: Instance Sharing

```yaml
experiments:
  - name: exp_1
    llm_middleware_defs:
      - name: audit_logger  # Instance A
        options: {level: "INFO"}

  - name: exp_2
    llm_middleware_defs:
      - name: audit_logger  # SAME instance A (reused!)
        options: {level: "INFO"}

  - name: exp_3
    llm_middleware_defs:
      - name: audit_logger  # NEW instance B (different options)
        options: {level: "DEBUG"}
```

**Result:**
- Experiments 1 & 2 share Middleware Instance A
- Experiment 3 gets its own Middleware Instance B

---

## Lifecycle Hooks

Middleware can implement **two types of hooks**:

### 1. Request/Response Hooks (Per-Request)

Called for every LLM interaction:

```python
class MyMiddleware:
    def on_request(self, request: Dict, metadata: Dict) -> Dict:
        """Intercept/modify request before LLM call"""
        return request

    def on_response(self, response: Dict, metadata: Dict) -> Dict:
        """Intercept/modify response after LLM call"""
        return response

    def on_error(self, error: Exception, metadata: Dict) -> None:
        """Handle LLM errors"""
        pass
```

**Called:** Once per experiment row per LLM invocation
**Frequency:** High (potentially thousands of times)

### 2. Suite-Level Hooks (Per-Experiment/Suite)

Called at experiment/suite boundaries:

```python
class MyMiddleware:
    def on_suite_loaded(self, suite_metadata: List[Dict], preflight_info: Dict) -> None:
        """Called once when suite starts"""
        pass

    def on_experiment_start(self, name: str, config: Dict) -> None:
        """Called before each experiment starts"""
        pass

    def on_experiment_complete(self, name: str, payload: Dict, config: Dict) -> None:
        """Called after each experiment completes"""
        pass

    def on_baseline_comparison(self, name: str, comparisons: Dict) -> None:
        """Called when baseline comparison runs"""
        pass

    def on_suite_complete(self) -> None:
        """Called once after all experiments finish"""
        pass
```

**Called:** Once per experiment or suite (low frequency)
**Frequency:** Low (typically <10 times per suite)

---

## Hook Invocation Timeline

### Suite Execution Flow

```
Suite Start
    ↓
┌───────────────────────────────────────────────────────────┐
│ on_suite_loaded(suite_metadata, preflight_info)          │
│   • Called ONCE per middleware instance                  │
│   • Provides metadata for ALL experiments in suite       │
└───────────────────────────────────────────────────────────┘
    ↓
┌─────────────── For Each Experiment ──────────────────────┐
│                                                           │
│  on_experiment_start(name, config)                       │
│   ↓                                                       │
│  ┌───────────────────────────────────────────────────┐   │
│  │ For Each Row:                                     │   │
│  │   on_request(request, metadata)                   │   │
│  │      ↓                                            │   │
│  │   [LLM Call]                                      │   │
│  │      ↓                                            │   │
│  │   on_response(response, metadata)                 │   │
│  │   or on_error(error, metadata)                    │   │
│  └───────────────────────────────────────────────────┘   │
│   ↓                                                       │
│  on_experiment_complete(name, payload, config)           │
│   ↓                                                       │
│  [If not baseline experiment]                            │
│  on_baseline_comparison(name, comparisons)               │
│                                                           │
└───────────────────────────────────────────────────────────┘
    ↓
┌───────────────────────────────────────────────────────────┐
│ on_suite_complete()                                       │
│   • Called ONCE per middleware instance                  │
└───────────────────────────────────────────────────────────┘
    ↓
Suite End
```

### Important Details

1. **`on_suite_loaded` is called once per instance**, not once per experiment
   - If middleware is shared across 5 experiments, called only ONCE
   - Use for suite-wide initialization (opening connections, allocating quotas)

2. **`on_experiment_start/complete` are called per experiment**, even for shared instances
   - If middleware is shared across 5 experiments, called 5 times each
   - Use for per-experiment metrics or state snapshots

3. **Request/response hooks are called per-row per-experiment**
   - For 100 rows × 5 experiments = 500 invocations minimum
   - Use for per-request logging, sanitization, or modification

---

## State Management

### Safe State Patterns

✅ **DO use state for:**

#### 1. Suite-Level Aggregation
```python
class CostTracker:
    def __init__(self, budget: float):
        self.total_cost = 0.0  # Shared across experiments
        self.budget = budget

    def on_response(self, response, metadata):
        cost = response.get("usage", {}).get("total_cost", 0)
        self.total_cost += cost
        return response

    def on_suite_complete(self):
        if self.total_cost > self.budget:
            print(f"Budget exceeded: ${self.total_cost} > ${self.budget}")
```

**Why Safe:** Intentional accumulation across experiments

#### 2. Shared Quota Management
```python
class RateLimiter:
    def __init__(self, max_requests: int):
        self.request_count = 0  # Shared quota
        self.max_requests = max_requests

    def on_request(self, request, metadata):
        self.request_count += 1
        if self.request_count > self.max_requests:
            raise Exception(f"Rate limit exceeded: {self.request_count} > {self.max_requests}")
        return request
```

**Why Safe:** Suite-level quota enforcement is the intended behavior

#### 3. Persistent Connections
```python
class DatabaseLogger:
    def on_suite_loaded(self, suite_metadata, preflight_info):
        self.connection = psycopg2.connect(...)  # Open once

    def on_response(self, response, metadata):
        self.connection.execute("INSERT INTO logs ...")  # Reuse connection

    def on_suite_complete(self):
        self.connection.close()  # Clean up once
```

**Why Safe:** Connection pooling reduces overhead

### Unsafe State Patterns

❌ **DO NOT use state for:**

#### 1. Per-Experiment Data That Shouldn't Leak
```python
class UNSAFE_ExperimentTracker:
    def __init__(self):
        self.experiment_rows = []  # PROBLEM: Accumulates across experiments!

    def on_request(self, request, metadata):
        self.experiment_rows.append(request)  # Leaks between experiments
        return request
```

**Fix:** Reset state in `on_experiment_start`:
```python
class SafeExperimentTracker:
    def __init__(self):
        self.experiment_rows = []

    def on_experiment_start(self, name, config):
        self.experiment_rows = []  # RESET per experiment

    def on_request(self, request, metadata):
        self.experiment_rows.append(request)
        return request
```

#### 2. Mutable Default Arguments
```python
class UNSAFE_RequestFilter:
    def __init__(self, blocked_words=[]):  # PROBLEM: Mutable default!
        self.blocked_words = blocked_words

    def on_request(self, request, metadata):
        if "bad_word" in request["prompt"]:
            self.blocked_words.append("bad_word")  # Persists across instances!
```

**Fix:** Use immutable defaults:
```python
class SafeRequestFilter:
    def __init__(self, blocked_words=None):
        self.blocked_words = list(blocked_words) if blocked_words else []
```

---

## Instance Sharing Examples

### Example 1: Audit Logging (Should Share)

```yaml
experiments:
  - name: exp_1
    llm_middleware_defs:
      - name: audit_logger
        options: {destination: "/logs/audit.json"}

  - name: exp_2
    llm_middleware_defs:
      - name: audit_logger
        options: {destination: "/logs/audit.json"}  # SAME options
```

**Behavior:**
- Both experiments share the SAME audit logger instance
- Logs from both experiments go to the same file
- File handle is opened once in `on_suite_loaded`, closed once in `on_suite_complete`

**Benefit:** Efficient file I/O, consistent log format

### Example 2: Per-Experiment Metrics (Should NOT Share)

```yaml
experiments:
  - name: exp_1_gpt4
    llm_middleware_defs:
      - name: cost_tracker
        options: {model: "gpt-4"}  # Different options

  - name: exp_2_gpt3
    llm_middleware_defs:
      - name: cost_tracker
        options: {model: "gpt-3.5"}  # Different options
```

**Behavior:**
- Each experiment gets its own cost tracker instance (different fingerprints)
- Costs are tracked independently
- Each instance reports separately in `on_experiment_complete`

**Benefit:** Accurate per-experiment cost attribution

### Example 3: Security-Level Isolation

```yaml
experiments:
  - name: exp_1_secret
    security_level: "SECRET"
    llm_middleware_defs:
      - name: audit_logger
        options: {level: "INFO"}

  - name: exp_2_official
    security_level: "OFFICIAL"
    llm_middleware_defs:
      - name: audit_logger
        options: {level: "INFO"}  # SAME options
```

**Behavior:**
- Different security levels → Different fingerprints → Separate instances
- SECRET logs go to one instance, OFFICIAL to another
- Prevents security level mixing

**Benefit:** Security isolation enforced automatically

---

## Debugging Middleware Issues

### Problem: "Middleware Not Executing"

**Symptoms:**
- `on_request` or `on_response` not being called
- Expected logs or metrics missing

**Debugging Steps:**

1. **Check middleware registration:**
   ```python
   # Verify middleware is registered
   from elspeth.core.llm.registry import _middleware_registry
   print(_middleware_registry._plugins.keys())
   ```

2. **Check configuration merge:**
   - Use `ConfigMerger` to trace middleware definitions
   - Verify middleware appears in final merged config

3. **Check hook signatures:**
   ```python
   # Hooks must match EXACTLY:
   def on_request(self, request: Dict, metadata: Dict) -> Dict:  # Correct
   def on_request(self, request):  # WRONG - signature mismatch
   ```

4. **Enable debug logging:**
   ```python
   import logging
   logging.getLogger("elspeth.core.experiments.runner").setLevel(logging.DEBUG)
   ```

### Problem: "State Leaking Between Experiments"

**Symptoms:**
- Row counts accumulating across experiments
- Metrics from one experiment appearing in another
- Memory growing unbounded

**Debugging Steps:**

1. **Check if instance is shared:**
   ```python
   # Add to middleware __init__:
   import uuid
   self._instance_id = str(uuid.uuid4())

   # Add to on_experiment_start:
   print(f"Instance {self._instance_id} starting experiment {name}")
   ```

2. **Reset state in `on_experiment_start`:**
   ```python
   def on_experiment_start(self, name, config):
       self.experiment_data = []  # RESET per experiment
       self.request_count = 0     # RESET counters
   ```

3. **Use immutable or isolated state:**
   ```python
   # Instead of:
   self.all_data = []  # Mutable, shared

   # Use:
   self.data_by_experiment = {}  # Isolated per experiment

   def on_experiment_start(self, name, config):
       self.data_by_experiment[name] = []
   ```

### Problem: "`on_suite_loaded` Called Multiple Times"

**Symptoms:**
- Suite-level initialization happens multiple times
- Resources (connections, files) opened repeatedly

**Root Cause:** Multiple middleware instances with different fingerprints

**Fix:** Ensure consistent configuration:
```yaml
# Before (creates 2 instances):
defaults:
  llm_middleware_defs:
    - name: db_logger
      options: {host: "localhost"}

experiments:
  - name: exp_1
    # Uses defaults (host: localhost)
  - name: exp_2
    llm_middleware_defs:
      - name: db_logger
        options: {host: "localhost", port: 5432}  # Different options!

# After (creates 1 instance):
defaults:
  llm_middleware_defs:
    - name: db_logger
      options: {host: "localhost", port: 5432}  # Consistent

experiments:
  - name: exp_1
    # Uses defaults
  - name: exp_2
    # Uses defaults (same instance)
```

---

## Best Practices

### ✅ DO

1. **Document State Behavior**
   ```python
   class MyMiddleware:
       """
       State Management:
       - `total_requests`: Suite-level counter (accumulates)
       - `experiment_rows`: Per-experiment list (resets on_experiment_start)
       """
   ```

2. **Use Suite Hooks for Expensive Operations**
   ```python
   def on_suite_loaded(self, suite_metadata, preflight_info):
       self.db = connect_to_database()  # Open once

   def on_suite_complete(self):
       self.db.close()  # Close once
   ```

3. **Validate Fingerprint Stability**
   ```python
   # Ensure options dict is JSON-serializable and stable
   options = {
       "threshold": 0.5,
       "tags": ["a", "b"],  # Lists are stable with sort_keys=True
   }
   ```

4. **Handle Missing Hooks Gracefully**
   ```python
   # Framework checks hasattr before calling:
   if hasattr(mw, "on_suite_loaded"):
       mw.on_suite_loaded(...)

   # No need to implement all hooks
   ```

### ❌ DON'T

1. **Don't Rely on Execution Order Between Middleware**
   - Middleware order is configuration-dependent
   - Design middleware to be order-independent

2. **Don't Modify Shared State Without Locks (if threaded)**
   ```python
   # If concurrency enabled:
   import threading

   class ThreadSafeMiddleware:
       def __init__(self):
           self.counter = 0
           self.lock = threading.Lock()

       def on_request(self, request, metadata):
           with self.lock:
               self.counter += 1
   ```

3. **Don't Assume Middleware Runs in Isolation**
   - Other middleware may modify request/response
   - Always return modified objects, don't mutate in place

---

## Configuration Reference

### Middleware Definition Schema

```yaml
llm_middleware_defs:
  - name: <middleware_name>          # Required: Plugin name
    security_level: <level>          # Optional: Inherited from context if omitted
    determinism_level: <level>       # Optional: Inherited from context if omitted
    options:                         # Optional: Plugin-specific options
      <key>: <value>
```

### Fingerprint Components

| Component | Source | Impact on Sharing |
|-----------|--------|-------------------|
| `name` | Middleware plugin name | Different names → different instances |
| `options` | JSON-serialized options dict | Different options → different instances |
| `security_level` | Parent experiment context | Different levels → different instances |

**Note:** `determinism_level` is NOT part of fingerprint (intentional design decision to allow sharing between deterministic/non-deterministic experiments).

---

## Related Documentation

- [Plugin Catalogue](plugin-catalogue.md) - Available middleware plugins
- [Plugin Security Model](plugin-security-model.md) - Security context propagation
- [Configuration Merge](configuration-merge.md) - How configuration layers merge
- [Experiment Runner](experiment-runner.md) - How middleware integrates with experiment execution

---

## Changelog

- **2025-01-14:** Initial documentation based on architectural review
- **Implementation:** `src/elspeth/core/experiments/suite_runner.py:232-245`
