# src/elspeth/testing/chaosllm/latency_simulator.py
"""Latency simulation for ChaosLLM server.

Re-exports LatencySimulator from chaosengine for backward compatibility.
"""

from elspeth.testing.chaosengine.latency import LatencySimulator

__all__ = ["LatencySimulator"]
