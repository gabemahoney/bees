"""Tests for ticket creation logic, validation, and hive operations."""

import json
import shutil
from unittest.mock import patch

import pytest

from src.id_utils import is_valid_ticket_id
from src.mcp_server import _create_ticket
from src.mcp_ticket_ops import _update_ticket
from src.paths import get_ticket_path
from src.reader import read_ticket
from src.repo_context import repo_root_context
from src.ticket_factory import create_bee, create_child_tier
from tests.conftest import write_scoped_config
from tests.helpers import setup_child_tiers
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_DOCS,
    HIVE_FRONTEND,
    TICKET_ID_NONEXISTENT,
    TITLE_PARENT_BEE,
    TITLE_TEST_BEE,
    TITLE_TEST_SUBTASK,
    TITLE_TEST_TASK,
)


class TestCreateBee:
    """Tests for creating bee tickets."""

    async def test_create_bee_without_parent_success(self, hive_tier_config):
        """Bee without parent succeeds with correct fields and file."""
        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE,
            description="Test bee description", tags=["test", "bee"], hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"
        assert "ticket_id" in result
        assert result["ticket_type"] == "bee"
        assert result["title"] == TITLE_TEST_BEE

        ticket_id = result["ticket_id"]
        # Verify new ID format: b.XXX (3 chars)
        assert ticket_id.startswith("b.")
        assert len(ticket_id) == 5  # "b." + 3 chars

        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        assert ticket_path.exists()

        ticket = read_ticket(ticket_id, file_path=ticket_path)
        assert ticket.title == TITLE_TEST_BEE
        assert ticket.description == "Test bee description"
        assert "test" in ticket.tags

    async def test_create_bee_with_parent_fails(self, hive_tier_config):
        """Bee with parent returns error dict."""
        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE, parent=TICKET_ID_NONEXISTENT, hive_name=HIVE_BACKEND
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_parent"
        assert "Bees cannot have a parent" in result["message"]

    async def test_create_bee_with_dependencies(self, hive_tier_config):
        """Bee with dependencies creates bidirectional links."""
        dep_result = await _create_ticket(ticket_type="bee", title="Dependency Epic", hive_name=HIVE_BACKEND)
        dep_id = dep_result["ticket_id"]

        result = await _create_ticket(
            ticket_type="bee", title=TITLE_TEST_BEE, up_dependencies=[dep_id], hive_name=HIVE_BACKEND
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert dep_id in ticket.up_dependencies

        dep_ticket = read_ticket(dep_id, file_path=get_ticket_path(dep_id, "bee", HIVE_BACKEND))
        assert ticket_id in dep_ticket.down_dependencies


class TestCreateTicketCacheEviction:
    """Tests that _create_ticket evicts cache after writing."""

    async def test_create_bee_evicts_cache(self, hive_tier_config):
        """Cache is evicted for the new ticket ID after bee creation."""
        with patch("src.mcp_ticket_ops.cache") as mock_cache:
            result = await _create_ticket(
                ticket_type="bee", title="Cache Test", hive_name=HIVE_BACKEND,
            )
        assert result["status"] == "success"
        mock_cache.evict.assert_called_with(result["ticket_id"])

    async def test_create_child_evicts_cache(self, hive_tier_config):
        """Cache is evicted for the new ticket ID after child tier creation."""
        _, _, child_tiers = hive_tier_config
        if not child_tiers:
            pytest.skip("No child tiers configured")
        parent = await _create_ticket(
            ticket_type="bee", title="Parent", hive_name=HIVE_BACKEND,
        )
        with patch("src.mcp_ticket_ops.cache") as mock_cache:
            result = await _create_ticket(
                ticket_type="t1", title="Child Cache Test",
                parent=parent["ticket_id"], hive_name=HIVE_BACKEND,
            )
        assert result["status"] == "success"
        mock_cache.evict.assert_called_with(result["ticket_id"])


class TestCreateChildTicket:
    """Tests for creating task and subtask tickets."""

    @pytest.mark.parametrize(
        "parent_type,child_type,child_title,child_desc,child_tags,expected_prefix,expected_len",
        [
            pytest.param("bee", "t1", TITLE_TEST_TASK, "Task description", ["backend"], "t1.", 9, id="task_with_bee_parent"),
            pytest.param("t1", "t2", TITLE_TEST_SUBTASK, "Subtask description", None, "t2.", 12, id="subtask_with_task_parent"),
        ],
    )
    async def test_create_child_with_parent_success(
        self, parent_type, child_type, child_title, child_desc, child_tags, expected_prefix, expected_len, hive_tier_config,
    ):
        """Child ticket with valid parent succeeds with bidirectional link."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires child_type to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if child_type == "t1" and "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})
        elif child_type == "t2" and "t2" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})

        # Create parent - if parent_type needs a parent, create grandparent first
        if parent_type == "bee":
            parent_result = await _create_ticket(
                ticket_type=parent_type, title=f"Parent {parent_type.capitalize()}", hive_name=HIVE_BACKEND,
            )
        else:
            # Parent is a child tier (like t1), so it needs a bee parent
            grandparent_result = await _create_ticket(
                ticket_type="bee", title="Grandparent Bee", hive_name=HIVE_BACKEND,
            )
            grandparent_id = grandparent_result["ticket_id"]
            parent_result = await _create_ticket(
                ticket_type=parent_type, title=f"Parent {parent_type.capitalize()}", parent=grandparent_id, hive_name=HIVE_BACKEND,
            )
        parent_id = parent_result["ticket_id"]

        child_kwargs = dict(ticket_type=child_type, title=child_title, parent=parent_id, description=child_desc, hive_name=HIVE_BACKEND)
        if child_tags:
            child_kwargs["tags"] = child_tags
        result = await _create_ticket(**child_kwargs)

        assert result["status"] == "success"
        child_id = result["ticket_id"]
        assert result["ticket_type"] == child_type

        # Verify new ID format
        assert child_id.startswith(expected_prefix)
        assert len(child_id) == expected_len

        child = read_ticket(child_id, file_path=get_ticket_path(child_id, child_type, HIVE_BACKEND))
        assert child.parent == parent_id

        parent = read_ticket(parent_id, file_path=get_ticket_path(parent_id, parent_type, HIVE_BACKEND))
        assert child_id in parent.children

    @pytest.mark.parametrize(
        "ticket_type,title,parent,expected_error",
        [
            pytest.param("t1", TITLE_TEST_TASK, TICKET_ID_NONEXISTENT, "Parent ticket does not exist", id="task_nonexistent_parent"),
            pytest.param("t2", TITLE_TEST_SUBTASK, None, "t2 ticket must have t1 parent, got None", id="subtask_without_parent"),
        ],
    )
    async def test_create_child_with_invalid_parent_fails(
        self, ticket_type, title, parent, expected_error, hive_tier_config,
    ):
        """Child ticket with invalid/missing parent returns error dict."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires ticket_type to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if ticket_type == "t1" and "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})
        elif ticket_type == "t2" and "t2" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})
        kwargs = dict(ticket_type=ticket_type, title=title, hive_name=HIVE_BACKEND)
        if parent is not None:
            kwargs["parent"] = parent
        result = await _create_ticket(**kwargs)
        assert result["status"] == "error"
        assert expected_error in result["message"]


