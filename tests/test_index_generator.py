"""Tests for index generation: scan_tickets, format_index_markdown, generate_index."""


import pytest

from src.index_generator import _TicketNode, _generate_mermaid_graph, _get_tier_display_names, _topo_sort_nodes, format_index_markdown, generate_index, scan_tickets
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
from tests.helpers import make_ticket
from tests.test_constants import (
    HIVE_BACKEND,
    TICKET_ID_EP1,
    TICKET_ID_EP2,
    TICKET_ID_INDEX_BABC1,
    TICKET_ID_INDEX_BEE_BACKEND1,
    TICKET_ID_INDEX_BEE_DEFAULT1,
    TICKET_ID_INDEX_BEE_DEFAULT2,
    TICKET_ID_INDEX_BEE_FRONTEND,
    MERMAID_TEST_TITLE,
    TICKET_ID_INDEX_BEES_ONLY_1,
    TICKET_ID_INDEX_BEES_ONLY_2,
    TICKET_ID_INDEX_HIER_BEE,
    TICKET_ID_INDEX_HIER_T1,
    TICKET_ID_INDEX_HIER_T2,
    TICKET_ID_INDEX_HIER_T3,
    TICKET_ID_INDEX_PHANTOM_PARENT,
    TICKET_ID_MERMAID_BEE_A,
    TICKET_ID_MERMAID_BEE_B,
    TICKET_ID_MERMAID_CIRC_A,
    TICKET_ID_MERMAID_CIRC_B,
    TICKET_ID_MERMAID_EPIC_A,
    TICKET_ID_MERMAID_EPIC_B,
    TICKET_ID_MERMAID_ORPHAN_DEP,
    TICKET_ID_INDEX_SUBTASK_B123A,
    TICKET_ID_INDEX_SUBTASK_SB1,
    TICKET_ID_INDEX_SUBTASK_TEST,
    TICKET_ID_INDEX_TASK_FXYZ9,
    TICKET_ID_INDEX_TASK_TEST,
    TICKET_ID_INDEX_TASK_TS1,
    TICKET_ID_INDEX_UNPARENTED,
    TITLE_TEST_BEE,
    TITLE_TEST_EPIC,
    TITLE_TEST_SUBTASK,
    TITLE_TEST_TASK,
)


@pytest.fixture
def index_env(tmp_path, monkeypatch, mock_global_bees_dir):
    """Tmp-path repo with global scoped config, hive registration, and ticket creation."""
    monkeypatch.chdir(tmp_path)

    class IndexEnv:
        def __init__(self, root, global_bees_dir):
            self.root = root
            self.global_bees_dir = global_bees_dir
            self.hives = {}
            self._hive_configs = {}

        def add_hive(self, name, display_name=None):
            """Create hive dir and register it."""
            hive_path = self.root / name
            hive_path.mkdir(exist_ok=True)
            self.hives[name] = hive_path
            self._hive_configs[name] = {
                "path": str(hive_path),
                "display_name": display_name or name.title(),
            }
            return hive_path

        def write_config(self, child_tiers=None, **overrides):
            scope_data = {
                "hives": self._hive_configs,
            }
            if child_tiers is not None:
                scope_data["child_tiers"] = child_tiers
            else:
                scope_data["child_tiers"] = {}
            scope_data.update(overrides)
            write_scoped_config(self.global_bees_dir, self.root, scope_data)

        def create_ticket(self, hive_path, ticket_id, ticket_type, title, status="open", parent_id=None, **extra):
            """Create ticket in hierarchical structure: {ticket_id}/{ticket_id}.md"""
            fields = {
                "id": ticket_id,
                "schema_version": "'1.1'",
                "type": ticket_type,
                "title": title,
                "status": status,
                "created_at": "'2026-01-30T10:00:00'",
                **extra,
            }
            lines = ["---"]
            for k, v in fields.items():
                lines.append(f"{k}: {v}")
            lines.append("---")
            lines.append("")
            lines.append(f"{title} body.")

            # Hierarchical structure: create ticket in its own directory
            if parent_id:
                # Nested under parent directory
                parent_dir = hive_path / parent_id
                ticket_dir = parent_dir / ticket_id
            else:
                # Root level
                ticket_dir = hive_path / ticket_id

            ticket_dir.mkdir(parents=True, exist_ok=True)
            path = ticket_dir / f"{ticket_id}.md"
            path.write_text("\n".join(lines))
            return path

        def setup_default_hive(self, child_tiers=None):
            hive_path = self.add_hive("default", "Default")
            # Default to standard 2-tier config if not specified
            if child_tiers is None:
                child_tiers = {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}
            self.write_config(child_tiers=child_tiers)
            return hive_path

    env = IndexEnv(tmp_path, mock_global_bees_dir)
    with repo_root_context(tmp_path):
        yield env


