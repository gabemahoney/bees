"""
Unit tests for MCP server business logic and ticket operations.

PURPOSE:
Tests the core MCP server ticket operations (create, update, delete) including
validation, business rules, and relationship management.
"""

from unittest.mock import patch

import pytest

from src.config import load_bees_config, save_bees_config
from src.mcp_id_utils import parse_ticket_id
from src.constants import GUID_LENGTH
from src.mcp_server import _create_ticket, _show_ticket, _update_ticket
from src.repo_context import repo_root_context
from src.ticket_factory import create_bee, create_child_tier
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_BACKEND,
    TAG_ALPHA,
    TAG_BETA,
    TAG_DELTA,
    TAG_GAMMA,
    TICKET_ID_INVALID_NOPE,
    TICKET_ID_INVALID_SHORT_ID,
    TICKET_ID_INVALID_SINGLE_CHAR,
    TICKET_ID_MCP_BEE_VARIANT,
    TICKET_ID_MCP_SUBTASK_VARIANT,
    TICKET_ID_MCP_TASK_VARIANT,
    TICKET_ID_NONEXISTENT,
    TICKET_ID_VALID_T3_CAPS,
    TITLE_TEST_BEE,
    TITLE_TEST_TASK,
)


@pytest.fixture
def git_repo_tmp_path(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create a temporary directory with git repo structure."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    write_scoped_config(mock_global_bees_dir, tmp_path, {
        "hives": {},
        "child_tiers": {},
    })
    with repo_root_context(tmp_path):
        yield tmp_path


class TestUpdateTicketSchema:
    """Tests that _update_ticket parameter types produce MCP-compatible schemas.

    Regression test for a bug where list/int params included Literal["__UNSET__"]
    in their type union, which added a string const to the anyOf JSON schema.
    MCP clients seeing a string type in the anyOf would serialize arrays as JSON
    strings, causing Pydantic validation to fail at the MCP transport layer.
    """

    def test_list_and_int_params_exclude_literal_unset(self):
        """Verify list/int params don't include Literal['__UNSET__'] in type hints.

        String params (title, description, etc.) can safely include the Literal
        because both the sentinel and valid values are strings — no schema conflict.
        """
        import inspect
        from typing import Literal, get_args, get_origin

        sig = inspect.signature(_update_ticket)
        # Params that must NOT have Literal["__UNSET__"] in their type union
        non_string_params = ["up_dependencies", "down_dependencies", "tags", "add_tags", "remove_tags"]

        for param_name in non_string_params:
            param = sig.parameters[param_name]
            annotation = param.annotation
            # Check if it's a Union (which shows as types.UnionType or typing.Union)
            args = get_args(annotation)
            if not args:
                continue  # Not a union, skip
            for arg in args:
                origin = get_origin(arg)
                if origin is Literal:
                    literal_values = get_args(arg)
                    assert "__UNSET__" not in literal_values, (
                        f"Parameter '{param_name}' has Literal['__UNSET__'] in its type union. "
                        f"This causes MCP clients to serialize arrays/ints as strings. "
                        f"Use `list[str] | None = _UNSET` instead (Pydantic v2 skips default validation)."
                    )

    def test_pydantic_validates_list_param_from_json(self):
        """Simulate FastMCP schema validation: list params deserialize from JSON correctly."""
        import inspect

        from pydantic import TypeAdapter

        sig = inspect.signature(_update_ticket)
        list_params = ["up_dependencies", "down_dependencies", "tags"]

        for param_name in list_params:
            annotation = sig.parameters[param_name].annotation
            adapter = TypeAdapter(annotation)

            # Should accept a Python list (normal MCP deserialization)
            result = adapter.validate_python(["ticket-id-1", "ticket-id-2"])
            assert result == ["ticket-id-1", "ticket-id-2"], f"{param_name}: list validation failed"

            # Should accept None (clear the field)
            result = adapter.validate_python(None)
            assert result is None, f"{param_name}: None validation failed"



