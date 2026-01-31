"""Unit tests for sample ticket creation and validation."""

from pathlib import Path

import pytest

from src.parser import parse_frontmatter
from src.reader import read_ticket
from src.validator import validate_ticket, ValidationError


class TestSampleTicketStructure:
    """Test that sample tickets have correct YAML frontmatter structure."""

    def test_sample_epic_has_valid_yaml(self):
        """Sample epic should have valid YAML frontmatter."""
        sample_path = Path("tickets/epics/sample-epic.md")
        if not sample_path.exists():
            pytest.skip("Sample epic not created yet")

        frontmatter, body = parse_frontmatter(sample_path)

        # Verify YAML parsed successfully (no errors)
        assert isinstance(frontmatter, dict)
        assert len(frontmatter) > 0

        # Verify basic structure
        assert "id" in frontmatter
        assert "type" in frontmatter
        assert "title" in frontmatter

    def test_sample_task_has_valid_yaml(self):
        """Sample task should have valid YAML frontmatter."""
        sample_path = Path("tickets/tasks/sample-task.md")
        if not sample_path.exists():
            pytest.skip("Sample task not created yet")

        frontmatter, body = parse_frontmatter(sample_path)

        assert isinstance(frontmatter, dict)
        assert len(frontmatter) > 0
        assert "id" in frontmatter
        assert "type" in frontmatter
        assert "title" in frontmatter

    def test_sample_subtask_has_valid_yaml(self):
        """Sample subtask should have valid YAML frontmatter."""
        sample_path = Path("tickets/subtasks/sample-subtask.md")
        if not sample_path.exists():
            pytest.skip("Sample subtask not created yet")

        frontmatter, body = parse_frontmatter(sample_path)

        assert isinstance(frontmatter, dict)
        assert len(frontmatter) > 0
        assert "id" in frontmatter
        assert "type" in frontmatter
        assert "title" in frontmatter


class TestSampleTicketRequiredFields:
    """Test that all required fields are present for each ticket type."""

    def test_epic_has_all_required_fields(self):
        """Sample epic should have id, type, and title."""
        sample_path = Path("tickets/epics/sample-epic.md")
        if not sample_path.exists():
            pytest.skip("Sample epic not created yet")

        frontmatter, _ = parse_frontmatter(sample_path)

        # Required fields
        assert frontmatter["id"]
        assert frontmatter["type"] == "epic"
        assert frontmatter["title"]

        # Validate against schema
        validate_ticket(frontmatter)  # Should not raise

    def test_task_has_all_required_fields(self):
        """Sample task should have id, type, title, and parent."""
        sample_path = Path("tickets/tasks/sample-task.md")
        if not sample_path.exists():
            pytest.skip("Sample task not created yet")

        frontmatter, _ = parse_frontmatter(sample_path)

        assert frontmatter["id"]
        assert frontmatter["type"] == "task"
        assert frontmatter["title"]
        assert "parent" in frontmatter  # Optional for tasks

        validate_ticket(frontmatter)

    def test_subtask_has_all_required_fields(self):
        """Sample subtask should have id, type, title, and parent (required)."""
        sample_path = Path("tickets/subtasks/sample-subtask.md")
        if not sample_path.exists():
            pytest.skip("Sample subtask not created yet")

        frontmatter, _ = parse_frontmatter(sample_path)

        assert frontmatter["id"]
        assert frontmatter["type"] == "subtask"
        assert frontmatter["title"]
        assert frontmatter["parent"]  # Required for subtasks

        validate_ticket(frontmatter)


class TestSampleTicketRelationships:
    """Test that parent/children relationships are correctly established."""

    def test_task_references_epic_as_parent(self):
        """Sample task should reference sample epic as parent."""
        task_path = Path("tickets/tasks/sample-task.md")
        epic_path = Path("tickets/epics/sample-epic.md")

        if not task_path.exists() or not epic_path.exists():
            pytest.skip("Sample tickets not created yet")

        task_fm, _ = parse_frontmatter(task_path)
        epic_fm, _ = parse_frontmatter(epic_path)

        # Task should reference epic as parent
        assert task_fm.get("parent") == epic_fm["id"]

    def test_subtask_references_task_as_parent(self):
        """Sample subtask should reference sample task as parent."""
        subtask_path = Path("tickets/subtasks/sample-subtask.md")
        task_path = Path("tickets/tasks/sample-task.md")

        if not subtask_path.exists() or not task_path.exists():
            pytest.skip("Sample tickets not created yet")

        subtask_fm, _ = parse_frontmatter(subtask_path)
        task_fm, _ = parse_frontmatter(task_path)

        # Subtask should reference task as parent
        assert subtask_fm["parent"] == task_fm["id"]

    def test_children_field_is_list(self):
        """Children field should be a list if present."""
        for sample_file in [
            "tickets/epics/sample-epic.md",
            "tickets/tasks/sample-task.md",
        ]:
            path = Path(sample_file)
            if not path.exists():
                continue

            frontmatter, _ = parse_frontmatter(path)
            if "children" in frontmatter:
                assert isinstance(frontmatter["children"], list)


