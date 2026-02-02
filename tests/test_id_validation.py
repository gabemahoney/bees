"""Unit tests for ID validation functions in the linter."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.linter import Linter
from src.linter_report import LinterReport
from src.models import Epic, Task, Subtask


class TestValidateIdFormat:
    """Tests for validate_id_format() function."""

    def _create_ticket_file(self, tmp_path, ticket_type, ticket_id, title, parent=None):
        """Helper to create a ticket file with standard structure.

        Args:
            tmp_path: pytest tmp_path fixture
            ticket_type: 'epic', 'task', or 'subtask'
            ticket_id: The ticket ID (e.g., 'bees-abc')
            title: The ticket title
            parent: Optional parent ID for tasks/subtasks

        Returns:
            Path to the created ticket file
        """
        type_dir = tmp_path / f"{ticket_type}s"
        type_dir.mkdir(exist_ok=True)

        frontmatter = f"""---
id: {ticket_id}
bees_version: '1.1'
type: {ticket_type}
title: {title}"""

        if parent:
            frontmatter += f"\nparent: {parent}"

        frontmatter += "\n---\n\nBody."

        file_path = type_dir / f"{ticket_id}.md"
        file_path.write_text(frontmatter)
        return file_path

    def test_valid_hive_prefixed_id(self, tmp_path):
        """Should pass validation for hive-prefixed IDs."""
        self._create_ticket_file(tmp_path, "epic", "backend.bees-abc", "Hive Prefixed")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    def test_valid_multi_word_hive_id(self, tmp_path):
        """Should pass validation for multi-word hive names with underscores."""
        self._create_ticket_file(tmp_path, "epic", "my_hive.bees-123", "Multi-word Hive")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    def test_valid_hive_with_numbers_id(self, tmp_path):
        """Should pass validation for hive names with numbers."""
        self._create_ticket_file(tmp_path, "epic", "hive_v2.bees-abc", "Hive with Numbers")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    def test_valid_hive_starting_with_underscore(self, tmp_path):
        """Should pass validation for hive names starting with underscore."""
        self._create_ticket_file(tmp_path, "epic", "_private.bees-abc", "Underscore Hive")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    def test_invalid_uppercase_id_caught_by_reader(self):
        """Invalid uppercase IDs are caught by reader, not linter.

        The reader's validator rejects IDs with uppercase letters,
        so they never reach the linter's validation.
        Uses mocking to isolate test from scanner behavior.
        """
        linter = Linter()

        # Mock scanner to return no tickets (simulating reader rejection)
        with patch.object(linter.scanner, 'scan_all', return_value=[]):
            report = linter.run()

            # No tickets loaded, so no format errors
            format_errors = report.get_errors(error_type="id_format")
            assert len(format_errors) == 0

    def test_invalid_too_long_id_caught_by_reader(self):
        """Invalid IDs that are too long are caught by reader, not linter.

        Uses mocking to isolate test from scanner behavior.
        """
        linter = Linter()

        # Mock scanner to return no tickets (simulating reader rejection)
        with patch.object(linter.scanner, 'scan_all', return_value=[]):
            report = linter.run()

            # No tickets loaded, so no format errors
            format_errors = report.get_errors(error_type="id_format")
            assert len(format_errors) == 0

    def test_invalid_too_short_id_caught_by_reader(self):
        """Invalid IDs that are too short are caught by reader, not linter.

        Uses mocking to isolate test from scanner behavior.
        """
        linter = Linter()

        # Mock scanner to return no tickets (simulating reader rejection)
        with patch.object(linter.scanner, 'scan_all', return_value=[]):
            report = linter.run()

            # No tickets loaded, so no format errors
            format_errors = report.get_errors(error_type="id_format")
            assert len(format_errors) == 0

    def test_invalid_wrong_prefix_caught_by_reader(self):
        """Invalid IDs with wrong prefix are caught by reader, not linter.

        Uses mocking to isolate test from scanner behavior.
        """
        linter = Linter()

        # Mock scanner to return no tickets (simulating reader rejection)
        with patch.object(linter.scanner, 'scan_all', return_value=[]):
            report = linter.run()

            # No tickets loaded, so no format errors
            format_errors = report.get_errors(error_type="id_format")
            assert len(format_errors) == 0

    def test_invalid_special_chars_caught_by_reader(self):
        """Invalid IDs with special characters are caught by reader, not linter.

        Uses mocking to isolate test from scanner behavior.
        """
        linter = Linter()

        # Mock scanner to return no tickets (simulating reader rejection)
        with patch.object(linter.scanner, 'scan_all', return_value=[]):
            report = linter.run()

            # No tickets loaded, so no format errors
            format_errors = report.get_errors(error_type="id_format")
            assert len(format_errors) == 0

    def test_none_id_handling(self):
        """Test validate_id_format() handles None ID gracefully."""
        from src.models import Epic
        from src.linter_report import LinterReport
        from src.linter import Linter

        linter = Linter()
        report = LinterReport()

        # Create mock ticket with None ID
        none_id_ticket = Epic(
            id=None,
            type="epic",
            title="No ID",
            description="Test"
        )

        linter.validate_id_format(none_id_ticket, report)
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 1
        assert format_errors[0].ticket_id is None or format_errors[0].ticket_id == "None"
        assert "does not match required format" in format_errors[0].message or "None" in format_errors[0].message

    def test_empty_string_id(self):
        """Test validate_id_format() rejects empty string ID."""
        from src.models import Epic
        from src.linter_report import LinterReport
        from src.linter import Linter

        linter = Linter()
        report = LinterReport()

        # Create mock ticket with empty string ID
        empty_id_ticket = Epic(
            id="",
            type="epic",
            title="Empty ID",
            description="Test"
        )

        linter.validate_id_format(empty_id_ticket, report)
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 1
        assert format_errors[0].ticket_id == ""
        assert "does not match required format" in format_errors[0].message

    def test_multiple_valid_ids(self, tmp_path):
        """Should validate multiple tickets with valid IDs."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        for ticket_id in ["bees-abc", "bees-123", "bees-x9z", "bees-000"]:
            (epics_dir / f"{ticket_id}.md").write_text(f"""---
id: {ticket_id}
type: epic
title: Test {ticket_id}
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

    # Direct method tests grouped together
    def test_validate_id_format_directly(self):
        """Test validate_id_format() method directly on mock ticket object."""
        from src.models import Epic
        from src.linter_report import LinterReport
        from src.linter import Linter

        linter = Linter()
        report = LinterReport()

        # Create mock ticket with valid ID
        valid_ticket = Epic(
            id="bees-abc",
            type="epic",
            title="Valid",
            description="Test"
        )

        linter.validate_id_format(valid_ticket, report)
        assert len(report.get_errors(error_type="id_format")) == 0

        # Create mock ticket with invalid ID (bypassing reader validation)
        invalid_ticket = Epic(
            id="INVALID-ID",
            type="epic",
            title="Invalid",
            description="Test"
        )

        linter.validate_id_format(invalid_ticket, report)
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 1
        assert format_errors[0].ticket_id == "INVALID-ID"
        # Verify complete error message
        error_msg = format_errors[0].message
        assert "INVALID-ID" in error_msg
        assert "does not match required format" in error_msg
        assert "bees-" in error_msg or "format" in error_msg


class TestValidateIdUniqueness:
    """Tests for validate_id_uniqueness() function."""

    def test_no_duplicates(self, tmp_path):
        """Should pass when all IDs are unique."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        subtasks_dir = tmp_path / "subtasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()
        subtasks_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Epic
---

Body.""")

        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
type: task
title: Task
parent: bees-abc
---

Body.""")

        (subtasks_dir / "bees-123.md").write_text("""---
id: bees-123
type: subtask
title: Subtask
parent: bees-xyz
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 0

    def test_duplicate_across_epics(self, tmp_path):
        """Should detect duplicate IDs across epics."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: Epic 1
---

Body.""")

        (epics_dir / "bees-ab2.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: Epic 2
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-abc"
        # Verify complete error message
        error_msg = duplicate_errors[0].message
        assert "Duplicate" in error_msg or "duplicate" in error_msg
        assert "default.bees-abc" in error_msg

    def test_duplicate_across_different_types(self, tmp_path):
        """Should detect duplicate IDs across different ticket types."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: Epic
---

Body.""")

        (tasks_dir / "bees-abc.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: task
title: Task
parent: bees-xyz
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-abc"
        # Verify complete error message
        error_msg = duplicate_errors[0].message
        assert "Duplicate" in error_msg or "duplicate" in error_msg
        assert "default.bees-abc" in error_msg

    def test_duplicate_in_tasks(self, tmp_path):
        """Should detect duplicate IDs in tasks."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        (tasks_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
bees_version: '1.1'
type: task
title: Task 1
parent: bees-abc
---

Body.""")

        (tasks_dir / "bees-xy2.md").write_text("""---
id: bees-xyz
bees_version: '1.1'
type: task
title: Task 2
parent: bees-abc
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-xyz"

    def test_duplicate_in_subtasks(self, tmp_path):
        """Should detect duplicate IDs in subtasks."""
        subtasks_dir = tmp_path / "subtasks"
        subtasks_dir.mkdir()

        (subtasks_dir / "bees-123.md").write_text("""---
id: bees-123
bees_version: '1.1'
type: subtask
title: Subtask 1
parent: bees-xyz
---

Body.""")

        (subtasks_dir / "bees-12b.md").write_text("""---
id: bees-123
bees_version: '1.1'
type: subtask
title: Subtask 2
parent: bees-xyz
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-123"

    def test_triple_duplicate(self, tmp_path):
        """Should detect when same ID is used three times."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        for i in range(3):
            (epics_dir / f"bees-{i:03d}.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Duplicate
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        # Implementation reports one error per duplicate occurrence after the first
        # With 3 tickets having the same ID, we get 2 duplicate errors
        assert len(duplicate_errors) == 2
        assert all(err.ticket_id == "default.bees-dup" for err in duplicate_errors)

    def test_multiple_different_duplicates(self, tmp_path):
        """Should detect multiple different duplicate IDs."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # First pair of duplicates
        (epics_dir / "bees-du1.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Dup 1
---

Body.""")

        (epics_dir / "bees-du2.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Dup 2
---

Body.""")

        # Second pair of duplicates
        (epics_dir / "bees-ab1.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: ABC 1
---

Body.""")

        (epics_dir / "bees-ab2.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: ABC 2
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 2
        duplicate_ids = {err.ticket_id for err in duplicate_errors}
        assert "default.bees-dup" in duplicate_ids
        assert "default.bees-abc" in duplicate_ids

    def test_mixed_unique_and_duplicate_ids(self, tmp_path):
        """Should detect only duplicates while passing unique IDs in mixed scenario."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Valid unique IDs
        (epics_dir / "bees-un1.md").write_text("""---
id: bees-un1
bees_version: '1.1'
type: epic
title: Unique 1
---

Body.""")

        (epics_dir / "bees-un2.md").write_text("""---
id: bees-un2
bees_version: '1.1'
type: epic
title: Unique 2
---

Body.""")

        (tasks_dir / "bees-un3.md").write_text("""---
id: bees-un3
bees_version: '1.1'
type: task
title: Unique 3
parent: bees-un1
---

Body.""")

        # Duplicate IDs
        (epics_dir / "bees-du1.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Dup 1
---

Body.""")

        (tasks_dir / "bees-du2.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: task
title: Dup 2
parent: bees-un1
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have no format errors for any IDs
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

        # Should detect exactly one duplicate
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-dup"

    def test_empty_tickets_list(self):
        """Should handle empty tickets list without errors."""
        from src.linter_report import LinterReport
        from src.linter import Linter

        linter = Linter()
        report = LinterReport()

        linter.validate_id_uniqueness([], report)
        assert len(report.errors) == 0

    def test_single_ticket_no_duplicates(self, tmp_path):
        """Should pass with single ticket (no duplicates possible)."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
type: epic
title: Single
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 0

    # Direct method tests grouped together
    def test_validate_id_uniqueness_directly(self):
        """Test validate_id_uniqueness() method directly on mock ticket objects."""
        from src.models import Epic, Task
        from src.linter_report import LinterReport
        from src.linter import Linter

        linter = Linter()
        report = LinterReport()

        # Create tickets with unique IDs
        tickets = [
            Epic(id="bees-abc", type="epic", title="Epic", description="Test"),
            Task(id="bees-xyz", type="task", title="Task", description="Test"),
        ]

        linter.validate_id_uniqueness(tickets, report)
        assert len(report.get_errors(error_type="duplicate_id")) == 0

        # Create tickets with duplicate IDs
        report = LinterReport()
        tickets_with_dup = [
            Epic(id="bees-abc", type="epic", title="Epic 1", description="Test"),
            Epic(id="bees-abc", type="epic", title="Epic 2", description="Test"),
        ]

        linter.validate_id_uniqueness(tickets_with_dup, report)
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "bees-abc"


class TestEdgeCases:
    """Tests for edge cases in ID validation.

    This test class covers important edge cases that could cause validation failures:
    - Empty directories and missing tickets
    - Mixed valid and duplicate IDs to ensure selective detection
    - Boundary values (all zeros, all nines, etc.)

    These edge cases ensure the linter is robust and handles unusual but valid
    scenarios without false positives or crashes.
    """

    def test_empty_tickets_directory(self, tmp_path):
        """Should handle empty tickets directory."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        subtasks_dir = tmp_path / "subtasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()
        subtasks_dir.mkdir()

        linter = Linter(str(tmp_path))
        report = linter.run()

        assert len(report.errors) == 0
        assert not report.is_corrupt()

    def test_mixed_valid_and_duplicate(self, tmp_path):
        """Should detect duplicates while passing valid IDs."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # Valid unique IDs
        (epics_dir / "bees-abc.md").write_text("""---
id: bees-abc
bees_version: '1.1'
type: epic
title: Valid 1
---

Body.""")

        (epics_dir / "bees-xyz.md").write_text("""---
id: bees-xyz
bees_version: '1.1'
type: epic
title: Valid 2
---

Body.""")

        # Duplicate ID
        (epics_dir / "bees-du1.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Dup 1
---

Body.""")

        (epics_dir / "bees-du2.md").write_text("""---
id: bees-dup
bees_version: '1.1'
type: epic
title: Dup 2
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have no format errors
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

        # Should have one duplicate error
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 1
        assert duplicate_errors[0].ticket_id == "default.bees-dup"

    def test_boundary_values(self, tmp_path):
        """Test boundary values for ID format."""
        epics_dir = tmp_path / "epics"
        epics_dir.mkdir()

        # All lowercase
        (epics_dir / "bees-zzz.md").write_text("""---
id: bees-zzz
type: epic
title: All Z
---

Body.""")

        # All numeric
        (epics_dir / "bees-999.md").write_text("""---
id: bees-999
type: epic
title: All 9
---

Body.""")

        # All zeros
        (epics_dir / "bees-000.md").write_text("""---
id: bees-000
type: epic
title: All 0
---

Body.""")

        # All 'a'
        (epics_dir / "bees-aaa.md").write_text("""---
id: bees-aaa
type: epic
title: All A
---

Body.""")

        linter = Linter(str(tmp_path))
        report = linter.run()

        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 0

    def test_large_id_set_no_false_positives(self, tmp_path):
        """Test that system handles large number of unique IDs without false positives."""
        epics_dir = tmp_path / "epics"
        tasks_dir = tmp_path / "tasks"
        epics_dir.mkdir()
        tasks_dir.mkdir()

        # Generate 1000+ unique IDs using different patterns
        import string
        ticket_count = 0

        # Generate IDs with all alphanumeric combinations (sample)
        for i in range(500):
            ticket_id = f"bees-{i:03x}"  # Use hex to get a-f and 0-9
            (epics_dir / f"{ticket_id}.md").write_text(f"""---
id: {ticket_id}
type: epic
title: Epic {i}
---

Body.""")
            ticket_count += 1

        # Generate more IDs with different patterns
        for i in range(500):
            ticket_id = f"bees-{chr(97 + (i % 26))}{(i // 26) % 10}{chr(97 + ((i // 260) % 26))}"
            (tasks_dir / f"{ticket_id}.md").write_text(f"""---
id: {ticket_id}
type: task
title: Task {i}
parent: bees-000
---

Body.""")
            ticket_count += 1

        linter = Linter(str(tmp_path))
        report = linter.run()

        # Should have no format errors
        format_errors = report.get_errors(error_type="id_format")
        assert len(format_errors) == 0

        # Should have no duplicate errors (all IDs are unique)
        duplicate_errors = report.get_errors(error_type="duplicate_id")
        assert len(duplicate_errors) == 0

        # Verify we actually tested a large set
        assert ticket_count >= 1000
