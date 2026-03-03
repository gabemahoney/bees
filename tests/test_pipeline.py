"""
Unit tests for query pipeline evaluation and orchestration.

PURPOSE:
Tests the PipelineEvaluator that orchestrates multi-stage query execution,
coordinating search and graph executors to process query pipelines.

SCOPE - Tests that belong here:
- PipelineEvaluator: Multi-stage query orchestration
- Stage-by-stage execution (piping results between stages)
- Integration between SearchExecutor and GraphExecutor
- Result set propagation through stages
- Empty result handling
- Multi-hive query context
- Error handling during execution

SCOPE - Tests that DON'T belong here:
- Query parsing -> test_query_parser.py
- Search execution details -> test_search_executor.py
- Graph execution details -> test_graph_executor.py
- Query storage -> test_query_tools.py
- Hive filtering logic -> test_multi_hive_query.py

RELATED FILES:
- test_search_executor.py: Search term execution (used by pipeline)
- test_graph_executor.py: Graph traversal (used by pipeline)
- test_query_parser.py: Parsing queries into pipeline stages
- test_multi_hive_query.py: Multi-hive filtering in pipelines
"""

from unittest.mock import patch

import pytest
import yaml

from src.fast_parser import fast_parse_frontmatter as real_fast_parse_frontmatter
from src.pipeline import PipelineEvaluator
from tests.test_constants import (
    TICKET_ID_EP1,
    TICKET_ID_EP2,
    TICKET_ID_ST1,
    TICKET_ID_TK1,
    TICKET_ID_TK2,
)


