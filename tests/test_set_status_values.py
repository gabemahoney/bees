"""
Unit tests for _set_status_values in src/mcp_ticket_ops.py.

PURPOSE:
Tests the _set_status_values function which sets or unsets status_values configuration
at three scope levels: global, repo_scope, and hive.

SCOPE - Tests that belong here:
- Parameter validation (invalid scope, missing hive_name, conflicting params, etc.)
- Set operation for each scope level (global, repo_scope, hive)
- Unset operation for each scope level
- Unset idempotency (unsetting when key already absent)
- Normalization: empty list treated as unset, duplicates deduplicated
- Existing tickets unaffected by set_status_values

SCOPE - Tests that DON'T belong here:
- CLI round-trip tests → test_cli_commands.py
- MCP server wrapper → test_mcp_server.py
"""

import asyncio

import pytest

from src.config import load_global_config
from src.mcp_ticket_ops import _set_status_values, _show_ticket
from tests.test_constants import (
    HIVE_BUGS,
    HIVE_FEATURES,
    SCOPE_TIER_DEFAULT,
    STATUS_VALUES_DUPES_EXPECTED,
    STATUS_VALUES_DUPES_INPUT,
    STATUS_VALUES_GLOBAL,
    STATUS_VALUES_HIVE,
    STATUS_VALUES_SCOPE,
)


# ===========================================================================
# Error tests
# ===========================================================================


class TestSetStatusValuesErrors:
    @pytest.mark.parametrize("kwargs,expected_error_type", [
        ({"scope": "invalid", "status_values": STATUS_VALUES_SCOPE}, "invalid_scope"),
        ({"scope": "hive", "status_values": STATUS_VALUES_SCOPE}, "missing_hive_name"),
        ({"scope": "global", "status_values": None, "unset": False}, "missing_status_values"),
        ({"scope": "global", "status_values": STATUS_VALUES_SCOPE, "unset": True}, "conflicting_params"),
        ({"scope": "global", "status_values": ["valid", ""]}, "invalid_status_values"),
    ], ids=["invalid_scope", "missing_hive_name", "missing_status_values", "conflicting_params", "invalid_status_values"])
    def test_parameter_validation_errors(self, isolated_bees_env, kwargs, expected_error_type):
        result = asyncio.run(_set_status_values(**kwargs))
        assert result["status"] == "error"
        assert result["error_type"] == expected_error_type

    def test_hive_not_found(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_status_values(
                scope="hive",
                hive_name="nonexistent",
                status_values=STATUS_VALUES_SCOPE,
                resolved_root=helper.base_path,
            )
        )
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    def test_no_matching_scope(self, isolated_bees_env, tmp_path):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        fake_root = tmp_path / "no_match_repo"
        fake_root.mkdir()

        result = asyncio.run(
            _set_status_values(
                scope="repo_scope",
                status_values=STATUS_VALUES_SCOPE,
                resolved_root=fake_root,
            )
        )
        assert result["status"] == "error"
        assert result["error_type"] == "no_matching_scope"


# ===========================================================================
# Set operations (3 scopes)
# ===========================================================================


class TestSetStatusValuesSet:
    def test_set_global(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_status_values(scope="global", status_values=STATUS_VALUES_GLOBAL)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"
        assert result["status_values"] == STATUS_VALUES_GLOBAL

        config = load_global_config()
        assert config["status_values"] == STATUS_VALUES_GLOBAL

    def test_set_repo_scope(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_status_values(
                scope="repo_scope",
                status_values=STATUS_VALUES_SCOPE,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"
        assert result["status_values"] == STATUS_VALUES_SCOPE

        config = load_global_config()
        scope_block = config["scopes"][str(helper.base_path)]
        assert scope_block["status_values"] == STATUS_VALUES_SCOPE

    def test_set_hive(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_status_values(
                scope="hive",
                hive_name=HIVE_FEATURES,
                status_values=STATUS_VALUES_HIVE,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "hive"
        assert result["hive_name"] == HIVE_FEATURES
        assert result["status_values"] == STATUS_VALUES_HIVE

        config = load_global_config()
        hive_entry = config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]
        assert hive_entry["status_values"] == STATUS_VALUES_HIVE


# ===========================================================================
# Unset operations (3 scopes)
# ===========================================================================


class TestSetStatusValuesUnset:
    def test_unset_global(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # First set global status_values
        config = load_global_config()
        config["status_values"] = STATUS_VALUES_GLOBAL
        from src.config import save_global_config
        save_global_config(config)

        result = asyncio.run(
            _set_status_values(scope="global", unset=True)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"

        config = load_global_config()
        assert "status_values" not in config

    def test_unset_repo_scope(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT, status_values=STATUS_VALUES_SCOPE)

        result = asyncio.run(
            _set_status_values(scope="repo_scope", unset=True, resolved_root=helper.base_path)
        )

        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"

        config = load_global_config()
        scope_block = config["scopes"][str(helper.base_path)]
        assert "status_values" not in scope_block

    def test_unset_hive(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # First set hive-level status_values
        asyncio.run(
            _set_status_values(
                scope="hive",
                hive_name=HIVE_FEATURES,
                status_values=STATUS_VALUES_HIVE,
                resolved_root=helper.base_path,
            )
        )

        result = asyncio.run(
            _set_status_values(
                scope="hive",
                hive_name=HIVE_FEATURES,
                unset=True,
                resolved_root=helper.base_path,
            )
        )

        assert result["status"] == "success"
        assert result["scope"] == "hive"
        assert result["hive_name"] == HIVE_FEATURES

        config = load_global_config()
        hive_entry = config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]
        # Explicit null is stored so this hive overrides scope/global inheritance
        assert "status_values" in hive_entry
        assert hive_entry["status_values"] is None


# ===========================================================================
# Unset idempotency
# ===========================================================================


class TestSetStatusValuesIdempotency:
    def test_unset_global_already_absent(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # status_values not set — unset should still succeed
        result = asyncio.run(
            _set_status_values(scope="global", unset=True)
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"


# ===========================================================================
# Normalization
# ===========================================================================


class TestSetStatusValuesNormalization:
    def test_empty_list_treated_as_unset(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # First set a value
        asyncio.run(
            _set_status_values(scope="global", status_values=STATUS_VALUES_GLOBAL)
        )

        # Now set empty list — should behave like unset
        result = asyncio.run(
            _set_status_values(scope="global", status_values=[])
        )

        assert result["status"] == "success"
        assert result["scope"] == "global"

        config = load_global_config()
        assert "status_values" not in config

    def test_duplicate_values_deduplicated(self, isolated_bees_env):
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = asyncio.run(
            _set_status_values(scope="global", status_values=STATUS_VALUES_DUPES_INPUT)
        )

        assert result["status"] == "success"
        assert result["status_values"] == STATUS_VALUES_DUPES_EXPECTED

        config = load_global_config()
        assert config["status_values"] == STATUS_VALUES_DUPES_EXPECTED


# ===========================================================================
# Existing tickets unaffected
# ===========================================================================


class TestSetStatusValuesExistingTickets:
    def test_existing_ticket_readable_after_change(self, isolated_bees_env):
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BUGS)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Create a ticket before changing status values
        helper.create_ticket(hive_dir, "b.abc", "bee", "Test Bee")

        # Change scope-level status_values
        asyncio.run(
            _set_status_values(
                scope="repo_scope",
                status_values=STATUS_VALUES_SCOPE,
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
