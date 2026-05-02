"""Unit tests for configuration system (loading, parsing, validation, persistence)."""

import json
import os
from pathlib import Path

import pytest

from src.config import (
    GLOBAL_SCHEMA_VERSION,
    BeesConfig,
    ChildTierConfig,
    ConflictRecord,
    HiveConfig,
    canonicalize_scope_pattern,
    check_scope_conflict,
    compute_scope_specificity,
    detect_hive_conflicts,
    find_all_matching_scopes,
    find_matching_scope,
    get_scoped_config,
    load_bees_config,
    load_global_config,
    match_scope_pattern,
    parse_scope_to_bees_config,
    resolve_child_tiers_for_hive,
    save_bees_config,
    save_global_config,
    scopes_overlap,
    serialize_bees_config_to_scope,
    set_config_path,
    set_test_config_override,
    validate_child_tiers,
    validate_scope_pattern,
)
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_scoped_config
from tests.test_constants import (
    SCOPE_PATTERN_BARE,
    SCOPE_PATTERN_DEEP,
    SCOPE_PATTERN_EXACT,
    SCOPE_PATTERN_EXACT_CHILD,
    SCOPE_PATTERN_SHALLOW,
    SCOPE_PATTERN_WILDCARD_PARENT,
)

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

    @pytest.mark.parametrize(
        "repo_root,pattern,expected",
        [
            # Terminal /* requires exactly one non-empty segment
            pytest.param("/repos/project/worktree", "/repos/project/*", True, id="terminal_slash_star_one_segment"),
            pytest.param("/repos/project", "/repos/project/*", False, id="terminal_slash_star_no_segment"),
            pytest.param("/repos/project/a/b", "/repos/project/*", False, id="terminal_slash_star_two_levels"),
            # Trailing-slash exact form matches repo path with or without trailing slash
            pytest.param("/repos/project", "/repos/project/", True, id="trailing_slash_exact_no_slash"),
            pytest.param("/repos/project/sub", "/repos/project/", False, id="trailing_slash_exact_no_child"),
        ],
    )
    def test_match_scope_pattern_new_forms(self, repo_root, pattern, expected):
        from src.config import _SCOPE_PATTERN_CACHE
        _SCOPE_PATTERN_CACHE.clear()
        assert match_scope_pattern(Path(repo_root), pattern) == expected

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

    def test_highest_specificity_wins(self, mock_global_bees_dir):
        """More-specific pattern wins even when listed second."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/repos/**": {"hives": {"general": {}}},
                "/repos/project/": {"hives": {"specific": {}}},
            },
        )
        config = load_global_config()
        result = find_matching_scope(Path("/repos/project"), config)
        assert result == "/repos/project/"

    def test_tie_breaks_on_dict_insertion_order(self, mock_global_bees_dir):
        """When two patterns have equal specificity, first in dict order wins."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/repos/project/**": {"hives": {"first": {}}},
                "/repos/another/**": {"hives": {"second": {}}},
            },
        )
        config = load_global_config()
        # /repos/project/** matches /repos/project/child; /repos/another/** does not
        result = find_matching_scope(Path("/repos/project/child"), config)
        assert result == "/repos/project/**"

    def test_no_match_returns_none_multi_scope(self, mock_global_bees_dir):
        """No matching pattern returns None with multi-scope config."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/repos/alpha/": {"hives": {}},
                "/repos/beta/**": {"hives": {}},
            },
        )
        config = load_global_config()
        result = find_matching_scope(Path("/repos/gamma"), config)
        assert result is None

    def test_deeper_pattern_beats_shallower_wildcard(self, mock_global_bees_dir):
        """Exact trailing-slash (tier 0) beats /** (tier 2) for same depth."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                "/repos/**": {"hives": {"wildcard": {}}},
                "/repos/project/": {"hives": {"exact": {}}},
                "/repos/project/**": {"hives": {"deep": {}}},
            },
        )
        config = load_global_config()
        # /repos/project/ and /repos/project/** both match /repos/project
        # /repos/project/ has tier 0 (exact) vs /repos/project/** tier 2 (**)
        # Exact form is more specific, so trailing-slash wins
        result = find_matching_scope(Path("/repos/project"), config)
        assert result == "/repos/project/"


class TestFindAllMatchingScopes:
    """Test find_all_matching_scopes for multi-scope resolution."""

    def test_single_scope_match(self, mock_global_bees_dir):
        """Single matching scope returns a list of one item."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {SCOPE_PATTERN_EXACT_CHILD: {"hives": {"specific": {}}}},
        )
        config = load_global_config()
        result = find_all_matching_scopes(Path("/Users/dev/projects/bees"), config)
        assert len(result) == 1
        assert result[0][0] == SCOPE_PATTERN_EXACT_CHILD

    def test_multiple_scopes_ordered_least_to_most_specific(self, mock_global_bees_dir):
        """Wildcard parent + exact child both match; ordered least→most specific."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_WILDCARD_PARENT: {"hives": {"general": {}}},
                SCOPE_PATTERN_EXACT_CHILD: {"hives": {"specific": {}}},
            },
        )
        config = load_global_config()
        result = find_all_matching_scopes(Path("/Users/dev/projects/bees"), config)
        assert len(result) == 2
        assert result[0][0] == SCOPE_PATTERN_WILDCARD_PARENT
        assert result[1][0] == SCOPE_PATTERN_EXACT_CHILD

    def test_no_scopes_match(self, mock_global_bees_dir):
        """No matching pattern returns empty list."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {"/other/path/": {"hives": {}}},
        )
        config = load_global_config()
        result = find_all_matching_scopes(Path("/Users/dev/projects/bees"), config)
        assert result == []

    def test_empty_scopes_dict(self):
        """Empty scopes dict returns empty list."""
        result = find_all_matching_scopes(Path("/any/path"), {"scopes": {}})
        assert result == []

    def test_missing_scopes_key(self):
        """Missing scopes key returns empty list."""
        result = find_all_matching_scopes(Path("/any/path"), {})
        assert result == []

    def test_wildcard_before_exact(self, mock_global_bees_dir):
        """Wildcard scope appears before exact scope in results (ascending specificity)."""
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_EXACT_CHILD: {"hives": {"exact": {}}},
                SCOPE_PATTERN_WILDCARD_PARENT: {"hives": {"wildcard": {}}},
            },
        )
        config = load_global_config()
        result = find_all_matching_scopes(Path("/Users/dev/projects/bees"), config)
        assert len(result) == 2
        # Wildcard (less specific) first, exact (more specific) second
        assert result[0][0] == SCOPE_PATTERN_WILDCARD_PARENT
        assert result[1][0] == SCOPE_PATTERN_EXACT_CHILD


# ============================================================================
# GLOBAL CONFIG TESTS
# ============================================================================


class TestLoadGlobalConfig:
    """Test load_global_config for reading ~/.bees/config.json."""

    def test_missing_file_returns_default(self, mock_global_bees_dir):
        config = load_global_config()
        assert config == {"scopes": {}, "schema_version": GLOBAL_SCHEMA_VERSION}

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
        assert config == {"scopes": {}, "schema_version": GLOBAL_SCHEMA_VERSION}
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

    def test_merges_hives_from_parent_and_child_scopes(self, mock_global_bees_dir):
        """Hive in a parent wildcard scope is visible alongside hives in the child scope.

        This is the core regression test for the multi-scope fix: a hive registered
        under /Users/dev/projects/** must be visible when the repo root matches the
        more-specific /Users/dev/projects/bees/ scope.
        """
        repo_root = Path("/Users/dev/projects/bees")
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_WILDCARD_PARENT: {
                    "hives": {"bugs": {"path": "/bugs", "display_name": "Bugs", "created_at": TS}},
                },
                SCOPE_PATTERN_EXACT_CHILD: {
                    "hives": {"backend": {"path": "/backend", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                },
            },
        )
        config = get_scoped_config(repo_root)
        assert config is not None
        assert "bugs" in config.hives, "parent-scope hive must be visible"
        assert "backend" in config.hives, "child-scope hive must be visible"

    def test_most_specific_scope_wins_hive_conflict(self, mock_global_bees_dir):
        """When the same hive name appears in both parent and child scopes, child wins."""
        repo_root = Path("/Users/dev/projects/bees")
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_WILDCARD_PARENT: {
                    "hives": {"shared": {"path": "/parent/shared", "display_name": "Shared-Parent", "created_at": TS}},
                },
                SCOPE_PATTERN_EXACT_CHILD: {
                    "hives": {"shared": {"path": "/child/shared", "display_name": "Shared-Child", "created_at": TS}},
                },
            },
        )
        config = get_scoped_config(repo_root)
        assert config is not None
        assert config.hives["shared"].path == "/child/shared"

    def test_non_hive_settings_come_from_most_specific_scope(self, mock_global_bees_dir):
        """child_tiers and other non-hive settings are taken from the most-specific scope."""
        repo_root = Path("/Users/dev/projects/bees")
        write_multi_scope_config(
            mock_global_bees_dir,
            {
                SCOPE_PATTERN_WILDCARD_PARENT: {
                    "hives": {"bugs": {"path": "/bugs", "display_name": "Bugs", "created_at": TS}},
                    "child_tiers": {"t1": ["Story", "Stories"]},
                },
                SCOPE_PATTERN_EXACT_CHILD: {
                    "hives": {"backend": {"path": "/backend", "display_name": "Backend", "created_at": TS}},
                    "child_tiers": {"t1": ["Task", "Tasks"]},
                },
            },
        )
        config = get_scoped_config(repo_root)
        assert config is not None
        assert config.child_tiers is not None
        assert config.child_tiers["t1"].singular == "Task"


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
        save_bees_config(config, str(tmp_path))

        loaded = load_bees_config()
        assert loaded is not None
        assert "backend" in loaded.hives

    def test_save_raises_when_no_matching_scope(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="not found in global config"):
            save_bees_config(BeesConfig(), "/nonexistent/scope")

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch, mock_global_bees_dir):
        monkeypatch.chdir(tmp_path)
        scope_data = {"hives": {}, "child_tiers": {}}
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        timestamp = "2026-02-01T15:30:45.678901"
        original = BeesConfig(
            hives={"backend": HiveConfig(path="/path/to/hive", display_name="Backend", created_at=timestamp)},
            child_tiers={"t1": ChildTierConfig("Task", "Tasks")},
        )
        save_bees_config(original, str(tmp_path))
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

        save_bees_config(BeesConfig(hives={"backend": _make_hive()}), str(tmp_path))

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
                save_bees_config(BeesConfig(hives={}), str(tmp_path))

        assert (mock_global_bees_dir / "config.json").read_text() == original_content


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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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
        save_bees_config(config, str(tmp_path))

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


# ============================================================================
# SCOPE PATTERN HELPER FUNCTION TESTS
# ============================================================================


class TestCanonicalizeScopePattern:
    """Test canonicalize_scope_pattern normalizes scope pattern strings."""

    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param(SCOPE_PATTERN_BARE, SCOPE_PATTERN_EXACT, id="bare_path_gets_trailing_slash"),
            pytest.param(SCOPE_PATTERN_EXACT, SCOPE_PATTERN_EXACT, id="trailing_slash_unchanged"),
            pytest.param(SCOPE_PATTERN_SHALLOW, SCOPE_PATTERN_SHALLOW, id="shallow_star_unchanged"),
            pytest.param(SCOPE_PATTERN_DEEP, SCOPE_PATTERN_DEEP, id="deep_doublestar_unchanged"),
            pytest.param("/foo", "/foo/", id="short_bare_path"),
            pytest.param("/foo/", "/foo/", id="short_trailing_slash"),
            pytest.param("/foo/*", "/foo/*", id="short_shallow"),
            pytest.param("/foo/**", "/foo/**", id="short_deep"),
        ],
    )
    def test_canonicalize(self, pattern, expected):
        assert canonicalize_scope_pattern(pattern) == expected


class TestValidateScopePattern:
    """Test validate_scope_pattern accepts valid forms and rejects mid-path wildcards."""

    @pytest.mark.parametrize(
        "pattern",
        [
            pytest.param(SCOPE_PATTERN_BARE, id="bare_path"),
            pytest.param(SCOPE_PATTERN_EXACT, id="trailing_slash"),
            pytest.param(SCOPE_PATTERN_SHALLOW, id="shallow_star"),
            pytest.param(SCOPE_PATTERN_DEEP, id="deep_doublestar"),
            pytest.param("/single/**", id="single_segment_deep"),
        ],
    )
    def test_valid_patterns_do_not_raise(self, pattern):
        validate_scope_pattern(pattern)  # must not raise

    @pytest.mark.parametrize(
        "pattern",
        [
            pytest.param("/foo/*/bar", id="mid_path_wildcard"),
            pytest.param("/foo/*/bar/**", id="mid_path_wildcard_with_terminal"),
            pytest.param("/a/*/b/c", id="mid_path_three_segments"),
        ],
    )
    def test_invalid_patterns_raise_value_error(self, pattern):
        with pytest.raises(ValueError, match="wildcards"):
            validate_scope_pattern(pattern)


