# ELSPETH Plugin Hardening Work Plan

## 0) North star principles

1. **Secure by default**: least privilege, deny by default, safe defaults in config.
2. **Self-describing plugins**: every plugin says who it is, what it needs, and what it outputs.
3. **Strong isolation for untrusted code**: in-process for core or vetted code, out-of-process sandbox for third party.
4. **Policy as code**: classification, egress and secrets use enforced by a central policy engine, not ad-hoc checks.
5. **Great DX**: discovery, scaffolding and validation built into the CLI so contributors cannot accidentally make unsafe things.

(WEP: High that these principles will scale without harming security or uptime.)

---

## 1) Make plugins self-describing with a manifest

Add a **manifest** that every plugin ships with. This makes the system discoverable and pluggable without docs spelunking, and gives you a central place to enforce policy.

**What the manifest should include**

* `name`, `type` (datasource, llm, llm_middleware, experiment, output)
* `version` and `api_version` (your SDK contract version)
* `description`
* `inputs_schema` and `outputs_schema` (JSON Schema, used for validation and UI)
* `config_schema` (JSON Schema)
* `required_permissions` (capabilities, see section 2)
* `max_output_classification` and `min_input_classification`
* `allowed_egress_hostnames` (explicit allow list for network)
* `side_effects` (file writes, network calls, external services)
* `healthcheck` support flag

**Sketch**

```python
from enum import Enum
from typing import Literal, List, Set, Dict, Any
from pydantic import BaseModel, Field

class Permission(str, Enum):
    NETWORK = "network"
    FILE_WRITE = "file.write"
    BLOB_WRITE = "blob.write"
    GITHUB_WRITE = "github.write"
    SECRET_READ = "secret.read"

class Classification(str, Enum):
    UNOFFICIAL = "unofficial"
    OFFICIAL = "official"
    OFFICIAL_SENSITIVE = "official-sensitive"
    SECRET = "secret"
    TOP_SECRET = "top-secret"

class PluginManifest(BaseModel):
    name: str
    type: Literal["datasource","llm","llm_middleware","experiment","output"]
    version: str
    api_version: str
    description: str = ""
    inputs_schema: Dict[str, Any] = {}
    outputs_schema: Dict[str, Any] = {}
    config_schema: Dict[str, Any] = {}
    required_permissions: Set[Permission] = Field(default_factory=set)
    max_output_classification: Classification = Classification.OFFICIAL
    allowed_egress_hostnames: List[str] = Field(default_factory=list)
```

At load time, validate the manifest and reject plugins that do not declare enough. This is where you also enforce API compatibility (`api_version`).

(WEP: High)

---

## 2) Capability-based permissions and a narrow Host API

Do not hand plugins your whole process and environment. Instead, inject a **narrow Host API** that performs privileged actions after your checks. Plugins request **capabilities** in their manifest and get a **scoped context**.

**Pattern**

* Provide a `HostAPI` object with methods like `open_output(path)`, `emit_metric(k,v)`, `http_request(url, ...)`, `put_blob(container, name, bytes)`.
* Each method enforces policy: classification, path sandboxing, egress allow lists, timeouts, and rate limits.
* The only way to do network or file IO in a plugin is through this Host API.

**Tiny example**

```python
from urllib.parse import urlsplit
from pathlib import Path

class SecurityError(RuntimeError): pass

class HostAPI:
    def __init__(self, out_root: Path, egress_allow: set[str]):
        self._out_root = out_root.resolve()
        self._egress = egress_allow

    def open_output(self, rel_path: str, mode="wb"):
        p = (self._out_root / rel_path).resolve()
        if not str(p).startswith(str(self._out_root)):
            raise SecurityError("path escape")
        return open(p, mode)

    def http_request(self, method: str, url: str, **kw):
        host = urlsplit(url).hostname or ""
        if host not in self._egress:
            raise SecurityError(f"egress blocked to {host}")
        kw.setdefault("timeout", 15)
        # call your bounded HTTP client here, with retries and circuit breaker
        return httpx.request(method, url, **kw)
```

If a plugin tries to import `os` and wander off, you still have a guardrail: it will not get secrets and cannot reach the network or file system in the sanctioned paths without the Host API.

(WEP: Medium to High. You still cannot fully stop a malicious in-process plugin from doing silly things. See section 3.)

---

## 3) Trust tiers and isolation levels