@pytest.fixture
def pipeline(isolated_bees_env):
    """Create PipelineEvaluator with test data using isolated_bees_env."""
    helper = isolated_bees_env

    hive_dir = helper.create_hive("test_hive", "Test Hive")
    helper.write_config()

    test_tickets = {
        TICKET_ID_EP1: {
            "id": TICKET_ID_EP1,
            "title": "Build Auth System",
            "type": "bee",
            "status": "open",
            "tags": ["backend", "security", "beta"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        },
        TICKET_ID_EP2: {
            "id": TICKET_ID_EP2,
            "title": "Frontend Dashboard",
            "type": "bee",
            "status": "closed",
            "tags": ["frontend", "ui"],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [TICKET_ID_EP1],
            "schema_version": "0.1",
        },
        TICKET_ID_TK1: {
            "id": TICKET_ID_TK1,
            "title": "Implement OAuth Login",
            "type": "t1",
            "status": "open",
            "tags": ["backend", "api"],
            "parent": TICKET_ID_EP1,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        },
        TICKET_ID_TK2: {
            "id": TICKET_ID_TK2,
            "title": "Build User Profile API",
            "type": "t1",
            "status": "open",
            "tags": ["backend", "api", "beta"],
            "parent": TICKET_ID_EP1,
            "children": [],
            "up_dependencies": [TICKET_ID_TK1],
            "down_dependencies": [],
            "schema_version": "0.1",
        },
        TICKET_ID_ST1: {
            "id": TICKET_ID_ST1,
            "title": "Write OAuth tests",
            "type": "t2",
            "status": "open",
            "tags": ["testing", "preview"],
            "parent": TICKET_ID_TK1,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        },
    }

    # Create hierarchical directory structure: {ticket_id}/{ticket_id}.md
    for ticket_id, frontmatter in test_tickets.items():
        ticket_dir = hive_dir / ticket_id
        ticket_dir.mkdir(parents=True, exist_ok=True)
        filepath = ticket_dir / f"{ticket_id}.md"
        content = f"---\n{yaml.dump(frontmatter)}---\n\n# {frontmatter['title']}\n\nTest ticket content.\n"
        with open(filepath, "w") as f:
            f.write(content)

    return PipelineEvaluator(tickets_dir=str(helper.base_path))


class TestPipelineEvaluatorInit:
    """Test PipelineEvaluator initialization and ticket loading."""

    def test_loads_and_normalizes_tickets(self, pipeline):
        """Test that all tickets are loaded and normalized for executor consumption."""
        assert len(pipeline.tickets) == 5
        assert TICKET_ID_EP1 in pipeline.tickets

        ticket = pipeline.tickets[TICKET_ID_TK1]
        # Check normalized fields exist
        for field in ["id", "title", "issue_type", "tags", "parent", "children", "up_dependencies", "down_dependencies"]:
            assert field in ticket

        # Verify relationships parsed correctly
        assert ticket["parent"] == TICKET_ID_EP1
        assert ticket["issue_type"] == "t1"

        tk2 = pipeline.tickets[TICKET_ID_TK2]
        assert TICKET_ID_TK1 in tk2["up_dependencies"]

        ep2 = pipeline.tickets[TICKET_ID_EP2]
        assert TICKET_ID_EP1 in ep2["down_dependencies"]


class TestQueryExecution:
    """Test sequential query execution with result passing."""

    def test_single_search_stage(self, pipeline):
        """Test execution of single search stage."""
        results = pipeline.execute_query([["type=bee"]])
        assert results == {TICKET_ID_EP1, TICKET_ID_EP2}

    def test_multiple_search_terms_anded(self, pipeline):
        """Test that multiple search terms in stage are ANDed."""
        results = pipeline.execute_query([["type=bee", "tag~beta"]])
        assert results == {TICKET_ID_EP1}

    def test_sequential_stage_execution(self, pipeline):
        """Test that stages execute sequentially with result passing."""
        results = pipeline.execute_query([["type=bee"], ["children"]])
        assert TICKET_ID_TK1 in results
        assert TICKET_ID_TK2 in results

    def test_deduplication_between_stages(self, pipeline):
        """Test that results are deduplicated between stages."""
        results = pipeline.execute_query([["type=t1"], ["parent"]])
        assert results == {TICKET_ID_EP1}

    def test_short_circuit_on_empty_results(self, pipeline):
        """Test that pipeline short-circuits when stage returns empty set."""
        results = pipeline.execute_query([
            ["type=bee", "tag~frontend"],
            ["children"],
            ["parent"],
        ])
        assert len(results) == 0

    def test_graph_stage_chaining(self, pipeline):
        """Test graph stage with multiple traversals chained."""
        results = pipeline.execute_query([["type=t1"], ["parent"], ["children"]])
        assert TICKET_ID_TK1 in results
        assert TICKET_ID_TK2 in results

    @pytest.mark.parametrize(
        "stages,expected_ids",
        [
            pytest.param([[f"parent={TICKET_ID_EP1}"]], {TICKET_ID_TK1, TICKET_ID_TK2}, id="parent_filter_alone"),
            pytest.param([[f"parent={TICKET_ID_EP1}", "type=t1"]], {TICKET_ID_TK1, TICKET_ID_TK2}, id="parent_with_type"),
            pytest.param([[f"parent={TICKET_ID_EP1}", "tag~api"]], {TICKET_ID_TK1, TICKET_ID_TK2}, id="parent_with_tag"),
            pytest.param([[f"parent={TICKET_ID_EP1}"], ["parent"]], {TICKET_ID_EP1}, id="parent_filter_multistage"),
        ],
    )
    def test_parent_filter(self, pipeline, stages, expected_ids):
        """Test parent= filter in various combinations."""
        results = pipeline.execute_query(stages)
        assert results == expected_ids


class TestStatusFilter:
    """Test status= filter in pipeline queries."""

    def test_status_filter_returns_matching(self, pipeline):
        """Test that status= filter returns only tickets with matching status."""
        results = pipeline.execute_query([["status=open"]])
        assert TICKET_ID_EP1 in results
        assert TICKET_ID_TK1 in results
        assert TICKET_ID_TK2 in results
        assert TICKET_ID_ST1 in results
        # bees-ep2 has status=closed, should not be in results
        assert TICKET_ID_EP2 not in results

    def test_status_combined_with_type(self, pipeline):
        """Test status= combined with type= (AND logic)."""
        results = pipeline.execute_query([["type=bee", "status=open"]])
        assert results == {TICKET_ID_EP1}

    def test_status_filter_then_graph(self, pipeline):
        """Test status= filter followed by graph traversal."""
        results = pipeline.execute_query([["status=open", "type=bee"], ["children"]])
        assert TICKET_ID_TK1 in results
        assert TICKET_ID_TK2 in results


class TestBatchExecution:
    """Test batch query execution with cached ticket data."""

    def test_executes_multiple_queries(self, pipeline):
        """Test that batch execution runs multiple queries and reuses cached data."""
        initial_count = len(pipeline.tickets)
        queries = [
            [["type=bee"]],
            [["type=t1"]],
            [["tag~beta"]],
        ]

        results = pipeline.execute_batch(queries)

        assert len(results) == 3
        assert len(results[0]) == 2
        assert len(results[1]) == 2
        assert len(results[2]) == 2
        assert len(pipeline.tickets) == initial_count

    def test_batch_with_complex_queries(self, pipeline):
        """Test batch execution with multi-stage queries."""
        queries = [
            [["type=bee", "tag~beta"], ["children"]],
            [["type=t1"], ["parent"]],
        ]

        results = pipeline.execute_batch(queries)

        assert TICKET_ID_TK1 in results[0]
        assert TICKET_ID_TK2 in results[0]
        assert TICKET_ID_EP1 in results[1]


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_query_stages(self, pipeline):
        """Test execution with empty stages list returns all tickets."""
        results = pipeline.execute_query([])
        assert len(results) == len(pipeline.tickets)

    def test_query_with_no_matching_tickets(self, pipeline):
        """Test query that matches no tickets."""
        results = pipeline.execute_query([["type=bee", "tag~nonexistent"]])
        assert len(results) == 0

    def test_graph_traversal_with_missing_relationships(self, pipeline):
        """Test graph traversal on tickets with no relationships."""
        results = pipeline.execute_query([[f"id={TICKET_ID_ST1}"], ["children"]])
        assert len(results) == 0


class TestHierarchicalStorage:
    """Test hierarchical directory storage and recursive glob patterns."""

    def test_loads_tickets_from_hierarchical_structure(self, isolated_bees_env):
        """Test that pipeline loads tickets from {ticket_id}/{ticket_id}.md structure."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Create ticket in hierarchical structure
        ticket_id = "b.tst"
        ticket_dir = hive_dir / ticket_id
        ticket_dir.mkdir(parents=True, exist_ok=True)

        ticket_data = {
            "id": ticket_id,
            "title": "Hierarchical Test",
            "type": "bee",
            "status": "open",
            "tags": [],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        }

        filepath = ticket_dir / f"{ticket_id}.md"
        content = f"---\n{yaml.dump(ticket_data)}---\n\nContent\n"
        with open(filepath, "w") as f:
            f.write(content)

        pipeline = PipelineEvaluator()
        assert ticket_id in pipeline.tickets
        assert pipeline.tickets[ticket_id]["title"] == "Hierarchical Test"

    def test_excludes_special_directories(self, isolated_bees_env):
        """Test that pipeline excludes eggs/, evicted/, .hive/ directories."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Create tickets in excluded directories
        excluded_dirs = ["eggs", "evicted", ".hive", "cemetery"]

        for excluded_dir in excluded_dirs:
            excluded_path = hive_dir / excluded_dir
            excluded_path.mkdir(parents=True, exist_ok=True)

            ticket_id = f"b.exc{excluded_dir[0]}"  # b.exce, b.excev, b.exc.
            ticket_dir = excluded_path / ticket_id
            ticket_dir.mkdir(parents=True, exist_ok=True)

            ticket_data = {
                "id": ticket_id,
                "title": f"Excluded from {excluded_dir}",
                "type": "bee",
                "status": "open",
                "tags": [],
                "parent": None,
                "children": [],
                "up_dependencies": [],
                "down_dependencies": [],
                "schema_version": "0.1",
            }

            filepath = ticket_dir / f"{ticket_id}.md"
            content = f"---\n{yaml.dump(ticket_data)}---\n\nContent\n"
            with open(filepath, "w") as f:
                f.write(content)

        # Create valid ticket at root level
        valid_id = "b.vam"
        valid_dir = hive_dir / valid_id
        valid_dir.mkdir(parents=True, exist_ok=True)

        valid_data = {
            "id": valid_id,
            "title": "Valid Ticket",
            "type": "bee",
            "status": "open",
            "tags": [],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        }

        filepath = valid_dir / f"{valid_id}.md"
        content = f"---\n{yaml.dump(valid_data)}---\n\nContent\n"
        with open(filepath, "w") as f:
            f.write(content)

        pipeline = PipelineEvaluator()

        # Valid ticket should be loaded
        assert valid_id in pipeline.tickets

        # Excluded tickets should NOT be loaded
        for excluded_dir in excluded_dirs:
            excluded_id = f"b.exc{excluded_dir[0]}"
            assert excluded_id not in pipeline.tickets

    def test_excludes_index_md_files(self, isolated_bees_env):
        """Test that pipeline excludes index.md files."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Create index.md file in hive root
        index_path = hive_dir / "index.md"
        index_content = "---\nid: should-not-load\ntitle: Index\ntype: bee\nschema_version: '0.1'\n---\nIndex content\n"
        with open(index_path, "w") as f:
            f.write(index_content)

        # Create valid ticket
        ticket_id = "b.vnd"
        ticket_dir = hive_dir / ticket_id
        ticket_dir.mkdir(parents=True, exist_ok=True)

        ticket_data = {
            "id": ticket_id,
            "title": "Valid Ticket",
            "type": "bee",
            "status": "open",
            "tags": [],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        }

        filepath = ticket_dir / f"{ticket_id}.md"
        content = f"---\n{yaml.dump(ticket_data)}---\n\nContent\n"
        with open(filepath, "w") as f:
            f.write(content)

        pipeline = PipelineEvaluator()

        # Valid ticket should be loaded
        assert ticket_id in pipeline.tickets

        # index.md ID should NOT be loaded
        assert "should-not-load" not in pipeline.tickets

    def test_only_loads_matching_hierarchical_pattern(self, isolated_bees_env):
        """Test that pipeline only loads files where directory name matches file stem."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Create mismatched pattern: directory name != file stem
        mismatched_dir = hive_dir / "wrong-dir-name"
        mismatched_dir.mkdir(parents=True, exist_ok=True)

        mismatched_file = mismatched_dir / "b.mis.md"
        mismatched_data = {
            "id": "b.mis",
            "title": "Mismatched Pattern",
            "type": "bee",
            "status": "open",
            "tags": [],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        }
        content = f"---\n{yaml.dump(mismatched_data)}---\n\nContent\n"
        with open(mismatched_file, "w") as f:
            f.write(content)

        # Create correctly matched pattern: directory name == file stem
        matched_id = "b.mat"
        matched_dir = hive_dir / matched_id
        matched_dir.mkdir(parents=True, exist_ok=True)

        matched_file = matched_dir / f"{matched_id}.md"
        matched_data = {
            "id": matched_id,
            "title": "Matched Pattern",
            "type": "bee",
            "status": "open",
            "tags": [],
            "parent": None,
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "schema_version": "0.1",
        }
        content = f"---\n{yaml.dump(matched_data)}---\n\nContent\n"
        with open(matched_file, "w") as f:
            f.write(content)

        pipeline = PipelineEvaluator()

        # Matched pattern should be loaded
        assert matched_id in pipeline.tickets

        # Mismatched pattern should NOT be loaded
        assert "b.mis" not in pipeline.tickets


class TestPipelineCacheIntegration:
    """fast_parse_frontmatter behavior across multiple PipelineEvaluator instances."""

    def test_each_instance_independently_parses_all_files(self, isolated_bees_env):
        """Each PipelineEvaluator instance calls fast_parse_frontmatter for every ticket file."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.ci1", "bee", "Cache Integration 1")
        helper.create_ticket(hive_dir, "b.ci2", "bee", "Cache Integration 2")

        with patch("src.fast_parser.fast_parse_frontmatter", wraps=real_fast_parse_frontmatter) as mock_parse:
            pipeline1 = PipelineEvaluator()
            first_count = mock_parse.call_count
            assert first_count == 2

            pipeline2 = PipelineEvaluator()
            assert mock_parse.call_count == first_count + 2  # Each instance parses all files fresh

        assert len(pipeline1.tickets) == 2
        assert len(pipeline2.tickets) == 2

    def test_modified_file_reflected_in_new_instance(self, isolated_bees_env):
        """A new PipelineEvaluator always reads fresh — file changes are picked up immediately."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.ci3", "bee", "Original Title")

        with patch("src.fast_parser.fast_parse_frontmatter", wraps=real_fast_parse_frontmatter) as mock_parse:
            pipeline1 = PipelineEvaluator()
            assert mock_parse.call_count == 1

            helper.create_ticket(hive_dir, "b.ci3", "bee", "Updated Title")

            pipeline2 = PipelineEvaluator()
            assert mock_parse.call_count == 2  # Second instance re-parses

        assert pipeline1.tickets["b.ci3"]["title"] == "Original Title"
        assert pipeline2.tickets["b.ci3"]["title"] == "Updated Title"


