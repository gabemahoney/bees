"""Unit tests for ticket path resolution and filesystem utilities."""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.cache
from src.config import ConfigLoadError
from src.id_utils import is_ticket_id
from src.mcp_id_utils import parse_ticket_id, parse_type_from_ticket_id
from src.parser import parse_frontmatter as real_parse_frontmatter
from src.paths import (
    build_ticket_path_map,
    compute_ticket_directory,
    ensure_ticket_directory_exists,
    find_enclosing_hive_root,
    find_foreign_subtrees,
    find_nested_hive_root,
    find_ticket_file,
    get_ticket_path,
    hive_crossing_reason,
    infer_ticket_type_from_id,
    iter_ticket_files,
    iter_ticket_files_deep,
    list_tickets,
    walk_hive,
)
from src.reader import get_ticket_type
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_scoped_config
from tests.helpers import backdate, write_ticket_file
from src.paths import compute_ticket_path as _compute_ticket_path
from tests.test_constants import (
    TICKET_ID_ABC,
    TICKET_ID_CASE_AMX_LOWER,
    TICKET_ID_EP1,
    TICKET_ID_LEGACY_BEE,
    TICKET_ID_LEGACY_TASK,
    TICKET_ID_LINTER_SUBTASK_MAIN,
    TICKET_ID_LINTER_TASK_MAIN,
    TICKET_ID_LINTER_TIER1,
    TICKET_ID_LINTER_VALID,
    TICKET_ID_PATH_BAD_YAML,
    TICKET_ID_PATH_NO_TYPE,
    TICKET_ID_PATH_NO_VERSION,
    TICKET_ID_T1,
    TICKET_ID_T2,
    TICKET_ID_VALID_T1_R8P2,
    TICKET_ID_VALID_T3_CAPS,
)


class TestParseTicketId:
    """Tests for parse_ticket_id function from mcp_id_utils."""

    @pytest.mark.parametrize(
        "ticket_id,expected_prefix,expected_short_id",
        [
            pytest.param(TICKET_ID_CASE_AMX_LOWER, "b", "amx", id="bee"),
            pytest.param(TICKET_ID_VALID_T1_R8P2, "t1", "r8p.2a", id="t1"),
            pytest.param(TICKET_ID_T2, "t2", "abc.de.fg", id="t2"),
            pytest.param(TICKET_ID_VALID_T3_CAPS, "t3", "x4f.2a.bc.de", id="t3"),
            pytest.param("t10.abc.de.fg.hi.jk.mn.pq.rs.tu.vw.xy", "t10", "abc.de.fg.hi.jk.mn.pq.rs.tu.vw.xy", id="t10"),
        ],
    )
    def test_parse_valid_ids(self, ticket_id, expected_prefix, expected_short_id):
        """Should parse new format ticket IDs correctly."""
        type_prefix, short_id = parse_ticket_id(ticket_id)
        assert type_prefix == expected_prefix
        assert short_id == expected_short_id

    @pytest.mark.parametrize(
        "ticket_id,expected_error",
        [
            pytest.param(None, "ticket_id cannot be None", id="none"),
            pytest.param("", "ticket_id cannot be empty", id="empty_string"),
            pytest.param("   ", "ticket_id cannot be empty", id="whitespace_only"),
            pytest.param("no_dot", "Invalid ticket_id format.*Expected format", id="no_dot"),
            pytest.param("b.", "Both prefix and shortID required", id="empty_short_id"),
            pytest.param(".Amx", "Both prefix and shortID required", id="empty_prefix"),
        ],
    )
    def test_parse_invalid_ids(self, ticket_id, expected_error):
        """Should raise ValueError for invalid IDs."""
        with pytest.raises(ValueError, match=expected_error):
            parse_ticket_id(ticket_id)  # type: ignore


class TestParseTypeFromTicketId:
    """Tests for parse_type_from_ticket_id function."""

    @pytest.mark.parametrize(
        "ticket_id,expected_type",
        [
            pytest.param(TICKET_ID_CASE_AMX_LOWER, "bee", id="bee"),
            pytest.param(TICKET_ID_VALID_T1_R8P2, "t1", id="t1"),
            pytest.param(TICKET_ID_T2, "t2", id="t2"),
            pytest.param(TICKET_ID_VALID_T3_CAPS, "t3", id="t3"),
            pytest.param("t10.abc.de.fg.hi.jk.mn.pq.rs.tu.vw.xy", "t10", id="t10"),
        ],
    )
    def test_parse_type(self, ticket_id, expected_type):
        """Should extract ticket type from ID."""
        ticket_type = parse_type_from_ticket_id(ticket_id)
        assert ticket_type == expected_type