Run plugins in different modes by **trust tier**.

* **Core**: your repo, code reviewed, runs in-process for performance.
* **Vetted**: partners or internal teams, runs **out-of-process** with a thin RPC boundary and a minimal environment.
* **Untrusted**: vendor or community, runs in a **container or micro-VM** with a seccomp/AppArmor profile, cgroup limits, read-only rootfs, and network blocked except through your policy proxy.

**How**

* Spawn via a worker process that only receives the Host API surface over IPC (e.g., gRPC or msgpack).
* For containers, run as non-root, mount only an outputs volume, pass secrets via a sidecar that issues ephemeral tokens on demand, not raw env vars.
* Enforce cgroup CPU and memory limits and process timeouts.
* Block direct `pip install` at runtime. Plugins are installed by your orchestrator, verified and pinned.

This preserves availability and limits the blast radius without punishing trusted core code.

(WEP: High for reducing risk and keeping SLOs predictable.)

---

## 4) Policy as code for classification, egress and secrets

Move hard rules out of arbitrary code into a central **policy engine**. Keep it simple initially.

* Authorisation checks: `experiment.level <= plugin.max_output_classification` enforced before run.
* Egress policy: `output.repository` not allowed in protected environments, unless whitelisted.
* Secrets policy: plugins never read environment directly. They request named secrets, the Host API returns ephemeral scoped tokens or references.

You can implement v1 as Python rules plus JSON Schema validation. If you want external policy later, wire to OPA or Cedar.

(WEP: High)

---

## 5) Supply chain integrity and plugin provenance

* Require **signed plugin distributions**. For internal wheel files, sign with Sigstore and verify on install.
* Pin dependencies with hashes, maintain an SBOM, run `pip audit` in CI and at start-up.
* Only load plugins from a **whitelist of package names** and sources.
* Record an attestation per run: plugin names, versions, manifest, and checksums included in the signed artefact manifest you already produce.

(WEP: High)

---

## 6) Versioning and compatibility

* Give your plugin SDK a clear **semver**. Breaks only in major.
* Each plugin declares `api_version` and you refuse to load incompatible ones.
* Provide adapters for one major back to keep the ecosystem moving.
* Add `elspeth plugins doctor` to detect drift.

(WEP: High)

---

## 7) First class observability, health and resilience

**Reliability features baked into the framework, not ad-hoc:**

* Timeouts, retries with jitter, exponential backoff.
* Circuit breakers per external system.
* Bulkheads and concurrency limits per plugin instance.
* Heartbeats and health checks, surfaced in metrics.
* Idempotency keys and outbox pattern for outputs so retries do not duplicate.

**Observability:**

* OpenTelemetry traces that show `datasource -> llm -> outputs` with correlation IDs.
* Structured JSON logs, no secrets, optional redaction.
* SLIs per plugin: success rate, latency, error classes, saturation.

(WEP: High)

---

## 8) Developer experience that prevents footguns

* **Discovery**: `elspeth plugins ls`, `elspeth plugins info <name>`, show manifest, config schema, declared permissions, egress allow list, classification limits.
* **Scaffolding**: upgrade `scripts/plugin_scaffold.py` into a CLI `elspeth plugin init` that writes a manifest, stubs, tests, and a minimal README.
* **Validation**: `elspeth plugins verify` runs schema validation and a static policy linter. Fail builds if a plugin asks for dangerous permissions without rationale.
* **Dry-run visualiser**: `elspeth plan` shows the data flow graph, classifications and policies that will be enforced. This helps IRAP assessors too.

(WEP: High)

---

## 9) Safer configuration and secrets handling

* Replace raw secret strings in config with **secret refs** like `secret://azure-openai/key`. The Host API resolves them just-in-time and injects to clients, not to plugins.
* Validate config strictly using JSON Schema and refuse unknown fields.
* Provide environment profiles: `dev`, `test`, `prod` that toggle defaults. In `prod`, forbid dangerous sinks by policy.

(WEP: High)

---

## 10) Excel and CSV safety for output plugins

Keep the analysts safe when they open files:

* Escape or prefix values beginning with `=`, `+`, `-`, `@`.
* Always write explicit cell types where the library allows.
* Add a config flag `sanitize_spreadsheet_values: true` and default it to true in `prod`.

(WEP: High for risk reduction, Low cost)

---

