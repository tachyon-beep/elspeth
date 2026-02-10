# src/elspeth/testing/chaosengine/__init__.py
"""ChaosEngine: Shared utilities for chaos testing servers.

Provides composition-based building blocks used by ChaosLLM, ChaosWeb, and
future chaos plugins (ChaosFile, ChaosSQL, etc.):

- InjectionEngine: Burst state machine + priority/weighted error selection
- MetricsStore: Thread-safe SQLite with schema-driven DDL
- LatencySimulator: Configurable artificial latency
- Config loading: deep_merge, preset loading, YAML precedence

Each chaos plugin *composes* these utilities rather than inheriting from
base classes, avoiding covariant return type friction and HTTP-leakage
into non-HTTP domains.
"""

from elspeth.testing.chaosengine.config_loader import (
    deep_merge,
    list_presets,
    load_preset,
)
from elspeth.testing.chaosengine.injection_engine import InjectionEngine
from elspeth.testing.chaosengine.latency import LatencySimulator
from elspeth.testing.chaosengine.metrics_store import MetricsStore
from elspeth.testing.chaosengine.types import (
    BurstConfig,
    ErrorSpec,
    LatencyConfig,
    MetricsConfig,
    MetricsSchema,
    ServerConfig,
)
from elspeth.testing.chaosengine.vocabulary import ENGLISH_VOCABULARY, LOREM_VOCABULARY

__all__ = [
    "ENGLISH_VOCABULARY",
    "LOREM_VOCABULARY",
    "BurstConfig",
    "ErrorSpec",
    "InjectionEngine",
    "LatencyConfig",
    "LatencySimulator",
    "MetricsConfig",
    "MetricsSchema",
    "MetricsStore",
    "ServerConfig",
    "deep_merge",
    "list_presets",
    "load_preset",
]