class TestUpdateTicket:
    """Tests for update_ticket MCP tool functionality."""

    async def test_update_ticket_basic_fields(self, hive_tier_config):
        """Test updating basic fields (title, tags, status)."""
        repo_root, hive_path, tier_config = hive_tier_config

        from src.paths import get_ticket_path
        from src.reader import read_ticket

        epic_id, _ = create_bee(
            hive_name=HIVE_BACKEND, title="Original Title", description="Original description",
            tags=["label1"], status="open",
        )

        result = await _update_ticket(
            ticket_id=epic_id, title="Updated Title", description="Updated description",
            tags=["label1", "label2"], status="in_progress",
        )

        assert result["status"] == "success"
        assert result["updated"] == [epic_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        assert bee.title == "Updated Title"
        assert bee.description == "Updated description"
        assert bee.tags == ["label1", "label2"]
        assert bee.status == "in_progress"

    @pytest.mark.parametrize(
        "invalid_title", ["", "   "],
    )
    async def test_update_ticket_empty_title(self, hive_tier_config, invalid_title):
        """Test updating with empty/whitespace title returns error dict."""
        epic_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Original Title")
        result = await _update_ticket(ticket_id=epic_id, title=invalid_title)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_title"
        assert "Ticket title cannot be empty" in result["message"]

    async def test_update_ticket_nonexistent(self, hive_tier_config):
        """Test updating a non-existent ticket returns error dict."""
        result = await _update_ticket(ticket_id=TICKET_ID_NONEXISTENT, title="Test")
        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"

    @pytest.mark.parametrize(
        "factory,factory_kwargs,update_kwargs,error_match",
        [
            pytest.param("create_child_tier", {"ticket_type": "t1", "title": TITLE_TEST_TASK, "parent": None}, {"up_dependencies": [TICKET_ID_NONEXISTENT]}, "Dependency ticket does not exist", id="nonexistent_up_dep"),
            pytest.param("create_child_tier", {"ticket_type": "t1", "title": TITLE_TEST_TASK, "parent": None}, {"down_dependencies": [TICKET_ID_NONEXISTENT]}, "Dependency ticket does not exist", id="nonexistent_down_dep"),
        ],
    )
    async def test_update_ticket_nonexistent_relationships(self, hive_tier_config, factory, factory_kwargs, update_kwargs, error_match):
        """Test updating with non-existent dependencies returns error dict."""
        _, _, tier_config = hive_tier_config
        if factory == "create_child_tier" and "t1" not in tier_config:
            return  # Skip: t1 tickets not valid in bees-only hive
        # Create parent bee first if using create_child_tier
        if factory == "create_child_tier":
            parent_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Parent Bee")
            factory_kwargs["parent"] = parent_id
            factory_fn = create_child_tier
        else:
            factory_fn = create_bee
        ticket_id, _ = factory_fn(hive_name=HIVE_BACKEND, **factory_kwargs)
        result = await _update_ticket(ticket_id=ticket_id, **update_kwargs)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_dependency"
        assert error_match in result["message"]

    async def test_update_ticket_circular_dependency(self, hive_tier_config):
        """Test updating with circular dependency returns error dict."""
        _, _, tier_config = hive_tier_config
        if "t1" not in tier_config:
            return  # Skip: t1 tickets not valid in bees-only hive
        parent_id, _ = create_bee(title="Parent Bee", hive_name=HIVE_BACKEND)
        task1_id, _ = create_child_tier(ticket_type="t1", hive_name=HIVE_BACKEND, title="Task 1", parent=parent_id)
        task2_id, _ = create_child_tier(ticket_type="t1", hive_name=HIVE_BACKEND, title="Task 2", parent=parent_id)
        result = await _update_ticket(ticket_id=task1_id, up_dependencies=[task2_id], down_dependencies=[task2_id])
        assert result["status"] == "error"
        assert result["error_type"] == "circular_dependency"
        assert "Circular dependency detected" in result["message"]

    async def test_update_ticket_partial_update(self, hive_tier_config):
        """Test that partial updates only modify specified fields."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        epic_id, _ = create_bee(
            hive_name=HIVE_BACKEND, title="Original Title", description="Original description",
            tags=["label1", "label2"], status="open",
        )
        await _update_ticket(ticket_id=epic_id, title="Updated Title", status="in_progress")

        bee = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        assert bee.title == "Updated Title"
        assert bee.status == "in_progress"
        assert bee.description == "Original description"
        assert bee.tags == ["label1", "label2"]

    @pytest.mark.parametrize(
        "initial_egg,updated_egg",
        [
            pytest.param(None, "b.Xyz", id="none_to_value"),
            pytest.param("b.Abc", "b.Xyz", id="value_to_different_value"),
            pytest.param("b.Abc", None, id="value_to_none"),
        ],
    )
    async def test_update_ticket_egg_field(self, hive_tier_config, initial_egg, updated_egg):
        """Test updating egg field across various transitions."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        epic_id, _ = create_bee(
            hive_name=HIVE_BACKEND, title=TITLE_TEST_BEE, egg=initial_egg,
        )
        result = await _update_ticket(ticket_id=epic_id, egg=updated_egg)

        assert result["status"] == "success"
        assert result["updated"] == [epic_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        assert bee.egg == updated_egg

    async def test_update_ticket_egg_unchanged_when_not_provided(self, hive_tier_config):
        """Test that egg field is not modified when egg parameter is not passed."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        epic_id, _ = create_bee(
            hive_name=HIVE_BACKEND, title=TITLE_TEST_BEE, egg="b.Original",
        )
        await _update_ticket(ticket_id=epic_id, title="New Title")

        bee = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        assert bee.egg == "b.Original"
        assert bee.title == "New Title"

    async def test_update_ticket_preserves_created_at(self, hive_tier_config):
        """Test that created_at is unchanged after a status update."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        epic_id, _ = create_bee(hive_name=HIVE_BACKEND, title=TITLE_TEST_BEE, status="open")
        original = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        original_created_at = original.created_at

        await _update_ticket(ticket_id=epic_id, status="finished")

        updated = read_ticket(epic_id, file_path=get_ticket_path(epic_id, "bee", HIVE_BACKEND))
        assert updated.created_at == original_created_at


class TestColonizeHiveMCPIntegration:
    """Integration tests for colonize_hive MCP tool wrapper."""

    async def test_colonize_hive_success_case(self, git_repo_tmp_path):
        """Test successful colonization via MCP wrapper."""
        import json

        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "backend_hive"
        hive_path.mkdir()
        result = await _colonize_hive("Back End", str(hive_path))

        assert result["status"] == "success"
        assert result["normalized_name"] == "back_end"
        assert result["display_name"] == "Back End"
        assert result["path"] == str(hive_path)
        assert not (hive_path / "eggs").exists(), "eggs/ should not be auto-created"
        assert not (hive_path / "evicted").exists(), "evicted/ should not be auto-created"
        assert (hive_path / ".hive" / "identity.json").exists()

        # Verify identity data
        with open(hive_path / ".hive" / "identity.json") as f:
            identity_data = json.load(f)
        assert identity_data["normalized_name"] == "back_end"
        assert identity_data["display_name"] == "Back End"
        assert "created_at" in identity_data

    @pytest.mark.parametrize(
        "name,path_suffix,error_match",
        [
            pytest.param("Test Hive", "relative/path", "must be absolute", id="not_absolute"),
            pytest.param("!!!", None, "empty string", id="invalid_name"),
        ],
    )
    async def test_colonize_hive_validation_errors(self, git_repo_tmp_path, name, path_suffix, error_match):
        """Test colonize_hive validation error cases."""
        from src.mcp_hive_ops import _colonize_hive

        if path_suffix and not path_suffix.startswith("/"):
            path = path_suffix  # relative path
        else:
            path = str(git_repo_tmp_path / "test")
            (git_repo_tmp_path / "test").mkdir(exist_ok=True)

        result = await _colonize_hive(name, path)
        assert result["status"] == "error"
        assert error_match in result["message"]

    async def test_colonize_hive_creates_missing_parent(self, git_repo_tmp_path):
        """Test that parent directory is created if it doesn't exist."""
        from src.mcp_hive_ops import _colonize_hive

        nonexistent_parent = git_repo_tmp_path / "does_not_exist" / "nested"
        result = await _colonize_hive("Test Hive", str(nonexistent_parent))
        assert result["status"] == "success"
        assert nonexistent_parent.exists()

    async def test_colonize_hive_duplicate_name(self, git_repo_tmp_path):
        """Test error case: duplicate hive name."""
        from src.mcp_hive_ops import _colonize_hive

        for name in ["hive1", "hive2"]:
            (git_repo_tmp_path / name).mkdir()

        await _colonize_hive("Test Hive", str(git_repo_tmp_path / "hive1"))
        result = await _colonize_hive("Test Hive", str(git_repo_tmp_path / "hive2"))
        assert result["status"] == "error"
        assert result["error_type"] == "duplicate_name_error"
        assert "already exists" in result["message"]

    async def test_colonize_hive_registers_in_config(self, git_repo_tmp_path):
        """Test that colonize_hive registers hive in config.json."""
        from src.config import load_bees_config
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "api"
        hive_path.mkdir()
        await _colonize_hive("API", str(hive_path))

        config = load_bees_config()
        assert "api" in config.hives
        assert config.hives["api"].display_name == "API"

    @pytest.mark.parametrize(
        "display_name,expected_normalized",
        [
            pytest.param("Back End", "back_end", id="spaces_to_underscores"),
            pytest.param("UPPERCASE", "uppercase", id="uppercase_to_lower"),
            pytest.param("Multi Word Name", "multi_word_name", id="multi_word"),
            pytest.param("API-v2", "api_v2", id="hyphen_to_underscore"),
        ],
    )
    async def test_colonize_hive_name_normalization(self, git_repo_tmp_path, display_name, expected_normalized):
        """Test that MCP wrapper correctly normalizes hive names."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / f"hive_{expected_normalized}"
        hive_path.mkdir()
        result = await _colonize_hive(display_name, str(hive_path))
        assert result["normalized_name"] == expected_normalized


class TestColonizeHiveMCPErrorCases:
    """Integration tests for colonize_hive error handling."""

    async def test_colonize_hive_error_writing_identity_file(self, git_repo_tmp_path):
        """Test error case: cannot write .hive/identity.json file."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        original_open = open

        def mock_open_func(file, *args, **kwargs):
            if "identity.json" in str(file):
                raise PermissionError("Permission denied")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", mock_open_func):
            result = await _colonize_hive("Test Hive", str(hive_path))
            assert result["status"] == "error"
            assert result["error_type"] == "filesystem_error"
            assert "identity" in result["message"]

    async def test_colonize_hive_config_write_failure(self, git_repo_tmp_path):
        """Test error case: cannot write config.json."""
        from src.mcp_hive_ops import _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        with patch("src.mcp_hive_ops.save_bees_config", side_effect=OSError("Disk full")):
            with patch("src.mcp_hive_ops.save_global_config", side_effect=OSError("Disk full")):
                result = await _colonize_hive("Test Hive", str(hive_path))
                assert result["status"] == "error"
                assert result["error_type"] in ("config_write_error", "config_error")
                assert "config" in result["message"]


class TestParseTicketId:
    """Tests for parse_ticket_id() utility function."""

    @pytest.mark.parametrize(
        "ticket_id,expected_prefix,expected_short_id",
        [
            pytest.param(TICKET_ID_MCP_BEE_VARIANT, "b", "ab1", id="bee"),
            pytest.param(TICKET_ID_MCP_TASK_VARIANT, "t1", "xyz.9a", id="tier1_task"),
            pytest.param(TICKET_ID_MCP_SUBTASK_VARIANT, "t2", "amx.ab.cd", id="tier2_task"),
            pytest.param(TICKET_ID_VALID_T3_CAPS, "t3", "x4f.2a.bc.de", id="tier3_task"),
            pytest.param(TICKET_ID_INVALID_SINGLE_CHAR, "b", "a", id="short_id"),
        ],
    )
    def test_parse_valid_ticket_id(self, ticket_id, expected_prefix, expected_short_id):
        """Test parsing various valid ticket ID formats."""
        type_prefix, short_id = parse_ticket_id(ticket_id)
        assert type_prefix == expected_prefix
        assert short_id == expected_short_id

    @pytest.mark.parametrize(
        "ticket_id,error_match",
        [
            pytest.param(None, "ticket_id cannot be None", id="none"),
            pytest.param("", "ticket_id cannot be empty", id="empty_string"),
            pytest.param("   ", "ticket_id cannot be empty", id="whitespace_only"),
            pytest.param("no-dot-format", "Invalid ticket_id format", id="missing_dot"),
            pytest.param(".empty-prefix", "Both prefix and shortID required", id="empty_prefix"),
            pytest.param("b.", "Both prefix and shortID required", id="empty_short_id"),
        ],
    )
    def test_parse_invalid_ticket_id(self, ticket_id, error_match):
        """Test that invalid ticket IDs raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            parse_ticket_id(ticket_id)


class TestListHives:
    """Tests for list_hives MCP tool functionality."""

    @pytest.fixture
    def repo_and_ctx(self, bees_repo, monkeypatch, mock_mcp_context, mock_global_bees_dir):
        """Provide bees_repo and a mock MCP context."""
        monkeypatch.chdir(bees_repo)
        write_scoped_config(mock_global_bees_dir, bees_repo, {
            "hives": {},
                "child_tiers": {},
        })
        with repo_root_context(bees_repo):
            yield bees_repo, mock_mcp_context(bees_repo)

    async def test_list_hives_returns_all_hives_from_config(self, repo_and_ctx):
        """Test list_hives returns correct data when config.json exists with hives."""
        from src.config import BeesConfig, HiveConfig, save_bees_config
        from src.mcp_hive_ops import _list_hives

        temp_repo, mock_ctx = repo_and_ctx
        hive1_path = temp_repo / "hive1"
        hive2_path = temp_repo / "hive2"
        hive1_path.mkdir()
        hive2_path.mkdir()

        save_bees_config(BeesConfig(hives={
            "back_end": HiveConfig(display_name="Back End", path=str(hive1_path), created_at="2024-01-01T00:00:00"),
            "frontend": HiveConfig(display_name="Frontend", path=str(hive2_path), created_at="2024-01-02T00:00:00"),
        }))

        result = await _list_hives(mock_ctx)
        assert result["status"] == "success"
        assert len(result["hives"]) == 2
        hives = {h["normalized_name"]: h for h in result["hives"]}
        assert hives["back_end"]["display_name"] == "Back End"
        assert hives["frontend"]["display_name"] == "Frontend"

    @pytest.mark.parametrize(
        "setup",
        [
            pytest.param("no_config", id="no_config"),
            pytest.param("empty_config", id="empty_hives"),
        ],
    )
    async def test_list_hives_empty_scenarios(self, repo_and_ctx, setup):
        """Test list_hives returns empty list with no config or empty hives."""
        from src.config import BeesConfig, save_bees_config
        from src.mcp_hive_ops import _list_hives

        _, mock_ctx = repo_and_ctx
        if setup == "empty_config":
            save_bees_config(BeesConfig(hives={}))

        result = await _list_hives(mock_ctx)
        assert result["status"] == "success"
        assert result["hives"] == []

    async def test_list_hives_handles_exception(self, repo_and_ctx, monkeypatch):
        """Test list_hives handles exceptions gracefully."""
        from src.mcp_hive_ops import _list_hives

        _, mock_ctx = repo_and_ctx
        monkeypatch.setattr("src.mcp_hive_ops.load_bees_config", lambda *a, **kw: (_ for _ in ()).throw(Exception("Failed")))
        result = await _list_hives(mock_ctx)
        assert result["status"] == "error"
        assert result["error_type"] == "list_hives_error"
        assert "Failed to list hives" in result["message"]


class TestAbandonHive:
    """Tests for _abandon_hive() function."""

    async def test_abandon_hive_removes_from_config(self, git_repo_tmp_path):
        """Test that abandon_hive removes hive entry from config."""
        from src.config import load_bees_config
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))
        assert "test_hive" in load_bees_config().hives

        result = await _abandon_hive("Test Hive")
        assert result["status"] == "success"
        assert "test_hive" not in load_bees_config().hives

    async def test_abandon_hive_preserves_files(self, git_repo_tmp_path):
        """Test that abandon_hive leaves ticket files and directories intact."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Test Hive", str(hive_path))
        (hive_path / "test.md").write_text("test ticket")

        await _abandon_hive("Test Hive")

        assert hive_path.exists()
        assert (hive_path / "test.md").read_text() == "test ticket"
        assert (hive_path / ".hive").exists()
        assert not (hive_path / "eggs").exists(), "eggs/ should not be auto-created"
        assert not (hive_path / "evicted").exists(), "evicted/ should not be auto-created"

    async def test_abandon_hive_returns_error_for_nonexistent(self, git_repo_tmp_path):
        """Test that abandon_hive returns error dict for non-existent hive."""
        from src.mcp_hive_ops import _abandon_hive

        result = await _abandon_hive("NonExistent")
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    @pytest.mark.parametrize(
        "abandon_name",
        [
            pytest.param("back_end", id="normalized_name"),
            pytest.param("Back End", id="display_name"),
            pytest.param("BACK END", id="uppercase"),
        ],
    )
    async def test_abandon_hive_name_variants(self, abandon_name, git_repo_tmp_path):
        """Test that abandon_hive works with various name forms."""
        from src.mcp_hive_ops import _abandon_hive, _colonize_hive

        hive_path = git_repo_tmp_path / "test_hive"
        hive_path.mkdir()
        await _colonize_hive("Back End", str(hive_path))
        result = await _abandon_hive(abandon_name)
        assert result["status"] == "success"