## 11) Endpoint safelists and TLS everywhere

* Validate endpoints in plugin config must be `https://`, and hostnames must be in the plugin’s `allowed_egress_hostnames`.
* Optionally support certificate pinning for high assurance environments.

(WEP: Medium to High)

---

## 12) Testing strategy

* Golden tests for plugin outputs using fixtures and recorded LLM responses.
* Property based tests for prompt variant expansion and validation.
* Chaos tests for outputs: inject transient failures, verify retries, idempotency and circuit breaking.
* Security tests: run semgrep rules for banned imports in plugin packages, and verify no direct environment access.

(WEP: High)

---

## 13) Migration and rollout

* Introduce the manifest and Host API behind a feature flag.
* Migrate core plugins first, then vet others by trust tier.
* Add the out-of-process runner for vetted and untrusted tiers once the Host API is stable.
* Freeze the old interface after one minor release and remove it in the next major.

(WEP: High)

---

## Short priority roadmap

1. **Manifest + schema validation + API semver**
2. **Host API with capability checks** (path sandboxing, egress allow lists, classification gates)
3. **CLI discovery, verify, plan**
4. **Excel/CSV sanitisation** default on
5. **Out-of-process runner for vetted plugins** with timeouts, cgroups, and minimal env
6. **Supply chain hardening**: signed wheels, SBOM, plugin allow list
7. **OPA or simple policy layer** for environment-specific rules
8. **OpenTelemetry + SLOs** baked in

---

## Why this does not compromise security or availability

* You are tightening the **attack surface** with a narrow Host API and clear permissions.
* You are improving **availability** with bulkheads, circuit breakers and idempotency.
* You are making audits easier with **self-describing** plugins, policy gates and a visible plan of what will run.
* You keep developer velocity high with scaffolding and validation that catch mistakes before they reach prod.

=======================

## ELSPETH LLM Middleware Reform Proposal

## 1) Roles and boundaries

* **LLM client plugin**
  Single job: turn a canonical request into provider API calls, handle auth, retries, and shape the response back. No policy, no business rules.

* **LLM middleware plugin**
  Cross-cutting concerns that wrap around any client: input validation, PII scrubbing, safety checks, audit/metrics, rate limiting, caching, routing, output redaction. Middleware should be ignorant of the transport details.

* **Optional content-aware service**
  A separate “guardrail” service that enforces content policy for multiple runtimes and teams. Use this when you want central control, rapid rule updates, or segregation of duties for IRAP. You can also run it as a local sidecar to avoid extra network hops.

(WEP: High this separation will keep the surface small and testable.)

---

## 2) Unlimited middleware without chaos

Give middleware a tiny, predictable contract with **phases** and **selectors**.

### Interface with phases

Support the full lifecycle including streaming.

```python
from typing import Protocol, AsyncIterator, Any
from pydantic import BaseModel

class LLMRequest(BaseModel):
    messages: list[dict]  # your canonical Message
    model: str
    stream: bool = False
    tags: dict[str, str] = {}  # e.g. {"provider":"azure","region":"aue"}
    classification: str  # official, official-sensitive, etc.
    context: dict[str, Any] = {}  # trace id, user, etc.

class LLMResponse(BaseModel):
    content: str
    usage: dict[str, int]
    raw: dict

class LLMDelta(BaseModel):
    token: str

class Middleware(Protocol):
    name: str
    order: int  # used for deterministic composition
    selector: "LabelSelector"  # see below

    async def on_request(self, req: LLMRequest, ctx: dict) -> LLMRequest: ...
    async def on_stream_delta(self, delta: LLMDelta, ctx: dict) -> LLMDelta: ...
    async def on_response(self, res: LLMResponse, ctx: dict) -> LLMResponse: ...
    async def on_error(self, err: Exception, ctx: dict) -> None: ...
```

* **on_request** can mutate or reject requests.
* **on_stream_delta** lets you filter or redact tokens on the fly.
* **on_response** can post-process content and attach metrics.
* **on_error** can classify and map exceptions.

Make every method optional with safe defaults so middleware can be lightweight.

### Selectors for compatibility

Middleware declares where it applies using **label selectors** rather than hardcoding provider checks.

```python
class LabelSelector(BaseModel):
    # any simple subset of k8s-style selectors works
    match_all: dict[str, str] = {}       # must match all pairs
    match_any: list[dict[str, str]] = [] # match any of these maps
```