class TestGetTierDisplayNames:

    @pytest.mark.parametrize(
        "child_tiers,expected",
        [
            pytest.param(
                {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                {"t1": "Tasks", "t2": "Subtasks"},
                id="friendly_names",
            ),
            pytest.param(
                {"t1": [], "t2": []},
                {"t1": "t1", "t2": "t2"},
                id="null_friendly_names",
            ),
            pytest.param(
                {},
                {},
                id="no_child_tiers",
            ),
            pytest.param(
                {
                    "t1": ["Epic", "Epics"],
                    "t2": ["Feature", "Features"],
                    "t3": ["Story", "Stories"],
                    "t4": ["Task", "Tasks"],
                },
                {"t1": "Epics", "t2": "Features", "t3": "Stories", "t4": "Tasks"},
                id="multi_tier_config",
            ),
        ],
    )
    def test_get_tier_display_names_with_config(self, child_tiers, expected, index_env):
        """Should return correct tier display name mapping based on config."""
        index_env.write_config(child_tiers=child_tiers)
        result = _get_tier_display_names()
        assert result == expected

    def test_get_tier_display_names_no_config(self, tmp_path, monkeypatch):
        """Should return empty dict when no config exists."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            result = _get_tier_display_names()
        assert result == {}


class TestScanTickets:

    def test_scan_tickets_empty_directory(self, index_env):
        """Should return empty lists when no tickets exist."""
        index_env.setup_default_hive()
        result = scan_tickets()
        assert "bee" in result
        assert "t1" in result
        assert "t2" in result
        assert len(result["bee"]) == 0

    def test_scan_tickets_with_mixed_types(self, index_env):
        """Should group tickets by type correctly from hierarchical structure."""
        hive = index_env.setup_default_hive()
        index_env.create_ticket(hive, TICKET_ID_EP1, "bee", "Test Epic 1")
        index_env.create_ticket(hive, TICKET_ID_EP2, "bee", "Test Epic 2", status="closed")
        index_env.create_ticket(hive, TICKET_ID_INDEX_TASK_TS1, "t1", "Test Task 1")
        index_env.create_ticket(hive, TICKET_ID_INDEX_SUBTASK_SB1, "t2", "Test Subtask 1", parent=TICKET_ID_INDEX_TASK_TS1, parent_id=TICKET_ID_INDEX_TASK_TS1)

        result = scan_tickets()
        assert len(result["bee"]) == 2
        assert len(result["t1"]) == 1
        assert len(result["t2"]) == 1

        epic_ids = [t.id for t in result["bee"]]
        assert TICKET_ID_EP1 in epic_ids
        assert TICKET_ID_EP2 in epic_ids
        assert result["t1"][0].id == TICKET_ID_INDEX_TASK_TS1
        assert result["t2"][0].id == TICKET_ID_INDEX_SUBTASK_SB1

    def test_scan_tickets_with_invalid_ticket(self, index_env):
        """Should skip invalid tickets and continue processing."""
        hive = index_env.setup_default_hive()
        index_env.create_ticket(hive, TICKET_ID_EP1, "bee", "Valid Epic")

        # Create invalid ticket manually in hierarchical structure (missing required fields)
        invalid_dir = hive / "b.inv"
        invalid_dir.mkdir(exist_ok=True)
        (invalid_dir / "b.inv.md").write_text("---\ntype: bee\nschema_version: '1.1'\n---\n\nInvalid ticket missing id.")

        with pytest.warns(UserWarning, match="Failed to load ticket"):
            result = scan_tickets()

        assert len(result["bee"]) == 1
        assert result["bee"][0].id == TICKET_ID_EP1

    def test_scan_tickets_dynamic_result_dict_from_config(self, index_env):
        """Should initialize result dict dynamically from child_tiers config."""
        index_env.add_hive("default", "Default")
        index_env.write_config(
            child_tiers={"t1": ["Epic", "Epics"], "t2": ["Feature", "Features"], "t3": ["Task", "Tasks"]}
        )

        result = scan_tickets()
        assert "bee" in result
        assert "t1" in result
        assert "t2" in result
        assert "t3" in result

    def test_scan_tickets_backward_compatibility_no_config(self, tmp_path, monkeypatch):
        """Should return only bee tier when no config exists (dynamic tier system)."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            result = scan_tickets()
        assert "bee" in result
        assert len(result) == 1  # Only bee tier when no config



class TestTopoSortNodes:
    """Tests for _topo_sort_nodes dependency-aware ordering."""

    def test_dep_comes_after_its_dependency(self):
        """Node depending on another should appear after it."""
        a = _TicketNode(ticket=make_ticket(id="b.aaa", title="Alpha"))
        b = _TicketNode(ticket=make_ticket(id="b.bbb", title="Beta", up_dependencies=["b.aaa"]))
        result = _topo_sort_nodes([b, a])
        assert [n.ticket.id for n in result] == ["b.aaa", "b.bbb"]

    def test_alphabetical_tiebreak_within_same_level(self):
        """Nodes with no deps between each other sort alphabetically by title."""
        c = _TicketNode(ticket=make_ticket(id="b.c11", title="Cherry"))
        a = _TicketNode(ticket=make_ticket(id="b.a22", title="Apple"))
        b = _TicketNode(ticket=make_ticket(id="b.b33", title="Banana"))
        result = _topo_sort_nodes([c, a, b])
        assert [n.ticket.id for n in result] == ["b.a22", "b.b33", "b.c11"]

    def test_cycle_does_not_hang(self):
        """Circular dependency returns all nodes without hanging."""
        a = _TicketNode(ticket=make_ticket(id="b.cyA", title="Cycle A", up_dependencies=["b.cyB"]))
        b = _TicketNode(ticket=make_ticket(id="b.cyB", title="Cycle B", up_dependencies=["b.cyA"]))
        result = _topo_sort_nodes([a, b])
        assert len(result) == 2
        assert {n.ticket.id for n in result} == {"b.cyA", "b.cyB"}


class TestFormatIndexMarkdown:

    def test_format_empty_tickets(self):
        """Should return header-only output with no details blocks when all ticket lists empty."""
        tickets = {"bee": [], "t1": [], "t2": []}
        result = format_index_markdown(tickets)
        assert "# Ticket Index" in result
        assert "Generated:" in result
        assert "<details>" not in result

    def test_format_with_tickets(self):
        """Should render bee with children as <details>, unlinked tickets as plain <a> links."""
        epic1 = make_ticket(id=TICKET_ID_EP1, title=TITLE_TEST_EPIC)
        task1 = make_ticket(id=TICKET_ID_INDEX_TASK_TS1, type="t1", title=TITLE_TEST_TASK, status="in_progress")
        subtask1 = make_ticket(
            id=TICKET_ID_INDEX_SUBTASK_SB1, type="t2", title=TITLE_TEST_SUBTASK, parent=TICKET_ID_INDEX_TASK_TS1, status="closed"
        )
        tickets = {"bee": [epic1], "t1": [task1], "t2": [subtask1]}
        result = format_index_markdown(tickets)

        assert "# Ticket Index" in result
        # Bee has no linked children — renders as markdown link in <div> (leaf)
        assert f'<div id="b-ep1"' in result
        assert f"[{TITLE_TEST_EPIC}]({TICKET_ID_EP1}/{TICKET_ID_EP1}.md) [{TICKET_ID_EP1}]" in result
        assert '<summary id="b-ep1">' not in result
        # Unlinked tickets appear in Unparented section as markdown links
        assert f"[Test Task]({TICKET_ID_INDEX_TASK_TS1}/{TICKET_ID_INDEX_TASK_TS1}.md) [{TICKET_ID_INDEX_TASK_TS1}]" in result
        assert f"[Test Subtask]({TICKET_ID_INDEX_SUBTASK_SB1}/{TICKET_ID_INDEX_SUBTASK_SB1}.md) [{TICKET_ID_INDEX_SUBTASK_SB1}]" in result

    def test_format_sorts_by_title(self):
        """Should sort tickets by title (alphabetical) within each section."""
        epic1 = make_ticket(id="b.zzz", title="Last")
        epic2 = make_ticket(id="b.aaa", title="First")
        epic3 = make_ticket(id="b.mmm", title="Middle")
        tickets = {"bee": [epic1, epic2, epic3], "t1": [], "t2": []}
        result = format_index_markdown(tickets)

        pos_first = result.index("b.aaa")   # "First"
        pos_last = result.index("b.zzz")    # "Last"
        pos_mid = result.index("b.mmm")     # "Middle"
        assert pos_first < pos_last < pos_mid

    def test_format_sorts_children_alphabetically_by_title(self):
        """Children of a bee render in alphabetical title order regardless of dependencies."""
        child_a = make_ticket(id="t1.depA", type="t1", title="Setup Step")
        child_b = make_ticket(id="t1.depB", type="t1", title="Build Step", up_dependencies=["t1.depA"])
        bee = make_ticket(id="b.par1", title="Parent Bee", children=["t1.depA", "t1.depB"])
        tickets = {"bee": [bee], "t1": [child_a, child_b]}
        result = format_index_markdown(tickets)

        # "Build Step" (depB) < "Setup Step" (depA) alphabetically
        pos_b = result.index("t1.depB")
        pos_a = result.index("t1.depA")
        assert pos_b < pos_a

    def test_format_with_dynamic_tier_sections(self, index_env):
        """Leaf tickets render as plain links; no flat section headers."""
        index_env.write_config(child_tiers={"t1": ["Epic", "Epics"], "t2": ["Feature", "Features"]})

        epic1 = make_ticket(id="b.ep1", title=TITLE_TEST_BEE)
        t1_1 = make_ticket(id="t1.tk11", type="t1", title=TITLE_TEST_EPIC)
        t2_1 = make_ticket(id="t2.st21", type="t2", title="Test Feature")
        tickets = {"bee": [epic1], "t1": [t1_1], "t2": [t2_1]}
        result = format_index_markdown(tickets)

        # All tickets are leaves (no parent-child links) — render as markdown links in <div>
        assert "<div id=" in result
        assert "## Bees" not in result
        assert "## Epics" not in result
        assert "## Features" not in result

    def test_format_with_null_friendly_names_uses_tier_ids(self, index_env):
        """Bee with no children renders as plain link (no empty-state message)."""
        index_env.write_config(child_tiers={"t1": [], "t2": []})
        bee = make_ticket(id="b.nfn", title="Null Names Bee")
        tickets = {"bee": [bee], "t1": [], "t2": []}
        result = format_index_markdown(tickets)

        assert "# Ticket Index" in result
        assert '<div id="b-nfn"' in result
        assert "<details>" not in result

    def test_format_with_four_tier_config(self, index_env):
        """Bee with no children renders as plain link regardless of tier depth."""
        index_env.write_config(
            child_tiers={
                "t1": ["Epic", "Epics"],
                "t2": ["Feature", "Features"],
                "t3": ["Story", "Stories"],
                "t4": ["Task", "Tasks"],
            }
        )
        bee = make_ticket(id="b.4tr", title="Four Tier Bee")
        tickets = {"bee": [bee], "t1": [], "t2": [], "t3": [], "t4": []}
        result = format_index_markdown(tickets)

        assert '<div id="b-4tr"' in result
        assert "<details>" not in result
        assert "## Bees" not in result
        assert "## Epics" not in result


class TestGenerateIndex:

    def test_generate_index_end_to_end(self, index_env):
        """Should generate complete index with details blocks from hierarchical tickets directory."""
        hive = index_env.setup_default_hive()
        index_env.create_ticket(hive, TICKET_ID_EP1, "bee", "Sample Epic")
        index_env.create_ticket(hive, TICKET_ID_INDEX_TASK_TS1, "t1", "Sample Task")

        result = generate_index()

        assert "# Ticket Index" in result
        assert "Sample Epic" in result
        assert "Sample Task" in result
        # Bee has no linked children — renders as plain link, no empty-state message
        assert '<summary id="b-ep1">' not in result

    def test_hierarchical_paths_for_all_types(self, index_env):
        """Should generate hierarchical paths ({id}/{id}.md) for all ticket types."""
        hive = index_env.setup_default_hive()
        index_env.create_ticket(hive, TICKET_ID_INDEX_BEE_DEFAULT2, "bee", "Test Epic")
        index_env.create_ticket(hive, TICKET_ID_INDEX_TASK_TEST, "t1", "Test Task")
        index_env.create_ticket(hive, TICKET_ID_INDEX_SUBTASK_TEST, "t2", "Test Subtask", parent=TICKET_ID_INDEX_TASK_TEST, parent_id=TICKET_ID_INDEX_TASK_TEST)

        result = generate_index()

        # Hierarchical paths: {id}/{id}.md
        assert f"{TICKET_ID_INDEX_BEE_DEFAULT2}/{TICKET_ID_INDEX_BEE_DEFAULT2}.md" in result
        assert f"{TICKET_ID_INDEX_TASK_TEST}/{TICKET_ID_INDEX_TASK_TEST}.md" in result
        assert f"{TICKET_ID_INDEX_SUBTASK_TEST}/{TICKET_ID_INDEX_SUBTASK_TEST}.md" in result
        assert "tickets/epics/" not in result
        assert "tickets/tasks/" not in result
        assert "tickets/subtasks/" not in result

class TestPerHiveIndexGeneration:

    def test_scan_tickets_filter_by_hive(self, index_env):
        """Should filter tickets by hive prefix."""
        be = index_env.add_hive("backend", "Backend")
        fe = index_env.add_hive("frontend", "Frontend")
        df = index_env.add_hive("default", "Default")
        index_env.write_config()

        index_env.create_ticket(be, TICKET_ID_INDEX_BEE_BACKEND1, "bee", "Backend Epic")
        index_env.create_ticket(fe, TICKET_ID_INDEX_BEE_FRONTEND, "bee", "Frontend Epic")
        index_env.create_ticket(df, TICKET_ID_INDEX_BEE_DEFAULT1, "bee", "Legacy Epic")

        result = scan_tickets(hive_name="backend")
        assert len(result["bee"]) == 1
        assert result["bee"][0].id == TICKET_ID_INDEX_BEE_BACKEND1

        result = scan_tickets(hive_name="frontend")
        assert len(result["bee"]) == 1
        assert result["bee"][0].id == TICKET_ID_INDEX_BEE_FRONTEND

        result = scan_tickets()
        assert len(result["bee"]) == 3

    def test_generate_index_with_hive_writes_to_hive_root(self, index_env):
        """Should write index to hive root directory when hive_name provided."""
        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()
        index_env.create_ticket(be, TICKET_ID_INDEX_BEE_BACKEND1, "bee", "Backend Epic")

        generate_index(hive_name="backend")

        index_path = be / "index.md"
        assert index_path.exists()
        index_content = index_path.read_text()
        assert "# Ticket Index" in index_content
        assert TICKET_ID_INDEX_BEE_BACKEND1 in index_content
        assert "Backend Epic" in index_content

    def test_generate_index_all_hives_writes_multiple_indexes(self, index_env):
        """Should write separate indexes for all hives when hive_name omitted."""
        be = index_env.add_hive("backend", "Backend")
        fe = index_env.add_hive("frontend", "Frontend")
        index_env.write_config()

        index_env.create_ticket(be, TICKET_ID_INDEX_BEE_BACKEND1, "bee", "Backend Epic")
        index_env.create_ticket(fe, TICKET_ID_INDEX_BEE_FRONTEND, "bee", "Frontend Epic")

        generate_index()

        backend_index = be / "index.md"
        assert backend_index.exists()
        backend_content = backend_index.read_text()
        assert TICKET_ID_INDEX_BEE_BACKEND1 in backend_content
        assert "Backend Epic" in backend_content
        assert TICKET_ID_INDEX_BEE_FRONTEND not in backend_content

        frontend_index = fe / "index.md"
        assert frontend_index.exists()
        frontend_content = frontend_index.read_text()
        assert TICKET_ID_INDEX_BEE_FRONTEND in frontend_content
        assert "Frontend Epic" in frontend_content
        assert TICKET_ID_INDEX_BEE_BACKEND1 not in frontend_content

    def test_generate_index_hive_not_in_config(self, index_env):
        """Should create hive directory and write index when hive not in config."""
        hive = index_env.add_hive("newback", "New Backend")
        index_env.write_config()
        index_env.create_ticket(hive, "b.nep1", "bee", "New Backend Epic")

        generate_index(hive_name="newback")

        index_path = hive / "index.md"
        assert index_path.exists()
        index_content = index_path.read_text()
        assert "b.nep1" in index_content

    def test_generate_index_no_config_returns_markdown(self, index_env):
        """Should return markdown without writing when no config exists."""
        hive = index_env.setup_default_hive()
        index_env.create_ticket(hive, TICKET_ID_EP1, "bee", "Legacy Epic")

        result = generate_index()

        assert TICKET_ID_EP1 in result
        assert "Legacy Epic" in result

        index_path = hive / "index.md"
        assert index_path.exists()



class TestHierarchicalStorageLinkGeneration:

    def test_format_uses_hierarchical_link_paths(self):
        """Should use hierarchical paths ({id}/{id}.md) without type subdirectories."""
        epic1 = make_ticket(id=TICKET_ID_INDEX_BABC1, title=TITLE_TEST_EPIC)
        task1 = make_ticket(id=TICKET_ID_INDEX_TASK_FXYZ9, type="t1", title=TITLE_TEST_TASK)
        subtask1 = make_ticket(
            id=TICKET_ID_INDEX_SUBTASK_B123A, type="t2", title=TITLE_TEST_SUBTASK, parent=TICKET_ID_INDEX_BABC1
        )
        tickets = {"bee": [epic1], "t1": [task1], "t2": [subtask1]}
        result = format_index_markdown(tickets)

        # Hierarchical paths appear in href attributes
        assert f"({TICKET_ID_INDEX_BABC1}/{TICKET_ID_INDEX_BABC1}.md)" in result
        assert f"({TICKET_ID_INDEX_TASK_FXYZ9}/{TICKET_ID_INDEX_TASK_FXYZ9}.md)" in result
        assert f"({TICKET_ID_INDEX_SUBTASK_B123A}/{TICKET_ID_INDEX_SUBTASK_B123A}.md)" in result
        assert "tickets/epics/" not in result
        assert "tickets/tasks/" not in result
        assert "tickets/subtasks/" not in result

class TestIsIndexStaleHierarchicalStorage:

    def test_is_index_stale_scans_hierarchical_directories(self, index_env):
        """Should scan hive recursively for hierarchical ticket structure."""
        import time

        from src.index_generator import is_index_stale

        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()

        index_path = be / "index.md"
        index_path.write_text("# Old Index")

        index_env.create_ticket(be, "b.babc", "bee", "Test Epic")

        time.sleep(0.01)
        # Update ticket in hierarchical structure
        ticket_dir = be / "b.babc"
        (ticket_dir / "b.babc.md").write_text(
            "---\nid: b.babc\ntype: bee\ntitle: Updated Epic\nschema_version: '1.1'\n---\nUpdated."
        )

        assert is_index_stale(HIVE_BACKEND) is True

    def test_is_index_stale_skips_index_itself(self, index_env):
        """Should skip index.md when checking modification times."""
        import time

        from src.index_generator import is_index_stale

        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()

        # Create ticket in hierarchical structure
        ticket_dir = be / "b.babc"
        ticket_dir.mkdir(exist_ok=True)
        (ticket_dir / "b.babc.md").write_text(
            "---\nid: b.babc\ntype: bee\nschema_version: '1.1'\n---\nEpic."
        )
        time.sleep(0.01)
        (be / "index.md").write_text("# Index")

        assert is_index_stale(HIVE_BACKEND) is False

    def test_is_index_stale_detects_nested_ticket_changes(self, index_env):
        """Should detect changes in nested child tickets."""
        import time

        from src.index_generator import is_index_stale

        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()

        # Create parent bee ticket
        bee_dir = be / "b.abc"
        bee_dir.mkdir()
        (bee_dir / "b.abc.md").write_text(
            "---\nid: b.abc\nschema_version: '1.1'\ntype: bee\ntitle: Parent\n---\nParent."
        )

        time.sleep(0.01)
        (be / "index.md").write_text("# Index")
        time.sleep(0.01)

        # Create nested child ticket (should trigger staleness)
        child_dir = bee_dir / "t1.x4f.ab"
        child_dir.mkdir()
        (child_dir / "t1.x4f.ab.md").write_text(
            "---\nid: t1.x4f.ab\nschema_version: '1.1'\ntype: t1\ntitle: Child\nparent: b.abc\n---\nChild."
        )

        assert is_index_stale(HIVE_BACKEND) is True

    def test_is_index_stale_empty_hive_directory(self, index_env):
        """Should handle empty hive directory (no tickets) gracefully."""
        from src.index_generator import is_index_stale

        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()
        (be / "index.md").write_text("# Index")

        assert is_index_stale(HIVE_BACKEND) is False

    def test_is_index_stale_ignores_non_md_files(self, index_env):
        """Should ignore non-.md files when checking staleness."""
        import time

        from src.index_generator import is_index_stale

        be = index_env.add_hive("backend", "Backend")
        index_env.write_config()

        # Create ticket in hierarchical structure
        ticket_dir = be / "b.babc"
        ticket_dir.mkdir(exist_ok=True)
        (ticket_dir / "b.babc.md").write_text(
            "---\nid: b.babc\ntype: bee\nschema_version: '1.1'\n---\nEpic."
        )
        time.sleep(0.01)
        (be / "index.md").write_text("# Index")
        time.sleep(0.01)

        # Add non-.md files (should not trigger staleness)
        (be / "README.txt").write_text("readme")
        (be / "notes.json").write_text("{}")
        (be / ".hidden").write_text("hidden")
        (ticket_dir / "config.yaml").write_text("config: true")

        assert is_index_stale(HIVE_BACKEND) is False


class TestHierarchicalStorageExclusions:

    @pytest.mark.parametrize(
        "excluded_dir,hive_name,root_type,root_id,excluded_type",
        [
            pytest.param("eggs", "backend", "bee", "b.babc", "t1", id="eggs_directory"),
            pytest.param("evicted", "frontend", "t1", "t1.fxy.za", "bee", id="evicted_directory"),
            pytest.param("cemetery", "backend", "bee", "b.babc", "t1", id="cemetery_directory"),
        ],
    )
    def test_scan_tickets_excludes_subdirectory(
        self, excluded_dir, hive_name, root_type, root_id, excluded_type, index_env
    ):
        """Should exclude tickets in eggs/evicted subdirectories from scan."""
        hive = index_env.add_hive(hive_name, hive_name.title())
        index_env.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]})
        index_env.create_ticket(hive, root_id, root_type, "Root Ticket")

        subdir = hive / excluded_dir
        subdir.mkdir()
        excluded_id = "t1.exc.ma" if excluded_type == "t1" else "b.exc"
        index_env.create_ticket(subdir, excluded_id, excluded_type, "Excluded Ticket")

        result = scan_tickets()
        assert len(result[root_type]) == 1
        assert len(result[excluded_type]) == 0
        assert result[root_type][0].id == root_id

    def test_scan_tickets_excludes_both_eggs_and_evicted(self, index_env):
        """Should exclude both /eggs and /evicted subdirectories simultaneously."""
        hive = index_env.add_hive("test_hive", "Test Hive")
        index_env.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]})
        index_env.create_ticket(hive, "b.tst1", "bee", "Active Epic")
        index_env.create_ticket(hive, "t1.tst.12", "t1", "Active Task")

        eggs_dir = hive / "eggs"
        eggs_dir.mkdir()
        index_env.create_ticket(eggs_dir, "t2.egg.1a.bc", "t2", "Template Subtask")

        evicted_dir = hive / "evicted"
        evicted_dir.mkdir()
        index_env.create_ticket(evicted_dir, "b.old1", "bee", "Archived Epic", status="completed")

        result = scan_tickets()
        assert len(result["bee"]) == 1
        assert len(result["t1"]) == 1
        assert len(result["t2"]) == 0
        assert result["bee"][0].id == "b.tst1"
        assert result["t1"][0].id == "t1.tst.12"

    def test_generate_index_excludes_eggs_and_evicted(self, index_env):
        """Generated index should not include tickets from /eggs or /evicted."""
        hive = index_env.add_hive("my_hive", "My Hive")
        index_env.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]})
        index_env.create_ticket(hive, "b.vis1", "bee", "Visible Epic")

        eggs_dir = hive / "eggs"
        eggs_dir.mkdir()
        index_env.create_ticket(eggs_dir, "t1.egg1", "t1", "Hidden Egg")

        evicted_dir = hive / "evicted"
        evicted_dir.mkdir()
        index_env.create_ticket(evicted_dir, "t2.old1", "t2", "Hidden Archive")

        result = generate_index()

        assert "b.vis1" in result
        assert "Visible Epic" in result
        assert "t1.egg1" not in result
        assert "Hidden Egg" not in result
        assert "t2.old1" not in result
        assert "Hidden Archive" not in result

    def test_generate_index_excludes_cemetery(self, index_env):
        """Generated index should not include tickets from cemetery/."""
        hive = index_env.add_hive("my_hive", "My Hive")
        index_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        index_env.create_ticket(hive, "b.vis3", "bee", "Active Epic")

        cemetery_dir = hive / "cemetery"
        cemetery_dir.mkdir()
        index_env.create_ticket(cemetery_dir, "b.ded2", "bee", "Buried Epic")

        result = generate_index()
        assert "b.vis3" in result
        assert "Active Epic" in result
        assert "b.ded2" not in result
        assert "Buried Epic" not in result


