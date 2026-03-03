"""Tests for _get_types core function, get_types MCP adapter, and get-types CLI."""

import json
from pathlib import Path

import pytest

from src.config import load_global_config, save_global_config
from src.mcp_ticket_ops import _get_types
from tests.test_constants import (
    CHILD_TIERS_GLOBAL,
    CHILD_TIERS_HIVE,
    CHILD_TIERS_SCOPE,
    HIVE_BACKEND,
    HIVE_BUGS,
    HIVE_FEATURES,
)


class TestGetTypesCore:
    """Test _get_types() core function at all three config levels."""

    @pytest.mark.asyncio
    async def test_global_set_others_null(self, isolated_bees_env):
        """Global child_tiers set; scope and all hives null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config()

        config = load_global_config()
        config["scopes"][str(helper.base_path)].pop("child_tiers", None)
        config["child_tiers"] = CHILD_TIERS_GLOBAL
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] == CHILD_TIERS_GLOBAL
        assert result["scope"] is None
        assert result["hives"][HIVE_FEATURES] is None

    @pytest.mark.asyncio
    async def test_scope_set_others_null(self, isolated_bees_env):
        """Scope child_tiers set; global and all hives null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(CHILD_TIERS_SCOPE)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] is None
        assert result["scope"] == CHILD_TIERS_SCOPE
        assert result["hives"][HIVE_FEATURES] is None

    @pytest.mark.asyncio
    async def test_hive_set_others_null(self, isolated_bees_env):
        """One hive's child_tiers set; global and scope null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config()

        config = load_global_config()
        config["scopes"][str(helper.base_path)].pop("child_tiers", None)
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["child_tiers"] = CHILD_TIERS_HIVE
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] is None
        assert result["scope"] is None
        assert result["hives"][HIVE_FEATURES] == CHILD_TIERS_HIVE

    @pytest.mark.asyncio
    async def test_all_three_levels_set(self, isolated_bees_env):
        """All three levels set; returned independently, no merging."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(CHILD_TIERS_SCOPE)

        config = load_global_config()
        config["child_tiers"] = CHILD_TIERS_GLOBAL
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["child_tiers"] = CHILD_TIERS_HIVE
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] == CHILD_TIERS_GLOBAL
        assert result["scope"] == CHILD_TIERS_SCOPE
        assert result["hives"][HIVE_FEATURES] == CHILD_TIERS_HIVE

    @pytest.mark.asyncio
    async def test_nothing_configured(self, isolated_bees_env):
        """Nothing set anywhere; all null, status success."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config()

        config = load_global_config()
        config["scopes"][str(helper.base_path)].pop("child_tiers", None)
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["global"] is None
        assert result["scope"] is None
        assert result["hives"][HIVE_FEATURES] is None

    @pytest.mark.asyncio
    async def test_hive_empty_dict_vs_null(self, isolated_bees_env):
        """One hive has {}, another has null; appear as {} and null."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.create_hive(HIVE_BUGS)
        helper.write_config()

        config = load_global_config()
        config["scopes"][str(helper.base_path)].pop("child_tiers", None)
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["child_tiers"] = {}
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert result["hives"][HIVE_FEATURES] == {}
        assert result["hives"][HIVE_BUGS] is None

    @pytest.mark.asyncio
    async def test_multiple_hives_mixed(self, isolated_bees_env):
        """Multiple hives with mixed configurations."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.create_hive(HIVE_BUGS)
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(CHILD_TIERS_SCOPE)

        config = load_global_config()
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["child_tiers"] = CHILD_TIERS_HIVE
        config["scopes"][str(helper.base_path)]["hives"][HIVE_BACKEND]["child_tiers"] = CHILD_TIERS_SCOPE
        save_global_config(config)

        result = await _get_types(resolved_root=helper.base_path)

        assert result["status"] == "success"
        assert HIVE_FEATURES in result["hives"]
        assert HIVE_BUGS in result["hives"]
        assert HIVE_BACKEND in result["hives"]
        assert result["hives"][HIVE_FEATURES] == CHILD_TIERS_HIVE
        assert result["hives"][HIVE_BACKEND] == CHILD_TIERS_SCOPE
        assert result["hives"][HIVE_BUGS] is None

    @pytest.mark.asyncio
    async def test_no_matching_scope(self, isolated_bees_env):
        """No scope matches; returns no_matching_scope error."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(CHILD_TIERS_SCOPE)

        result = await _get_types(resolved_root=Path("/tmp/nonexistent-repo-xyz"))

        assert result["status"] == "error"
        assert result["error_type"] == "no_matching_scope"


class TestGetTypesMCPAdapter:
    """Test get_types MCP tool adapter."""

    @pytest.mark.asyncio
    async def test_adapter_no_spurious_hive_name_kwarg(self, isolated_bees_env):
        """Regression b.Qrh: adapter must not forward hive_name to _get_types.

        Before fix, get_types had a hive_name param and forwarded it to
        _get_types which does not accept it, raising TypeError.
        """
        from src.mcp_server import get_types

        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config()

        result = await get_types(ctx=None, repo_root=str(helper.base_path))
        assert result["status"] == "success"
        assert "hives" in result

    @pytest.mark.asyncio
    async def test_adapter_returns_all_keys(self, isolated_bees_env):
        """Call get_types(ctx=None, repo_root=...), check all four keys present."""
        from src.mcp_server import get_types

        helper = isolated_bees_env
        helper.create_hive(HIVE_FEATURES)
        helper.write_config(CHILD_TIERS_SCOPE)

        config = load_global_config()
        config["child_tiers"] = CHILD_TIERS_GLOBAL
        config["scopes"][str(helper.base_path)]["hives"][HIVE_FEATURES]["child_tiers"] = CHILD_TIERS_HIVE
        save_global_config(config)

        result = await get_types(ctx=None, repo_root=str(helper.base_path))

        assert result["status"] == "success"
        assert result["global"] == CHILD_TIERS_GLOBAL
        assert result["scope"] == CHILD_TIERS_SCOPE
        assert HIVE_FEATURES in result["hives"]
        assert result["hives"][HIVE_FEATURES] == CHILD_TIERS_HIVE


class TestGetTypesCLI:
    """CLI integration tests for `bees get-types`."""

    def test_cli_get_types(self, cli_runner, isolated_bees_env):
        """get-types exits 0 and returns valid JSON with all four keys."""
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(CHILD_TIERS_SCOPE)

        stdout, exit_code = cli_runner(["get-types"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert "global" in result
        assert "scope" in result
        assert "hives" in result
