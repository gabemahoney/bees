"""Unit tests for index generation functions."""

import pytest
from pathlib import Path

from src.index_generator import scan_tickets, format_index_markdown, generate_index
from src.models import Epic, Task, Subtask, Ticket


class TestScanTickets:
    """Tests for scan_tickets function."""

    def test_scan_tickets_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty lists when no tickets exist."""
        # Create empty tickets directory structure
        tickets_dir = tmp_path / "tickets"
        (tickets_dir / "epics").mkdir(parents=True)
        (tickets_dir / "tasks").mkdir(parents=True)
        (tickets_dir / "subtasks").mkdir(parents=True)

        # Monkeypatch TICKETS_DIR to use tmp_path
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        result = scan_tickets()

        assert result == {
            "epic": [],
            "task": [],
            "subtask": []
        }

    def test_scan_tickets_with_mixed_types(self, tmp_path, monkeypatch):
        """Should group tickets by type correctly."""
        tickets_dir = tmp_path / "tickets"
        epics_dir = tickets_dir / "epics"
        tasks_dir = tickets_dir / "tasks"
        subtasks_dir = tickets_dir / "subtasks"

        epics_dir.mkdir(parents=True)
        tasks_dir.mkdir(parents=True)
        subtasks_dir.mkdir(parents=True)

        # Create sample tickets
        (epics_dir / "bees-ep1.md").write_text("""---
id: bees-ep1
type: epic
title: Test Epic 1
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic description.""")

        (epics_dir / "bees-ep2.md").write_text("""---
id: bees-ep2
type: epic
title: Test Epic 2
status: closed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Another epic.""")

        (tasks_dir / "bees-ts1.md").write_text("""---
id: bees-ts1
type: task
title: Test Task 1
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Task description.""")

        (subtasks_dir / "bees-sb1.md").write_text("""---
id: bees-sb1
type: subtask
title: Test Subtask 1
parent: bees-ts1
status: open
created_at: '2026-01-30T13:00:00'
updated_at: '2026-01-30T13:00:00'
---

Subtask description.""")

        # Monkeypatch TICKETS_DIR
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        result = scan_tickets()

        assert len(result["epic"]) == 2
        assert len(result["task"]) == 1
        assert len(result["subtask"]) == 1

        # Verify ticket IDs
        epic_ids = [t.id for t in result["epic"]]
        assert "bees-ep1" in epic_ids
        assert "bees-ep2" in epic_ids

        assert result["task"][0].id == "bees-ts1"
        assert result["subtask"][0].id == "bees-sb1"

    def test_scan_tickets_with_invalid_ticket(self, tmp_path, monkeypatch):
        """Should skip invalid tickets and continue processing."""
        tickets_dir = tmp_path / "tickets"
        epics_dir = tickets_dir / "epics"
        epics_dir.mkdir(parents=True)

        # Create valid ticket
        (epics_dir / "bees-ep1.md").write_text("""---
id: bees-ep1
type: epic
title: Valid Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Valid.""")

        # Create invalid ticket (missing required fields)
        (epics_dir / "bees-ep2.md").write_text("""---
type: epic
---

Invalid ticket missing id.""")

        # Monkeypatch TICKETS_DIR
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        # Should succeed and return the valid ticket
        with pytest.warns(UserWarning, match="Failed to load ticket"):
            result = scan_tickets()

        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "bees-ep1"


class TestFormatIndexMarkdown:
    """Tests for format_index_markdown function."""

    def test_format_empty_tickets(self):
        """Should format index with 'No tickets found' for empty lists."""
        tickets = {
            "epic": [],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        assert "# Ticket Index" in result
        assert "## Epics" in result
        assert "## Tasks" in result
        assert "## Subtasks" in result
        assert result.count("*No tickets found*") == 3

    def test_format_with_tickets(self):
        """Should format tickets with ID, title, and status."""
        epic1 = Epic(
            id="bees-ep1",
            type="epic",
            title="Test Epic",
            status="open"
        )
        task1 = Task(
            id="bees-ts1",
            type="task",
            title="Test Task",
            status="in_progress"
        )
        subtask1 = Subtask(
            id="bees-sb1",
            type="subtask",
            title="Test Subtask",
            parent="bees-ts1",
            status="closed"
        )

        tickets = {
            "epic": [epic1],
            "task": [task1],
            "subtask": [subtask1]
        }

        result = format_index_markdown(tickets)

        # Check structure
        assert "# Ticket Index" in result
        assert "## Epics" in result
        assert "## Tasks" in result
        assert "## Subtasks" in result

        # Check epic formatting
        assert "[bees-ep1] Test Epic (open)" in result

        # Check task formatting
        assert "[bees-ts1] Test Task (in_progress)" in result

        # Check subtask formatting (includes parent)
        assert "[bees-sb1] Test Subtask (closed) (parent: bees-ts1)" in result

    def test_format_sorts_by_id(self):
        """Should sort tickets by ID within each section."""
        epic1 = Epic(id="bees-z9", type="epic", title="Last", status="open")
        epic2 = Epic(id="bees-a1", type="epic", title="First", status="open")
        epic3 = Epic(id="bees-m5", type="epic", title="Middle", status="open")

        tickets = {
            "epic": [epic1, epic2, epic3],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # Find positions of each epic ID in result
        pos_a1 = result.index("bees-a1")
        pos_m5 = result.index("bees-m5")
        pos_z9 = result.index("bees-z9")

        # Should be in alphabetical order
        assert pos_a1 < pos_m5 < pos_z9

    def test_format_handles_missing_status(self):
        """Should display 'unknown' for tickets without status."""
        epic1 = Epic(
            id="bees-ep1",
            type="epic",
            title="No Status",
            status=None
        )

        tickets = {
            "epic": [epic1],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        assert "[bees-ep1] No Status (unknown)" in result


class TestGenerateIndex:
    """Tests for generate_index function."""

    def test_generate_index_end_to_end(self, tmp_path, monkeypatch):
        """Should generate complete index from tickets directory."""
        tickets_dir = tmp_path / "tickets"
        epics_dir = tickets_dir / "epics"
        tasks_dir = tickets_dir / "tasks"

        epics_dir.mkdir(parents=True)
        tasks_dir.mkdir(parents=True)

        # Create sample tickets
        (epics_dir / "bees-ep1.md").write_text("""---
id: bees-ep1
type: epic
title: Sample Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic body.""")

        (tasks_dir / "bees-ts1.md").write_text("""---
id: bees-ts1
type: task
title: Sample Task
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Task body.""")

        # Monkeypatch TICKETS_DIR
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        result = generate_index()

        # Verify structure
        assert "# Ticket Index" in result
        assert "## Epics" in result
        assert "## Tasks" in result
        assert "## Subtasks" in result

        # Verify content
        assert "[bees-ep1] Sample Epic (open)" in result
        assert "[bees-ts1] Sample Task (open)" in result
        assert "*No tickets found*" in result  # For subtasks section

    def test_generate_index_empty_directory(self, tmp_path, monkeypatch):
        """Should generate index with 'No tickets found' for all sections."""
        tickets_dir = tmp_path / "tickets"
        (tickets_dir / "epics").mkdir(parents=True)
        (tickets_dir / "tasks").mkdir(parents=True)
        (tickets_dir / "subtasks").mkdir(parents=True)

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        result = generate_index()

        assert "# Ticket Index" in result
        assert result.count("*No tickets found*") == 3