def setup_index_hives_with_child_tiers(index_env, hive_configs, global_child_tiers=None):
    """Helper to set up multiple hives with per-hive child_tiers for index generator tests.

    Args:
        index_env: IndexEnv fixture instance
        hive_configs: Dict of {hive_name: {"child_tiers": {...}, "display_name": str (optional)}}
        global_child_tiers: Optional global child_tiers dict (list format)

    Returns:
        Dict of {hive_name: hive_path}
    """
    hives = {}
    scope_data = {"hives": {}}

    for hive_name, hive_spec in hive_configs.items():
        hive_path = index_env.add_hive(hive_name, hive_spec.get("display_name", hive_name.title()))
        hives[hive_name] = hive_path

        scope_data["hives"][hive_name] = {
            "path": str(hive_path),
            "display_name": hive_spec.get("display_name", hive_name.title()),
            "created_at": "2026-02-05T00:00:00",
        }

        if "child_tiers" in hive_spec:
            scope_data["hives"][hive_name]["child_tiers"] = hive_spec["child_tiers"]

    if global_child_tiers is not None:
        scope_data["child_tiers"] = global_child_tiers

    write_scoped_config(index_env.global_bees_dir, index_env.root, scope_data)
    return hives


class TestPerHiveChildTiersResolution:
    """Tests for per-hive child_tiers resolution in index generator functions."""

    def test_get_tier_display_names_uses_hive_child_tiers(self, index_env):
        """_get_tier_display_names should use hive-level child_tiers, not global."""
        # Set up two hives with different child_tiers
        setup_index_hives_with_child_tiers(
            index_env,
            {
                "hive1": {"child_tiers": {"t1": ["Epic", "Epics"]}},
                "hive2": {
                    "child_tiers": {
                        "t1": ["Task", "Tasks"],
                        "t2": ["Subtask", "Subtasks"],
                        "t3": ["Work Item", "Work Items"],
                    }
                },
            },
            global_child_tiers={"t1": ["Task", "Tasks"]},
        )

        # Test hive1: should get "Epics" (singular tier with custom name)
        with repo_root_context(index_env.root):
            names_hive1 = _get_tier_display_names(hive_name="hive1")
            assert names_hive1 == {"t1": "Epics"}

            # Test hive2: should get 3-tier names
            names_hive2 = _get_tier_display_names(hive_name="hive2")
            assert names_hive2 == {"t1": "Tasks", "t2": "Subtasks", "t3": "Work Items"}

    def test_scan_tickets_uses_hive_child_tiers(self, index_env):
        """scan_tickets should use hive-level child_tiers to determine tier keys."""
        # Set up two hives with different child_tiers (no global)
        hives = setup_index_hives_with_child_tiers(
            index_env,
            {
                "hive1": {"child_tiers": {"t1": ["Task", "Tasks"]}},
                "hive2": {"child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]}},
            },
        )

        # Create tickets in both hives
        index_env.create_ticket(hives["hive1"], "b.h1e1", "bee", "Hive1 Bee")
        index_env.create_ticket(hives["hive1"] / "b.h1e1", "t1.h1t.1a", "t1", "Hive1 Task", parent_id="b.h1e1")

        index_env.create_ticket(hives["hive2"], "b.h2e1", "bee", "Hive2 Bee")
        index_env.create_ticket(hives["hive2"] / "b.h2e1", "t1.h2t.1a", "t1", "Hive2 Task", parent_id="b.h2e1")
        index_env.create_ticket(
            hives["hive2"] / "b.h2e1" / "t1.h2t.1a", "t2.h2s.1a.bc", "t2", "Hive2 Subtask", parent_id="t1.h2t.1a"
        )

        # Test hive1: should have keys ["bee", "t1"] only
        with repo_root_context(index_env.root):
            result_hive1 = scan_tickets(hive_name="hive1")
            assert set(result_hive1.keys()) == {"bee", "t1"}
            assert len(result_hive1["bee"]) == 1
            assert len(result_hive1["t1"]) == 1

            # Test hive2: should have keys ["bee", "t1", "t2"]
            result_hive2 = scan_tickets(hive_name="hive2")
            assert set(result_hive2.keys()) == {"bee", "t1", "t2"}
            assert len(result_hive2["bee"]) == 1
            assert len(result_hive2["t1"]) == 1
            assert len(result_hive2["t2"]) == 1

    def test_format_index_markdown_uses_hive_tier_names(self, index_env):
        """format_index_markdown should use per-hive tier display names in empty-state."""
        # Set up hive with custom tier names and global config
        hives = setup_index_hives_with_child_tiers(
            index_env,
            {"custom_hive": {"child_tiers": {"t1": ["Epic", "Epics"]}, "display_name": "Custom Hive"}},
            global_child_tiers={"t1": ["Task", "Tasks"]},
        )

        # Create tickets
        index_env.create_ticket(hives["custom_hive"], "b.cst1", "bee", "Custom Bee")
        index_env.create_ticket(hives["custom_hive"] / "b.cst1", "t1.cst.2a", "t1", "Custom Task", parent_id="b.cst1")

        # Generate markdown with hive_name
        with repo_root_context(index_env.root):
            tickets = scan_tickets(hive_name="custom_hive")
            result = format_index_markdown(tickets, hive_name="custom_hive")

            # bee has a t1 child (t1.Cst2) which has no children — renders as markdown link
            assert "Custom Bee" in result
            assert "## Epics" not in result
            assert "## Tasks" not in result

    def test_bees_only_hive_has_no_tier_sections(self, index_env):
        """Hive configured as bees-only (empty child_tiers) should have no tier sections in index."""
        # Set up bees-only hive with global config having t1
        hives = setup_index_hives_with_child_tiers(
            index_env,
            {"bees_only_hive": {"child_tiers": {}, "display_name": "Bees Only"}},
            global_child_tiers={"t1": ["Task", "Tasks"]},
        )

        # Create only bee tickets
        index_env.create_ticket(hives["bees_only_hive"], "b.bo1", "bee", "Bees Only Bee 1")
        index_env.create_ticket(hives["bees_only_hive"], "b.bo2", "bee", "Bees Only Bee 2")

        # Scan tickets
        with repo_root_context(index_env.root):
            result = scan_tickets(hive_name="bees_only_hive")

            # Should only have "bee" key, no tier keys
            assert set(result.keys()) == {"bee"}
            assert len(result["bee"]) == 2

            # Format markdown
            markdown = format_index_markdown(result, hive_name="bees_only_hive")

            # Should have no tier sections
            assert "## Tasks" not in markdown
            assert "## t1" not in markdown

    def test_hive_without_child_tiers_falls_back_to_global(self, index_env):
        """Hive without child_tiers should fall back to global config."""
        # Set up hive without child_tiers (None) and global config with t1
        hives = setup_index_hives_with_child_tiers(
            index_env,
            {"hive_fallback": {}},  # No child_tiers specified
            global_child_tiers={"t1": ["Task", "Tasks"]},
        )

        # Create tickets: bee and t1 (should be valid via global fallback)
        index_env.create_ticket(hives["hive_fallback"], "b.fb1", "bee", "Fallback Bee")
        index_env.create_ticket(hives["hive_fallback"] / "b.fb1", "t1.fb2.1a", "t1", "Fallback Task", parent_id="b.fb1")

        # Test that scan_tickets includes t1 tier key (via global fallback)
        with repo_root_context(index_env.root):
            result = scan_tickets(hive_name="hive_fallback")
            assert set(result.keys()) == {"bee", "t1"}
            assert len(result["bee"]) == 1
            assert len(result["t1"]) == 1

            # Test that _get_tier_display_names uses global config
            names = _get_tier_display_names(hive_name="hive_fallback")
            assert names == {"t1": "Tasks"}


class TestHierarchyRendering:
    """Tests for hierarchical details/summary rendering in format_index_markdown."""

    def test_full_four_tier_hierarchy(self, index_env):
        """4-tier chain (Bee→Epic→Task→Subtask) renders all nodes as nested <details>."""
        index_env.write_config(
            child_tiers={"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"], "t3": ["Subtask", "Subtasks"]}
        )
        bee = make_ticket(id=TICKET_ID_INDEX_HIER_BEE, children=[TICKET_ID_INDEX_HIER_T1])
        t1 = make_ticket(id=TICKET_ID_INDEX_HIER_T1, type="t1", title="Hier Epic", children=[TICKET_ID_INDEX_HIER_T2])
        t2 = make_ticket(id=TICKET_ID_INDEX_HIER_T2, type="t2", title="Hier Task", children=[TICKET_ID_INDEX_HIER_T3])
        t3 = make_ticket(id=TICKET_ID_INDEX_HIER_T3, type="t3", title="Hier Subtask")
        tickets = {"bee": [bee], "t1": [t1], "t2": [t2], "t3": [t3]}
        result = format_index_markdown(tickets)

        # Parent tiers with children render as <details>; deepest leaf renders as plain <a>
        assert f'<summary id="b-hc1">' in result
        assert f'<summary id="t1-hc1-ab">' in result
        assert f'<summary id="t2-hc1-ab-cd">' in result
        assert f'<div id="t3-hc1-ab-cd-ef"' in result
        assert f'<summary id="t3-hc1-ab-cd-ef">' not in result

    def test_partial_two_tier_hierarchy(self):
        """Bee with direct leaf children renders children as <details> blocks."""
        bee = make_ticket(id="b.p2t", children=["t1.p2ta"])
        task = make_ticket(id="t1.p2ta", type="t1", title="Direct Task")
        tickets = {"bee": [bee], "t1": [task]}
        result = format_index_markdown(tickets)

        assert "<details>" in result
        # All children render as <details> for consistent hierarchy
        assert 'id="t1-p2ta"' in result

    def test_bee_with_multiple_children(self):
        """All children of a bee are rendered, none omitted."""
        bee = make_ticket(id="b.mc1", children=["t1.mc1a", "t1.mc1b"])
        child1 = make_ticket(id="t1.mc1a", type="t1", title="Child A")
        child2 = make_ticket(id="t1.mc1b", type="t1", title="Child B")
        tickets = {"bee": [bee], "t1": [child1, child2]}
        result = format_index_markdown(tickets)

        assert "Child A" in result
        assert "Child B" in result

    def test_missing_child_reference_no_crash(self):
        """Bee referencing a non-existent child ID does not crash; bee renders as plain link."""
        bee = make_ticket(id="b.mcr", children=["t1.gone"])
        tickets = {"bee": [bee], "t1": []}
        result = format_index_markdown(tickets)

        assert '<div id="b-mcr"' in result
        assert "t1.gone" not in result  # Missing child is silently skipped

    @pytest.mark.parametrize(
        "has_children,expect_details",
        [
            pytest.param(False, False, id="leaf_is_plain_link"),
            pytest.param(True, True, id="non_leaf_is_details"),
        ],
    )
    def test_leaf_vs_non_leaf_rendering(self, has_children, expect_details):
        """Leaf nodes render as plain <a> links; nodes with children render as <details>."""
        child_ids = ["t2.lvn1a"] if has_children else []
        t1 = make_ticket(id="t1.lvn1", type="t1", title="Test Node", children=child_ids)
        children = [make_ticket(id="t2.lvn1a", type="t2", title="Leaf")] if has_children else []
        bee = make_ticket(id="b.lvn", children=["t1.lvn1"])
        tickets = {"bee": [bee], "t1": [t1], "t2": children}
        result = format_index_markdown(tickets)

        if expect_details:
            assert '<summary id="t1-lvn1">' in result
        else:
            assert '<div id="t1-lvn1"' in result
            assert '<summary id="t1-lvn1">' not in result


