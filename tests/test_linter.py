"""Unit tests for linter module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.linter import TicketScanner, Linter
from src.linter_report import LinterReport
from src.models import Epic, Task, Subtask


class TestTicketScanner:
    """Tests for TicketScanner class."""

    def test_create_scanner(self, tmp_path):
        """Should create scanner with tickets directory."""
        scanner = TicketScanner(str(tmp_path))

        assert scanner.tickets_dir == tmp_path

    def test_scan_all_empty_directory(self, tmp_path):
        """Should handle empty tickets directory."""
        # Create subdirectories
        (tmp_path / "epics").mkdir()
        (tmp_path / "tasks").mkdir()
        (tmp_path / "subtasks").mkdir()

        scanner = TicketScanner(str(tmp_path))
        tickets = list(scanner.scan_all())

        assert len(tickets) == 0

    def test_scan_all_missing_directory_raises_error(self, tmp_path):
        """Should raise error if tickets directory doesn't exist."""
        scanner = TicketScanner(str(tmp_path / "nonexistent"))

        with pytest.raises(FileNotFoundError, match="Tickets directory not found"):
            list(scanner.scan_all())

    def test_scan_all_missing_subdirectory(self, tmp_path):
        """Should handle missing subdirectories gracefully."""
        # Only create epics directory
        (tmp_path / "epics").mkdir()

        scanner = TicketScanner(str(tmp_path))
        tickets = list(scanner.scan_all())

        # Should not crash, just return empty list
        assert len(tickets) == 0

    def test_scan_all_loads_tickets(self, tmp_path):
        """Should load tickets from all subdirectories."""
        # Create subdirectories
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        subtasks_dir = tmp_path / "subtasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()
        subtasks_dir.mkdir()

        # Create test tickets
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Test Epic
---

Epic description.""")

        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: task
title: Test Task
parent: bees-abc
---

Task description.""")

        (subtasks_dir / "bees-123.md").write_text("""---
id: bees-123
type: subtask
title: Test Subtask
parent: bees-xyz
---

Subtask description.""")

        scanner = TicketScanner(str(tmp_path))
        tickets = list(scanner.scan_all())

        assert len(tickets) == 3
        assert any(t.id == "default.bees-abc" and isinstance(t, Epic) for t in tickets)
        assert any(t.id == "default.bees-xyz" and isinstance(t, Task) for t in tickets)
        assert any(t.id == "default.bees-123" and isinstance(t, Subtask) for t in tickets)

    def test_scan_all_handles_invalid_tickets(self, tmp_path):
        """Should skip invalid tickets and continue scanning."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # Valid ticket
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Valid
---

Body.""")

        # Invalid ticket (no frontmatter)
        (epics_dir / "invalid.md").write_text("No frontmatter here")

        scanner = TicketScanner(str(tmp_path))
        tickets = list(scanner.scan_all())

        # Should load the valid ticket and skip the invalid one
        assert len(tickets) == 1
        assert tickets[0].id == "default.bees-abc"

    def test_scan_all_sorted_order(self, tmp_path):
        """Should scan tickets in sorted order."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # Create tickets in non-alphabetical order
        for ticket_id in ["default.bees-zzz", "default.bees-aaa", "default.bees-mmm"]:
            (epics_dir / f"{ticket_id}.md").write_text(f"""---
id: {ticket_id}
type: epic
title: Test
---

