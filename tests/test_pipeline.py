"""Unit tests for PipelineEvaluator class."""

import json
import pytest
import tempfile
import yaml
from pathlib import Path
from src.pipeline import PipelineEvaluator


@pytest.fixture
def temp_tickets_dir(tmp_path, monkeypatch):
    """Create temporary tickets directory with test tickets in markdown format (flat storage)."""
    from src.repo_context import repo_root_context
    
    # Change to tmp_path so autouse fixture sets context correctly
    monkeypatch.chdir(tmp_path)
    
    # Create hive directory
    hive_dir = tmp_path / "test_hive"
    hive_dir.mkdir()

    # Create .bees config directory
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir()
    
    # Create config file with hive
    config_data = {
        "hives": {
            "test_hive": {
                "path": str(hive_dir),
                "display_name": "Test Hive"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    config_file = bees_dir / "config.json"
    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    # Mock get_config_path to return our test config
    import src.config
    monkeypatch.setattr(src.config, 'get_config_path', lambda repo_root=None: config_file)
    
    # Clear config cache
    if hasattr(src.config, '_bees_config_cache'):
        src.config._bees_config_cache = None

    # Create test tickets in hive root (flat storage) with bees_version field
    test_tickets = {
        "bees-ep1.md": {
            "id": "bees-ep1",
            "title": "Build Auth System",
            "type": "epic",
            "status": "open",
            "labels": ["backend", "security", "beta"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "bees_version": "1.1"
        },
        "bees-ep2.md": {
            "id": "bees-ep2",
            "title": "Frontend Dashboard",
            "type": "epic",
            "status": "closed",
            "labels": ["frontend", "ui"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": ["bees-ep1"],
            "bees_version": "1.1"
        },
        "bees-tk1.md": {
            "id": "bees-tk1",
            "title": "Implement OAuth Login",
            "type": "task",
            "status": "open",
            "labels": ["backend", "api"],
            "parent": "bees-ep1",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "bees_version": "1.1"
        },
        "bees-tk2.md": {
            "id": "bees-tk2",
            "title": "Build User Profile API",
            "type": "task",
            "status": "open",
            "labels": ["backend", "api", "beta"],
            "parent": "bees-ep1",
            "children": [],
            "up_dependencies": ["bees-tk1"],
            "down_dependencies": [],
            "bees_version": "1.1"
        },
        "bees-st1.md": {
            "id": "bees-st1",
            "title": "Write OAuth tests",
            "type": "chore",
            "status": "open",
            "labels": ["testing", "preview"],
            "parent": "bees-tk1",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "bees_version": "1.1"
        },
    }

    for filename, frontmatter in test_tickets.items():
        filepath = hive_dir / filename
        content = f"---\n{yaml.dump(frontmatter)}---\n\n# {frontmatter['title']}\n\nTest ticket content.\n"
        with open(filepath, 'w') as f:
            f.write(content)

    yield tmp_path


@pytest.fixture
def pipeline(temp_tickets_dir):
    """Create PipelineEvaluator with test data.
    
    Note: Relies on set_repo_root_context autouse fixture to provide context.
    """
    return PipelineEvaluator(tickets_dir=str(temp_tickets_dir))


class TestPipelineEvaluatorInit:
    """Test PipelineEvaluator initialization and ticket loading."""

    def test_loads_tickets_into_memory(self, pipeline):
        """Test that all tickets are loaded into memory on init."""
        assert len(pipeline.tickets) == 5
        assert 'bees-ep1' in pipeline.tickets
        assert 'bees-tk1' in pipeline.tickets
        assert 'bees-tk2' in pipeline.tickets
        assert 'bees-st1' in pipeline.tickets
        assert 'bees-ep2' in pipeline.tickets

    def test_normalizes_ticket_structure(self, pipeline):
        """Test that tickets are normalized for executor consumption."""
        ticket = pipeline.tickets['bees-tk1']

        # Check normalized fields exist
        assert 'id' in ticket
        assert 'title' in ticket
        assert 'issue_type' in ticket
        assert 'labels' in ticket
        assert 'parent' in ticket
        assert 'children' in ticket
        assert 'up_dependencies' in ticket
        assert 'down_dependencies' in ticket

    def test_parses_parent_relationship(self, pipeline):
        """Test that parent relationships are parsed correctly."""
        tk1 = pipeline.tickets['bees-tk1']
        assert tk1['parent'] == 'bees-ep1'

    def test_parses_up_dependencies(self, pipeline):
        """Test that blocked_by dependencies are parsed as up_dependencies."""
        tk2 = pipeline.tickets['bees-tk2']
        assert 'bees-tk1' in tk2['up_dependencies']

    def test_parses_down_dependencies(self, pipeline):
        """Test that blocks dependencies are parsed as down_dependencies."""
        ep2 = pipeline.tickets['bees-ep2']
        assert 'bees-ep1' in ep2['down_dependencies']




class TestStageTypeDetection:
    """Test stage type detection and routing logic."""

    def test_detects_search_stage_with_type(self, pipeline):
        """Test detection of search stage with type= term."""
        stage = ['type=epic']
        assert pipeline.get_stage_type(stage) == 'search'

    def test_detects_search_stage_with_id(self, pipeline):
        """Test detection of search stage with id= term."""
        stage = ['id=bees-ep1']
        assert pipeline.get_stage_type(stage) == 'search'

    def test_detects_search_stage_with_title_regex(self, pipeline):
        """Test detection of search stage with title~ term."""
        stage = ['title~Auth']
        assert pipeline.get_stage_type(stage) == 'search'

    def test_detects_search_stage_with_label_regex(self, pipeline):
        """Test detection of search stage with label~ term."""
        stage = ['label~beta']
        assert pipeline.get_stage_type(stage) == 'search'

    def test_detects_graph_stage_with_parent(self, pipeline):
        """Test detection of graph stage with parent term."""
        stage = ['parent']
        assert pipeline.get_stage_type(stage) == 'graph'

    def test_detects_graph_stage_with_children(self, pipeline):
        """Test detection of graph stage with children term."""
        stage = ['children']
        assert pipeline.get_stage_type(stage) == 'graph'

    def test_detects_graph_stage_with_dependencies(self, pipeline):
        """Test detection of graph stage with dependency terms."""
        stage = ['up_dependencies']
        assert pipeline.get_stage_type(stage) == 'graph'

        stage = ['down_dependencies']
        assert pipeline.get_stage_type(stage) == 'graph'

    def test_raises_error_on_mixed_stage(self, pipeline):
        """Test that mixed search/graph stages raise error."""
        mixed_stage = ['type=epic', 'parent']

        with pytest.raises(ValueError) as exc_info:
            pipeline.get_stage_type(mixed_stage)

        assert "mixed search and graph terms" in str(exc_info.value)

    def test_raises_error_on_empty_stage(self, pipeline):
        """Test that empty stage raises error."""
        with pytest.raises(ValueError) as exc_info:
            pipeline.get_stage_type([])

        assert "empty stage" in str(exc_info.value)

    def test_raises_error_on_unknown_terms(self, pipeline):
        """Test that unrecognized terms raise error."""
        with pytest.raises(ValueError) as exc_info:
            pipeline.get_stage_type(['unknown_term'])

        assert "no recognized search or graph terms" in str(exc_info.value)


class TestQueryExecution:
    """Test sequential query execution with result passing."""

    def test_single_search_stage(self, pipeline):
        """Test execution of single search stage."""
        stages = [['type=epic']]
        results = pipeline.execute_query(stages)

        assert len(results) == 2
        assert 'bees-ep1' in results
        assert 'bees-ep2' in results

    def test_multiple_search_terms_anded(self, pipeline):
        """Test that multiple search terms in stage are ANDed."""
        stages = [['type=epic', 'label~beta']]
        results = pipeline.execute_query(stages)

        # Only bees-ep1 is epic AND has beta label
        assert len(results) == 1
        assert 'bees-ep1' in results

    def test_sequential_stage_execution(self, pipeline):
        """Test that stages execute sequentially with result passing."""
        # Stage 1: Get all epics (bees-ep1, bees-ep2)
        # Stage 2: Get children of those epics
        stages = [
            ['type=epic'],
            ['children']
        ]
        results = pipeline.execute_query(stages)

        # Should return children of epics: bees-tk1, bees-tk2, bees-st1
        assert 'bees-tk1' in results
        assert 'bees-tk2' in results

    def test_deduplication_between_stages(self, pipeline):
        """Test that results are deduplicated between stages."""
        # Get tasks, then get their parents (epics)
        stages = [
            ['type=task'],
            ['parent']
        ]
        results = pipeline.execute_query(stages)

        # Both tasks have same parent, should be deduplicated
        assert len(results) == 1
        assert 'bees-ep1' in results

    def test_short_circuit_on_empty_results(self, pipeline):
        """Test that pipeline short-circuits when stage returns empty set."""
        # Stage 1: Get closed items (only bees-ep2)
        # Stage 2: Get children (bees-ep2 has no children, returns empty)
        # Stage 3: Should not execute
        stages = [
            ['type=epic', 'label~frontend'],  # Gets bees-ep2
            ['children'],  # bees-ep2 has no children -> empty
            ['parent']  # Should not execute
        ]
        results = pipeline.execute_query(stages)

        assert len(results) == 0

    def test_graph_stage_with_multiple_terms(self, pipeline):
        """Test graph stage with multiple terms ANDed together."""
        # Get tasks, traverse to parent, then to children of that parent
        stages = [
            ['type=task'],
            ['parent'],
            ['children']
        ]
        results = pipeline.execute_query(stages)

        # Should get children of parent epic
        assert 'bees-tk1' in results
        assert 'bees-tk2' in results

    def test_single_parent_filter(self, pipeline):
        """Test execution of single parent= search filter."""
        stages = [['parent=bees-ep1']]
        results = pipeline.execute_query(stages)

        # Should return both tasks with parent bees-ep1
        assert len(results) == 2
        assert 'bees-tk1' in results
        assert 'bees-tk2' in results

    def test_parent_filter_combined_with_type(self, pipeline):
        """Test parent= filter combined with type= filter."""
        stages = [['parent=bees-ep1', 'type=task']]
        results = pipeline.execute_query(stages)

        # Should return both tasks with parent bees-ep1 and type=task
        assert len(results) == 2
        assert 'bees-tk1' in results
        assert 'bees-tk2' in results

    def test_parent_filter_combined_with_label(self, pipeline):
        """Test parent= filter combined with label~ filter."""
        stages = [['parent=bees-ep1', 'label~api']]
        results = pipeline.execute_query(stages)

        # Both bees-tk1 and bees-tk2 have parent=bees-ep1 and api label
        assert len(results) == 2
        assert 'bees-tk1' in results
        assert 'bees-tk2' in results

    def test_parent_filter_in_multistage_pipeline(self, pipeline):
        """Test parent= filter in multi-stage query with result passing."""
        # Stage 1: Get all children of bees-ep1 using parent= filter
        # Stage 2: Traverse back to their parent
        stages = [
            ['parent=bees-ep1'],
            ['parent']
        ]
        results = pipeline.execute_query(stages)

        # Stage 1 gets bees-tk1 and bees-tk2, stage 2 gets their parent
        assert len(results) == 1
        assert 'bees-ep1' in results


class TestBatchExecution:
    """Test batch query execution with cached ticket data."""

    def test_executes_multiple_queries(self, pipeline):
        """Test that batch execution runs multiple queries."""
        queries = [
            [['type=epic']],
            [['type=task']],
            [['label~beta']],
        ]

        results = pipeline.execute_batch(queries)

        assert len(results) == 3
        assert len(results[0]) == 2  # 2 epics
        assert len(results[1]) == 2  # 2 tasks
        assert len(results[2]) == 2  # 2 tickets with beta label

    def test_reuses_in_memory_data(self, pipeline):
        """Test that batch execution reuses cached data."""
        # Verify tickets are loaded
        initial_ticket_count = len(pipeline.tickets)

        queries = [
            [['type=epic']],
            [['type=task']],
        ]

        pipeline.execute_batch(queries)

        # Ticket count should remain the same (no reload)
        assert len(pipeline.tickets) == initial_ticket_count

    def test_batch_with_complex_queries(self, pipeline):
        """Test batch execution with multi-stage queries."""
        queries = [
            # Query 1: Epics with beta label and their children
            [['type=epic', 'label~beta'], ['children']],
            # Query 2: Tasks and their parents
            [['type=task'], ['parent']],
        ]

        results = pipeline.execute_batch(queries)

        assert len(results) == 2
        # Query 1: children of bees-ep1
        assert 'bees-tk1' in results[0]
        assert 'bees-tk2' in results[0]
        # Query 2: parent of tasks
        assert 'bees-ep1' in results[1]


class TestMarkdownTicketLoading:
    """Test markdown ticket loading with YAML frontmatter."""



    def test_normalizes_type_to_issue_type(self, pipeline):
        """Test that 'type' field from YAML is mapped to 'issue_type'."""
        ticket = pipeline.tickets['bees-tk1']
        assert ticket['issue_type'] == 'task'

    def test_extracts_relationship_fields_directly(self, pipeline):
        """Test that relationship fields are extracted directly from YAML."""
        tk2 = pipeline.tickets['bees-tk2']
        assert tk2['parent'] == 'bees-ep1'
        assert 'bees-tk1' in tk2['up_dependencies']




class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_query_stages(self, pipeline):
        """Test execution with empty stages list."""
        # Should return all tickets when no stages provided
        results = pipeline.execute_query([])
        assert len(results) == len(pipeline.tickets)

    def test_query_with_no_matching_tickets(self, pipeline):
        """Test query that matches no tickets."""
        stages = [['type=epic', 'label~nonexistent']]
        results = pipeline.execute_query(stages)

        assert len(results) == 0

    def test_graph_traversal_with_missing_relationships(self, pipeline):
        """Test graph traversal on tickets with no relationships."""
        # Get chore without children, try to traverse children
        stages = [
            ['id=bees-st1'],
            ['children']
        ]
        results = pipeline.execute_query(stages)

        # Should return empty set
        assert len(results) == 0





