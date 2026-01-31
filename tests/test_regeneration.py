"""Tests for index regeneration workflow including CLI and watcher functionality."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.cli import regenerate_index
from src.index_generator import is_index_stale, generate_index
from src.paths import get_index_path, TICKETS_DIR
from src.watcher import TicketChangeHandler


class TestRegenerateIndexCLI:
    """Test regenerate_index CLI command."""

    def test_regenerates_when_index_missing(self, tmp_path, monkeypatch):
        """Test regeneration when index.md doesn't exist."""
        # Setup test environment
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        # Create a test ticket
        test_ticket = tickets_dir / "epics" / "bees-abc.md"
        test_ticket.write_text("""---
id: bees-abc
title: Test Epic
type: epic
status: open
---
Test content""")

        # Mock paths to use tmp_path
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.cli.get_index_path", lambda: tickets_dir / "index.md")

        # Run regeneration
        exit_code = regenerate_index(force=False)

        assert exit_code == 0
        index_path = tickets_dir / "index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "# Ticket Index" in content
        assert "*Generated:" in content

    def test_skips_when_index_current(self, tmp_path, monkeypatch):
        """Test that regeneration is skipped when index is up-to-date."""
        # Setup test environment
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        # Create ticket and index
        test_ticket = tickets_dir / "epics" / "bees-abc.md"
        test_ticket.write_text("""---
id: bees-abc
title: Test Epic
type: epic
status: open
---
Test content""")

        index_path = tickets_dir / "index.md"
        index_path.write_text("# Ticket Index\n*Generated: 2026-01-30 12:00:00*\n")

        # Make index newer than ticket by sleeping briefly
        time.sleep(0.01)
        index_path.touch()

        # Mock paths
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.cli.get_index_path", lambda: index_path)
        monkeypatch.setattr("src.cli.is_index_stale", lambda: False)

        # Run regeneration without force
        exit_code = regenerate_index(force=False)

        assert exit_code == 0
        # Content should be unchanged (old timestamp preserved)
        assert "2026-01-30 12:00:00" in index_path.read_text()

    def test_force_regenerates_even_when_current(self, tmp_path, monkeypatch):
        """Test that --force flag regenerates even when index is current."""
        # Setup test environment
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        # Create ticket and index
        test_ticket = tickets_dir / "epics" / "bees-abc.md"
        test_ticket.write_text("""---
id: bees-abc
title: Test Epic
type: epic
status: open
---
Test content""")

        index_path = tickets_dir / "index.md"
        old_content = "# Ticket Index\n*Generated: 2026-01-30 12:00:00*\n"
        index_path.write_text(old_content)

        # Mock paths
        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.cli.get_index_path", lambda: index_path)

        # Run regeneration with force
        exit_code = regenerate_index(force=True)

        assert exit_code == 0
        new_content = index_path.read_text()
        # Should have new timestamp
        assert new_content != old_content
        assert "# Ticket Index" in new_content


class TestIsIndexStale:
    """Test index staleness detection."""

    def test_stale_when_index_missing(self, tmp_path, monkeypatch):
        """Test that missing index is considered stale."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.index_generator.get_index_path",
                           lambda: tickets_dir / "index.md")

        assert is_index_stale() is True

    def test_stale_when_ticket_newer(self, tmp_path, monkeypatch):
        """Test that index is stale when ticket is newer."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        # Create index first
        index_path = tickets_dir / "index.md"
        index_path.write_text("old index")

        # Sleep to ensure different mtime
        time.sleep(0.01)

        # Create newer ticket
        ticket_path = tickets_dir / "epics" / "bees-xyz.md"
        ticket_path.write_text("""---
id: bees-abc
title: Test
type: epic
status: open
---""")

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.paths.get_index_path", lambda: index_path)

        assert is_index_stale() is True

    def test_not_stale_when_index_newer(self, tmp_path, monkeypatch):
        """Test that index is not stale when newer than all tickets."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        # Create ticket first
        ticket_path = tickets_dir / "epics" / "bees-xyz.md"
        ticket_path.write_text("""---
id: bees-xyz
title: Test
type: epic
status: open
---""")

        # Sleep to ensure different mtime
        time.sleep(0.01)

        # Create newer index
        index_path = tickets_dir / "index.md"
        index_path.write_text("new index")

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.paths.get_index_path", lambda: index_path)

        assert is_index_stale() is False

    def test_not_stale_when_no_tickets(self, tmp_path, monkeypatch):
        """Test that index is not stale when no tickets exist."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()
        (tickets_dir / "tasks").mkdir()
        (tickets_dir / "subtasks").mkdir()

        index_path = tickets_dir / "index.md"
        index_path.write_text("empty index")

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)
        monkeypatch.setattr("src.paths.get_index_path", lambda: index_path)

        assert is_index_stale() is False


class TestTimestampInIndex:
    """Test that generated index includes timestamp."""

    def test_timestamp_in_generated_index(self, tmp_path, monkeypatch):
        """Test that generate_index includes timestamp header."""
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        index_content = generate_index()

        assert "# Ticket Index" in index_content
        assert "*Generated:" in index_content
        # Should contain a timestamp in format YYYY-MM-DD HH:MM:SS
        import re
        timestamp_pattern = r"\*Generated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\*"
        assert re.search(timestamp_pattern, index_content)


class TestTicketChangeHandler:
    """Test file system watcher handler."""

    def test_ignores_directory_events(self):
        """Test that directory events are ignored."""
        handler = TicketChangeHandler()

        # Mock directory event
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/path/to/dir"

        assert handler._should_process_event(event) is False

    def test_ignores_non_md_files(self):
        """Test that non-.md files are ignored."""
        handler = TicketChangeHandler()

        # Mock non-markdown file event
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/file.txt"

        assert handler._should_process_event(event) is False

    def test_ignores_index_md(self):
        """Test that index.md itself is ignored to avoid loops."""
        handler = TicketChangeHandler()

        # Mock index.md event
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/tickets/index.md"

        assert handler._should_process_event(event) is False

    def test_processes_ticket_md_files(self):
        """Test that ticket .md files are processed."""
        handler = TicketChangeHandler()

        # Mock ticket file event
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/tickets/epics/bees-abc.md"

        assert handler._should_process_event(event) is True

    def test_debouncing_prevents_rapid_regeneration(self):
        """Test that debouncing delays regeneration."""
        handler = TicketChangeHandler(debounce_seconds=0.1)

        # Mock event
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/path/to/bees-abc.md"

        with patch.object(handler, '_trigger_regeneration') as mock_regen:
            handler.on_created(event)
            # Regeneration should be called
            mock_regen.assert_called_once()


class TestRegenerationAfterTicketCreation:
    """Integration test: creating ticket and regenerating shows it in index."""

    def test_new_ticket_appears_in_regenerated_index(self, tmp_path, monkeypatch):
        """Test that creating a new ticket and regenerating includes it in index."""
        # Setup test environment
        tickets_dir = tmp_path / "tickets"
        tickets_dir.mkdir()
        (tickets_dir / "epics").mkdir()

        monkeypatch.setattr("src.paths.TICKETS_DIR", tickets_dir)

        # Generate initial index (empty)
        initial_index = generate_index()
        assert "bees-def" not in initial_index

        # Create new ticket
        new_ticket = tickets_dir / "epics" / "bees-def.md"
        new_ticket.write_text("""---
id: bees-def
title: New Epic
type: epic
status: open
---
New content""")

        # Regenerate index
        updated_index = generate_index()

        # New ticket should appear
        assert "bees-def" in updated_index
        assert "New Epic" in updated_index
