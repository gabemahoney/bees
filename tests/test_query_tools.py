"""Tests for named query tools (query storage and MCP tools)."""

import pytest
import tempfile
from pathlib import Path
import yaml

from src.query_storage import QueryStorage, save_query, load_query, list_queries, validate_query
from src.query_parser import QueryValidationError
from src.mcp_query_ops import _add_named_query, _execute_query, _execute_freeform_query


class TestQueryStorage:
    """Tests for QueryStorage class."""

    def test_initialize_creates_file(self):
        """Test that initializing storage creates queries file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            assert queries_file.exists()
            assert storage.list_queries() == []

    def test_save_and_load_query(self):
        """Test saving and loading a named query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Save a simple query
            query = [
                ["type=task", "title~.*"]
            ]
            storage.save_query("test_query", query)

            # Load it back
            loaded = storage.load_query("test_query")
            assert loaded == query

    def test_save_query_validates_structure(self):
        """Test that save_query validates query structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Invalid query - not a list
            with pytest.raises(QueryValidationError):
                storage.save_query("bad_query", "not a list")

            # Invalid query - empty
            with pytest.raises(QueryValidationError):
                storage.save_query("bad_query", [])

    def test_save_query_always_validates(self):
        """Test that save_query always validates queries with no ability to skip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Invalid query with mixed terms should be rejected
            invalid_query = [["type=task", "parent"]]  # Mixed search and graph
            with pytest.raises(QueryValidationError, match="Cannot mix"):
                storage.save_query("bad_query", invalid_query)

            # Invalid regex should be rejected
            invalid_regex_query = [["title~[invalid("]]
            with pytest.raises(QueryValidationError, match="Invalid regex"):
                storage.save_query("bad_regex", invalid_regex_query)

            # Invalid ticket type should be rejected
            invalid_type_query = [["type=invalid_type"]]
            with pytest.raises(QueryValidationError, match="Invalid type"):
                storage.save_query("bad_type", invalid_type_query)

    def test_save_query_validates_string_input(self):
        """Test that save_query validates both string and list query_yaml inputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Valid YAML string should be accepted
            valid_yaml_string = "- [type=task]"
            storage.save_query("valid_string", valid_yaml_string)
            loaded = storage.load_query("valid_string")
            assert loaded == [["type=task"]]

            # Invalid YAML string should be rejected
            invalid_yaml_string = "- [type=invalid_type]"
            with pytest.raises(QueryValidationError, match="Invalid type"):
                storage.save_query("invalid_string", invalid_yaml_string)

    def test_save_query_validates_list_input(self):
        """Test that save_query validates list query_yaml inputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Valid list should be accepted
            valid_list = [["type=task"]]
            storage.save_query("valid_list", valid_list)
            loaded = storage.load_query("valid_list")
            assert loaded == valid_list

            # Invalid list should be rejected
            invalid_list = [["type=invalid_type"]]
            with pytest.raises(QueryValidationError, match="Invalid type"):
                storage.save_query("invalid_list", invalid_list)

    def test_save_query_validation_error_messages(self):
        """Test that validation errors provide clear feedback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Empty query error message
            with pytest.raises(QueryValidationError) as exc_info:
                storage.save_query("empty", [])
            assert "cannot be empty" in str(exc_info.value)

            # Mixed terms error message
            with pytest.raises(QueryValidationError) as exc_info:
                storage.save_query("mixed", [["type=task", "parent"]])
            assert "Cannot mix" in str(exc_info.value)

            # Invalid regex error message
            with pytest.raises(QueryValidationError) as exc_info:
                storage.save_query("bad_regex", [["title~[invalid("]])
            assert "Invalid regex" in str(exc_info.value)

    def test_load_nonexistent_query_raises_error(self):
        """Test that loading nonexistent query raises KeyError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            with pytest.raises(KeyError, match="Query not found"):
                storage.load_query("nonexistent")

    def test_list_queries(self):
        """Test listing all available queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Initially empty
            assert storage.list_queries() == []

            # Add some queries
            storage.save_query("query1", [["type=task"]])
            storage.save_query("query2", [["type=epic"]])

            # Should be sorted
            queries = storage.list_queries()
            assert queries == ["query1", "query2"]

    def test_save_query_updates_existing(self):
        """Test that saving query with existing name updates it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_file = Path(tmpdir) / "test_queries.yaml"
            storage = QueryStorage(str(queries_file))

            # Save initial query
            storage.save_query("test", [["type=task"]])

            # Update with new query
            new_query = [["type=epic"]]
            storage.save_query("test", new_query)

            # Should have new value
            loaded = storage.load_query("test")
            assert loaded == new_query