class TestHierarchyEdgeCases:
    """Edge case tests for hierarchy rendering."""

    def test_empty_hive_no_details(self):
        """Empty hive produces header + timestamp only, no details or mermaid blocks."""
        result = format_index_markdown({"bee": []})
        assert "# Ticket Index" in result
        assert "<details>" not in result
        assert "```mermaid" not in result
        assert "graph TD" not in result

    def test_bees_only_hive_details_per_bee(self, index_env):
        """Bees-only hive renders each bee as details with empty-state, no nesting."""
        index_env.write_config(child_tiers={})
        bee1 = make_ticket(id=TICKET_ID_INDEX_BEES_ONLY_1, title="Bee One")
        bee2 = make_ticket(id=TICKET_ID_INDEX_BEES_ONLY_2, title="Bee Two")
        tickets = {"bee": [bee1, bee2]}
        result = format_index_markdown(tickets)

        # Bees with no children render as markdown links in <div>, not <details>
        assert "<details>" not in result
        assert "Bee One" in result
        assert "Bee Two" in result

    def test_anchor_ids_replace_dots_with_hyphens(self):
        """Summary elements have id attributes with dots replaced by hyphens."""
        bee = make_ticket(id=TICKET_ID_INDEX_HIER_BEE, title="Anchor Test")
        tickets = {"bee": [bee]}
        result = format_index_markdown(tickets)

        assert 'id="b-hc1"' in result
        assert 'id="b.hc1"' not in result

    def test_unparented_ticket_in_unparented_section(self):
        """Non-bee ticket with phantom parent appears in Unparented Tickets section."""
        orphan = make_ticket(
            id=TICKET_ID_INDEX_UNPARENTED, type="t1", title="Orphan Task",
            parent=TICKET_ID_INDEX_PHANTOM_PARENT,
        )
        tickets = {"bee": [], "t1": [orphan]}
        result = format_index_markdown(tickets)

        assert "<details><summary>Unparented Tickets</summary>" in result
        assert "Orphan Task" in result


