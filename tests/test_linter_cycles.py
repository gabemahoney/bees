"""Unit tests for cycle detection in the linter.

Tests cycle detection for both blocking dependencies and hierarchical (parent/child)
relationships, including various cycle configurations and edge cases.
"""

import pytest
from src.linter import Linter
from src.models import Ticket


class TestCycleDetection:
    """Test suite for cycle detection functionality."""

    def test_blocking_3_node_cycle(self, tmp_path):
        """Test detection of 3-node cycle in blocking dependencies (A->B->C->A)."""
        # Setup tickets directory
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create 3-node blocking dependency cycle
        ticket_a = Ticket(
            id="default.bees-aa1",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-cc1"],  # A depends on C
            down_dependencies=["default.bees-bb1"]  # B depends on A
        )
        ticket_b = Ticket(
            id="default.bees-bb1",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-aa1"],  # B depends on A
            down_dependencies=["default.bees-cc1"]  # C depends on B
        )
        ticket_c = Ticket(
            id="default.bees-cc1",
            type="task",
            title="Task C",
            up_dependencies=["default.bees-bb1"],  # C depends on B
            down_dependencies=["default.bees-aa1"]  # A depends on C
        )

        # Write tickets
        self._write_ticket(tickets_dir / "tasks" / "bees-aa1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-bb1.md", ticket_b)
        self._write_ticket(tickets_dir / "tasks" / "bees-cc1.md", ticket_c)

        # Run linter
        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        # Should detect cycle
        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) >= 1, "Should detect at least one cycle"

        # Check cycle path is in error message
        error_msg = cycle_errors[0].message
        assert "default.bees-aa1" in error_msg
        assert "default.bees-bb1" in error_msg
        assert "default.bees-cc1" in error_msg
        assert "Cycle detected" in error_msg

    def test_blocking_2_node_cycle(self, tmp_path):
        """Test detection of 2-node cycle in blocking dependencies (A->B->A)."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create 2-node blocking dependency cycle
        ticket_a = Ticket(
            id="default.bees-aa2",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-bb2"],  # A depends on B
            down_dependencies=["default.bees-bb2"]  # B depends on A
        )
        ticket_b = Ticket(
            id="default.bees-bb2",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-aa2"],  # B depends on A
            down_dependencies=["default.bees-aa2"]  # A depends on B
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-aa2.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-bb2.md", ticket_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) >= 1, "Should detect 2-node cycle"

    def test_blocking_self_cycle(self, tmp_path):
        """Test detection of self-cycle in blocking dependencies (A->A)."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create self-cycle
        ticket_a = Ticket(
            id="default.bees-aa3",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-aa3"],  # A depends on itself
            down_dependencies=["default.bees-aa3"]  # A blocks itself
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-aa3.md", ticket_a)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) >= 1, "Should detect self-cycle"

    def test_hierarchical_3_node_cycle(self, tmp_path):
        """Test detection of 3-node cycle in parent/child hierarchy."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        # Create 3-node hierarchy cycle (Epic->Task->Subtask->Epic)
        # This shouldn't happen in practice, but we should detect it
        epic = Ticket(
            id="default.bees-ep1",
            type="epic",
            title="Epic A",
            parent="default.bees-st1",  # Epic's parent is Subtask (cycle!)
            children=["default.bees-tk1"]
        )
        task = Ticket(
            id="default.bees-tk1",
            type="task",
            title="Task B",
            parent="default.bees-ep1",
            children=["default.bees-st1"]
        )
        subtask = Ticket(
            id="default.bees-st1",
            type="subtask",
            title="Subtask C",
            parent="default.bees-tk1",
            children=["default.bees-ep1"]
        )

        self._write_ticket(tickets_dir / "epics" / "bees-ep1.md", epic)
        self._write_ticket(tickets_dir / "tasks" / "bees-tk1.md", task)
        self._write_ticket(tickets_dir / "subtasks" / "bees-st1.md", subtask)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) >= 1, "Should detect hierarchy cycle"

    def test_hierarchical_2_node_cycle(self, tmp_path):
        """Test detection of 2-node cycle in parent/child hierarchy."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create 2-node hierarchy cycle
        task_a = Ticket(
            id="default.bees-ta1",
            type="task",
            title="Task A",
            parent="default.bees-tb1",
            children=["default.bees-tb1"]
        )
        task_b = Ticket(
            id="default.bees-tb1",
            type="task",
            title="Task B",
            parent="default.bees-ta1",
            children=["default.bees-ta1"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-ta1.md", task_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-tb1.md", task_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) >= 1, "Should detect 2-node hierarchy cycle"

    def test_hierarchical_self_cycle(self, tmp_path):
        """Test detection of self-cycle in parent/child hierarchy."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create self-cycle in hierarchy
        task = Ticket(
            id="default.bees-ts1",
            type="task",
            title="Task Self",
            parent="default.bees-ts1",
            children=["default.bees-ts1"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-ts1.md", task)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) >= 1, "Should detect self-cycle in hierarchy"

    def test_acyclic_blocking_graph(self, tmp_path):
        """Test that acyclic blocking dependency graph passes without errors."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create acyclic dependency chain: A -> B -> C
        ticket_a = Ticket(
            id="default.bees-ac1",
            type="task",
            title="Task A",
            up_dependencies=[],
            down_dependencies=["default.bees-bc1"]
        )
        ticket_b = Ticket(
            id="default.bees-bc1",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-ac1"],
            down_dependencies=["default.bees-cc2"]
        )
        ticket_c = Ticket(
            id="default.bees-cc2",
            type="task",
            title="Task C",
            up_dependencies=["default.bees-bc1"],
            down_dependencies=[]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-ac1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-bc1.md", ticket_b)
        self._write_ticket(tickets_dir / "tasks" / "bees-cc2.md", ticket_c)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) == 0, "Acyclic graph should not report cycles"

    def test_acyclic_hierarchy(self, tmp_path):
        """Test that acyclic parent/child hierarchy passes without errors."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        # Create acyclic hierarchy: Epic -> Task -> Subtask
        epic = Ticket(
            id="default.bees-ae1",
            type="epic",
            title="Epic A",
            parent=None,
            children=["default.bees-at1"]
        )
        task = Ticket(
            id="default.bees-at1",
            type="task",
            title="Task A",
            parent="default.bees-ae1",
            children=["default.bees-as1"]
        )
        subtask = Ticket(
            id="default.bees-as1",
            type="subtask",
            title="Subtask A",
            parent="default.bees-at1",
            children=[]
        )

        self._write_ticket(tickets_dir / "epics" / "bees-ae1.md", epic)
        self._write_ticket(tickets_dir / "tasks" / "bees-at1.md", task)
        self._write_ticket(tickets_dir / "subtasks" / "bees-as1.md", subtask)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) == 0, "Acyclic hierarchy should not report cycles"

    def test_nested_cycles(self, tmp_path):
        """Test detection of nested/multiple independent cycles."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create two independent cycles: (A->B->A) and (C->D->C)
        ticket_a = Ticket(
            id="default.bees-na1",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-nb1"],
            down_dependencies=["default.bees-nb1"]
        )
        ticket_b = Ticket(
            id="default.bees-nb1",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-na1"],
            down_dependencies=["default.bees-na1"]
        )
        ticket_c = Ticket(
            id="default.bees-nc1",
            type="task",
            title="Task C",
            up_dependencies=["default.bees-nd1"],
            down_dependencies=["default.bees-nd1"]
        )
        ticket_d = Ticket(
            id="default.bees-nd1",
            type="task",
            title="Task D",
            up_dependencies=["default.bees-nc1"],
            down_dependencies=["default.bees-nc1"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-na1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-nb1.md", ticket_b)
        self._write_ticket(tickets_dir / "tasks" / "bees-nc1.md", ticket_c)
        self._write_ticket(tickets_dir / "tasks" / "bees-nd1.md", ticket_d)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        # Should detect both cycles
        assert len(cycle_errors) >= 2, "Should detect both independent cycles"

    def test_empty_graph(self, tmp_path):
        """Test cycle detection on empty ticket database."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        hierarchy_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) == 0, "Empty graph should have no cycles"
        assert len(hierarchy_errors) == 0, "Empty graph should have no hierarchy cycles"

    def test_single_node(self, tmp_path):
        """Test cycle detection on single ticket with no dependencies."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        ticket = Ticket(
            id="default.bees-sn1",
            type="task",
            title="Single Task",
            up_dependencies=[],
            down_dependencies=[],
            parent=None,
            children=[]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-sn1.md", ticket)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        hierarchy_errors = report.get_errors(error_type="hierarchy_cycle")
        assert len(cycle_errors) == 0, "Single node should have no cycles"
        assert len(hierarchy_errors) == 0, "Single node should have no hierarchy cycles"

    def test_disconnected_components(self, tmp_path):
        """Test cycle detection on graph with disconnected components."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Component 1: A -> B (acyclic)
        ticket_a = Ticket(
            id="default.bees-dc1",
            type="task",
            title="Task A",
            up_dependencies=[],
            down_dependencies=["default.bees-db1"]
        )
        ticket_b = Ticket(
            id="default.bees-db1",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-dc1"],
            down_dependencies=[]
        )

        # Component 2: C -> D -> C (cycle)
        ticket_c = Ticket(
            id="default.bees-dc2",
            type="task",
            title="Task C",
            up_dependencies=["default.bees-dd1"],
            down_dependencies=["default.bees-dd1"]
        )
        ticket_d = Ticket(
            id="default.bees-dd1",
            type="task",
            title="Task D",
            up_dependencies=["default.bees-dc2"],
            down_dependencies=["default.bees-dc2"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-dc1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-db1.md", ticket_b)
        self._write_ticket(tickets_dir / "tasks" / "bees-dc2.md", ticket_c)
        self._write_ticket(tickets_dir / "tasks" / "bees-dd1.md", ticket_d)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        # Should detect cycle in component 2, but not in component 1
        assert len(cycle_errors) >= 1, "Should detect cycle in disconnected component"

    def test_mixed_blocking_parent_cycles(self, tmp_path):
        """Test that blocking and parent cycles are detected independently."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create blocking cycle: A -> B -> A
        # AND parent cycle: A is parent of B, B is parent of A
        ticket_a = Ticket(
            id="default.bees-ma1",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-mb1"],
            down_dependencies=["default.bees-mb1"],
            parent="default.bees-mb1",
            children=["default.bees-mb1"]
        )
        ticket_b = Ticket(
            id="default.bees-mb1",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-ma1"],
            down_dependencies=["default.bees-ma1"],
            parent="default.bees-ma1",
            children=["default.bees-ma1"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-ma1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-mb1.md", ticket_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        blocking_errors = report.get_errors(error_type="dependency_cycle")
        hierarchy_errors = report.get_errors(error_type="hierarchy_cycle")

        # Should detect both types of cycles
        assert len(blocking_errors) >= 1, "Should detect blocking cycle"
        assert len(hierarchy_errors) >= 1, "Should detect hierarchy cycle"

    def test_cycle_error_message_format(self, tmp_path):
        """Test that cycle error messages include proper cycle paths."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "tasks").mkdir()

        # Create simple cycle A -> B -> A
        ticket_a = Ticket(
            id="default.bees-em1",
            type="task",
            title="Task A",
            up_dependencies=["default.bees-em2"],
            down_dependencies=["default.bees-em2"]
        )
        ticket_b = Ticket(
            id="default.bees-em2",
            type="task",
            title="Task B",
            up_dependencies=["default.bees-em1"],
            down_dependencies=["default.bees-em1"]
        )

        self._write_ticket(tickets_dir / "tasks" / "bees-em1.md", ticket_a)
        self._write_ticket(tickets_dir / "tasks" / "bees-em2.md", ticket_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) >= 1

        error_msg = cycle_errors[0].message
        # Check format includes cycle path with arrow notation
        assert "->" in error_msg, "Error message should include -> notation"
        assert "Cycle detected" in error_msg, "Error should indicate cycle was detected"
        assert "default.bees-em1" in error_msg and "default.bees-em2" in error_msg, "Should include both ticket IDs"

    def _write_ticket(self, path, ticket):
        """Helper to write a ticket to a markdown file with YAML frontmatter."""
        lines = [
            "---\n",
            f"id: {ticket.id}\n",
            f"type: {ticket.type}\n",
            f"title: {ticket.title}\n",
        ]

        if ticket.parent:
            lines.append(f"parent: {ticket.parent}\n")

        if ticket.children:
            lines.append("children:\n")
            for child_id in ticket.children:
                lines.append(f"  - {child_id}\n")

        if ticket.up_dependencies:
            lines.append("up_dependencies:\n")
            for dep_id in ticket.up_dependencies:
                lines.append(f"  - {dep_id}\n")

        if ticket.down_dependencies:
            lines.append("down_dependencies:\n")
            for dep_id in ticket.down_dependencies:
                lines.append(f"  - {dep_id}\n")

        lines.append("---\n")
        lines.append("\n")
        lines.append(f"Description for {ticket.title}\n")

        path.write_text("".join(lines))