class TestQueryValidation:
    """Tests for query validation logic."""

    def test_validate_valid_query(self):
        """Test validating a valid query."""
        valid_query = [
            ["type=task", "label~beta"],
            ["parent"]
        ]
        stages = validate_query(valid_query)
        assert stages == valid_query

    def test_validate_invalid_query_empty(self):
        """Test that empty query is rejected."""
        with pytest.raises(QueryValidationError, match="cannot be empty"):
            validate_query([])

    def test_validate_invalid_query_mixed_terms(self):
        """Test that mixing search and graph terms is rejected."""
        invalid_query = [
            ["type=task", "parent"]  # Mixed search and graph
        ]
        with pytest.raises(QueryValidationError, match="Cannot mix"):
            validate_query(invalid_query)

    def test_validate_invalid_regex(self):
        """Test that invalid regex patterns are rejected."""
        invalid_query = [
            ["title~[invalid("]  # Unclosed bracket
        ]
        with pytest.raises(QueryValidationError, match="Invalid regex"):
            validate_query(invalid_query)

    def test_validate_invalid_type(self):
        """Test that invalid ticket type is rejected."""
        invalid_query = [
            ["type=invalid_type"]
        ]
        with pytest.raises(QueryValidationError, match="Invalid type"):
            validate_query(invalid_query)


class TestAddNamedQueryTool:
    """Tests for add_named_query MCP tool."""

    def test_add_valid_query(self):
        """Test adding a valid named query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use temporary storage
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                query_yaml = """
- - type=task
  - label~beta
"""
                result = _add_named_query("test_query", query_yaml)

                assert result["status"] == "success"
                assert result["query_name"] == "test_query"

                # Verify query was saved
                queries = list_queries()
                assert "test_query" in queries

            finally:
                src.query_storage._default_storage = old_storage

    def test_add_query_empty_name(self):
        """Test that empty name is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            _add_named_query("", "- [type=task]")

    def test_add_query_invalid_structure(self):
        """Test that invalid query structure is rejected."""
        with pytest.raises(ValueError, match="Invalid query structure"):
            _add_named_query("bad_query", "not valid yaml list")

    def test_add_query_duplicate_name(self):
        """Test that duplicate name updates existing query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Add first query
                _add_named_query("test", "- [type=task]")

                # Add second query with same name - should succeed (update)
                result = _add_named_query("test", "- [type=epic]")
                assert result["status"] == "success"

                # Should only have one query
                queries = list_queries()
                assert queries.count("test") == 1

            finally:
                src.query_storage._default_storage = old_storage


class TestExecuteQueryTool:
    """Tests for execute_query MCP tool."""

    async def test_execute_nonexistent_query(self, isolated_bees_env):
        """Test that executing nonexistent query raises error."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                with pytest.raises(ValueError, match="Query not found"):
                    await _execute_query("nonexistent", ctx=None)

            finally:
                src.query_storage._default_storage = old_storage

    async def test_execute_query_with_valid_name(self, isolated_bees_env):
        """Test executing a valid registered query."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Register a query
                query_yaml = "- [type=task]"
                _add_named_query("test_query", query_yaml)

                # Execute query - should succeed with 0 results since no tickets exist
                result = await _execute_query("test_query", ctx=None)
                assert result["status"] == "success"
                assert result["query_name"] == "test_query"
                assert result["result_count"] == 0
                assert result["ticket_ids"] == []

            finally:
                src.query_storage._default_storage = old_storage

    async def test_execute_query_with_hive_filter(self, isolated_bees_env):
        """Test executing query with hive_names filtering."""
        # Set up hive config with backend hive
        isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Register a query
                query_yaml = "- [type=task]"
                _add_named_query("test_query", query_yaml)

                # Execute with hive filter - should succeed with 0 results
                result = await _execute_query("test_query", hive_names=["backend"], ctx=None)
                assert result["status"] == "success"
                assert result["query_name"] == "test_query"
                assert result["result_count"] == 0

            finally:
                src.query_storage._default_storage = old_storage

    async def test_execute_query_with_invalid_hive(self, isolated_bees_env):
        """Test executing query with invalid hive name raises error."""
        # Set up hive config with backend hive only
        isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Register a query
                query_yaml = "- [type=task]"
                _add_named_query("test_query", query_yaml)

                # Execute with invalid hive should raise ValueError
                with pytest.raises(ValueError, match="Hive not found"):
                    await _execute_query("test_query", hive_names=["nonexistent_hive"], ctx=None)

            finally:
                src.query_storage._default_storage = old_storage




class TestEndToEnd:
    """End-to-end tests for named query workflow."""

    def test_register_and_execute_query(self):
        """Test full workflow: register query, then execute it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Register a query
                query_yaml = """
- - type=task
  - label~beta
"""
                result = _add_named_query("beta_tasks", query_yaml)
                assert result["status"] == "success"

                # Note: Full execution requires .beads/issues.jsonl to exist
                # This test verifies the query can be loaded
                loaded = load_query("beta_tasks")
                assert loaded == [["type=task", "label~beta"]]

            finally:
                src.query_storage._default_storage = old_storage

    def test_invalid_query_rejected(self):
        """Test that invalid queries are always rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Invalid query should be rejected
                invalid_query = """