class TestGenerateMermaidGraph:
    """Tests for _generate_mermaid_graph dependency graph generation."""

    def test_single_ticket_returns_empty(self):
        """Single ticket produces empty string — single-node graphs are not useful."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title=MERMAID_TEST_TITLE)
        assert _generate_mermaid_graph([a]) == ""

    def test_two_tickets_no_deps_produces_no_graph(self):
        """Two tickets with no edges produce no graph (nothing to visualise)."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title=MERMAID_TEST_TITLE)
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title=MERMAID_TEST_TITLE)
        result = _generate_mermaid_graph([a, b])
        assert result == ""

    def test_single_dep_edge_produces_graph(self):
        """Two tickets with a dependency produce a graph TD block with an edge."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Dep Source")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Dep Target", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        assert "graph TD" in result
        assert "b_ma1 --> b_mb1" in result

    def test_all_classdef_declarations_present(self):
        """Graph output contains all four status classDef declarations."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        for status in ("larva", "pupa", "worker", "finished"):
            assert f"classDef {status}" in result

    def test_nodes_carry_status_class(self):
        """Node declarations include :::status syntax."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="A", status="pupa")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="B", status="worker", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        assert ":::pupa" in result
        assert ":::worker" in result

    def test_orphan_dep_stadium_shape_no_click(self):
        """Orphan dep renders as stadium-shaped node with no click directive."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="A", up_dependencies=[TICKET_ID_MERMAID_ORPHAN_DEP])
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="B")
        result = _generate_mermaid_graph([a, b])

        # Orphan uses stadium shape ([" "])
        assert f'b_mzz(["{TICKET_ID_MERMAID_ORPHAN_DEP}"])' in result
        # No click for orphan
        assert "click b_mzz" not in result

    def test_no_click_directives_in_graph(self):
        """Graph output contains no click directives (they open the browser in PyCharm)."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        assert "click " not in result

    def test_external_dep_renders_as_orphan(self):
        """Dep pointing outside the provided ticket set renders as orphan node."""
        ea = make_ticket(id=TICKET_ID_MERMAID_EPIC_A, type="t1", title="Epic A")
        eb = make_ticket(
            id=TICKET_ID_MERMAID_EPIC_B, type="t1", title="Epic B",
            up_dependencies=[TICKET_ID_MERMAID_EPIC_A, TICKET_ID_MERMAID_ORPHAN_DEP],
        )
        result = _generate_mermaid_graph([ea, eb])

        # Internal dep: normal edge
        assert "t1_mea_1a --> t1_meb_1a" in result
        # External dep: orphan node (stadium shape)
        assert f'b_mzz(["{TICKET_ID_MERMAID_ORPHAN_DEP}"])' in result

    def test_node_ids_use_underscores(self):
        """Mermaid node identifiers replace dots with underscores (labels keep dots)."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        # Node identifiers use underscores
        assert "b_ma1[" in result
        # Dot-form never appears as a node identifier (only inside quoted labels)
        assert "b.ma1[" not in result
        assert "b.ma1 -->" not in result

    def test_node_labels_include_id_and_title(self):
        """Node labels contain ticket ID and title in ["id: title"] format."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Alpha Bee")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Beta Bee", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        assert f'"{TICKET_ID_MERMAID_BEE_A}: Alpha Bee"' in result
        assert f'"{TICKET_ID_MERMAID_BEE_B}: Beta Bee"' in result

    def test_title_sanitization_strips_breaking_chars(self):
        """Mermaid-breaking characters are stripped or replaced in node labels."""
        bad_title = '''"quotes" <brackets> pipes|here {braces} (parens) `backticks` #hash semi;colon'''
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title=bad_title)
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Safe", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = _generate_mermaid_graph([a, b])

        assert "graph TD" in result
        # Extract the label portion for bee A's node declaration
        label = ""
        for line in result.splitlines():
            if "b_ma1[" in line:
                label = line
                break
        assert label, "Node declaration for b_ma1 not found in Mermaid output"
        # " replaced by '
        assert "'quotes'" in label
        # All other unsafe chars stripped from label
        for ch in ("<", ">", "|", "{", "}", "(", ")", "`", "#", ";"):
            assert ch not in label


class TestMermaidIntegration:
    """Integration tests for Mermaid dependency graphs within format_index_markdown output."""

    @pytest.fixture(autouse=True)
    def enable_mermaid(self, monkeypatch):
        monkeypatch.setattr("src.config.get_mermaid_charts_enabled", lambda: True)

    def test_bee_deps_graph_before_bee_links(self):
        """Bee-level dep graph appears before the first bee link."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        graph_pos = result.index("graph TD")
        first_link_pos = result.index(f'id="b-ma1"')
        assert graph_pos < first_link_pos

    def test_child_tier_graph_inside_bee_details(self):
        """Child-tier dep graph appears inside parent bee's <details> block."""
        t1_a = make_ticket(id=TICKET_ID_MERMAID_EPIC_A, type="t1", title="Epic A")
        t1_b = make_ticket(
            id=TICKET_ID_MERMAID_EPIC_B, type="t1", title="Epic B",
            up_dependencies=[TICKET_ID_MERMAID_EPIC_A],
        )
        bee = make_ticket(
            id=TICKET_ID_MERMAID_BEE_A, title="Parent Bee",
            children=[TICKET_ID_MERMAID_EPIC_A, TICKET_ID_MERMAID_EPIC_B],
        )
        result = format_index_markdown(
            {"bee": [bee], "t1": [t1_a, t1_b]}, include_timestamp=False,
        )

        # graph TD is inside the bee's <details>, after <summary>
        summary_pos = result.index(f'id="b-ma1"')
        graph_pos = result.index("graph TD")
        close_details = result.index("</details>")
        assert summary_pos < graph_pos < close_details

    def test_no_bee_deps_omits_top_level_graph(self):
        """Two bees with no dep edges produce no Mermaid graph (nothing to visualise)."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B")
        result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        assert "graph TD" not in result

    def test_no_child_deps_omits_child_graph(self):
        """Bee with two children that have no deps omits the Mermaid graph inside the bee section."""
        t1_a = make_ticket(id=TICKET_ID_MERMAID_EPIC_A, type="t1", title="Epic A")
        t1_b = make_ticket(id=TICKET_ID_MERMAID_EPIC_B, type="t1", title="Epic B")
        bee = make_ticket(
            id=TICKET_ID_MERMAID_BEE_A, title="Parent Bee",
            children=[TICKET_ID_MERMAID_EPIC_A, TICKET_ID_MERMAID_EPIC_B],
        )
        result = format_index_markdown(
            {"bee": [bee], "t1": [t1_a, t1_b]}, include_timestamp=False,
        )

        assert "graph TD" not in result
        # But the tickets still appear as leaf links
        assert '<div id="t1-mea-1a"' in result
        assert '<div id="t1-meb-1a"' in result

    def test_no_click_directives_in_full_output(self):
        """No click directives appear anywhere in the rendered output."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        assert 'id="b-ma1"' in result  # <details> anchor still present
        assert "click " not in result

    def test_classdef_declarations_in_generated_graph(self):
        """classDef declarations present in any generated Mermaid block."""
        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A", status="pupa")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        for status in ("larva", "pupa", "worker", "finished"):
            assert f"classDef {status}" in result

    def test_cross_parent_dep_not_rendered_as_sibling_edge(self):
        """Cross-parent dep renders as orphan inside child-tier graph, not a real sibling edge."""
        t1_a = make_ticket(id=TICKET_ID_MERMAID_EPIC_A, type="t1", title="Epic in A")
        t1_b = make_ticket(
            id=TICKET_ID_MERMAID_EPIC_B, type="t1", title="Epic in B",
            up_dependencies=[TICKET_ID_MERMAID_EPIC_A],
        )
        bee_a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A", children=[TICKET_ID_MERMAID_EPIC_A])
        bee_b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B", children=[TICKET_ID_MERMAID_EPIC_B])
        result = format_index_markdown(
            {"bee": [bee_a, bee_b], "t1": [t1_a, t1_b]}, include_timestamp=False,
        )

        # Bee B's <details> contains a child-tier graph for t1_b
        bee_b_summary = f'id="b-mb1"'
        bee_b_start = result.index(bee_b_summary)
        # Find the </details> that closes bee B
        bee_b_end = result.index("</details>", bee_b_start)
        bee_b_block = result[bee_b_start:bee_b_end]

        # Inside bee B's block: t1_b is a single child so no child-tier graph is generated
        assert "graph TD" not in bee_b_block

    def test_graph_generation_exception_shows_fallback(self):
        """Exception in graph generation emits fallback message, ticket links still render."""
        from unittest.mock import patch

        a = make_ticket(id=TICKET_ID_MERMAID_BEE_A, title="Bee A")
        b = make_ticket(id=TICKET_ID_MERMAID_BEE_B, title="Bee B", up_dependencies=[TICKET_ID_MERMAID_BEE_A])
        with patch("src.index_generator._generate_mermaid_graph", side_effect=RuntimeError("boom")):
            result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        assert "*Dependency graph could not be generated*" in result
        assert f'id="b-ma1"' in result  # bee links still rendered
        assert "graph TD" not in result

    def test_circular_dependency_no_infinite_loop(self):
        """Circular deps between two bees render a graph without hanging."""
        a = make_ticket(
            id=TICKET_ID_MERMAID_CIRC_A, title="Circ A",
            up_dependencies=[TICKET_ID_MERMAID_CIRC_B],
        )
        b = make_ticket(
            id=TICKET_ID_MERMAID_CIRC_B, title="Circ B",
            up_dependencies=[TICKET_ID_MERMAID_CIRC_A],
        )
        result = format_index_markdown({"bee": [a, b]}, include_timestamp=False)

        assert "graph TD" in result
        assert "b_ca1" in result
        assert "b_cb1" in result
        assert "-->" in result