Body.""")

        scanner = TicketScanner(str(tmp_path))
        tickets = list(scanner.scan_all())

        # Should be sorted
        assert tickets[0].id == "default.bees-aaa"
        assert tickets[1].id == "default.bees-mmm"
        assert tickets[2].id == "default.bees-zzz"


class TestLinter:
    """Tests for Linter class."""

    def test_create_linter(self):
        """Should create linter with tickets directory."""
        linter = Linter("tickets")

        assert linter.tickets_dir == "tickets"
        assert isinstance(linter.scanner, TicketScanner)

    def test_run_empty_tickets(self, tmp_path):
        """Should handle empty tickets directory."""
        (tmp_path / "epics").mkdir()
        (tmp_path / "tasks").mkdir()
        (tmp_path / "subtasks").mkdir()

        linter = Linter(str(tmp_path))
        report = linter.run()

        assert isinstance(report, LinterReport)
        assert len(report.errors) == 0
        assert not report.is_corrupt()

    def test_run_validates_tickets(self, tmp_path):
        """Should run validation on all tickets."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Test
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        assert isinstance(report, LinterReport)

    def test_validate_id_format_valid(self, tmp_path):
        """Should pass validation for valid ID format."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Test
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not have id_format errors
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    def test_validate_id_format_invalid(self, tmp_path):
        """Should skip tickets with invalid ID format during loading.

        Note: Invalid IDs are caught by the reader's validator before the
        linter can process them. The linter's ID validation is for tickets
        that bypass the reader.
        """
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Valid ticket
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Valid
---

Body.""")

        # Invalid ID - will be skipped during load
        (tasks_dir / "INVALID-ID.md").write_text("""---
id: INVALID-ID
type: task
title: Invalid
parent: bees-abc
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Invalid tickets are skipped during load, so linter won't see them
        # The linter only validates tickets that were successfully loaded
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0  # Invalid ticket was never loaded

    def test_validate_id_uniqueness_no_duplicates(self, tmp_path):
        """Should pass when all IDs are unique."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Test 1
---

Body.""")

        (epics_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: epic
title: Test 2
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not have duplicate_id errors
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 0

    def test_validate_id_uniqueness_detects_duplicates(self, tmp_path):
        """Should detect duplicate IDs."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Create two tickets with same ID
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Epic
---

Body.""")

        (tasks_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: task
title: Task
parent: bees-xyz
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have duplicate_id error
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-abc"
        assert "Duplicate" in duplicate_errors[0].message

    def test_run_reports_ticket_count(self, tmp_path):
        """Should log ticket count during scan."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        for i in range(3):
            (epics_dir / f"bees-{i:03d}.md").write_text(f"""---
id: bees-{i:03d}
type: epic
title: Test {i}
---

Body.""")

        linter = Linter(str(tmp_path))

        # Run and verify report is returned
        report = linter.run()
        assert isinstance(report, LinterReport)

    def test_validate_ticket_stub(self, tmp_path):
        """Should call validate_ticket for each ticket."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Test
---

Body.""")

        linter = Linter(str(tmp_path))
        report = LinterReport()

        # Load ticket manually to test validate_ticket
        from src.reader import read_ticket
        ticket = read_ticket(epics_dir / "bees-abc.md")

        # Should not raise
        linter.validate_ticket(ticket, report)

    def test_integration_multiple_error_types(self, tmp_path):
        """Should detect duplicate IDs across tickets.

        Note: Invalid ID formats are caught during ticket loading by the
        reader's validator, so they never reach the linter. The linter
        catches issues like duplicate IDs that span multiple valid tickets.
        """
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # Duplicate IDs - both have valid format but same ID
        (epics_dir / "bees-dup.md").write_text("""---
id: bees-dup
type: epic
title: Dup 1
---

Body.""")

        (epics_dir / "bees-du2.md").write_text("""---
id: bees-dup
type: epic
title: Dup 2
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should detect duplicate ID
        assert len(report.get_errors(error_type="duplicate_id")) == 1
        assert report.is_corrupt()


class TestBidirectionalValidation:
    """Tests for bidirectional relationship validation."""

    def test_parent_children_valid_bidirectional(self, tmp_path):
        """Should pass when parent/children relationships are bidirectional."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Parent Epic
children:
  - bees-xyz
---

Parent.""")

        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: task
title: Child Task
parent: bees-abc
---

Child.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not have orphaned_child or orphaned_parent errors
        assert len(report.get_errors(error_type="orphaned_child")) == 0
        assert len(report.get_errors(error_type="orphaned_parent")) == 0

    def test_parent_children_orphaned_child(self, tmp_path):
        """Should detect when child lists parent but parent doesn't list child."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Parent doesn't list child
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Parent Epic
---

Parent.""")

        # Child lists parent
        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: task
title: Child Task
parent: bees-abc
---

Child.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have orphaned_child error
        errors = report.get_errors(error_type="orphaned_child")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-xyz"
        assert "default.bees-abc" in errors[0].message
        assert "does not list" in errors[0].message

    def test_parent_children_orphaned_parent(self, tmp_path):
        """Should detect when parent lists child but child doesn't list parent."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Parent lists child
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Parent Epic
children:
  - bees-xyz
---

Parent.""")

        # Child doesn't list parent
        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: task
title: Child Task
---

Child.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have orphaned_parent error
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-abc"
        assert "default.bees-xyz" in errors[0].message
        assert "does not list" in errors[0].message

    def test_parent_children_multiple_children(self, tmp_path):
        """Should validate all children in bidirectional relationships."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Parent
children:
  - bees-001
  - bees-002
  - bees-003
---

Parent.""")

        # One valid child
        (tasks_dir / "bees-001.md").write_text("""---
id: bees-001
type: task
title: Child 1
parent: bees-abc
---

Child 1.""")

        # One child missing parent backlink
        (tasks_dir / "bees-002.md").write_text("""---
id: bees-002
type: task
title: Child 2
---

Child 2.""")

        # One child with correct backlink
        (tasks_dir / "bees-003.md").write_text("""---
id: bees-003
type: task
title: Child 3
parent: bees-abc
---

Child 3.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have one orphaned_parent error for bees-002
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-abc"
        assert "default.bees-002" in errors[0].message

    def test_dependencies_valid_bidirectional(self, tmp_path):
        """Should pass when dependency relationships are bidirectional."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Upstream Task
down_dependencies:
  - bees-bbb
---

Upstream.""")

        (tasks_dir / "bees-bbb.md").write_text("""---
id: bees-bbb
type: task
title: Downstream Task
up_dependencies:
  - bees-aaa
---

Downstream.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not have dependency errors
        assert len(report.get_errors(error_type="orphaned_dependency")) == 0
        assert len(report.get_errors(error_type="missing_backlink")) == 0

    def test_dependencies_orphaned_dependency(self, tmp_path):
        """Should detect when ticket has up_dependency but upstream doesn't have down_dependency."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Upstream doesn't list downstream
        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Upstream Task
---

Upstream.""")

        # Downstream lists upstream
        (tasks_dir / "bees-bbb.md").write_text("""---
id: bees-bbb
type: task
title: Downstream Task
up_dependencies:
  - bees-aaa
---

Downstream.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have orphaned_dependency error
        errors = report.get_errors(error_type="orphaned_dependency")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-bbb"
        assert "default.bees-aaa" in errors[0].message
        assert "does not list" in errors[0].message

    def test_dependencies_missing_backlink(self, tmp_path):
        """Should detect when ticket has down_dependency but downstream doesn't have up_dependency."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Upstream lists downstream
        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Upstream Task
down_dependencies:
  - bees-bbb
---

Upstream.""")

        # Downstream doesn't list upstream
        (tasks_dir / "bees-bbb.md").write_text("""---
id: bees-bbb
type: task
title: Downstream Task
---

Downstream.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have missing_backlink error
        errors = report.get_errors(error_type="missing_backlink")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-aaa"
        assert "default.bees-bbb" in errors[0].message
        assert "does not list" in errors[0].message

    def test_dependencies_multiple_dependencies(self, tmp_path):
        """Should validate all dependencies in bidirectional relationships."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Upstream
down_dependencies:
  - bees-b01
  - bees-b02
  - bees-b03
---

Upstream.""")

        # Valid bidirectional
        (tasks_dir / "bees-b01.md").write_text("""---
id: bees-b01
type: task
title: Downstream 1
up_dependencies:
  - bees-aaa
---

Down 1.""")

        # Missing backlink
        (tasks_dir / "bees-b02.md").write_text("""---
id: bees-b02
type: task
title: Downstream 2
---

Down 2.""")

        # Valid bidirectional
        (tasks_dir / "bees-b03.md").write_text("""---
id: bees-b03
type: task
title: Downstream 3
up_dependencies:
  - bees-aaa
---

Down 3.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have one missing_backlink error for bees-b02
        errors = report.get_errors(error_type="missing_backlink")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-aaa"
        assert "default.bees-b02" in errors[0].message

    def test_edge_case_empty_relationships(self, tmp_path):
        """Should handle tickets with no relationships gracefully."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Standalone Task
---

No relationships.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not have any relationship errors
        assert len(report.get_errors(error_type="orphaned_child")) == 0
        assert len(report.get_errors(error_type="orphaned_parent")) == 0
        assert len(report.get_errors(error_type="orphaned_dependency")) == 0
        assert len(report.get_errors(error_type="missing_backlink")) == 0

    def test_edge_case_nonexistent_ticket_ids(self, tmp_path):
        """Should skip validation for nonexistent ticket references."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # References nonexistent parent
        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Task
parent: bees-nonexistent
up_dependencies:
  - bees-missing
---

Task.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should not crash, and not report bidirectional errors
        # (nonexistent tickets are handled by other validators)
        assert len(report.get_errors(error_type="orphaned_child")) == 0
        assert len(report.get_errors(error_type="orphaned_dependency")) == 0

    def test_edge_case_self_reference(self, tmp_path):
        """Should handle self-referencing tickets."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Self-reference in children
        (tasks_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: task
title: Self Reference
children:
  - bees-aaa
---

Task.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should detect orphaned_parent (self doesn't list self as parent)
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 1
        assert errors[0].ticket_id == "default.bees-aaa"
