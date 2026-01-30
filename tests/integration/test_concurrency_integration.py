"""Integration tests for concurrency config wiring.

These tests verify that RuntimeConcurrencyConfig is properly wired through
the CLI -> Orchestrator -> RowProcessor -> TransformExecutor pipeline.

STATUS: IMPLEMENTED
- Orchestrator: accepts concurrency_config parameter
- TransformExecutor: accepts max_workers parameter
- RowProcessor: accepts max_workers and forwards to TransformExecutor
"""

from elspeth.contracts.config import RuntimeConcurrencyConfig
from elspeth.core.config import ConcurrencySettings
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.engine.executors import TransformExecutor
from elspeth.engine.orchestrator import Orchestrator
from elspeth.engine.processor import RowProcessor
from elspeth.engine.spans import SpanFactory


class TestConcurrencyConfigInOrchestrator:
    """Test that RuntimeConcurrencyConfig is properly passed to Orchestrator."""

    def test_orchestrator_accepts_concurrency_config(self) -> None:
        """Orchestrator constructor accepts concurrency_config parameter."""
        db = LandscapeDB.in_memory()
        config = RuntimeConcurrencyConfig(max_workers=8)

        try:
            # Should not raise
            orchestrator = Orchestrator(db, concurrency_config=config)
            assert orchestrator._concurrency_config is config
            assert orchestrator._concurrency_config.max_workers == 8
        finally:
            db.close()

    def test_orchestrator_accepts_none_config(self) -> None:
        """Orchestrator works without concurrency config."""
        db = LandscapeDB.in_memory()

        try:
            orchestrator = Orchestrator(db, concurrency_config=None)
            assert orchestrator._concurrency_config is None
        finally:
            db.close()

    def test_config_from_settings(self) -> None:
        """RuntimeConcurrencyConfig.from_settings() creates config correctly."""
        settings = ConcurrencySettings(max_workers=16)
        config = RuntimeConcurrencyConfig.from_settings(settings)

        assert config.max_workers == 16


class TestConcurrencyConfigInTransformExecutor:
    """Test that max_workers is passed to TransformExecutor."""

    def test_executor_accepts_max_workers(self) -> None:
        """TransformExecutor constructor accepts max_workers parameter."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        span_factory = SpanFactory()

        try:
            executor = TransformExecutor(recorder, span_factory, max_workers=8)
            assert executor._max_workers == 8
        finally:
            db.close()

    def test_executor_without_max_workers(self) -> None:
        """TransformExecutor works without max_workers (no cap)."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        span_factory = SpanFactory()

        try:
            executor = TransformExecutor(recorder, span_factory)
            assert executor._max_workers is None
        finally:
            db.close()


class TestConcurrencyConfigInRowProcessor:
    """Test that max_workers flows through RowProcessor."""

    def test_processor_accepts_max_workers(self) -> None:
        """RowProcessor constructor accepts and forwards max_workers."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        span_factory = SpanFactory()

        try:
            processor = RowProcessor(
                recorder=recorder,
                span_factory=span_factory,
                run_id="test-run",
                source_node_id="source-1",
                max_workers=4,
            )
            # Verify max_workers was passed to TransformExecutor
            assert processor._transform_executor._max_workers == 4
        finally:
            db.close()

    def test_processor_without_max_workers(self) -> None:
        """RowProcessor works without max_workers."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        span_factory = SpanFactory()

        try:
            processor = RowProcessor(
                recorder=recorder,
                span_factory=span_factory,
                run_id="test-run",
                source_node_id="source-1",
            )
            # No max_workers means no cap
            assert processor._transform_executor._max_workers is None
        finally:
            db.close()


class TestConcurrencyConfigProtocolCompliance:
    """Test that RuntimeConcurrencyConfig implements RuntimeConcurrencyProtocol."""

    def test_protocol_compliance(self) -> None:
        """RuntimeConcurrencyConfig satisfies RuntimeConcurrencyProtocol."""
        from elspeth.contracts.config import RuntimeConcurrencyConfig, RuntimeConcurrencyProtocol

        config = RuntimeConcurrencyConfig(max_workers=8)

        # Protocol requires max_workers property
        assert isinstance(config, RuntimeConcurrencyProtocol)
        assert config.max_workers == 8

    def test_orchestrator_accepts_protocol(self) -> None:
        """Orchestrator accepts any object implementing RuntimeConcurrencyProtocol."""
        from dataclasses import dataclass

        from elspeth.contracts.config import RuntimeConcurrencyProtocol

        @dataclass(frozen=True)
        class CustomConcurrencyConfig:
            """Custom implementation of RuntimeConcurrencyProtocol."""

            max_workers: int

        # Verify it satisfies the protocol
        custom_config = CustomConcurrencyConfig(max_workers=12)
        assert isinstance(custom_config, RuntimeConcurrencyProtocol)

        # Verify Orchestrator accepts it
        db = LandscapeDB.in_memory()
        try:
            orchestrator = Orchestrator(db, concurrency_config=custom_config)
            assert orchestrator._concurrency_config.max_workers == 12
        finally:
            db.close()
