# Deployment Diagram

```penguin
diagram "Deployment View" {
  direction: right

  group "Secure Desktop" {
    node operator "Security Analyst"
    node cli "elspeth.cli\n(src/elspeth/cli.py:65)"
    node localEnv "Local Config & Secrets\n(.env, keychain)"
  }

  group "Enterprise Network" {
    node proxy "Egress Firewall / Proxy"
    node vault "Secret Store / MDM"
  }

  group "Azure Cloud" {
    node azureML "Azure ML Compute\n(src/elspeth/plugins/llms/middleware_azure.py:76)"
    node blob "Azure Storage\n(config/blob_store.yaml:4)"
    node openai "Azure OpenAI Endpoint\n(src/elspeth/plugins/llms/azure_openai.py:25)"
    node devops "GitHub / Azure DevOps\n(src/elspeth/plugins/outputs/repository.py:137)"
  }

  operator -> cli "execute workflows"
  cli -> localEnv "load settings.yaml / prompt packs"
  cli -> proxy "outbound calls (requests>=2.31.0)"
  proxy -> blob "dataset ingress (HTTPS)"
  proxy -> openai "LLM invocations (TLS)"
  proxy -> devops "artifact pushes (optional)"
  vault -> cli "inject env vars (API keys, SAS tokens)"
  cli -> azureML "optional remote run\nvia middleware callbacks"
  azureML -> blob "managed identity\n(DefaultAzureCredential)"
  azureML -> openai "Azure ML managed networking"
}
```

- **Local execution** – Analysts run the CLI on a managed workstation, sourcing profiles and secrets from local environment stores (`src/elspeth/cli.py:65`).
- **Enterprise controls** – Outbound traffic is mediated by corporate proxies and secrets can be provisioned through vault tooling instead of static files (`config/settings.yaml:3`, `scripts/bootstrap.sh:16`).
- **Cloud integrations** – Azure middleware attaches to ML runs when present, while datasources and sinks interact with blob storage and Azure OpenAI (`src/elspeth/plugins/llms/middleware_azure.py:102`, `src/elspeth/plugins/datasources/blob.py:35`, `src/elspeth/plugins/outputs/blob.py:64`).