class TestComputeScopeSpecificity:
    """Test compute_scope_specificity returns correct (segment_count, wildcard_tier) tuples."""

    @pytest.mark.parametrize(
        "pattern,expected",
        [
            pytest.param(SCOPE_PATTERN_EXACT, (2, 0), id="trailing_slash_exact"),
            pytest.param(SCOPE_PATTERN_BARE, (2, 0), id="bare_path_exact_tier"),
            pytest.param(SCOPE_PATTERN_SHALLOW, (2, 1), id="shallow_star"),
            pytest.param(SCOPE_PATTERN_DEEP, (2, 2), id="deep_doublestar"),
            pytest.param("/foo/", (1, 0), id="one_segment_exact"),
            pytest.param("/foo/*", (1, 1), id="one_segment_shallow"),
            pytest.param("/foo/**", (1, 2), id="one_segment_deep"),
            pytest.param("/a/b/c/", (3, 0), id="three_segment_exact"),
            pytest.param("/a/b/c/**", (3, 2), id="three_segment_deep"),
        ],
    )
    def test_specificity(self, pattern, expected):
        assert compute_scope_specificity(pattern) == expected

    def test_shallow_beats_deep_same_prefix(self):
        """Lower wildcard tier is more specific: /* (tier 1) outranks /** (tier 2)."""
        seg_s, tier_s = compute_scope_specificity(SCOPE_PATTERN_SHALLOW)
        seg_d, tier_d = compute_scope_specificity(SCOPE_PATTERN_DEEP)
        # When negating wildcard_tier for ranking: (2, -1) > (2, -2)
        assert (seg_s, -tier_s) > (seg_d, -tier_d)

    def test_exact_beats_shallow_same_prefix(self):
        """Lower wildcard tier is more specific: exact (tier 0) outranks /* (tier 1)."""
        seg_e, tier_e = compute_scope_specificity(SCOPE_PATTERN_EXACT)
        seg_s, tier_s = compute_scope_specificity(SCOPE_PATTERN_SHALLOW)
        # When negating wildcard_tier for ranking: (2, 0) > (2, -1)
        assert (seg_e, -tier_e) > (seg_s, -tier_s)

    def test_more_segments_beats_fewer_same_tier(self):
        """Three-segment exact beats two-segment exact."""
        assert compute_scope_specificity("/a/b/c/") > compute_scope_specificity("/a/b/")


