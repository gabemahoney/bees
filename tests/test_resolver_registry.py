"""Unit tests for resolver registry dataclass and config parsing."""

import json

import pytest

from src.config import ResolverEntry, _parse_resolvers_data, load_resolver_registry, save_resolver_registry


class TestParseResolversData:
    """Tests for _parse_resolvers_data validation."""

    def test_valid_full_entry(self):
        data = {
            "my_resolver": {
                "path": "/usr/local/bin/resolver",
                "timeout": 30,
                "convention": "pep8",
            }
        }
        result = _parse_resolvers_data(data)
        assert result["my_resolver"] == ResolverEntry(
            path="/usr/local/bin/resolver", timeout=30, convention="pep8"
        )

    @pytest.mark.parametrize(
        "entry_data,expected_error",
        [
            pytest.param(
                {"r": {}},
                "missing required 'path'",
                id="missing_path",
            ),
            pytest.param(
                {"r": {"path": 42}},
                "path must be a string",
                id="non_string_path",
            ),
            pytest.param(
                {"r": {"path": "/bin/r", "timeout": "30"}},
                "timeout must be a number",
                id="bad_timeout_type",
            ),
            pytest.param(
                {"r": {"path": "/bin/r", "timeout": -5}},
                "timeout must be positive",
                id="negative_timeout",
            ),
            pytest.param(
                {"r": {"path": "/bin/r", "convention": 123}},
                "convention must be a string",
                id="non_string_convention",
            ),
        ],
    )
    def test_invalid_entries_raise(self, entry_data, expected_error):
        with pytest.raises(ValueError, match=expected_error):
            _parse_resolvers_data(entry_data)


class TestLoadResolverRegistry:
    """Tests for load_resolver_registry."""

    def test_absent_resolvers_key_returns_empty(self, mock_global_bees_dir):
        (mock_global_bees_dir / "config.json").write_text(
            json.dumps({"scopes": {}, "schema_version": "2.0"})
        )
        assert load_resolver_registry() == {}

    def test_no_config_file_returns_empty(self):
        # mock_global_bees_dir (autouse) redirects config; no file written → empty
        assert load_resolver_registry() == {}

    def test_populated_resolvers_returns_entries(self, mock_global_bees_dir):
        config = {
            "scopes": {},
            "schema_version": "2.0",
            "resolvers": {
                "fast": {"path": "/bin/fast", "timeout": 10},
                "slow": {"path": "/bin/slow", "convention": "strict"},
            },
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config))
        result = load_resolver_registry()
        assert len(result) == 2
        assert result["fast"] == ResolverEntry(path="/bin/fast", timeout=10)
        assert result["slow"] == ResolverEntry(path="/bin/slow", convention="strict")


class TestSaveLoadRoundTrip:
    """Tests for save_resolver_registry + load_resolver_registry round-trip."""

    def test_round_trip_full_entries(self):
        registry = {
            "alpha": ResolverEntry(path="/bin/alpha", timeout=5.0, convention="pep8"),
            "beta": ResolverEntry(path="/bin/beta"),
        }
        save_resolver_registry(registry)
        assert load_resolver_registry() == registry

    def test_round_trip_empty_registry(self):
        save_resolver_registry({})
        assert load_resolver_registry() == {}

    def test_round_trip_required_fields_only(self):
        registry = {"minimal": ResolverEntry(path="/bin/minimal")}
        save_resolver_registry(registry)
        entry = load_resolver_registry()["minimal"]
        assert entry.path == "/bin/minimal"
        assert entry.timeout is None
        assert entry.convention is None

    def test_save_preserves_existing_config_keys(self, mock_global_bees_dir):
        original = {
            "scopes": {},
            "schema_version": "2.0",
            "mermaid_charts": True,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(original))
        save_resolver_registry({"r": ResolverEntry(path="/bin/r")})
        saved = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert saved["mermaid_charts"] is True
        assert "resolvers" in saved
