"""Tests for multi-hive query filtering functionality."""

import pytest
import tempfile
import json
from pathlib import Path

from src.mcp_query_ops import _execute_query
from src.pipeline import PipelineEvaluator
from src.config import BeesConfig, HiveConfig, save_bees_config
from src.query_storage import QueryStorage, save_query


class TestMultiHiveQueryValidation:
    """Tests for hive existence validation in execute_query."""

    async def test_execute_query_validates_hive_exists(self, monkeypatch):
        """Test that execute_query validates specified hive exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Create .git directory for repo root detection
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir(exist_ok=True)

            # Setup test environment
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            # Create config with one hive
            config_dir = Path(tmpdir) / ".bees"
            config_dir.mkdir(exist_ok=True)
            config_path = config_dir / "config.json"

            config = BeesConfig(
                hives={
                    "backend": HiveConfig(
                        path="/fake/path",
                        display_name="Backend",
                        created_at="2026-02-02T00:00:00"
                    )
                },
                allow_cross_hive_dependencies=False,
                schema_version="1.0"
            )

            # Save config
            with open(config_path, 'w') as f:
                json.dump({
                    "hives": {
                        "backend": {
                            "path": config.hives["backend"].path,
                            "display_name": config.hives["backend"].display_name,
                            "created_at": config.hives["backend"].created_at
                        }
                    },
                    "allow_cross_hive_dependencies": config.allow_cross_hive_dependencies,
                    "schema_version": config.schema_version
                }, f)

            try:
                # Register a test query
                save_query("test_query", [["type=task"]])

                # Test with nonexistent hive
                with pytest.raises(ValueError, match="Hive not found: nonexistent"):
                    await _execute_query("test_query", hive_names=["nonexistent"])

            finally:
                src.query_storage._default_storage = old_storage

    async def test_execute_query_lists_available_hives_on_error(self, monkeypatch):
        """Test that error message lists available hives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Create .git directory for repo root detection
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir(exist_ok=True)

            # Setup test environment
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            # Create config with multiple hives
            config_dir = Path(tmpdir) / ".bees"
            config_dir.mkdir(exist_ok=True)
            config_path = config_dir / "config.json"

            config = BeesConfig(
                hives={
                    "backend": HiveConfig(
                        path="/fake/path1",
                        display_name="Backend",
                        created_at="2026-02-02T00:00:00"
                    ),
                    "frontend": HiveConfig(
                        path="/fake/path2",
                        display_name="Frontend",
                        created_at="2026-02-02T00:00:00"
                    )
                },
                allow_cross_hive_dependencies=False,
                schema_version="1.0"
            )

            # Save config
            with open(config_path, 'w') as f:
                json.dump({
                    "hives": {
                        "backend": {
                            "path": config.hives["backend"].path,
                            "display_name": config.hives["backend"].display_name,
                            "created_at": config.hives["backend"].created_at
                        },
                        "frontend": {
                            "path": config.hives["frontend"].path,
                            "display_name": config.hives["frontend"].display_name,
                            "created_at": config.hives["frontend"].created_at
                        }
                    },
                    "allow_cross_hive_dependencies": config.allow_cross_hive_dependencies,
                    "schema_version": config.schema_version
                }, f)

            try:
                # Register a test query
                save_query("test_query", [["type=task"]])

                # Test with nonexistent hive - should list available hives
                with pytest.raises(ValueError, match="Available hives: backend, frontend"):
                    await _execute_query("test_query", hive_names=["nonexistent"])

            finally:
                src.query_storage._default_storage = old_storage

    async def test_execute_query_error_when_no_config(self, monkeypatch):
        """Test error handling when no hive config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)

            # Create .git directory for repo root detection
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir(exist_ok=True)

            # Setup test environment
            import src.query_storage
            old_storage = src.query_storage._default_storage
            src.query_storage._default_storage = QueryStorage(
                str(Path(tmpdir) / "queries.yaml")
            )

            try:
                # Register a test query
                save_query("test_query", [["type=task"]])

                # Test with hive_names when no config exists
                with pytest.raises(ValueError, match="Available hives: none"):
                    await _execute_query("test_query", hive_names=["backend"])

            finally:
                src.query_storage._default_storage = old_storage


class TestPipelineHiveFiltering:
    """Tests for hive filtering in PipelineEvaluator."""

    def test_pipeline_filters_by_single_hive(self, isolated_bees_env):
        """Test that pipeline filters to only tickets from specified hive."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config()

        # Create tickets with different hive prefixes
        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
