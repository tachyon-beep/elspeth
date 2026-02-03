# tests/engine/test_tokens.py
"""Tests for TokenManager."""

from typing import Any

from elspeth.contracts import NodeType, SourceRow
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _make_observed_contract(*field_names: str) -> SchemaContract:
    """Create an OBSERVED mode contract with specified fields."""
    fields = tuple(
        FieldContract(
            normalized_name=name,
            original_name=f"'{name}'",
            python_type=object,  # Accept any type
            required=False,
            source="inferred",
        )
        for name in field_names
    )
    return SchemaContract(mode="OBSERVED", fields=fields, locked=False)


def _make_source_row(data: dict[str, Any]) -> SourceRow:
    """Create a SourceRow with an OBSERVED contract containing all data fields."""
    contract = _make_observed_contract(*data.keys())
    return SourceRow.valid(data, contract=contract)


def _make_pipeline_row(data: dict[str, Any], contract: SchemaContract | None = None) -> PipelineRow:
    """Create a PipelineRow with an OBSERVED contract if not provided."""
    if contract is None:
        contract = _make_observed_contract(*data.keys())
    return PipelineRow(data, contract)


class TestTokenManager:
    """High-level token management."""

    def test_create_initial_token(self) -> None:
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        token_info = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        assert token_info.row_id is not None
        assert token_info.token_id is not None
        assert isinstance(token_info.row_data, PipelineRow)
        assert token_info.row_data.to_dict() == {"value": 42}

    def test_fork_token(self) -> None:
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        # step_in_pipeline is required - Orchestrator/RowProcessor is the authority
        # run_id is required for atomic outcome recording
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["stats", "classifier"],
            step_in_pipeline=1,  # Fork happens at step 1
            run_id=run.run_id,
        )

        assert len(children) == 2
        assert children[0].branch_name == "stats"
        assert children[1].branch_name == "classifier"
        # Children inherit row_data (as PipelineRow)
        assert isinstance(children[0].row_data, PipelineRow)
        assert children[0].row_data.to_dict() == {"value": 42}

    def test_update_row_data(self) -> None:
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        token_info = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"x": 1}),
        )

        # Create new PipelineRow for update
        new_row = _make_pipeline_row({"x": 1, "y": 2})
        updated = manager.update_row_data(token_info, new_data=new_row)

        assert isinstance(updated.row_data, PipelineRow)
        assert updated.row_data.to_dict() == {"x": 1, "y": 2}
        assert updated.token_id == token_info.token_id  # Same token


