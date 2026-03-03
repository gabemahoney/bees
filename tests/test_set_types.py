"""
Unit tests for _set_types in src/mcp_ticket_ops.py.

PURPOSE:
Tests the _set_types function which sets or unsets child_tiers configuration
at three scope levels: global, repo_scope, and hive.

SCOPE - Tests that belong here:
- Parameter validation (invalid scope, missing hive_name, conflicting params, etc.)
- Set operation for each scope level (global, repo_scope, hive)
- Unset operation for each scope level
- Unset idempotency (unsetting when key already absent)
- Bees-only ({}) set test
- Existing tickets unaffected by set_types

SCOPE - Tests that DON'T belong here:
- CLI round-trip tests → test_cli_commands.py (TestSetTypesCommands)
- MCP server wrapper → test_mcp_server.py
- _get_types tests → test_mcp_ticket_ops.py
"""

import asyncio

import pytest

from src.config import load_global_config
from src.mcp_ticket_ops import _set_types, _show_ticket
from tests.test_constants import (
    GLOBAL_TIER_DEFAULT,
    HIVE_BUGS,
    HIVE_FEATURES,
    HIVE_TIER_BEES_ONLY,
    HIVE_TIER_EPICS,
    SCOPE_TIER_DEFAULT,
)


# ===========================================================================
# Error tests (7)
# ===========================================================================


class TestSetTypesErrors:
    @pytest.mark.parametrize("kwargs,expected_error_type", [
        ({"scope": "invalid", "child_tiers": SCOPE_TIER_DEFAULT}, "invalid_scope"),
        ({"scope": "hive", "child_tiers": SCOPE_TIER_DEFAULT}, "missing_hive_name"),
        ({"scope": "global", "child_tiers": {"t1": "not_a_list"}}, "invalid_child_tiers"),
        ({"scope": "global", "child_tiers": None, "unset": False}, "missing_child_tiers"),
        ({"scope": "global", "child_tiers": SCOPE_TIER_DEFAULT, "unset": True}, "conflicting_params"),
    ])
    def test_parameter_validation_errors(self, isolated_bees_env, kwargs, expected_error_type):
        result = asyncio.run(_set_types(**kwargs))
        assert result["status"] == "error"
        assert result["error_type"] == expected_error_type

    def test_hive_not_found(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_types(
                scope="hive",
                hive_name="nonexistent",
                child_tiers=SCOPE_TIER_DEFAULT,
                resolved_root=helper.base_path,
            )
        )
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    def test_no_matching_scope(self, isolated_bees_env, tmp_path):
        # Config exists but has no scope matching our resolved_root
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Use a path that doesn't match any scope pattern
        fake_root = tmp_path / "no_match_repo"
        fake_root.mkdir()

        result = asyncio.run(
            _set_types(
                scope="repo_scope",
                child_tiers=SCOPE_TIER_DEFAULT,
                resolved_root=fake_root,
            )
        )
        assert result["status"] == "error"
        assert result["error_type"] == "no_matching_scope"


# ===========================================================================
# Set operations (3 scopes)
# ===========================================================================


class TestSetTypesSet:
    def test_set_global(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_types(scope="global", child_tiers=GLOBAL_TIER_DEFAULT)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"
        assert result["child_tiers"] == GLOBAL_TIER_DEFAULT

        # Verify persisted
        config = load_global_config()
        assert config["child_tiers"] == GLOBAL_TIER_DEFAULT

    def test_set_repo_scope(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        new_tiers = {"t1": ["Story", "Stories"]}
        result = asyncio.run(
            _set_types(
                scope="repo_scope",
                child_tiers=new_tiers,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"
        assert result["child_tiers"] == new_tiers

        # Verify persisted in the scope block
        config = load_global_config()
        scope_block = config["scopes"][str(helper.base_path)]
        assert scope_block["child_tiers"] == new_tiers

    def test_set_hive(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_types(
                scope="hive",
                hive_name=HIVE_FEATURES,
                child_tiers=HIVE_TIER_EPICS,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "hive"
        assert result["hive_name"] == HIVE_FEATURES
        assert result["child_tiers"] == {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]}

        # Verify persisted in the hive entry
        config = load_global_config()
        hive_entry = config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]
        assert hive_entry["child_tiers"] == {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]}


# ===========================================================================
# Unset operations (3 scopes)
# ===========================================================================


class TestSetTypesUnset:
    def test_unset_global(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # First set global child_tiers
        config = load_global_config()
        config["child_tiers"] = GLOBAL_TIER_DEFAULT
        from src.config import save_global_config
        save_global_config(config)

        # Now unset
        result = asyncio.run(
            _set_types(scope="global", unset=True)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"

        # Verify removed
        config = load_global_config()
        assert "child_tiers" not in config

    def test_unset_repo_scope(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_types(scope="repo_scope", unset=True, resolved_root=helper.base_path)
        )

        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"

        # Verify removed from scope block
        config = load_global_config()
        scope_block = config["scopes"][str(helper.base_path)]
        assert "child_tiers" not in scope_block

    def test_unset_hive(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # First set hive-level child_tiers
        asyncio.run(
            _set_types(
                scope="hive",
                hive_name=HIVE_FEATURES,
                child_tiers=HIVE_TIER_EPICS,
                resolved_root=helper.base_path,
            )
        )

        # Now unset
        result = asyncio.run(
            _set_types(
                scope="hive",
                hive_name=HIVE_FEATURES,
                unset=True,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "hive"
        assert result["hive_name"] == HIVE_FEATURES

        # Verify removed from hive entry
        config = load_global_config()
        hive_entry = config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]
        assert "child_tiers" not in hive_entry


# ===========================================================================
# Unset idempotency
# ===========================================================================


class TestSetTypesUnsetIdempotency:
    def test_unset_global_already_absent(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Global child_tiers is not set — unset should still succeed
        result = asyncio.run(
            _set_types(scope="global", unset=True)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"


# ===========================================================================
# Bees-only ({}) set test
# ===========================================================================


class TestSetTypeBeesOnly:
    def test_set_bees_only_hive(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_BUGS)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_types(
                scope="hive",
                hive_name=HIVE_BUGS,
                child_tiers=HIVE_TIER_BEES_ONLY,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["child_tiers"] == {}

        # Verify persisted
        config = load_global_config()
        hive_entry = config["scopes"][str(helper.base_path)]["hives"][HIVE_BUGS]
        assert hive_entry["child_tiers"] == {}


# ===========================================================================
# Existing tickets unaffected
# ===========================================================================


class TestSetTypesExistingTickets:
    def test_existing_tickets_unaffected(self, isolated_bees_env):
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Create a ticket before changing types
        helper.create_ticket(hive_dir, "b.abc", "bee", "Test Bee")

        # Change the scope-level child_tiers
        asyncio.run(
            _set_types(
                scope="repo_scope",
                child_tiers={"t1": ["Phase", "Phases"]},
                resolved_root=helper.base_path,
            )
        )

        # Ticket should still be readable
        result = asyncio.run(
            _show_ticket(["b.abc"], resolved_root=helper.base_path)
        )
        assert result["status"] == "success"
        assert len(result["tickets"]) == 1
        assert result["tickets"][0]["ticket_id"] == "b.abc"