Examples

* Azure Content Safety middleware
  `match_any: [{"provider":"azure"},{"capability":"content_safety_proxy"}]`
* JSON mode post-processor
  `match_all: {"supports_json_mode":"true"}`

At plan time, you evaluate selectors against the LLM client’s labels and fail fast if something cannot apply.

(WEP: High. Selectors avoid vendor if/else in code and keep things composable.)

---

## 3) Keep the LLM client tiny

Define a narrow client protocol and keep vendor quirks inside.

```python
class LLMClient(Protocol):
    name: str
    tags: dict[str, str]          # provider, region, model_family
    capabilities: set[str]        # streaming, tools, json_mode
    async def complete(self, req: LLMRequest, ctx: dict) -> LLMResponse: ...
    async def stream(self, req: LLMRequest, ctx: dict) -> AsyncIterator[LLMDelta]: ...
```

* Retries, backoff, timeouts are here, not in middleware.
* No policy decisions here apart from transport-level ones.

(WEP: High. This reduces blast radius when you swap SDKs or models.)

---

## 4) Ordering without footguns

Let middleware declare **ordering constraints**. Do a topological sort at plan time.

* Phases or groups help: `security_pre`, `transform`, `transport`, `security_post`, `analytics`.
* Also allow “before/after X” in a manifest to resolve specific conflicts.

Add a **latency budget** to the plan. If cumulative worst case exceeds budget, produce a plan warning or skip non-essential middleware by policy.

(WEP: Medium to High. Prevents death by a thousand interceptors.)

---

## 5) Security and compliance baked in

* **Policy gates centrally**: before you run, check classification rules, allowed egress, and secret access. Deny by default.
* **Host API**: all file and network IO from middleware goes through a small Host API that enforces paths, TLS, hostname allow lists, and redaction.
* **No direct env reads** in middleware. Secrets are resolved via short-lived handles from the Host API.
* **Streaming redaction**: give middleware a chance to redact deltas (for PII or secrets) before they hit sinks.

(WEP: High. IRAP friendly, reduces accidental leaks.)

---

## 6) When to split “content aware” into a separate service

**Good reasons to externalise**

* You want one policy to rule them all across Python, Node, and Batch.
* Frequent rule changes by a governance team without code deploys.
* You need stronger isolation boundaries for assessors.
* You need centralised audit and tuning.
* You want to scale safety compute separately and cache verdicts across teams.

**Trade-offs**

* Extra hop adds latency and a new failure mode.
* You must manage auth to the guard service and its uptime.
* Content context may be truncated unless you pass enough metadata.

**Pragmatic pattern**

* Run it as a **sidecar** for low latency in most environments.
* Allow a **remote mode** for shared environments.
* Always include a **circuit breaker** plus a policy for `fail_closed` or `fail_open` by classification.
* Cache recent verdicts by content hash with TTL to save cost and time.

(WEP: High this hybrid gives you the best of both worlds.)

---

## 7) Minimal manifest to make this ergonomic

Give both clients and middleware a manifest so the CLI can compose safely.

```json
{
  "name": "azure_content_safety",
  "type": "llm_middleware",
  "api_version": "1.2",
  "description": "Checks prompts and responses with Azure Content Safety",
  "required_permissions": ["network","secret.read"],
  "allowed_egress_hostnames": ["*.cognitiveservices.azure.com"],
  "selector": { "match_any": [
    {"provider":"azure"},
    {"capability":"content_safety_proxy"}
  ]},
  "order": 10,
  "fail_mode": "abort",
  "timeout_ms": 1200,
  "max_output_classification": "official-sensitive"
}
```

At plan time:

1. Validate API compatibility.
2. Evaluate selectors against the chosen client’s `tags` and `capabilities`.
3. Enforce classification gates and egress allow lists.
4. Topologically sort by `order` and any before/after hints.
5. Emit a plan that shows the chain and budgets.

(WEP: High. Makes behaviour transparent to operators and assessors.)

---

## 8) Availability and performance

* Concurrency limits and bulkheads per middleware and per client.
* Timeouts and retries with jitter on transport only.
* Circuit breakers per external dependency including guard services.
* Idempotency keys for outputs so retries do not duplicate work.
* Streaming middleware runs in a tight loop and must be non-blocking.

Tiny streaming loop sketch:

