"""Unit tests for index generation functions."""

import pytest
from pathlib import Path

from src.index_generator import scan_tickets, format_index_markdown, generate_index
from src.models import Epic, Task, Subtask, Ticket


class TestScanTickets:
    """Tests for scan_tickets function."""

    def test_scan_tickets_empty_directory(self, tmp_path, monkeypatch):
        """Should return empty lists when no tickets exist."""
        import json
        
        # Create empty default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()
        
        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = scan_tickets()

        assert result == {
            "epic": [],
            "task": [],
            "subtask": []
        }

    def test_scan_tickets_with_mixed_types(self, tmp_path, monkeypatch):
        """Should group tickets by type correctly."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create sample tickets in hive root
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Test Epic 1
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic description.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Test Epic 2
status: closed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Another epic.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Test Task 1
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Task description.""")

        (default_hive / "default.bees-sb1.md").write_text("""---
id: default.bees-sb1
bees_version: '1.1'
type: subtask
title: Test Subtask 1
parent: default.bees-ts1
status: open
created_at: '2026-01-30T13:00:00'
updated_at: '2026-01-30T13:00:00'
---

Subtask description.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = scan_tickets()

        assert len(result["epic"]) == 2
        assert len(result["task"]) == 1
        assert len(result["subtask"]) == 1

        # Verify ticket IDs
        epic_ids = [t.id for t in result["epic"]]
        assert "default.bees-ep1" in epic_ids
        assert "default.bees-ep2" in epic_ids

        assert result["task"][0].id == "default.bees-ts1"
        assert result["subtask"][0].id == "default.bees-sb1"

    def test_scan_tickets_with_invalid_ticket(self, tmp_path, monkeypatch):
        """Should skip invalid tickets and continue processing."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create valid ticket
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Valid Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Valid.""")

        # Create invalid ticket (missing required fields)
        (default_hive / "default.bees-ep2.md").write_text("""---
type: epic
bees_version: '1.1'
---

Invalid ticket missing id.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Should succeed and return the valid ticket
        with pytest.warns(UserWarning, match="Failed to load ticket"):
            result = scan_tickets()

        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "default.bees-ep1"

    def test_scan_tickets_filter_by_status(self, tmp_path, monkeypatch):
        """Should filter tickets by status."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create tickets with different statuses
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Completed Epic
status: completed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filter for open only
        result = scan_tickets(status_filter='open')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "default.bees-ep1"

        # Filter for completed only
        result = scan_tickets(status_filter='completed')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "default.bees-ep2"

    def test_scan_tickets_filter_by_type(self, tmp_path, monkeypatch):
        """Should filter tickets by type."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create tickets of different types
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Test Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Test Task
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Task.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filter for epics only
        result = scan_tickets(type_filter='epic')
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 0

        # Filter for tasks only
        result = scan_tickets(type_filter='task')
        assert len(result["epic"]) == 0
        assert len(result["task"]) == 1

    def test_scan_tickets_combined_filters(self, tmp_path, monkeypatch):
        """Should apply both status and type filters."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create diverse tickets
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open epic.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Completed Epic
status: completed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed epic.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Open Task
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Open task.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filter for open epics only
        result = scan_tickets(status_filter='open', type_filter='epic')
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 0
        assert result["epic"][0].id == "default.bees-ep1"

        # Filter for completed tasks (should be empty)
        result = scan_tickets(status_filter='completed', type_filter='task')
        assert len(result["epic"]) == 0
        assert len(result["task"]) == 0


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
            id="default.bees-ep1",
            type="epic",
            title="Test Epic",
            status="open"
        )
        task1 = Task(
            id="default.bees-ts1",
            type="task",
            title="Test Task",
            status="in_progress"
        )
        subtask1 = Subtask(
            id="default.bees-sb1",
            type="subtask",
            title="Test Subtask",
            parent="default.bees-ts1",
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

        # Check epic formatting with clickable link (flat storage format)
        assert "[default.bees-ep1: Test Epic](default.bees-ep1.md) (open)" in result

        # Check task formatting with clickable link (flat storage format)
        assert "[default.bees-ts1: Test Task](default.bees-ts1.md) (in_progress)" in result

        # Check subtask formatting (includes parent and clickable link, flat storage format)
        assert "[default.bees-sb1: Test Subtask](default.bees-sb1.md) (closed) (parent: default.bees-ts1)" in result

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
            id="default.bees-ep1",
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

        assert "[default.bees-ep1: No Status](default.bees-ep1.md) (unknown)" in result

    def test_format_with_special_characters_in_title(self):
        """Should handle special characters in title for markdown links."""
        epic1 = Epic(
            id="default.bees-ep1",
            type="epic",
            title="Test [Special] Characters: & Symbols",
            status="open"
        )

        tickets = {
            "epic": [epic1],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # Markdown link should preserve special characters in link text
        assert "[default.bees-ep1: Test [Special] Characters: & Symbols](default.bees-ep1.md) (open)" in result

    def test_format_link_paths_are_relative(self):
        """Should use relative paths for ticket links (flat storage format)."""
        epic1 = Epic(id="default.bees-abc", type="epic", title="Test", status="open")
        task1 = Task(id="default.bees-xyz", type="task", title="Test", status="open")
        subtask1 = Subtask(id="default.bees-123", type="subtask", title="Test", parent="default.bees-xyz", status="open")

        tickets = {
            "epic": [epic1],
            "task": [task1],
            "subtask": [subtask1]
        }

        result = format_index_markdown(tickets)

        # All links should use flat relative paths (no type subdirectories)
        assert "(default.bees-abc.md)" in result
        assert "(default.bees-xyz.md)" in result
        assert "(default.bees-123.md)" in result

    def test_format_link_includes_id_and_title(self):
        """Should include both ID and title in link text."""
        epic1 = Epic(
            id="bees-test",
            type="epic",
            title="My Epic Title",
            status="open"
        )

        tickets = {
            "epic": [epic1],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # Link text should be "ID: Title"
        assert "[bees-test: My Epic Title]" in result

    def test_format_link_path_uses_flat_structure(self):
        """Should generate link paths without type subdirectories (flat storage)."""
        epic1 = Epic(id="default.bees-abc", type="epic", title="Test Epic", status="open")
        task1 = Task(id="default.bees-xyz", type="task", title="Test Task", status="open")
        subtask1 = Subtask(id="default.bees-123", type="subtask", title="Test Subtask", parent="default.bees-xyz", status="open")

        tickets = {
            "epic": [epic1],
            "task": [task1],
            "subtask": [subtask1]
        }

        result = format_index_markdown(tickets)

        # Epic link should use flat path (no subdirectory)
        assert "[default.bees-abc: Test Epic](default.bees-abc.md)" in result

        # Task link should use flat path (no subdirectory)
        assert "[default.bees-xyz: Test Task](default.bees-xyz.md)" in result

        # Subtask link should use flat path (no subdirectory)
        assert "[default.bees-123: Test Subtask](default.bees-123.md)" in result


class TestGenerateIndex:
    """Tests for generate_index function."""

    def test_generate_index_end_to_end(self, tmp_path, monkeypatch):
        """Should generate complete index from tickets directory."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create sample tickets in hive root
        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Sample Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic body.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Sample Task
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Task body.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        # Verify structure
        assert "# Ticket Index" in result
        assert "## Epics" in result
        assert "## Tasks" in result
        assert "## Subtasks" in result

        # Verify content with clickable links (flat storage format)
        assert "[default.bees-ep1: Sample Epic](default.bees-ep1.md) (open)" in result
        assert "[default.bees-ts1: Sample Task](default.bees-ts1.md) (open)" in result
        assert "*No tickets found*" in result  # For subtasks section

    def test_generate_index_empty_directory(self, tmp_path, monkeypatch):
        """Should generate index with 'No tickets found' for all sections."""
        import json
        
        # Create empty default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        assert "# Ticket Index" in result
        assert result.count("*No tickets found*") == 3

    def test_generate_index_with_status_filter(self, tmp_path, monkeypatch):
        """Should filter index by status."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Completed Epic
status: completed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index(status_filter='open')
        assert "[default.bees-ep1: Open Epic](default.bees-ep1.md) (open)" in result
        assert "default.bees-ep2" not in result

    def test_generate_index_with_type_filter(self, tmp_path, monkeypatch):
        """Should filter index by type."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Test Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Test Task
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Task.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index(type_filter='epic')
        assert "[default.bees-ep1: Test Epic](default.bees-ep1.md) (open)" in result
        assert "default.bees-ts1" not in result

    def test_generate_index_with_combined_filters(self, tmp_path, monkeypatch):
        """Should filter index by both status and type."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open epic.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Completed Epic
status: completed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Completed epic.""")

        (default_hive / "default.bees-ts1.md").write_text("""---
id: default.bees-ts1
bees_version: '1.1'
type: task
title: Open Task
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Open task.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index(status_filter='open', type_filter='epic')
        assert "[default.bees-ep1: Open Epic](default.bees-ep1.md) (open)" in result
        assert "default.bees-ep2" not in result
        assert "default.bees-ts1" not in result

    def test_flat_paths_for_all_types(self, tmp_path, monkeypatch):
        """Should generate flat paths ({id}.md) for all ticket types."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create one ticket of each type in hive root
        (default_hive / "default.bees-ep9.md").write_text("""---
id: default.bees-ep9
bees_version: '1.1'
type: epic
title: Test Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Epic.""")

        (default_hive / "default.bees-ts9.md").write_text("""---
id: default.bees-ts9
bees_version: '1.1'
type: task
title: Test Task
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Task.""")

        (default_hive / "default.bees-sb9.md").write_text("""---
id: default.bees-sb9
bees_version: '1.1'
type: subtask
title: Test Subtask
parent: default.bees-ts9
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Subtask.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        # Verify flat paths for all types (no type subdirectories)
        assert "default.bees-ep9.md" in result
        assert "default.bees-ts9.md" in result
        assert "default.bees-sb9.md" in result

        # Verify hierarchical paths are NOT used
        assert "tickets/epics/" not in result
        assert "tickets/tasks/" not in result
        assert "tickets/subtasks/" not in result

    def test_flat_paths_with_empty_sections(self, tmp_path, monkeypatch):
        """Should handle empty sections correctly with flat structure."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Only create epic in hive root, no tasks or subtasks
        (default_hive / "default.bees-on1.md").write_text("""---
id: default.bees-on1
bees_version: '1.1'
type: epic
title: Only Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Solo epic.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        # Should have flat path for epic
        assert "default.bees-on1.md" in result

        # Should have "No tickets found" for empty sections
        assert result.count("*No tickets found*") == 2

    def test_flat_paths_with_mixed_statuses(self, tmp_path, monkeypatch):
        """Should use flat paths regardless of ticket status."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create tickets with various statuses in hive root
        (default_hive / "default.bees-op1.md").write_text("""---
id: default.bees-op1
bees_version: '1.1'
type: epic
title: Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open.""")

        (default_hive / "default.bees-pr1.md").write_text("""---
id: default.bees-pr1
bees_version: '1.1'
type: epic
title: In Progress Epic
status: in_progress
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

In progress.""")

        (default_hive / "default.bees-cl1.md").write_text("""---
id: default.bees-cl1
bees_version: '1.1'
type: epic
title: Closed Epic
status: closed
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Closed.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        # All should use flat paths regardless of status
        assert "default.bees-op1.md" in result
        assert "default.bees-pr1.md" in result
        assert "default.bees-cl1.md" in result

    def test_flat_paths_with_various_ids(self, tmp_path, monkeypatch):
        """Should handle tickets with various ID formats using flat paths."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        # Create tickets with different ID formats in hive root
        (default_hive / "default.bees-abc.md").write_text("""---
id: default.bees-abc
bees_version: '1.1'
type: task
title: Alpha ID
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Alpha.""")

        (default_hive / "default.bees-123.md").write_text("""---
id: default.bees-123
bees_version: '1.1'
type: task
title: Numeric ID
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Numeric.""")

        (default_hive / "default.bees-x9z.md").write_text("""---
id: default.bees-x9z
bees_version: '1.1'
type: task
title: Mixed ID
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Mixed.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        result = generate_index()

        # All should use flat paths (no type subdirectories)
        assert "default.bees-abc.md" in result
        assert "default.bees-123.md" in result
        assert "default.bees-x9z.md" in result


class TestPerHiveIndexGeneration:
    """Tests for per-hive index generation functionality."""

    def test_scan_tickets_filter_by_hive(self, tmp_path, monkeypatch):
        """Should filter tickets by hive prefix."""
        import json
        
        # Create hive directories
        backend_hive = tmp_path / "backend"
        frontend_hive = tmp_path / "frontend"
        default_hive = tmp_path / "default"
        backend_hive.mkdir()
        frontend_hive.mkdir()
        default_hive.mkdir()

        # Create tickets with different hive prefixes in their respective hives
        (backend_hive / "backend.bees-ep1.md").write_text("""---
id: backend.bees-ep1
bees_version: '1.1'
type: epic
title: Backend Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Backend epic.""")

        (frontend_hive / "frontend.bees-ep2.md").write_text("""---
id: frontend.bees-ep2
bees_version: '1.1'
type: epic
title: Frontend Epic
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Frontend epic.""")

        (default_hive / "default.bees-ep3.md").write_text("""---
id: default.bees-ep3
bees_version: '1.1'
type: epic
title: Legacy Epic
status: open
created_at: '2026-01-30T12:00:00'
updated_at: '2026-01-30T12:00:00'
---

Legacy epic.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                },
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend"
                },
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filter for backend hive only
        result = scan_tickets(hive_name='backend')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "backend.bees-ep1"

        # Filter for frontend hive only
        result = scan_tickets(hive_name='frontend')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "frontend.bees-ep2"

        # No hive filter returns all tickets
        result = scan_tickets()
        assert len(result["epic"]) == 3

    def test_scan_tickets_hive_excludes_legacy(self, tmp_path, monkeypatch):
        """Should exclude legacy tickets when filtering by hive."""
        import json
        
        # Create hive directories
        backend_hive = tmp_path / "backend"
        default_hive = tmp_path / "default"
        backend_hive.mkdir()
        default_hive.mkdir()

        (backend_hive / "backend.bees-ep1.md").write_text("""---
id: backend.bees-ep1
bees_version: '1.1'
type: epic
title: Backend Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Backend.""")

        (default_hive / "default.bees-ep2.md").write_text("""---
id: default.bees-ep2
bees_version: '1.1'
type: epic
title: Legacy Epic
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Legacy.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                },
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filtering by hive should exclude legacy ticket
        result = scan_tickets(hive_name='backend')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "backend.bees-ep1"

    def test_generate_index_with_hive_writes_to_hive_root(self, tmp_path, monkeypatch):
        """Should write index to hive root directory when hive_name provided."""
        import json

        # Create hive directory
        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create hive-prefixed ticket in hive root
        (backend_hive / "backend.bees-ep1.md").write_text("""---
id: backend.bees-ep1
bees_version: '1.1'
type: epic
title: Backend Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Backend epic.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Generate index for backend hive
        result = generate_index(hive_name='backend')

        # Verify index was written to hive root
        index_path = backend_hive / "index.md"
        assert index_path.exists()

        # Verify index content
        index_content = index_path.read_text()
        assert "# Ticket Index" in index_content
        assert "backend.bees-ep1" in index_content
        assert "Backend Epic" in index_content

    def test_generate_index_all_hives_writes_multiple_indexes(self, tmp_path, monkeypatch):
        """Should write separate indexes for all hives when hive_name omitted."""
        import json

        # Create hive directories
        backend_hive = tmp_path / "backend"
        frontend_hive = tmp_path / "frontend"
        backend_hive.mkdir()
        frontend_hive.mkdir()

        # Create tickets in respective hive roots
        (backend_hive / "backend.bees-ep1.md").write_text("""---
id: backend.bees-ep1
bees_version: '1.1'
type: epic
title: Backend Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Backend.""")

        (frontend_hive / "frontend.bees-ep2.md").write_text("""---
id: frontend.bees-ep2
bees_version: '1.1'
type: epic
title: Frontend Epic
status: open
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Frontend.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                },
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Generate indexes for all hives
        generate_index()

        # Verify backend index
        backend_index = backend_hive / "index.md"
        assert backend_index.exists()
        backend_content = backend_index.read_text()
        assert "backend.bees-ep1" in backend_content
        assert "Backend Epic" in backend_content
        assert "frontend.bees-ep2" not in backend_content

        # Verify frontend index
        frontend_index = frontend_hive / "index.md"
        assert frontend_index.exists()
        frontend_content = frontend_index.read_text()
        assert "frontend.bees-ep2" in frontend_content
        assert "Frontend Epic" in frontend_content
        assert "backend.bees-ep1" not in frontend_content

    def test_generate_index_hive_not_in_config(self, tmp_path, monkeypatch):
        """Should create hive directory and write index when hive not in config."""
        import json
        
        # Create newback hive directory
        newback_hive = tmp_path / "newback"
        newback_hive.mkdir()

        (newback_hive / "newback.bees-ep1.md").write_text("""---
id: newback.bees-ep1
bees_version: '1.1'
type: epic
title: New Backend Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

New backend.""")

        # Create .bees/config.json with newback hive
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "newback": {
                    "path": str(newback_hive),
                    "display_name": "New Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Generate index for hive
        result = generate_index(hive_name='newback')

        # Should write index to hive directory
        hive_dir = tmp_path / "newback"
        assert hive_dir.exists()

        index_path = hive_dir / "index.md"
        assert index_path.exists()

        index_content = index_path.read_text()
        assert "newback.bees-ep1" in index_content

    def test_generate_index_no_config_returns_markdown(self, tmp_path, monkeypatch):
        """Should return markdown without writing when no config exists."""
        import json
        
        # Create default hive directory
        default_hive = tmp_path / "default"
        default_hive.mkdir()

        (default_hive / "default.bees-ep1.md").write_text("""---
id: default.bees-ep1
bees_version: '1.1'
type: epic
title: Legacy Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Legacy.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "default": {
                    "path": str(default_hive),
                    "display_name": "Default"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Generate index - should return markdown and write to hive root
        result = generate_index()

        # Should contain the ticket
        assert "default.bees-ep1" in result
        assert "Legacy Epic" in result

        # Should write to hive root when config exists
        index_path = default_hive / "index.md"
        assert index_path.exists()

    def test_scan_tickets_hive_with_status_filter(self, tmp_path, monkeypatch):
        """Should combine hive and status filters."""
        import json
        
        # Create backend hive directory
        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        (backend_hive / "backend.bees-ep1.md").write_text("""---
id: backend.bees-ep1
bees_version: '1.1'
type: epic
title: Backend Open Epic
status: open
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Open.""")

        (backend_hive / "backend.bees-ep2.md").write_text("""---
id: backend.bees-ep2
bees_version: '1.1'
type: epic
title: Backend Closed Epic
status: closed
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Closed.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Filter for backend + open only
        result = scan_tickets(hive_name='backend', status_filter='open')
        assert len(result["epic"]) == 1
        assert result["epic"][0].id == "backend.bees-ep1"


class TestFlatStorageLinkGeneration:
    """Tests for flat storage link generation (Task bees-qjt92)."""

    def test_format_uses_flat_link_paths(self):
        """Should use relative paths without type subdirectories for flat storage."""
        epic1 = Epic(id="backend.bees-abc1", type="epic", title="Test Epic", status="open")
        task1 = Task(id="frontend.bees-xyz9", type="task", title="Test Task", status="open")
        subtask1 = Subtask(id="backend.bees-123a", type="subtask", title="Test Subtask", parent="backend.bees-abc1", status="open")

        tickets = {
            "epic": [epic1],
            "task": [task1],
            "subtask": [subtask1]
        }

        result = format_index_markdown(tickets)

        # Links should use flat format: {ticket_id}.md (no type subdirectories)
        assert "[backend.bees-abc1: Test Epic](backend.bees-abc1.md)" in result
        assert "[frontend.bees-xyz9: Test Task](frontend.bees-xyz9.md)" in result
        assert "[backend.bees-123a: Test Subtask](backend.bees-123a.md)" in result

        # Should NOT contain old hierarchical paths
        assert "tickets/epics/" not in result
        assert "tickets/tasks/" not in result
        assert "tickets/subtasks/" not in result

    def test_format_flat_links_with_legacy_ids(self):
        """Should use flat links even for tickets without hive prefix."""
        epic1 = Epic(id="default.bees-ep1", type="epic", title="Legacy Epic", status="open")

        tickets = {
            "epic": [epic1],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # Should use simple relative path
        assert "[default.bees-ep1: Legacy Epic](default.bees-ep1.md)" in result

    def test_format_flat_links_work_from_hive_root(self):
        """Links should work from {hive_name}/index.md to {hive_name}/{ticket_id}.md."""
        # This is a documentation test - links are relative from index location
        epic1 = Epic(id="backend.bees-abc1", type="epic", title="Backend Epic", status="open")

        tickets = {
            "epic": [epic1],
            "task": [],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # Link format should be relative path from index
        # When index is at backend/index.md, link backend.bees-abc1.md points to backend/backend.bees-abc1.md
        assert "(backend.bees-abc1.md)" in result

    def test_format_flat_links_multiple_tickets(self):
        """Should generate flat links for multiple tickets correctly."""
        epic1 = Epic(id="backend.bees-001", type="epic", title="First Epic", status="open")
        epic2 = Epic(id="backend.bees-002", type="epic", title="Second Epic", status="closed")
        task1 = Task(id="frontend.bees-101", type="task", title="First Task", status="open")

        tickets = {
            "epic": [epic1, epic2],
            "task": [task1],
            "subtask": []
        }

        result = format_index_markdown(tickets)

        # All links should use flat format
        assert "[backend.bees-001: First Epic](backend.bees-001.md)" in result
        assert "[backend.bees-002: Second Epic](backend.bees-002.md)" in result
        assert "[frontend.bees-101: First Task](frontend.bees-101.md)" in result


class TestIsIndexStaleFlatStorage:
    """Tests for is_index_stale() with flat storage (Task bees-qjt92)."""

    def test_is_index_stale_scans_hive_root(self, tmp_path, monkeypatch):
        """Should scan hive root directory for ticket files, not subdirectories."""
        import json
        from src.index_generator import is_index_stale

        # Create hive with flat storage
        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create index.md
        index_path = backend_hive / "index.md"
        index_path.write_text("# Old Index")

        # Create ticket files in hive root (flat storage)
        (backend_hive / "backend.bees-abc1.md").write_text("""---
id: backend.bees-abc1
type: epic
title: Test Epic
bees_version: '1.1'
---
Epic.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Make ticket newer than index
        import time
        time.sleep(0.01)
        (backend_hive / "backend.bees-abc1.md").write_text("""---
id: backend.bees-abc1
type: epic
title: Updated Epic
bees_version: '1.1'
---
Updated.""")

        # Should detect stale index
        assert is_index_stale("backend") is True

    def test_is_index_stale_skips_index_itself(self, tmp_path, monkeypatch):
        """Should skip index.md when checking modification times."""
        import json
        from src.index_generator import is_index_stale
        import time

        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create old ticket
        (backend_hive / "backend.bees-abc1.md").write_text("""---
id: backend.bees-abc1
type: epic
bees_version: '1.1'
---
Epic.""")

        time.sleep(0.01)

        # Create index (newer than ticket)
        index_path = backend_hive / "index.md"
        index_path.write_text("# Index")

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Index is newer than tickets, should not be stale
        assert is_index_stale("backend") is False

    def test_is_index_stale_no_subdirectory_scan(self, tmp_path, monkeypatch):
        """Should NOT scan type subdirectories (epics/, tasks/, subtasks/)."""
        import json
        from src.index_generator import is_index_stale
        import time

        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create index
        index_path = backend_hive / "index.md"
        index_path.write_text("# Index")

        time.sleep(0.01)

        # Create OLD-STYLE subdirectories with tickets (should be ignored)
        epics_dir = backend_hive / "epics"
        epics_dir.mkdir()
        (epics_dir / "backend.bees-old.md").write_text("""---
id: backend.bees-old
bees_version: '1.1'
type: epic
---
Old style.""")

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Should NOT detect stale because subdirectories are not scanned
        assert is_index_stale("backend") is False

    def test_is_index_stale_empty_hive_directory(self, tmp_path, monkeypatch):
        """Should handle empty hive directory (no tickets) gracefully."""
        import json
        from src.index_generator import is_index_stale

        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create index in empty hive
        index_path = backend_hive / "index.md"
        index_path.write_text("# Index")

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Empty hive with index should not be stale
        assert is_index_stale("backend") is False

    def test_is_index_stale_ignores_non_md_files(self, tmp_path, monkeypatch):
        """Should ignore non-.md files in hive root when checking staleness."""
        import json
        from src.index_generator import is_index_stale
        import time

        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create old ticket
        (backend_hive / "backend.bees-abc1.md").write_text("""---
id: backend.bees-abc1
type: epic
bees_version: '1.1'
---
Epic.""")

        time.sleep(0.01)

        # Create index (newer than ticket)
        index_path = backend_hive / "index.md"
        index_path.write_text("# Index")

        time.sleep(0.01)

        # Create non-.md files that are newer than index (should be ignored)
        (backend_hive / "README.txt").write_text("readme")
        (backend_hive / "notes.json").write_text("{}")
        (backend_hive / ".hidden").write_text("hidden")
        (backend_hive / "config.yaml").write_text("config: true")

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Should NOT be stale - non-.md files should be ignored
        assert is_index_stale("backend") is False


class TestFlatStorageExclusions:
    """Tests for /eggs and /evicted directory exclusion in flat storage."""

    def test_scan_tickets_excludes_eggs_directory(self, tmp_path, monkeypatch):
        """Should exclude tickets in /eggs subdirectory from scan."""
        import json

        # Create hive directory
        backend_hive = tmp_path / "backend"
        backend_hive.mkdir()

        # Create valid ticket in hive root
        (backend_hive / "backend.bees-abc.md").write_text("""---
id: backend.bees-abc
type: epic
title: Valid Epic
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Valid epic in hive root.""")

        # Create /eggs subdirectory with ticket (should be excluded)
        eggs_dir = backend_hive / "eggs"
        eggs_dir.mkdir()
        (eggs_dir / "backend.bees-egg.md").write_text("""---
id: backend.bees-egg
type: task
title: Egg Template
status: open
bees_version: '1.1'
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Template in eggs directory.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Scan tickets - should only find ticket in hive root
        result = scan_tickets()
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 0  # Egg template excluded
        assert result["epic"][0].id == "backend.bees-abc"

    def test_scan_tickets_excludes_evicted_directory(self, tmp_path, monkeypatch):
        """Should exclude tickets in /evicted subdirectory from scan."""
        import json

        # Create hive directory
        frontend_hive = tmp_path / "frontend"
        frontend_hive.mkdir()

        # Create valid ticket in hive root
        (frontend_hive / "frontend.bees-xyz.md").write_text("""---
id: frontend.bees-xyz
type: task
title: Active Task
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Active task in hive root.""")

        # Create /evicted subdirectory with archived ticket (should be excluded)
        evicted_dir = frontend_hive / "evicted"
        evicted_dir.mkdir()
        (evicted_dir / "frontend.bees-old1.md").write_text("""---
id: frontend.bees-old1
type: epic
title: Archived Epic
status: completed
bees_version: '1.1'
created_at: '2026-01-29T10:00:00'
updated_at: '2026-01-30T12:00:00'
---

Archived epic in evicted directory.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Scan tickets - should only find active ticket, not archived
        result = scan_tickets()
        assert len(result["task"]) == 1
        assert len(result["epic"]) == 0  # Archived epic excluded
        assert result["task"][0].id == "frontend.bees-xyz"

    def test_scan_tickets_excludes_both_eggs_and_evicted(self, tmp_path, monkeypatch):
        """Should exclude both /eggs and /evicted subdirectories simultaneously."""
        import json

        # Create hive directory
        hive = tmp_path / "test_hive"
        hive.mkdir()

        # Create valid tickets in hive root
        (hive / "test_hive.bees-001.md").write_text("""---
id: test_hive.bees-001
type: epic
title: Active Epic
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Active epic.""")

        (hive / "test_hive.bees-002.md").write_text("""---
id: test_hive.bees-002
type: task
title: Active Task
status: open
bees_version: '1.1'
created_at: '2026-01-30T11:00:00'
updated_at: '2026-01-30T11:00:00'
---

Active task.""")

        # Create /eggs directory with template
        eggs_dir = hive / "eggs"
        eggs_dir.mkdir()
        (eggs_dir / "test_hive.bees-egg1.md").write_text("""---
id: test_hive.bees-egg1
type: subtask
title: Template Subtask
bees_version: '1.1'
---

Template.""")

        # Create /evicted directory with archived ticket
        evicted_dir = hive / "evicted"
        evicted_dir.mkdir()
        (evicted_dir / "test_hive.bees-old1.md").write_text("""---
id: test_hive.bees-old1
type: epic
title: Archived Epic
status: completed
bees_version: '1.1'
---

Archived.""")

        # Create .bees/config.json
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "test_hive": {
                    "path": str(hive),
                    "display_name": "Test Hive"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Scan tickets - should only find active tickets in hive root
        result = scan_tickets()
        assert len(result["epic"]) == 1
        assert len(result["task"]) == 1
        assert len(result["subtask"]) == 0  # Template excluded
        assert result["epic"][0].id == "test_hive.bees-001"
        assert result["task"][0].id == "test_hive.bees-002"

    def test_generate_index_excludes_eggs_and_evicted(self, tmp_path, monkeypatch):
        """Generated index should not include tickets from /eggs or /evicted."""
        import json

        # Create hive
        hive = tmp_path / "my_hive"
        hive.mkdir()

        # Valid ticket in root
        (hive / "my_hive.bees-001.md").write_text("""---
id: my_hive.bees-001
type: epic
title: Visible Epic
status: open
bees_version: '1.1'
created_at: '2026-01-30T10:00:00'
updated_at: '2026-01-30T10:00:00'
---

Visible.""")

        # Ticket in /eggs (excluded)
        eggs_dir = hive / "eggs"
        eggs_dir.mkdir()
        (eggs_dir / "my_hive.bees-egg.md").write_text("""---
id: my_hive.bees-egg
type: task
title: Hidden Egg
bees_version: '1.1'
---

Hidden.""")

        # Ticket in /evicted (excluded)
        evicted_dir = hive / "evicted"
        evicted_dir.mkdir()
        (evicted_dir / "my_hive.bees-old.md").write_text("""---
id: my_hive.bees-old
type: subtask
title: Hidden Archive
bees_version: '1.1'
---

Hidden.""")

        # Create config
        bees_dir = tmp_path / ".bees"
        bees_dir.mkdir()
        config = {
            "hives": {
                "my_hive": {
                    "path": str(hive),
                    "display_name": "My Hive"
                }
            },
            "allow_cross_hive_dependencies": False,
            "schema_version": "1.0"
        }
        (bees_dir / "config.json").write_text(json.dumps(config))
        monkeypatch.chdir(tmp_path)

        # Generate index
        result = generate_index()

        # Should only include visible epic
        assert "my_hive.bees-001" in result
        assert "Visible Epic" in result

        # Should NOT include eggs or evicted tickets
        assert "my_hive.bees-egg" not in result
        assert "Hidden Egg" not in result
        assert "my_hive.bees-old" not in result
        assert "Hidden Archive" not in result