class TestScopesOverlap:
    """Test scopes_overlap detects patterns that can match the same repo path."""

    @pytest.mark.parametrize(
        "pattern_a,pattern_b,expected",
        [
            # Exact patterns at different depths do not overlap
            pytest.param(
                "/repos/project/",
                "/repos/project/worktree/",
                False,
                id="exact_vs_child_exact",
            ),
            # /* reaches exactly one level deeper
            pytest.param(
                "/repos/project/*",
                "/repos/project/worktree/",
                True,
                id="shallow_star_vs_one_level_child",
            ),
            # /* does NOT reach two levels deeper
            pytest.param(
                "/repos/project/*",
                "/repos/project/a/b/",
                False,
                id="shallow_star_vs_two_levels",
            ),
            # /** reaches any depth
            pytest.param(
                SCOPE_PATTERN_DEEP,
                "/repos/project/a/b/c/",
                True,
                id="deep_doublestar_vs_deep_child",
            ),
            # Non-overlapping paths
            pytest.param(
                "/repos/project/",
                "/repos/other/",
                False,
                id="different_paths_no_overlap",
            ),
            # Same canonical pattern always overlaps
            pytest.param(
                SCOPE_PATTERN_EXACT,
                SCOPE_PATTERN_BARE,
                True,
                id="same_effective_pattern_overlaps",
            ),
            # /** ancestor overlaps with /* child
            pytest.param(
                "/repos/**",
                "/repos/project/*",
                True,
                id="deep_ancestor_vs_shallow_child",
            ),
        ],
    )
    def test_overlap(self, pattern_a, pattern_b, expected):
        assert scopes_overlap(pattern_a, pattern_b) == expected