class TestIDFormatValidation:
    """Tests for validating new type-prefixed ID format across all tiers."""

    @pytest.mark.parametrize(
        "ticket_type,expected_prefix,expected_len,parent_type",
        [
            pytest.param("bee", "b.", 5, None, id="bee_format"),
            pytest.param("t1", "t1.", 9, "bee", id="task_format"),
            pytest.param("t2", "t2.", 12, "t1", id="subtask_format"),
        ],
    )
    async def test_ticket_id_format_for_all_tiers(
        self, ticket_type, expected_prefix, expected_len, parent_type, hive_tier_config
    ):
        """All tier types generate IDs with correct format: bee→b.XXX, t1→t1.XXXX, t2→t2.XXXXX."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires ticket_type to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if ticket_type == "t1" and "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})
        elif ticket_type == "t2" and "t2" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})

        # Create parent if needed
        parent_id = None
        if parent_type:
            if parent_type == "bee":
                parent_result = await _create_ticket(
                    ticket_type=parent_type, title=f"Parent {parent_type}", hive_name=HIVE_BACKEND
                )
            else:
                # parent_type is a child tier (like t1), so it needs a bee parent
                grandparent_result = await _create_ticket(
                    ticket_type="bee", title="Grandparent Bee", hive_name=HIVE_BACKEND
                )
                grandparent_id = grandparent_result["ticket_id"]
                parent_result = await _create_ticket(
                    ticket_type=parent_type, title=f"Parent {parent_type}", parent=grandparent_id, hive_name=HIVE_BACKEND
                )
            parent_id = parent_result["ticket_id"]

        # Create ticket
        kwargs = {"ticket_type": ticket_type, "title": f"Test {ticket_type}", "hive_name": HIVE_BACKEND}
        if parent_id:
            kwargs["parent"] = parent_id

        result = await _create_ticket(**kwargs)

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Verify ID format
        assert ticket_id.startswith(expected_prefix), f"Expected ID to start with {expected_prefix}, got {ticket_id}"
        assert len(ticket_id) == expected_len, f"Expected ID length {expected_len}, got {len(ticket_id)} for {ticket_id}"

        # Verify ticket exists and is readable
        ticket_path = get_ticket_path(ticket_id, ticket_type, HIVE_BACKEND)
        assert ticket_path.exists()
        ticket = read_ticket(ticket_id, file_path=ticket_path)
        assert ticket.id == ticket_id


class TestHierarchicalPrefix:
    """Tests verifying child IDs embed parent short ID as a prefix (SRD SR-9.1, SR-9.3)."""

    async def test_t1_id_embeds_parent_bee_short_id(self, hive_tier_config):
        """T1 ticket ID starts with parent bee's short ID."""
        setup_child_tiers({"t1": ("Task", "Tasks")})
        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]
        bee_short_id = bee_id.split(".", 1)[1]  # e.g., "abc" from "b.abc"

        t1_result = await _create_ticket(ticket_type="t1", title="Child Task", parent=bee_id, hive_name=HIVE_BACKEND)
        t1_id = t1_result["ticket_id"]
        t1_short_id = t1_id.split(".", 1)[1]  # e.g., "abcXY"

        assert t1_short_id.startswith(bee_short_id), (
            f"T1 short ID '{t1_short_id}' should start with bee short ID '{bee_short_id}'"
        )

    async def test_t2_id_embeds_parent_t1_short_id(self, hive_tier_config):
        """T2 ticket ID starts with parent T1's short ID."""
        setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})
        bee_result = await _create_ticket(ticket_type="bee", title="Grandparent Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]

        t1_result = await _create_ticket(ticket_type="t1", title="Parent Task", parent=bee_id, hive_name=HIVE_BACKEND)
        t1_id = t1_result["ticket_id"]
        t1_short_id = t1_id.split(".", 1)[1]

        t2_result = await _create_ticket(ticket_type="t2", title="Child Subtask", parent=t1_id, hive_name=HIVE_BACKEND)
        t2_id = t2_result["ticket_id"]
        t2_short_id = t2_id.split(".", 1)[1]

        assert t2_short_id.startswith(t1_short_id), (
            f"T2 short ID '{t2_short_id}' should start with T1 short ID '{t1_short_id}'"
        )

    async def test_multiple_t1_children_all_embed_parent_prefix(self, hive_tier_config):
        """Multiple T1 children under same bee all embed parent's short ID (SRD SR-9.3)."""
        setup_child_tiers({"t1": ("Task", "Tasks")})
        bee_result = await _create_ticket(ticket_type="bee", title="Parent", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]
        bee_short_id = bee_id.split(".", 1)[1]

        for i in range(5):
            t1_result = await _create_ticket(ticket_type="t1", title=f"Task {i}", parent=bee_id, hive_name=HIVE_BACKEND)
            t1_short_id = t1_result["ticket_id"].split(".", 1)[1]
            assert t1_short_id.startswith(bee_short_id), (
                f"T1 short ID '{t1_short_id}' should start with bee short ID '{bee_short_id}'"
            )


class TestBidirectionalRelationships:
    """Tests for bidirectional relationship updates."""

    @pytest.mark.parametrize("parent_type,child_type", [("bee", "t1"), ("t1", "t2")])
    async def test_parent_children_bidirectional_sync(self, parent_type, child_type, hive_tier_config):
        """Parent's children array updated when creating child with parent field."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires child_type to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if child_type == "t1" and "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})
        elif child_type == "t2" and "t2" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})

        # Create parent - if parent_type needs a parent, create grandparent first
        if parent_type == "bee":
            parent_result = await _create_ticket(
                ticket_type=parent_type, title=f"Parent {parent_type.capitalize()}", hive_name=HIVE_BACKEND
            )
        else:
            grandparent_result = await _create_ticket(
                ticket_type="bee", title="Grandparent Bee", hive_name=HIVE_BACKEND
            )
            grandparent_id = grandparent_result["ticket_id"]
            parent_result = await _create_ticket(
                ticket_type=parent_type, title=f"Parent {parent_type.capitalize()}", parent=grandparent_id, hive_name=HIVE_BACKEND
            )
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type=child_type, title=f"Child {child_type.capitalize()}", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        parent = read_ticket(parent_id, file_path=get_ticket_path(parent_id, parent_type, HIVE_BACKEND))
        child = read_ticket(child_id, file_path=get_ticket_path(child_id, child_type, HIVE_BACKEND))
        assert child.parent == parent_id
        assert child_id in parent.children

    @pytest.mark.parametrize(
        "dependency_field,expected_reverse_field",
        [("up_dependencies", "down_dependencies"), ("down_dependencies", "up_dependencies")],
    )
    async def test_dependencies_bidirectional_sync(self, dependency_field, expected_reverse_field, hive_tier_config):
        """Dependencies automatically update the reverse relationship field."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create bee parent for t1 tickets
        parent_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        ticket1_result = await _create_ticket(ticket_type="t1", title="Task 1", parent=parent_id, hive_name=HIVE_BACKEND)
        ticket1_id = ticket1_result["ticket_id"]

        ticket2_result = await _create_ticket(
            ticket_type="t1", title="Task 2", parent=parent_id, hive_name="backend", **{dependency_field: [ticket1_id]},
        )
        ticket2_id = ticket2_result["ticket_id"]

        ticket1 = read_ticket(ticket1_id, file_path=get_ticket_path(ticket1_id, "t1", HIVE_BACKEND))
        ticket2 = read_ticket(ticket2_id, file_path=get_ticket_path(ticket2_id, "t1", HIVE_BACKEND))
        assert ticket1_id in getattr(ticket2, dependency_field)
        assert ticket2_id in getattr(ticket1, expected_reverse_field)

    async def test_multiple_children_bidirectional_update(self, hive_tier_config):
        """Multiple children correctly update parent's children array."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        parent_result = await _create_ticket(ticket_type="bee", title=TITLE_PARENT_BEE, hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        child1_id = (await _create_ticket(
            ticket_type="t1", title="Child 1", parent=parent_id, hive_name=HIVE_BACKEND
        ))["ticket_id"]
        child2_id = (await _create_ticket(
            ticket_type="t1", title="Child 2", parent=parent_id, hive_name=HIVE_BACKEND
        ))["ticket_id"]

        parent = read_ticket(parent_id, file_path=get_ticket_path(parent_id, "bee", HIVE_BACKEND))
        assert child1_id in parent.children
        assert child2_id in parent.children


class TestValidation:
    """Tests for input validation and error handling."""

    @pytest.mark.parametrize(
        "title,expected_error",
        [
            pytest.param("", "Ticket title cannot be empty", id="empty_title"),
            pytest.param("   ", "Ticket title cannot be empty", id="whitespace_only_title"),
        ],
    )
    async def test_invalid_title_fails(self, title, expected_error, hive_tier_config):
        """Empty or whitespace-only title returns error dict."""
        result = await _create_ticket(ticket_type="bee", title=title, hive_name=HIVE_BACKEND)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_title"
        assert expected_error in result["message"]

    @pytest.mark.parametrize(
        "ticket_type,extra_assertion",
        [
            pytest.param("invalid", None, id="invalid_type"),
            pytest.param("epic", "Must be one of:", id="epic_type_renamed"),
        ],
    )
    async def test_invalid_ticket_type_fails(self, ticket_type, extra_assertion, hive_tier_config):
        """Invalid ticket_type returns error dict."""
        result = await _create_ticket(ticket_type=ticket_type, title=TITLE_TEST_BEE, hive_name=HIVE_BACKEND)
        error_msg = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert "Invalid type:" in error_msg
        if extra_assertion:
            assert extra_assertion in error_msg


class TestDynamicTierTypes:
    """Tests for dynamic tier type validation from child_tiers config."""

    async def test_legacy_types_always_valid(self, hive_tier_config):
        """Legacy types 't1' and 't2' are valid when configured."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 and t2 to be configured - set them up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config or "t2" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})

        # Create bee parent for t1
        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]

        task_result = await _create_ticket(ticket_type="t1", title="Legacy Task", parent=bee_id, hive_name=HIVE_BACKEND)
        assert task_result["status"] == "success"

        subtask_result = await _create_ticket(
            ticket_type="t2", title="Legacy Subtask", parent=task_result["ticket_id"], hive_name=HIVE_BACKEND,
        )
        assert subtask_result["status"] == "success"

    async def test_undefined_tier_type_rejected(self, hive_tier_config):
        """Tier types not in child_tiers config return error dict."""
        result = await _create_ticket(ticket_type="t99", title="Invalid Tier", hive_name=HIVE_BACKEND)
        error_msg = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert "Invalid type:" in error_msg
        assert "t99" in error_msg

    async def test_create_dynamic_tier_tickets_success(self, hive_tier_config):
        """T1 tier ticket creation succeeds when configured."""
        from src.paths import infer_ticket_type_from_id

        setup_child_tiers({"t1": ("Task", "Tasks")})

        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        assert bee_result["status"] == "success"
        bee_id = bee_result["ticket_id"]
        assert infer_ticket_type_from_id(bee_id) == "bee"

        t1_result = await _create_ticket(
            ticket_type="t1", title="T1 Task", parent=bee_id,
            description="First tier ticket", tags=["tier1"], hive_name=HIVE_BACKEND,
        )
        assert t1_result["status"] == "success"
        t1_id = t1_result["ticket_id"]
        # New format: t1 tickets use "t1." prefix
        assert t1_id.startswith("t1.")

        t1_path = get_ticket_path(t1_id, "t1", HIVE_BACKEND)
        assert t1_path.exists(), f"T1 ticket file not found at {t1_path}"

        t1_ticket = read_ticket(t1_id, file_path=t1_path)
        assert t1_ticket.type == "t1"
        assert t1_ticket.title == "T1 Task"
        assert t1_ticket.parent == bee_id
        assert "tier1" in t1_ticket.tags
        assert infer_ticket_type_from_id(t1_id) == "t1"

    async def test_dynamic_tier_with_dependencies(self, hive_tier_config):
        """Dynamic tier tickets support dependencies with bidirectional sync."""
        setup_child_tiers({"t1": ("Task", "Tasks")})

        bee_id = (await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND))["ticket_id"]

        t1_blocking_id = (await _create_ticket(
            ticket_type="t1", title="Blocking Task", parent=bee_id, hive_name=HIVE_BACKEND
        ))["ticket_id"]

        t1_blocked_id = (await _create_ticket(
            ticket_type="t1", title="Blocked Task", parent=bee_id,
            up_dependencies=[t1_blocking_id], hive_name=HIVE_BACKEND,
        ))["ticket_id"]

        blocked_ticket = read_ticket(t1_blocked_id, file_path=get_ticket_path(t1_blocked_id, "t1", HIVE_BACKEND))
        assert t1_blocking_id in blocked_ticket.up_dependencies

        blocking_ticket = read_ticket(t1_blocking_id, file_path=get_ticket_path(t1_blocking_id, "t1", HIVE_BACKEND))
        assert t1_blocked_id in blocking_ticket.down_dependencies

    @pytest.mark.parametrize(
        "create_kwargs,expected_error",
        [
            pytest.param(
                dict(ticket_type="t1", title=TITLE_TEST_TASK, up_dependencies=[TICKET_ID_NONEXISTENT], hive_name=HIVE_BACKEND),
                "Dependency ticket does not exist",
                id="nonexistent_dependency",
            ),
        ],
    )
    async def test_dependency_validation_fails(self, create_kwargs, expected_error, hive_tier_config):
        """Invalid dependency references return error dict."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create bee parent for t1 ticket
        parent_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        # Add parent to create_kwargs
        create_kwargs["parent"] = parent_id

        result = await _create_ticket(**create_kwargs)
        assert result["status"] == "error"
        assert expected_error in result["message"]

    async def test_circular_dependency_fails(self, hive_tier_config):
        """Circular dependency (same ticket in up and down) fails."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create bee parent for t1 tickets
        parent_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        task_id = (await _create_ticket(ticket_type="t1", title="Existing Task", parent=parent_id, hive_name=HIVE_BACKEND))["ticket_id"]

        result = await _create_ticket(
            ticket_type="t1", title=TITLE_TEST_TASK, parent=parent_id,
            up_dependencies=[task_id], down_dependencies=[task_id], hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "circular_dependency"
        assert "Circular dependency detected" in result["message"]


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    async def test_create_ticket_with_all_optional_fields(self, hive_tier_config):
        """All optional fields populated correctly."""
        result = await _create_ticket(
            ticket_type="bee", title="Full Epic", description="Full description",
            tags=["label1", "label2"], status="in_progress", hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"

        ticket = read_ticket(result["ticket_id"], file_path=get_ticket_path(result["ticket_id"], "bee", HIVE_BACKEND))
        assert ticket.title == "Full Epic"
        assert ticket.description == "Full description"
        assert len(ticket.tags) == 2
        assert ticket.status == "in_progress"

    @pytest.mark.parametrize(
        "title,description,verify_fn",
        [
            pytest.param("Minimal Epic", None, lambda t: t.title == "Minimal Epic", id="minimal_fields"),
            pytest.param("Unicode Test: \u4f60\u597d \U0001f680", None, lambda t: t.title == "Unicode Test: \u4f60\u597d \U0001f680", id="unicode_title"),
            pytest.param("Long Description Test", "x" * 10000, lambda t: len(t.description) == 10000, id="long_description"),
        ],
    )
    async def test_create_bee_with_special_content(self, title, description, verify_fn, hive_tier_config):
        """Bee tickets with special content variations."""
        kwargs = dict(ticket_type="bee", title=title, hive_name=HIVE_BACKEND)
        if description is not None:
            kwargs["description"] = description
        result = await _create_ticket(**kwargs)
        assert result["status"] == "success"
        ticket = read_ticket(result["ticket_id"], file_path=get_ticket_path(result["ticket_id"], "bee", HIVE_BACKEND))
        assert verify_fn(ticket)


class TestMultiTierEdgeCases:
    """Edge case tests for multi-tier configurations."""

    @pytest.mark.parametrize(
        "tier_config,tier_chain",
        [
            pytest.param(
                {"t1": ("Epic", "Epics"), "t2": ("Feature", "Features"), "t3": ("Story", "Stories")},
                [("t1", "T1 Epic"), ("t2", "T2 Feature"), ("t3", "T3 Story")],
                id="four_tier",
            ),
            pytest.param(
                {"t1": ("Initiative", "Initiatives"), "t2": ("Epic", "Epics"), "t3": ("Feature", "Features"), "t4": ("Task", "Tasks")},
                [("t1", "T1"), ("t2", "T2"), ("t3", "T3"), ("t4", "T4")],
                id="five_tier",
            ),
        ],
    )
    async def test_create_tickets_with_deep_tier_config(self, tier_config, tier_chain, hive_tier_config):
        """Tickets created across multiple tier levels with correct parent-child links."""
        setup_child_tiers(tier_config)

        bee_result = await _create_ticket(ticket_type="bee", title="Root Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]
        assert bee_result["status"] == "success"

        parent_id = bee_id
        created_ids = []
        for tier_type, tier_title in tier_chain:
            result = await _create_ticket(ticket_type=tier_type, title=tier_title, parent=parent_id, hive_name=HIVE_BACKEND)
            assert result["status"] == "success"
            created_ids.append(result["ticket_id"])
            parent_id = result["ticket_id"]

        deepest_type, deepest_title = tier_chain[-1]
        deepest_ticket = read_ticket(created_ids[-1], file_path=get_ticket_path(created_ids[-1], deepest_type, HIVE_BACKEND))
        assert deepest_ticket.title == deepest_title
        assert deepest_ticket.parent == created_ids[-2] if len(created_ids) > 1 else bee_id
        assert deepest_ticket.type == deepest_type

        for i in range(len(created_ids) - 1):
            ticket = read_ticket(created_ids[i], file_path=get_ticket_path(created_ids[i], tier_chain[i][0], HIVE_BACKEND))
            expected_parent = created_ids[i - 1] if i > 0 else bee_id
            assert ticket.parent == expected_parent
            assert created_ids[i + 1] in ticket.children

    async def test_empty_child_tiers_allows_only_bee(self, hive_tier_config):
        """Empty child_tiers allows only bee, rejects t1."""
        setup_child_tiers({})

        # Bee should work
        assert (await _create_ticket(ticket_type="bee", title="Bee Only", hive_name=HIVE_BACKEND))["status"] == "success"

        # t1 should fail when child_tiers is empty
        result = await _create_ticket(ticket_type="t1", title="T1 Should Fail", hive_name=HIVE_BACKEND)
        error_msg = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert "Invalid type:" in error_msg

    @pytest.mark.parametrize(
        "wrong_child_type,wrong_parent_type,parent_tier_idx,expected_error",
        [
            pytest.param("t2", "bee", None, "t2 ticket must have t1 parent, got bee", id="t2_with_bee_parent"),
            pytest.param("t3", "t1", 0, "t3 ticket must have t2 parent, got t1", id="t3_with_t1_parent"),
        ],
    )
    async def test_multi_tier_hierarchy_enforcement(
        self, wrong_child_type, wrong_parent_type, parent_tier_idx, expected_error, hive_tier_config,
    ):
        """Hierarchy rules enforced across all tier levels."""
        setup_child_tiers({"t1": ("Epic", "Epics"), "t2": ("Feature", "Features"), "t3": ("Story", "Stories")})

        bee_id = (await _create_ticket(ticket_type="bee", title="Bee", hive_name=HIVE_BACKEND))["ticket_id"]

        if wrong_parent_type == "bee":
            wrong_parent_id = bee_id
        else:
            wrong_parent_id = (await _create_ticket(ticket_type="t1", title="T1", parent=bee_id, hive_name=HIVE_BACKEND))["ticket_id"]

        result = await _create_ticket(
            ticket_type=wrong_child_type, title=f"{wrong_child_type} with wrong parent",
            parent=wrong_parent_id, hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert expected_error in result["message"]

class TestCrossTypeDependencyValidation:
    """Tests for cross-type dependency rejection in _create_ticket and _update_ticket."""

    @pytest.mark.parametrize(
        "dep_field",
        [
            pytest.param("up_dependencies", id="up_deps"),
            pytest.param("down_dependencies", id="down_deps"),
        ],
    )
    async def test_create_ticket_rejects_cross_type_dependency(self, dep_field, hive_tier_config):
        """Creating a t1 ticket with a bee as a dependency returns error dict."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]  # type "bee" — cross-type for a t1 dep

        result = await _create_ticket(
            ticket_type="t1",
            title="Task with Cross-Type Dep",
            parent=bee_id,
            **{dep_field: [bee_id]},
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_dependency"
        assert "Cross-type dependency" in result["message"]

    @pytest.mark.parametrize(
        "dep_field",
        [
            pytest.param("up_dependencies", id="up_deps"),
            pytest.param("down_dependencies", id="down_deps"),
        ],
    )
    async def test_update_ticket_rejects_cross_type_dependency(self, dep_field, hive_tier_config):
        """Updating a t1 ticket with a bee as a dependency returns error dict."""
        repo_root, hive_path, tier_config = hive_tier_config
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        bee_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]

        t1_result = await _create_ticket(
            ticket_type="t1", title="Task", parent=bee_id, hive_name=HIVE_BACKEND
        )
        t1_id = t1_result["ticket_id"]

        result = await _update_ticket(
            ticket_id=t1_id,
            **{dep_field: [bee_id]},
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_dependency"
        assert "Cross-type dependency" in result["message"]


@pytest.fixture(scope="function")
def temp_tickets_dir(tmp_path, monkeypatch, mock_global_bees_dir):
    """Multi-hive fixture with 12 hives for normalization edge case tests."""
    from datetime import datetime

    monkeypatch.chdir(tmp_path)

    hive_names = ["backend", "frontend", "test_hive", "my_hive", "front_end",
                  "back_end", "myhive", "test_123", "test", "a", "_1", "my_hive_123"]
    hive_configs = {}
    for name in hive_names:
        (tmp_path / name).mkdir(exist_ok=True)
        display = name.replace("_", " ").title() if "_" in name else name.title()
        hive_configs[name] = {"path": str(tmp_path / name), "display_name": display, "created_at": datetime.now().isoformat()}

    scope_data = {
        "hives": hive_configs,
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    with repo_root_context(tmp_path):
        yield tmp_path


class TestCreateTicketWithHive:
    """Tests for _create_ticket() with hive_name parameter."""

    @pytest.mark.parametrize(
        "ticket_type, title, expected_prefix",
        [
            pytest.param("bee", "Backend Epic", "b.", id="bee"),
            pytest.param("t1", "Backend Task", "t1.", id="task")
        ],
    )
    async def test_create_ticket_with_hive(self, temp_tickets_dir, ticket_type, title, expected_prefix):
        """Bee/task created with type-prefixed ID and stored in hive directory."""
        # Configure child_tiers if needed for t1 creation
        if ticket_type == "t1":
            setup_child_tiers({"t1": ("Task", "Tasks")})
            # t1 requires bee parent
            parent_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
            parent_id = parent_result["ticket_id"]
            result = await _create_ticket(ticket_type=ticket_type, title=title, description="Backend work", hive_name=HIVE_BACKEND, parent=parent_id)
        else:
            result = await _create_ticket(ticket_type=ticket_type, title=title, description="Backend work", hive_name=HIVE_BACKEND)

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert ticket_id.startswith(expected_prefix)
        assert is_valid_ticket_id(ticket_id)

        if ticket_type == "bee":
            epic_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
            assert epic_path.exists()
            # Hierarchical storage: ticket file is at {hive}/{ticket_id}/{ticket_id}.md
            assert epic_path.parent.name == ticket_id  # Directory name matches ticket ID
            assert epic_path.parent.parent == temp_tickets_dir / "backend"  # Bee directory under hive root
            assert read_ticket(ticket_id, file_path=epic_path).title == "Backend Epic"

    async def test_create_subtask_with_hive(self, temp_tickets_dir):
        """Subtask created with type-prefixed ID and parent link."""
        # Configure child_tiers for t1 and t2
        setup_child_tiers({"t1": ("Task", "Tasks"), "t2": ("Subtask", "Subtasks")})

        # Create bee grandparent for t1 parent
        grandparent_result = await _create_ticket(ticket_type="bee", title="Grandparent Bee", hive_name=HIVE_BACKEND)
        grandparent_id = grandparent_result["ticket_id"]

        # Create t1 parent with bee grandparent
        parent_id = (await _create_ticket(ticket_type="t1", title="Parent Task", hive_name=HIVE_BACKEND, parent=grandparent_id))["ticket_id"]

        result = await _create_ticket(
            ticket_type="t2", title="Backend Subtask", hive_name=HIVE_BACKEND, parent=parent_id, description="Backend work",
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert ticket_id.startswith("t2.")
        assert is_valid_ticket_id(ticket_id)
        assert read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "subtask", HIVE_BACKEND)).parent == parent_id

    @pytest.mark.parametrize(
        "hive_name",
        [pytest.param("My Hive", id="spaces_to_underscores"), pytest.param("Front-End", id="hyphens_to_underscores")],
    )
    async def test_hive_name_normalization(self, temp_tickets_dir, hive_name):
        """Hive names accepted for storage, IDs use type prefix."""
        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=hive_name)
        # New format: IDs are type-prefixed, not hive-prefixed
        assert result["ticket_id"].startswith("b.")

    async def test_multiple_hives(self, temp_tickets_dir):
        """Tickets created in multiple hives stored in correct directories."""
        backend_result = await _create_ticket(ticket_type="bee", title="Backend Epic", hive_name=HIVE_BACKEND)
        frontend_result = await _create_ticket(ticket_type="bee", title="Frontend Epic", hive_name=HIVE_FRONTEND)
        # New format: both use type prefix, not hive prefix
        assert backend_result["ticket_id"].startswith("b.")
        assert frontend_result["ticket_id"].startswith("b.")
        # Verify they're stored in different directories
        backend_path = get_ticket_path(backend_result["ticket_id"], "bee", HIVE_BACKEND)
        frontend_path = get_ticket_path(frontend_result["ticket_id"], "bee", HIVE_FRONTEND)
        # Hierarchical storage: {hive}/{ticket_id}/{ticket_id}.md
        assert backend_path.parent.parent == temp_tickets_dir / "backend"
        assert frontend_path.parent.parent == temp_tickets_dir / "frontend"


class TestHiveNameValidation:
    """Tests for _create_ticket() hive_name validation."""

    @pytest.mark.parametrize(
        "hive_name",
        [
            pytest.param(HIVE_BACKEND, id="simple_alphanumeric"),
            pytest.param("back_end", id="normalized_with_underscore"),
            pytest.param("myhive", id="simple_lowercase"),
            pytest.param("test_123", id="alphanumeric_with_underscore"),
        ],
    )
    async def test_valid_hive_names_pass(self, temp_tickets_dir, hive_name):
        """Valid normalized hive names pass validation, IDs use type prefix."""
        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=hive_name)
        assert result["status"] == "success"
        # New format: IDs use type prefix, not hive prefix
        assert result["ticket_id"].startswith("b.")

    @pytest.mark.parametrize(
        "hive_name",
        [pytest.param("!@#$%", id="all_special_chars"), pytest.param("!!!!", id="all_exclamation_marks"), pytest.param("---", id="all_hyphens")],
    )
    async def test_invalid_hive_names_raise_error(self, temp_tickets_dir, hive_name):
        """Hive names normalizing to empty return error dict."""
        result = await _create_ticket(ticket_type="bee", title="Test", hive_name=hive_name)
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "Invalid hive_name" in result["message"]

class TestRequiredHiveName:
    """Tests for _create_ticket() with required hive_name parameter."""

    async def test_create_ticket_without_hive_raises_error(self, temp_tickets_dir):
        """TypeError when hive_name not provided."""
        with pytest.raises(TypeError):
            await _create_ticket(ticket_type="bee", title="Test Epic")

    @pytest.mark.parametrize(
        "hive_name",
        [pytest.param(None, id="none_value"), pytest.param("", id="empty_string"), pytest.param("   ", id="whitespace_only")],
    )
    async def test_create_ticket_with_invalid_hive_value_raises_error(self, temp_tickets_dir, hive_name):
        """Error dict returned when hive_name is None, empty, or whitespace."""
        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=hive_name)
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "hive_name is required" in result["message"]


class TestHiveConfigValidation:
    """Tests for hive config validation in _create_ticket()."""

    @pytest.mark.parametrize(
        "hive_name, expected_normalized",
        [pytest.param("nonexistent", "nonexistent", id="nonexistent_hive"), pytest.param("Other Hive", "other_hive", id="unnormalized_nonexistent_hive")],
    )
    async def test_create_ticket_with_nonexistent_hive_raises_error(self, multi_hive_config, hive_name, expected_normalized):
        """Error dict returned when hive does not exist in config."""
        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=hive_name)
        error_msg = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        # Error can come from resolve_child_tiers_for_hive or hive validation
        assert ("not found in config" in error_msg or "does not exist" in error_msg)
        assert expected_normalized in error_msg

class TestHivePathValidation:
    """Tests for hive path validation in _create_ticket()."""

    async def test_missing_hive_directory_raises_error(self, multi_hive_config):
        """Error dict returned when hive path does not exist."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]
        shutil.rmtree(backend_dir)

        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=HIVE_BACKEND)
        error_msg = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "does not exist" in error_msg
        assert str(backend_dir) in error_msg

    async def test_hive_path_is_file_not_directory_raises_error(self, multi_hive_config):
        """Error dict returned when hive path is a file instead of directory."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]
        shutil.rmtree(backend_dir)
        backend_dir.touch()

        result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=HIVE_BACKEND)
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "not a directory" in result["message"]

    async def test_unwritable_hive_directory_raises_error(self, multi_hive_config):
        """Error dict returned when hive directory is not writable, using os.access (no temp file)."""
        repo_root, hive_paths, config_data = multi_hive_config

        with patch("src.mcp_ticket_ops.os.access", return_value=False) as mock_access:
            result = await _create_ticket(ticket_type="bee", title="Test Epic", hive_name=HIVE_BACKEND)
            assert result["status"] == "error"
            assert result["error_type"] == "hive_not_found"
            assert "not writable" in result["message"]
            mock_access.assert_called_once()


class TestParentRelationships:
    """Tests for parent and children fields during ticket creation and updates."""

    @pytest.mark.parametrize(
        "kwarg,value",
        [
            pytest.param("parent", "b.ABC", id="parent_param_removed"),
            pytest.param("children", ["t1.ABCD"], id="children_param_removed"),
        ],
    )
    async def test_update_ticket_rejects_parent_children_kwargs(self, kwarg, value, hive_tier_config):
        """update_ticket no longer accepts parent or children kwargs — passing them raises TypeError."""
        bee_id = (await _create_ticket(
            ticket_type="bee", title="Test Bee", hive_name=HIVE_BACKEND
        ))["ticket_id"]
        with pytest.raises(TypeError):
            await _update_ticket(ticket_id=bee_id, **{kwarg: value})

    async def test_create_with_parent_then_update_other_fields_succeeds(self, hive_tier_config):
        """Creating ticket with parent, then updating non-relationship fields succeeds."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Configure t1 if not present
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create parent and child
        parent_result = await _create_ticket(
            ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND
        )
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="t1", title="Original Title", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        # Update non-relationship fields should succeed
        await _update_ticket(
            ticket_id=child_id,
            title="Updated Title",
            status="in_progress",
            tags=["updated", "test"],
            hive_name=HIVE_BACKEND,
        )

        # Verify updates applied
        child_ticket = read_ticket(child_id, file_path=get_ticket_path(child_id, "t1", HIVE_BACKEND))
        assert child_ticket.title == "Updated Title"
        assert child_ticket.status == "in_progress"
        assert "updated" in child_ticket.tags

        # Verify parent relationship unchanged
        assert child_ticket.parent == parent_id
        parent_ticket = read_ticket(parent_id, file_path=get_ticket_path(parent_id, "bee", HIVE_BACKEND))
        assert child_id in parent_ticket.children

    async def test_create_time_parent_bidirectional_sync_works(self, hive_tier_config):
        """Regression: Creating ticket with parent still updates parent's children array."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Configure t1 if not present
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # This test verifies create-time behavior is unchanged
        parent_result = await _create_ticket(
            ticket_type="bee", title="Parent", hive_name=HIVE_BACKEND
        )
        parent_id = parent_result["ticket_id"]

        child_result = await _create_ticket(
            ticket_type="t1", title="Child", parent=parent_id, hive_name=HIVE_BACKEND
        )
        child_id = child_result["ticket_id"]

        # Verify bidirectional sync worked at creation time
        child_ticket = read_ticket(child_id, file_path=get_ticket_path(child_id, "t1", HIVE_BACKEND))
        assert child_ticket.parent == parent_id

        parent_ticket = read_ticket(parent_id, file_path=get_ticket_path(parent_id, "bee", HIVE_BACKEND))
        assert child_id in parent_ticket.children

    async def test_update_dependencies_still_works(self, hive_tier_config):
        """Regression: Updating dependencies (not parent/children) still works after immutability change."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Test requires t1 to be configured - set it up if not present
        from tests.helpers import setup_child_tiers
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create bee parent for t1 tickets
        parent_result = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND)
        parent_id = parent_result["ticket_id"]

        # Create three tickets
        ticket1 = await _create_ticket(ticket_type="t1", title="Task 1", parent=parent_id, hive_name=HIVE_BACKEND)
        ticket1_id = ticket1["ticket_id"]

        ticket2 = await _create_ticket(ticket_type="t1", title="Task 2", parent=parent_id, hive_name=HIVE_BACKEND)
        ticket2_id = ticket2["ticket_id"]

        ticket3 = await _create_ticket(ticket_type="t1", title="Task 3", parent=parent_id, hive_name=HIVE_BACKEND)
        ticket3_id = ticket3["ticket_id"]

        # Update ticket2 to depend on ticket1 and block ticket3
        await _update_ticket(
            ticket_id=ticket2_id,
            up_dependencies=[ticket1_id],
            down_dependencies=[ticket3_id],
            hive_name=HIVE_BACKEND,
        )

        # Verify bidirectional dependency sync
        ticket2_data = read_ticket(ticket2_id, file_path=get_ticket_path(ticket2_id, "t1", HIVE_BACKEND))
        assert ticket1_id in ticket2_data.up_dependencies
        assert ticket3_id in ticket2_data.down_dependencies

        ticket1_data = read_ticket(ticket1_id, file_path=get_ticket_path(ticket1_id, "t1", HIVE_BACKEND))
        assert ticket2_id in ticket1_data.down_dependencies

        ticket3_data = read_ticket(ticket3_id, file_path=get_ticket_path(ticket3_id, "t1", HIVE_BACKEND))
        assert ticket2_id in ticket3_data.up_dependencies


@pytest.fixture(scope="function")
def per_hive_tier_env(bees_repo, monkeypatch, mock_global_bees_dir):
    """Multi-hive environment with different per-hive child_tiers configs.

    - backend: t1 + t2 (full hierarchy)
    - frontend: t1 only (no subtasks)
    - docs: bees-only (empty child_tiers)
    Scope-level fallback: t1 only.
    """
    repo_root = bees_repo
    monkeypatch.chdir(repo_root)

    hive_names = [HIVE_BACKEND, HIVE_FRONTEND, HIVE_DOCS]
    hives_config = {}
    for hive_name in hive_names:
        hive_path = repo_root / hive_name
        hive_path.mkdir(parents=True, exist_ok=True)
        hive_identity = hive_path / ".hive"
        hive_identity.mkdir(parents=True, exist_ok=True)
        (hive_identity / "identity.json").write_text(json.dumps({
            "normalized_name": hive_name,
            "display_name": hive_name.title(),
            "created_at": "2026-02-05T00:00:00",
        }))
        hives_config[hive_name] = {
            "path": str(hive_path),
            "display_name": hive_name.title(),
        }

    scope_data = {
        "hives": hives_config,
        "child_tiers": {"t1": ["Task", "Tasks"]},
    }
    hive_child_tiers = {
        HIVE_BACKEND: {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
        HIVE_FRONTEND: {"t1": ["Epic", "Epics"]},
        HIVE_DOCS: {},
    }
    write_scoped_config(mock_global_bees_dir, repo_root, scope_data, hive_child_tiers=hive_child_tiers)

    with repo_root_context(repo_root):
        yield repo_root


class TestPerHiveTierEnforcement:
    """Tests for per-hive tier rejection and error message quality (SR-12.5).

    Core rejection scenarios (bees-only, override, fallback) covered by TestPerHiveChildTiers.
    This class focuses on cross-hive validation matrix and error message quality.
    """

    @pytest.mark.parametrize("hive_name", [
        pytest.param(HIVE_BACKEND, id="backend_full_tiers"),
        pytest.param(HIVE_FRONTEND, id="frontend_t1_only"),
        pytest.param(HIVE_DOCS, id="docs_bees_only"),
    ])
    async def test_bee_type_always_valid_regardless_of_hive_config(self, per_hive_tier_env, hive_name):
        """Bee type accepted in every hive regardless of child_tiers config."""
        result = await _create_ticket(ticket_type="bee", title=f"Bee in {hive_name}", hive_name=hive_name)
        assert result["status"] == "success"
        assert result["ticket_type"] == "bee"

    async def test_error_message_references_hive_name(self, per_hive_tier_env):
        """Rejection error dict includes hive name and lists valid types."""
        result = await _create_ticket(ticket_type="t2", title="Should Fail", hive_name=HIVE_FRONTEND)
        error = result["message"]
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert HIVE_FRONTEND in error
        assert "Must be one of:" in error

    async def test_error_message_lists_hive_specific_valid_types(self, per_hive_tier_env):
        """Error for docs hive shows only 'bee'; error for frontend shows 'bee, t1'."""
        # Docs hive: only bee valid
        docs_result = await _create_ticket(ticket_type="t1", title="Fail", hive_name=HIVE_DOCS)
        docs_error = docs_result["message"]
        assert docs_result["status"] == "error"
        assert docs_result["error_type"] == "invalid_ticket_type"
        assert "bee" in docs_error
        # t1 should NOT be listed as valid for docs hive
        if "Must be one of:" in docs_error:
            valid_types_section = docs_error.split("Must be one of:")[1]
            assert "t1" not in valid_types_section

        # Frontend hive: bee + t1 valid
        frontend_result = await _create_ticket(ticket_type="t2", title="Fail", hive_name=HIVE_FRONTEND)
        frontend_error = frontend_result["message"]
        assert frontend_result["status"] == "error"
        assert "bee" in frontend_error
        assert "t1" in frontend_error

    @pytest.mark.parametrize(
        "hive_name,ticket_type,should_succeed",
        [
            pytest.param(HIVE_BACKEND, "t1", True, id="backend_t1_valid"),
            pytest.param(HIVE_BACKEND, "t2", True, id="backend_t2_valid"),
            pytest.param(HIVE_FRONTEND, "t1", True, id="frontend_t1_valid"),
            pytest.param(HIVE_FRONTEND, "t2", False, id="frontend_t2_invalid"),
            pytest.param(HIVE_DOCS, "t1", False, id="docs_t1_invalid"),
            pytest.param(HIVE_DOCS, "t2", False, id="docs_t2_invalid"),
        ],
    )
    async def test_cross_hive_tier_matrix(self, per_hive_tier_env, hive_name, ticket_type, should_succeed):
        """Matrix test: each type validated against each hive's own child_tiers."""
        bee = await _create_ticket(ticket_type="bee", title="Parent Bee", hive_name=hive_name)
        bee_id = bee["ticket_id"]

        if ticket_type == "t1":
            if should_succeed:
                result = await _create_ticket(
                    ticket_type="t1", title="Test T1", parent=bee_id, hive_name=hive_name,
                )
                assert result["status"] == "success"
            else:
                result = await _create_ticket(
                    ticket_type="t1", title="Test T1", parent=bee_id, hive_name=hive_name,
                )
                assert result["status"] == "error"
                assert result["error_type"] == "invalid_ticket_type"
                assert "Invalid type:" in result["message"]

        elif ticket_type == "t2":
            if should_succeed:
                t1 = await _create_ticket(
                    ticket_type="t1", title="Parent T1", parent=bee_id, hive_name=hive_name,
                )
                result = await _create_ticket(
                    ticket_type="t2", title="Test T2", parent=t1["ticket_id"], hive_name=hive_name,
                )
                assert result["status"] == "success"
            else:
                result = await _create_ticket(
                    ticket_type="t2", title="Test T2", parent=bee_id, hive_name=hive_name,
                )
                assert result["status"] == "error"
                assert result["error_type"] == "invalid_ticket_type"
                assert "Invalid type:" in result["message"]


class TestPerHiveChildTiers:
    """Tests for per-hive child_tiers configuration and enforcement."""

    async def test_create_ticket_bees_only_hive_rejects_child_tier(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Bees-only hive (child_tiers = {}) rejects child tier with clear error."""
        from src.config import load_bees_config

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        # Create two hives: backend allows t1, frontend is bees-only
        backend_hive = repo_root / "backend"
        backend_hive.mkdir()
        frontend_hive = repo_root / "frontend"
        frontend_hive.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend",
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                },
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend",
                    "child_tiers": {},  # Explicitly bees-only
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Verify config is loaded correctly
            config = load_bees_config()
            assert "backend" in config.hives
            assert "frontend" in config.hives
            assert config.hives["frontend"].child_tiers == {}

            # Create bee parent in frontend hive (should succeed)
            bee_result = await _create_ticket(
                ticket_type="bee",
                title="Frontend Bee",
                hive_name="frontend",
            )
            assert bee_result["status"] == "success"

            # Attempt to create t1 in bees-only frontend hive (should fail)
            t1_result = await _create_ticket(
                ticket_type="t1",
                title="Frontend Task",
                parent=bee_result["ticket_id"],
                hive_name="frontend",
            )
            error_msg = t1_result["message"]
            assert t1_result["status"] == "error"
            assert t1_result["error_type"] == "invalid_ticket_type"
            assert "Invalid type:" in error_msg
            assert "frontend" in error_msg

    async def test_create_ticket_bees_only_hive_allows_bee(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Bees-only hive allows bee creation."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        bees_only_hive = repo_root / "bees_only"
        bees_only_hive.mkdir()

        scope_data = {
            "hives": {
                "bees_only": {
                    "path": str(bees_only_hive),
                    "display_name": "Bees Only",
                    "child_tiers": {},  # Explicitly bees-only
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Create bee in bees-only hive (should succeed)
            result = await _create_ticket(
                ticket_type="bee",
                title="Bee in Bees-Only Hive",
                hive_name="bees_only",
            )
            assert result["status"] == "success"
            assert result["ticket_id"].startswith("b.")

            # Verify ticket exists
            ticket = read_ticket(result["ticket_id"], file_path=get_ticket_path(result["ticket_id"], "bee", "bees_only"))
            assert ticket.title == "Bee in Bees-Only Hive"

    async def test_create_ticket_hive_tiers_override_global(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Hive-specific child_tiers override scope-level child_tiers."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        backend_hive = repo_root / "backend"
        backend_hive.mkdir()
        frontend_hive = repo_root / "frontend"
        frontend_hive.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend",
                    # Hive-specific config with t1 and t2
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Feature", "Features"],
                    },
                },
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend",
                    # No child_tiers - should fall back to scope level
                },
            },
            # Scope-level (global) config
            "child_tiers": {"t1": ["Task", "Tasks"]},
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Backend hive should use hive-specific tiers (t1 and t2)
            bee_backend = await _create_ticket(
                ticket_type="bee",
                title="Backend Bee",
                hive_name="backend",
            )
            bee_backend_id = bee_backend["ticket_id"]

            # Create t1 in backend (should use hive-specific config)
            t1_backend = await _create_ticket(
                ticket_type="t1",
                title="Backend T1",
                parent=bee_backend_id,
                hive_name="backend",
            )
            assert t1_backend["status"] == "success"

            # Create t2 in backend (should work because hive-specific config includes t2)
            t2_backend = await _create_ticket(
                ticket_type="t2",
                title="Backend T2",
                parent=t1_backend["ticket_id"],
                hive_name="backend",
            )
            assert t2_backend["status"] == "success"

            # Frontend hive should use scope-level tiers (t1 only)
            bee_frontend = await _create_ticket(
                ticket_type="bee",
                title="Frontend Bee",
                hive_name="frontend",
            )
            bee_frontend_id = bee_frontend["ticket_id"]

            # Create t1 in frontend (should use scope-level config)
            t1_frontend = await _create_ticket(
                ticket_type="t1",
                title="Frontend T1",
                parent=bee_frontend_id,
                hive_name="frontend",
            )
            assert t1_frontend["status"] == "success"

            # Try to create t2 in frontend
            # Should fail - scope config doesn't have t2
            t2_frontend_result = await _create_ticket(
                ticket_type="t2",
                title="Frontend T2",
                parent=t1_frontend["ticket_id"],
                hive_name="frontend",
            )
            assert t2_frontend_result["status"] == "error"
            assert t2_frontend_result["error_type"] == "invalid_ticket_type"
            assert "Invalid type:" in t2_frontend_result["message"]

    async def test_create_ticket_hive_falls_back_to_global(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Hive without child_tiers uses scope-level (global) child_tiers."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        hive_path = repo_root / "backend"
        hive_path.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(hive_path),
                    "display_name": "Backend",
                    # No child_tiers - falls back to scope level
                },
            },
            # Scope-level config
            "child_tiers": {
                "t1": ["Task", "Tasks"],
                "t2": ["Subtask", "Subtasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Create bee parent
            bee_result = await _create_ticket(
                ticket_type="bee",
                title="Backend Bee",
                hive_name="backend",
            )
            bee_id = bee_result["ticket_id"]

            # Create t1 (should use scope-level config)
            t1_result = await _create_ticket(
                ticket_type="t1",
                title="Backend Task",
                parent=bee_id,
                hive_name="backend",
            )
            assert t1_result["status"] == "success"
            t1_id = t1_result["ticket_id"]

            # Create t2 (should also work with scope-level config)
            t2_result = await _create_ticket(
                ticket_type="t2",
                title="Backend Subtask",
                parent=t1_id,
                hive_name="backend",
            )
            assert t2_result["status"] == "success"

            # Verify tickets exist
            t1_ticket = read_ticket(t1_id, file_path=get_ticket_path(t1_id, "t1", "backend"))
            assert t1_ticket.title == "Backend Task"
            t2_ticket = read_ticket(
                t2_result["ticket_id"], file_path=get_ticket_path(t2_result["ticket_id"], "t2", "backend")
            )
            assert t2_ticket.title == "Backend Subtask"

    async def test_create_ticket_passes_hive_name_to_id_gen(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Verify hive_name is propagated to ID generation functions."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        hive_path = repo_root / "backend"
        hive_path.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(hive_path),
                    "display_name": "Backend",
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Test bee creation passes hive_name to ID generation
            with patch(
                "src.ticket_factory.generate_unique_ticket_id"
            ) as mock_gen_id:
                # Use valid ID format: b.XXX (3 chars from ID_CHARSET)
                mock_gen_id.return_value = "b.abc"
                create_bee(title="Test Bee", hive_name="backend")
                # Verify generate_unique_ticket_id called with hive_name
                assert mock_gen_id.called
                call_kwargs = mock_gen_id.call_args.kwargs
                assert "hive_name" in call_kwargs
                assert call_kwargs["hive_name"] == "backend"

            # Test child tier creation passes hive_name to ID generation
            # First create a real bee parent
            bee_result = await _create_ticket(
                ticket_type="bee",
                title="Parent Bee",
                hive_name="backend",
            )
            bee_id = bee_result["ticket_id"]

            bee_short = bee_id.split(".", 1)[1]
            with patch(
                "src.ticket_factory.generate_child_tier_id"
            ) as mock_gen_child_id:
                # Return a valid child ID that embeds the parent's short ID
                mock_gen_child_id.return_value = f"t1.{bee_short}.xy"
                create_child_tier(
                    ticket_type="t1",
                    title="Test Task",
                    parent=bee_id,
                    hive_name="backend",
                )
                # Verify generate_child_tier_id called with parent_id and parent_dir
                assert mock_gen_child_id.called
                call_kwargs = mock_gen_child_id.call_args.kwargs
                assert call_kwargs["parent_id"] == bee_id
                expected_parent_dir = hive_path / bee_id
                assert call_kwargs["parent_dir"] == expected_parent_dir


class TestUpdateTicketPerHive:
    """Tests for _update_ticket() with per-hive child_tiers enforcement."""

    async def test_update_ticket_in_hive_with_custom_tiers(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Update ticket in hive with custom tiers - title, status, tags."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        backend_hive = repo_root / "backend"
        backend_hive.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Feature", "Features"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Create bee parent
            bee_result = await _create_ticket(
                ticket_type="bee",
                title="Backend Bee",
                hive_name="backend",
            )
            bee_id = bee_result["ticket_id"]

            # Create t1 ticket
            t1_result = await _create_ticket(
                ticket_type="t1",
                title="Original Epic",
                parent=bee_id,
                hive_name="backend",
                status="open",
                tags=["original"],
            )
            assert t1_result["status"] == "success"
            t1_id = t1_result["ticket_id"]

            # Update the t1 ticket
            update_result = await _update_ticket(
                ticket_id=t1_id,
                title="Updated Epic",
                status="in_progress",
                tags=["updated", "backend"],
                hive_name="backend",
            )
            assert update_result["status"] == "success"

            # Verify updates applied
            updated_ticket = read_ticket(t1_id, file_path=get_ticket_path(t1_id, "t1", "backend"))
            assert updated_ticket.title == "Updated Epic"
            assert updated_ticket.status == "in_progress"
            assert "updated" in updated_ticket.tags
            assert "backend" in updated_ticket.tags

            # Verify parent relationship unchanged
            assert updated_ticket.parent == bee_id

    async def test_update_ticket_resolves_hive_from_ticket_location(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Update ticket without hive_name - should auto-resolve from location."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        backend_hive = repo_root / "backend"
        backend_hive.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend",
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Create bee with explicit hive_name
            bee_result = await _create_ticket(
                ticket_type="bee",
                title="Test Bee",
                hive_name="backend",
            )
            bee_id = bee_result["ticket_id"]

            # Update without hive_name - should auto-resolve
            update_result = await _update_ticket(
                ticket_id=bee_id,
                title="Updated Bee",
                status="in_progress",
            )
            assert update_result["status"] == "success"

            # Verify update applied
            updated_ticket = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", "backend"))
            assert updated_ticket.title == "Updated Bee"
            assert updated_ticket.status == "in_progress"

    async def test_update_ticket_across_hives_independent(
        self, tmp_path, monkeypatch, mock_global_bees_dir
    ):
        """Update tickets in two hives with different tier configs independently."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        monkeypatch.chdir(repo_root)

        backend_hive = repo_root / "backend"
        backend_hive.mkdir()
        frontend_hive = repo_root / "frontend"
        frontend_hive.mkdir()

        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_hive),
                    "display_name": "Backend",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Feature", "Features"],
                    },
                },
                "frontend": {
                    "path": str(frontend_hive),
                    "display_name": "Frontend",
                    "child_tiers": {"t1": ["Story", "Stories"]},
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        with repo_root_context(repo_root):
            # Create backend tickets
            backend_bee = await _create_ticket(
                ticket_type="bee",
                title="Backend Bee",
                hive_name="backend",
            )
            backend_bee_id = backend_bee["ticket_id"]

            backend_t1 = await _create_ticket(
                ticket_type="t1",
                title="Backend Epic",
                parent=backend_bee_id,
                hive_name="backend",
            )
            backend_t1_id = backend_t1["ticket_id"]

            # Create frontend tickets
            frontend_bee = await _create_ticket(
                ticket_type="bee",
                title="Frontend Bee",
                hive_name="frontend",
            )
            frontend_bee_id = frontend_bee["ticket_id"]

            frontend_t1 = await _create_ticket(
                ticket_type="t1",
                title="Frontend Story",
                parent=frontend_bee_id,
                hive_name="frontend",
            )
            frontend_t1_id = frontend_t1["ticket_id"]

            # Update backend ticket
            await _update_ticket(
                ticket_id=backend_t1_id,
                title="Updated Backend Epic",
                status="in_progress",
                tags=["backend"],
                hive_name="backend",
            )

            # Update frontend ticket
            await _update_ticket(
                ticket_id=frontend_t1_id,
                title="Updated Frontend Story",
                status="completed",
                tags=["frontend"],
                hive_name="frontend",
            )

            # Verify backend updates
            backend_ticket = read_ticket(backend_t1_id, file_path=get_ticket_path(backend_t1_id, "t1", "backend"))
            assert backend_ticket.title == "Updated Backend Epic"
            assert backend_ticket.status == "in_progress"
            assert "backend" in backend_ticket.tags

            # Verify frontend updates
            frontend_ticket = read_ticket(frontend_t1_id, file_path=get_ticket_path(frontend_t1_id, "t1", "frontend"))
            assert frontend_ticket.title == "Updated Frontend Story"
            assert frontend_ticket.status == "completed"
            assert "frontend" in frontend_ticket.tags

            # Verify tickets remain independent
            assert backend_ticket.parent == backend_bee_id
            assert frontend_ticket.parent == frontend_bee_id


class TestCreateTicketStatusValidation:
    """Tests for status validation in _create_ticket."""

    async def test_invalid_status_fails(self, isolated_bees_env):
        """Create ticket with invalid status returns an error dict."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["open", "closed", "in_progress"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="bogus",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_status"
        assert "Invalid status" in result["message"]

    async def test_valid_status_passes(self, isolated_bees_env):
        """Create ticket with valid status succeeds."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["open", "closed", "in_progress"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="closed",
        )
        assert result["status"] == "success"

    async def test_omitted_status_no_status_values_succeeds(self, isolated_bees_env):
        """No status_values configured + status omitted → succeeds, ticket.status is None."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config()

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"
        ticket = read_ticket(result["ticket_id"], file_path=get_ticket_path(result["ticket_id"], "bee", HIVE_BACKEND))
        assert ticket.status is None

    async def test_omitted_status_with_status_values_raises(self, isolated_bees_env):
        """status_values configured + status omitted → returns error dict requiring status."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["larva", "pupa", "worker", "finished"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "status_required"
        assert "status is required" in result["message"]

    async def test_freeform_any_status_accepted(self, isolated_bees_env):
        """Without status_values configured, any status string accepted."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config()

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="any_random_status",
        )
        assert result["status"] == "success"

    def test_create_ticket_cli_outputs_json_error_for_missing_status(
        self, cli_runner, isolated_bees_env
    ):
        """CLI exits 1 with JSON error (not traceback) when status is required but omitted."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(status_values=["larva", "pupa", "worker", "finished"])

        stdout, exit_code = cli_runner(
            ["create-ticket", "--ticket-type", "bee", "--hive", HIVE_BACKEND, "--title", "Test Bee"]
        )

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["status"] == "error"
        assert result["error_type"] == "status_required"
        assert "status is required" in result["message"]