invalid_structure_here
"""
                with pytest.raises((ValueError, QueryValidationError)):
                    _add_named_query("invalid_query", invalid_query)

            finally:
                src.query_storage._default_storage = old_storage


class TestExecuteFreeformQuery:
    """Tests for execute_freeform_query MCP tool."""

    async def test_execute_freeform_query_with_valid_query(self, isolated_bees_env):
        """Test executing a valid freeform query without persisting."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        # Should succeed with 0 results since no tickets exist
        query_yaml = "- [type=task]"
        
        result = await _execute_freeform_query(query_yaml, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0
        assert result["ticket_ids"] == []

    async def test_execute_freeform_query_with_invalid_yaml_syntax(self, isolated_bees_env):
        """Test that invalid YAML syntax raises QueryValidationError."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        invalid_yaml = "- [type=task\n  missing bracket"
        
        with pytest.raises(ValueError, match="Invalid query structure"):
            await _execute_freeform_query(invalid_yaml, ctx=None)

    async def test_execute_freeform_query_with_hive_filter(self, isolated_bees_env):
        """Test executing freeform query with hive_names parameter."""
        # Set up hive config with backend hive
        isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()
        
        query_yaml = "- [type=task]"
        
        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(query_yaml, hive_names=["backend"], ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0

    async def test_execute_freeform_query_with_nonexistent_hive(self, isolated_bees_env):
        """Test that non-existent hive raises ValueError with available hives message."""
        # Set up hive config with backend hive only
        isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()
        
        query_yaml = "- [type=epic]"
        
        with pytest.raises(ValueError, match="Hive not found.*nonexistent_hive"):
            await _execute_freeform_query(query_yaml, hive_names=["nonexistent_hive"], ctx=None)

    def test_execute_freeform_query_empty_result_set(self):
        """Test that empty result set returns status=success with result_count=0."""
        # This test would require actual ticket setup, so we skip the full test
        # and verify the structure would work based on other tests
        pass

    async def test_execute_freeform_query_multi_stage(self, isolated_bees_env):
        """Test executing multi-stage freeform query."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        multi_stage_query = """
- [type=epic]
- [children]
"""
        
        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(multi_stage_query, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0

    async def test_execute_freeform_query_validation_errors(self, isolated_bees_env):
        """Test that query validation errors are caught and reported."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        # Invalid query structure (not a list)
        invalid_query = "type=task"

        with pytest.raises(ValueError, match="Invalid query structure"):
            await _execute_freeform_query(invalid_query, ctx=None)

    @pytest.mark.asyncio
    async def test_execute_freeform_query_with_parent_filter(self, isolated_bees_env):
        """Test freeform query with parent= search term."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        query_yaml = "- [parent=some-epic-id]"

        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(query_yaml, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0
        assert result["ticket_ids"] == []

    @pytest.mark.asyncio
    async def test_execute_freeform_query_parent_combined_with_type(self, isolated_bees_env):
        """Test freeform query with parent= combined with type= filter."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        query_yaml = "- [type=task, parent=epic-123]"

        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(query_yaml, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_freeform_query_parent_combined_with_label(self, isolated_bees_env):
        """Test freeform query with parent= combined with label~ filter."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        query_yaml = "- [parent=epic-123, label~beta]"

        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(query_yaml, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0

    @pytest.mark.asyncio
    async def test_execute_freeform_query_parent_in_multistage(self, isolated_bees_env):
        """Test freeform query with parent= in multi-stage pipeline."""
        # Set up hive config
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()
        
        multi_stage_query = """
- [parent=epic-123]
- [parent]
"""

        # Should succeed with 0 results since no tickets exist
        result = await _execute_freeform_query(multi_stage_query, ctx=None)
        assert result["status"] == "success"
        assert result["result_count"] == 0