class TestCheckScopeConflict:
    """Test check_scope_conflict detects patterns with the same bare prefix and wildcard tier.

    Note: In practice, "same bare prefix + same wildcard tier" always produces the same
    canonical form, so the conflict branch (step 5 in check_scope_conflict) is unreachable
    with valid inputs — step 4 (canonical equality → re-use is valid → return None) always
    fires first. The function is correct: re-using an existing scope is not an error. All
    tests below return None because any candidate that would conflict is indistinguishable
    from a re-use at the canonical level.
    """

    def test_identical_canonical_pattern_returns_none(self):
        """Exact canonical match is not a conflict — it means re-use."""
        config = {"scopes": {SCOPE_PATTERN_SHALLOW: {"hives": {}}}}
        # Same pattern (identical canonical) → None
        assert check_scope_conflict(SCOPE_PATTERN_SHALLOW, config) is None

    def test_bare_and_trailing_slash_same_canonical_no_conflict(self):
        """Bare path and trailing-slash form are the same canonical key."""
        config = {"scopes": {SCOPE_PATTERN_EXACT: {"hives": {}}}}
        # /repos/project canonicalizes to /repos/project/ — identical → None
        assert check_scope_conflict(SCOPE_PATTERN_BARE, config) is None

    @pytest.mark.parametrize(
        "candidate,existing,expected_conflict",
        [
            pytest.param(
                "/repos/project/other/*",
                "/repos/project/alt/*",
                None,
                id="different_bare_prefix_same_tier_no_conflict",
            ),
            pytest.param(
                "/repos/project/*",
                "/repos/project/*",
                None,
                id="same_prefix_same_tier_exact_canonical_no_conflict",
            ),
            pytest.param(
                "/repos/project/*",
                "/repos/project/**",
                None,
                id="same_prefix_different_tier_no_conflict",
            ),
            pytest.param(
                "/repos/project/worktree/*",
                "/repos/project/**",
                None,
                id="different_segment_count_no_conflict",
            ),
        ],
    )
    def test_conflict_cases(self, candidate, existing, expected_conflict):
        config = {"scopes": {existing: {"hives": {}}}}
        assert check_scope_conflict(candidate, config) == expected_conflict

    def test_empty_scopes_returns_none(self):
        assert check_scope_conflict("/repos/project/*", {"scopes": {}}) is None

    def test_missing_scopes_key_returns_none(self):
        assert check_scope_conflict("/repos/project/*", {}) is None