```python
async def run_stream(client, mws, req, ctx):
    req1 = await fold(req, mws, "on_request", ctx)
    async for d in client.stream(req1, ctx):
        d1 = await fold(d, mws, "on_stream_delta", ctx)
        yield d1
    # final on_response can receive the reconstructed content if you buffer it
```

(WEP: High that these patterns keep SLOs healthy.)

---

## 9) Decision guide

* **Keep LLM client and middleware separate**
  Yes. It isolates vendor churn and lets you compose cross-cutting concerns cleanly. (WEP: High)

* **Make middleware unlimited and composable**
  Yes, with selectors, phases, and budgets so “unlimited” does not become “unbounded”. (WEP: High)

* **Externalise content-aware checks**
  Yes when you need cross-team policy, stronger separation, or frequent rule updates. Prefer sidecar first, remote service second. (WEP: High for large orgs, Medium for single team)

---

## 10) Small changes you can land first

1. Define the `LLMClient`, `Middleware`, and event phases as above.
2. Add `tags` and `capabilities` to clients, and a selector to each middleware.
3. Do a plan step that resolves compatibility, ordering, and policy before execution.
4. Move Azure Content Safety into a middleware that selects on `provider=azure` or `capability=content_safety_proxy`.
5. Add a guardrail interface so the same middleware can call a sidecar or a remote service with the same code path.

=======================

## The Router sink pattern [recommended]

A single output plugin that:

* Accepts the full results table
* Evaluates one or more criteria
* For each matching route, writes a filtered view to one or more child sinks
* Enforces classification, egress and schema per route
* Emits audit metrics

### Config shape

Use JSONLogic for predicates in v1. It is pure data, easy to validate, no eval, and portable. Keep “first_match” vs “multi_match” explicit.

```yaml
outputs:
  - type: router
    name: results_router
    mode: multi_match            # or first_match
    default_route:               # optional
      sinks:
        - type: csv_file
          path: outputs/uncategorised.csv
    routes:
      - name: success
        when: {"==": [{"var":"succeeded"}, true]}
        select: ["id","prompt","model","latency_ms","succeeded"]   # projection
        schema:                                    # optional JSON Schema
          required: ["id","prompt","succeeded"]
        sinks:
          - type: csv_file
            path: outputs/success.csv
          - type: excel
            path: outputs/success.xlsx
      - name: failure
        when: {"==": [{"var":"succeeded"}, false]}
        sinks:
          - type: csv_file
            path: outputs/failure.csv
      - name: slow_expensive
        when:
          {"and":[
            {">":[{"var":"latency_ms"}, 2000]},
            {">":[{"var":"usage.total_cost_cents"}, 50]}
          ]}
        sinks:
          - type: blob
            container: audit
            prefix: slow/
```

Nice-to-haves in config:

* `criteria_library:` reusable named predicates and composition by reference
  Example: `{"and":[{"ref":"is_success"},{"not":{"ref":"is_expensive"}}]}`
* `on_child_error:` abort | skip | quarantine (quarantine writes failing rows to a local signed bundle)
* `sanitize_spreadsheet_values:` true by default for Excel and CSV
* `classification_policy:` inherit | enforce_highest | explicit:"official-sensitive"
* `metrics:` emit counts per route, sample ids, and hashes only

### Why JSONLogic

* Safe and auditable, easy to render in IRAP docs
* Schema-validateable
* You can later add engines like CEL behind a common interface without changing configs

### Alternate routing modes

* `first_match`: stop at first true condition, deterministic order
* `multi_match`: allow a row to go to multiple routes
* `else` via `default_route`

## Smarter without bloat: two useful variants

1. **Tag-and-demux**
   Add a tiny experiment-phase plugin that computes a `route` label per row (using the same DSL). The Router then just splits on `route`. This decouples decision logic from output shape and lets you reuse the same routing across different output layouts.

2. **Decision table**
   For simple cases, a table is more readable than nested logic:

```yaml
decision_table:
  inputs: ["succeeded", "latency_ms", "cost_cents"]
  rules:
    - when: ["true", "<=2000", "<=50"]   # strings map to operators
      route: "success_fast"
    - when: ["false", "*", "*"]
      route: "failure"
    - when: ["true", ">2000", ">50"]
      route: "slow_expensive"
```

You can compile this to JSONLogic internally.

## Security and IRAP concerns baked in

