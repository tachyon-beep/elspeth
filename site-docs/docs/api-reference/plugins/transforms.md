# Transforms API

API documentation for transform plugins (LLM clients and middleware).

!!! info "User Guide Available"
    For configuration examples and middleware usage, see **[Plugin Catalogue: Processing with LLMs](../../plugins/overview.md#processing-with-llms)**.

---

## Overview

Transform plugins process data through LLM APIs and middleware pipelines.

---

## LLM Client Interface

All LLM clients implement the transform interface:

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.security.classified_data import ClassifiedDataFrame

class LLMClient(BasePlugin):
    def transform(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
        """Transform data through LLM.

        Args:
            frame: Input data with classification

        Returns:
            Transformed data with uplifted classification
        """
        pass
```

---

## Built-In LLM Clients

### Azure OpenAI

::: elspeth.plugins.nodes.transforms.llm.azure_openai.AzureOpenAIClient
    options:
      members:
        - __init__
        - transform
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  type: azure_openai
  endpoint: https://my-openai.openai.azure.com
  api_key: ${AZURE_OPENAI_KEY}
  deployment_name: gpt-4
  security_level: OFFICIAL
  model_params:
    temperature: 0.7
    max_tokens: 500
```

---

### OpenAI HTTP

::: elspeth.plugins.nodes.transforms.llm.openai_http.OpenAIHTTPClient
    options:
      members:
        - __init__
        - transform
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  type: http_openai
  api_base: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
  model: gpt-4
  security_level: OFFICIAL
```

---

### Mock LLM (Testing)

::: elspeth.plugins.nodes.transforms.llm.mock.MockLLMClient
    options:
      members:
        - __init__
        - transform
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  type: mock
  response_template: "Mock: {text}"
  security_level: UNOFFICIAL
  seed: 42
```

---

## Middleware

Middleware wraps LLM clients to add security filters, logging, and monitoring.

### Middleware Interface

```python
class LLMMiddleware:
    def before_request(self, prompt: str, metadata: dict) -> tuple[str, dict]:
        """Process prompt before LLM call."""
        return prompt, metadata

    def after_response(self, response: str, metadata: dict) -> tuple[str, dict]:
        """Process response after LLM call."""
        return response, metadata
```

---

## Built-In Middleware

### PII Shield

Block or mask Personal Identifiable Information.

::: elspeth.plugins.nodes.transforms.llm.middleware.PIIShield
    options:
      members:
        - __init__
        - before_request
        - after_response
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  middleware:
    - type: pii_shield
      on_violation: abort  # abort | mask | log
      include_defaults: true
```

---

### Classified Material Filter

Block classified document markings.

::: elspeth.plugins.nodes.transforms.llm.middleware.ClassifiedMaterialFilter
    options:
      members:
        - __init__
        - before_request
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  middleware:
    - type: classified_material
      on_violation: abort
      include_defaults: true
```

---

### Audit Logger

Log all LLM requests and responses.

::: elspeth.plugins.nodes.transforms.llm.middleware.AuditLogger
    options:
      members:
        - __init__
        - before_request
        - after_response
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  middleware:
    - type: audit_logger
      include_prompts: false
      channel: llm_requests
```

---

### Health Monitor

Track latency, errors, and health metrics.

::: elspeth.plugins.nodes.transforms.llm.middleware.HealthMonitor
    options:
      members:
        - __init__
        - before_request
        - after_response
      show_root_heading: false
      heading_level: 3

**Configuration**:
```yaml
llm:
  middleware:
    - type: health_monitor
      heartbeat_interval: 60
      stats_window: 300
```

---

## Middleware Execution Order

Middleware runs in declaration order:

```yaml
llm:
  middleware:
    - type: pii_shield           # 1. Block PII first
    - type: classified_material  # 2. Block classified markings
    - type: audit_logger         # 3. Log sanitized prompts
    - type: health_monitor       # 4. Track performance
```

---

## Custom LLM Client Example

```python
from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security.classified_data import ClassifiedDataFrame
import requests

class CustomLLMClient(BasePlugin):
    """Custom LLM API client."""

    def __init__(self, *, security_level: SecurityLevel, api_endpoint: str, api_key: str):
        super().__init__(security_level=security_level)
        self.api_endpoint = api_endpoint
        self.api_key = api_key

    def transform(self, frame: ClassifiedDataFrame) -> ClassifiedDataFrame:
        """Transform data through custom LLM API."""
        results = []
        for idx, row in frame.data.iterrows():
            response = requests.post(
                self.api_endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"prompt": row['text']}
            )
            results.append(response.json()['completion'])

        frame.data['llm_response'] = results
        return frame.with_uplifted_classification(self.get_security_level())
```

---

## Related Documentation

- **[Plugin Catalogue](../../plugins/overview.md#processing-with-llms)** - Configuration examples
- **[Security Model](../../user-guide/security-model.md)** - Middleware security patterns
- **[BasePlugin](../core/base-plugin.md)** - Plugin base class
