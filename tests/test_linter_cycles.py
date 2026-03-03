"""
Unit tests for dependency cycle detection in linter.

PURPOSE:
Tests the linter's ability to detect circular dependencies in both blocking
dependencies (up/down) and hierarchical relationships (parent/child).

SCOPE - Tests that belong here:
- detect_cycles(): Cycle detection algorithm
- Direct cycles (A->B->A)
- Transitive cycles (A->B->C->A)
- Self-referencing cycles (A->A)
- Cycle detection in up_dependencies/down_dependencies
- Cycle detection in parent/children relationships
- Complex multi-path cycles
- Edge cases: empty graphs, single nodes, disconnected components

SCOPE - Tests that DON'T belong here:
- General linter engine -> test_linter.py
- Other validation rules -> test_linter.py, test_validation_*.py
- Hive-specific validation -> test_linter_hive_validation.py
- Tier hierarchy validation -> test_linter_tier_validation.py
- Report formatting -> test_linter_report.py

RELATED FILES:
- test_linter.py: Main linter engine and general validation
- test_mcp_relationships.py: Relationship CRUD (preventing cycles at creation)
"""

import pytest

from src.linter import Linter
from src.models import Ticket


class TestCycleDetection:
    """Test suite for cycle detection functionality."""

    @pytest.mark.parametrize(
        "cycle_type,node_count,expected_error_type",
        [
            ("blocking", 1, "dependency_cycle"),
            ("blocking", 2, "dependency_cycle"),
            ("blocking", 3, "dependency_cycle"),
            ("hierarchical", 1, "hierarchy_cycle"),
            ("hierarchical", 2, "hierarchy_cycle"),
            ("hierarchical", 3, "hierarchy_cycle"),
        ],
    )
    def test_cycle_detection(self, cycle_type, node_count, expected_error_type, tmp_path):
        """Test detection of cycles in blocking dependencies and hierarchical relationships."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        tickets = []
        node_ids = [f"t1.cy{i}{node_count}x" for i in range(node_count)]

        if cycle_type == "blocking":
            for i in range(node_count):
                next_i = (i + 1) % node_count
                prev_i = (i - 1) % node_count
                ticket = Ticket(
                    id=node_ids[i], type="t1", title=f"Task {chr(65 + i)}",
                    up_dependencies=[node_ids[next_i]], down_dependencies=[node_ids[prev_i]],
                )
                tickets.append(ticket)
        elif cycle_type == "hierarchical":
            for i in range(node_count):
                next_i = (i + 1) % node_count
                prev_i = (i - 1) % node_count
                ticket = Ticket(
                    id=node_ids[i], type="t1", title=f"Task {chr(65 + i)}",
                    parent=node_ids[next_i], children=[node_ids[prev_i]],
                )
                tickets.append(ticket)

        for ticket in tickets:
            self._write_ticket(tickets_dir, ticket)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type=expected_error_type)
        assert len(cycle_errors) >= 1, f"Should detect {cycle_type} cycle with {node_count} nodes"
        error_msg = cycle_errors[0].message
        assert "Cycle detected" in error_msg or "cycle" in error_msg.lower()

    def test_nested_cycles(self, tmp_path):
        """Test detection of nested/multiple independent cycles."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        # Two independent cycles: (A->B->A) and (C->D->C)
        tickets = [
            Ticket(id="t1.nca1", type="t1", title="Task A",
                   up_dependencies=["t1.ncb1"], down_dependencies=["t1.ncb1"]),
            Ticket(id="t1.ncb1", type="t1", title="Task B",
                   up_dependencies=["t1.nca1"], down_dependencies=["t1.nca1"]),
            Ticket(id="t1.ncc1", type="t1", title="Task C",
                   up_dependencies=["t1.ncd1"], down_dependencies=["t1.ncd1"]),
            Ticket(id="t1.ncd1", type="t1", title="Task D",
                   up_dependencies=["t1.ncc1"], down_dependencies=["t1.ncc1"]),
        ]

        for ticket in tickets:
            self._write_ticket(tickets_dir, ticket)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        assert len(report.get_errors(error_type="dependency_cycle")) >= 2

    def test_mixed_blocking_parent_cycles(self, tmp_path):
        """Test that blocking and parent cycles are detected independently."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        ticket_a = Ticket(
            id="t1.mxa1", type="t1", title="Task A",
            up_dependencies=["t1.mxb1"], down_dependencies=["t1.mxb1"],
            parent="t1.mxb1", children=["t1.mxb1"],
        )
        ticket_b = Ticket(
            id="t1.mxb1", type="t1", title="Task B",
            up_dependencies=["t1.mxa1"], down_dependencies=["t1.mxa1"],
            parent="t1.mxa1", children=["t1.mxa1"],
        )

        self._write_ticket(tickets_dir, ticket_a)
        self._write_ticket(tickets_dir, ticket_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        assert len(report.get_errors(error_type="dependency_cycle")) >= 1
        assert len(report.get_errors(error_type="hierarchy_cycle")) >= 1

    def test_cycle_error_message_format(self, tmp_path):
        """Test that cycle error messages include proper cycle paths."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        ticket_a = Ticket(
            id="t1.ema1", type="t1", title="Task A",
            up_dependencies=["t1.emb1"], down_dependencies=["t1.emb1"],
        )
        ticket_b = Ticket(
            id="t1.emb1", type="t1", title="Task B",
            up_dependencies=["t1.ema1"], down_dependencies=["t1.ema1"],
        )

        self._write_ticket(tickets_dir, ticket_a)
        self._write_ticket(tickets_dir, ticket_b)

        linter = Linter(tickets_dir=str(tickets_dir))
        report = linter.run()

        cycle_errors = report.get_errors(error_type="dependency_cycle")
        assert len(cycle_errors) >= 1

        error_msg = cycle_errors[0].message
        assert "->" in error_msg
        assert "Cycle detected" in error_msg
        assert "t1.ema1" in error_msg and "t1.emb1" in error_msg

    def _write_ticket(self, base_dir, ticket):
        """Helper to write a ticket to hierarchical storage: {base_dir}/{ticket_id}/{ticket_id}.md"""
        lines = [
            "---\n",
            "schema_version: '1.1'\n",
            f"id: {ticket.id}\n",
            f"type: {ticket.type}\n",
            f"title: {ticket.title}\n",
            "status: open\n",
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

        # Use hierarchical structure: {base_dir}/{ticket_id}/{ticket_id}.md
        ticket_dir = base_dir / ticket.id
        ticket_dir.mkdir(parents=True, exist_ok=True)
        ticket_file = ticket_dir / f"{ticket.id}.md"
        ticket_file.write_text("".join(lines))
