# src/elspeth/plugins/llm/__init__.py
"""LLM transform plugins for ELSPETH.

Provides transforms for Azure OpenAI, OpenRouter, and other LLM providers.
Includes support for pooled execution, batch processing, and multi-query evaluation.

Plugins are accessed via PluginManager, not direct imports:
    manager = PluginManager()
    manager.register_builtin_plugins()
    transform = manager.get_transform_by_name("azure_llm")

For testing or advanced usage, import directly from module paths:
    from elspeth.plugins.llm.azure import AzureLLMTransform
    from elspeth.plugins.llm.templates import PromptTemplate
"""