@pytest.mark.integration
class TestShowTicket:
    """Tests for the show_ticket MCP command."""

    async def test_show_ticket_epic(self, hive_env):
        """Test showing a bee ticket with all fields."""
        repo_root, hive_path, hive_name = hive_env
        ticket_id, _ = create_bee(
            title=TITLE_TEST_BEE, description="Epic description", tags=["test", "bee"],
            status="open", hive_name=HIVE_BACKEND,
        )
        result = await _show_ticket(ticket_ids=[ticket_id])

        assert result["status"] == "success"
        assert result["tickets"][0]["ticket_id"] == ticket_id
        assert result["tickets"][0]["ticket_type"] == "bee"
        assert result["tickets"][0]["title"] == TITLE_TEST_BEE
        assert result["tickets"][0]["tags"] == ["test", "bee"]
        assert result["tickets"][0]["parent"] is None
        # Verify all expected fields present
        for field in ["created_at", "schema_version", "description", "ticket_status",
                      "children", "up_dependencies", "down_dependencies"]:
            assert field in result["tickets"][0]
        assert result["not_found"] == []

    async def test_show_ticket_task(self, hive_env):
        """Test showing a task ticket."""
        repo_root, hive_path, hive_name = hive_env
        epic_id, _ = create_bee(title="Parent Epic", hive_name=HIVE_BACKEND)
        task_id, _ = create_child_tier(
            ticket_type="t1", title=TITLE_TEST_TASK, description="Task description", parent=epic_id,
            tags=["backend"], status="in_progress", hive_name=HIVE_BACKEND,
        )
        result = await _show_ticket(ticket_ids=[task_id])
        assert result["tickets"][0]["ticket_type"] == "t1"
        assert result["tickets"][0]["parent"] == epic_id

    @pytest.mark.parametrize(
        "ticket_id",
        [
            pytest.param(TICKET_ID_NONEXISTENT, id="nonexistent"),
            pytest.param("", id="empty"),
        ],
    )
    async def test_show_ticket_missing_ids_go_to_not_found(self, hive_env, ticket_id):
        """Valid-format but missing IDs go into not_found; no error raised."""
        result = await _show_ticket(ticket_ids=[ticket_id])
        assert result["status"] == "success"
        assert result["tickets"] == []
        assert ticket_id in result["not_found"]

    @pytest.mark.parametrize(
        "ticket_id",
        [
            pytest.param(TICKET_ID_INVALID_SHORT_ID, id="malformed_short"),
            pytest.param(TICKET_ID_INVALID_NOPE, id="malformed_long"),
            pytest.param("invalid!!!", id="malformed_special_chars"),
        ],
    )
    async def test_show_ticket_invalid_format_returns_error(self, hive_env, ticket_id):
        """IDs that don't match the ticket ID format return an error response."""
        result = await _show_ticket(ticket_ids=[ticket_id])
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_id"

    async def test_show_ticket_empty_list(self, hive_env):
        """Empty ticket_ids list returns empty success response."""
        result = await _show_ticket(ticket_ids=[])
        assert result == {"status": "success", "tickets": [], "not_found": [], "errors": []}

    async def test_show_ticket_partial_not_found(self, hive_env):
        """One valid + one nonexistent ID: valid ticket returned, missing ID in not_found."""
        repo_root, hive_path, hive_name = hive_env
        ticket_id, _ = create_bee(title="Valid Bee", hive_name=HIVE_BACKEND)
        fake_id = "b.yyy"
        result = await _show_ticket(ticket_ids=[ticket_id, fake_id])
        assert result["status"] == "success"
        assert len(result["tickets"]) == 1
        assert result["tickets"][0]["ticket_id"] == ticket_id
        assert result["not_found"] == [fake_id]

    async def test_show_ticket_all_not_found(self, hive_env):
        """All nonexistent IDs: empty tickets list, all IDs in not_found."""
        fake_ids = ["b.xxx", "b.yyy"]
        result = await _show_ticket(ticket_ids=fake_ids)
        assert result["status"] == "success"
        assert result["tickets"] == []
        assert result["not_found"] == fake_ids

    async def test_show_ticket_with_dependencies(self, hive_env):
        """Test showing a ticket with dependencies."""
        repo_root, hive_path, hive_name = hive_env
        parent_id, _ = create_bee(title="Parent Bee", hive_name=HIVE_BACKEND)
        blocking_id, _ = create_child_tier(ticket_type="t1", title="Blocking Task", parent=parent_id, hive_name=HIVE_BACKEND)
        ticket_id, _ = create_child_tier(ticket_type="t1", title="Dependent Task", parent=parent_id, hive_name=HIVE_BACKEND)
        await _update_ticket(ticket_id=ticket_id, up_dependencies=[blocking_id])
        result = await _show_ticket(ticket_ids=[ticket_id])
        assert result["tickets"][0]["up_dependencies"] == [blocking_id]

    @pytest.mark.parametrize(
        "ticket_id,title,egg_input,expected_egg",
        [
            pytest.param(
                "b.eg1",
                "Egg String Bee",
                "https://example.com/spec.md",
                "https://example.com/spec.md",
                id="string_default_resolver",
            ),
            pytest.param(
                "b.eg2",
                "Null Egg Bee",
                None,
                None,
                id="null_egg",
            ),
        ],
    )
    async def test_show_ticket_egg_variants(self, hive_env, ticket_id, title, egg_input, expected_egg):
        """show_ticket returns egg as-is (default resolver) or null."""
        repo_root, hive_path, hive_name = hive_env
        write_ticket_file(hive_path, ticket_id, title=title, egg=egg_input)
        result = await _show_ticket(ticket_ids=[ticket_id])
        assert result["status"] == "success"
        assert result["tickets"][0]["egg"] == expected_egg

    async def test_show_ticket_egg_custom_resolver(self, hive_env, tmp_path):
        """show_ticket uses custom egg_resolver subprocess when configured."""
        repo_root, hive_path, hive_name = hive_env

        resolver_script = tmp_path / "egg_resolver.sh"
        resolver_script.write_text('#!/bin/bash\necho \'["resolved_resource.txt"]\'\n')
        resolver_script.chmod(0o755)

        config = load_bees_config()
        config.egg_resolver = str(resolver_script)
        save_bees_config(config)

        write_ticket_file(hive_path, "b.eg3", title="Custom Resolver Bee", egg="input-spec")
        result = await _show_ticket(ticket_ids=["b.eg3"], resolved_root=repo_root)
        assert result["status"] == "success"
        assert result["tickets"][0]["egg"] == ["resolved_resource.txt"]


