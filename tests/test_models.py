"""Unit tests for ticket models."""

import pytest
from src.models import Ticket, Epic, Task, Subtask


class TestTicketModel:
    """Tests for Ticket dataclass."""

    def test_ticket_accepts_bees_version(self):
        """Ticket model should accept bees_version field."""
        ticket = Ticket(
            id="default.bees-abc",
            type="task",
            title="Test Ticket",
            bees_version='1.1'
        )

        assert ticket.bees_version == '1.1'

    def test_ticket_bees_version_defaults_to_none(self):
        """bees_version field should default to None for backward compatibility."""
        ticket = Ticket(
            id="default.bees-abc",
            type="task",
            title="Test Ticket"
        )

        assert ticket.bees_version is None


class TestEpicModel:
    """Tests for Epic model."""

    def test_epic_accepts_bees_version(self):
        """Epic model should accept and preserve bees_version field."""
        epic = Epic(
            id="default.bees-250",
            type="epic",
            title="Test Epic",
            bees_version='1.1'
        )

        assert epic.bees_version == '1.1'
        assert epic.type == "epic"  # Verify __post_init__ still works


class TestTaskModel:
    """Tests for Task model."""

    def test_task_accepts_bees_version(self):
        """Task model should accept and preserve bees_version field."""
        task = Task(
            id="default.bees-jty",
            type="task",
            title="Test Task",
            bees_version='1.1'
        )

        assert task.bees_version == '1.1'
        assert task.type == "task"  # Verify __post_init__ still works


class TestSubtaskModel:
    """Tests for Subtask model."""

    def test_subtask_accepts_bees_version(self):
        """Subtask model should accept and preserve bees_version field."""
        subtask = Subtask(
            id="default.bees-xyz",
            type="subtask",
            title="Test Subtask",
            parent="default.bees-jty",
            bees_version='1.1'
        )

        assert subtask.bees_version == '1.1'
        assert subtask.type == "subtask"  # Verify __post_init__ still works

    def test_subtask_requires_parent(self):
        """Subtask must have a parent, even with bees_version field."""
        with pytest.raises(ValueError, match="Subtask must have a parent"):
            Subtask(
                id="default.bees-xyz",
                type="subtask",
                title="Test Subtask",
                bees_version='1.1'
            )
