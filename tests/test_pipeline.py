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

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_missing_tickets_dir_raises_error(self, tmp_path):
        """Test that missing tickets directory raises FileNotFoundError."""
        nonexistent_dir = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError) as exc_info:
            PipelineEvaluator(tickets_dir=str(nonexistent_dir))

        assert "Tickets directory not found" in str(exc_info.value)

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_invalid_yaml_raises_error(self, tmp_path):
        """Test that malformed YAML frontmatter raises ValueError."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Create markdown file with invalid YAML in hive root
        bad_file = tickets_dir / "bad.md"
        with open(bad_file, 'w') as f:
            f.write('---\n')
            f.write('id: bees-123\n')
            f.write('invalid: yaml: syntax: here\n')
            f.write('---\n')

        with pytest.raises(ValueError) as exc_info:
            PipelineEvaluator(tickets_dir=str(tickets_dir))

        assert "Invalid YAML" in str(exc_info.value)

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_skips_tickets_without_id(self, tmp_path):
        """Test that tickets without IDs are skipped with warning."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Ticket without ID (in hive root)
        no_id_file = tickets_dir / "no-id.md"
        with open(no_id_file, 'w') as f:
            f.write('---\ntitle: No ID ticket\ntype: task\nbees_version: "1.1"\n---\n# No ID\n')

        # Valid ticket (in hive root)
        valid_file = tickets_dir / "valid.md"
        with open(valid_file, 'w') as f:
            f.write('---\nid: bees-123\ntitle: Valid ticket\ntype: task\nbees_version: "1.1"\n---\n# Valid\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 1
        assert 'bees-123' in pipeline.tickets


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

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_loads_tickets_from_hive_root(self, tmp_path):
        """Test that tickets are loaded from hive root (flat storage)."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Create tickets in hive root (flat storage)
        for ticket_id, ticket_type in [("bees-ep1", "epic"), ("bees-tk1", "task"), ("bees-st1", "subtask")]:
            filepath = tickets_dir / f"{ticket_id}.md"
            with open(filepath, 'w') as f:
                f.write(f'---\nid: {ticket_id}\ntype: {ticket_type}\ntitle: Test\nbees_version: "1.1"\n---\n# Test\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 3
        assert 'bees-ep1' in pipeline.tickets
        assert 'bees-tk1' in pipeline.tickets
        assert 'bees-st1' in pipeline.tickets

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_skips_files_without_frontmatter(self, tmp_path):
        """Test that markdown files without YAML frontmatter are skipped."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # File without frontmatter (in hive root)
        bad_file = tickets_dir / "no-frontmatter.md"
        with open(bad_file, 'w') as f:
            f.write('# Just a regular markdown file\n\nNo YAML here.')

        # Valid file (in hive root)
        good_file = tickets_dir / "valid.md"
        with open(good_file, 'w') as f:
            f.write('---\nid: bees-123\ntype: task\ntitle: Valid\nbees_version: "1.1"\n---\n# Valid\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 1
        assert 'bees-123' in pipeline.tickets

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_skips_files_with_malformed_frontmatter(self, tmp_path):
        """Test that files with incomplete frontmatter delimiters are skipped."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # File with only opening delimiter (in hive root)
        bad_file = tickets_dir / "malformed.md"
        with open(bad_file, 'w') as f:
            f.write('---\nid: bees-bad\nNo closing delimiter')

        # Valid file (in hive root)
        good_file = tickets_dir / "valid.md"
        with open(good_file, 'w') as f:
            f.write('---\nid: bees-123\ntype: task\nbees_version: "1.1"\n---\n# Valid\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 1
        assert 'bees-123' in pipeline.tickets

    def test_normalizes_type_to_issue_type(self, pipeline):
        """Test that 'type' field from YAML is mapped to 'issue_type'."""
        ticket = pipeline.tickets['bees-tk1']
        assert ticket['issue_type'] == 'task'

    def test_extracts_relationship_fields_directly(self, pipeline):
        """Test that relationship fields are extracted directly from YAML."""
        tk2 = pipeline.tickets['bees-tk2']
        assert tk2['parent'] == 'bees-ep1'
        assert 'bees-tk1' in tk2['up_dependencies']

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_handles_empty_hive_root_gracefully(self, tmp_path):
        """Test that empty hive root directory doesn't cause errors."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Empty hive root with no tickets
        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 0


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

    @pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
    def test_handles_tickets_without_labels(self, tmp_path):
        """Test that tickets without labels field are handled gracefully."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Ticket without labels field (in hive root)
        task_file = tickets_dir / "bees-1.md"
        with open(task_file, 'w') as f:
            f.write('---\nid: bees-1\ntype: task\ntitle: Test\nbees_version: "1.1"\n---\n# Test\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        # Should handle gracefully with empty labels array
        ticket = pipeline.tickets['bees-1']
        assert ticket['labels'] == []

        # Label search should not crash
        stages = [['label~test']]
        results = pipeline.execute_query(stages)
        assert len(results) == 0


@pytest.mark.skip(reason="tickets_dir parameter is deprecated - PipelineEvaluator now loads from hive config")
class TestFlatStorageScanning:
    """Test flat storage scanning (bees_version 1.1) with hive root directory."""

    def test_loads_tickets_from_hive_root_only(self, tmp_path):
        """Test that _load_tickets() scans only hive root, not subdirectories."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Create tickets in hive root with bees_version field
        root_ticket = tickets_dir / "bees-root1.md"
        with open(root_ticket, 'w') as f:
            f.write('---\nid: bees-root1\ntype: epic\ntitle: Root Ticket\nbees_version: "1.1"\n---\n# Root\n')

        # Create subdirectory with tickets (should be ignored)
        subdir = tickets_dir / "subdir"
        subdir.mkdir()
        sub_ticket = subdir / "bees-sub1.md"
        with open(sub_ticket, 'w') as f:
            f.write('---\nid: bees-sub1\ntype: task\ntitle: Subdir Ticket\nbees_version: "1.1"\n---\n# Sub\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        # Should only load root ticket, not subdirectory ticket
        assert len(pipeline.tickets) == 1
        assert 'bees-root1' in pipeline.tickets
        assert 'bees-sub1' not in pipeline.tickets

    def test_filters_by_bees_version_field(self, tmp_path):
        """Test that files without bees_version field are skipped."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Ticket with bees_version (should be loaded)
        valid_ticket = tickets_dir / "bees-valid.md"
        with open(valid_ticket, 'w') as f:
            f.write('---\nid: bees-valid\ntype: epic\ntitle: Valid\nbees_version: "1.1"\n---\n# Valid\n')

        # Ticket without bees_version (should be skipped)
        invalid_ticket = tickets_dir / "bees-invalid.md"
        with open(invalid_ticket, 'w') as f:
            f.write('---\nid: bees-invalid\ntype: task\ntitle: No Version\n---\n# Invalid\n')

        # Regular markdown file (should be skipped)
        readme = tickets_dir / "README.md"
        with open(readme, 'w') as f:
            f.write('# Project README\n\nThis is not a ticket.')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        # Should only load ticket with bees_version field
        assert len(pipeline.tickets) == 1
        assert 'bees-valid' in pipeline.tickets
        assert 'bees-invalid' not in pipeline.tickets

    def test_excludes_eggs_subdirectory(self, tmp_path):
        """Test that /eggs subdirectory is excluded from scanning."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Ticket in root (should be loaded)
        root_ticket = tickets_dir / "bees-root.md"
        with open(root_ticket, 'w') as f:
            f.write('---\nid: bees-root\ntype: epic\ntitle: Root\nbees_version: "1.1"\n---\n# Root\n')

        # Ticket in /eggs subdirectory (should be ignored)
        eggs_dir = tickets_dir / "eggs"
        eggs_dir.mkdir()
        eggs_ticket = eggs_dir / "bees-eggs.md"
        with open(eggs_ticket, 'w') as f:
            f.write('---\nid: bees-eggs\ntype: task\ntitle: Eggs\nbees_version: "1.1"\n---\n# Eggs\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        assert len(pipeline.tickets) == 1
        assert 'bees-root' in pipeline.tickets
        assert 'bees-eggs' not in pipeline.tickets

    def test_excludes_evicted_subdirectory(self, tmp_path):
        """Test that /evicted subdirectory is excluded from scanning."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Ticket in root (should be loaded)
        root_ticket = tickets_dir / "bees-root.md"
        with open(root_ticket, 'w') as f:
            f.write('---\nid: bees-root\ntype: epic\ntitle: Root\nbees_version: "1.1"\n---\n# Root\n')

        # Ticket in /evicted subdirectory (should be ignored)
        evicted_dir = tickets_dir / "evicted"
        evicted_dir.mkdir()
        evicted_ticket = evicted_dir / "bees-evicted.md"
        with open(evicted_ticket, 'w') as f:
            f.write('---\nid: bees-evicted\ntype: task\ntitle: Evicted\nbees_version: "1.1"\n---\n# Evicted\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        assert len(pipeline.tickets) == 1
        assert 'bees-root' in pipeline.tickets
        assert 'bees-evicted' not in pipeline.tickets

    def test_handles_invalid_yaml_gracefully(self, tmp_path):
        """Test error handling for invalid YAML in ticket files."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # File with invalid YAML
        bad_yaml = tickets_dir / "bees-bad.md"
        with open(bad_yaml, 'w') as f:
            f.write('---\nid: bees-bad\ninvalid: yaml: syntax: here\n---\n# Bad\n')

        with pytest.raises(ValueError) as exc_info:
            PipelineEvaluator(tickets_dir=str(tickets_dir))

        assert "Invalid YAML" in str(exc_info.value)

    def test_queries_work_with_flat_storage(self, tmp_path):
        """Test that queries work correctly with flat storage tickets."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Create test tickets in flat storage
        tickets = {
            "bees-ep1": {"type": "epic", "labels": ["backend"]},
            "bees-tk1": {"type": "task", "parent": "bees-ep1", "labels": ["backend"]},
            "bees-tk2": {"type": "task", "parent": "bees-ep1", "labels": ["frontend"]},
        }

        for ticket_id, data in tickets.items():
            filepath = tickets_dir / f"{ticket_id}.md"
            frontmatter = {
                "id": ticket_id,
                "type": data["type"],
                "title": f"Test {ticket_id}",
                "bees_version": "1.1",
                "parent": data.get("parent"),
                "labels": data.get("labels", []),
            }
            with open(filepath, 'w') as f:
                f.write(f"---\n{yaml.dump(frontmatter)}---\n# Test\n")

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        # Test type filtering
        epic_query = [['type=epic']]
        epic_results = pipeline.execute_query(epic_query)
        assert len(epic_results) == 1
        assert 'bees-ep1' in epic_results

        # Test label filtering
        backend_query = [['label~backend']]
        backend_results = pipeline.execute_query(backend_query)
        assert len(backend_results) == 2
        assert 'bees-ep1' in backend_results
        assert 'bees-tk1' in backend_results

        # Test relationship traversal
        children_query = [['id=bees-ep1'], ['children']]
        children_results = pipeline.execute_query(children_query)
        assert len(children_results) == 2
        assert 'bees-tk1' in children_results
        assert 'bees-tk2' in children_results