class TestTokenManagerCoalesce:
    """Test token coalescing (join operations)."""

    def test_coalesce_tokens(self) -> None:
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        # Create initial token and fork it
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["stats", "classifier"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        # Update children with branch-specific data
        stats_token = manager.update_row_data(
            children[0],
            new_data=_make_pipeline_row({"value": 42, "mean": 10.5}),
        )
        classifier_token = manager.update_row_data(
            children[1],
            new_data=_make_pipeline_row({"value": 42, "label": "A"}),
        )

        # Coalesce the branches (merged_data is now PipelineRow)
        merged = manager.coalesce_tokens(
            parents=[stats_token, classifier_token],
            merged_data=_make_pipeline_row({"value": 42, "mean": 10.5, "label": "A"}),
            step_in_pipeline=3,
        )

        assert merged.token_id is not None
        assert merged.row_id == initial.row_id
        assert isinstance(merged.row_data, PipelineRow)
        assert merged.row_data.to_dict() == {"value": 42, "mean": 10.5, "label": "A"}


class TestTokenManagerForkIsolation:
    """Test that forked tokens have isolated row_data (no shared mutable objects).

    Note: PipelineRow is immutable (MappingProxyType), so we test isolation
    via to_dict() and verify deepcopy produces independent copies.
    """

    def test_fork_nested_data_isolation(self) -> None:
        """Forked children must have independent copies of nested data.

        Bug: P2-2026-01-20-forked-token-row-data-shallow-copy-leaks-nested-mutations
        When row_data contains nested dicts/lists, shallow copy causes siblings
        to share nested objects. Deepcopy via PipelineRow.__deepcopy__ prevents this.
        """
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        # Create token with NESTED data (common from JSON sources)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"payload": {"x": 1, "y": 2}, "items": [1, 2, 3]}),
        )

        # Fork to two branches
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["branch_a", "branch_b"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        child_a = children[0]
        child_b = children[1]

        # Get dict copies - PipelineRow is immutable so we verify via to_dict()
        dict_a = child_a.row_data.to_dict()
        dict_b = child_b.row_data.to_dict()

        # Mutate dict_a's nested data
        dict_a["payload"]["x"] = 999
        dict_a["items"].append(4)

        # Get fresh dict from child_b - should be unaffected
        dict_b_fresh = child_b.row_data.to_dict()
        assert dict_b_fresh["payload"]["x"] == 1, "Nested dict mutation leaked to sibling!"
        assert dict_b_fresh["items"] == [1, 2, 3], "Nested list mutation leaked to sibling!"

    def test_fork_with_custom_nested_data_isolation(self) -> None:
        """Custom row_data in fork should also be deep copied."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 1}),
        )

        # Fork with custom nested row_data (as PipelineRow)
        custom_data = _make_pipeline_row({"nested": {"key": "original"}})
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["a", "b"],
            step_in_pipeline=1,
            run_id=run.run_id,
            row_data=custom_data,
        )

        # Get dict copies and mutate one
        dict_0 = children[0].row_data.to_dict()
        dict_0["nested"]["key"] = "modified"

        # Siblings should be isolated
        dict_1 = children[1].row_data.to_dict()
        assert dict_1["nested"]["key"] == "original"


class TestTokenManagerExpandIsolation:
    """Test that expanded tokens have isolated row_data (no shared mutable objects).

    Mirrors TestTokenManagerForkIsolation - both fork_token and expand_token
    create sibling tokens that must have independent data.

    Note: PipelineRow is immutable, so we test isolation via to_dict().
    """

    def test_expand_nested_data_isolation(self) -> None:
        """Expanded children must have independent copies of nested data.

        Bug: P2-2026-01-21-expand-token-shared-row-data
        When expanded_rows contain nested dicts/lists, shallow copy causes siblings
        to share nested objects. Deepcopy in expand_token prevents this.
        """
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        # Create parent token
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"original": "data"}),
        )

        # Expand with NESTED data (common from batch aggregations)
        expanded_rows = [
            {"payload": {"x": 1, "y": 2}, "items": [1, 2, 3]},
            {"payload": {"x": 10, "y": 20}, "items": [10, 20, 30]},
        ]

        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=expanded_rows,
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        child_a = children[0]
        child_b = children[1]

        # Get dict copies and mutate one
        dict_a = child_a.row_data.to_dict()
        dict_a["payload"]["x"] = 999
        dict_a["items"].append(4)

        # Get fresh dict from child_b - should be unaffected
        dict_b = child_b.row_data.to_dict()
        assert dict_b["payload"]["x"] == 10, "Nested dict mutation leaked to sibling!"
        assert dict_b["items"] == [10, 20, 30], "Nested list mutation leaked to sibling!"

    def test_expand_shared_input_isolation(self) -> None:
        """Expanded tokens must be isolated even when input rows share objects.

        This tests the case where a plugin returns rows with shared nested objects
        (e.g., using dict(row) shallow copy). TokenManager must isolate them.
        """
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 1}),
        )

        # Simulate plugin using dict(row) shallow copy - SHARED nested object
        shared_metadata = {"version": 1, "tags": ["a", "b"]}
        expanded_rows = [
            {"id": 1, "meta": shared_metadata},  # Both point to SAME dict!
            {"id": 2, "meta": shared_metadata},
        ]

        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=expanded_rows,
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        # Get dict copies and mutate one
        dict_0 = children[0].row_data.to_dict()
        dict_0["meta"]["version"] = 999
        dict_0["meta"]["tags"].append("mutated")

        # Get fresh dict from child 1 - must NOT see the mutation
        dict_1 = children[1].row_data.to_dict()
        assert dict_1["meta"]["version"] == 1, "Shared object mutation leaked!"
        assert dict_1["meta"]["tags"] == ["a", "b"], "Shared list mutation leaked!"

    def test_expand_deep_nesting_isolation(self) -> None:
        """Test isolation with deeply nested structures (3+ levels)."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 1}),
        )

        # Deep nesting: dict -> list -> dict -> list
        expanded_rows = [
            {"level1": {"level2": [{"level3": ["deep_value"]}]}},
            {"level1": {"level2": [{"level3": ["deep_value"]}]}},
        ]

        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=expanded_rows,
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        # Get dict copies and mutate at the deepest level
        dict_0 = children[0].row_data.to_dict()
        dict_0["level1"]["level2"][0]["level3"][0] = "MUTATED"

        # Sibling must be unaffected
        dict_1 = children[1].row_data.to_dict()
        assert dict_1["level1"]["level2"][0]["level3"][0] == "deep_value"


