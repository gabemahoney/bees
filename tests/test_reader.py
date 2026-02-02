"""Unit tests for ticket reader and parser."""

import pytest
from pathlib import Path
from datetime import datetime

from src.reader import read_ticket
from src.parser import parse_frontmatter, ParseError
from src.validator import validate_ticket, validate_id_format, ValidationError
from src.models import Epic, Task, Subtask


class TestParseFrontmatter:
    """Tests for frontmatter parsing."""

    def test_parse_valid_frontmatter(self, tmp_path):
        """Should successfully parse valid YAML frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: epic
title: Test Epic
---

This is the body.""")

        frontmatter, body = parse_frontmatter(file_path)

        assert frontmatter["id"] == "default.bees-250"
        assert frontmatter["type"] == "epic"
        assert frontmatter["title"] == "Test Epic"
        assert body == "This is the body."

    def test_parse_with_lists(self, tmp_path):
        """Should parse lists in frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-abc
type: task
title: Test Task
labels:
  - open
  - p0
children:
  - default.bees-xyz
---

Body text.""")

        frontmatter, body = parse_frontmatter(file_path)

        assert frontmatter["labels"] == ["open", "p0"]
        assert frontmatter["children"] == ["default.bees-xyz"]

    def test_missing_frontmatter_raises_error(self, tmp_path):
        """Should raise error if no frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text("Just plain text")

        with pytest.raises(ParseError, match="does not start with"):
            parse_frontmatter(file_path)

    def test_malformed_yaml_raises_error(self, tmp_path):
        """Should raise error on invalid YAML."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
title: [invalid yaml: unclosed
---

Body.""")

        with pytest.raises(ParseError, match="Failed to parse YAML"):
            parse_frontmatter(file_path)

    def test_missing_closing_delimiter(self, tmp_path):
        """Should raise error if closing --- is missing."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: epic

Body without closing delimiter.""")

        with pytest.raises(ParseError, match="invalid frontmatter format"):
            parse_frontmatter(file_path)

    def test_nonexistent_file_raises_error(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        file_path = tmp_path / "nonexistent.md"

        with pytest.raises(FileNotFoundError):
            parse_frontmatter(file_path)


class TestValidateTicket:
    """Tests for ticket validation."""

    def test_validate_valid_epic(self):
        """Should pass validation for valid epic."""
        data = {
            "id": "default.bees-250",
            "type": "epic",
            "title": "Test Epic",
            "labels": ["open"],
            "children": ["default.bees-abc"]
        }

        # Should not raise
        validate_ticket(data)

    def test_validate_valid_task(self):
        """Should pass validation for valid task."""
        data = {
            "id": "default.bees-jty",
            "type": "task",
            "title": "Test Task",
            "parent": "default.bees-250"
        }

        validate_ticket(data)

    def test_validate_valid_subtask(self):
        """Should pass validation for valid subtask with parent."""
        data = {
            "id": "default.bees-xyz",
            "type": "subtask",
            "title": "Test Subtask",
            "parent": "default.bees-jty"
        }

        validate_ticket(data)

    def test_missing_required_field_raises_error(self):
        """Should raise error if required field missing."""
        data = {"id": "default.bees-250", "title": "Missing type"}

        with pytest.raises(ValidationError, match="Missing required field: type"):
            validate_ticket(data)

    def test_invalid_type_raises_error(self):
        """Should raise error for invalid type enum."""
        data = {"id": "default.bees-250", "type": "invalid", "title": "Test"}

        with pytest.raises(ValidationError, match="Invalid type"):
            validate_ticket(data)

    def test_invalid_id_format_raises_error(self):
        """Should raise error for invalid ID format."""
        data = {"id": "INVALID-ID", "type": "epic", "title": "Test"}

        with pytest.raises(ValidationError, match="Invalid ID format"):
            validate_ticket(data)

    def test_subtask_without_parent_raises_error(self):
        """Should raise error if subtask has no parent."""
        data = {"id": "default.bees-xyz", "type": "subtask", "title": "Test"}

        with pytest.raises(ValidationError, match="Subtask must have a parent"):
            validate_ticket(data)

    def test_labels_must_be_list(self):
        """Should raise error if labels is not a list."""
        data = {
            "id": "default.bees-250",
            "type": "epic",
            "title": "Test",
            "labels": "not-a-list"
        }

        with pytest.raises(ValidationError, match="must be list"):
            validate_ticket(data)


class TestValidateIdFormat:
    """Tests for ID format validation."""

    def test_valid_ids(self):
        """Should accept valid ID formats."""
        assert validate_id_format("default.bees-250")
        assert validate_id_format("default.bees-abc")
        assert validate_id_format("default.bees-9pw")
        assert validate_id_format("default.bees-jty")

    def test_invalid_ids(self):
        """Should reject invalid ID formats."""
        assert not validate_id_format("bees-UPPER")
        assert not validate_id_format("invalid-250")
        assert not validate_id_format("bees-")
        assert not validate_id_format("bees-toolong")
        assert not validate_id_format("250")


class TestReadTicket:
    """Tests for read_ticket function."""

    def test_read_epic(self, tmp_path):
        """Should read and return Epic object."""
        file_path = tmp_path / "test-epic.md"
        file_path.write_text("""---
id: default.bees-250
type: epic
title: Core Schema
bees_version: '1.1'
labels:
  - open
  - p0
children:
  - default.bees-jty
---

Implementation of the core schema.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket, Epic)
        assert ticket.id == "default.bees-250"
        assert ticket.type == "epic"
        assert ticket.title == "Core Schema"
        assert ticket.labels == ["open", "p0"]
        assert ticket.children == ["default.bees-jty"]
        assert "Implementation of the core schema" in ticket.description

    def test_read_task(self, tmp_path):
        """Should read and return Task object."""
        file_path = tmp_path / "test-task.md"
        file_path.write_text("""---
id: default.bees-jty
type: task
title: Design Schema
bees_version: '1.1'
parent: default.bees-250
up_dependencies:
  - default.bees-abc
---

Design the ticket schema.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket, Task)
        assert ticket.id == "default.bees-jty"
        assert ticket.type == "task"
        assert ticket.parent == "default.bees-250"
        assert ticket.up_dependencies == ["default.bees-abc"]

    def test_read_subtask(self, tmp_path):
        """Should read and return Subtask object."""
        file_path = tmp_path / "test-subtask.md"
        file_path.write_text("""---
id: default.bees-xyz
type: subtask
title: Write code
bees_version: '1.1'
parent: default.bees-jty
---

Write the implementation.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket, Subtask)
        assert ticket.id == "default.bees-xyz"
        assert ticket.type == "subtask"
        assert ticket.parent == "default.bees-jty"

    def test_read_with_datetime(self, tmp_path):
        """Should parse datetime fields."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: epic
title: Test
bees_version: '1.1'
created_at: 2026-01-30T10:00:00
---

Body.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket.created_at, datetime)
        assert ticket.created_at.year == 2026

    def test_invalid_file_raises_error(self, tmp_path):
        """Should raise error for invalid files."""
        file_path = tmp_path / "test.md"
        file_path.write_text("Invalid content")

        with pytest.raises(ParseError):
            read_ticket(file_path)

    def test_validation_error_on_invalid_data(self, tmp_path):
        """Should raise ValidationError for schema violations."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: INVALID-ID