class TestFastParserIntegration:
    """Verify fast_parse_frontmatter integration inside _load_tickets()."""

    def test_fast_parse_frontmatter_invoked_not_yaml(self, isolated_bees_env):
        """_load_tickets() calls fast_parse_frontmatter for each ticket file."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.fp1", "bee", "Fast Parse One")
        helper.create_ticket(hive_dir, "b.fp2", "bee", "Fast Parse Two")

        with patch("src.fast_parser.fast_parse_frontmatter", wraps=real_fast_parse_frontmatter) as mock_fast:
            pipeline = PipelineEvaluator()

        assert mock_fast.call_count == 2
        assert "b.fp1" in pipeline.tickets
        assert "b.fp2" in pipeline.tickets

    def test_normalized_fields_from_fast_parsed_data(self, isolated_bees_env):
        """All normalized pipeline fields are correctly mapped from fast_parse_frontmatter output."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("bugs", "Bugs")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.nfp", "bee", "Normalized Fields", status="pupa")

        pipeline = PipelineEvaluator()
        assert "b.nfp" in pipeline.tickets
        ticket = pipeline.tickets["b.nfp"]

        assert ticket["id"] == "b.nfp"
        assert ticket["title"] == "Normalized Fields"
        assert ticket["issue_type"] == "bee"   # 'type' field maps to 'issue_type'
        assert ticket["status"] == "pupa"
        assert ticket["hive"] == "bugs"
        assert isinstance(ticket["tags"], list)
        assert isinstance(ticket["children"], list)
        assert isinstance(ticket["up_dependencies"], list)
        assert isinstance(ticket["down_dependencies"], list)

    def test_schema_version_absent_excludes_ticket(self, isolated_bees_env):
        """Files without schema_version are not loaded — fast_parse_frontmatter returns None."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        # Write a file without schema_version
        ticket_id = "b.nsv"
        ticket_dir = hive_dir / ticket_id
        ticket_dir.mkdir(parents=True, exist_ok=True)
        (ticket_dir / f"{ticket_id}.md").write_text(
            "---\nid: b.nsv\ntype: bee\ntitle: No Schema Version\nstatus: open\n---\nBody.\n"
        )

        # Write a valid ticket for comparison
        helper.create_ticket(hive_dir, "b.hsv", "bee", "Has Schema Version")

        pipeline = PipelineEvaluator()
        assert "b.nsv" not in pipeline.tickets
        assert "b.hsv" in pipeline.tickets

    def test_reverse_relationship_parent_to_children(self, isolated_bees_env):
        """_build_reverse_relationships() adds child ticket ID to parent's children list."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        helper.create_ticket(hive_dir, "b.par", "bee", "Parent Bee")
        helper.create_ticket(hive_dir, "t1.par.c1", "t1", "Child Task", parent="b.par")

        pipeline = PipelineEvaluator()
        assert "t1.par.c1" in pipeline.tickets
        assert "t1.par.c1" in pipeline.tickets["b.par"]["children"]

    def test_reverse_relationship_up_to_down_dependencies(self, isolated_bees_env):
        """_build_reverse_relationships() adds blocked ticket to blocker's down_dependencies."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("test_hive", "Test Hive")
        helper.write_config()

        helper.create_ticket(hive_dir, "b.bkr", "bee", "Blocker")

        # Write blocked ticket manually with proper YAML multi-line list
        blocked_id = "b.bkd"
        ticket_dir = hive_dir / blocked_id
        ticket_dir.mkdir(parents=True, exist_ok=True)
        (ticket_dir / f"{blocked_id}.md").write_text(
            "---\n"
            "id: b.bkd\n"
            "type: bee\n"
            "title: Blocked\n"
            "status: open\n"
            "up_dependencies:\n"
            "  - b.bkr\n"
            "schema_version: '0.1'\n"
            "guid: bkddef1234567890abcdef1234567890bk\n"
            "---\nBody.\n"
        )

        pipeline = PipelineEvaluator()
        assert "b.bkd" in pipeline.tickets
        assert "b.bkd" in pipeline.tickets["b.bkr"]["down_dependencies"]