* **Classification gates** per route and per child sink. Never downgrade. If any child sink is lower than the row’s classification, apply `on_violation: abort|skip|mask`.
* **No secrets in predicates.** Predicates only see row data and safe metadata.
* **Egress allow-lists** still enforced by child sinks and the Host API.
* **Audit**: log route counts, route names, child sink ids, and a sample of row ids. Never log raw prompts by default.
* **Idempotency**: write a signed routing manifest: route name → list of row ids and target artefacts. Retries can reconcile using this manifest.
* **Excel/CSV safety**: prefix `= + - @` with a quote when writing. Default to on.

## Implementation sketch

### 1) Config models

```python
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict

@dataclass
class RouteSpec:
    name: str
    when: Dict[str, Any]                  # JSONLogic
    sinks: List[Dict[str, Any]]           # child sink configs
    select: Optional[List[str]] = None    # projection
    schema: Optional[Dict[str, Any]] = None

@dataclass
class RouterConfig:
    mode: str = "multi_match"             # or first_match
    routes: List[RouteSpec] = field(default_factory=list)
    default_route: Optional[Dict[str, Any]] = None
    sanitize_spreadsheet_values: bool = True
    on_child_error: str = "abort"
```

### 2) Engine abstraction

```python
class CriteriaEngine:
    def compile(self, expr: dict): ...
    def match_mask(self, df, compiled) -> "pd.Series[bool]": ...
```

* Start with JSONLogic row-wise evaluation.
* Later add a vectoriser that maps a safe subset of JSONLogic to pandas masks for big workloads.

### 3) Router sink skeleton

```python
class RouterSink(ResultSink):
    def __init__(self, cfg: RouterConfig, host_api: HostAPI):
        self.cfg = cfg
        self.host = host_api
        self._compiled = [(r, criteria_engine.compile(r.when)) for r in cfg.routes]
        self._child_sinks = {
            r.name: [build_sink(sc) for sc in r.sinks] for r in cfg.routes
        }
        self._default_sinks = [build_sink(sc) for sc in (cfg.default_route or {}).get("sinks", [])]

    def write(self, df: "pd.DataFrame", ctx: RunContext):
        routing_manifest = []
        remaining = df.index.to_series().copy()

        for route, compiled in self._compiled:
            mask = criteria_engine.match_mask(df, compiled)
            part = df[mask]
            if part.empty:
                continue

            part = self._apply_projection_and_schema(part, route)

            # security gating per route + per sink
            self._enforce_classification(part, ctx, route)

            # write to each child sink with error policy
            for sink in self._child_sinks[route.name]:
                self._safe_write(sink, part, ctx, route)

            routing_manifest.append({"route": route.name, "rows": part.index.tolist()})

            if self.cfg.mode == "first_match":
                remaining = remaining[~mask]
                if remaining.empty:
                    break

        # default route for anything left
        if self._default_sinks and not remaining.empty:
            leftover = df.loc[remaining.index]
            for sink in self._default_sinks:
                self._safe_write(sink, leftover, ctx, name="default")

        self._write_signed_manifest(routing_manifest, ctx)
```

Key helpers:

* `_apply_projection_and_schema` uses JSON Schema to validate, and optional `select` to keep only expected columns
* `_enforce_classification` checks row or run classification against each sink’s declared level
* `_safe_write` enforces Excel/CSV sanitisation and honours `on_child_error`

### 4) Criteria library and references

Allow top-level `criteria_library` in config, resolve `{"ref":"name"}` inside any `when`. This gives reuse without spawning a new plugin type.

## Is a “criteria plugin” type worth it

Usually no. Criteria are data, not behaviour. A separate plugin type adds surface area, versioning and security review for something that can be a small, testable module. If you ever need pluggable evaluators, wrap them behind `CriteriaEngine` and ship as core-vetted modules, not third-party code running in-process.

## Performance notes

* For typical datasets, a row-wise JSONLogic pass is fine.
* For big tables, add a vectoriser to translate a safe subset to pandas masks.
* Use first_match if predicates are mutually exclusive to short-circuit early.
* Emit per-route counts and timings to spot hot predicates.

## Migration

* Land the Router sink with JSONLogic and schema projection.
* Move your current success/failure splits to Router routes.
* Replace ad-hoc filters in downstream sinks with projections and route-level schema.
* Add the signed routing manifest to your integrity story.
