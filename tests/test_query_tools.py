"""
Unit tests for MCP query tools (config-backed named queries).

PURPOSE:
Tests MCP tools for registering, executing, listing, and deleting named queries,
plus config-backed resolution and conflict-checking logic.

SCOPE - Tests that belong here:
- _add_named_query(): MCP tool for registering queries
- _execute_named_query(): MCP tool for running named queries
- _execute_freeform_query(): MCP tool for ad-hoc queries
- _delete_named_query(): MCP tool for removing named queries
- _list_named_queries(): MCP tool for listing available queries
- resolve_named_query(): Config resolution logic
- check_query_name_conflict(): Uniqueness checking logic
- Error handling: duplicate names, invalid queries, scope resolution

SCOPE - Tests that DON'T belong here:
- Query parsing -> test_query_parser.py
- Query execution logic -> test_pipeline.py
- Search execution -> test_search_executor.py
- Graph execution -> test_graph_executor.py
- Multi-hive filtering -> test_multi_hive_query.py

RELATED FILES:
- test_query_parser.py: Query parsing and validation
- test_pipeline.py: Query execution engine
- test_multi_hive_query.py: Multi-hive query filtering
"""

from pathlib import Path

import pytest

from src.config import check_query_name_conflict, resolve_named_query
from src.mcp_query_ops import (
    _add_named_query,
    _delete_named_query,
    _execute_freeform_query,
    _execute_named_query,
    _list_named_queries,
)
from tests.conftest import write_global_queries, write_scoped_config
from tests.test_constants import (
    HIVE_BACKEND,
    RESULT_STATUS_SUCCESS,
)