@pytest.mark.integration
class TestGuidInTicketOps:
    """Tests for GUID field in create, show, and update ticket operations."""

    async def test_create_bee_returns_guid(self, hive_env):
        """create_ticket (bee) response includes guid key with correct length and prefix."""
        repo_root, hive_path, hive_name = hive_env
        result = await _create_ticket(
            ticket_type="bee", title="GUID Bee", hive_name=HIVE_BACKEND,
        )
        assert "guid" in result
        guid = result["guid"]
        assert len(guid) == GUID_LENGTH
        # GUID prefix matches the bee's short_id (3 chars after "b.")
        short_id = result["ticket_id"].split(".", 1)[1]
        assert guid[:3] == short_id

    async def test_create_t1_returns_guid(self, hive_env):
        """create_ticket (t1) response includes guid with prefix matching period-stripped short_id."""
        repo_root, hive_path, hive_name = hive_env
        parent_id, _ = create_bee(title="Parent", hive_name=HIVE_BACKEND)
        result = await _create_ticket(
            ticket_type="t1", title="GUID Task", parent=parent_id, hive_name=HIVE_BACKEND,
        )
        assert "guid" in result
        guid = result["guid"]
        assert len(guid) == GUID_LENGTH
        short_id = result["ticket_id"].split(".", 1)[1]
        stripped = short_id.replace(".", "")  # guid seeded with period-stripped short_id
        assert guid[:5] == stripped

    async def test_show_ticket_includes_guid(self, hive_env):
        """show_ticket response includes the guid field."""
        repo_root, hive_path, hive_name = hive_env
        create_result = await _create_ticket(
            ticket_type="bee", title="Show GUID Bee", hive_name=HIVE_BACKEND,
        )
        show_result = await _show_ticket(ticket_ids=[create_result["ticket_id"]])
        assert "guid" in show_result["tickets"][0]
        assert show_result["tickets"][0]["guid"] == create_result["guid"]

    async def test_update_ticket_id_guid_params_removed(self, hive_env):
        """update_ticket no longer accepts id or guid kwargs — passing them raises TypeError."""
        repo_root, hive_path, hive_name = hive_env
        ticket_id, _ = create_bee(title="Immutable Test", hive_name=HIVE_BACKEND)
        with pytest.raises(TypeError):
            await _update_ticket(ticket_id=ticket_id, id="anything")
        with pytest.raises(TypeError):
            await _update_ticket(ticket_id=ticket_id, guid="anything")