# ===========================================================================
# Smoke tests: generate_index succeeds when hive has a corrupt ticket
# ===========================================================================


class TestGenerateIndexWithCorruptTicket:
    """Prove generate_index runs normally on a hive containing a corrupt ticket."""

    async def test_generate_index_single_hive_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """generate_index for a specific hive succeeds even if that hive has a corrupt ticket."""
        from src.mcp_index_ops import _generate_index
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={})

        # Write a valid ticket
        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")

        # Write a corrupt ticket (malformed YAML, missing required fields)
        corrupt_dir = hive_dir / "b.crp"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "b.crp.md").write_text(
            "---\n"
            "id: b.crp\n"
            "type: bee\n"
            "# Missing title, ticket_status, schema_version, guid, egg\n"
            "---\n"
            "Corrupt ticket.\n"
        )

        result = await _generate_index(hive_name="backend")

        assert result["status"] == "success"
        assert result["skipped_hives"] == []
        assert "b.vet" in (hive_dir / "index.md").read_text()

    async def test_generate_index_global_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """Global generate_index indexes all hives including those with corrupt tickets."""
        from src.mcp_index_ops import _generate_index
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={})

        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")

        # Write a corrupt ticket (malformed YAML)
        corrupt_dir = hive_dir / "b.crp"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "b.crp.md").write_text(
            "---\n"
            "id: b.crp\n"
            "type: bee\n"
            "# Missing required fields\n"
            "---\n"
            "Corrupt ticket.\n"
        )

        result = await _generate_index()

        assert result["status"] == "success"
        assert result["skipped_hives"] == []
        assert (hive_dir / "index.md").exists()