class TestAddNamedQueryTool:
    """Tests for add_named_query MCP tool with config-backed storage."""

    def test_global_scope_succeeds(self, tmp_path, mock_global_bees_dir):
        """scope='global' succeeds; query readable from global config."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("my_query", "- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "my_query"

        from src.config import load_global_config

        gc = load_global_config()
        assert "my_query" in gc.get("queries", {})

    def test_repo_scope_succeeds(self, tmp_path, mock_global_bees_dir):
        """scope='repo' succeeds when repo root is registered."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("repo_q", "- [type=t1]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        assert "repo_q" in gc["scopes"][str(tmp_path)].get("queries", {})

    def test_repo_scope_not_found(self, tmp_path, mock_global_bees_dir):
        """scope='repo' returns scope_not_found for unregistered repo root."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("q", "- [type=t1]", scope="repo", resolved_root=Path("/unregistered/repo"))
        assert result["status"] == "error"
        assert result["error_type"] == "scope_not_found"

    def test_invalid_scope(self, tmp_path, mock_global_bees_dir):
        """Returns invalid_scope for unrecognized scope value."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("q", "- [type=t1]", scope="invalid", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_scope"

    def test_global_name_conflict(self, tmp_path, mock_global_bees_dir):
        """Rejects name at global level with query_name_conflict."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        write_global_queries(mock_global_bees_dir, {"q1": [["type=bee"]]})

        result = _add_named_query("q1", "- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_repo_name_conflict(self, tmp_path, mock_global_bees_dir):
        """Rejects name at caller's repo scope with query_name_conflict."""
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}}, queries={"q1": [["type=t1"]]}
        )

        result = _add_named_query("q1", "- [type=bee]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_repo_succeeds_same_name_different_repo(self, tmp_path, mock_global_bees_dir):
        """scope='repo' succeeds when same name exists only in different repo's scope."""
        import json

        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        result = _add_named_query("q1", "- [type=bee]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

    def test_global_conflict_any_repo(self, tmp_path, mock_global_bees_dir):
        """scope='global' returns query_name_conflict when name exists in any repo scope."""
        import json

        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        result = _add_named_query("q1", "- [type=bee]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_empty_name_rejected(self, tmp_path, mock_global_bees_dir):
        """Empty name returns error dict."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("", "- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_query"
        assert "cannot be empty" in result["message"]


class TestExecuteNamedQueryTool:
    """Tests for execute_named_query MCP tool with config-backed resolution."""

    async def test_resolves_from_repo_scope(self, isolated_bees_env):
        """Query in caller's repo scope resolves and executes successfully."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(
            env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}},
            queries={"my_query": [["type=t1"]]},
        )

        result = await _execute_named_query("my_query", resolved_root=env.base_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "my_query"
        assert result["result_count"] == 0

    async def test_falls_through_to_global(self, isolated_bees_env):
        """Query only in global scope falls through and executes successfully."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}})
        write_global_queries(env.global_bees_dir, {"global_q": [["type=bee"]]})

        result = await _execute_named_query("global_q", resolved_root=env.base_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "global_q"

    async def test_returns_query_out_of_scope(self, isolated_bees_env):
        """Query in different repo's scope returns query_out_of_scope."""
        import json

        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}})
        config_path = env.global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        result = await _execute_named_query("other_q", resolved_root=env.base_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_out_of_scope"

    async def test_returns_query_not_found(self, isolated_bees_env):
        """Query absent everywhere returns query_not_found with available_queries list."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(
            env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}},
            queries={"repo_q": [["type=t1"]]},
        )
        write_global_queries(env.global_bees_dir, {"global_q": [["type=bee"]]})

        result = await _execute_named_query("nonexistent", resolved_root=env.base_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_not_found"
        assert "repo_q" in result["available_queries"]
        assert "global_q" in result["available_queries"]

    async def test_repo_scope_query_executes_with_resolved_root(self, isolated_bees_env):
        """Regression (b.zFJ): repo-scoped query succeeds when resolved_root is passed."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}})
        _add_named_query("repo_q", "- [type=bee]", scope="repo", resolved_root=env.base_path)

        result = await _execute_named_query("repo_q", resolved_root=env.base_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "repo_q"

    async def test_repo_scope_query_out_of_scope_when_root_is_none(self, isolated_bees_env):
        """Negative: repo-scoped query returns query_out_of_scope when resolved_root=None."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}})
        _add_named_query("repo_q", "- [type=bee]", scope="repo", resolved_root=env.base_path)

        result = await _execute_named_query("repo_q", resolved_root=None)
        assert result["status"] == "error"
        assert result["error_type"] == "query_out_of_scope"


class TestExecuteFreeformQuery:
    """Tests for execute_freeform_query MCP tool."""

    async def test_execute_freeform_query_basic(self, isolated_bees_env):
        """Test executing a valid freeform query without persisting."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("- [type=t1]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0
        assert result["ticket_ids"] == []

    @pytest.mark.parametrize(
        "invalid_yaml, error_match",
        [
            ("- [type=t1\n  missing bracket", "Invalid query structure"),
            ("type=t1", "Invalid query structure"),
        ],
    )
    async def test_execute_freeform_query_rejects_invalid(self, isolated_bees_env, invalid_yaml, error_match):
        """Test that invalid YAML syntax and structure return error dicts."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query(invalid_yaml)
        assert result["status"] == "error"
        assert result["error_type"] == "parse_error"
        assert error_match in result["message"]

    async def test_execute_freeform_query_with_hive_filter(self, isolated_bees_env):
        """Test executing freeform query with hive= search term."""
        isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("- [type=t1, hive=backend]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0

    async def test_execute_freeform_query_multi_stage(self, isolated_bees_env):
        """Test executing multi-stage freeform query."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("- [type=bee]\n- [children]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0

    @pytest.mark.parametrize(
        "query_yaml",
        [
            "- [parent=some-bee-id]",
            "- [type=t1, parent=bee-123]",
            "- [parent=bee-123, tag~beta]",
        ],
    )
    async def test_execute_freeform_query_with_parent_filter(self, isolated_bees_env, query_yaml):
        """Test freeform query with parent= search term and combinations."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query(query_yaml)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0

    async def test_execute_freeform_query_parent_in_multistage(self, isolated_bees_env):
        """Test freeform query with parent= in multi-stage pipeline."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("- [parent=bee-123]\n- [parent]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0


class TestResolveNamedQuery:
    """Tests for resolve_named_query config resolution logic."""

    def test_returns_from_repo_scope(self, tmp_path, mock_global_bees_dir):
        """Query found in caller's repo scope returns with scope='repo'."""
        scope_data = {"hives": {}, "child_tiers": {}}
        stages = [["type=t1"]]
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"my_query": stages})

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("my_query", tmp_path, gc)
        assert result == {"status": "found", "stages": stages, "scope": "repo"}

    def test_falls_through_to_global(self, tmp_path, mock_global_bees_dir):
        """Query only in global scope returns with scope='global'."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        write_global_queries(mock_global_bees_dir, {"global_q": [["type=bee"]]})

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("global_q", tmp_path, gc)
        assert result == {"status": "found", "stages": [["type=bee"]], "scope": "global"}

    def test_repo_takes_precedence(self, tmp_path, mock_global_bees_dir):
        """When both repo and global define same name, repo wins."""
        repo_stages = [["type=t1"]]
        global_stages = [["type=bee"]]
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"shared_q": repo_stages})
        write_global_queries(mock_global_bees_dir, {"shared_q": global_stages})

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("shared_q", tmp_path, gc)
        assert result == {"status": "found", "stages": repo_stages, "scope": "repo"}

    def test_out_of_scope(self, tmp_path, mock_global_bees_dir):
        """Query in a different repo's scope returns out_of_scope."""
        other_repo = Path("/other/repo")
        # Write config with two scopes: caller's (no queries) and other (has the query)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        # Manually add another scope with queries
        import json

        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"][str(other_repo)] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("other_q", tmp_path, gc)
        assert result == {"status": "out_of_scope"}

    def test_not_found(self, tmp_path, mock_global_bees_dir):
        """Query absent everywhere returns not_found."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("nonexistent", tmp_path, gc)
        assert result == {"status": "not_found"}


class TestCheckQueryNameConflict:
    """Tests for check_query_name_conflict uniqueness logic."""

    def test_repo_scope_conflict_at_repo(self, tmp_path, mock_global_bees_dir):
        """scope='repo', name in caller's repo scope → conflict returned."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"q1": [["type=t1"]]})

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "repo", tmp_path, gc)
        assert result is not None
        assert result["level"] == "repo"
        assert result["location"] == str(tmp_path)

    def test_repo_scope_conflict_at_global(self, tmp_path, mock_global_bees_dir):
        """scope='repo', name in global → conflict returned."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        write_global_queries(mock_global_bees_dir, {"q1": [["type=bee"]]})

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "repo", tmp_path, gc)
        assert result is not None
        assert result["level"] == "global"
        assert result["location"] == "global"

    def test_repo_scope_no_conflict_other_repo(self, tmp_path, mock_global_bees_dir):
        """scope='repo', name only in different repo → None (no conflict)."""
        import json

        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        # Add another scope with the query
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "repo", tmp_path, gc)
        assert result is None

    def test_global_scope_conflict_at_global(self, tmp_path, mock_global_bees_dir):
        """scope='global', name in global → conflict returned."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        write_global_queries(mock_global_bees_dir, {"q1": [["type=bee"]]})

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "global", tmp_path, gc)
        assert result is not None
        assert result["level"] == "global"
        assert result["location"] == "global"

    def test_global_scope_conflict_any_repo(self, tmp_path, mock_global_bees_dir):
        """scope='global', name in any repo scope (even different repo) → conflict returned."""
        import json

        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        # Add another repo scope with the query
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": [["type=t1"]]}}
        config_path.write_text(json.dumps(config, indent=2))

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "global", tmp_path, gc)
        assert result is not None
        assert result["level"] == "repo"
        assert result["location"] == "/other/repo"

    def test_no_conflict_anywhere(self, tmp_path, mock_global_bees_dir):
        """Name absent everywhere → None."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("nonexistent", "repo", tmp_path, gc)
        assert result is None


class TestDeleteNamedQueryTool:
    """Tests for _delete_named_query MCP tool with config-backed storage."""

    def test_delete_global_query_by_name(self, tmp_path, mock_global_bees_dir):
        """Deletes a globally-registered query by name, leaving others intact."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        write_global_queries(mock_global_bees_dir, {"doomed": [["type=bee"]], "keeper": [["type=t1"]]})

        result = _delete_named_query("doomed", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "doomed"

        from src.config import load_global_config

        gc = load_global_config()
        assert "doomed" not in gc.get("queries", {})
        assert "keeper" in gc["queries"]

    def test_delete_repo_query_by_name(self, tmp_path, mock_global_bees_dir):
        """Deletes a repo-scoped query by name, leaving others intact."""
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}},
            queries={"doomed": [["type=t1"]], "keeper": [["type=bee"]]},
        )

        result = _delete_named_query("doomed", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "doomed"

        from src.config import load_global_config

        gc = load_global_config()
        scope_queries = gc["scopes"][str(tmp_path)].get("queries", {})
        assert "doomed" not in scope_queries
        assert "keeper" in scope_queries

    def test_empty_dict_cleanup_repo(self, tmp_path, mock_global_bees_dir):
        """After deleting last repo query, 'queries' key is absent from scope entry."""
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}},
            queries={"only_one": [["type=t1"]]},
        )

        result = _delete_named_query("only_one", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        assert "queries" not in gc["scopes"][str(tmp_path)]

    def test_empty_dict_cleanup_global(self, tmp_path, mock_global_bees_dir):
        """After deleting last global query, top-level 'queries' key is absent."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        write_global_queries(mock_global_bees_dir, {"only_one": [["type=bee"]]})

        result = _delete_named_query("only_one", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        assert "queries" not in gc

    def test_returns_query_not_found(self, tmp_path, mock_global_bees_dir):
        """Name absent in global and all repo scopes returns query_not_found."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _delete_named_query("ghost", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_not_found"

    def test_deletes_query_regardless_of_scope(self, tmp_path, mock_global_bees_dir):
        """Query is found and deleted whether registered at global or repo scope."""
        # Register one query at global scope and one at repo scope
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}},
            queries={"repo_q": [["type=t1"]]},
        )
        write_global_queries(mock_global_bees_dir, {"global_q": [["type=bee"]]})

        # Delete the repo-scoped query (no scope arg needed)
        result_repo = _delete_named_query("repo_q", resolved_root=tmp_path)
        assert result_repo["status"] == RESULT_STATUS_SUCCESS
        assert result_repo["query_name"] == "repo_q"

        # Delete the global query (no scope arg needed)
        result_global = _delete_named_query("global_q", resolved_root=tmp_path)
        assert result_global["status"] == RESULT_STATUS_SUCCESS
        assert result_global["query_name"] == "global_q"

        from src.config import load_global_config

        gc = load_global_config()
        assert "queries" not in gc
        assert "queries" not in gc["scopes"][str(tmp_path)]

    def test_does_not_delete_from_other_repo_scope(self, tmp_path, mock_global_bees_dir):
        """Query in repo_B is not deleted when _delete_named_query is called from repo_A."""
        import json

        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()

        config = {
            "schema_version": "2.0",
            "scopes": {
                str(repo_a): {"hives": {}, "child_tiers": {}},
                str(repo_b): {"hives": {}, "child_tiers": {}, "queries": {"target_q": [["type=bee"]]}},
            },
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config, indent=2))

        result = _delete_named_query("target_q", resolved_root=repo_a)
        assert result["status"] == "error"
        assert result["error_type"] == "query_not_found"

        from src.config import load_global_config

        gc = load_global_config()
        assert "target_q" in gc["scopes"][str(repo_b)]["queries"]


