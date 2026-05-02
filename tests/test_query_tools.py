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

from src.config import GLOBAL_SCHEMA_VERSION, check_query_name_conflict, resolve_named_query
from src.mcp_query_ops import (
    _add_named_query,
    _delete_named_query,
    _execute_freeform_query,
    _execute_named_query,
    _list_named_queries,
)
from tests.conftest import build_query, write_global_queries, write_scoped_config
from tests.test_constants import (
    HIVE_BACKEND,
    RESULT_STATUS_SUCCESS,
)


class TestAddNamedQueryTool:
    """Tests for add_named_query MCP tool with config-backed storage."""

    def test_global_scope_succeeds(self, tmp_path, mock_global_bees_dir):
        """scope='global' succeeds; query readable from global config."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("my_query", "stages:\n- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "my_query"

        from src.config import load_global_config

        gc = load_global_config()
        assert "my_query" in gc.get("queries", {})

    def test_repo_scope_succeeds(self, tmp_path, mock_global_bees_dir):
        """scope='repo' succeeds when repo root is registered."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("repo_q", "stages:\n- [type=t1]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        assert "repo_q" in gc["scopes"][str(tmp_path)].get("queries", {})

    def test_repo_scope_not_found(self, tmp_path, mock_global_bees_dir):
        """scope='repo' returns scope_not_found for unregistered repo root."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("q", "stages:\n- [type=t1]", scope="repo", resolved_root=Path("/unregistered/repo"))
        assert result["status"] == "error"
        assert result["error_type"] == "scope_not_found"

    def test_invalid_scope(self, tmp_path, mock_global_bees_dir):
        """Returns invalid_scope for unrecognized scope value."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("q", "stages:\n- [type=t1]", scope="invalid", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_scope"

    def test_global_name_conflict(self, tmp_path, mock_global_bees_dir):
        """Rejects name at global level with query_name_conflict."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        write_global_queries(mock_global_bees_dir, {"q1": build_query([["type=bee"]])})

        result = _add_named_query("q1", "stages:\n- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_repo_name_conflict(self, tmp_path, mock_global_bees_dir):
        """Rejects name at caller's repo scope with query_name_conflict."""
        write_scoped_config(
            mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}}, queries={"q1": build_query([["type=t1"]])}
        )

        result = _add_named_query("q1", "stages:\n- [type=bee]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_repo_succeeds_same_name_different_repo(self, tmp_path, mock_global_bees_dir):
        """scope='repo' succeeds when same name exists only in different repo's scope."""
        import json

        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": build_query([["type=t1"]])}}
        config_path.write_text(json.dumps(config, indent=2))

        result = _add_named_query("q1", "stages:\n- [type=bee]", scope="repo", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

    def test_global_conflict_any_repo(self, tmp_path, mock_global_bees_dir):
        """scope='global' returns query_name_conflict when name exists in any repo scope."""
        import json

        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": build_query([["type=t1"]])}}
        config_path.write_text(json.dumps(config, indent=2))

        result = _add_named_query("q1", "stages:\n- [type=bee]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "query_name_conflict"

    def test_empty_name_rejected(self, tmp_path, mock_global_bees_dir):
        """Empty name returns error dict."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query("", "stages:\n- [type=t1]", scope="global", resolved_root=tmp_path)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_query"
        assert "cannot be empty" in result["message"]

    def test_report_field_round_trip(self, tmp_path, mock_global_bees_dir):
        """Query with report field is stored and retrievable with stages and report intact."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})

        result = _add_named_query(
            "q_with_report",
            "stages:\n- [type=t1]\nreport:\n- title\n- ticket_status",
            scope="global",
            resolved_root=tmp_path,
        )
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        stored = gc["queries"]["q_with_report"]
        assert stored["stages"] == [["type=t1"]]
        assert stored["report"] == ["title", "ticket_status"]


class TestExecuteNamedQueryTool:
    """Tests for execute_named_query MCP tool with config-backed resolution."""

    async def test_resolves_from_repo_scope(self, isolated_bees_env):
        """Query in caller's repo scope resolves and executes successfully."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(
            env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}},
            queries={"my_query": build_query([["type=t1"]])},
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
        write_global_queries(env.global_bees_dir, {"global_q": build_query([["type=bee"]])})

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
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": build_query([["type=t1"]])}}
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
            queries={"repo_q": build_query([["type=t1"]])},
        )
        write_global_queries(env.global_bees_dir, {"global_q": build_query([["type=bee"]])})

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
        _add_named_query("repo_q", "stages:\n- [type=bee]", scope="repo", resolved_root=env.base_path)

        result = await _execute_named_query("repo_q", resolved_root=env.base_path)
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["query_name"] == "repo_q"

    async def test_repo_scope_query_out_of_scope_when_root_is_none(self, isolated_bees_env):
        """Negative: repo-scoped query returns query_out_of_scope when resolved_root=None."""
        env = isolated_bees_env
        env.create_hive("test_hive", "Test Hive")
        write_scoped_config(env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}})
        _add_named_query("repo_q", "stages:\n- [type=bee]", scope="repo", resolved_root=env.base_path)

        result = await _execute_named_query("repo_q", resolved_root=None)
        assert result["status"] == "error"
        assert result["error_type"] == "query_out_of_scope"


class TestExecuteFreeformQuery:
    """Tests for execute_freeform_query MCP tool."""

    async def test_execute_freeform_query_basic(self, isolated_bees_env):
        """Test executing a valid freeform query without persisting."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("stages:\n- [type=t1]")
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

        result = await _execute_freeform_query("stages:\n- [type=t1, hive=backend]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0

    async def test_execute_freeform_query_multi_stage(self, isolated_bees_env):
        """Test executing multi-stage freeform query."""
        isolated_bees_env.create_hive("test_hive", "Test Hive")
        isolated_bees_env.write_config()

        result = await _execute_freeform_query("stages:\n- [type=bee]\n- [children]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0

    @pytest.mark.parametrize(
        "query_yaml",
        [
            "stages:\n- [parent=some-bee-id]",
            "stages:\n- [type=t1, parent=bee-123]",
            "stages:\n- [parent=bee-123, tag~beta]",
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

        result = await _execute_freeform_query("stages:\n- [parent=bee-123]\n- [parent]")
        assert result["status"] == RESULT_STATUS_SUCCESS
        assert result["result_count"] == 0


class TestResolveNamedQuery:
    """Tests for resolve_named_query config resolution logic."""

    def test_returns_from_repo_scope(self, tmp_path, mock_global_bees_dir):
        """Query found in caller's repo scope returns with scope='repo'."""
        scope_data = {"hives": {}, "child_tiers": {}}
        stages = [["type=t1"]]
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"my_query": build_query(stages)})

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("my_query", tmp_path, gc)
        assert result == {"status": "found", "stages": stages, "scope": "repo"}

    def test_falls_through_to_global(self, tmp_path, mock_global_bees_dir):
        """Query only in global scope returns with scope='global'."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        write_global_queries(mock_global_bees_dir, {"global_q": build_query([["type=bee"]])})

        from src.config import load_global_config

        gc = load_global_config()
        result = resolve_named_query("global_q", tmp_path, gc)
        assert result == {"status": "found", "stages": [["type=bee"]], "scope": "global"}

    def test_repo_takes_precedence(self, tmp_path, mock_global_bees_dir):
        """When both repo and global define same name, repo wins."""
        repo_stages = [["type=t1"]]
        global_stages = [["type=bee"]]
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"shared_q": build_query(repo_stages)})
        write_global_queries(mock_global_bees_dir, {"shared_q": build_query(global_stages)})

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
        config["scopes"][str(other_repo)] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": build_query([["type=t1"]])}}
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
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data, queries={"q1": build_query([["type=t1"]])})

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
        write_global_queries(mock_global_bees_dir, {"q1": build_query([["type=bee"]])})

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
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": build_query([["type=t1"]])}}
        config_path.write_text(json.dumps(config, indent=2))

        from src.config import load_global_config

        gc = load_global_config()
        result = check_query_name_conflict("q1", "repo", tmp_path, gc)
        assert result is None

    def test_global_scope_conflict_at_global(self, tmp_path, mock_global_bees_dir):
        """scope='global', name in global → conflict returned."""
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        write_global_queries(mock_global_bees_dir, {"q1": build_query([["type=bee"]])})

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
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"q1": build_query([["type=t1"]])}}
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
        write_global_queries(mock_global_bees_dir, {"doomed": build_query([["type=bee"]]), "keeper": build_query([["type=t1"]])})

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
            queries={"doomed": build_query([["type=t1"]]), "keeper": build_query([["type=bee"]])},
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
            queries={"only_one": build_query([["type=t1"]])},
        )

        result = _delete_named_query("only_one", resolved_root=tmp_path)
        assert result["status"] == RESULT_STATUS_SUCCESS

        from src.config import load_global_config

        gc = load_global_config()
        assert "queries" not in gc["scopes"][str(tmp_path)]

    def test_empty_dict_cleanup_global(self, tmp_path, mock_global_bees_dir):
        """After deleting last global query, top-level 'queries' key is absent."""
        write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {}, "child_tiers": {}})
        write_global_queries(mock_global_bees_dir, {"only_one": build_query([["type=bee"]])})

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
            queries={"repo_q": build_query([["type=t1"]])},
        )
        write_global_queries(mock_global_bees_dir, {"global_q": build_query([["type=bee"]])})

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
            "schema_version": GLOBAL_SCHEMA_VERSION,
            "scopes": {
                str(repo_a): {"hives": {}, "child_tiers": {}},
                str(repo_b): {"hives": {}, "child_tiers": {}, "queries": {"target_q": build_query([["type=bee"]])}},
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
            queries={"repo_q": build_query([["type=t1"]])},
        )
        # Add a second repo scope with its own query
        config_path = mock_global_bees_dir / "config.json"
        config = json.loads(config_path.read_text())
        config["scopes"]["/other/repo"] = {"hives": {}, "child_tiers": {}, "queries": {"other_q": build_query([["type=bee"]])}}
        config_path.write_text(json.dumps(config, indent=2))
        write_global_queries(mock_global_bees_dir, {"global_q": build_query([["type=bee"]])})

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
            "scopes": {"/some/other/repo": {"hives": {}, "child_tiers": {}, "queries": {"hidden": build_query([["type=t1"]])}}},
            "queries": {"visible": build_query([["type=bee"]])},
            "schema_version": GLOBAL_SCHEMA_VERSION,
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
            queries={"q1": build_query([["type=t1"]]), "q2": build_query([["type=bee"]])},
        )
        write_global_queries(mock_global_bees_dir, {"gq": build_query([["type=bee"]])})

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

        result = await _execute_freeform_query("stages:\n- ['type=bee']", resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert "b.vet" in result["ticket_ids"]


# ===========================================================================
# Projection and response format tests
# ===========================================================================


class TestProjection:
    """Tests for _project_tickets field mapping, null handling, and sort order."""

    async def test_field_name_mapping_ticket_type(self, isolated_bees_env):
        """ticket_type in report maps to the internal issue_type field (from 'type' frontmatter)."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.typ", title="Type Mapping", type="bee")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- ticket_type",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        rows = {r["ticket_id"]: r for r in result["tickets"]}
        assert rows["b.typ"]["ticket_type"] == "bee"

    async def test_field_name_mapping_ticket_status(self, isolated_bees_env):
        """ticket_status in report maps to the internal status field."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.sts", title="Status Mapping", status="pupa")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- ticket_status",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        rows = {r["ticket_id"]: r for r in result["tickets"]}
        assert rows["b.sts"]["ticket_status"] == "pupa"

    async def test_ticket_id_always_present_in_each_row(self, isolated_bees_env):
        """Every projected row always includes ticket_id even when not in report list."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.tid", title="ID Always Present")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- title",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["tickets"]) >= 1
        for row in result["tickets"]:
            assert "ticket_id" in row

    async def test_null_value_for_absent_field(self, isolated_bees_env):
        """A ticket field absent in the pipeline dict is projected as None."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        # Root bee ticket has no parent → parent field is None in pipeline dict
        write_ticket_file(hive_dir, "b.nup", title="Null Parent")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- parent",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["tickets"]) >= 1
        # All returned tickets are root bees with no parent
        for row in result["tickets"]:
            assert row["parent"] is None

    async def test_results_sorted_by_ticket_id(self, isolated_bees_env):
        """Projected rows are sorted ascending by ticket_id regardless of creation order."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        # Write tickets in reverse alphabetical order
        write_ticket_file(hive_dir, "b.zzz", title="Last Ticket")
        write_ticket_file(hive_dir, "b.aaa", title="First Ticket")
        write_ticket_file(hive_dir, "b.mmm", title="Middle Ticket")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- title",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        ids = [r["ticket_id"] for r in result["tickets"]]
        assert ids == sorted(ids)
        assert ids.index("b.aaa") < ids.index("b.mmm") < ids.index("b.zzz")

    async def test_multiple_fields_projected(self, isolated_bees_env):
        """Multiple valid report fields all appear in each row."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.mfp", title="Multi Field", status="worker")

        result = await _execute_freeform_query(
            "stages:\n- ['id=b.mfp']\nreport:\n- title\n- ticket_type\n- ticket_status",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["tickets"]) == 1
        row = result["tickets"][0]
        assert row["ticket_id"] == "b.mfp"
        assert row["title"] == "Multi Field"
        assert row["ticket_type"] == "bee"
        assert row["ticket_status"] == "worker"


    async def test_hive_field_returns_hive_name(self, isolated_bees_env):
        """report: ['hive'] returns the hive's name for each ticket in the result."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("my_hive", "My Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.hv1", title="Hive Field Test")

        result = await _execute_freeform_query(
            "stages:\n- ['id=b.hv1']\nreport:\n- hive",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert len(result["tickets"]) == 1
        row = result["tickets"][0]
        assert row["ticket_id"] == "b.hv1"
        assert row["hive"] == "my_hive"


class TestResponseFormatBranching:
    """Tests for the report-vs-ticket_ids response format branching."""

    async def test_freeform_without_report_returns_ticket_ids(self, isolated_bees_env):
        """Freeform query without report returns ticket_ids list, no tickets key."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.fwr", title="Freeform Without Report")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']", resolved_root=helper.base_path
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "ticket_ids" in result
        assert "tickets" not in result
        assert "stages_executed" in result

    async def test_freeform_with_report_returns_tickets_list(self, isolated_bees_env):
        """Freeform query with report returns tickets list, no ticket_ids key."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.fwp", title="Freeform With Report")

        result = await _execute_freeform_query(
            "stages:\n- ['type=bee']\nreport:\n- title",
            resolved_root=helper.base_path,
        )

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "tickets" in result
        assert "ticket_ids" not in result
        assert "stages_executed" in result

    async def test_named_query_without_report_returns_ticket_ids(self, isolated_bees_env):
        """Named query without report returns ticket_ids list, no tickets key."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.nwr", title="Named Without Report")
        write_scoped_config(
            helper.global_bees_dir, helper.base_path,
            {"hives": helper.hives, "child_tiers": {}},
            queries={"q_no_report": build_query([["type=bee"]])},
        )

        result = await _execute_named_query("q_no_report", resolved_root=helper.base_path)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "ticket_ids" in result
        assert "tickets" not in result
        assert result["query_name"] == "q_no_report"

    async def test_named_query_with_report_returns_tickets_list(self, isolated_bees_env):
        """Named query with report returns tickets list, no ticket_ids key."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.nwp", title="Named With Report")
        write_scoped_config(
            helper.global_bees_dir, helper.base_path,
            {"hives": helper.hives, "child_tiers": {}},
            queries={"q_with_report": build_query([["type=bee"]], report=["title"])},
        )

        result = await _execute_named_query("q_with_report", resolved_root=helper.base_path)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "tickets" in result
        assert "ticket_ids" not in result
        assert result["query_name"] == "q_with_report"

    async def test_named_query_config_roundtrip_with_projection(self, isolated_bees_env):
        """Named query stored with report field executes and returns projected rows."""
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        write_ticket_file(hive_dir, "b.rtp", title="Round Trip Bee", status="finished")

        # Store query with report via _add_named_query
        _add_named_query(
            "rtrip",
            "stages:\n- ['type=bee']\nreport:\n- title\n- ticket_status",
            scope="global",
            resolved_root=helper.base_path,
        )

        result = await _execute_named_query("rtrip", resolved_root=helper.base_path)

        assert result["status"] == RESULT_STATUS_SUCCESS
        assert "tickets" in result
        rows = {r["ticket_id"]: r for r in result["tickets"]}
        assert "b.rtp" in rows
        assert rows["b.rtp"]["title"] == "Round Trip Bee"
        assert rows["b.rtp"]["ticket_status"] == "finished"
