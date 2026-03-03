"""Tests for bee egg field creation, resolution, and update."""

import pytest

from src.mcp_server import _create_ticket
from src.mcp_ticket_ops import _show_ticket, _update_ticket
from src.paths import get_ticket_path
from src.reader import read_ticket
from tests.conftest import write_scoped_config
from tests.helpers import setup_child_tiers
from tests.test_constants import (
    EGG_ARRAY,
    EGG_NULL,
    EGG_OBJECT,
    EGG_URL,
    HIVE_BACKEND,
)


class TestCreateBeeWithEgg:
    """Tests for creating bee tickets with egg field."""

    async def test_create_bee_with_string_egg(self, hive_tier_config):
        """Create bee with string egg and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with String Egg",
            hive_name=HIVE_BACKEND,
            egg=EGG_URL,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Read back and verify egg field
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.egg == EGG_URL

    async def test_create_bee_with_null_egg(self, hive_tier_config):
        """Create bee with explicit null egg and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Null Egg",
            hive_name=HIVE_BACKEND,
            egg=EGG_NULL,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Read back and verify egg field is null
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.egg is None

    async def test_create_bee_with_object_egg(self, hive_tier_config):
        """Create bee with object egg and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Object Egg",
            hive_name=HIVE_BACKEND,
            egg=EGG_OBJECT,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Read back and verify egg field
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.egg == EGG_OBJECT
        assert ticket.egg["type"] == "spec"
        assert ticket.egg["url"] == "https://example.com/spec.md"

    async def test_create_bee_with_array_egg(self, hive_tier_config):
        """Create bee with array egg and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Array Egg",
            hive_name=HIVE_BACKEND,
            egg=EGG_ARRAY,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Read back and verify egg field
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.egg == EGG_ARRAY
        assert len(ticket.egg) == 2

    async def test_create_bee_without_egg_defaults_to_null(self, hive_tier_config):
        """Create bee without egg parameter and verify it defaults to null."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee without Egg",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        # Read back and verify egg field defaults to null
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.egg is None

        # Verify YAML frontmatter contains egg: null
        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        content = ticket_path.read_text()
        assert "egg: null" in content or "egg: ~" in content

    async def test_create_t1_ticket_no_egg_in_frontmatter(self, hive_tier_config):
        """Create t1 ticket and verify egg field is NOT in frontmatter."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Ensure t1 is configured
        if "t1" not in tier_config:
            setup_child_tiers({"t1": ("Task", "Tasks")})

        # Create parent bee first
        bee_result = await _create_ticket(
            ticket_type="bee",
            title="Parent Bee",
            hive_name=HIVE_BACKEND,
        )
        bee_id = bee_result["ticket_id"]

        # Create t1 child ticket
        t1_result = await _create_ticket(
            ticket_type="t1",
            title="Task without Egg",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert t1_result["status"] == "success"
        t1_id = t1_result["ticket_id"]

        # Read the raw file and verify egg is NOT in frontmatter
        t1_path = get_ticket_path(t1_id, "t1", HIVE_BACKEND)
        content = t1_path.read_text()
        # Egg should not appear in the frontmatter
        assert "egg:" not in content

    async def test_show_ticket_returns_egg_field(self, hive_tier_config):
        """Show ticket via MCP and verify egg field contains resolved resources."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Create bee with egg
        result = await _create_ticket(
            ticket_type="bee",
            title="Bee for Show Test",
            hive_name=HIVE_BACKEND,
            egg=EGG_URL,
        )
        ticket_id = result["ticket_id"]

        # Show ticket via MCP
        show_result = await _show_ticket(ticket_ids=[ticket_id])

        # Verify egg field in response contains resolved resources
        # Default resolver is identity: returns value unchanged
        assert show_result["status"] == "success"
        assert "egg" in show_result["tickets"][0]
        assert show_result["tickets"][0]["egg"] == EGG_URL


class TestShowTicketEggResolution:
    """Tests for show_ticket egg resolution with default resolver."""

    @pytest.mark.parametrize(
        "egg_value,expected_resolved",
        [
            pytest.param(None, None, id="null"),
            pytest.param("file.txt", "file.txt", id="string"),
            pytest.param(
                {"path": "file.txt", "line": 42},
                {"path": "file.txt", "line": 42},
                id="object",
            ),
            pytest.param(
                ["file1.txt", "file2.txt"],
                ["file1.txt", "file2.txt"],
                id="array",
            ),
            pytest.param(42, 42, id="integer"),
            pytest.param(True, True, id="boolean"),
        ],
    )
    async def test_show_ticket_resolves_egg_with_default_resolver(
        self, hive_tier_config, egg_value, expected_resolved
    ):
        """Test show_ticket resolves egg values using default resolver."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Create bee with egg
        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Egg for Resolution Test",
            hive_name=HIVE_BACKEND,
            egg=egg_value,
        )
        ticket_id = result["ticket_id"]

        # Show ticket via MCP
        show_result = await _show_ticket(ticket_ids=[ticket_id])

        # Verify egg field contains resolved resources
        assert show_result["status"] == "success"
        assert "egg" in show_result["tickets"][0]
        assert show_result["tickets"][0]["egg"] == expected_resolved

    async def test_show_ticket_resolves_egg_with_custom_resolver(self, hive_tier_config, mock_global_bees_dir):
        """Test show_ticket resolves egg values using custom resolver."""
        repo_root, hive_path, tier_config = hive_tier_config

        # Create resolver script
        resolver_script = repo_root / "custom_resolver.sh"
        resolver_script.write_text(
            """#!/bin/bash
echo '["custom_resolved_file1.txt", "custom_resolved_file2.txt"]'
"""
        )
        resolver_script.chmod(0o755)

        # Configure custom resolver in config
        scope_data = {
            "hives": {HIVE_BACKEND: {"path": str(hive_path), "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
            "egg_resolver": str(resolver_script),
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        # Create bee with egg
        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Custom Resolver",
            hive_name=HIVE_BACKEND,
            egg="custom-spec",
        )
        ticket_id = result["ticket_id"]

        # Show ticket via MCP
        show_result = await _show_ticket(ticket_ids=[ticket_id], resolved_root=repo_root)

        # Verify egg field contains custom-resolved resources
        assert show_result["status"] == "success"
        assert "egg" in show_result["tickets"][0]
        assert show_result["tickets"][0]["egg"] == ["custom_resolved_file1.txt", "custom_resolved_file2.txt"]


    async def test_show_ticket_custom_resolver_no_resolved_root_falls_back_to_raw_egg(
        self, hive_tier_config, mock_global_bees_dir
    ):
        """Regression b.H3N: show_ticket with custom resolver and resolved_root=None.

        The ValueError is caught internally; the ticket appears in tickets with the raw
        egg value as fallback, and the error appears in the errors list.
        """
        repo_root, hive_path, tier_config = hive_tier_config

        resolver_script = repo_root / "custom_resolver.sh"
        resolver_script.write_text("#!/bin/bash\necho '[]'\n")
        resolver_script.chmod(0o755)

        scope_data = {
            "hives": {HIVE_BACKEND: {"path": str(hive_path), "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
            "egg_resolver": str(resolver_script),
        }
        write_scoped_config(mock_global_bees_dir, repo_root, scope_data)

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee Custom Resolver No Root",
            hive_name=HIVE_BACKEND,
            egg="raw-spec-value",
        )
        ticket_id = result["ticket_id"]

        show_result = await _show_ticket(ticket_ids=[ticket_id], resolved_root=None)

        # Ticket still returned with raw egg as fallback
        assert show_result["status"] == "success"
        assert len(show_result["tickets"]) == 1
        assert show_result["tickets"][0]["ticket_id"] == ticket_id
        assert show_result["tickets"][0]["egg"] == "raw-spec-value"

        # Error recorded in errors list
        assert len(show_result["errors"]) == 1
        assert show_result["errors"][0]["id"] == ticket_id
        assert "resolved_root is required" in show_result["errors"][0]["reason"]


class TestUpdateTicketEgg:
    """Tests for updating bee tickets with egg field of various JSON types."""

    @pytest.mark.parametrize(
        "egg_value,expected",
        [
            pytest.param(None, None, id="null"),
            pytest.param("file.txt", "file.txt", id="string"),
            pytest.param({"path": "file.txt", "line": 42}, {"path": "file.txt", "line": 42}, id="object"),
            pytest.param(["file1.txt", "file2.txt"], ["file1.txt", "file2.txt"], id="array"),
            pytest.param(42, 42, id="integer"),
            pytest.param(True, True, id="boolean"),
        ],
    )
    async def test_update_ticket_egg_json_types(self, hive_tier_config, egg_value, expected):
        """Update ticket egg with each JSON type and verify show_ticket returns resolved values."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Egg Update Test", hive_name=HIVE_BACKEND, egg="initial",
        )
        ticket_id = result["ticket_id"]

        await _update_ticket(ticket_id=ticket_id, egg=egg_value, hive_name=HIVE_BACKEND)

        show_result = await _show_ticket(ticket_ids=[ticket_id])
        assert show_result["tickets"][0]["egg"] == expected

    async def test_update_ticket_egg_via_show(self, hive_tier_config):
        """Update egg and verify it appears in show_ticket response."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Show Egg Test", hive_name=HIVE_BACKEND,
        )
        ticket_id = result["ticket_id"]

        egg_obj = {"type": "spec", "url": "https://example.com"}
        await _update_ticket(ticket_id=ticket_id, egg=egg_obj, hive_name=HIVE_BACKEND)

        show_result = await _show_ticket(ticket_ids=[ticket_id])
        # show_ticket returns resolved egg values (default resolver: identity, returns value unchanged)
        assert show_result["tickets"][0]["egg"] == {"type": "spec", "url": "https://example.com"}


class TestShowTicketReturnsRawEgg:
    """Regression tests for b.sGS: show_ticket must return raw egg, not resolver output."""

    async def test_show_ticket_dict_egg_is_raw_dict_not_json_string_list(self, hive_tier_config):
        """show_ticket returns the raw dict egg, not a JSON-stringified list.

        Regression: the default egg resolver wraps dicts as [json.dumps(dict)].
        show_ticket must bypass resolution and return ticket.egg directly.
        Without the fix this assertion fails because the egg comes back as
        ['{"priority": 1, "estimate": "2h"}'] instead of the original dict.
        """
        repo_root, hive_path, tier_config = hive_tier_config

        egg = {"priority": 1, "estimate": "2h"}
        result = await _create_ticket(
            ticket_type="bee",
            title="Regression b.sGS",
            hive_name=HIVE_BACKEND,
            egg=egg,
        )
        ticket_id = result["ticket_id"]

        show_result = await _show_ticket(ticket_ids=[ticket_id])

        assert show_result["status"] == "success"
        returned_egg = show_result["tickets"][0]["egg"]
        # Must be the original dict, not a list wrapping a JSON string
        assert returned_egg == {"priority": 1, "estimate": "2h"}
        assert not isinstance(returned_egg, list)