class TestDetectHiveConflicts:
    """Test detect_hive_conflicts identifies duplicate hive names across overlapping scopes.

    Uses find_all_matching_scopes output format: list of (scope_pattern, BeesConfig) tuples.
    Critical: non-overlapping scopes must NOT produce false positives.
    """

    def _make_matching_scopes(self, scope_hive_map: dict[str, list[str]]) -> list[tuple[str, BeesConfig]]:
        """Build find_all_matching_scopes-style output from {scope_pattern: [hive_names]}."""
        result = []
        for pattern, hive_names in scope_hive_map.items():
            hives = {name: _make_hive(display_name=name.title()) for name in hive_names}
            config = BeesConfig(hives=hives)
            result.append((pattern, config))
        return result

    def test_same_hive_in_overlapping_scopes_returns_conflict(self):
        """Same hive name in two matching scopes → ConflictRecord returned."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend"],
            SCOPE_PATTERN_EXACT_CHILD: ["backend"],
        })
        conflicts = detect_hive_conflicts(matching)
        assert len(conflicts) == 1
        assert conflicts[0].normalized_hive_name == "backend"
        assert {conflicts[0].scope_a, conflicts[0].scope_b} == {
            SCOPE_PATTERN_WILDCARD_PARENT,
            SCOPE_PATTERN_EXACT_CHILD,
        }

    def test_same_hive_in_non_overlapping_scopes_returns_empty(self):
        """Same hive name in non-overlapping scopes → empty list (no false positive)."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_DEEP: ["backend"],
        })
        # Only one scope matches → no conflict possible
        conflicts = detect_hive_conflicts(matching)
        assert conflicts == []

    def test_different_hive_names_across_scopes_returns_empty(self):
        """Different hive names across scopes → empty list."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend"],
            SCOPE_PATTERN_EXACT_CHILD: ["frontend"],
        })
        conflicts = detect_hive_conflicts(matching)
        assert conflicts == []

    def test_multiple_conflicting_hives_all_captured(self):
        """Multiple hive names each in multiple scopes → all conflicts captured."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend", "frontend"],
            SCOPE_PATTERN_EXACT_CHILD: ["backend", "frontend"],
        })
        conflicts = detect_hive_conflicts(matching)
        conflict_names = sorted(c.normalized_hive_name for c in conflicts)
        assert conflict_names == ["backend", "frontend"]
        assert len(conflicts) == 2

    def test_empty_input_returns_empty(self):
        """Empty matching_scopes list → empty list."""
        conflicts = detect_hive_conflicts([])
        assert conflicts == []

    def test_single_scope_no_conflict(self):
        """A single scope with multiple hives never conflicts with itself."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend", "frontend", "api"],
        })
        conflicts = detect_hive_conflicts(matching)
        assert conflicts == []

    def test_conflict_record_fields(self):
        """ConflictRecord contains the expected fields."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend"],
            SCOPE_PATTERN_EXACT_CHILD: ["backend"],
        })
        conflicts = detect_hive_conflicts(matching)
        assert len(conflicts) == 1
        record = conflicts[0]
        assert isinstance(record, ConflictRecord)
        assert record.normalized_hive_name == "backend"
        assert record.scope_a in (SCOPE_PATTERN_WILDCARD_PARENT, SCOPE_PATTERN_EXACT_CHILD)
        assert record.scope_b in (SCOPE_PATTERN_WILDCARD_PARENT, SCOPE_PATTERN_EXACT_CHILD)
        assert record.scope_a != record.scope_b

    def test_three_scopes_same_hive_produces_three_pairs(self):
        """Three scopes with same hive → C(3,2) = 3 ConflictRecords."""
        matching = self._make_matching_scopes({
            SCOPE_PATTERN_WILDCARD_PARENT: ["backend"],
            SCOPE_PATTERN_EXACT_CHILD: ["backend"],
            SCOPE_PATTERN_DEEP: ["backend"],
        })
        conflicts = detect_hive_conflicts(matching)
        assert len(conflicts) == 3
        assert all(c.normalized_hive_name == "backend" for c in conflicts)