---
Backend epic description
""")

        (frontend_dir / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
title: Frontend Epic
type: epic
status: open
labels: []
---
Frontend epic description
""")

        # Note: Legacy tickets without hive prefix would go in a legacy hive
        # For this test we just test filtering between two hives

        # Create pipeline and filter by backend hive
        evaluator = PipelineEvaluator()
        stages = [["type=epic"]]

        results = evaluator.execute_query(stages, hive_names=["backend"])

        # Should only include backend ticket
        assert results == {"backend.bees-abc"}

    def test_pipeline_filters_by_multiple_hives(self, isolated_bees_env):
        """Test that pipeline filters to tickets from multiple specified hives."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        database_dir = isolated_bees_env.create_hive("database", "Database")
        isolated_bees_env.write_config()

        # Create tickets with different hive prefixes
        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
---
Backend epic description
""")

        (frontend_dir / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
title: Frontend Epic
type: epic
status: open
labels: []
---
Frontend epic description
""")

        (database_dir / "database.bees-def.md").write_text("""---
id: database.bees-def
bees_version: '1.1'
title: Database Epic
type: epic
status: open
labels: []
---
Database epic description
""")

        # Create pipeline and filter by backend and frontend hives
        evaluator = PipelineEvaluator()
        stages = [["type=epic"]]

        results = evaluator.execute_query(stages, hive_names=["backend", "frontend"])

        # Should include backend and frontend, but not database
        assert results == {"backend.bees-abc", "frontend.bees-xyz"}

    def test_pipeline_default_includes_all_hives(self, isolated_bees_env):
        """Test that omitting hive_names includes all tickets."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        legacy_dir = isolated_bees_env.create_hive("legacy", "Legacy")
        isolated_bees_env.write_config()

        # Create tickets with different hive prefixes
        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
---
Backend epic description
""")

        (frontend_dir / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
title: Frontend Epic
type: epic
status: open
labels: []
---
Frontend epic description
""")

        (legacy_dir / "legacy.bees-123.md").write_text("""---
id: legacy.bees-123
bees_version: '1.1'
title: Legacy Epic
type: epic
status: open
labels: []
---
Legacy epic without hive prefix
""")

        # Create pipeline without hive filter
        evaluator = PipelineEvaluator()
        stages = [["type=epic"]]

        results = evaluator.execute_query(stages)

        # Should include all tickets
        assert results == {"backend.bees-abc", "frontend.bees-xyz", "legacy.bees-123"}

    def test_pipeline_excludes_legacy_tickets_when_filtering(self, isolated_bees_env):
        """Test that legacy tickets (no hive prefix) are excluded when filtering."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        legacy_dir = isolated_bees_env.create_hive("legacy", "Legacy")
        isolated_bees_env.write_config()

        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
---
Backend epic description
""")

        (legacy_dir / "legacy.bees-123.md").write_text("""---
id: legacy.bees-123
bees_version: '1.1'
title: Legacy Epic
type: epic
status: open
labels: []
---
Legacy epic in legacy hive
""")

        # Filter by backend hive
        evaluator = PipelineEvaluator()
        stages = [["type=epic"]]

        results = evaluator.execute_query(stages, hive_names=["backend"])

        # Legacy ticket should be excluded
        assert "legacy.bees-123" not in results
        assert results == {"backend.bees-abc"}

    def test_pipeline_empty_hive_list(self, isolated_bees_env):
        """Test that empty hive list filters out all hive-prefixed tickets."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        legacy_dir = isolated_bees_env.create_hive("legacy", "Legacy")
        isolated_bees_env.write_config()

        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
---
Backend epic description
""")

        (legacy_dir / "legacy.bees-123.md").write_text("""---
id: legacy.bees-123
bees_version: '1.1'
title: Legacy Epic
type: epic
status: open
labels: []
---
Legacy epic
""")

        # Filter with empty hive list
        evaluator = PipelineEvaluator()
        stages = [["type=epic"]]

        results = evaluator.execute_query(stages, hive_names=[])

        # Should return empty set since no tickets match empty list
        assert results == set()

    def test_pipeline_hive_filter_with_search_stages(self, isolated_bees_env):
        """Test that hive filtering works correctly with search stages."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config()

        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Task
type: task
status: open
labels: [priority]
---
Backend task description
""")

        (backend_dir / "backend.bees-def.md").write_text("""---
id: backend.bees-def
bees_version: '1.1'
title: Another Backend Task
type: task
status: closed
labels: []
---
Another backend task
""")

        (frontend_dir / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
title: Frontend Task
type: task
status: open
labels: [priority]
---
Frontend task description
""")

        # Filter by backend hive and open status
        evaluator = PipelineEvaluator()
        stages = [["type=task"], ["label~priority"]]

        results = evaluator.execute_query(stages, hive_names=["backend"])

        # Should only include backend.bees-abc (backend + priority label)
        assert results == {"backend.bees-abc"}

    def test_pipeline_hive_filter_with_graph_stages(self, isolated_bees_env):
        """Test that hive filtering works correctly with graph stages."""
        # Create hives with proper config
        backend_dir = isolated_bees_env.create_hive("backend", "Backend")
        frontend_dir = isolated_bees_env.create_hive("frontend", "Frontend")
        isolated_bees_env.write_config()

        (backend_dir / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
bees_version: '1.1'
title: Backend Epic
type: epic
status: open
labels: []
children: [backend.bees-def]
---
Backend epic description
""")

        (backend_dir / "backend.bees-def.md").write_text("""---
id: backend.bees-def
bees_version: '1.1'
title: Backend Task
type: task
status: open
labels: []
parent: backend.bees-abc
---
Backend task description
""")

        (frontend_dir / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
bees_version: '1.1'
title: Frontend Epic
type: epic
status: open
labels: []
children: [frontend.bees-123]
---
Frontend epic description
""")

        (frontend_dir / "frontend.bees-123.md").write_text("""---
id: frontend.bees-123
bees_version: '1.1'
title: Frontend Task
type: task
status: open
labels: []
parent: frontend.bees-xyz
---
Frontend task description
""")

        # Filter by backend hive and traverse to children
        evaluator = PipelineEvaluator()
        stages = [["type=epic"], ["children"]]

        results = evaluator.execute_query(stages, hive_names=["backend"])

        # Should only include backend.bees-def (child of backend epic)
        assert results == {"backend.bees-def"}