class TestSampleTicketDependencies:
    """Test that dependency links are properly formatted."""

    def test_dependency_fields_are_lists(self):
        """up_dependencies and down_dependencies should be lists."""
        for sample_file in [
            "tickets/epics/sample-epic.md",
            "tickets/tasks/sample-task.md",
            "tickets/subtasks/sample-subtask.md",
        ]:
            path = Path(sample_file)
            if not path.exists():
                continue

            frontmatter, _ = parse_frontmatter(path)

            if "up_dependencies" in frontmatter:
                assert isinstance(frontmatter["up_dependencies"], list)

            if "down_dependencies" in frontmatter:
                assert isinstance(frontmatter["down_dependencies"], list)

    def test_dependency_items_are_strings(self):
        """Dependency lists should contain only strings (ticket IDs)."""
        for sample_file in [
            "tickets/epics/sample-epic.md",
            "tickets/tasks/sample-task.md",
            "tickets/subtasks/sample-subtask.md",
        ]:
            path = Path(sample_file)
            if not path.exists():
                continue

            frontmatter, _ = parse_frontmatter(path)

            for dep_list in [
                frontmatter.get("up_dependencies", []),
                frontmatter.get("down_dependencies", []),
            ]:
                for dep_id in dep_list:
                    assert isinstance(dep_id, str)


class TestSampleTicketFileLocation:
    """Test that files are written to correct directories."""

    def test_epic_in_epics_directory(self):
        """Sample epic should be in tickets/epics/."""
        epic_path = Path("tickets/epics/sample-epic.md")
        if not epic_path.exists():
            pytest.skip("Sample epic not created yet")

        assert epic_path.parent.name == "epics"
        assert epic_path.exists()

    def test_task_in_tasks_directory(self):
        """Sample task should be in tickets/tasks/."""
        task_path = Path("tickets/tasks/sample-task.md")
        if not task_path.exists():
            pytest.skip("Sample task not created yet")

        assert task_path.parent.name == "tasks"
        assert task_path.exists()

    def test_subtask_in_subtasks_directory(self):
        """Sample subtask should be in tickets/subtasks/."""
        subtask_path = Path("tickets/subtasks/sample-subtask.md")
        if not subtask_path.exists():
            pytest.skip("Sample subtask not created yet")

        assert subtask_path.parent.name == "subtasks"
        assert subtask_path.exists()


class TestSampleTicketReaderIntegration:
    """Test that sample tickets can be read back using reader module."""

    def test_read_sample_epic(self):
        """Reader should successfully parse sample epic."""
        epic_path = Path("tickets/epics/sample-epic.md")
        if not epic_path.exists():
            pytest.skip("Sample epic not created yet")

        epic = read_ticket(epic_path)

        assert epic.id
        assert epic.type == "epic"
        assert epic.title
        assert isinstance(epic.labels, list)

    def test_read_sample_task(self):
        """Reader should successfully parse sample task."""
        task_path = Path("tickets/tasks/sample-task.md")
        if not task_path.exists():
            pytest.skip("Sample task not created yet")

        task = read_ticket(task_path)

        assert task.id
        assert task.type == "task"
        assert task.title
        assert isinstance(task.labels, list)

    def test_read_sample_subtask(self):
        """Reader should successfully parse sample subtask."""
        subtask_path = Path("tickets/subtasks/sample-subtask.md")
        if not subtask_path.exists():
            pytest.skip("Sample subtask not created yet")

        subtask = read_ticket(subtask_path)

        assert subtask.id
        assert subtask.type == "subtask"
        assert subtask.title
        assert subtask.parent  # Required for subtasks
        assert isinstance(subtask.labels, list)

    def test_all_samples_parse_without_errors(self):
        """All sample tickets should parse successfully."""
        sample_files = [
            "tickets/epics/sample-epic.md",
            "tickets/tasks/sample-task.md",
            "tickets/subtasks/sample-subtask.md",
        ]

        for sample_file in sample_files:
            path = Path(sample_file)
            if not path.exists():
                continue

            # Should not raise any exceptions
            ticket = read_ticket(path)
            assert ticket is not None


class TestSampleTicketEdgeCases:
    """Test edge cases and validation errors."""

    def test_missing_fields_would_fail_validation(self):
        """Verify that missing required fields would fail validation."""
        # Test that our validator catches missing fields
        with pytest.raises(ValidationError, match="Missing required field"):
            validate_ticket({"type": "epic", "title": "Test"})  # Missing id

        with pytest.raises(ValidationError, match="Missing required field"):
            validate_ticket({"id": "bees-123", "title": "Test"})  # Missing type

        with pytest.raises(ValidationError, match="Missing required field"):
            validate_ticket({"id": "bees-123", "type": "epic"})  # Missing title

    def test_subtask_without_parent_fails_validation(self):
        """Subtask without parent should fail validation."""
        with pytest.raises(ValidationError, match="Subtask must have a parent"):
            validate_ticket({
                "id": "bees-123",
                "type": "subtask",
                "title": "Test Subtask",
            })

    def test_invalid_id_format_fails_validation(self):
        """Invalid ID format should fail validation."""
        with pytest.raises(ValidationError, match="Invalid ID format"):
            validate_ticket({
                "id": "invalid-id",
                "type": "epic",
                "title": "Test",
            })

    def test_invalid_type_fails_validation(self):
        """Invalid ticket type should fail validation."""
        with pytest.raises(ValidationError, match="Invalid type"):
            validate_ticket({
                "id": "bees-123",
                "type": "invalid_type",
                "title": "Test",
            })

    def test_malformed_yaml_would_raise_parse_error(self):
        """Malformed YAML should raise ParseError during parsing."""
        from src.parser import ParseError

        # Create a temporary file with malformed YAML
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\n")
            f.write("id: bees-123\n")
            f.write("type: epic\n")
            f.write("title: Test\n")
            f.write("labels: [unclosed array\n")  # Malformed YAML
            f.write("---\n")
            temp_path = f.name

        try:
            with pytest.raises(ParseError):
                parse_frontmatter(temp_path)
        finally:
            Path(temp_path).unlink()
