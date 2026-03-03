"""Unit tests for configuration system (loading, parsing, validation, persistence)."""

import json
import os
from pathlib import Path

import pytest

from src.config import (
    BeesConfig,
    ChildTierConfig,
    HiveConfig,
    find_matching_scope,
    get_scoped_config,
    load_bees_config,
    load_global_config,
    match_scope_pattern,
    parse_scope_to_bees_config,
    resolve_child_tiers_for_hive,
    save_bees_config,
    save_global_config,
    serialize_bees_config_to_scope,
    set_config_path,
    set_test_config_override,
    validate_child_tiers,
    validate_unique_hive_name,
)
from src.id_utils import normalize_hive_name
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config

TS = "2026-02-01T12:00:00"


def _make_hive(path="tickets/backend/", display_name="Backend", created_at=TS):
    return HiveConfig(path=path, display_name=display_name, created_at=created_at)


@pytest.fixture(autouse=True)
def setup_repo_context(tmp_path):
    """Set repo_root context to tmp_path for all tests."""
    with repo_root_context(tmp_path):
        yield


class TestBeesConfigDataclasses:
    """Test BeesConfig and HiveConfig dataclass initialization."""

    def test_hive_config_initialization(self):
        """Test HiveConfig stores all fields correctly."""
        hive = HiveConfig(path="/path/to/hive", display_name="My Hive", created_at="2026-02-01T13:45:30.123456")
        assert hive.path == "/path/to/hive"
        assert hive.display_name == "My Hive"
        assert hive.created_at == "2026-02-01T13:45:30.123456"

    @pytest.mark.parametrize(
        "child_tiers,expected",
        [
            pytest.param(None, None, id="default_none"),
            pytest.param({}, {}, id="bees_only_empty_dict"),
            pytest.param(
                {"t1": ChildTierConfig("Task", "Tasks"), "t2": ChildTierConfig("Subtask", "Subtasks")},
                {"t1": ChildTierConfig("Task", "Tasks"), "t2": ChildTierConfig("Subtask", "Subtasks")},
                id="populated_tiers",
            ),
        ],
    )
    def test_hive_config_with_child_tiers(self, child_tiers, expected):
        """Test HiveConfig initialization with various child_tiers values."""
        hive = HiveConfig(
            path="/path/to/hive",
            display_name="My Hive",
            created_at=TS,
            child_tiers=child_tiers,
        )
        assert hive.child_tiers == expected

    @pytest.mark.parametrize(
        "kwargs,expected_hives,expected_version",
        [
            pytest.param({}, {}, "2.0", id="defaults"),
            pytest.param(
                {
                    "hives": {"test": HiveConfig(path="/path", display_name="Test", created_at=TS)},
                    "schema_version": "2.0",
                },
                None, "2.0",  # None = skip hives check
                id="custom_values",
            ),
        ],
    )
    def test_bees_config_initialization(self, kwargs, expected_hives, expected_version):
        """Test BeesConfig with default and custom values."""
        config = BeesConfig(**kwargs)
        if expected_hives is not None:
            assert config.hives == expected_hives
        assert config.schema_version == expected_version


# ============================================================================
# SCOPE MATCHING TESTS
# ============================================================================


