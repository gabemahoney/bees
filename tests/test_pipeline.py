"""Unit tests for PipelineEvaluator class."""

import json
import pytest
import tempfile
import yaml
from pathlib import Path
from src.pipeline import PipelineEvaluator


@pytest.fixture
def temp_tickets_dir(tmp_path):
    """Create temporary tickets directory with test tickets in markdown format."""
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()

    # Create subdirectories
    (tickets_dir / "epics").mkdir()
    (tickets_dir / "tasks").mkdir()
    (tickets_dir / "subtasks").mkdir()

    # Create test tickets as markdown files with YAML frontmatter
    test_tickets = {
        "epics/bees-ep1.md": {
            "id": "bees-ep1",
            "title": "Build Auth System",
            "type": "epic",
            "status": "open",
            "labels": ["backend", "security", "beta"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": []
        },
        "epics/bees-ep2.md": {
            "id": "bees-ep2",
            "title": "Frontend Dashboard",
            "type": "epic",
            "status": "closed",
            "labels": ["frontend", "ui"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": ["bees-ep1"]
        },
        "tasks/bees-tk1.md": {
            "id": "bees-tk1",
            "title": "Implement OAuth Login",
            "type": "task",
            "status": "open",
            "labels": ["backend", "api"],
            "parent": "bees-ep1",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": []
        },
        "tasks/bees-tk2.md": {
            "id": "bees-tk2",
            "title": "Build User Profile API",
            "type": "task",
            "status": "open",
            "labels": ["backend", "api", "beta"],
            "parent": "bees-ep1",
            "children": [],
            "up_dependencies": ["bees-tk1"],
            "down_dependencies": []
        },
        "subtasks/bees-st1.md": {
            "id": "bees-st1",
            "title": "Write OAuth tests",
            "type": "chore",
            "status": "open",
            "labels": ["testing", "preview"],
            "parent": "bees-tk1",
            "children": [],
            "up_dependencies": [],
            "down_dependencies": []
        },
    }

    for filename, frontmatter in test_tickets.items():
        filepath = tickets_dir / filename
        content = f"---\n{yaml.dump(frontmatter)}---\n\n# {frontmatter['title']}\n\nTest ticket content.\n"
        with open(filepath, 'w') as f:
            f.write(content)

    return tickets_dir


@pytest.fixture
def pipeline(temp_tickets_dir):
    """Create PipelineEvaluator with test data."""
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

    def test_missing_tickets_dir_raises_error(self, tmp_path):
        """Test that missing tickets directory raises FileNotFoundError."""
        nonexistent_dir = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError) as exc_info:
            PipelineEvaluator(tickets_dir=str(nonexistent_dir))

        assert "Tickets directory not found" in str(exc_info.value)

    def test_invalid_yaml_raises_error(self, tmp_path):
        """Test that malformed YAML frontmatter raises ValueError."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create markdown file with invalid YAML
        bad_file = tickets_dir / "tasks" / "bad.md"
        with open(bad_file, 'w') as f:
            f.write('---\n')
            f.write('id: bees-123\n')
            f.write('invalid: yaml: syntax: here\n')
            f.write('---\n')

        with pytest.raises(ValueError) as exc_info:
            PipelineEvaluator(tickets_dir=str(tickets_dir))

        assert "Invalid YAML" in str(exc_info.value)

    def test_skips_tickets_without_id(self, tmp_path):
        """Test that tickets without IDs are skipped with warning."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Ticket without ID
        no_id_file = tickets_dir / "tasks" / "no-id.md"
        with open(no_id_file, 'w') as f:
            f.write('---\ntitle: No ID ticket\ntype: task\n---\n# No ID\n')

        # Valid ticket
        valid_file = tickets_dir / "tasks" / "valid.md"
        with open(valid_file, 'w') as f:
            f.write('---\nid: bees-123\ntitle: Valid ticket\ntype: task\n---\n# Valid\n')

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

    def test_loads_tickets_from_subdirectories(self, tmp_path):
        """Test that tickets are loaded from epics/, tasks/, subtasks/ subdirectories."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        # Create tickets in each subdirectory
        for subdir, ticket_id in [("epics", "bees-ep1"), ("tasks", "bees-tk1"), ("subtasks", "bees-st1")]:
            filepath = tickets_dir / subdir / f"{ticket_id}.md"
            with open(filepath, 'w') as f:
                f.write(f'---\nid: {ticket_id}\ntype: {subdir[:-1]}\ntitle: Test\n---\n# Test\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 3
        assert 'bees-ep1' in pipeline.tickets
        assert 'bees-tk1' in pipeline.tickets
        assert 'bees-st1' in pipeline.tickets

    def test_skips_files_without_frontmatter(self, tmp_path):
        """Test that markdown files without YAML frontmatter are skipped."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # File without frontmatter
        bad_file = tickets_dir / "tasks" / "no-frontmatter.md"
        with open(bad_file, 'w') as f:
            f.write('# Just a regular markdown file\n\nNo YAML here.')

        # Valid file
        good_file = tickets_dir / "tasks" / "valid.md"
        with open(good_file, 'w') as f:
            f.write('---\nid: bees-123\ntype: task\ntitle: Valid\n---\n# Valid\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 1
        assert 'bees-123' in pipeline.tickets

    def test_skips_files_with_malformed_frontmatter(self, tmp_path):
        """Test that files with incomplete frontmatter delimiters are skipped."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # File with only opening delimiter
        bad_file = tickets_dir / "tasks" / "malformed.md"
        with open(bad_file, 'w') as f:
            f.write('---\nid: bees-bad\nNo closing delimiter')

        # Valid file
        good_file = tickets_dir / "tasks" / "valid.md"
        with open(good_file, 'w') as f:
            f.write('---\nid: bees-123\ntype: task\n---\n# Valid\n')

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

    def test_handles_missing_subdirectories_gracefully(self, tmp_path):
        """Test that missing subdirectories don't cause errors."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        # Only create tasks directory, not epics or subtasks
        (tickets_dir / "tasks").mkdir()

        task_file = tickets_dir / "tasks" / "bees-tk1.md"
        with open(task_file, 'w') as f:
            f.write('---\nid: bees-tk1\ntype: task\ntitle: Test\n---\n# Test\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))
        assert len(pipeline.tickets) == 1
        assert 'bees-tk1' in pipeline.tickets


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

    def test_handles_tickets_without_labels(self, tmp_path):
        """Test that tickets without labels field are handled gracefully."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Ticket without labels field
        task_file = tickets_dir / "tasks" / "bees-1.md"
        with open(task_file, 'w') as f:
            f.write('---\nid: bees-1\ntype: task\ntitle: Test\n---\n# Test\n')

        pipeline = PipelineEvaluator(tickets_dir=str(tickets_dir))

        # Should handle gracefully with empty labels array
        ticket = pipeline.tickets['bees-1']
        assert ticket['labels'] == []

        # Label search should not crash
        stages = [['label~test']]
        results = pipeline.execute_query(stages)
        assert len(results) == 0
