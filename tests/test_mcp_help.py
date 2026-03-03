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


@pytest.mark.parametrize(
    "command_name,deprecated_param",
    [
        ("create_ticket", "owner"),
        ("create_ticket", "priority"),
        ("update_ticket", "owner"),
        ("update_ticket", "priority"),
    ],
    ids=["create_no_owner", "create_no_priority", "update_no_owner", "update_no_priority"],
)
def test_no_deprecated_params(command_name: str, deprecated_param: str):
    """Verify deprecated params (owner, priority) are not in create_ticket or update_ticket."""
    result = _help()
    cmd = get_command_by_name(result, command_name)
    assert cmd is not None, f"Command {command_name} not found"

    param_names = get_param_names(cmd)
    assert deprecated_param not in param_names, (
        f"Deprecated param '{deprecated_param}' should not appear in {command_name}"
    )


def test_egg_param_in_create_ticket():
    """Verify egg parameter is present in create_ticket."""
    result = _help()
    cmd = get_command_by_name(result, "create_ticket")
    assert cmd is not None, "create_ticket command not found"

    param_names = get_param_names(cmd)
    assert "egg" in param_names, "egg parameter should be in create_ticket"


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
        "egg",
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
    }

    result = _help()
    cmd = get_command_by_name(result, "update_ticket")
    assert cmd is not None, "update_ticket command not found"

    actual_params = get_param_names(cmd)
    assert actual_params == expected_params, (
        f"update_ticket param mismatch. Missing: {expected_params - actual_params}, "
        f"Extra: {actual_params - expected_params}"
    )
