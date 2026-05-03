"""Tests for bee reference_materials field creation, resolution, and update."""

import pytest

from src.mcp_server import _create_ticket
from src.mcp_ticket_ops import _show_ticket, _update_ticket
from src.paths import get_ticket_path
from src.reader import read_ticket
from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_BACKEND,
    REFERENCE_MATERIALS_MULTI,
    REFERENCE_MATERIALS_NULL,
    REFERENCE_MATERIALS_SINGLE,
    REFERENCE_MATERIALS_WITH_RESOLVER,
)


class TestCreateBeeWithReferenceMaterials:
    """Tests for creating bee tickets with reference_materials field."""

    async def test_create_bee_with_single_reference_material(self, hive_tier_config):
        """Create bee with a single reference material entry and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Single Reference",
            hive_name=HIVE_BACKEND,
            reference_materials=REFERENCE_MATERIALS_SINGLE,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.reference_materials == REFERENCE_MATERIALS_SINGLE

    async def test_create_bee_with_null_reference_materials(self, hive_tier_config):
        """Create bee with explicit null reference_materials and verify it persists."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Null Reference",
            hive_name=HIVE_BACKEND,
            reference_materials=REFERENCE_MATERIALS_NULL,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.reference_materials is None

    async def test_create_bee_with_multiple_reference_materials(self, hive_tier_config):
        """Create bee with multiple reference material entries and verify they persist."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee with Multi Reference",
            hive_name=HIVE_BACKEND,
            reference_materials=REFERENCE_MATERIALS_MULTI,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.reference_materials == REFERENCE_MATERIALS_MULTI
        assert len(ticket.reference_materials) == 2

    async def test_create_bee_without_reference_materials_defaults_to_null(self, hive_tier_config):
        """Create bee without reference_materials parameter and verify it defaults to null."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee without Reference",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"
        ticket_id = result["ticket_id"]

        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.reference_materials is None

        # Verify YAML frontmatter contains reference_materials: null
        ticket_path = get_ticket_path(ticket_id, "bee", HIVE_BACKEND)
        content = ticket_path.read_text()
        assert "reference_materials: null" in content or "reference_materials: ~" in content

    async def test_create_t1_ticket_no_reference_materials_in_frontmatter(self, hive_tier_config):
        """Create t1 ticket and verify reference_materials field is NOT in frontmatter."""
        repo_root, hive_path, tier_config = hive_tier_config

        if "t1" not in tier_config:
            pytest.skip("bees_only config has no t1 tier")

        bee_result = await _create_ticket(
            ticket_type="bee",
            title="Parent Bee",
            hive_name=HIVE_BACKEND,
        )
        bee_id = bee_result["ticket_id"]

        t1_result = await _create_ticket(
            ticket_type="t1",
            title="Task without Reference",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert t1_result["status"] == "success"
        t1_id = t1_result["ticket_id"]

        t1_path = get_ticket_path(t1_id, "t1", HIVE_BACKEND)
        content = t1_path.read_text()
        assert "reference_materials:" not in content

    async def test_show_ticket_returns_reference_materials_field(self, hive_tier_config):
        """Show ticket via MCP and verify reference_materials field is present."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Bee for Show Test",
            hive_name=HIVE_BACKEND,
            reference_materials=REFERENCE_MATERIALS_SINGLE,
        )
        ticket_id = result["ticket_id"]

        show_result = await _show_ticket(ticket_ids=[ticket_id])

        assert show_result["status"] == "success"
        assert "reference_materials" in show_result["tickets"][0]


class TestShowTicketReferenceMaterialsResolution:
    """Tests for show_ticket reference_materials field in the response."""

    async def test_show_ticket_null_reference_materials(self, hive_tier_config):
        """show_ticket returns null reference_materials when stored as null."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Null Ref Bee",
            hive_name=HIVE_BACKEND,
            reference_materials=None,
        )
        ticket_id = result["ticket_id"]

        show_result = await _show_ticket(ticket_ids=[ticket_id])

        assert show_result["status"] == "success"
        assert "reference_materials" in show_result["tickets"][0]
        assert show_result["tickets"][0]["reference_materials"] is None

    @pytest.mark.parametrize(
        "rm_value",
        [
            pytest.param(REFERENCE_MATERIALS_SINGLE, id="single_entry"),
            pytest.param(REFERENCE_MATERIALS_MULTI, id="multi_entry"),
        ],
    )
    async def test_show_ticket_reference_materials_has_resolved_key(
        self, hive_tier_config, rm_value
    ):
        """show_ticket returns reference_materials entries with 'resolved' key added."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee",
            title="Ref Bee",
            hive_name=HIVE_BACKEND,
            reference_materials=rm_value,
        )
        ticket_id = result["ticket_id"]

        show_result = await _show_ticket(ticket_ids=[ticket_id])

        assert show_result["status"] == "success"
        rm = show_result["tickets"][0]["reference_materials"]
        assert rm is not None
        assert len(rm) == len(rm_value)
        for entry in rm:
            assert "value" in entry
            assert "resolved" in entry


class TestUpdateTicketReferenceMaterials:
    """Tests for updating bee tickets with reference_materials field."""

    @pytest.mark.parametrize(
        "rm_value,expected",
        [
            pytest.param(None, None, id="null"),
            pytest.param(REFERENCE_MATERIALS_SINGLE, REFERENCE_MATERIALS_SINGLE, id="single"),
            pytest.param(REFERENCE_MATERIALS_MULTI, REFERENCE_MATERIALS_MULTI, id="multi"),
        ],
    )
    async def test_update_ticket_reference_materials_types(self, hive_tier_config, rm_value, expected):
        """Update ticket reference_materials with various values and verify they persist."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Reference Update Test", hive_name=HIVE_BACKEND,
        )
        ticket_id = result["ticket_id"]

        await _update_ticket(ticket_ids=ticket_id, reference_materials=rm_value, hive_name=HIVE_BACKEND)

        # Read back raw ticket value (not via show_ticket which adds "resolved" key)
        ticket = read_ticket(ticket_id, file_path=get_ticket_path(ticket_id, "bee", HIVE_BACKEND))
        assert ticket.reference_materials == expected

    async def test_update_ticket_reference_materials_show_has_resolved_key(self, hive_tier_config):
        """Update reference_materials and verify show_ticket adds 'resolved' key per entry."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Show Reference Test", hive_name=HIVE_BACKEND,
        )
        ticket_id = result["ticket_id"]

        new_rm = [{"value": "docs/api.md"}]
        await _update_ticket(ticket_ids=ticket_id, reference_materials=new_rm, hive_name=HIVE_BACKEND)

        show_result = await _show_ticket(ticket_ids=[ticket_id])
        rm = show_result["tickets"][0]["reference_materials"]
        assert rm is not None
        assert len(rm) == 1
        assert rm[0]["value"] == "docs/api.md"
        assert "resolved" in rm[0]

    async def test_update_ticket_reference_materials_via_show(self, hive_tier_config):
        """Update reference_materials and verify the entries appear correctly in show_ticket."""
        repo_root, hive_path, tier_config = hive_tier_config

        result = await _create_ticket(
            ticket_type="bee", title="Show Reference Test 2", hive_name=HIVE_BACKEND,
        )
        ticket_id = result["ticket_id"]

        new_rm = [{"value": "docs/api.md"}, {"value": "docs/guide.md"}]
        await _update_ticket(ticket_ids=ticket_id, reference_materials=new_rm, hive_name=HIVE_BACKEND)

        show_result = await _show_ticket(ticket_ids=[ticket_id])
        rm = show_result["tickets"][0]["reference_materials"]
        assert len(rm) == 2
        values = [e["value"] for e in rm]
        assert "docs/api.md" in values
        assert "docs/guide.md" in values


class TestReferenceMaterialsInWriteTicketFile:
    """Tests that write_ticket_file correctly writes reference_materials to YAML frontmatter."""

    def test_write_ticket_file_with_reference_materials(self, hive_tier_config):
        """write_ticket_file writes reference_materials to the YAML frontmatter."""
        repo_root, hive_path, tier_config = hive_tier_config

        write_ticket_file(
            hive_path, "b.rm1", title="Reference Bee",
            reference_materials=REFERENCE_MATERIALS_SINGLE,
        )

        ticket_path = hive_path / "b.rm1" / "b.rm1.md"
        content = ticket_path.read_text()
        assert "reference_materials:" in content
        # The dict entry is written in YAML block sequence format
        assert "docs/spec.md" in content

    def test_write_ticket_file_with_null_reference_materials(self, hive_tier_config):
        """write_ticket_file writes reference_materials: null when None."""
        repo_root, hive_path, tier_config = hive_tier_config

        write_ticket_file(
            hive_path, "b.rm2", title="Null Reference Bee",
            reference_materials=None,
        )

        ticket_path = hive_path / "b.rm2" / "b.rm2.md"
        content = ticket_path.read_text()
        assert "reference_materials:" in content

    def test_write_ticket_file_omit_reference_materials(self, hive_tier_config):
        """write_ticket_file omits reference_materials when omit_reference_materials=True."""
        repo_root, hive_path, tier_config = hive_tier_config

        write_ticket_file(
            hive_path, "b.rm3", title="Omit Reference Bee",
            omit_reference_materials=True,
        )

        ticket_path = hive_path / "b.rm3" / "b.rm3.md"
        content = ticket_path.read_text()
        assert "reference_materials:" not in content