class TestTokenManagerEdgeCases:
    """Test edge cases and error handling."""

    def test_fork_with_custom_row_data(self) -> None:
        """Fork can override parent row_data."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        # Fork with custom row_data (as PipelineRow)
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["branch_a"],
            step_in_pipeline=1,
            run_id=run.run_id,
            row_data=_make_pipeline_row({"value": 42, "forked": True}),
        )

        assert children[0].row_data.to_dict() == {"value": 42, "forked": True}

    def test_update_preserves_branch_name(self) -> None:
        """update_row_data preserves branch_name."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"x": 1}),
        )

        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["my_branch"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        updated = manager.update_row_data(
            children[0],
            new_data=_make_pipeline_row({"x": 1, "y": 2}),
        )

        assert updated.branch_name == "my_branch"

    def test_update_preserves_all_lineage_fields(self) -> None:
        """update_row_data must preserve ALL lineage metadata fields.

        Bug: P2-2026-01-31-update-row-data-drops-lineage
        update_row_data() was only preserving branch_name, dropping:
        - fork_group_id
        - join_group_id
        - expand_group_id
        """
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"x": 1}),
        )

        # Fork to get a token with fork_group_id
        forked_children, fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["stats_branch"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )
        forked_token = forked_children[0]

        # Verify fork created the fork_group_id
        assert forked_token.fork_group_id == fork_group_id
        assert forked_token.branch_name == "stats_branch"

        # Update the forked token's row data
        updated = manager.update_row_data(
            forked_token,
            new_data=_make_pipeline_row({"x": 1, "y": 2}),
        )

        # ALL lineage fields must be preserved
        assert updated.row_data.to_dict() == {"x": 1, "y": 2}, "row_data should be updated"
        assert updated.token_id == forked_token.token_id, "token_id must be preserved"
        assert updated.row_id == forked_token.row_id, "row_id must be preserved"
        assert updated.branch_name == "stats_branch", "branch_name must be preserved"
        assert updated.fork_group_id == fork_group_id, "fork_group_id must be preserved"

    def test_update_preserves_expand_group_id(self) -> None:
        """update_row_data must preserve expand_group_id from expanded tokens."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"original": "data"}),
        )

        # Expand to get tokens with expand_group_id
        expanded_children, expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=[{"id": 1}, {"id": 2}],
            step_in_pipeline=2,
            run_id=run.run_id,
        )
        expanded_token = expanded_children[0]

        # Verify expand created the expand_group_id
        assert expanded_token.expand_group_id == expand_group_id

        # Update the expanded token's row data
        updated = manager.update_row_data(
            expanded_token,
            new_data=_make_pipeline_row({"id": 1, "processed": True}),
        )

        # expand_group_id must be preserved
        assert updated.expand_group_id == expand_group_id, "expand_group_id must be preserved"

    def test_update_preserves_join_group_id(self) -> None:
        """update_row_data must preserve join_group_id from coalesced tokens."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        # Fork and then coalesce to get a token with join_group_id
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["a", "b"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        merged = manager.coalesce_tokens(
            parents=children,
            merged_data=_make_pipeline_row({"value": 42, "merged": True}),
            step_in_pipeline=3,
        )

        # Verify coalesce created join_group_id
        assert merged.join_group_id is not None

        # Update the merged token's row data
        updated = manager.update_row_data(
            merged,
            new_data=_make_pipeline_row({"value": 42, "merged": True, "enriched": "yes"}),
        )

        # join_group_id must be preserved
        assert updated.join_group_id == merged.join_group_id, "join_group_id must be preserved"

    def test_multiple_rows_different_tokens(self) -> None:
        """Each source row gets its own row_id and token_id."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        token1 = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"id": 1}),
        )
        token2 = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=1,
            source_row=_make_source_row({"id": 2}),
        )

        assert token1.row_id != token2.row_id
        assert token1.token_id != token2.token_id


class TestTokenManagerStepInPipeline:
    """Test that step_in_pipeline flows through to audit trail."""

    def test_fork_stores_step_in_pipeline(self) -> None:
        """TokenManager.fork_token passes step_in_pipeline to recorder."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        # Fork with step_in_pipeline=2
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["a", "b"],
            step_in_pipeline=2,
            run_id=run.run_id,
        )

        # Verify step_in_pipeline is stored in audit trail
        token_a = recorder.get_token(children[0].token_id)
        token_b = recorder.get_token(children[1].token_id)
        assert token_a is not None
        assert token_b is not None
        assert token_a.step_in_pipeline == 2
        assert token_b.step_in_pipeline == 2

    def test_coalesce_stores_step_in_pipeline(self) -> None:
        """TokenManager.coalesce_tokens passes step_in_pipeline to recorder."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"value": 42}),
        )

        # Fork and then coalesce
        children, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["a", "b"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )

        merged = manager.coalesce_tokens(
            parents=children,
            merged_data=_make_pipeline_row({"value": 42, "merged": True}),
            step_in_pipeline=3,
        )

        # Verify step_in_pipeline is stored in audit trail
        merged_token = recorder.get_token(merged.token_id)
        assert merged_token is not None
        assert merged_token.step_in_pipeline == 3


class TestTokenManagerExpand:
    """Test token expansion (deaggregation: 1 input -> N outputs)."""

    def test_expand_token_creates_children(self) -> None:
        """expand_token creates child tokens for each expanded row."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        # Create initial token
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"original": "data"}),
        )

        expanded_rows = [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
            {"id": 3, "value": "c"},
        ]

        # Act
        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=expanded_rows,
            step_in_pipeline=2,
            run_id=run.run_id,
        )

        # Assert: correct number of children
        assert len(children) == 3

        # All children share same row_id (same source row)
        for child in children:
            assert child.row_id == parent.row_id
            assert child.token_id != parent.token_id

        # Each child has its expanded row data (as PipelineRow)
        assert isinstance(children[0].row_data, PipelineRow)
        assert children[0].row_data.to_dict() == {"id": 1, "value": "a"}
        assert children[1].row_data.to_dict() == {"id": 2, "value": "b"}
        assert children[2].row_data.to_dict() == {"id": 3, "value": "c"}

        # Verify parent relationships in database
        for i, child in enumerate(children):
            parents = recorder.get_token_parents(child.token_id)
            assert len(parents) == 1
            assert parents[0].parent_token_id == parent.token_id
            assert parents[0].ordinal == i

    def test_expand_token_inherits_branch_name(self) -> None:
        """expand_token children inherit parent's branch_name."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)

        # Create initial token and fork to get a branch_name
        initial = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({}),
        )

        # Fork to get a token with branch_name
        forked, _fork_group_id = manager.fork_token(
            parent_token=initial,
            branches=["stats_branch"],
            step_in_pipeline=1,
            run_id=run.run_id,
        )
        parent = forked[0]  # Has branch_name="stats_branch"

        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=[{"a": 1}, {"a": 2}],
            step_in_pipeline=2,
            run_id=run.run_id,
        )

        # Children inherit branch_name
        assert all(c.branch_name == "stats_branch" for c in children)

    def test_expand_token_stores_step_in_pipeline(self) -> None:
        """expand_token passes step_in_pipeline to recorder."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.tokens import TokenManager

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        manager = TokenManager(recorder)
        parent = manager.create_initial_token(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            source_row=_make_source_row({"x": 1}),
        )

        children, _expand_group_id = manager.expand_token(
            parent_token=parent,
            expanded_rows=[{"a": 1}, {"a": 2}],
            step_in_pipeline=5,
            run_id=run.run_id,
        )

        # Verify step_in_pipeline is stored in audit trail
        for child in children:
            db_token = recorder.get_token(child.token_id)
            assert db_token is not None
            assert db_token.step_in_pipeline == 5
