"""Tests for mcp_help module."""

import pytest

from src.mcp_help import _help


def get_command_by_name(result: dict, command_name: str) -> dict | None:
    """Helper to extract a command by name from _help() result."""
    commands = result.get("commands", [])
    for cmd in commands:
        if cmd.get("name") == command_name:
            return cmd
    return None


def get_param_names(command: dict) -> set[str]:
    """Extract parameter names from a command dict."""
    params = command.get("parameters", [])
    return {p["name"] for p in params}


@pytest.mark.parametrize("command_name", ["create_ticket", "update_ticket"])
def test_owner_param_absent(command_name: str):
    """Verify the deprecated owner param is not in create_ticket or update_ticket."""
    result = _help()
    cmd = get_command_by_name(result, command_name)
    assert cmd is not None, f"Command {command_name} not found"

    assert "owner" not in get_param_names(cmd), f"Deprecated param 'owner' should not appear in {command_name}"


@pytest.mark.parametrize("command_name", ["create_ticket", "update_ticket"])
def test_priority_param_present(command_name: str):
    """Verify priority is listed for create_ticket and update_ticket."""
    result = _help()
    cmd = get_command_by_name(result, command_name)
    assert cmd is not None, f"Command {command_name} not found"

    assert "priority" in get_param_names(cmd), f"priority should appear in {command_name}"


@pytest.mark.parametrize(
    "section",
    [
        pytest.param(lambda: _help.__doc__, id="get_help_docstring"),
        pytest.param(lambda: _help()["concepts"], id="concepts"),
    ],
)
def test_queries_sections_list_priority_terms(section):
    """Both QUERIES sections list the six priority terms, negatives and priority=none."""
    text = " ".join(section().split())

    for term in ("priority=N", "priority!=N", "priority<N", "priority<=N", "priority>N", "priority>=N"):
        assert term in text
    assert "negatives allowed" in text
    assert "priority=none" in text


def test_reference_materials_param_in_create_ticket():
    """Verify reference_materials parameter is present in create_ticket."""
    result = _help()
    cmd = get_command_by_name(result, "create_ticket")
    assert cmd is not None, "create_ticket command not found"

    param_names = get_param_names(cmd)
    assert "reference_materials" in param_names, "reference_materials parameter should be in create_ticket"


def test_bees_version_not_in_concepts():
    """Verify bees_version does not appear in concepts text."""
    result = _help()
    concepts = result.get("concepts", "")
    assert "bees_version" not in concepts, "bees_version should not appear in concepts"


def test_schema_version_in_concepts():
    """Verify schema_version appears in concepts text."""
    result = _help()
    concepts = result.get("concepts", "")
    assert "schema_version" in concepts, "schema_version should appear in concepts"


def test_status_values_section_in_concepts():
    """Verify STATUS_VALUES section appears in concepts text."""
    result = _help()
    concepts = result.get("concepts", "")
    assert "STATUS_VALUES" in concepts, "STATUS_VALUES section should appear in concepts"


def test_all_expected_commands_present():
    """Verify all expected command names are present."""
    expected_commands = {
        "health_check",
        "create_ticket",
        "update_ticket",
        "delete_ticket",
        "show_ticket",
        "get_types",
        "set_types",
        "add_named_query",
        "execute_named_query",
        "execute_freeform_query",
        "generate_index",
        "colonize_hive",
        "list_hives",
        "abandon_hive",
        "rename_hive",
        "sanitize_hive",
        "move_bee",
    }

    result = _help()
    commands = result.get("commands", [])
    actual_commands = {cmd["name"] for cmd in commands}

    assert actual_commands == expected_commands, (
        f"Command name mismatch. Missing: {expected_commands - actual_commands}, "
        f"Extra: {actual_commands - expected_commands}"
    )


def test_create_ticket_has_expected_params():
    """Verify create_ticket has all expected parameters."""
    expected_params = {
        "ticket_type",
        "title",
        "hive_name",
        "description",
        "parent",
        "children",
        "up_dependencies",
        "down_dependencies",
        "tags",
        "status",
        "reference_materials",
        "priority",
    }

    result = _help()
    cmd = get_command_by_name(result, "create_ticket")
    assert cmd is not None, "create_ticket command not found"

    actual_params = get_param_names(cmd)
    assert actual_params == expected_params, (
        f"create_ticket param mismatch. Missing: {expected_params - actual_params}, "
        f"Extra: {actual_params - expected_params}"
    )


def test_update_ticket_has_expected_params():
    """Verify update_ticket has all expected parameters."""
    expected_params = {
        "ticket_id",
        "title",
        "description",
        "parent",
        "children",
        "up_dependencies",
        "down_dependencies",
        "tags",
        "status",
        "priority",
    }

    result = _help()
    cmd = get_command_by_name(result, "update_ticket")
    assert cmd is not None, "update_ticket command not found"

    actual_params = get_param_names(cmd)
    assert actual_params == expected_params, (
        f"update_ticket param mismatch. Missing: {expected_params - actual_params}, "
        f"Extra: {actual_params - expected_params}"
    )