class TestAddRemoveTags:
    """Tests for add_tags and remove_tags parameters in _update_ticket."""

    @pytest.mark.parametrize(
        "initial_tags,add,expected",
        [
            pytest.param([], [TAG_GAMMA], [TAG_GAMMA], id="no_tags_add_one"),
            pytest.param([TAG_ALPHA], [TAG_ALPHA, TAG_GAMMA], [TAG_ALPHA, TAG_GAMMA], id="dedup_existing"),
        ],
    )
    async def test_add_tags_appends_without_duplicates(self, hive_tier_config, initial_tags, add, expected):
        """add_tags appends new tags and deduplicates existing ones."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        bee_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Tag Test Bee", tags=initial_tags)
        result = await _update_ticket(ticket_id=bee_id, add_tags=add)

        assert result["updated"] == [bee_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", HIVE_BACKEND))
        assert sorted(bee.tags) == sorted(expected)

    @pytest.mark.parametrize(
        "initial_tags,remove,expected",
        [
            pytest.param([TAG_ALPHA, TAG_BETA], [TAG_ALPHA], [TAG_BETA], id="remove_existing"),
            pytest.param([TAG_ALPHA], [TAG_BETA], [TAG_ALPHA], id="skip_absent"),
        ],
    )
    async def test_remove_tags_removes_and_skips_absent(self, hive_tier_config, initial_tags, remove, expected):
        """remove_tags removes present tags and silently skips absent ones."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        bee_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Remove Tag Bee", tags=initial_tags)
        result = await _update_ticket(ticket_id=bee_id, remove_tags=remove)

        assert result["updated"] == [bee_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", HIVE_BACKEND))
        assert sorted(bee.tags) == sorted(expected)

    async def test_add_remove_tags_combined_with_status_change(self, hive_tier_config):
        """add_tags and remove_tags can be combined with a status change."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        bee_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Combined Tag Bee", tags=[TAG_ALPHA])
        result = await _update_ticket(
            ticket_id=bee_id,
            add_tags=[TAG_GAMMA],
            remove_tags=[TAG_ALPHA],
            status="worker",
        )

        assert result["updated"] == [bee_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", HIVE_BACKEND))
        assert bee.tags == [TAG_GAMMA]
        assert bee.status == "worker"

    async def test_same_tag_in_add_and_remove_ends_up_removed(self, hive_tier_config):
        """When a tag appears in both add_tags and remove_tags, it ends up removed."""
        from src.paths import get_ticket_path
        from src.reader import read_ticket

        bee_id, _ = create_bee(hive_name=HIVE_BACKEND, title="Add-Remove Conflict Bee", tags=[TAG_ALPHA])
        result = await _update_ticket(
            ticket_id=bee_id,
            add_tags=[TAG_DELTA],
            remove_tags=[TAG_DELTA],
        )

        assert result["updated"] == [bee_id]
        assert result["not_found"] == []
        assert result["failed"] == []
        bee = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", HIVE_BACKEND))
        assert TAG_DELTA not in bee.tags


class TestResolveEggsTool:
    """Tests that resolve_eggs is NOT exposed as an MCP tool."""

    def test_resolve_eggs_not_registered_as_mcp_tool(self):
        """resolve_eggs must not be registered as an MCP tool on the server."""
        import src.mcp_server

        assert not hasattr(src.mcp_server, "resolve_eggs")
