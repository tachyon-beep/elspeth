"""Tests for commencement gate evaluation."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from elspeth.contracts.errors import CommencementGateFailedError
from elspeth.core.dependency_config import CommencementGateConfig
from elspeth.engine.commencement import (
    build_preflight_context,
    evaluate_commencement_gates,
)


class TestEvaluateCommencementGates:
    def test_passing_gate(self) -> None:
        gates = [
            CommencementGateConfig(
                name="ready",
                condition="collections['test']['count'] > 0",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {"test": {"count": 10, "reachable": True}},
            "env": {"HOME": "/home/user"},
        }
        results = evaluate_commencement_gates(gates, context)
        assert len(results) == 1
        assert results[0].result is True
        assert results[0].name == "ready"

    def test_failing_gate_raises(self) -> None:
        gates = [
            CommencementGateConfig(
                name="ready",
                condition="collections['test']['count'] > 0",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {"test": {"count": 0, "reachable": False}},
            "env": {},
        }
        with pytest.raises(CommencementGateFailedError, match="ready"):
            evaluate_commencement_gates(gates, context)

    def test_expression_error_raises(self) -> None:
        gates = [
            CommencementGateConfig(
                name="bad",
                condition="collections['missing']['count'] > 0",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {},
            "env": {},
        }
        with pytest.raises(CommencementGateFailedError, match="bad"):
            evaluate_commencement_gates(gates, context)

    def test_snapshot_excludes_env(self) -> None:
        gates = [
            CommencementGateConfig(
                name="ready",
                condition="collections['test']['count'] > 0",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {"test": {"count": 5, "reachable": True}},
            "env": {"SECRET_KEY": "abc123"},
        }
        results = evaluate_commencement_gates(gates, context)
        snapshot = results[0].context_snapshot
        assert "env" not in snapshot
        assert "SECRET_KEY" not in str(snapshot)

    def test_snapshot_is_deep_frozen(self) -> None:
        gates = [
            CommencementGateConfig(
                name="ready",
                condition="collections['test']['count'] > 0",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {"test": {"count": 5, "reachable": True}},
            "env": {},
        }
        results = evaluate_commencement_gates(gates, context)
        assert isinstance(results[0].context_snapshot, MappingProxyType)

    def test_multiple_gates_all_pass(self) -> None:
        gates = [
            CommencementGateConfig(name="g1", condition="collections['a']['count'] > 0"),
            CommencementGateConfig(name="g2", condition="collections['b']['count'] > 0"),
        ]
        context = {
            "dependency_runs": {},
            "collections": {
                "a": {"count": 5, "reachable": True},
                "b": {"count": 3, "reachable": True},
            },
            "env": {},
        }
        results = evaluate_commencement_gates(gates, context)
        assert len(results) == 2

    def test_second_gate_fails_stops_evaluation(self) -> None:
        gates = [
            CommencementGateConfig(name="g1", condition="collections['a']['count'] > 0"),
            CommencementGateConfig(name="g2", condition="collections['b']['count'] > 0"),
        ]
        context = {
            "dependency_runs": {},
            "collections": {
                "a": {"count": 5, "reachable": True},
                "b": {"count": 0, "reachable": False},
            },
            "env": {},
        }
        with pytest.raises(CommencementGateFailedError, match="g2"):
            evaluate_commencement_gates(gates, context)

    def test_env_accessible_in_expression(self) -> None:
        gates = [
            CommencementGateConfig(
                name="env_check",
                condition="env['ENVIRONMENT'] == 'production'",
            )
        ]
        context = {
            "dependency_runs": {},
            "collections": {},
            "env": {"ENVIRONMENT": "production"},
        }
        results = evaluate_commencement_gates(gates, context)
        assert len(results) == 1
        assert results[0].result is True

    def test_empty_gates_returns_empty(self) -> None:
        results = evaluate_commencement_gates([], {"dependency_runs": {}, "collections": {}, "env": {}})
        assert results == []


class TestBuildPreflightContext:
    def test_includes_all_sections(self) -> None:
        context = build_preflight_context(
            dependency_results={},
            collection_probes={"test": {"count": 5, "reachable": True}},
            env={"HOME": "/home"},
        )
        assert "dependency_runs" in context
        assert "collections" in context
        assert "env" in context

    def test_env_defaults_to_os_environ(self) -> None:
        context = build_preflight_context(
            dependency_results={},
            collection_probes={},
        )
        assert "env" in context
        assert isinstance(context["env"], dict)
