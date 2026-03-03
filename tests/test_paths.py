"""Unit tests for ticket path resolution and filesystem utilities."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

import src.cache
from src.mcp_id_utils import parse_ticket_id, parse_type_from_ticket_id
from src.parser import parse_frontmatter as real_parse_frontmatter
from src.paths import (
    build_ticket_path_map,
    compute_ticket_directory,
    ensure_ticket_directory_exists,
    get_ticket_path,
    infer_ticket_type_from_id,
    list_tickets,
)
from src.reader import get_ticket_type
from src.repo_context import repo_root_context
from tests.conftest import write_scoped_config
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
    """Cache behavior for list_tickets() and infer_ticket_type_from_id()."""

    def test_list_tickets_cache_hit_on_second_call(self, isolated_bees_env):
        """Second list_tickets() call returns cached results without re-parsing."""
        helper = isolated_bees_env
        hive_dir = helper.create_hive("backend")
        helper.write_config()
        helper.create_ticket(hive_dir, "b.nc1", "bee", "List Cache Test")

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
        helper.create_ticket(hive_dir, "b.ic1", "bee", "Infer Cache Test")

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
        helper.create_ticket(hive_dir, "b.sc1", "bee", "Shared Cache Test")

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
        file_mtime = ticket_file.stat().st_mtime

        mock_ticket = MagicMock()
        mock_ticket.type = "bee"
        src.cache.put("b.cht1", file_mtime, ticket_file, mock_ticket)

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