class TestListNamedQueryTool:
    """Tests for _list_named_queries MCP tool with config-backed storage."""

    def test_default_returns_global_and_repo(self, tmp_path, mock_global_bees_dir):
        """Default mode returns global + caller's repo queries, NOT other repo's."""
        import json

        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}},
            queries={"repo_q": [["type=t1"]]},
        )
        # Add a second repo scope with its own query
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": [["type=bee"]]}}
        config_path.write_text(json.dumps(config, indent=2))
        write_global_queries(mock_global_bees_dir, {"global_q": [["type=bee"]]})

        result = _list_named_queries(resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        names = [q["name"] for q in result["queries"]]
        assert "repo_q" in names
        assert "global_q" in names
        assert "other_q" not in names

        # Verify scope and repo_root fields
        by_name = {q["name"]: q for q in result["queries"]}
        assert by_name["repo_q"]["scope"] == "repo"
        assert by_name["repo_q"]["repo_root"] == str(tmp_path)
        assert by_name["global_q"]["scope"] == "global"
        assert by_name["global_q"]["repo_root"] is None

    def test_default_no_scope_match(self, tmp_path, mock_global_bees_dir):
        """When resolved_root matches no scope, returns only global queries (no error)."""
        import json

        # Write config with a scope that does NOT match tmp_path
        config_path = mock_global_bees_dir / "config.json"
        config = {
            "scopes": {"/some/other/repo": {"hives": {}, "child_tiers": {}, "queries": {"hidden": [["type=t1"]]}}},
            "queries": {"visible": [["type=bee"]]},
            "schema_version": "2.0",
        }
        config_path.write_text(json.dumps(config, indent=2))

        result = _list_named_queries(resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        names = [q["name"] for q in result["queries"]]
        assert "visible" in names
        assert "hidden" not in names

    def test_count_matches_len(self, tmp_path, mock_global_bees_dir):
        """count field equals len(queries) in both default and show_all modes."""
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}},
            queries={"q1": [["type=t1"]], "q2": [["type=bee"]]},
        )
        write_global_queries(mock_global_bees_dir, {"gq": [["type=bee"]]})

        default_result = _list_named_queries(resolved_root=tmp_path)
        assert default_result["count"] == len(default_result["queries"])

    def test_empty_returns_success(self, tmp_path, mock_global_bees_dir):
        """No queries defined anywhere returns success with empty list."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _list_named_queries(resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["queries"] == []
        assert result["count"] == 0


# ===========================================================================
# Smoke tests: freeform query succeeds when hive contains a corrupt ticket
# ===========================================================================


class TestFreeformQueryWithCorruptTicket:
    """Prove query runs normally on a hive that contains a corrupt sibling ticket."""

    async def test_freeform_query_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """Freeform query returns valid results on hive with a corrupt ticket sibling."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        # Write a valid ticket
        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")

        # Write a corrupt ticket (malformed YAML, missing required fields)
        from tests.helpers import write_corrupt_ticket
        write_corrupt_ticket(hive_dir, "b.crp")

        result = await _execute_freeform_query("- ['type=bee']", resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert "b.vet" in result["ticket_ids"]
