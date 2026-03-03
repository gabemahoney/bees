"""Unit tests for validator per-hive child_tiers support."""

import pytest

from src.repo_context import repo_root_context
from src.validator import ValidationError, validate_child_tier_parent, validate_ticket_type
from tests.conftest import write_scoped_config


@pytest.fixture(autouse=True)
def setup_repo_context(tmp_path):
    """Set repo_root context to tmp_path for all tests."""
    with repo_root_context(tmp_path):
        yield


class TestValidateTicketTypeWithHiveName:
    """Test validate_ticket_type with hive_name parameter for per-hive child_tiers."""

    def test_validate_with_hive_name_resolves_hive_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type uses hive-level child_tiers when hive_name provided."""
        # Setup: scope has no child_tiers, but hive "backend" has t1+t2
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
            "child_tiers": {},  # Scope is bees-only
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: "bee" is always valid
        validate_ticket_type("bee", hive_name="backend")

        # Test: tier IDs from hive config are valid
        validate_ticket_type("t1", hive_name="backend")
        validate_ticket_type("t2", hive_name="backend")

        # Test: friendly names from hive config are valid
        validate_ticket_type("Epic", hive_name="backend")
        validate_ticket_type("Epics", hive_name="backend")
        validate_ticket_type("Task", hive_name="backend")
        validate_ticket_type("Tasks", hive_name="backend")

        # Test: types not in hive config are invalid
        with pytest.raises(ValidationError, match="Invalid type: t3"):
            validate_ticket_type("t3", hive_name="backend")

    def test_validate_with_hive_name_bees_only_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type with hive having child_tiers={} (bees-only)."""
        # Setup: hive "docs" is explicitly bees-only (child_tiers={})
        scope_data = {
            "hives": {
                "docs": {
                    "path": "tickets/docs/",
                    "display_name": "Docs",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},  # Explicitly bees-only
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: "bee" is valid
        validate_ticket_type("bee", hive_name="docs")

        # Test: all child tiers are invalid (bees-only hive)
        with pytest.raises(ValidationError, match="Invalid type: t1"):
            validate_ticket_type("t1", hive_name="docs")

        with pytest.raises(ValidationError, match="Invalid type: Task"):
            validate_ticket_type("Task", hive_name="docs")

    def test_validate_with_hive_name_fallback_to_scope(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type falls back to scope-level child_tiers when hive has None."""
        # Setup: hive "frontend" has no child_tiers (None), scope has t1
        scope_data = {
            "hives": {
                "frontend": {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    # No child_tiers key → falls through to scope level
                },
            },
            "child_tiers": {
                "t1": ["Story", "Stories"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: uses scope-level child_tiers
        validate_ticket_type("bee", hive_name="frontend")
        validate_ticket_type("t1", hive_name="frontend")
        validate_ticket_type("Story", hive_name="frontend")
        validate_ticket_type("Stories", hive_name="frontend")

        # Test: t2 not in scope config
        with pytest.raises(ValidationError, match="Invalid type: t2"):
            validate_ticket_type("t2", hive_name="frontend")

    def test_validate_with_hive_name_multiple_hives_different_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type resolves different child_tiers per hive."""
        # Setup: two hives with different child_tiers
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                    },
                },
                "frontend": {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Story", "Stories"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test backend: only t1/Epic valid
        validate_ticket_type("t1", hive_name="backend")
        validate_ticket_type("Epic", hive_name="backend")

        with pytest.raises(ValidationError, match="Invalid type: t2"):
            validate_ticket_type("t2", hive_name="backend")

        with pytest.raises(ValidationError, match="Invalid type: Story"):
            validate_ticket_type("Story", hive_name="backend")

        # Test frontend: t1, t2, Story, Task all valid
        validate_ticket_type("t1", hive_name="frontend")
        validate_ticket_type("t2", hive_name="frontend")
        validate_ticket_type("Story", hive_name="frontend")
        validate_ticket_type("Task", hive_name="frontend")

        # Test frontend: Epic not valid (only in backend)
        with pytest.raises(ValidationError, match="Invalid type: Epic"):
            validate_ticket_type("Epic", hive_name="frontend")


class TestValidateTicketTypeBackwardCompat:
    """Test validate_ticket_type backward compatibility (no hive_name parameter)."""

    def test_validate_without_hive_name_uses_scope_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type without hive_name uses scope-level child_tiers."""
        # Setup: scope has t1+t2
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Epic", "Epics"],
                "t2": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: scope-level child_tiers are used
        validate_ticket_type("bee")  # No hive_name
        validate_ticket_type("t1")
        validate_ticket_type("t2")
        validate_ticket_type("Epic")
        validate_ticket_type("Task")

        # Test: t3 not in scope config
        with pytest.raises(ValidationError, match="Invalid type: t3"):
            validate_ticket_type("t3")

    def test_validate_without_hive_name_scope_none_defaults_to_empty(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type without hive_name when scope child_tiers is None."""
        # Setup: scope has no child_tiers (None → should default to {})
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            # No child_tiers key → None → defaults to {}
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: only "bee" is valid (bees-only fallback)
        validate_ticket_type("bee")

        # Test: all child tiers are invalid
        with pytest.raises(ValidationError, match="Invalid type: t1"):
            validate_ticket_type("t1")

    def test_validate_without_hive_name_no_config_defaults_to_empty(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type without hive_name when no config exists."""
        # Setup: no config file at all
        # (mock_global_bees_dir is empty)

        # Test: only "bee" is valid (bees-only fallback)
        validate_ticket_type("bee")

        # Test: all child tiers are invalid
        with pytest.raises(ValidationError, match="Invalid type: t1"):
            validate_ticket_type("t1")


class TestValidateChildTierParentWithHiveName:
    """Test validate_child_tier_parent with hive_name parameter for per-hive child_tiers."""

    def test_validate_with_hive_name_child_tier_requires_parent(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent enforces parent requirement for hive child tiers."""
        # Setup: hive "backend" has t1+t2
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: bee never requires parent
        validate_child_tier_parent({"type": "bee"}, hive_name="backend")
        validate_child_tier_parent({"type": "bee", "parent": None}, hive_name="backend")

        # Test: child tiers require parent (tier IDs)
        with pytest.raises(ValidationError, match="t1 must have a parent"):
            validate_child_tier_parent({"type": "t1"}, hive_name="backend")

        with pytest.raises(ValidationError, match="t2 must have a parent"):
            validate_child_tier_parent({"type": "t2", "parent": None}, hive_name="backend")

        # Test: child tiers require parent (friendly names)
        with pytest.raises(ValidationError, match="Epic must have a parent"):
            validate_child_tier_parent({"type": "Epic"}, hive_name="backend")

        with pytest.raises(ValidationError, match="Task must have a parent"):
            validate_child_tier_parent({"type": "Task", "parent": ""}, hive_name="backend")

        # Test: child tiers with parent are valid
        validate_child_tier_parent({"type": "t1", "parent": "b.Abc"}, hive_name="backend")
        validate_child_tier_parent({"type": "Epic", "parent": "b.Xyz"}, hive_name="backend")

    def test_validate_with_hive_name_bees_only_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent with bees-only hive (child_tiers={})."""
        # Setup: hive "docs" is bees-only
        scope_data = {
            "hives": {
                "docs": {
                    "path": "tickets/docs/",
                    "display_name": "Docs",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: bee never requires parent
        validate_child_tier_parent({"type": "bee"}, hive_name="docs")

        # Test: unknown types don't trigger parent requirement (not a child tier)
        # This should NOT raise ValidationError from validate_child_tier_parent
        # (It might fail in validate_ticket_type, but that's not this function's job)
        validate_child_tier_parent({"type": "t1"}, hive_name="docs")  # Not a child tier in this hive

    def test_validate_with_hive_name_fallback_to_scope(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent falls back to scope-level child_tiers."""
        # Setup: hive has no child_tiers, scope has t1
        scope_data = {
            "hives": {
                "frontend": {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Story", "Stories"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: uses scope-level child_tiers
        with pytest.raises(ValidationError, match="t1 must have a parent"):
            validate_child_tier_parent({"type": "t1"}, hive_name="frontend")

        with pytest.raises(ValidationError, match="Story must have a parent"):
            validate_child_tier_parent({"type": "Story"}, hive_name="frontend")

        validate_child_tier_parent({"type": "t1", "parent": "b.Abc"}, hive_name="frontend")


class TestValidateChildTierParentBackwardCompat:
    """Test validate_child_tier_parent backward compatibility (no hive_name parameter)."""

    def test_validate_without_hive_name_uses_scope_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent without hive_name uses scope-level child_tiers."""
        # Setup: scope has t1+t2
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Epic", "Epics"],
                "t2": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: scope-level child_tiers enforce parent requirement
        with pytest.raises(ValidationError, match="t1 must have a parent"):
            validate_child_tier_parent({"type": "t1"})  # No hive_name

        with pytest.raises(ValidationError, match="Epic must have a parent"):
            validate_child_tier_parent({"type": "Epic"})

        validate_child_tier_parent({"type": "t1", "parent": "b.Abc"})

    def test_validate_without_hive_name_scope_none_defaults_to_empty(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent without hive_name when scope child_tiers is None."""
        # Setup: scope has no child_tiers
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: no child tiers configured, so t1 is not a child tier (no parent required)
        validate_child_tier_parent({"type": "t1"})  # Should not raise

    def test_validate_without_hive_name_no_config_defaults_to_empty(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent without hive_name when no config exists."""
        # Setup: no config file
        # Test: no child tiers, so t1 is not a child tier
        validate_child_tier_parent({"type": "t1"})  # Should not raise


class TestValidateTicketTypeEdgeCases:
    """Test validate_ticket_type edge cases and error handling."""

    def test_validate_nonexistent_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type with non-existent hive_name when config exists."""
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: when config exists, non-existent hive raises ValueError from resolve_child_tiers_for_hive
        # But when hive_name is provided and config exists, resolve_child_tiers_for_hive checks existence
        # Actually, let's test that "bee" is still valid even with non-existent hive
        # because "bee" returns early before loading config
        validate_ticket_type("bee", hive_name="nonexistent")

        # Test: for non-bee types with non-existent hive, should raise ValueError
        with pytest.raises(ValueError, match="Hive 'nonexistent' does not exist"):
            validate_ticket_type("t1", hive_name="nonexistent")

    def test_validate_bee_always_valid_regardless_of_config(self, tmp_path, mock_global_bees_dir):
        """Test that 'bee' type is always valid regardless of child_tiers config."""
        # Test: no config
        validate_ticket_type("bee")
        validate_ticket_type("bee", hive_name=None)

        # Setup: bees-only config
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},
                },
            },
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        validate_ticket_type("bee")
        validate_ticket_type("bee", hive_name="backend")


class TestValidateChildTierParentEdgeCases:
    """Test validate_child_tier_parent edge cases and error handling."""

    def test_validate_nonexistent_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_child_tier_parent with non-existent hive_name when config exists."""
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: "bee" never requires parent, returns early before checking hive
        validate_child_tier_parent({"type": "bee"}, hive_name="nonexistent")

        # Test: for non-bee types with non-existent hive, should raise ValueError
        with pytest.raises(ValueError, match="Hive 'nonexistent' does not exist"):
            validate_child_tier_parent({"type": "t1"}, hive_name="nonexistent")

    def test_validate_bee_never_requires_parent_regardless_of_config(self, tmp_path, mock_global_bees_dir):
        """Test that 'bee' type never requires parent regardless of child_tiers config."""
        # Test: no config
        validate_child_tier_parent({"type": "bee"})
        validate_child_tier_parent({"type": "bee", "parent": None})

        # Setup: config with child_tiers
        scope_data = {
            "hives": {
                "backend": {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        validate_child_tier_parent({"type": "bee"}, hive_name="backend")
        validate_child_tier_parent({"type": "bee", "parent": None}, hive_name="backend")