class TestMatchScopePattern:
    """Test match_scope_pattern for glob-style directory matching."""

    @pytest.mark.parametrize(
        "repo_root,pattern,expected",
        [
            # Exact match
            pytest.param("/Users/dev/projects/bees", "/Users/dev/projects/bees", True, id="exact_match"),
            pytest.param("/Users/dev/projects/bees", "/Users/dev/projects/other", False, id="exact_no_match"),
            # ** recursive match (also matches base dir)
            pytest.param("/Users/dev/projects/bees", "/Users/dev/projects/bees/**", True, id="doublestar_base"),
            pytest.param("/Users/dev/projects/bees/wt1", "/Users/dev/projects/bees/**", True, id="doublestar_child"),
            pytest.param("/Users/dev/projects/bees/a/b/c", "/Users/dev/projects/bees/**", True, id="doublestar_deep"),
            pytest.param("/Users/dev/projects/other", "/Users/dev/projects/bees/**", False, id="doublestar_no_match"),
            pytest.param("/Users/dev/projects/bees_other", "/Users/dev/projects/bees/**", False, id="doublestar_no_suffix"),
            # * single segment match
            pytest.param("/Users/dev/projects/bees", "/Users/dev/projects/bees*", True, id="star_exact"),
            pytest.param("/Users/dev/projects/bees_other", "/Users/dev/projects/bees*", True, id="star_suffix"),
            pytest.param("/Users/dev/projects/bees123", "/Users/dev/projects/bees*", True, id="star_digits"),
            pytest.param("/Users/dev/projects/bees/wt1", "/Users/dev/projects/bees*", False, id="star_no_recurse"),
            # * in middle
            pytest.param("/Users/dev/projects/bees", "/Users/dev/*/bees", True, id="star_middle"),
            pytest.param("/Users/dev/other/bees", "/Users/dev/*/bees", True, id="star_middle_other"),
            pytest.param("/Users/dev/a/b/bees", "/Users/dev/*/bees", False, id="star_middle_no_recurse"),
        ],
    )
    def test_match_scope_pattern(self, repo_root, pattern, expected):
        from src.config import _SCOPE_PATTERN_CACHE
        _SCOPE_PATTERN_CACHE.clear()
        assert match_scope_pattern(Path(repo_root), pattern) == expected

    def test_concurrent_cache_writes(self):
        """Concurrent threads can safely read/write _SCOPE_PATTERN_CACHE.

        NOTE: This is a functional-correctness-under-concurrency test, not a
        lock-presence verification. CPython's GIL makes dict writes atomic, so
        removing the lock would not cause failures here. The _CACHE_LOCK exists
        for free-threaded Python (PEP 703 / 3.13t+) where dict ops are no
        longer implicitly serialized.
        """
        import threading

        from src.config import _SCOPE_PATTERN_CACHE

        _SCOPE_PATTERN_CACHE.clear()

        num_threads = 30
        patterns = [f"/Users/dev/proj_{i}/**" for i in range(num_threads)]
        repo_root = Path("/Users/dev/proj_0/sub")
        barrier = threading.Barrier(num_threads)
        results: list[bool | Exception] = [None] * num_threads  # type: ignore[list-item]

        def worker(idx: int) -> None:
            try:
                barrier.wait()
                results[idx] = match_scope_pattern(repo_root, patterns[idx])
            except Exception as exc:
                results[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Thread 0 should match (proj_0/** vs proj_0/sub), rest should not
        assert results[0] is True
        for i in range(1, num_threads):
            assert results[i] is False, f"Thread {i} returned {results[i]}"

    def test_match_scope_pattern_thread_safety(self):
        """Threads racing to compile the same uncached pattern all get correct results.

        NOTE: This is a functional-correctness-under-concurrency test, not a
        lock-presence verification. CPython's GIL makes dict writes atomic, so
        removing the lock would not cause failures here. The _CACHE_LOCK exists
        for free-threaded Python (PEP 703 / 3.13t+) where dict ops are no
        longer implicitly serialized.
        """
        import threading

        from src.config import _SCOPE_PATTERN_CACHE

        _SCOPE_PATTERN_CACHE.clear()

        num_threads = 30
        pattern = "/Users/dev/regression/**"
        repo_root = Path("/Users/dev/regression/child")
        barrier = threading.Barrier(num_threads)
        results: list[bool | Exception] = [None] * num_threads  # type: ignore[list-item]

        def worker(idx: int) -> None:
            try:
                barrier.wait()
                results[idx] = match_scope_pattern(repo_root, pattern)
            except Exception as exc:
                results[idx] = exc

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i, result in enumerate(results):
            assert result is True, f"Thread {i} returned {result!r}, expected True"


class TestFindMatchingScope:
    """Test find_matching_scope for first-match-wins resolution."""

    def test_first_match_wins(self):
        global_config = {
            "scopes": {
                "/Users/dev/projects/bees": {"hives": {"specific": {}}},
                "/Users/dev/projects/**": {"hives": {"general": {}}},
            }
        }
        result = find_matching_scope(Path("/Users/dev/projects/bees"), global_config)
        assert result == "/Users/dev/projects/bees"

    def test_falls_through_to_wildcard(self):
        global_config = {
            "scopes": {
                "/Users/dev/projects/other": {"hives": {}},
                "/Users/dev/projects/**": {"hives": {"general": {}}},
            }
        }
        result = find_matching_scope(Path("/Users/dev/projects/bees"), global_config)
        assert result == "/Users/dev/projects/**"

    def test_no_match_returns_none(self):
        global_config = {
            "scopes": {
                "/Users/dev/projects/other": {"hives": {}},
            }
        }
        assert find_matching_scope(Path("/Users/dev/projects/bees"), global_config) is None

    def test_empty_scopes(self):
        assert find_matching_scope(Path("/any/path"), {"scopes": {}}) is None

    def test_missing_scopes_key(self):
        assert find_matching_scope(Path("/any/path"), {}) is None


# ============================================================================
# GLOBAL CONFIG TESTS
# ============================================================================


class TestLoadGlobalConfig:
    """Test load_global_config for reading ~/.bees/config.json."""

    def test_missing_file_returns_default(self, mock_global_bees_dir):
        config = load_global_config()
        assert config == {"scopes": {}, "schema_version": "2.0"}

    def test_valid_config(self, mock_global_bees_dir):
        data = {"scopes": {"/path": {"hives": {}}}, "schema_version": "2.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(data))
        config = load_global_config()
        assert config["scopes"]["/path"]["hives"] == {}

    def test_malformed_json_returns_default(self, mock_global_bees_dir, caplog):
        import logging
        (mock_global_bees_dir / "config.json").write_text("{invalid json")
        with caplog.at_level(logging.WARNING):
            config = load_global_config()
        assert config == {"scopes": {}, "schema_version": "2.0"}
        assert "Malformed JSON" in caplog.text

    def test_adds_missing_scopes_key(self, mock_global_bees_dir):
        (mock_global_bees_dir / "config.json").write_text(json.dumps({"schema_version": "2.0"}))
        config = load_global_config()
        assert "scopes" in config
        assert config["scopes"] == {}

    def test_cache_returns_same_object(self, mock_global_bees_dir):
        """Consecutive calls return the same cached object when file is unchanged."""
        data = {"scopes": {"/cached": {"hives": {}}}, "schema_version": "2.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(data))
        result1 = load_global_config()
        result2 = load_global_config()
        assert result1 is result2

    def test_cache_invalidated_on_mtime_change(self, mock_global_bees_dir):
        """Cache is invalidated when the file's mtime changes."""
        config_path = mock_global_bees_dir / "config.json"
        v1 = {"scopes": {"/v1": {"hives": {}}}, "schema_version": "2.0"}
        config_path.write_text(json.dumps(v1))
        result1 = load_global_config()
        assert "/v1" in result1["scopes"]

        # Write v2 and bump mtime by 1 second
        v2 = {"scopes": {"/v2": {"hives": {}}}, "schema_version": "2.0"}
        config_path.write_text(json.dumps(v2))
        st = config_path.stat()
        os.utime(config_path, (st.st_atime, st.st_mtime + 1))

        result2 = load_global_config()
        assert result2 is not result1
        assert "/v2" in result2["scopes"]

    @pytest.mark.parametrize(
        "config_key",
        [
            pytest.param("delete_with_dependencies", id="delete_with_dependencies"),
            pytest.param("auto_fix_dangling_refs", id="auto_fix_dangling_refs"),
        ],
    )
    @pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
    def test_boolean_global_flag_valid(self, config_key, value, mock_global_bees_dir):
        """load_global_config() succeeds when a boolean global flag is True or False."""
        data = {"scopes": {}, "schema_version": "2.0", config_key: value}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(data))
        loaded = load_global_config()
        assert loaded.get(config_key) == value

    @pytest.mark.parametrize(
        "config_key, invalid_value, error_match",
        [
            pytest.param("delete_with_dependencies", "true", "Global delete_with_dependencies must be a boolean", id="dwd-string_true"),
            pytest.param("delete_with_dependencies", "false", "Global delete_with_dependencies must be a boolean", id="dwd-string_false"),
            pytest.param("delete_with_dependencies", 1, "Global delete_with_dependencies must be a boolean", id="dwd-int_one"),
            pytest.param("delete_with_dependencies", 0, "Global delete_with_dependencies must be a boolean", id="dwd-int_zero"),
            pytest.param("auto_fix_dangling_refs", "true", "Global auto_fix_dangling_refs must be a boolean", id="afdr-string_true"),
            pytest.param("auto_fix_dangling_refs", 1, "Global auto_fix_dangling_refs must be a boolean", id="afdr-int_one"),
        ],
    )
    def test_boolean_global_flag_non_boolean_raises(self, config_key, invalid_value, error_match, mock_global_bees_dir):
        """load_global_config() raises ValueError when a boolean global flag is not a boolean."""
        data = {"scopes": {}, "schema_version": "2.0", config_key: invalid_value}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(data))
        with pytest.raises(ValueError, match=error_match):
            load_global_config()

    def test_auto_fix_dangling_refs_absent_succeeds(self, mock_global_bees_dir):
        """load_global_config() succeeds when auto_fix_dangling_refs is absent."""
        data = {"scopes": {}, "schema_version": "2.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(data))
        loaded = load_global_config()
        assert "auto_fix_dangling_refs" not in loaded


class TestSaveGlobalConfig:
    """Test save_global_config for atomic writes."""

    def test_creates_directory_and_file(self, mock_global_bees_dir):
        save_global_config({"scopes": {}, "schema_version": "2.0"})
        assert (mock_global_bees_dir / "config.json").exists()

    def test_writes_valid_json(self, mock_global_bees_dir):
        data = {"scopes": {"/path": {"hives": {"backend": {}}}}, "schema_version": "2.0"}
        save_global_config(data)
        loaded = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert loaded == data

    def test_formatted_output(self, mock_global_bees_dir):
        save_global_config({"scopes": {}, "schema_version": "2.0"})
        content = (mock_global_bees_dir / "config.json").read_text()
        assert "  " in content
        assert content.endswith("\n")

    def test_atomic_write_no_partial_on_failure(self, mock_global_bees_dir):
        from unittest.mock import patch

        # Write initial config
        save_global_config({"scopes": {"/path": {"hives": {}}}, "schema_version": "2.0"})
        original = (mock_global_bees_dir / "config.json").read_text()

        with patch("os.replace", side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError):
                save_global_config({"scopes": {"CORRUPTED": {}}, "schema_version": "2.0"})

        assert (mock_global_bees_dir / "config.json").read_text() == original


class TestParseScopeToBeesConfig:
    """Test parse_scope_to_bees_config for scope dict → BeesConfig conversion."""

    def test_full_scope(self):
        scope = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
        }
        config = parse_scope_to_bees_config(scope)
        assert "backend" in config.hives
        assert config.hives["backend"].path == "/path"
        assert "t1" in config.child_tiers
        assert config.child_tiers["t1"].singular == "Task"

    def test_empty_scope(self):
        config = parse_scope_to_bees_config({})
        assert config.hives == {}
        assert config.child_tiers is None

    def test_missing_child_tiers_returns_none(self):
        scope = {"hives": {}}
        config = parse_scope_to_bees_config(scope)
        assert config.child_tiers is None

    def test_empty_child_tiers_returns_empty_dict(self):
        scope = {"hives": {}, "child_tiers": {}}
        config = parse_scope_to_bees_config(scope)
        assert config.child_tiers == {}

    @pytest.mark.parametrize(
        "hive_child_tiers,expected_child_tiers",
        [
            pytest.param(None, None, id="hive_child_tiers_absent"),
            pytest.param({}, {}, id="hive_child_tiers_empty"),
            pytest.param(
                {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                {"t1": ChildTierConfig("Task", "Tasks"), "t2": ChildTierConfig("Subtask", "Subtasks")},
                id="hive_child_tiers_populated",
            ),
        ],
    )
    def test_hive_level_child_tiers_parsing(self, hive_child_tiers, expected_child_tiers):
        """Test _parse_hives_data correctly parses hive-level child_tiers."""
        hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS}
        if hive_child_tiers is not None:
            hive_data["child_tiers"] = hive_child_tiers
        scope = {"hives": {"backend": hive_data}}
        config = parse_scope_to_bees_config(scope)
        assert config.hives["backend"].child_tiers == expected_child_tiers

    def test_missing_scope_child_tiers_no_warning(self, caplog):
        """Test parse_scope_to_bees_config doesn't log warning when child_tiers is missing."""
        import logging
        scope = {"hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}}}
        with caplog.at_level(logging.WARNING):
            config = parse_scope_to_bees_config(scope)
        assert config.child_tiers is None
        # Verify no warnings about missing child_tiers
        assert not any("child_tiers" in record.message.lower() for record in caplog.records)


class TestSerializeBeesConfigToScope:
    """Test serialize_bees_config_to_scope for BeesConfig → scope dict conversion."""

    def test_round_trip(self):
        config = BeesConfig(
            hives={"backend": HiveConfig(path="/path", display_name="Backend", created_at=TS)},
            child_tiers={"t1": ChildTierConfig("Task", "Tasks")},
        )
        scope = serialize_bees_config_to_scope(config)
        restored = parse_scope_to_bees_config(scope)
        assert restored.hives["backend"].path == "/path"
        assert restored.child_tiers["t1"].singular == "Task"

    def test_empty_config(self):
        scope = serialize_bees_config_to_scope(BeesConfig())
        assert scope["hives"] == {}
        assert "child_tiers" not in scope  # None = omitted from output

    def test_empty_child_tiers_serialized(self):
        config = BeesConfig(child_tiers={})
        scope = serialize_bees_config_to_scope(config)
        assert scope["child_tiers"] == {}  # {} = bees-only, must be preserved

    def test_none_friendly_names(self):
        config = BeesConfig(child_tiers={"t1": ChildTierConfig(None, None)})
        scope = serialize_bees_config_to_scope(config)
        assert scope["child_tiers"]["t1"] == []

    @pytest.mark.parametrize(
        "hive_child_tiers,expected_serialized",
        [
            pytest.param(None, None, id="hive_child_tiers_none_omitted"),
            pytest.param({}, {}, id="hive_child_tiers_empty_preserved"),
            pytest.param(
                {"t1": ChildTierConfig("Task", "Tasks")},
                {"t1": ["Task", "Tasks"]},
                id="hive_child_tiers_populated",
            ),
        ],
    )
    def test_hive_level_child_tiers_serialization(self, hive_child_tiers, expected_serialized):
        """Test serialize_bees_config_to_scope handles hive-level child_tiers correctly."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    child_tiers=hive_child_tiers,
                )
            }
        )
        scope = serialize_bees_config_to_scope(config)
        if expected_serialized is None:
            assert "child_tiers" not in scope["hives"]["backend"]
        else:
            assert scope["hives"]["backend"]["child_tiers"] == expected_serialized

    @pytest.mark.parametrize(
        "scope_child_tiers,hive_child_tiers",
        [
            pytest.param(None, None, id="both_none"),
            pytest.param({}, {}, id="both_empty"),
            pytest.param(None, {}, id="scope_none_hive_empty"),
            pytest.param({}, None, id="scope_empty_hive_none"),
            pytest.param(
                {"t1": ["Task", "Tasks"]},
                {"t1": ["Subtask", "Subtasks"]},
                id="both_populated",
            ),
        ],
    )
    def test_round_trip_none_vs_empty_dict(self, scope_child_tiers, hive_child_tiers):
        """Test serialize/parse round-trip preserves None vs {} distinction."""
        # Build scope dict manually
        scope = {"hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}}}
        if scope_child_tiers is not None:
            scope["child_tiers"] = scope_child_tiers
        if hive_child_tiers is not None:
            scope["hives"]["backend"]["child_tiers"] = hive_child_tiers

        # Parse to BeesConfig
        config = parse_scope_to_bees_config(scope)

        # Serialize back to scope dict
        reserialized = serialize_bees_config_to_scope(config)

        # Verify scope-level child_tiers
        if scope_child_tiers is None:
            assert "child_tiers" not in reserialized
        else:
            assert reserialized["child_tiers"] == scope_child_tiers

        # Verify hive-level child_tiers
        if hive_child_tiers is None:
            assert "child_tiers" not in reserialized["hives"]["backend"]
        else:
            assert reserialized["hives"]["backend"]["child_tiers"] == hive_child_tiers


class TestUndertakerScheduleParsing:
    """Tests for undertaker_schedule config key (underscore, not hyphen)."""

    def test_underscore_key_parsed(self):
        """undertaker_schedule (underscore) key is read into HiveConfig attributes."""
        scope = {
            "hives": {
                "main": {
                    "path": "/path",
                    "display_name": "Main",
                    "created_at": TS,
                    "undertaker_schedule": {
                        "interval_seconds": 3600,
                        "query_yaml": "- ['status=finished']",
                    },
                }
            }
        }
        config = parse_scope_to_bees_config(scope)
        hive = config.hives["main"]
        assert hive.undertaker_schedule_seconds == 3600
        assert hive.undertaker_schedule_query_yaml == "- ['status=finished']"

    def test_hyphen_key_ignored(self):
        """undertaker-schedule (legacy hyphen) is silently ignored; fields remain None."""
        scope = {
            "hives": {
                "main": {
                    "path": "/path",
                    "display_name": "Main",
                    "created_at": TS,
                    "undertaker-schedule": {
                        "interval_seconds": 3600,
                        "query_yaml": "- ['status=finished']",
                    },
                }
            }
        }
        config = parse_scope_to_bees_config(scope)
        hive = config.hives["main"]
        assert hive.undertaker_schedule_seconds is None
        assert hive.undertaker_schedule_query_yaml is None

    def test_round_trip_preserves_schedule(self):
        """Serialize then re-parse preserves all undertaker_schedule fields."""
        hive_cfg = HiveConfig(
            path="/path",
            display_name="Main",
            created_at=TS,
            undertaker_schedule_seconds=1800,
            undertaker_schedule_query_yaml="- ['status=finished']",
            undertaker_schedule_log_path="/tmp/ut.log",
        )
        config = BeesConfig(hives={"main": hive_cfg})
        scope = serialize_bees_config_to_scope(config)
        restored = parse_scope_to_bees_config(scope)
        hive = restored.hives["main"]
        assert hive.undertaker_schedule_seconds == 1800
        assert hive.undertaker_schedule_query_yaml == "- ['status=finished']"
        assert hive.undertaker_schedule_log_path == "/tmp/ut.log"

    def test_round_trip_uses_underscore_key(self):
        """Serialized scope dict uses 'undertaker_schedule' (underscore), not hyphen."""
        hive_cfg = HiveConfig(
            path="/path",
            display_name="Main",
            created_at=TS,
            undertaker_schedule_seconds=600,
            undertaker_schedule_query_yaml="- ['status=finished']",
        )
        config = BeesConfig(hives={"main": hive_cfg})
        scope = serialize_bees_config_to_scope(config)
        assert "undertaker_schedule" in scope["hives"]["main"]
        assert "undertaker-schedule" not in scope["hives"]["main"]


class TestGetScopedConfig:
    """Test get_scoped_config for full scope resolution."""

    def test_returns_config_for_matching_scope(self, mock_global_bees_dir, tmp_path):
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        config = get_scoped_config(tmp_path)
        assert config is not None
        assert "backend" in config.hives

    def test_returns_none_for_no_match(self, mock_global_bees_dir):
        assert get_scoped_config(Path("/nonexistent/path")) is None


# ============================================================================
# SCOPED LOAD/SAVE TESTS
# ============================================================================


class TestLoadBeesConfig:
    """Test load_bees_config (scoped version)."""

    def test_load_returns_none_when_no_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        assert load_bees_config() is None

    def test_load_returns_config_for_matching_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "tickets/backend/", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        config = load_bees_config()
        assert config is not None
        assert len(config.hives) == 1
        assert config.hives["backend"].path == "tickets/backend/"
        assert config.hives["backend"].display_name == "Backend"
        assert config.hives["backend"].created_at == TS

    def test_load_empty_hives(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        config = load_bees_config()
        assert config is not None
        assert config.hives == {}

    def test_load_malformed_json_returns_default(self, tmp_path, monkeypatch, mock_global_bees_dir, caplog):
        import logging
        monkeypatch.chdir(tmp_path)
        (mock_global_bees_dir / "config.json").write_text("{invalid json")
        with caplog.at_level(logging.WARNING):
            config = load_bees_config()
        # Returns None because malformed global config → empty scopes → no match
        assert config is None

    @pytest.mark.parametrize(
        "scope_data,error_match",
        [
            pytest.param({"hives": {}, "schema_version": 123}, "schema_version must be a string", id="invalid_schema_version"),
            pytest.param({"hives": {"backend": "not a dict"}}, "Hive 'backend' data must be a dict", id="invalid_hive_data"),
        ],
    )
    def test_load_invalid_scope_data(self, tmp_path, monkeypatch, mock_global_bees_dir, scope_data, error_match):
        monkeypatch.chdir(tmp_path)
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        with pytest.raises(ValueError, match=error_match):
            load_bees_config()


class TestSaveBeesConfig:
    """Test save_bees_config (scoped version)."""

    def test_save_updates_matching_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = BeesConfig(
            hives={"backend": HiveConfig(path="tickets/backend/", display_name="Backend", created_at=TS)},
        )
        save_bees_config(config)

        loaded = load_bees_config()
        assert loaded is not None
        assert "backend" in loaded.hives

    def test_save_raises_when_no_matching_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="No scope matches"):
            save_bees_config(BeesConfig())

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        timestamp = "2026-02-01T15:30:45.678901"
        original = BeesConfig(
            hives={"backend": HiveConfig(path="/path/to/hive", display_name="Backend", created_at=timestamp)},
            child_tiers={"t1": ChildTierConfig("Task", "Tasks")},
        )
        save_bees_config(original)
        loaded = load_bees_config()
        assert loaded is not None
        assert loaded.hives["backend"].created_at == timestamp
        assert loaded.hives["backend"].path == "/path/to/hive"
        assert loaded.child_tiers["t1"].singular == "Task"

    def test_save_preserves_other_scopes(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {"hives": {}, "child_tiers": {}},
                "/other/repo": {"hives": {"other": {"path": "/other", "display_name": "Other", "created_at": TS}}, "child_tiers": {}},
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        save_bees_config(BeesConfig(hives={"backend": _make_hive()}))

        loaded_global = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert "/other/repo" in loaded_global["scopes"]
        assert "other" in loaded_global["scopes"]["/other/repo"]["hives"]

    def test_save_atomic_no_partial_on_failure(self, tmp_path, monkeypatch, mock_global_bees_dir):
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        original_content = (mock_global_bees_dir / "config.json").read_text()

        with patch("os.replace", side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError):
                save_bees_config(BeesConfig(hives={}))

        assert (mock_global_bees_dir / "config.json").read_text() == original_content


class TestValidateUniqueHiveName:
    """Test validate_unique_hive_name for duplicate detection."""

    @pytest.mark.parametrize(
        "existing_hives,check_name",
        [
            pytest.param(None, "backend", id="no_config"),
            pytest.param({}, "backend", id="empty_hives"),
            pytest.param(
                {"frontend": HiveConfig(path="tickets/frontend/", display_name="Frontend", created_at=TS)},
                "backend",
                id="new_unique_name",
            ),
        ],
    )
    def test_validate_unique_name_passes(self, existing_hives, check_name, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        if existing_hives is not None:
            scope_data = {"hives": {}, "child_tiers": {}}
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            save_bees_config(BeesConfig(hives=existing_hives))
        validate_unique_hive_name(check_name)

    @pytest.mark.parametrize(
        "registered_name,display_name,check_name,error_match",
        [
            pytest.param("back_end", "Back End", "back_end", "normalized name 'back_end' already exists", id="duplicate_normalized"),
            pytest.param("backend", "BACKEND", normalize_hive_name("BACKEND"), "normalized name 'backend' already exists", id="case_insensitive"),
            pytest.param("back_end_services", "Back End Services", "back_end_services", "Display name: 'Back End Services'", id="display_name_in_error"),
        ],
    )
    def test_validate_unique_name_collision(self, registered_name, display_name, check_name, error_match, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        hive = HiveConfig(path=f"tickets/{registered_name}/", display_name=display_name, created_at=TS)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        save_bees_config(BeesConfig(hives={registered_name: hive}))
        with pytest.raises(ValueError, match=error_match):
            validate_unique_hive_name(check_name)


# ============================================================================
# EGG RESOLVER CONFIG TESTS
# ============================================================================


class TestEggResolverConfigValidation:
    """Test egg_resolver and egg_resolver_timeout validation at all config levels."""

    @pytest.mark.parametrize(
        "level,egg_resolver,egg_resolver_timeout",
        [
            pytest.param("global", "python resolve.py", 30, id="global_both"),
            pytest.param("global", "python resolve.py", None, id="global_resolver_only"),
            pytest.param("global", None, 30, id="global_timeout_only"),
            pytest.param("scope", "node resolver.js", 45.5, id="scope_both_float_timeout"),
            pytest.param("scope", "bash resolver.sh", None, id="scope_resolver_only"),
            pytest.param("scope", None, 60, id="scope_timeout_only"),
            pytest.param("hive", "java Resolver", 120, id="hive_both"),
            pytest.param("hive", "go run resolver.go", None, id="hive_resolver_only"),
            pytest.param("hive", None, 90, id="hive_timeout_only"),
        ],
    )
    def test_valid_egg_resolver_config_loads(self, level, egg_resolver, egg_resolver_timeout, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test valid egg_resolver and egg_resolver_timeout load correctly at all levels."""
        monkeypatch.chdir(tmp_path)

        if level == "global":
            global_config = {"scopes": {}, "schema_version": "2.0"}
            if egg_resolver is not None:
                global_config["egg_resolver"] = egg_resolver
            if egg_resolver_timeout is not None:
                global_config["egg_resolver_timeout"] = egg_resolver_timeout
            (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))
            loaded = load_global_config()
            assert loaded.get("egg_resolver") == egg_resolver
            assert loaded.get("egg_resolver_timeout") == egg_resolver_timeout

        elif level == "scope":
            scope_data = {
                "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                "child_tiers": {},
            }
            if egg_resolver is not None:
                scope_data["egg_resolver"] = egg_resolver
            if egg_resolver_timeout is not None:
                scope_data["egg_resolver_timeout"] = egg_resolver_timeout
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            config = load_bees_config()
            assert config.egg_resolver == egg_resolver
            assert config.egg_resolver_timeout == egg_resolver_timeout

        else:  # hive level
            hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS}
            if egg_resolver is not None:
                hive_data["egg_resolver"] = egg_resolver
            if egg_resolver_timeout is not None:
                hive_data["egg_resolver_timeout"] = egg_resolver_timeout
            scope_data = {"hives": {"backend": hive_data}, "child_tiers": {}}
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            config = load_bees_config()
            assert config.hives["backend"].egg_resolver == egg_resolver
            assert config.hives["backend"].egg_resolver_timeout == egg_resolver_timeout

    @pytest.mark.parametrize(
        "level,field,invalid_value,error_match",
        [
            pytest.param("global", "egg_resolver", 123, "Global egg_resolver must be a string or null", id="global_resolver_number"),
            pytest.param("global", "egg_resolver", ["python", "resolve.py"], "Global egg_resolver must be a string or null", id="global_resolver_array"),
            pytest.param("global", "egg_resolver_timeout", "30", "Global egg_resolver_timeout must be a number or null", id="global_timeout_string"),
            pytest.param("global", "egg_resolver_timeout", ["30"], "Global egg_resolver_timeout must be a number or null", id="global_timeout_array"),
            pytest.param("global", "egg_resolver_timeout", -5, "Global egg_resolver_timeout must be positive", id="global_timeout_negative"),
            pytest.param("global", "egg_resolver_timeout", 0, "Global egg_resolver_timeout must be positive", id="global_timeout_zero"),
            pytest.param("scope", "egg_resolver", 456, "Scope egg_resolver must be a string or null", id="scope_resolver_number"),
            pytest.param("scope", "egg_resolver", {"cmd": "python"}, "Scope egg_resolver must be a string or null", id="scope_resolver_dict"),
            pytest.param("scope", "egg_resolver_timeout", "60", "Scope egg_resolver_timeout must be a number or null", id="scope_timeout_string"),
            pytest.param("scope", "egg_resolver_timeout", -10, "Scope egg_resolver_timeout must be positive", id="scope_timeout_negative"),
            pytest.param("hive", "egg_resolver", 789, "Hive 'backend' egg_resolver must be a string or null", id="hive_resolver_number"),
            pytest.param("hive", "egg_resolver", True, "Hive 'backend' egg_resolver must be a string or null", id="hive_resolver_bool"),
            pytest.param("hive", "egg_resolver_timeout", "90", "Hive 'backend' egg_resolver_timeout must be a number or null", id="hive_timeout_string"),
            pytest.param("hive", "egg_resolver_timeout", -15, "Hive 'backend' egg_resolver_timeout must be positive", id="hive_timeout_negative"),
        ],
    )
    def test_invalid_egg_resolver_config_raises_error(self, level, field, invalid_value, error_match, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test invalid egg_resolver config raises error at load time."""
        monkeypatch.chdir(tmp_path)

        if level == "global":
            global_config = {"scopes": {}, "schema_version": "2.0", field: invalid_value}
            (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))
            with pytest.raises(ValueError, match=error_match):
                load_global_config()

        elif level == "scope":
            scope_data = {
                "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                "child_tiers": {},
                field: invalid_value,
            }
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            with pytest.raises(ValueError, match=error_match):
                load_bees_config()

        else:  # hive level
            hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS, field: invalid_value}
            scope_data = {"hives": {"backend": hive_data}, "child_tiers": {}}
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            with pytest.raises(ValueError, match=error_match):
                load_bees_config()


class TestEggResolverResolution:
    """Test egg_resolver resolution with 3-level fallback."""

    def test_hive_overrides_scope_and_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test hive-level egg_resolver takes precedence."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver": "hive_resolver",
                        }
                    },
                    "child_tiers": {},
                    "egg_resolver": "scope_resolver",
                }
            },
            "schema_version": "2.0",
            "egg_resolver": "global_resolver",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result == "hive_resolver"

    def test_scope_overrides_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level egg_resolver takes precedence when hive has none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                    "egg_resolver": "scope_resolver",
                }
            },
            "schema_version": "2.0",
            "egg_resolver": "global_resolver",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result == "scope_resolver"

    def test_global_used_when_scope_and_hive_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test global-level egg_resolver used when scope and hive have none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
            "egg_resolver": "global_resolver",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result == "global_resolver"

    def test_null_falls_through_to_next_level(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test null egg_resolver at hive level falls through to scope."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver": None,
                        }
                    },
                    "child_tiers": {},
                    "egg_resolver": "scope_resolver",
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result == "scope_resolver"

    def test_default_terminates_fallback_chain(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test 'default' keyword stops fallback chain and returns None."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver": "default",
                        }
                    },
                    "child_tiers": {},
                    "egg_resolver": "scope_resolver",
                }
            },
            "schema_version": "2.0",
            "egg_resolver": "global_resolver",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result is None

    def test_default_at_scope_level(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test 'default' keyword at scope level stops fallback."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                    "egg_resolver": "default",
                }
            },
            "schema_version": "2.0",
            "egg_resolver": "global_resolver",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result is None

    def test_no_config_anywhere_returns_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_egg_resolver returns None when not configured anywhere."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_egg_resolver
        result = resolve_egg_resolver("backend")
        assert result is None

    def test_nonexistent_hive_raises_error(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_egg_resolver raises error for nonexistent hive."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_egg_resolver
        with pytest.raises(ValueError, match="Hive 'nonexistent' does not exist"):
            resolve_egg_resolver("nonexistent")


class TestEggResolverTimeoutResolution:
    """Test egg_resolver_timeout resolution with 3-level fallback."""

    def test_hive_overrides_scope_and_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test hive-level timeout takes precedence."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver_timeout": 10,
                        }
                    },
                    "child_tiers": {},
                    "egg_resolver_timeout": 20,
                }
            },
            "schema_version": "2.0",
            "egg_resolver_timeout": 30,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result == 10

    def test_scope_overrides_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level timeout takes precedence when hive has none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                    "egg_resolver_timeout": 45,
                }
            },
            "schema_version": "2.0",
            "egg_resolver_timeout": 60,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result == 45

    def test_global_used_when_scope_and_hive_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test global-level timeout used when scope and hive have none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
            "egg_resolver_timeout": 90,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result == 90

    def test_null_falls_through_to_next_level(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test null timeout at hive level falls through to scope."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver_timeout": None,
                        }
                    },
                    "child_tiers": {},
                    "egg_resolver_timeout": 120,
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result == 120

    def test_float_timeout_preserved(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test float timeout values are preserved."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "egg_resolver_timeout": 45.5,
                        }
                    },
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result == 45.5

    def test_no_timeout_anywhere_returns_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_egg_resolver_timeout returns None when not configured anywhere."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_egg_resolver_timeout
        result = resolve_egg_resolver_timeout("backend")
        assert result is None

    def test_nonexistent_hive_raises_error(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_egg_resolver_timeout raises error for nonexistent hive."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_egg_resolver_timeout
        with pytest.raises(ValueError, match="Hive 'nonexistent' does not exist"):
            resolve_egg_resolver_timeout("nonexistent")


class TestEggResolverSerialization:
    """Test egg_resolver fields are serialized correctly."""

    def test_serialize_includes_fields_when_present(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test serialization includes egg_resolver fields when not None."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    egg_resolver="python resolve.py",
                    egg_resolver_timeout=30,
                )
            },
            egg_resolver="node resolver.js",
            egg_resolver_timeout=60,
        )

        scope_dict = serialize_bees_config_to_scope(config)

        # Check hive-level fields
        assert scope_dict["hives"]["backend"]["egg_resolver"] == "python resolve.py"
        assert scope_dict["hives"]["backend"]["egg_resolver_timeout"] == 30

        # Check scope-level fields
        assert scope_dict["egg_resolver"] == "node resolver.js"
        assert scope_dict["egg_resolver_timeout"] == 60

    def test_serialize_excludes_fields_when_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test serialization excludes egg_resolver fields when None."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    egg_resolver=None,
                    egg_resolver_timeout=None,
                )
            },
            egg_resolver=None,
            egg_resolver_timeout=None,
        )

        scope_dict = serialize_bees_config_to_scope(config)

        # Check hive-level fields are not present
        assert "egg_resolver" not in scope_dict["hives"]["backend"]
        assert "egg_resolver_timeout" not in scope_dict["hives"]["backend"]

        # Check scope-level fields are not present
        assert "egg_resolver" not in scope_dict
        assert "egg_resolver_timeout" not in scope_dict

    def test_roundtrip_with_egg_resolver_fields(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test save and load roundtrip preserves egg_resolver fields."""
        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        original = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    egg_resolver="python resolve.py",
                    egg_resolver_timeout=45,
                )
            },
            egg_resolver="node resolver.js",
            egg_resolver_timeout=90,
        )

        save_bees_config(original)
        loaded = load_bees_config()

        assert loaded.hives["backend"].egg_resolver == "python resolve.py"
        assert loaded.hives["backend"].egg_resolver_timeout == 45
        assert loaded.egg_resolver == "node resolver.js"
        assert loaded.egg_resolver_timeout == 90


class TestResolveChildTiersForHive:
    """Test resolve_child_tiers_for_hive() with 3-level fallback."""

    def test_hive_level_overrides_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test hive-level child_tiers takes precedence over scope-level."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "child_tiers": {"t1": ["Issue", "Issues"]},
                        }
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {"t1": ChildTierConfig("Issue", "Issues")}

    def test_scope_level_overrides_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level child_tiers takes precedence when hive has none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                }
            },
            "schema_version": "2.0",
            "child_tiers": {"t1": ["Epic", "Epics"]},
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {"t1": ChildTierConfig("Task", "Tasks")}

    def test_global_level_fallback(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test global-level child_tiers used when hive and scope are None."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                }
            },
            "schema_version": "2.0",
            "child_tiers": {"t1": ["Epic", "Epics"]},
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {"t1": ChildTierConfig("Epic", "Epics")}

    def test_all_levels_none_returns_empty(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test returns {} (bees-only) when no level has child_tiers configured."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {}

    def test_empty_dict_stops_at_hive(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test {} at hive level stops the chain even if scope has tiers."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "child_tiers": {},
                        }
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {}

    def test_empty_dict_stops_at_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test {} at scope level stops the chain even if global has tiers."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
            "child_tiers": {"t1": ["Epic", "Epics"]},
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {}

    def test_empty_dict_stops_at_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test {} at global level returns bees-only."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                }
            },
            "schema_version": "2.0",
            "child_tiers": {},
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {}

    def test_nonexistent_hive_raises(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test ValueError raised when hive doesn't exist in config."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        with pytest.raises(ValueError, match="nonexistent"):
            resolve_child_tiers_for_hive("nonexistent")

    def test_config_param_used_when_provided(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test that explicit config param is used instead of loading."""
        config = BeesConfig(
            hives={"myhive": HiveConfig(
                path="/path", display_name="My Hive", created_at=TS,
                child_tiers={"t1": ChildTierConfig("Task", "Tasks")},
            )},
            child_tiers={"t1": ChildTierConfig("Epic", "Epics")},
        )

        result = resolve_child_tiers_for_hive("myhive", config=config)
        assert result == {"t1": ChildTierConfig("Task", "Tasks")}

    def test_null_at_hive_level_falls_through_to_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test explicit null child_tiers at hive level falls through to scope."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "child_tiers": None,
                        }
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {"t1": ChildTierConfig("Task", "Tasks")}

    def test_missing_key_at_hive_level_falls_through(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test absent child_tiers key at hive level falls through (same as None)."""
        monkeypatch.chdir(tmp_path)
        # Hive entry has no child_tiers key at all
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {"path": "/path", "display_name": "Backend", "created_at": TS}
                    },
                    "child_tiers": {"t1": ["Epic", "Epics"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result == {"t1": ChildTierConfig("Epic", "Epics")}

    @pytest.mark.parametrize(
        "hive_tiers,scope_tiers,global_tiers,expected_t1_name",
        [
            pytest.param(
                {"t1": ["Hive Task", "Hive Tasks"]}, {"t1": ["Scope Task", "Scope Tasks"]},
                {"t1": ["Global Task", "Global Tasks"]}, "Hive Task",
                id="hive_wins_over_all",
            ),
            pytest.param(
                None, {"t1": ["Scope Task", "Scope Tasks"]},
                {"t1": ["Global Task", "Global Tasks"]}, "Scope Task",
                id="scope_wins_when_hive_none",
            ),
            pytest.param(
                None, None, {"t1": ["Global Task", "Global Tasks"]}, "Global Task",
                id="global_wins_when_hive_and_scope_none",
            ),
        ],
    )
    def test_fallback_priority_parametrized(
        self, hive_tiers, scope_tiers, global_tiers, expected_t1_name,
        tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """Test fallback priority across all three configured levels."""
        monkeypatch.chdir(tmp_path)
        hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS}
        if hive_tiers is not None:
            hive_data["child_tiers"] = hive_tiers

        scope_entry = {"hives": {"backend": hive_data}}
        if scope_tiers is not None:
            scope_entry["child_tiers"] = scope_tiers

        global_config = {"scopes": {str(tmp_path): scope_entry}, "schema_version": "2.0"}
        if global_tiers is not None:
            global_config["child_tiers"] = global_tiers

        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("backend")
        assert result["t1"].singular == expected_t1_name


class TestResolveChildTiersMultipleHives:
    """Test per-hive child_tiers resolution with multiple independent hives."""

    def test_each_hive_resolves_independently(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test multiple hives each resolve to their own child_tiers independently."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "features": {
                            "path": "/features",
                            "display_name": "Features",
                            "created_at": TS,
                            "child_tiers": {"t1": ["Epic", "Epics"]},
                        },
                        "bugs": {
                            "path": "/bugs",
                            "display_name": "Bugs",
                            "created_at": TS,
                            "child_tiers": {},
                        },
                        "backend": {
                            "path": "/backend",
                            "display_name": "Backend",
                            "created_at": TS,
                        },
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        # features: hive-level override → Epics only
        features_tiers = resolve_child_tiers_for_hive("features")
        assert features_tiers["t1"].singular == "Epic"
        assert len(features_tiers) == 1

        # bugs: hive-level empty {} → bees-only
        bugs_tiers = resolve_child_tiers_for_hive("bugs")
        assert bugs_tiers == {}

        # backend: no hive child_tiers → inherits scope Task/Subtask
        backend_tiers = resolve_child_tiers_for_hive("backend")
        assert backend_tiers["t1"].singular == "Task"
        assert backend_tiers["t2"].singular == "Subtask"
        assert len(backend_tiers) == 2

    def test_hive_override_does_not_affect_other_hives(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test setting child_tiers on one hive doesn't bleed into others."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "hive_a": {
                            "path": "/a", "display_name": "A", "created_at": TS,
                            "child_tiers": {"t1": ["Custom", "Customs"]},
                        },
                        "hive_b": {
                            "path": "/b", "display_name": "B", "created_at": TS,
                        },
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        a_tiers = resolve_child_tiers_for_hive("hive_a")
        b_tiers = resolve_child_tiers_for_hive("hive_b")

        assert a_tiers["t1"].singular == "Custom"
        assert b_tiers["t1"].singular == "Task"

    @pytest.mark.parametrize(
        "hive_tiers,expected_count",
        [
            pytest.param(
                {"t1": ["Story", "Stories"]}, 1,
                id="hive_fewer_tiers_than_scope",
            ),
            pytest.param(
                {"t1": ["Phase", "Phases"], "t2": ["Step", "Steps"], "t3": ["Action", "Actions"]}, 3,
                id="hive_more_tiers_than_scope",
            ),
        ],
    )
    def test_hive_tier_count_independent_of_scope(
        self, hive_tiers, expected_count, tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """Test hive can have different number of tiers than scope."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "test_hive": {
                            "path": "/path", "display_name": "Test", "created_at": TS,
                            "child_tiers": hive_tiers,
                        }
                    },
                    "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        result = resolve_child_tiers_for_hive("test_hive")
        assert len(result) == expected_count


class TestChildTiersConfigRoundTrip:
    """Test per-hive child_tiers survives config save/load round-trip."""

    def test_hive_child_tiers_preserved_through_save_load(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test per-hive child_tiers persists through save_bees_config/load_bees_config cycle."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "child_tiers": {"t1": ["Epic", "Epics"]},
                },
                "backend": {
                    "path": "/backend", "display_name": "Backend", "created_at": TS,
                },
            },
            "child_tiers": {"t1": ["Task", "Tasks"]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = load_bees_config()
        assert config is not None
        save_bees_config(config)

        # Verify per-hive tiers survived in raw JSON
        raw = json.loads((mock_global_bees_dir / "config.json").read_text())
        features_data = raw["scopes"][str(tmp_path)]["hives"]["features"]
        assert "child_tiers" in features_data
        assert features_data["child_tiers"]["t1"] == ["Epic", "Epics"]

        # Verify backend still has no hive-level child_tiers
        backend_data = raw["scopes"][str(tmp_path)]["hives"]["backend"]
        assert "child_tiers" not in backend_data

    def test_scope_child_tiers_preserved_alongside_hive_overrides(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level child_tiers aren't corrupted by hive-level overrides."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "child_tiers": {"t1": ["Epic", "Epics"]},
                },
            },
            "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = load_bees_config()
        save_bees_config(config)

        raw = json.loads((mock_global_bees_dir / "config.json").read_text())
        scope = raw["scopes"][str(tmp_path)]
        assert scope["child_tiers"]["t1"] == ["Task", "Tasks"]
        assert scope["child_tiers"]["t2"] == ["Subtask", "Subtasks"]

    def test_resolution_consistent_after_round_trip(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_child_tiers_for_hive gives same result before and after save/load."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "child_tiers": {"t1": ["Epic", "Epics"]},
                },
                "backend": {
                    "path": "/backend", "display_name": "Backend", "created_at": TS,
                },
            },
            "child_tiers": {"t1": ["Task", "Tasks"]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Resolve before round-trip
        before_features = resolve_child_tiers_for_hive("features")
        before_backend = resolve_child_tiers_for_hive("backend")

        # Round-trip
        config = load_bees_config()
        save_bees_config(config)

        # Resolve after round-trip
        after_features = resolve_child_tiers_for_hive("features")
        after_backend = resolve_child_tiers_for_hive("backend")

        assert before_features == after_features
        assert before_backend == after_backend


# ============================================================================
# STATUS VALUES CONFIG TESTS
# ============================================================================


class TestStatusValuesConfigValidation:
    """Test status_values validation at global, scope, and hive levels."""

    @pytest.mark.parametrize(
        "level,status_values",
        [
            pytest.param("global", ["open", "closed"], id="global_valid_list"),
            pytest.param("global", [], id="global_empty_list"),
            pytest.param("global", ["pupa", "larva", "worker", "finished"], id="global_multiple_values"),
            pytest.param("scope", ["todo", "doing", "done"], id="scope_valid_list"),
            pytest.param("scope", [], id="scope_empty_list"),
            pytest.param("hive", ["open", "in_progress", "completed"], id="hive_valid_list"),
            pytest.param("hive", [], id="hive_empty_list"),
        ],
    )
    def test_valid_status_values_load(self, level, status_values, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test valid status_values load correctly at all levels."""
        monkeypatch.chdir(tmp_path)

        if level == "global":
            global_config = {"scopes": {}, "schema_version": "2.0", "status_values": status_values}
            (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))
            loaded = load_global_config()
            assert loaded.get("status_values") == status_values

        elif level == "scope":
            scope_data = {
                "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                "child_tiers": {},
                "status_values": status_values,
            }
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            config = load_bees_config()
            assert config.status_values == status_values

        else:  # hive level
            hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS, "status_values": status_values}
            scope_data = {"hives": {"backend": hive_data}, "child_tiers": {}}
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            config = load_bees_config()
            assert config.hives["backend"].status_values == status_values

    @pytest.mark.parametrize(
        "level,invalid_value,error_match",
        [
            pytest.param("global", "open", "Global status_values must be a list", id="global_string"),
            pytest.param("global", {"status": "open"}, "Global status_values must be a list", id="global_dict"),
            pytest.param("global", 123, "Global status_values must be a list", id="global_int"),
            pytest.param("global", ["open", 123], "must be a list of strings", id="global_list_with_non_string"),
            pytest.param("global", ["open", None], "must be a list of strings", id="global_list_with_null"),
            pytest.param("scope", "open", "Scope status_values must be a list", id="scope_string"),
            pytest.param("scope", {"status": "open"}, "Scope status_values must be a list", id="scope_dict"),
            pytest.param("scope", 456, "Scope status_values must be a list", id="scope_int"),
            pytest.param("scope", ["todo", 789], "must be a list of strings", id="scope_list_with_non_string"),
            pytest.param("hive", "open", "Hive 'backend' status_values must be a list", id="hive_string"),
            pytest.param("hive", {"status": "open"}, "Hive 'backend' status_values must be a list", id="hive_dict"),
            pytest.param("hive", 123, "Hive 'backend' status_values must be a list", id="hive_int"),
            pytest.param("hive", ["open", False], "must be a list of strings", id="hive_list_with_bool"),
            pytest.param("global", ["open", ""], "must not contain empty strings", id="global_empty_string"),
            pytest.param("scope", ["", "done"], "must not contain empty strings", id="scope_empty_string"),
            pytest.param("hive", ["open", "  "], "must not contain empty strings", id="hive_whitespace_string"),
        ],
    )
    def test_invalid_status_values_raise_error(self, level, invalid_value, error_match, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test invalid status_values raise ValueError at all levels."""
        monkeypatch.chdir(tmp_path)

        if level == "global":
            global_config = {"scopes": {}, "schema_version": "2.0", "status_values": invalid_value}
            (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))
            with pytest.raises(ValueError, match=error_match):
                load_global_config()

        elif level == "scope":
            scope_data = {
                "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                "child_tiers": {},
                "status_values": invalid_value,
            }
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            with pytest.raises(ValueError, match=error_match):
                load_bees_config()

        else:  # hive level
            hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS, "status_values": invalid_value}
            scope_data = {"hives": {"backend": hive_data}, "child_tiers": {}}
            write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
            with pytest.raises(ValueError, match=error_match):
                load_bees_config()


class TestStatusValuesResolution:
    """Test status_values resolution with 3-level fallback."""

    def test_hive_overrides_scope_and_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test hive-level status_values takes precedence."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "status_values": ["hive_open", "hive_closed"],
                        }
                    },
                    "child_tiers": {},
                    "status_values": ["scope_todo", "scope_done"],
                }
            },
            "schema_version": "2.0",
            "status_values": ["global_open", "global_closed"],
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == ["hive_open", "hive_closed"]

    def test_scope_overrides_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level status_values takes precedence when hive has none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                    "status_values": ["scope_todo", "scope_done"],
                }
            },
            "schema_version": "2.0",
            "status_values": ["global_open", "global_closed"],
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == ["scope_todo", "scope_done"]

    def test_global_used_when_scope_and_hive_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test global-level status_values used when scope and hive have none."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                }
            },
            "schema_version": "2.0",
            "status_values": ["global_open", "global_closed"],
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == ["global_open", "global_closed"]

    def test_empty_list_falls_through_to_next_level(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test empty list [] at hive level falls through to scope."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "status_values": [],
                        }
                    },
                    "child_tiers": {},
                    "status_values": ["scope_todo", "scope_done"],
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == ["scope_todo", "scope_done"]

    def test_empty_list_at_scope_falls_through_to_global(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test empty list [] at scope level falls through to global."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {},
                    "status_values": [],
                }
            },
            "schema_version": "2.0",
            "status_values": ["global_open", "global_closed"],
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == ["global_open", "global_closed"]

    def test_null_overrides_scope_inheritance(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test explicit null at hive level stops inheritance — no constraints for that hive."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "backend": {
                            "path": "/path",
                            "display_name": "Backend",
                            "created_at": TS,
                            "status_values": None,
                        }
                    },
                    "child_tiers": {},
                    "status_values": ["scope_todo", "scope_done"],
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result is None

    def test_no_config_anywhere_returns_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_status_values_for_hive returns None when not configured anywhere."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result is None

    def test_nonexistent_hive_raises_error(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_status_values_for_hive raises error for nonexistent hive."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": "/path", "display_name": "Backend", "created_at": TS}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_status_values_for_hive
        with pytest.raises(ValueError, match="Hive 'nonexistent' does not exist"):
            resolve_status_values_for_hive("nonexistent")

    def test_config_param_used_when_provided(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test that explicit config param is used instead of loading."""
        config = BeesConfig(
            hives={"myhive": HiveConfig(
                path="/path", display_name="My Hive", created_at=TS,
                status_values=["open", "closed"],
            )},
            status_values=["todo", "done"],
        )

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("myhive", config=config)
        assert result == ["open", "closed"]

    @pytest.mark.parametrize(
        "hive_values,scope_values,global_values,expected",
        [
            pytest.param(
                ["hive_open", "hive_closed"], ["scope_todo", "scope_done"],
                ["global_open", "global_closed"], ["hive_open", "hive_closed"],
                id="hive_wins_over_all",
            ),
            pytest.param(
                None, ["scope_todo", "scope_done"],
                ["global_open", "global_closed"], ["scope_todo", "scope_done"],
                id="scope_wins_when_hive_none",
            ),
            pytest.param(
                [], ["scope_todo", "scope_done"],
                ["global_open", "global_closed"], ["scope_todo", "scope_done"],
                id="scope_wins_when_hive_empty",
            ),
            pytest.param(
                None, None, ["global_open", "global_closed"], ["global_open", "global_closed"],
                id="global_wins_when_hive_and_scope_none",
            ),
            pytest.param(
                [], [], ["global_open", "global_closed"], ["global_open", "global_closed"],
                id="global_wins_when_hive_and_scope_empty",
            ),
            pytest.param(None, None, None, None, id="all_none_returns_none"),
            pytest.param([], [], [], None, id="all_empty_returns_none"),
        ],
    )
    def test_fallback_priority_parametrized(
        self, hive_values, scope_values, global_values, expected,
        tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """Test fallback priority across all three configured levels."""
        monkeypatch.chdir(tmp_path)
        hive_data = {"path": "/path", "display_name": "Backend", "created_at": TS}
        if hive_values is not None:
            hive_data["status_values"] = hive_values

        scope_entry = {"hives": {"backend": hive_data}}
        if scope_values is not None:
            scope_entry["status_values"] = scope_values

        global_config = {"scopes": {str(tmp_path): scope_entry}, "schema_version": "2.0"}
        if global_values is not None:
            global_config["status_values"] = global_values

        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        result = resolve_status_values_for_hive("backend")
        assert result == expected


class TestStatusValuesMultipleHives:
    """Test per-hive status_values resolution with multiple independent hives."""

    def test_each_hive_resolves_independently(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test multiple hives each resolve to their own status_values independently."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "features": {
                            "path": "/features",
                            "display_name": "Features",
                            "created_at": TS,
                            "status_values": ["backlog", "active", "shipped"],
                        },
                        "bugs": {
                            "path": "/bugs",
                            "display_name": "Bugs",
                            "created_at": TS,
                            "status_values": [],
                        },
                        "backend": {
                            "path": "/backend",
                            "display_name": "Backend",
                            "created_at": TS,
                        },
                    },
                    "child_tiers": {},
                    "status_values": ["todo", "doing", "done"],
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive

        # features: hive-level override
        features_values = resolve_status_values_for_hive("features")
        assert features_values == ["backlog", "active", "shipped"]

        # bugs: hive-level empty [] → falls through to scope
        bugs_values = resolve_status_values_for_hive("bugs")
        assert bugs_values == ["todo", "doing", "done"]

        # backend: no hive status_values → inherits scope
        backend_values = resolve_status_values_for_hive("backend")
        assert backend_values == ["todo", "doing", "done"]

    def test_hive_override_does_not_affect_other_hives(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test setting status_values on one hive doesn't bleed into others."""
        monkeypatch.chdir(tmp_path)
        global_config = {
            "scopes": {
                str(tmp_path): {
                    "hives": {
                        "hive_a": {
                            "path": "/a", "display_name": "A", "created_at": TS,
                            "status_values": ["custom_open", "custom_closed"],
                        },
                        "hive_b": {
                            "path": "/b", "display_name": "B", "created_at": TS,
                        },
                    },
                    "child_tiers": {},
                    "status_values": ["open", "closed"],
                }
            },
            "schema_version": "2.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(global_config))

        from src.config import resolve_status_values_for_hive
        a_values = resolve_status_values_for_hive("hive_a")
        b_values = resolve_status_values_for_hive("hive_b")

        assert a_values == ["custom_open", "custom_closed"]
        assert b_values == ["open", "closed"]


class TestStatusValuesSerialization:
    """Test status_values serialization preserves None, [], and non-empty lists."""

    def test_serialize_includes_fields_when_present(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test serialization includes status_values when not None."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    status_values=["hive_open", "hive_closed"],
                )
            },
            status_values=["scope_todo", "scope_done"],
        )

        scope_dict = serialize_bees_config_to_scope(config)

        # Check hive-level fields
        assert scope_dict["hives"]["backend"]["status_values"] == ["hive_open", "hive_closed"]

        # Check scope-level fields
        assert scope_dict["status_values"] == ["scope_todo", "scope_done"]

    def test_serialize_excludes_fields_when_none(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test serialization excludes status_values when None."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    status_values=None,
                )
            },
            status_values=None,
        )

        scope_dict = serialize_bees_config_to_scope(config)

        # Check hive-level fields are not present
        assert "status_values" not in scope_dict["hives"]["backend"]

        # Check scope-level fields are not present
        assert "status_values" not in scope_dict

    def test_serialize_preserves_empty_list(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test serialization preserves empty list [] (different from None)."""
        config = BeesConfig(
            hives={
                "backend": HiveConfig(
                    path="/path",
                    display_name="Backend",
                    created_at=TS,
                    status_values=[],
                )
            },
            status_values=[],
        )

        scope_dict = serialize_bees_config_to_scope(config)

        # Check empty list is preserved at both levels
        assert scope_dict["hives"]["backend"]["status_values"] == []
        assert scope_dict["status_values"] == []

    def test_scope_level_not_corrupted_by_hive_overrides(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test scope-level status_values aren't corrupted by hive-level overrides."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "status_values": ["backlog", "active"],
                },
            },
            "child_tiers": {},
            "status_values": ["todo", "doing", "done"],
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = load_bees_config()
        save_bees_config(config)

        raw = json.loads((mock_global_bees_dir / "config.json").read_text())
        scope = raw["scopes"][str(tmp_path)]
        assert scope["status_values"] == ["todo", "doing", "done"]


class TestStatusValuesConfigRoundTrip:
    """Test status_values survives config save/load round-trip."""

    def test_hive_status_values_preserved_through_save_load(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test per-hive status_values persists through save_bees_config/load_bees_config cycle."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "status_values": ["backlog", "active", "shipped"],
                },
                "backend": {
                    "path": "/backend", "display_name": "Backend", "created_at": TS,
                },
            },
            "child_tiers": {},
            "status_values": ["todo", "doing", "done"],
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = load_bees_config()
        assert config is not None
        save_bees_config(config)

        # Verify per-hive values survived in raw JSON
        raw = json.loads((mock_global_bees_dir / "config.json").read_text())
        features_data = raw["scopes"][str(tmp_path)]["hives"]["features"]
        assert "status_values" in features_data
        assert features_data["status_values"] == ["backlog", "active", "shipped"]

        # Verify backend still has no hive-level status_values
        backend_data = raw["scopes"][str(tmp_path)]["hives"]["backend"]
        assert "status_values" not in backend_data

    def test_resolution_consistent_after_round_trip(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test resolve_status_values_for_hive gives same result before and after save/load."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "features": {
                    "path": "/features", "display_name": "Features", "created_at": TS,
                    "status_values": ["backlog", "active"],
                },
                "backend": {
                    "path": "/backend", "display_name": "Backend", "created_at": TS,
                },
            },
            "child_tiers": {},
            "status_values": ["todo", "done"],
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        from src.config import resolve_status_values_for_hive

        # Resolve before round-trip
        before_features = resolve_status_values_for_hive("features")
        before_backend = resolve_status_values_for_hive("backend")

        # Round-trip
        config = load_bees_config()
        save_bees_config(config)

        # Resolve after round-trip
        after_features = resolve_status_values_for_hive("features")
        after_backend = resolve_status_values_for_hive("backend")

        assert before_features == after_features
        assert before_backend == after_backend

    def test_empty_list_preserved_through_round_trip(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test empty list [] is preserved through save/load cycle."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {
                "backend": {
                    "path": "/backend", "display_name": "Backend", "created_at": TS,
                    "status_values": [],
                },
            },
            "child_tiers": {},
            "status_values": [],
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        config = load_bees_config()
        save_bees_config(config)

        # Verify empty lists are preserved in raw JSON
        raw = json.loads((mock_global_bees_dir / "config.json").read_text())
        backend_data = raw["scopes"][str(tmp_path)]["hives"]["backend"]
        assert backend_data["status_values"] == []
        assert raw["scopes"][str(tmp_path)]["status_values"] == []


class TestSetConfigPath:
    """Tests for set_config_path() override behavior."""

    def test_load_reads_from_override_path(self, tmp_path):
        """set_config_path causes load_global_config to read from the specified file."""
        config_data = {"scopes": {"/test": {"hives": {}}}, "schema_version": "2.0"}
        config_file = tmp_path / "custom_config.json"
        config_file.write_text(json.dumps(config_data))
        try:
            set_config_path(str(config_file))
            result = load_global_config()
            assert result["scopes"] == {"/test": {"hives": {}}}
        finally:
            set_config_path(None)

    def test_reset_to_default_reads_default_path(self, tmp_path, mock_global_bees_dir):
        """set_config_path(None) resets to reading from ~/.bees/config.json."""
        custom_data = {"scopes": {"/custom": {}}, "schema_version": "2.0"}
        disk_data = {"scopes": {"/disk": {"hives": {}}}, "schema_version": "2.0"}

        config_file = tmp_path / "custom_config.json"
        config_file.write_text(json.dumps(custom_data))
        (mock_global_bees_dir / "config.json").write_text(json.dumps(disk_data))

        set_config_path(str(config_file))
        try:
            result = load_global_config()
            assert "/custom" in result["scopes"]
        finally:
            set_config_path(None)

        result = load_global_config()
        assert "/disk" in result["scopes"]

    def test_save_writes_to_override_path(self, tmp_path):
        """save_global_config writes to the override path when set_config_path is active."""
        config_file = tmp_path / "save_target.json"
        # File need not exist before save
        new_config = {"scopes": {"/saved": {"hives": {}}}, "schema_version": "2.0"}
        try:
            set_config_path(str(config_file))
            save_global_config(new_config)
            written = json.loads(config_file.read_text())
            assert written["scopes"] == {"/saved": {"hives": {}}}
        finally:
            set_config_path(None)


# ============================================================================
# IN-MEMORY CONFIG OVERRIDE TESTS
# ============================================================================


class TestConfigOverride:
    """Tests for set_test_config_override() in-memory bypass of disk I/O."""

    def test_load_returns_override_without_disk(self, mock_global_bees_dir):
        """load_global_config returns override dict without reading disk."""
        override = {"scopes": {"/test": {"hives": {}}}, "schema_version": "2.0"}
        try:
            set_test_config_override(override)
            result = load_global_config()
            assert result is override
            assert result["scopes"] == {"/test": {"hives": {}}}
        finally:
            set_test_config_override(None)

    def test_save_mutates_override_not_disk(self, mock_global_bees_dir):
        """save_global_config mutates override in-place; disk file is unchanged."""
        override = {"scopes": {"/original": {"hives": {}}}, "schema_version": "2.0"}
        disk_config = {"scopes": {"/disk": {"hives": {}}}, "schema_version": "2.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(disk_config))

        try:
            set_test_config_override(override)
            save_global_config({"scopes": {"/updated": {"hives": {}}}, "schema_version": "2.0"})
            assert "/updated" in override["scopes"]
            disk_content = json.loads((mock_global_bees_dir / "config.json").read_text())
            assert "/disk" in disk_content["scopes"]
        finally:
            set_test_config_override(None)

    def test_clear_override_resumes_disk_reads(self, mock_global_bees_dir):
        """After set_test_config_override(None), load_global_config reads from disk."""
        override = {"scopes": {"/in-memory": {"hives": {}}}, "schema_version": "2.0"}
        disk_config = {"scopes": {"/on-disk": {"hives": {}}}, "schema_version": "2.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(disk_config))

        set_test_config_override(override)
        assert "/in-memory" in load_global_config()["scopes"]

        set_test_config_override(None)
        assert "/on-disk" in load_global_config()["scopes"]

    def test_concurrent_load_save_under_override(self, mock_global_bees_dir):
        """10 concurrent threads calling load/save under active override do not race."""
        import threading

        NUM_THREADS = 10
        barrier = threading.Barrier(NUM_THREADS)
        errors = []
        override = {"scopes": {}, "schema_version": "2.0"}

        try:
            set_test_config_override(override)

            def worker(i):
                try:
                    barrier.wait()
                    if i % 2 == 0:
                        result = load_global_config()
                        assert result is not None
                    else:
                        save_global_config({"scopes": {f"/t{i}": {}}, "schema_version": "2.0"})
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(NUM_THREADS)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors, f"Thread errors: {errors}"
            assert not (mock_global_bees_dir / "config.json").exists()
        finally:
            set_test_config_override(None)


# ============================================================================
# TestValidateChildTiersCap
# ============================================================================


class TestValidateChildTiersCap:
    """Tests for the T9 depth cap enforced by validate_child_tiers."""

    @pytest.mark.parametrize(
        "child_tiers",
        [
            pytest.param(
                {"t1": ChildTierConfig("Epic", "Epics")},
                id="t1_only",
            ),
            pytest.param(
                {f"t{i}": ChildTierConfig(f"Tier{i}", f"Tier{i}s") for i in range(1, 6)},
                id="t1_through_t5",
            ),
            pytest.param(
                {f"t{i}": ChildTierConfig(f"Tier{i}", f"Tier{i}s") for i in range(1, 10)},
                id="t1_through_t9_max",
            ),
        ],
    )
    def test_valid_tiers_within_cap(self, child_tiers):
        """validate_child_tiers does not raise for tiers t1–t9."""
        validate_child_tiers(child_tiers)  # must not raise

    @pytest.mark.parametrize(
        "child_tiers,bad_key",
        [
            pytest.param(
                {"t10": ChildTierConfig("Leaf", "Leaves")},
                "t10",
                id="t10_alone_exceeds_cap",
            ),
            pytest.param(
                {
                    **{f"t{i}": ChildTierConfig(f"Tier{i}", f"Tier{i}s") for i in range(1, 10)},
                    "t10": ChildTierConfig("Deep", "Deeps"),
                },
                "t10",
                id="t1_through_t10_exceeds_cap",
            ),
            pytest.param(
                {"t15": ChildTierConfig("Way", "Ways")},
                "t15",
                id="t15_far_exceeds_cap",
            ),
        ],
    )
    def test_invalid_tiers_exceed_cap(self, child_tiers, bad_key):
        """validate_child_tiers raises ValueError for tier keys beyond t9."""
        with pytest.raises(ValueError, match=r"t(10|15)|T9|exceeds maximum"):
            validate_child_tiers(child_tiers)
