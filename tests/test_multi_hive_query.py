"""
Unit tests for multi-hive query filtering via hive= and hive~ pipeline terms.

PURPOSE:
Tests hive-based filtering using hive= (exact match) and hive~ (regex)
search terms in query pipelines, which replaced the old hive_names parameter.

SCOPE - Tests that belong here:
- hive= and hive~ as pipeline search terms for hive filtering
- Cross-hive queries (no hive term = all hives)
- Single-hive queries (hive=backend)
- Multi-hive queries via regex (hive~backend|frontend)
- hive= in named queries via _execute_named_query
- Result filtering by hive membership

SCOPE - Tests that DON'T belong here:
- Pipeline execution logic -> test_pipeline.py
- Search/graph execution -> test_search_executor.py, test_graph_executor.py
- Query parsing -> test_query_parser.py
- Hive management -> test_colonize_hive.py, test_config.py

RELATED FILES:
- test_pipeline.py: Pipeline that applies hive filtering
- test_query_tools.py: MCP tools for query execution
- test_config.py: Hive configuration
"""



from src.mcp_query_ops import _execute_named_query
from src.pipeline import PipelineEvaluator
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import (
    TICKET_ID_INDEX_BEE_BACKEND1 as TICKET_ID_BACKEND_ABC,
    TICKET_ID_INDEX_TASK_TEST as TICKET_ID_BACKEND_DEF,
    TICKET_ID_INDEX_BEE_DEFAULT1 as TICKET_ID_DATABASE_DEF,
    TICKET_ID_INDEX_TASK_FRONTEND as TICKET_ID_FRONTEND_123,
    TICKET_ID_INDEX_BEE_FRONTEND as TICKET_ID_FRONTEND_XYZ,
    TICKET_ID_LEGACY_BEE as TICKET_ID_LEGACY_123,
)


class TestPipelineHiveFiltering:
    """Tests for hive filtering via hive= and hive~ pipeline terms."""

    def test_pipeline_filters_by_single_hive(self, isolated_bees_env):
        """Regression: hive=backend in query filters results to backend hive without hive_names."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config()

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Epic", body="Frontend bee description")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive=backend", "type=bee"]])
        assert results == {TICKET_ID_BACKEND_ABC}

    def test_pipeline_filters_by_multiple_hives(self, isolated_bees_env):
        """hive~ regex with alternation filters to multiple hives."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        database_dir = isolated_bees_env.create_hive("database", "Database")
        isolated_bees_env.write_config()

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Epic", body="Frontend bee description")
        write_ticket_file(database_dir, TICKET_ID_DATABASE_DEF, title="Database Epic", body="Database bee description")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive~backend|frontend", "type=bee"]])
        assert results == {TICKET_ID_BACKEND_ABC, TICKET_ID_FRONTEND_XYZ}

    def test_pipeline_default_includes_all_hives(self, isolated_bees_env):
        """No hive= term returns tickets from all hives."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        legacy_dir = isolated_bees_env.create_hive("legacy", "Legacy")
        isolated_bees_env.write_config()

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Epic", body="Frontend bee description")
        write_ticket_file(legacy_dir, TICKET_ID_LEGACY_123, title="Legacy Epic", body="Legacy bee without hive prefix")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["type=bee"]])
        assert results == {TICKET_ID_BACKEND_ABC, TICKET_ID_FRONTEND_XYZ, TICKET_ID_LEGACY_123}

    def test_pipeline_excludes_legacy_tickets_when_filtering(self, isolated_bees_env):
        """hive=backend excludes tickets from other hives."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        legacy_dir = isolated_bees_env.create_hive("legacy", "Legacy")
        isolated_bees_env.write_config()

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")
        write_ticket_file(legacy_dir, TICKET_ID_LEGACY_123, title="Legacy Epic", body="Legacy bee in legacy hive")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive=backend", "type=bee"]])
        assert results == {TICKET_ID_BACKEND_ABC}

    def test_pipeline_hive_filter_with_search_stages(self, isolated_bees_env):
        """hive= works correctly in multi-stage pipelines with search terms."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config(child_tiers={"t1": ("Task", "Tasks")})

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Task", type="t1",
                          tags=["priority"], body="Backend task description")
        write_ticket_file(backend_dir, TICKET_ID_BACKEND_DEF, title="Another Backend Task", type="t1",
                          status="closed", body="Another backend task")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Task", type="t1",
                          tags=["priority"], body="Frontend task description")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive=backend", "type=t1"], ["tag~priority"]])
        assert results == {TICKET_ID_BACKEND_ABC}

    def test_pipeline_hive_filter_with_graph_stages(self, isolated_bees_env):
        """hive= in stage 1 limits initial results before graph traversal."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config(child_tiers={"t1": ("Task", "Tasks")})

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic",
                          children=[TICKET_ID_BACKEND_DEF], body="Backend bee description")
        write_ticket_file(backend_dir, TICKET_ID_BACKEND_DEF, title="Backend Task", type="t1",
                          parent=TICKET_ID_BACKEND_ABC, body="Backend task description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Epic",
                          children=[TICKET_ID_FRONTEND_123], body="Frontend bee description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_123, title="Frontend Task", type="t1",
                          parent=TICKET_ID_FRONTEND_XYZ, body="Frontend task description")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive=backend", "type=bee"], ["children"]])
        assert results == {TICKET_ID_BACKEND_DEF}

    def test_nonexistent_hive_returns_empty(self, isolated_bees_env):
        """hive= with nonexistent hive name returns empty results (no error)."""
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        isolated_bees_env.write_config()

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")

        evaluator = PipelineEvaluator()
        results = evaluator.execute_query([["hive=nonexistent", "type=bee"]])
        assert results == set()

    async def test_named_query_with_hive_term(self, isolated_bees_env):
        """hive= in a named query YAML filters correctly at execution time."""
        env = isolated_bees_env
        backend_dir = env.create_hive("backend", "Backend")
        frontend_dir = env.create_hive("frontend", "Frontend")
        write_scoped_config(
            env.global_bees_dir, env.base_path, {"hives": env.hives, "child_tiers": {}},
            queries={"backend_bees": [["hive=backend", "type=bee"]]},
        )

        write_ticket_file(backend_dir, TICKET_ID_BACKEND_ABC, title="Backend Epic", body="Backend bee description")
        write_ticket_file(frontend_dir, TICKET_ID_FRONTEND_XYZ, title="Frontend Epic", body="Frontend bee description")

        result = await _execute_named_query("backend_bees", resolved_root=env.base_path)
        assert result["status"] == "success"
        assert TICKET_ID_BACKEND_ABC in result["ticket_ids"]
        assert TICKET_ID_FRONTEND_XYZ not in result["ticket_ids"]