type: epic
title: Test
---

Body.""")

        with pytest.raises(ValidationError):
            read_ticket(file_path)

    def test_read_with_extra_fields(self, tmp_path):
        """Should ignore extra fields not in Ticket model."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: epic
title: Test Epic
bees_version: '1.1'
custom_field: some_value
another_extra: 123
labels:
  - open
---

Body text.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket, Epic)
        assert ticket.id == "default.bees-250"
        assert ticket.title == "Test Epic"
        assert ticket.labels == ["open"]
        # Extra fields should be filtered out
        assert not hasattr(ticket, "custom_field")
        assert not hasattr(ticket, "another_extra")

    def test_read_with_bees_version(self, tmp_path):
        """Should parse and preserve bees_version field."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: epic
title: Versioned Epic
bees_version: '1.1'
---

Epic with schema version.""")

        ticket = read_ticket(file_path)

        assert isinstance(ticket, Epic)
        assert ticket.bees_version == '1.1'

    def test_read_without_bees_version_raises_error(self, tmp_path):
        """Should raise ValidationError for tickets without bees_version field."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: task
title: Task Without Version
---

Task without schema version.""")

        with pytest.raises(ValidationError, match="missing 'bees_version' field"):
            read_ticket(file_path)

    def test_bees_version_validation_error_message(self, tmp_path):
        """Should provide clear error message when bees_version is missing."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-abc
type: epic
title: Epic Without Version
---

Body content.""")

        with pytest.raises(ValidationError) as exc_info:
            read_ticket(file_path)

        assert "not a valid Bees ticket" in str(exc_info.value)
        assert "bees_version" in str(exc_info.value)

    def test_bees_version_preserved_through_read_write_cycle(self, tmp_path):
        """Should preserve bees_version field through read/write cycle."""
        file_path = tmp_path / "test.md"
        file_path.write_text("""---
id: default.bees-250
type: task
title: Test Task
bees_version: '1.1'
parent: default.bees-abc
---

Task description.""")

        ticket = read_ticket(file_path)

        # Verify bees_version is preserved
        assert ticket.bees_version == '1.1'
        assert isinstance(ticket, Task)
        assert ticket.id == "default.bees-250"
