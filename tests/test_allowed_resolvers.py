"""Tests for allowed_resolvers field on HiveConfig: parsing, serialization, and colonize_hive validation."""

import pytest

from src.config import (
    BeesConfig,
    HiveConfig,
    ResolverEntry,
    parse_scope_to_bees_config,
    save_resolver_registry,
    serialize_bees_config_to_scope,
)
from src.mcp_hive_ops import colonize_hive_core
from src.repo_context import repo_root_context


TS = "2026-02-01T12:00:00"
_HIVE_BASE = {"path": "/path", "display_name": "Test", "created_at": TS}


def _scope_with_allowed(allowed_resolvers):
    """Build a minimal scope dict with allowed_resolvers on the single hive."""
    hive_data = {**_HIVE_BASE, "allowed_resolvers": allowed_resolvers}
    return {"hives": {"test": hive_data}}


class TestAllowedResolversParsing:
    """Tests for allowed_resolvers field parsing via parse_scope_to_bees_config."""

    def test_absent_key_yields_none(self):
        scope = {"hives": {"test": dict(_HIVE_BASE)}}
        config = parse_scope_to_bees_config(scope)
        assert config.hives["test"].allowed_resolvers is None

    def test_null_value_yields_none(self):
        config = parse_scope_to_bees_config(_scope_with_allowed(None))
        assert config.hives["test"].allowed_resolvers is None

    def test_empty_list_preserved(self):
        config = parse_scope_to_bees_config(_scope_with_allowed([]))
        assert config.hives["test"].allowed_resolvers == []

    def test_valid_string_list_preserved(self):
        config = parse_scope_to_bees_config(_scope_with_allowed(["fast", "slow"]))
        assert config.hives["test"].allowed_resolvers == ["fast", "slow"]

    @pytest.mark.parametrize(
        "bad_value,expected_fragment",
        [
            pytest.param(42, "must be a list or null", id="non_list_int"),
            pytest.param("string", "must be a list or null", id="non_list_string"),
            pytest.param([1, "ok"], "must be a string", id="non_string_element_int"),
            pytest.param(["ok", None], "must be a string", id="non_string_element_none"),
        ],
    )
    def test_invalid_values_raise(self, bad_value, expected_fragment):
        with pytest.raises(ValueError, match=expected_fragment):
            parse_scope_to_bees_config(_scope_with_allowed(bad_value))


class TestAllowedResolversSerialize:
    """Tests for allowed_resolvers round-trip through serialize/parse."""

    def test_none_is_omitted_from_serialization(self):
        config = BeesConfig(hives={"test": HiveConfig(path="/p", display_name="T", created_at=TS)})
        scope = serialize_bees_config_to_scope(config)
        assert "allowed_resolvers" not in scope["hives"]["test"]

    def test_empty_list_is_serialized(self):
        hive = HiveConfig(path="/p", display_name="T", created_at=TS, allowed_resolvers=[])
        scope = serialize_bees_config_to_scope(BeesConfig(hives={"test": hive}))
        assert scope["hives"]["test"]["allowed_resolvers"] == []

    def test_round_trip_preserves_list(self):
        names = ["alpha", "beta"]
        hive = HiveConfig(path="/p", display_name="T", created_at=TS, allowed_resolvers=names)
        scope = serialize_bees_config_to_scope(BeesConfig(hives={"test": hive}))
        restored = parse_scope_to_bees_config(scope)
        assert restored.hives["test"].allowed_resolvers == names


class TestColonizeHiveAllowedResolvers:
    """Tests for allowed_resolvers validation in colonize_hive_core."""

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        """Minimal git repo with a hive directory ready to colonize."""
        (tmp_path / ".git").mkdir()
        hive_path = tmp_path / "myhive"
        hive_path.mkdir()
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            yield tmp_path, hive_path

    async def test_no_allowed_resolvers_succeeds(self, repo):
        _, hive_path = repo
        result = await colonize_hive_core("My Hive", str(hive_path))
        assert result["status"] == "success"
        assert "allowed_resolvers" not in result

    async def test_empty_allowed_resolvers_succeeds(self, repo):
        _, hive_path = repo
        result = await colonize_hive_core("My Hive", str(hive_path), allowed_resolvers=[])
        assert result["status"] == "success"
        assert result["allowed_resolvers"] == []

    async def test_default_name_allowed_without_registry(self, repo):
        """'default' is a built-in sentinel and never needs to be in the registry."""
        _, hive_path = repo
        result = await colonize_hive_core("My Hive", str(hive_path), allowed_resolvers=["default"])
        assert result["status"] == "success"

    async def test_registered_resolver_succeeds(self, repo):
        _, hive_path = repo
        save_resolver_registry({"fast": ResolverEntry(path="/bin/fast")})
        result = await colonize_hive_core("My Hive", str(hive_path), allowed_resolvers=["fast"])
        assert result["status"] == "success"
        assert result["allowed_resolvers"] == ["fast"]

    async def test_registered_plus_default_succeeds(self, repo):
        _, hive_path = repo
        save_resolver_registry({"fast": ResolverEntry(path="/bin/fast")})
        result = await colonize_hive_core(
            "My Hive", str(hive_path), allowed_resolvers=["fast", "default"]
        )
        assert result["status"] == "success"

    async def test_unknown_resolver_returns_error(self, repo):
        _, hive_path = repo
        result = await colonize_hive_core("My Hive", str(hive_path), allowed_resolvers=["no_such"])
        assert result["status"] == "error"
        assert result["error_type"] == "unknown_resolver"
        assert "no_such" in result["validation_details"]["unknown_names"]

    async def test_partially_unknown_resolver_reports_unknowns(self, repo):
        _, hive_path = repo
        save_resolver_registry({"known": ResolverEntry(path="/bin/k")})
        result = await colonize_hive_core(
            "My Hive", str(hive_path), allowed_resolvers=["known", "ghost"]
        )
        assert result["status"] == "error"
        assert result["error_type"] == "unknown_resolver"
        assert result["validation_details"]["unknown_names"] == ["ghost"]
