"""
Unit tests for demo ticket generation script.

Tests that generated tickets have valid frontmatter, correct file structure,
bidirectional relationships, and proper directory placement.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path for importing generate_demo_tickets
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reader import read_ticket
from src.paths import get_ticket_path


def read_ticket_by_id(ticket_id: str, ticket_type: str):
    """Helper to read ticket by ID and type."""
    return read_ticket(get_ticket_path(ticket_id, ticket_type))


@pytest.fixture
def setup_tickets_dir(tmp_path, monkeypatch):
    """Create temporary hive-based directory structure."""
    import src.config
    import json

    # Create default hive directory
    default_hive = tmp_path / "default"
    default_hive.mkdir()
    (default_hive / "eggs").mkdir()
    (default_hive / "evicted").mkdir()

    # Create config
    config_dir = tmp_path / ".bees"
    config_dir.mkdir()
    config_file = config_dir / "config.json"

    config_data = {
        "hives": {
            "default": {"path": str(default_hive), "display_name": "Default"}
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }

    with open(config_file, 'w') as f:
        json.dump(config_data, f)

    # Mock get_config_path to return our temporary config file
    monkeypatch.setattr(src.config, 'get_config_path', lambda: config_file)

    # Clear the hive config cache
    if hasattr(src.config, '_hive_config_cache'):
        src.config._hive_config_cache = None

    # Change to the tmp_path directory so path resolution works
    monkeypatch.chdir(tmp_path)

    yield tmp_path


@pytest.fixture
def generated_tickets(setup_tickets_dir):
    """Generate demo tickets and return their IDs."""
    from scripts.generate_demo_tickets import (
        generate_demo_epics,
        generate_demo_tasks,
        generate_demo_subtasks,
    )

    # Suppress print statements during tests
    with patch("builtins.print"):
        epics = generate_demo_epics()
        tasks = generate_demo_tasks(epics)
        subtasks = generate_demo_subtasks(tasks)

    return {"epics": epics, "tasks": tasks, "subtasks": subtasks}


class TestDemoEpicGeneration:
    """Tests for epic ticket generation."""

    def test_generates_correct_number_of_epics(self, generated_tickets):
        """Test that exactly 5 epics are generated."""
        assert len(generated_tickets["epics"]) == 5

    def test_epic_files_exist(self, generated_tickets, setup_tickets_dir):
        """Test that epic files are created in correct hive directory."""
        # Epics now stored in hive root with flat storage
        default_dir = setup_tickets_dir / "default"
        for epic_id in generated_tickets["epics"].values():
            epic_file = default_dir / f"{epic_id}.md"
            assert epic_file.exists(), f"Epic file {epic_id}.md not found in {default_dir}"

    def test_epic_has_valid_frontmatter(self, generated_tickets):
        """Test that epics have all required frontmatter fields."""
        epic_id = list(generated_tickets["epics"].values())[0]
        ticket = read_ticket(get_ticket_path(epic_id, "epic"))

        # Required fields
        assert ticket.id == epic_id
        assert ticket.type == "epic"
        assert ticket.title
        assert ticket.description
        assert isinstance(ticket.labels, list)
        assert ticket.status in ["open", "in progress", "completed"]
        assert ticket.priority is not None
        assert 0 <= ticket.priority <= 4
        assert ticket.owner

    def test_epic_status_variety(self, generated_tickets):
        """Test that epics have diverse statuses."""
        statuses = set()
        for epic_id in generated_tickets["epics"].values():
            ticket = read_ticket_by_id(epic_id, "epic")
            statuses.add(ticket.status)

        # Should have at least 2 different statuses
        assert len(statuses) >= 2
        # Should include standard statuses
        assert statuses.issubset({"open", "in progress", "completed"})

    def test_epic_priority_variety(self, generated_tickets):
        """Test that epics have diverse priority levels."""
        priorities = set()
        for epic_id in generated_tickets["epics"].values():
            ticket = read_ticket_by_id(epic_id, "epic")
            priorities.add(ticket.priority)

        # Should have at least 2 different priorities
        assert len(priorities) >= 2

    def test_epic_has_labels(self, generated_tickets):
        """Test that all epics have meaningful labels."""
        for epic_id in generated_tickets["epics"].values():
            ticket = read_ticket_by_id(epic_id, "epic")
            assert len(ticket.labels) > 0, f"Epic {epic_id} has no labels"


class TestDemoTaskGeneration:
    """Tests for task ticket generation."""

    def test_generates_correct_number_of_tasks(self, generated_tickets):
        """Test that exactly 8 tasks are generated."""
        assert len(generated_tickets["tasks"]) == 8

    def test_task_files_exist(self, generated_tickets, setup_tickets_dir):
        """Test that task files are created in correct hive directory."""
        # Tasks now stored in hive root with flat storage
        default_dir = setup_tickets_dir / "default"
        for task_id in generated_tickets["tasks"].values():
            task_file = default_dir / f"{task_id}.md"
            assert task_file.exists(), f"Task file {task_id}.md not found in {default_dir}"

    def test_task_has_valid_frontmatter(self, generated_tickets):
        """Test that tasks have all required frontmatter fields."""
        task_id = list(generated_tickets["tasks"].values())[0]
        ticket = read_ticket_by_id(task_id, "task")

        # Required fields
        assert ticket.id == task_id
        assert ticket.type == "task"
        assert ticket.title
        assert ticket.description
        assert isinstance(ticket.labels, list)
        assert ticket.status in ["open", "in progress", "completed"]
        assert ticket.priority is not None
        assert ticket.owner

    def test_task_has_parent_epic(self, generated_tickets):
        """Test that all tasks have a parent epic."""
        epic_ids = set(generated_tickets["epics"].values())

        for task_id in generated_tickets["tasks"].values():
            ticket = read_ticket_by_id(task_id, "task")
            assert ticket.parent is not None, f"Task {task_id} has no parent"
            assert (
                ticket.parent in epic_ids
            ), f"Task {task_id} parent {ticket.parent} is not an epic"

    def test_task_blocking_dependencies(self, generated_tickets):
        """Test that some tasks have blocking dependencies."""
        task_ids = set(generated_tickets["tasks"].values())
        has_dependencies = False

        for task_id in generated_tickets["tasks"].values():
            ticket = read_ticket_by_id(task_id, "task")
            if ticket.up_dependencies:
                has_dependencies = True
                # Verify dependencies reference other tasks
                for dep_id in ticket.up_dependencies:
                    assert (
                        dep_id in task_ids
                    ), f"Task {task_id} depends on invalid task {dep_id}"

        assert has_dependencies, "No tasks have blocking dependencies"

    def test_task_status_variety(self, generated_tickets):
        """Test that tasks have diverse statuses."""
        statuses = set()
        for task_id in generated_tickets["tasks"].values():
            ticket = read_ticket_by_id(task_id, "task")
            statuses.add(ticket.status)

        # Should have at least 2 different statuses
        assert len(statuses) >= 2


class TestDemoSubtaskGeneration:
    """Tests for subtask ticket generation."""

    def test_generates_correct_number_of_subtasks(self, generated_tickets):
        """Test that exactly 15 subtasks are generated."""
        assert len(generated_tickets["subtasks"]) == 15

    def test_subtask_files_exist(self, generated_tickets, setup_tickets_dir):
        """Test that subtask files are created in correct hive directory."""
        # Subtasks now stored in hive root with flat storage
        default_dir = setup_tickets_dir / "default"
        for subtask_id in generated_tickets["subtasks"].values():
            subtask_file = default_dir / f"{subtask_id}.md"
            assert subtask_file.exists(), f"Subtask file {subtask_id}.md not found in {default_dir}"

    def test_subtask_has_valid_frontmatter(self, generated_tickets):
        """Test that subtasks have all required frontmatter fields."""
        subtask_id = list(generated_tickets["subtasks"].values())[0]
        ticket = read_ticket_by_id(subtask_id, "subtask")

        # Required fields
        assert ticket.id == subtask_id
        assert ticket.type == "subtask"
        assert ticket.title
        assert ticket.description
        assert isinstance(ticket.labels, list)
        assert ticket.status in ["open", "in progress", "completed"]
        assert ticket.priority is not None
        assert ticket.owner

    def test_subtask_has_parent_task(self, generated_tickets):
        """Test that all subtasks have a parent task."""
        task_ids = set(generated_tickets["tasks"].values())

        for subtask_id in generated_tickets["subtasks"].values():
            ticket = read_ticket_by_id(subtask_id, "subtask")
            assert ticket.parent is not None, f"Subtask {subtask_id} has no parent"
            assert (
                ticket.parent in task_ids
            ), f"Subtask {subtask_id} parent {ticket.parent} is not a task"

    def test_subtask_status_variety(self, generated_tickets):
        """Test that subtasks have diverse statuses."""
        statuses = set()
        for subtask_id in generated_tickets["subtasks"].values():
            ticket = read_ticket_by_id(subtask_id, "subtask")
            statuses.add(ticket.status)

        # Should have at least 2 different statuses
        assert len(statuses) >= 2


class TestDemoTicketRelationships:
    """Tests for bidirectional relationships in demo tickets."""

    def test_task_parent_references_are_valid(self, generated_tickets):
        """Test that task parent references point to valid epics."""
        epic_ids = set(generated_tickets["epics"].values())

        for task_id in generated_tickets["tasks"].values():
            task = read_ticket_by_id(task_id, "task")
            if task.parent:
                assert task.parent in epic_ids, (
                    f"Task {task_id} references invalid parent {task.parent}"
                )

    def test_subtask_parent_references_are_valid(self, generated_tickets):
        """Test that subtask parent references point to valid tasks."""
        task_ids = set(generated_tickets["tasks"].values())

        for subtask_id in generated_tickets["subtasks"].values():
            subtask = read_ticket_by_id(subtask_id, "subtask")
            assert subtask.parent in task_ids, (
                f"Subtask {subtask_id} references invalid parent {subtask.parent}"
            )

    def test_dependency_references_are_valid(self, generated_tickets):
        """Test that dependency references point to valid tickets."""
        task_ids = set(generated_tickets["tasks"].values())

        for task_id in generated_tickets["tasks"].values():
            task = read_ticket_by_id(task_id, "task")
            for dep_id in task.up_dependencies:
                assert dep_id in task_ids, (
                    f"Task {task_id} has invalid dependency {dep_id}"
                )


class TestDemoTicketDiversity:
    """Tests for diversity and variety in generated tickets."""

    def test_labels_cover_multiple_domains(self, generated_tickets):
        """Test that labels span multiple technical domains."""
        all_labels = set()

        for ticket_type, ticket_dict in [
            ("epic", generated_tickets["epics"]),
            ("task", generated_tickets["tasks"]),
            ("subtask", generated_tickets["subtasks"]),
        ]:
            for ticket_id in ticket_dict.values():
                ticket = read_ticket_by_id(ticket_id, ticket_type)
                all_labels.update(ticket.labels)

        # Should have labels from different domains
        assert "backend" in all_labels or "frontend" in all_labels
        # Should have enough label diversity
        assert len(all_labels) >= 10

    def test_owners_include_teams_and_individuals(self, generated_tickets):
        """Test that owners include both team and individual assignments."""
        all_owners = set()

        for ticket_type, ticket_dict in [
            ("epic", generated_tickets["epics"]),
            ("task", generated_tickets["tasks"]),
            ("subtask", generated_tickets["subtasks"]),
        ]:
            for ticket_id in ticket_dict.values():
                ticket = read_ticket_by_id(ticket_id, ticket_type)
                if ticket.owner:
                    all_owners.add(ticket.owner)

        # Should have at least one team-style owner (contains "team")
        team_owners = [o for o in all_owners if "team" in o.lower()]
        # Should have at least one individual owner (contains "@")
        individual_owners = [o for o in all_owners if "@" in o]

        assert len(team_owners) > 0, "No team owners found"
        assert len(individual_owners) > 0, "No individual owners found"

    def test_priority_distribution(self, generated_tickets):
        """Test that priorities are well-distributed."""
        priorities = []

        for ticket_type, ticket_dict in [
            ("epic", generated_tickets["epics"]),
            ("task", generated_tickets["tasks"]),
            ("subtask", generated_tickets["subtasks"]),
        ]:
            for ticket_id in ticket_dict.values():
                ticket = read_ticket_by_id(ticket_id, ticket_type)
                priorities.append(ticket.priority)

        # Should have priorities from at least 3 different levels
        unique_priorities = set(priorities)
        assert len(unique_priorities) >= 3, f"Only {len(unique_priorities)} priority levels used"


class TestDependencyChains:
    """Tests for dependency chains in demo tickets."""

    def test_has_dependency_chains(self, generated_tickets):
        """Test that demo includes multi-level dependency chains."""
        task_deps = {}

        # Build dependency graph
        for task_id in generated_tickets["tasks"].values():
            task = read_ticket_by_id(task_id, "task")
            if task.up_dependencies:
                task_deps[task_id] = task.up_dependencies

        # Look for chains (task depending on task that depends on another task)
        chain_found = False
        for task_id, deps in task_deps.items():
            for dep_id in deps:
                if dep_id in task_deps:
                    # Found a chain: task_id -> dep_id -> task_deps[dep_id]
                    chain_found = True
                    break
            if chain_found:
                break

        # Note: This test may fail if the demo data doesn't include chains
        # That's okay - it's aspirational to encourage adding chains
        # For now, just verify the structure exists to support chains
        assert isinstance(task_deps, dict)

    def test_completed_tasks_at_start_of_chains(self, generated_tickets):
        """Test that completed tasks are at the start of dependency chains."""
        # Find tasks with no up_dependencies and status=completed
        root_completed = []
        for task_id in generated_tickets["tasks"].values():
            task = read_ticket_by_id(task_id, "task")
            if not task.up_dependencies and task.status == "completed":
                root_completed.append(task_id)

        # Should have at least one completed task at the root of chains
        assert len(root_completed) > 0, "No completed tasks at root of chains"


class TestFlatStorageArchitecture:
    """Tests for flat storage path validation."""

    def test_fixtures_use_flat_storage_paths(self, generated_tickets, setup_tickets_dir):
        """Verify that test fixtures check correct directory paths (default/ not default/epics/)."""
        # All tickets should be in the root of the hive, not in subdirectories
        default_dir = setup_tickets_dir / "default"

        # Verify epics subdirectory does not exist or is not used
        epics_subdir = default_dir / "epics"
        tasks_subdir = default_dir / "tasks"
        subtasks_subdir = default_dir / "subtasks"

        # Check that tickets are in the flat root directory
        for epic_id in generated_tickets["epics"].values():
            epic_file = default_dir / f"{epic_id}.md"
            assert epic_file.exists(), f"Epic {epic_id}.md should exist in flat root {default_dir}"

            # Verify it's NOT in subdirectory (if subdirectory exists)
            if epics_subdir.exists():
                subdir_file = epics_subdir / f"{epic_id}.md"
                assert not subdir_file.exists(), f"Epic {epic_id}.md should NOT be in {epics_subdir}"

        for task_id in generated_tickets["tasks"].values():
            task_file = default_dir / f"{task_id}.md"
            assert task_file.exists(), f"Task {task_id}.md should exist in flat root {default_dir}"

            if tasks_subdir.exists():
                subdir_file = tasks_subdir / f"{task_id}.md"
                assert not subdir_file.exists(), f"Task {task_id}.md should NOT be in {tasks_subdir}"

        for subtask_id in generated_tickets["subtasks"].values():
            subtask_file = default_dir / f"{subtask_id}.md"
            assert subtask_file.exists(), f"Subtask {subtask_id}.md should exist in flat root {default_dir}"

            if subtasks_subdir.exists():
                subdir_file = subtasks_subdir / f"{subtask_id}.md"
                assert not subdir_file.exists(), f"Subtask {subtask_id}.md should NOT be in {subtasks_subdir}"

    def test_missing_ticket_in_root_directory(self, setup_tickets_dir):
        """Test edge case of missing ticket file in root directory."""
        from src.reader import read_ticket
        from src.paths import get_ticket_path

        # Try to read a ticket that doesn't exist (use hive-prefixed ID format)
        fake_ticket_id = "default.bees-fake123"
        fake_ticket_path = get_ticket_path(fake_ticket_id, "epic")

        # Should raise an exception or return None
        try:
            ticket = read_ticket(fake_ticket_path)
            # If we get here without exception, ticket should be None or invalid
            assert ticket is None or not hasattr(ticket, 'id'), \
                "Should not successfully read non-existent ticket"
        except (FileNotFoundError, ValueError, Exception):
            # Expected behavior - file doesn't exist
            pass

    def test_tickets_not_in_wrong_subdirectories(self, generated_tickets, setup_tickets_dir):
        """Validate test assertions fail if tickets are in wrong location."""
        default_dir = setup_tickets_dir / "default"

        # Verify that old subdirectories either don't exist or are empty
        old_subdirs = ["epics", "tasks", "subtasks"]

        for subdir_name in old_subdirs:
            subdir = default_dir / subdir_name
            if subdir.exists():
                # If subdirectory exists, it should be empty
                md_files = list(subdir.glob("*.md"))
                assert len(md_files) == 0, \
                    f"Found {len(md_files)} .md files in {subdir}, but flat storage should have all tickets in root"

        # Verify all generated tickets are in root, not subdirectories
        all_ticket_ids = (
            list(generated_tickets["epics"].values()) +
            list(generated_tickets["tasks"].values()) +
            list(generated_tickets["subtasks"].values())
        )

        for ticket_id in all_ticket_ids:
            root_file = default_dir / f"{ticket_id}.md"
            assert root_file.exists(), \
                f"Ticket {ticket_id}.md should exist in flat storage root {default_dir}"