class TestGetTicketPath:
    """Tests for get_ticket_path function with hierarchical storage."""

    @pytest.mark.parametrize(
        "ticket_id,ticket_type,error_match",
        [
            pytest.param("", "bee", "ticket_id cannot be empty", id="empty_id"),
        ],
    )
    def test_rejects_invalid_ids(self, multi_hive_config, ticket_id, ticket_type, error_match):
        """Should reject empty ticket IDs."""
        with pytest.raises(ValueError, match=error_match):
            get_ticket_path(ticket_id, ticket_type, "backend")

    def test_finds_bee_at_root(self, multi_hive_config):
        """Should find bee ticket in hierarchical directory at hive root."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create hierarchical structure: {ticket_id}/{ticket_id}.md
        ticket_dir = backend_dir / TICKET_ID_ABC
        ticket_dir.mkdir(parents=True)
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"
        ticket_file.write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        path = get_ticket_path(TICKET_ID_ABC, "bee", "backend")
        assert path == ticket_file

    def test_finds_child_ticket_nested_under_parent(self, multi_hive_config):
        """Should find child ticket in hierarchical directory nested under parent."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create hierarchical structure: {parent_id}/{child_id}/{child_id}.md
        # Use TICKET_ID_T1 (t1.abc.de) which encodes parent b.abc in its ID
        parent_dir = backend_dir / TICKET_ID_ABC
        parent_dir.mkdir(parents=True)
        (parent_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        child_dir = parent_dir / TICKET_ID_T1
        child_dir.mkdir(parents=True)
        child_file = child_dir / f"{TICKET_ID_T1}.md"
        child_file.write_text(f"---\nschema_version: 1.1\ntype: t1\nparent: {TICKET_ID_ABC}\n---\n")

        path = get_ticket_path(TICKET_ID_T1, "task", "backend")
        assert path == child_file

    def test_excludes_tickets_in_eggs_directory(self, multi_hive_config):
        """Should exclude tickets in eggs/ special directory from search."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create ticket in eggs directory (should be excluded)
        eggs_dir = backend_dir / "eggs" / TICKET_ID_ABC
        eggs_dir.mkdir(parents=True)
        (eggs_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path(TICKET_ID_ABC, "bee", "backend")

    def test_excludes_tickets_in_evicted_directory(self, multi_hive_config):
        """Should exclude tickets in evicted/ special directory from search."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create ticket in evicted directory (should be excluded)
        evicted_dir = backend_dir / "evicted" / TICKET_ID_ABC
        evicted_dir.mkdir(parents=True)
        (evicted_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path(TICKET_ID_ABC, "bee", "backend")

    def test_excludes_tickets_in_cemetery_directory(self, multi_hive_config):
        """Should exclude tickets in cemetery/ special directory from search."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create ticket in cemetery directory (should be excluded)
        cemetery_dir = backend_dir / "cemetery" / TICKET_ID_ABC
        cemetery_dir.mkdir(parents=True)
        (cemetery_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path(TICKET_ID_ABC, "bee", "backend")

    def test_excludes_tickets_in_hive_directory(self, multi_hive_config):
        """Should exclude tickets in .hive/ special directory from search."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create ticket in .hive directory (should be excluded)
        hive_meta_dir = backend_dir / ".hive" / TICKET_ID_ABC
        hive_meta_dir.mkdir(parents=True)
        (hive_meta_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path(TICKET_ID_ABC, "bee", "backend")

    def test_validates_hierarchical_pattern(self, multi_hive_config):
        """Should only match files where directory name equals ticket ID."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create file with wrong directory name (not hierarchical pattern)
        wrong_dir = backend_dir / "wrong_name"
        wrong_dir.mkdir(parents=True)
        (wrong_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path(TICKET_ID_ABC, "bee", "backend")

    def test_raises_not_found_for_nonexistent_ticket(self, multi_hive_config):
        """Should raise FileNotFoundError if ticket doesn't exist."""
        with pytest.raises(FileNotFoundError, match="not found in hive"):
            get_ticket_path("b.Nonexistent", "bee", "backend")


class TestComputeTicketDirectory:
    """Tests for compute_ticket_directory function for new ticket creation."""

    def test_rejects_empty_ticket_id(self, multi_hive_config):
        """Should reject empty ticket ID."""
        with pytest.raises(ValueError, match="ticket_id cannot be empty"):
            compute_ticket_directory("", None, "backend")

    def test_rejects_empty_hive_name(self, multi_hive_config):
        """Should reject empty hive name."""
        with pytest.raises(ValueError, match="hive_name cannot be empty"):
            compute_ticket_directory(TICKET_ID_ABC, None, "")

    def test_bee_directory_at_hive_root(self, multi_hive_config):
        """Should compute bee directory at hive root level."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Bee with no parent should be at hive root
        ticket_dir = compute_ticket_directory(TICKET_ID_ABC, None, "backend")
        assert ticket_dir == backend_dir / TICKET_ID_ABC

    def test_child_directory_nested_under_parent(self, multi_hive_config):
        """Should compute child directory nested under parent directory."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create parent bee directory structure
        parent_dir = backend_dir / TICKET_ID_ABC
        parent_dir.mkdir(parents=True)
        parent_file = parent_dir / f"{TICKET_ID_ABC}.md"
        parent_file.write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        # Child should be nested under parent
        child_dir = compute_ticket_directory(TICKET_ID_LINTER_TASK_MAIN, TICKET_ID_ABC, "backend")
        assert child_dir == parent_dir / TICKET_ID_LINTER_TASK_MAIN

    def test_grandchild_directory_deeply_nested(self, multi_hive_config):
        """Should compute grandchild directory deeply nested under parent chain."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir = hive_paths[0]

        # Create parent bee: b.abc
        parent_dir = backend_dir / TICKET_ID_ABC
        parent_dir.mkdir(parents=True)
        (parent_dir / f"{TICKET_ID_ABC}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        # Create child task: t1.abc.de (encodes parent b.abc)
        child_dir = parent_dir / TICKET_ID_T1
        child_dir.mkdir(parents=True)
        (child_dir / f"{TICKET_ID_T1}.md").write_text(f"---\nschema_version: 1.1\ntype: t1\nparent: {TICKET_ID_ABC}\n---\n")

        # Grandchild t2.abc.de.fg should be nested under child t1.abc.de
        grandchild_dir = compute_ticket_directory(TICKET_ID_T2, TICKET_ID_T1, "backend")
        assert grandchild_dir == child_dir / TICKET_ID_T2

    def test_raises_error_if_parent_not_found(self, multi_hive_config):
        """Should raise FileNotFoundError if parent ticket doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Parent ticket.*not found"):
            compute_ticket_directory(TICKET_ID_LINTER_TASK_MAIN, "b.Nonexistent", "backend")

    def test_raises_error_if_hive_not_in_config(self, multi_hive_config):
        """Should raise ValueError if hive not found in config."""
        with pytest.raises(ValueError, match="not found in config"):
            compute_ticket_directory(TICKET_ID_ABC, None, "nonexistent_hive")


class TestEnsureTicketDirectoryExists:
    """Tests for ensure_ticket_directory_exists function."""

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        """Should create hive root directory if it doesn't exist."""
        monkeypatch.chdir(tmp_path)
        hive_dir = tmp_path / "backend"
        assert not hive_dir.exists()
        ensure_ticket_directory_exists("backend")
        assert hive_dir.exists()
        assert hive_dir.is_dir()

    def test_no_error_if_directory_exists(self, tmp_path, monkeypatch):
        """Should not raise error if directory already exists."""
        monkeypatch.chdir(tmp_path)
        hive_dir = tmp_path / "backend"
        hive_dir.mkdir(parents=True)
        ensure_ticket_directory_exists("backend")
        assert hive_dir.exists()

    def test_invalid_hive_name_raises_error(self):
        """Should raise ValueError for empty hive name."""
        with pytest.raises(ValueError, match="hive_name is required"):
            ensure_ticket_directory_exists("")


class TestListTickets:
    """Tests for list_tickets function with hierarchical storage."""

    def test_list_epic_tickets_returns_empty_without_hives(self, tmp_path, monkeypatch):
        """Should return empty list when no hives configured."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            assert list_tickets("bee") == []

    def test_empty_directory(self, hive_env):
        """Should return empty list for empty hive directory."""
        repo_root, hive_path, hive_name = hive_env
        assert list_tickets("bee") == []

    def test_nonexistent_directory(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should return empty list when hive path doesn't exist."""
        monkeypatch.chdir(tmp_path)
        scope_data = {
            "hives": {"backend": {"path": str(tmp_path / "nonexistent"), "display_name": "Backend", "created_at": datetime.now().isoformat()}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        with repo_root_context(tmp_path):
            assert list_tickets("bee") == []

    def test_sorted_output(self, hive_env):
        """Should return tickets in sorted order with hierarchical structure."""
        repo_root, hive_path, hive_name = hive_env

        # Create hierarchical structure for each ticket
        for ticket_id in ["b.zzz", "b.aaa", "b.mmm"]:
            ticket_dir = hive_path / ticket_id
            ticket_dir.mkdir(parents=True)
            (ticket_dir / f"{ticket_id}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        tickets = list_tickets("bee")
        names = [t.name for t in tickets]
        assert names == sorted(names)

    def test_finds_tickets_recursively(self, hive_env):
        """Should find tickets at all levels of directory hierarchy."""
        repo_root, hive_path, hive_name = hive_env

        # Create bee at root
        bee_dir = hive_path / TICKET_ID_ABC
        bee_dir.mkdir(parents=True)
        (bee_dir / f"{TICKET_ID_ABC}.md").write_text(f"---\nid: {TICKET_ID_ABC}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Create child task nested under bee
        task_dir = bee_dir / TICKET_ID_LINTER_TASK_MAIN
        task_dir.mkdir(parents=True)
        (task_dir / f"{TICKET_ID_LINTER_TASK_MAIN}.md").write_text(f"---\nid: {TICKET_ID_LINTER_TASK_MAIN}\nschema_version: 1.1\ntitle: Test\ntype: t1\n---\n")

        # Create grandchild subtask deeply nested
        subtask_dir = task_dir / TICKET_ID_T2
        subtask_dir.mkdir(parents=True)
        (subtask_dir / f"{TICKET_ID_T2}.md").write_text(f"---\nid: {TICKET_ID_T2}\nschema_version: 1.1\ntitle: Test\ntype: t2\n---\n")

        # Should find all tickets regardless of nesting level
        tickets = list_tickets()
        assert len(tickets) == 3
        ticket_names = {t.name for t in tickets}
        assert f"{TICKET_ID_ABC}.md" in ticket_names
        assert f"{TICKET_ID_LINTER_TASK_MAIN}.md" in ticket_names
        assert f"{TICKET_ID_T2}.md" in ticket_names

    def test_validates_hierarchical_pattern(self, hive_env):
        """Should only include files matching hierarchical pattern {id}/{id}.md."""
        repo_root, hive_path, hive_name = hive_env

        # Valid hierarchical pattern
        valid_dir = hive_path / TICKET_ID_ABC
        valid_dir.mkdir(parents=True)
        (valid_dir / f"{TICKET_ID_ABC}.md").write_text(f"---\nid: {TICKET_ID_ABC}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Invalid: directory name doesn't match file name
        invalid_dir = hive_path / "wrong_name"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "b.Xyz.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        tickets = list_tickets()
        assert len(tickets) == 1
        assert tickets[0].name == f"{TICKET_ID_ABC}.md"

    def test_excludes_index_md_files(self, hive_env):
        """Should exclude index.md files from ticket listing."""
        repo_root, hive_path, hive_name = hive_env

        # Create valid ticket
        ticket_dir = hive_path / TICKET_ID_ABC
        ticket_dir.mkdir(parents=True)
        (ticket_dir / f"{TICKET_ID_ABC}.md").write_text(f"---\nid: {TICKET_ID_ABC}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Create index.md (should be excluded)
        (hive_path / "index.md").write_text("# Hive Index\n")

        tickets = list_tickets()
        assert len(tickets) == 1
        assert tickets[0].name == f"{TICKET_ID_ABC}.md"


class TestInferTicketTypeFromId:
    """Tests for infer_ticket_type_from_id function."""

    @pytest.mark.parametrize(
        "ticket_id",
        [
            pytest.param(TICKET_ID_LEGACY_BEE, id="legacy_epic"),
            pytest.param(TICKET_ID_LEGACY_TASK, id="legacy_task"),
            pytest.param(TICKET_ID_ABC, id="legacy_subtask"),
        ],
    )
    def test_returns_none_for_legacy_ids(self, tmp_path, monkeypatch, ticket_id):
        """Should return None for legacy IDs without hive prefix."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            assert infer_ticket_type_from_id(ticket_id) is None

    def test_returns_none_for_nonexistent_ticket(self, tmp_path, monkeypatch):
        """Should return None for ticket ID that doesn't exist."""
        monkeypatch.chdir(tmp_path)
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)
        with repo_root_context(tmp_path):
            assert infer_ticket_type_from_id("backend.nonexistent-id") is None

    @pytest.mark.parametrize(
        "ticket_id,hive_name,expected_type,title",
        [
            pytest.param(TICKET_ID_ABC, "backend", "bee", "Test Epic", id="bee"),
            pytest.param(TICKET_ID_LINTER_TASK_MAIN, "backend", "t1", "Test Task", id="t1"),
            pytest.param(TICKET_ID_LINTER_SUBTASK_MAIN, "frontend", "t2", "Test Subtask", id="t2"),
        ],
    )
    def test_infers_type_from_yaml_frontmatter(
        self, multi_hive_config, ticket_id, hive_name, expected_type, title
    ):
        """Should infer type from YAML frontmatter in hierarchical storage."""
        repo_root, hive_paths, config_data = multi_hive_config
        backend_dir, frontend_dir = hive_paths[0], hive_paths[1]

        hive_dir = backend_dir if hive_name == "backend" else frontend_dir

        # Create file at canonical hierarchical path (compute_ticket_path-derived)
        canonical_path = _compute_ticket_path(ticket_id, hive_dir)
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        canonical_path.write_text(f"---\nid: {ticket_id}\nschema_version: 1.1\ntitle: {title}\ntype: {expected_type}\n---\n\nBody content")

        assert infer_ticket_type_from_id(ticket_id) == expected_type

    @pytest.mark.parametrize(
        "ticket_id,content,expected",
        [
            pytest.param(TICKET_ID_PATH_BAD_YAML, "---\n[invalid: yaml: content\n---\n\nBody", None, id="invalid_yaml"),
            pytest.param(TICKET_ID_PATH_NO_TYPE, "---\ntitle: Test\n---\n\nBody content", None, id="missing_type"),
            pytest.param(TICKET_ID_PATH_NO_VERSION, "---\ntype: bee\ntitle: Test\n---\n\nBody content", None, id="missing_schema_version"),
            pytest.param(TICKET_ID_LINTER_VALID, f"---\nid: {TICKET_ID_LINTER_VALID}\nschema_version: 1.1\ntitle: Test\ntype: t1\n---\n\nBody content", "t1", id="valid_with_version"),
        ],
    )
    def test_yaml_frontmatter_edge_cases(self, tmp_path, monkeypatch, mock_global_bees_dir, ticket_id, content, expected):
        """Should handle various YAML frontmatter conditions in hierarchical storage."""
        monkeypatch.chdir(tmp_path)
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True, exist_ok=True)

        # Create hierarchical directory structure
        ticket_dir = backend_dir / ticket_id
        ticket_dir.mkdir(parents=True)
        (ticket_dir / f"{ticket_id}.md").write_text(content)

        now = datetime.now().isoformat()
        scope_data = {
            "hives": {"backend": {"path": str(backend_dir), "display_name": "Backend", "created_at": now}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
        with repo_root_context(tmp_path):
            assert infer_ticket_type_from_id(ticket_id) == expected

    @pytest.mark.parametrize(
        "ticket_id",
        [pytest.param("", id="empty_id"), pytest.param(TICKET_ID_LINTER_SUBTASK_MAIN, id="legacy_no_hive")],
    )
    def test_returns_none_for_invalid_ids(self, tmp_path, monkeypatch, ticket_id):
        """Should return None for empty or legacy IDs."""
        monkeypatch.chdir(tmp_path)
        with repo_root_context(tmp_path):
            assert infer_ticket_type_from_id(ticket_id) is None


class TestListTicketsFromHives:
    """Tests for list_tickets() scanning all hives with hierarchical storage."""

    def test_list_tickets_scans_all_hives(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should scan all configured hives when listing tickets."""
        monkeypatch.chdir(tmp_path)

        backend_dir = tmp_path / "backend"
        frontend_dir = tmp_path / "frontend"
        backend_dir.mkdir(parents=True)
        frontend_dir.mkdir(parents=True)

        # Create hierarchical structures
        backend_ticket_dir = backend_dir / TICKET_ID_ABC
        backend_ticket_dir.mkdir(parents=True)
        (backend_ticket_dir / f"{TICKET_ID_ABC}.md").write_text(f"---\nid: {TICKET_ID_ABC}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        frontend_ticket_dir = frontend_dir / TICKET_ID_LINTER_TASK_MAIN
        frontend_ticket_dir.mkdir(parents=True)
        (frontend_ticket_dir / f"{TICKET_ID_LINTER_TASK_MAIN}.md").write_text(f"---\nid: {TICKET_ID_LINTER_TASK_MAIN}\nschema_version: 1.1\ntitle: Test\ntype: t1\n---\n")

        now = datetime.now().isoformat()
        scope_data = {
            "hives": {
                "backend": {"path": str(backend_dir), "display_name": "Backend", "created_at": now},
                "frontend": {"path": str(frontend_dir), "display_name": "Frontend", "created_at": now},
            },
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            tickets = list_tickets()
            assert len(tickets) == 2
            ticket_names = {t.name for t in tickets}
            assert f"{TICKET_ID_ABC}.md" in ticket_names
            assert f"{TICKET_ID_LINTER_TASK_MAIN}.md" in ticket_names

    def test_list_tickets_filters_by_schema_version(self, hive_env):
        """Should only return files with schema_version field in hierarchical storage."""
        repo_root, hive_path, hive_name = hive_env

        # Valid ticket with hierarchical structure
        valid_dir = hive_path / TICKET_ID_LINTER_VALID
        valid_dir.mkdir(parents=True)
        (valid_dir / f"{TICKET_ID_LINTER_VALID}.md").write_text(f"---\nid: {TICKET_ID_LINTER_VALID}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Invalid ticket without schema_version (in hierarchical structure)
        invalid_dir = hive_path / "b.inv"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "b.inv.md").write_text("---\ntype: bee\n---\n")

        # Non-ticket file (not in hierarchical structure)
        (hive_path / "README.md").write_text("# README\n\nJust a regular file")

        tickets = list_tickets()
        assert len(tickets) == 1
        assert tickets[0].name == f"{TICKET_ID_LINTER_VALID}.md"

    def test_list_tickets_filters_by_type_with_schema_version(self, hive_env):
        """Should filter by type and validate schema_version with hierarchical storage."""
        repo_root, hive_path, hive_name = hive_env

        # Valid bee with hierarchical structure
        bee_dir = hive_path / TICKET_ID_EP1
        bee_dir.mkdir(parents=True)
        (bee_dir / f"{TICKET_ID_EP1}.md").write_text(f"---\nid: {TICKET_ID_EP1}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Valid task with hierarchical structure
        task_dir = hive_path / TICKET_ID_LINTER_TASK_MAIN
        task_dir.mkdir(parents=True)
        (task_dir / f"{TICKET_ID_LINTER_TASK_MAIN}.md").write_text(f"---\nid: {TICKET_ID_LINTER_TASK_MAIN}\nschema_version: 1.1\ntitle: Test\ntype: t1\n---\n")

        # Invalid bee without schema_version
        invalid_dir = hive_path / "b.ep2"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "b.ep2.md").write_text("---\ntype: bee\n---\n")

        epics = list_tickets("bee")
        assert len(epics) == 1
        assert epics[0].name == f"{TICKET_ID_EP1}.md"

    @pytest.mark.parametrize("subdir_name", ["eggs", "evicted", ".hive", "cemetery"], ids=["eggs", "evicted", "hive", "cemetery"])
    def test_list_tickets_excludes_special_directories(self, hive_env, subdir_name):
        """Should exclude tickets in eggs/, evicted/, and .hive/ special directories."""
        repo_root, hive_path, hive_name = hive_env

        # Create valid ticket at root with hierarchical structure
        root_dir = hive_path / "b.root"
        root_dir.mkdir(parents=True)
        (root_dir / "b.root.md").write_text("---\nid: b.root\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        # Create ticket in excluded directory with hierarchical structure
        ticket_id = f"b.{subdir_name[0:3] if not subdir_name.startswith('.') else 'hiv'}"
        excluded_ticket_dir = hive_path / subdir_name / ticket_id
        excluded_ticket_dir.mkdir(parents=True)
        (excluded_ticket_dir / f"{ticket_id}.md").write_text("---\nschema_version: 1.1\ntype: bee\n---\n")

        tickets = list_tickets()
        assert len(tickets) == 1
        assert tickets[0].name == "b.root.md"


class TestListTicketsDynamicTypeValidation:
    """Tests for list_tickets() dynamic type validation with child_tiers config."""

    @pytest.mark.parametrize(
        "ticket_type,setup_files,expected_count",
        [
            pytest.param("bee", [(TICKET_ID_EP1, "bee")], 1, id="accepts_bee"),
            pytest.param("t1", [(TICKET_ID_LINTER_TIER1, "t1")], 1, id="accepts_t1_from_config"),
            pytest.param(None, [(TICKET_ID_EP1, "bee"), (TICKET_ID_LINTER_TIER1, "t1")], 2, id="none_lists_all"),
        ],
    )
    def test_valid_type_queries(self, hive_env, ticket_type, setup_files, expected_count):
        """Should accept valid type queries and return correct counts with hierarchical storage."""
        repo_root, hive_path, hive_name = hive_env
        for ticket_id, ftype in setup_files:
            # Create hierarchical directory structure
            ticket_dir = hive_path / ticket_id
            ticket_dir.mkdir(parents=True)
            (ticket_dir / f"{ticket_id}.md").write_text(f"---\nid: {ticket_id}\nschema_version: 1.1\ntitle: Test\ntype: {ftype}\n---\n")
        tickets = list_tickets(ticket_type)
        assert len(tickets) == expected_count

    def test_rejects_invalid_tier_type(self, hive_env):
        """Should raise ValueError for tier type not in config."""
        with pytest.raises(ValueError, match="Invalid ticket type 't3'"):
            list_tickets("t3")

    def test_descriptive_error_message(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should provide descriptive error message with valid types."""
        monkeypatch.chdir(tmp_path)
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        scope_data = {
            "hives": {"backend": {"path": str(backend_dir), "display_name": "Backend", "created_at": datetime.now().isoformat()}},
            "child_tiers": {"t1": [None, None], "t2": [None, None], "t3": [None, None]},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            with pytest.raises(ValueError, match="Valid types for this configuration: bee, t1, t2, t3"):
                list_tickets("t99")

    def test_works_with_empty_child_tiers(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Should work when child_tiers is empty (bees-only config) with hierarchical storage."""
        monkeypatch.chdir(tmp_path)
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir(parents=True)

        # Create hierarchical directory structure
        ticket_dir = backend_dir / TICKET_ID_EP1
        ticket_dir.mkdir(parents=True)
        (ticket_dir / f"{TICKET_ID_EP1}.md").write_text(f"---\nid: {TICKET_ID_EP1}\nschema_version: 1.1\ntitle: Test\ntype: bee\n---\n")

        scope_data = {
            "hives": {"backend": {"path": str(backend_dir), "display_name": "Backend", "created_at": datetime.now().isoformat()}},
            "child_tiers": {},
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        with repo_root_context(tmp_path):
            tickets = list_tickets("bee")
            assert len(tickets) == 1

            with pytest.raises(ValueError, match="Invalid ticket type 't1'"):
                list_tickets("t1")


class TestPathsCacheIntegration:
    """Cache behavior for list_tickets() and infer_ticket_type_from_id() (files backdated, so caches trust them)."""

    def test_list_tickets_cache_hit_on_second_call(self, isolated_bees_env):
        """Second list_tickets() call returns cached results without re-parsing."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        backdate(helper.create_ticket(hive_dir, "b.nc1", "bee", "List Cache Test"))

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            list_tickets()
            assert mock_parse.call_count == 1

            list_tickets()
            assert mock_parse.call_count == 1  # cache hit, no re-parse

    def test_infer_type_cache_hit_on_second_call(self, isolated_bees_env):
        """Second infer_ticket_type_from_id() call returns cached result without re-parsing."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        backdate(helper.create_ticket(hive_dir, "b.ic1", "bee", "Infer Cache Test"))

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            result1 = infer_ticket_type_from_id("b.ic1")
            assert mock_parse.call_count == 1
            assert result1 == "bee"

            result2 = infer_ticket_type_from_id("b.ic1")
            assert mock_parse.call_count == 1  # cache hit
            assert result2 == "bee"

    def test_shared_cache_list_then_infer(self, isolated_bees_env):
        """list_tickets() populates cache; infer_ticket_type_from_id() hits without re-parse."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        backdate(helper.create_ticket(hive_dir, "b.sc1", "bee", "Shared Cache Test"))

        with patch("src.reader.parse_frontmatter", wraps=real_parse_frontmatter) as mock_parse:
            tickets = list_tickets()
            assert mock_parse.call_count == 1
            assert len(tickets) == 1

            ticket_type = infer_ticket_type_from_id("b.sc1")
            assert mock_parse.call_count == 1  # shared cache hit
            assert ticket_type == "bee"


class TestGetTicketType:
    """Tests for get_ticket_type() in src/reader.py."""

    def test_cache_hit_skips_filesystem(self, isolated_bees_env):
        """Cache hit returns ticket type without scanning the filesystem."""
        helper = isolated_bees_env
        ticket_file = helper.base_path / "b.cht1.md"
        ticket_file.touch()
        mock_ticket = MagicMock()
        mock_ticket.type = "bee"
        src.cache.put("b.cht1", src.cache.file_signature(ticket_file), ticket_file, mock_ticket)

        with patch("src.paths.find_ticket_file") as mock_find:
            result = get_ticket_type("b.cht1")

        assert result == "bee"
        mock_find.assert_not_called()

    def test_cache_miss_reads_from_disk(self, isolated_bees_env):
        """Cache miss falls back to filesystem scan and returns the correct type."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.cm1", "bee", "Cache Miss Test")

        result = get_ticket_type("b.cm1")
        assert result == "bee"

    def test_not_found_returns_none(self, isolated_bees_env):
        """Returns None for a ticket ID that doesn't exist in any hive."""
        helper = isolated_bees_env
        helper.create_hive("backend")
        helper.write_config()

        result = get_ticket_type("b.nonexistent")
        assert result is None


class TestBuildTicketPathMap:
    """Tests for build_ticket_path_map batch path resolution."""

    def test_finds_tickets_across_multiple_hives(self, isolated_bees_env):
        """Should find all requested tickets with correct hive names and paths."""
        helper = isolated_bees_env
        hive1_dir = helper.create_hive("backend")
        hive2_dir = helper.create_hive("frontend")
        helper.write_config()

        f1 = helper.create_ticket(hive1_dir, "b.aa1", "bee", "Bee One")
        f2 = helper.create_ticket(hive1_dir, "b.aa2", "bee", "Bee Two")
        f3 = helper.create_ticket(hive2_dir, "b.aa3", "bee", "Bee Three")

        result = build_ticket_path_map({"b.aa1", "b.aa2", "b.aa3"})

        assert len(result) == 3
        assert result["b.aa1"] == ("backend", f1)
        assert result["b.aa2"] == ("backend", f2)
        assert result["b.aa3"] == ("frontend", f3)

    def test_returns_empty_for_unknown_ids(self, isolated_bees_env):
        """Unknown IDs should not appear in the result dict."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.kn1", "bee", "Known")

        result = build_ticket_path_map({"b.kn1", "b.zzz"})

        assert "b.kn1" in result
        assert "b.zzz" not in result

    def test_single_walk_per_hive(self, isolated_bees_env):
        """Should walk each hive at most once, not once per ticket."""
        helper = isolated_bees_env
        hive1_dir = helper.create_hive("backend")
        hive2_dir = helper.create_hive("frontend")
        helper.write_config()

        helper.create_ticket(hive1_dir, "b.w11", "bee", "Walk One")
        helper.create_ticket(hive1_dir, "b.w12", "bee", "Walk Two")
        helper.create_ticket(hive2_dir, "b.w13", "bee", "Walk Three")

        with patch("os.walk", wraps=os.walk) as mock_walk:
            result = build_ticket_path_map({"b.w11", "b.w12", "b.w13"})

        assert len(result) == 3
        # At most one os.walk call per hive (2 hives = max 2 calls)
        assert mock_walk.call_count <= 2

    def test_empty_input(self, isolated_bees_env):
        """Empty input set should return empty dict."""
        helper = isolated_bees_env
        helper.create_hive("backend")
        helper.write_config()

        result = build_ticket_path_map(set())

        assert result == {}


class TestIterTicketFilesMdSlug:
    """iter_ticket_files and iter_ticket_files_deep with a subtask whose slug is 'md'.

    Regression test for b.6yv: Path.rglob('*.md') matches directories whose
    names end in '.md' (e.g. t1.abc.md/). iter_ticket_files uses selective
    directory traversal and only yields files, never directories.
    """

    def _setup_hive(self, tmp_path):
        """Create hive with b.abc bee and t1.abc.md subtask (slug='md')."""
        hive_dir = tmp_path / "myhive"
        hive_dir.mkdir()

        # Normal bee: b.abc/b.abc.md
        bee_dir = hive_dir / "b.abc"
        bee_dir.mkdir()
        bee_file = bee_dir / "b.abc.md"
        bee_file.write_text("---\nid: b.abc\nschema_version: 1.1\ntype: bee\ntitle: Test\n---\n")

        # Subtask with slug 'md': t1.abc.md/t1.abc.md.md
        subtask_dir = bee_dir / "t1.abc.md"
        subtask_dir.mkdir()
        subtask_file = subtask_dir / "t1.abc.md.md"
        subtask_file.write_text(
            "---\nid: t1.abc.md\nschema_version: 1.1\ntype: t1\ntitle: MD Slug\n---\n"
        )

        return hive_dir, bee_file, subtask_file, subtask_dir

    @pytest.mark.parametrize(
        "fn",
        [
            pytest.param(iter_ticket_files, id="iter_ticket_files"),
            pytest.param(iter_ticket_files_deep, id="iter_ticket_files_deep"),
        ],
    )
    def test_yields_only_files(self, tmp_path, fn):
        """Both iterators yield the two .md files and never the directory t1.abc.md/."""
        hive_dir, bee_file, subtask_file, subtask_dir = self._setup_hive(tmp_path)

        results = list(fn(hive_dir))

        assert bee_file in results
        assert subtask_file in results
        assert len(results) == 2
        for p in results:
            assert p.is_file(), f"Expected file, got directory: {p}"


NESTED_WALK_IDS = ["b.aaa", "b.mmm", "b.nnn", "b.sss"]


class TestNestedHivePruning:
    """Walks of a hive never enter another hive nested in its directory (b.x6n).

    Layout: hive outer/ holds b.aaa, a misplaced misc/b.mmm, and two nested hives:
    b.aaa/t1.aaa.bc/ (named like a ticket dir, holds b.nnn) and Sub/ (holds b.sss).
    """

    @pytest.fixture(params=["marker", "registered", "registered_other_scope"])
    def outer_hive(self, request, tmp_path, mock_global_bees_dir):
        """Hive outer/ with nested hives marked by .hive/ or registered (here or in another scope)."""
        outer = tmp_path / "outer"
        id_named, plain = outer / "b.aaa" / "t1.aaa.bc", outer / "Sub"
        write_ticket_file(outer, "b.aaa")
        write_ticket_file(outer / "misc", "b.mmm")
        write_ticket_file(id_named, "b.nnn")
        write_ticket_file(plain, "b.sss")
        hives = {"outer": {"path": str(outer), "display_name": "Outer"}}
        nested = {
            "nested_id": {"path": str(id_named), "display_name": "Nested Id"},
            "nested_plain": {"path": str(plain), "display_name": "Nested Plain"},
        }
        if request.param == "marker":
            for root in (id_named, plain):
                (root / ".hive").mkdir()
            write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": hives, "child_tiers": {}})
        elif request.param == "registered":
            write_scoped_config(mock_global_bees_dir, tmp_path, {"hives": {**hives, **nested}, "child_tiers": {}})
        else:
            write_multi_scope_config(
                mock_global_bees_dir, {str(tmp_path): {"hives": hives}, "/elsewhere/**": {"hives": nested}}
            )
        return outer, id_named, plain

    @pytest.mark.parametrize(
        "found_ids,expected",
        [
            pytest.param(lambda h: {p.parent.name for p in iter_ticket_files(h)}, {"b.aaa"}, id="iter_ticket_files"),
            pytest.param(
                lambda h: {p.parent.name for p in iter_ticket_files_deep(h)},
                {"b.aaa", "b.mmm"},
                id="iter_ticket_files_deep",
            ),
            pytest.param(lambda h: {t for t in NESTED_WALK_IDS if find_ticket_file(h, t)}, {"b.aaa"}, id="find"),
            pytest.param(
                lambda h: {t for t in NESTED_WALK_IDS if find_ticket_file(h, t, deep=True)},
                {"b.aaa", "b.mmm"},
                id="find_deep",
            ),
        ],
    )
    def test_walks_skip_nested_hives(self, outer_hive, found_ids, expected):
        """Ticket walks from the outer hive find only its own tickets."""
        outer, _, _ = outer_hive
        assert found_ids(outer) == expected

    def test_nested_hive_walk_finds_its_own_tickets(self, outer_hive):
        """A walk that starts at a nested hive's root walks that hive."""
        _, id_named, plain = outer_hive
        assert [p.parent.name for p in iter_ticket_files_deep(plain)] == ["b.sss"]
        assert find_ticket_file(id_named, "b.nnn") == id_named / "b.nnn" / "b.nnn.md"

    def test_walk_hive_yields_own_directories_sorted(self, outer_hive):
        """walk_hive yields the outer hive's directories top-down and sorted, filtered by enter."""
        outer, _, _ = outer_hive
        walked = [os.path.relpath(d, outer) for d, _, _ in walk_hive(outer)]
        assert walked == [".", "b.aaa", "misc", os.path.join("misc", "b.mmm")]
        assert [os.path.relpath(d, outer) for d, _, _ in walk_hive(outer, enter=is_ticket_id)] == [".", "b.aaa"]

    @pytest.mark.parametrize(
        "rel_path,expected_root",
        [
            pytest.param("Sub/b.sss", "Sub", id="inside_plain_nested"),
            pytest.param("b.aaa/t1.aaa.bc/b.nnn", "b.aaa/t1.aaa.bc", id="inside_ticket_named_nested"),
            pytest.param("Sub", "Sub", id="nested_root_itself"),
            pytest.param("misc/b.mmm", None, id="own_dir"),
            pytest.param(".", None, id="hive_root"),
            pytest.param("..", None, id="outside_hive"),
        ],
    )
    def test_find_enclosing_hive_root(self, outer_hive, rel_path, expected_root):
        """Returns the nested hive's root for a path inside it, else None."""
        outer, _, _ = outer_hive
        expected = None if expected_root is None else outer / expected_root
        assert find_enclosing_hive_root(outer, outer / rel_path) == expected

    @pytest.mark.parametrize(
        "rel_top,expected_root",
        [
            pytest.param("b.aaa", "b.aaa/t1.aaa.bc", id="nested_root_below"),
            pytest.param("Sub", None, id="top_is_nested_root"),
            pytest.param("misc", None, id="no_nested_hive"),
        ],
    )
    def test_find_nested_hive_root(self, outer_hive, rel_top, expected_root):
        """Returns the root of a nested hive strictly below top, else None."""
        outer, _, _ = outer_hive
        expected = None if expected_root is None else outer / expected_root
        assert find_nested_hive_root(outer / rel_top) == expected

    @pytest.mark.parametrize("skipped_dir", [".hidden", "evicted", "cemetery"])
    def test_find_nested_hive_root_looks_where_walks_do_not(self, tmp_path, skipped_dir):
        """A nested hive under a directory the ticket walks skip is still found."""
        inner = tmp_path / "b.aaa" / skipped_dir / "Inner"
        (inner / ".hive").mkdir(parents=True)
        assert find_nested_hive_root(tmp_path / "b.aaa") == inner

    @pytest.mark.parametrize(
        "walk",
        [
            pytest.param(lambda h: list(iter_ticket_files(h)), id="iter_ticket_files"),
            pytest.param(lambda h: list(iter_ticket_files_deep(h)), id="iter_ticket_files_deep"),
            pytest.param(lambda h: find_ticket_file(h, "b.aaa"), id="find_ticket_file"),
            pytest.param(lambda h: list(walk_hive(h)), id="walk_hive"),
            pytest.param(lambda h: find_nested_hive_root(h), id="find_nested_hive_root"),
            pytest.param(lambda h: find_enclosing_hive_root(h, h / "Sub"), id="find_enclosing_hive_root"),
        ],
    )
    def test_walks_raise_when_global_config_is_unloadable(self, tmp_path, mock_global_bees_dir, walk):
        """b.cyd: with the registered hive roots unknown, a walk raises ConfigLoadError instead of entering a nested hive."""
        hive = tmp_path / "outer"
        write_ticket_file(hive, "b.aaa")
        (mock_global_bees_dir / "config.json").write_text("{invalid json")

        with pytest.raises(ConfigLoadError):
            walk(hive)

    @pytest.mark.parametrize("outer_hive", ["marker"], indirect=True)
    @pytest.mark.parametrize(
        "src,dest,operation,expected",
        [
            pytest.param(
                "Sub/b.sss",
                "b.aaa/t1.aaa.bc/b.sss",
                "move",
                "{src} is inside another hive rooted at {o}/Sub",
                id="src_inside_hive_named_before_dest",
            ),
            pytest.param(
                "b.aaa",
                "Sub/b.aaa",
                "move",
                "{dest} is inside another hive rooted at {o}/Sub",
                id="dest_inside_hive_named_before_src_holding_one",
            ),
            pytest.param(
                "b.aaa",
                "cemetery/b.aaa",
                "move",
                "{src} holds another hive rooted at {o}/b.aaa/t1.aaa.bc, which the move would carry",
                id="src_holds_hive_move",
            ),
            pytest.param(
                "b.aaa",
                None,
                "delete",
                "{src} holds another hive rooted at {o}/b.aaa/t1.aaa.bc, which the delete would remove",
                id="src_holds_hive_delete",
            ),
            pytest.param(
                "misc/b.mmm",
                "b.aaa",
                "move",
                "{dest} already exists and holds another hive rooted at {o}/b.aaa/t1.aaa.bc",
                id="dest_exists_holding_hive",
            ),
            pytest.param("misc/b.mmm", "misc", "move", None, id="clean_move_onto_existing_dir"),
            pytest.param("misc", None, "delete", None, id="clean_delete"),
        ],
    )
    def test_hive_crossing_reason(self, outer_hive, src, dest, operation, expected):
        """Names the path and the root of the other hive it lies in or holds, src before dest; None when clean."""
        outer, _, _ = outer_hive
        src_path = outer / src
        dest_path = None if dest is None else outer / dest
        if expected is not None:
            expected = expected.format(src=src_path, dest=dest_path, o=outer)
        assert hive_crossing_reason(outer, src_path, dest_path, operation=operation) == expected

    @pytest.mark.parametrize("outer_hive", ["registered"], indirect=True)
    def test_registered_nested_hive_skipped_through_symlinked_root(self, outer_hive, tmp_path):
        """A registered nested hive is skipped also when the outer hive is walked through a symlink."""
        outer, _, _ = outer_hive
        link = tmp_path / "link"
        link.symlink_to(outer)
        assert {p.parent.name for p in iter_ticket_files_deep(link)} == {"b.aaa", "b.mmm"}


REAL_CASE = {
    "b.ai5": None,
    "b.ai5/prefix-tree/tickets/testplans/b.75s": None,
    "b.ai5/prefix-tree/tickets/testplans/b.75s/t1.75s.65": "b.75s",
    "b.ai5/prefix-tree/tickets/testplans/b.eiv": None,
    "b.ai5/prefix-tree/tickets/testplans/b.eiv/t1.19d.6c": "b.eiv",
}

# (ticket directories below the hive -> parent in the ticket's frontmatter (None: a bee or an unreadable file),
# expected [(subtree root, owner)])
FOREIGN_CASES = [
    pytest.param(REAL_CASE, [("b.ai5/prefix-tree", "b.ai5")], id="real_case_one_root_for_the_whole_fixture"),
    pytest.param(
        {"b.aaa": None, "b.aaa/t1.aaa.bc": "b.aaa", "b.aaa/t1.aaa.bc/fixtures/b.zzz": None},
        [("b.aaa/t1.aaa.bc/fixtures", "t1.aaa.bc")],
        id="owner_is_nearest_id_dir_above",
    ),
    pytest.param(
        {"b.abc": None, "b.abc/fixture/b.abc": None},
        [("b.abc/fixture", "b.abc")],
        id="copy_of_owners_own_id_while_the_real_file_is_outside",
    ),
    pytest.param(
        {
            "b.abc": None,
            "b.abc/t1.abc.aa": "b.abc",
            "b.abc/fixture/tickets/b.abc": None,
            "b.abc/fixture/tickets/b.abc/t1.abc.aa": "b.abc",
        },
        [("b.abc/fixture", "b.abc")],
        id="copy_of_owners_own_tree",
    ),
    pytest.param(
        {"b.abc/misc/b.abc": None, "b.abc/misc/b.abc/fixture/b.zzz": None},
        [("b.abc/misc/b.abc/fixture", "b.abc")],
        id="nested_candidates_root_is_the_inner_one",
    ),
    pytest.param(
        {
            "b.par": None,
            "b.par/misc/t1.par.aa": "b.par",
            "b.zzz": None,
            "b.zzz/fixture/b.qqq": None,
            "b.zzz/fixture/b.qqq/t1.par.aa": "b.qqq",
        },
        [("b.zzz/fixture", "b.zzz")],
        id="same_id_in_another_foreign_subtree_does_not_make_the_real_dir_foreign",
    ),
    pytest.param(
        {"b.abc": None, "b.abc/fixture/b.zzz": None, "b.abc/fixture/b.zzz/t1.abc.aa": "b.zzz"},
        [("b.abc/fixture", "b.abc")],
        id="ticket_below_an_unrelated_top_does_not_vouch",
    ),
    pytest.param(
        {"b.par": None, "b.par/t1.par.aa": "b.par", "b.par/misc/t1.par.aa": "b.par"},
        [("b.par/misc", "b.par")],
        id="copy_of_a_child_of_the_owner",
    ),
    pytest.param(
        {
            "b.abc": None,
            "b.abc/t1.abc.de": "b.abc",
            "b.abc/fixture/t1.abc.de": "b.abc",
            "b.abc/fixture/t1.abc.zz": "b.abc",
        },
        [("b.abc/fixture", "b.abc")],
        id="settled_duplicate_makes_a_mixed_directory_foreign",
    ),
    pytest.param(
        {"b.xxx/misc/b.yyy": "b.zzz", "b.xxx/misc/b.zzz": "b.yyy"},
        [("b.xxx/misc", "b.xxx")],
        id="unrelated_parent_cycle_terminates",
    ),
    pytest.param(
        {
            "b.xxx": None,
            "b.xxx/t1.xxx.aa": "t1.xxx.bb",
            "b.xxx/t1.xxx.bb": "t1.xxx.aa",
            "b.xxx/t1.xxx.aa/misc/b.yyy": None,
        },
        [("b.xxx/t1.xxx.aa/misc", "t1.xxx.aa")],
        id="cycle_in_the_ancestors_frontmatter_terminates",
    ),
    pytest.param({"b.xxx/misc/t0.abc.de": None}, [("b.xxx/misc", "b.xxx")], id="malformed_tier_id_ends_lineage"),
    pytest.param({"b.xxx/misc/t1.abc": None}, [("b.xxx/misc", "b.xxx")], id="short_child_id_ends_lineage"),
    pytest.param(
        {"b.xxx/misc/t1.abc.de.fg": None}, [("b.xxx/misc", "b.xxx")], id="malformed_child_id_ends_lineage"
    ),
    pytest.param({"t0.abc.de/misc/b.zzz": None}, [("t0.abc.de/misc", "t0.abc.de")], id="malformed_owner_id"),
    pytest.param(
        {"b.aaa/fx/b.fff": None, "b.bbb/fx/b.ggg": None},
        [("b.aaa/fx", "b.aaa"), ("b.bbb/fx", "b.bbb")],
        id="two_roots_in_path_order",
    ),
]

# As FOREIGN_CASES, but no foreign subtree
NOT_FOREIGN_CASES = [
    pytest.param({"b.aaa/misc/b.aaa": None}, id="own_id_above"),
    pytest.param({"b.par/misc/t1.par.aa": "b.par"}, id="parent_above_though_not_in_the_layout"),
    pytest.param({"b.par/misc/t1.zzz.aa": "b.par"}, id="parent_above_by_frontmatter_though_the_id_says_otherwise"),
    pytest.param({"b.par/misc/t1.par.aa": None}, id="parent_missing_or_corrupt_id_lineage_still_vouches"),
    pytest.param({"b.par/misc/t2.par.aa.bb": None}, id="grandparent_above_by_id_lineage"),
    pytest.param(
        {"b.par": None, "b.par/misc/b.yyy": "b.zzz", "b.zzz": "b.par"}, id="grandparent_above_by_frontmatter_chain"
    ),
    pytest.param({"t1.abc.de/misc/b.abc": None}, id="descendant_above"),
    pytest.param({"b.aaa/t1.aaa.bc/misc/b.zzz": "b.aaa"}, id="ancestor_above_but_not_nearest"),
    pytest.param(
        {"b.abc": None, "b.abc/misc/t1.abc.aa": "b.abc", "b.abc/misc/b.zzz": None}, id="mixed_dir_with_a_vouched_ticket"
    ),
    pytest.param({"b.abc/misc/b.abc": None, "b.abc/misc/b.abc/t1.abc.aa": "b.abc"}, id="misplaced_bee_with_child"),
    pytest.param({"b.abc/design/design": None}, id="non_ticket_stem_file"),
    pytest.param({"b.abc/misc/design/notes": None}, id="non_ticket_stem_file_deeper"),
    pytest.param({"wrong/b.xyz": None}, id="plain_dir_with_no_ticket_dir_above"),
    pytest.param({"wrong/b.aaa/b.bbb": None}, id="plain_dir_above_ticket_dirs_only"),
    pytest.param({"b.aaa/t1.aaa.bc": "b.zzz"}, id="only_ticket_dirs_above"),
    pytest.param(
        {"b.abc": None, "b.abc/fixture/t1.abc.de": "b.abc", "b.abc/fixture/t1.abc.zz": "b.abc"},
        id="mixed_directory_without_the_settled_duplicate",
    ),
    pytest.param({"b.xyz": None}, id="hive_root_ticket"),
    pytest.param({}, id="no_files"),
]


def _find_foreign_subtrees(layout: dict[str, str | None], children: dict[str, list[str]] | None = None):
    """Run find_foreign_subtrees() on tickets in the directories of layout below /hive; shallowest file wins an ID.

    children maps a directory of layout to the children in that ticket's frontmatter; given, it is the
    children_of_file lookup (a directory not in it has no children list), else none is passed.
    """
    hive = Path("/hive")
    files = {hive / directory / f"{Path(directory).name}.md": parent for directory, parent in layout.items()}
    parent_of_id: dict[str, str] = {}
    for file in sorted(files, key=lambda f: len(f.parts)):
        if files[file] is not None:
            parent_of_id.setdefault(file.stem, files[file])
    children_of_file = None
    if children is not None:
        by_file = {hive / directory / f"{Path(directory).name}.md": listed for directory, listed in children.items()}
        children_of_file = lambda file: by_file.get(file)  # noqa: E731
    return find_foreign_subtrees(hive, list(files), files.get, parent_of_id.get, children_of_file)


class TestFindForeignSubtrees:
    """find_foreign_subtrees: ticket trees under a non-ticket dir inside an unrelated ticket's folder (b.94t)."""

    @pytest.mark.parametrize("layout,expected", FOREIGN_CASES)
    def test_roots_and_owners(self, layout, expected):
        """A candidate dir none of whose top tickets is vouched for by the ticket dirs above it is a foreign root."""
        found = _find_foreign_subtrees(layout)

        assert [(subtree.root.relative_to("/hive").as_posix(), subtree.owner_id) for subtree in found] == expected

    @pytest.mark.parametrize("layout", NOT_FOREIGN_CASES)
    def test_no_foreign_subtree(self, layout):
        """Tickets related to a ticket dir above, in no candidate dir, or without a ticket-ID stem make no root."""
        assert _find_foreign_subtrees(layout) == []

    def test_children_of_file_vouches_for_a_ticket_its_parent_lists(self):
        """b.abc/notes/t1.xyz.aa is claimed by b.xyz listing it; foreign without the lookup or without the listing."""
        layout = {"b.abc": None, "b.xyz": None, "b.abc/notes/t1.xyz.aa": "b.xyz"}

        assert _find_foreign_subtrees(layout, children={"b.xyz": ["t1.xyz.aa"]}) == []
        assert [s.root for s in _find_foreign_subtrees(layout)] == [Path("/hive/b.abc/notes")]
        assert [s.root for s in _find_foreign_subtrees(layout, children={"b.xyz": []})] == [Path("/hive/b.abc/notes")]
        assert [s.root for s in _find_foreign_subtrees(layout, children={})] == [Path("/hive/b.abc/notes")]

    def test_children_of_file_ignores_a_parent_that_is_itself_unsettled(self):
        """A parent inside a candidate dir (e.g. a fixture) does not vouch for the ticket."""
        layout = {"b.abc": None, "b.abc/notes/t1.xyz.aa": "b.xyz", "b.abc/fixture/b.xyz": None}

        found = _find_foreign_subtrees(layout, children={"b.abc/fixture/b.xyz": ["t1.xyz.aa"]})

        assert sorted(s.root.name for s in found) == ["fixture", "notes"]

    def test_subtree_members_are_named_by_ticket_ids_and_files(self):
        """A root's ticket_ids and files hold every file under it, those in ticket dirs inside it included, in step."""
        (subtree,) = _find_foreign_subtrees(REAL_CASE)

        assert subtree.root == Path("/hive/b.ai5/prefix-tree")
        assert sorted(subtree.ticket_ids) == ["b.75s", "b.eiv", "t1.19d.6c", "t1.75s.65"]
        assert len(subtree.files) == len(subtree.ticket_ids)
        assert [f.stem for f in subtree.files] == subtree.ticket_ids
        assert Path("/hive/b.ai5/prefix-tree/tickets/testplans/b.75s/t1.75s.65/t1.75s.65.md") in subtree.files
        assert all(f.is_relative_to(subtree.root) for f in subtree.files)


class TestWalkSkipDirs:
    """walk_hive and find_ticket_file never enter the skip_dirs (b.94t).

    Layout: hive holds b.aaa with t1.aaa.bc and a folder fixture/ (b.fff inside), and a misplaced misc/b.fff.
    """

    @pytest.fixture
    def hive(self, tmp_path, mock_global_bees_dir):
        hive = tmp_path / "hive"
        write_ticket_file(hive, "b.aaa", children=["t1.aaa.bc"])
        write_ticket_file(hive / "b.aaa", "t1.aaa.bc", type="t1", parent="b.aaa")
        write_ticket_file(hive / "b.aaa" / "fixture", "b.fff", title="Fixture copy")
        write_ticket_file(hive / "misc", "b.fff", title="Hive copy")
        return hive

    @pytest.mark.parametrize("as_type", [Path, str])
    def test_walk_hive_prunes_skip_dirs_with_their_subtree(self, hive, as_type):
        """A skipped directory and everything below it is not yielded; the rest of the walk is unchanged."""
        skip = as_type(hive / "b.aaa" / "fixture")

        walked = [os.path.relpath(d, hive) for d, _, _ in walk_hive(hive, skip_dirs=[skip])]

        assert walked == [".", "b.aaa", os.path.join("b.aaa", "t1.aaa.bc"), "misc", os.path.join("misc", "b.fff")]
        assert os.path.join("b.aaa", "fixture", "b.fff") in [os.path.relpath(d, hive) for d, _, _ in walk_hive(hive)]

    def test_walk_hive_ignores_skip_dirs_outside_the_hive(self, hive, tmp_path):
        """A path that is not inside the hive prunes nothing."""
        everything = list(walk_hive(hive))

        assert list(walk_hive(hive, skip_dirs=[tmp_path / "elsewhere", tmp_path / "hive-sibling"])) == everything

    @pytest.mark.parametrize("deep", [False, True])
    def test_find_ticket_file_never_enters_a_skipped_ticket_dir(self, hive, deep):
        """A ticket inside a skipped directory is not found, though it is without skip_dirs."""
        skip = [hive / "b.aaa" / "t1.aaa.bc"]

        assert find_ticket_file(hive, "t1.aaa.bc", deep=deep) == hive / "b.aaa" / "t1.aaa.bc" / "t1.aaa.bc.md"
        assert find_ticket_file(hive, "t1.aaa.bc", deep=deep, skip_dirs=skip) is None

    def test_find_ticket_file_deep_finds_the_hive_copy_not_one_in_a_skipped_dir(self, hive):
        """Of two files for one ID, deep search finds the one outside skip_dirs (the other sorts first)."""
        fixture_copy = hive / "b.aaa" / "fixture" / "b.fff" / "b.fff.md"

        assert find_ticket_file(hive, "b.fff", deep=True) == fixture_copy
        found = find_ticket_file(hive, "b.fff", deep=True, skip_dirs=[hive / "b.aaa" / "fixture"])
        assert found == hive / "misc" / "b.fff" / "b.fff.md"
