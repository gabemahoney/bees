"""Tests for _get_status_values core function and get_status_values MCP adapter."""

import json

import pytest

from src.config import load_global_config, save_global_config
from src.mcp_ticket_ops import _get_status_values
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_BUGS,
    HIVE_FEATURES,
    SCOPE_TIER_DEFAULT,
    STATUS_VALUES_GLOBAL,
    STATUS_VALUES_HIVE,
    STATUS_VALUES_SCOPE,
)


class TestGetStatusValuesCore:
    """Test _get_status_values() core function at all three config levels."""

    @pytest.mark.asyncio
    async def test_global_set_scope_and_hives_not_set(self, isolated_bees_env):
        """Global set, scope/hives not set -> global=[...], scope=null, hive entries null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Set global-level status_values
        config = load_global_config()
        config["status_values"] = STATUS_VALUES_GLOBAL
        save_global_config(config)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] == STATUS_VALUES_GLOBAL
        assert result["scope"] is None
        assert result["hives"][HIVE_FEATURES] is None

    @pytest.mark.asyncio
    async def test_scope_set_global_not_set(self, isolated_bees_env):
        """Scope set, global not set -> scope=[...], global=null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT, status_values=STATUS_VALUES_SCOPE)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] is None
        assert result["scope"] == STATUS_VALUES_SCOPE

    @pytest.mark.asyncio
    async def test_hive_level_set_for_one_hive_only(self, isolated_bees_env):
        """Hive-level set for one hive only -> that hive returns list, others null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.create_hive(HIVE_BUGS)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Set hive-level status_values for features only
        config = load_global_config()
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["status_values"] = STATUS_VALUES_HIVE
        save_global_config(config)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["hives"][HIVE_FEATURES] == STATUS_VALUES_HIVE
        assert result["hives"][HIVE_BUGS] is None

    @pytest.mark.asyncio
    async def test_all_three_levels_set(self, isolated_bees_env):
        """All 3 levels set simultaneously -> all 3 returned independently (not resolved/merged)."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT, status_values=STATUS_VALUES_SCOPE)

        # Set global-level
        config = load_global_config()
        config["status_values"] = STATUS_VALUES_GLOBAL
        # Set hive-level
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["status_values"] = STATUS_VALUES_HIVE
        save_global_config(config)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] == STATUS_VALUES_GLOBAL
        assert result["scope"] == STATUS_VALUES_SCOPE
        assert result["hives"][HIVE_FEATURES] == STATUS_VALUES_HIVE

    @pytest.mark.asyncio
    async def test_nothing_configured(self, isolated_bees_env):
        """Nothing configured anywhere -> all null, all-null hives dict."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] is None
        assert result["scope"] is None
        assert result["hives"][HIVE_FEATURES] is None

    @pytest.mark.asyncio
    async def test_multiple_hives_mixed_config(self, isolated_bees_env):
        """Multiple hives with mixed config -> all hives appear in response."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.create_hive(HIVE_BUGS)
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(SCOPE_TIER_DEFAULT)

        # Set hive-level for features and backend, leave bugs unset
        config = load_global_config()
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["status_values"] = STATUS_VALUES_HIVE
        config["scopes"][str(helper.base_path)]["hives"][HIVE_BACKEND]["status_values"] = STATUS_VALUES_SCOPE
        save_global_config(config)

        result = await _get_status_values(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert HIVE_FEATURES in result["hives"]
        assert HIVE_BUGS in result["hives"]
        assert HIVE_BACKEND in result["hives"]
        assert result["hives"][HIVE_FEATURES] == STATUS_VALUES_HIVE
        assert result["hives"][HIVE_BACKEND] == STATUS_VALUES_SCOPE
        assert result["hives"][HIVE_BUGS] is None

    @pytest.mark.asyncio
    async def test_no_matching_scope(self, isolated_bees_env, tmp_path):
        """No matching scope (fake resolved_root path) -> error_type: 'no_matching_scope'."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT)

        fake_root = tmp_path / "no_match_repo"
        fake_root.mkdir()

        result = await _get_status_values(resolved_root=fake_root)

        assert result["status"] == "error"
        assert result["error_type"] == "no_matching_scope"


class TestGetStatusValuesMCPAdapter:
    """Test get_status_values MCP tool adapter."""

    @pytest.mark.asyncio
    async def test_mcp_adapter_returns_all_keys(self, isolated_bees_env):
        """MCP-registered get_status_values returns status=success with global, scope, hives keys."""
        from src.mcp_server import get_status_values

        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(SCOPE_TIER_DEFAULT, status_values=STATUS_VALUES_SCOPE)

        # Set global-level
        config = load_global_config()
        config["status_values"] = STATUS_VALUES_GLOBAL
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["status_values"] = STATUS_VALUES_HIVE
        save_global_config(config)

        result = await get_status_values(ctx=None, repo_root=str(helper.base_path))

        assert result["status"] == "success"
        assert result["global"] == STATUS_VALUES_GLOBAL
        assert result["scope"] == STATUS_VALUES_SCOPE
        assert HIVE_FEATURES in result["hives"]
        assert result["hives"][HIVE_FEATURES] == STATUS_VALUES_HIVE


class TestGetStatusValuesCLI:
    """CLI integration tests for `bees get-status-values`."""

    def test_get_status_values_happy_path(self, cli_runner, isolated_bees_env):
        """get-status-values exits 0 and returns JSON with global, scope, hives keys."""
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(SCOPE_TIER_DEFAULT)

        stdout, exit_code = cli_runner(["get-status-values"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert "global" in result
        assert "scope" in result
        assert "hives" in result
