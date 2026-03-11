"""Tests for queen repo (elevated_repos) configuration validation.

Covers:
- load_global_config() validation of elevated_repos, surfaced through _list_hives()
- check_queen_elevation() pure function
- check_queen_write_access() pure function
- Queen repo read access: list_hives, show_ticket across scopes
- Non-queen regression: only matching-scope hives visible
- MCP roots protocol path governs elevation check over repo_root param
- Queen-aware query execution: freeform and named queries span all scopes
"""

import json
from pathlib import Path

import pytest

from src.config import check_queen_elevation, check_queen_write_access
from src.mcp_hive_ops import _list_hives
from src.mcp_query_ops import _execute_freeform_query, _execute_named_query
from src.mcp_ticket_ops import _show_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_elevated_repos_config, write_global_queries, write_multi_scope_config, write_scoped_config
from tests.helpers import write_ticket_file


def _scope_entry(hive_dir: Path, hive_name: str) -> dict:
    """Build a minimal scope config entry for a single hive."""
    return {
        "hives": {hive_name: {"path": str(hive_dir), "display_name": hive_name.title()}},
        "child_tiers": {},
    }

# ---------------------------------------------------------------------------
# Parametrize cases for invalid elevated_repos structures
# ---------------------------------------------------------------------------
_INVALID_ELEVATED_REPOS_VALUES = [
    pytest.param([{"write": True}], id="missing_path_key"),
    pytest.param([{"path": 123}], id="path_not_a_string"),
    pytest.param([{"path": "/some/path", "write": "yes"}], id="write_not_bool"),
    pytest.param("oops", id="not_a_list"),
]


class TestElevatedReposConfigValidation:
    """Config validation for elevated_repos surfaced via list_hives."""

    @pytest.mark.parametrize("elevated_repos_value", _INVALID_ELEVATED_REPOS_VALUES)
    async def test_invalid_elevated_repos_returns_invalid_config(
        self,
        elevated_repos_value,
        tmp_path: Path,
        mock_global_bees_dir: Path,
        monkeypatch,
    ):
        """Invalid elevated_repos structures cause list_hives to return invalid_config."""
        monkeypatch.chdir(tmp_path)
        config = {
            "scopes": {},
            "schema_version": "2.0",
            "elevated_repos": elevated_repos_value,
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config))

        with repo_root_context(tmp_path):
            result = await _list_hives(resolved_root=tmp_path)

        assert result["status"] == "error"
        assert result["error_type"] == "invalid_config"

    async def test_nonexistent_elevated_repos_path_no_error(
        self,
        tmp_path: Path,
        mock_global_bees_dir: Path,
        monkeypatch,
    ):
        """Non-existent path in elevated_repos is silently accepted (no error)."""
        monkeypatch.chdir(tmp_path)
        write_elevated_repos_config(
            mock_global_bees_dir,
            [("/nonexistent/path/that/does/not/exist", True)],
        )

        with repo_root_context(tmp_path):
            result = await _list_hives(resolved_root=tmp_path)

        assert result["status"] == "success"


class TestCheckQueenElevation:
    """Unit tests for check_queen_elevation() in src/config.py."""

    def test_no_elevated_repos_key(self, tmp_path: Path):
        """Returns (False, False) when elevated_repos absent from config."""
        is_queen, has_write = check_queen_elevation(tmp_path, {})
        assert (is_queen, has_write) == (False, False)

    def test_repo_not_in_list(self, tmp_path: Path):
        """Returns (False, False) when resolved_root not in elevated_repos."""
        other = tmp_path / "other"
        other.mkdir()
        config = {"elevated_repos": [{"path": str(other)}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (False, False)

    def test_matching_entry_no_write_key(self, tmp_path: Path):
        """Returns (True, False) when matching entry has no write key."""
        config = {"elevated_repos": [{"path": str(tmp_path)}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, False)

    def test_matching_entry_write_true(self, tmp_path: Path):
        """Returns (True, True) when matching entry has write: true."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": True}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, True)

    def test_matching_entry_write_false(self, tmp_path: Path):
        """Returns (True, False) when matching entry has write: false."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": False}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, False)

    def test_nonexistent_path_skipped(self, tmp_path: Path):
        """Entries whose path doesn't exist on disk are skipped — no match, no error."""
        config = {"elevated_repos": [{"path": "/nonexistent/path/xyz"}]}
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (False, False)

    def test_nonexistent_path_skipped_even_if_listed_before_real_match(self, tmp_path: Path):
        """Nonexistent entries before a real match are skipped; real match still found."""
        config = {
            "elevated_repos": [
                {"path": "/nonexistent/path/xyz"},
                {"path": str(tmp_path), "write": True},
            ]
        }
        is_queen, has_write = check_queen_elevation(tmp_path, config)
        assert (is_queen, has_write) == (True, True)


class TestCheckQueenWriteAccess:
    """Unit tests for check_queen_write_access() in src/config.py."""

    def test_non_queen_repo_returns_none(self, tmp_path: Path):
        """Non-queen repo always has write access — returns None."""
        result = check_queen_write_access(tmp_path, {})
        assert result is None

    def test_queen_with_write_true_returns_none(self, tmp_path: Path):
        """Queen repo with write=True has write access — returns None."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": True}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is None

    def test_queen_without_write_returns_permission_denied(self, tmp_path: Path):
        """Queen repo without write access returns permission_denied error dict."""
        config = {"elevated_repos": [{"path": str(tmp_path)}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is not None
        assert result["error_type"] == "permission_denied"

    def test_queen_with_write_false_returns_permission_denied(self, tmp_path: Path):
        """Queen repo with write=False returns permission_denied error dict."""
        config = {"elevated_repos": [{"path": str(tmp_path), "write": False}]}
        result = check_queen_write_access(tmp_path, config)
        assert result is not None
        assert result["error_type"] == "permission_denied"


# ---------------------------------------------------------------------------
# Queen repo read-access tests
# ---------------------------------------------------------------------------


class TestQueenListHives:
    """Queen repo sees hives from ALL scopes via _list_hives."""

    async def test_queen_sees_all_scopes_with_scope_fields(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Queen returns hives from all scopes; each entry has correct scope field."""
        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        hive_a = scope_a / "alpha"
        hive_b = scope_b / "beta"
        hive_a.mkdir()
        hive_b.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()

        write_multi_scope_config(
            mock_global_bees_dir,
            {str(scope_a): _scope_entry(hive_a, "alpha"), str(scope_b): _scope_entry(hive_b, "beta")},
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])

        with repo_root_context(queen_root):
            result = await _list_hives(resolved_root=queen_root)

        assert result["status"] == "success"
        by_name = {h["normalized_name"]: h for h in result["hives"]}
        assert set(by_name) == {"alpha", "beta"}
        assert by_name["alpha"]["scope"] == str(scope_a)
        assert by_name["beta"]["scope"] == str(scope_b)

    async def test_same_name_hives_from_different_scopes_both_returned(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Queen list_hives returns both 'bugs' hives from different scopes as distinct entries."""
        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        bugs_a = scope_a / "bugs"
        bugs_b = scope_b / "bugs"
        bugs_a.mkdir()
        bugs_b.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()

        write_multi_scope_config(
            mock_global_bees_dir,
            {str(scope_a): _scope_entry(bugs_a, "bugs"), str(scope_b): _scope_entry(bugs_b, "bugs")},
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])

        with repo_root_context(queen_root):
            result = await _list_hives(resolved_root=queen_root)

        assert result["status"] == "success"
        bugs_entries = [h for h in result["hives"] if h["normalized_name"] == "bugs"]
        assert len(bugs_entries) == 2
        assert {h["scope"] for h in bugs_entries} == {str(scope_a), str(scope_b)}
        assert {h["path"] for h in bugs_entries} == {str(bugs_a), str(bugs_b)}


class TestQueenShowTicket:
    """Queen repo can read tickets from hives outside its own matching scope."""

    async def test_queen_reads_ticket_from_non_matching_scope(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Queen show_ticket finds a ticket in a hive invisible to normal repos."""
        monkeypatch.chdir(tmp_path)
        scope_other = tmp_path / "other_project"
        scope_other.mkdir()
        hive_other = scope_other / "other_hive"
        hive_other.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()

        write_multi_scope_config(
            mock_global_bees_dir, {str(scope_other): _scope_entry(hive_other, "other_hive")}
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])

        ticket_id = "b.abc"
        write_ticket_file(hive_other, ticket_id, title="Cross-Scope Ticket")

        with repo_root_context(queen_root):
            result = await _show_ticket(ticket_ids=[ticket_id], resolved_root=queen_root)

        assert result["status"] == "success"
        assert len(result["tickets"]) == 1
        assert result["tickets"][0]["ticket_id"] == ticket_id
        assert not result["not_found"]

    async def test_non_queen_cannot_find_ticket_in_other_scope(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Normal repo cannot read a ticket from a non-matching scope."""
        monkeypatch.chdir(tmp_path)
        scope_other = tmp_path / "other_project"
        scope_other.mkdir()
        hive_other = scope_other / "other_hive"
        hive_other.mkdir()
        # normal_root matches scope_normal; does NOT match scope_other
        scope_normal = tmp_path / "normal_project"
        scope_normal.mkdir()
        normal_root = scope_normal

        write_multi_scope_config(
            mock_global_bees_dir,
            {
                str(scope_other): _scope_entry(hive_other, "other_hive"),
                str(normal_root): {"hives": {}, "child_tiers": {}},
            },
        )
        # normal_root NOT in elevated_repos

        ticket_id = "b.abc"
        write_ticket_file(hive_other, ticket_id, title="Cross-Scope Ticket")

        with repo_root_context(normal_root):
            result = await _show_ticket(ticket_ids=[ticket_id], resolved_root=normal_root)

        assert result["status"] == "success"
        assert ticket_id in result["not_found"]


class TestNonQueenRegression:
    """Normal repos only see hives from their matching scope (SR-5 regression guard)."""

    async def test_non_queen_list_hives_only_from_matching_scope(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Normal repo list_hives omits hives from non-matching scopes."""
        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        hive_a = scope_a / "alpha"
        hive_b = scope_b / "beta"
        hive_a.mkdir()
        hive_b.mkdir()
        # normal_root exactly matches scope_a, not in elevated_repos
        normal_root = scope_a

        write_multi_scope_config(
            mock_global_bees_dir,
            {str(scope_a): _scope_entry(hive_a, "alpha"), str(scope_b): _scope_entry(hive_b, "beta")},
        )

        with repo_root_context(normal_root):
            result = await _list_hives(resolved_root=normal_root)

        assert result["status"] == "success"
        names = {h["normalized_name"] for h in result["hives"]}
        assert "alpha" in names
        assert "beta" not in names


class TestRootsWinsElevationCheck:
    """MCP roots protocol path governs elevation when both roots and repo_root param are present."""

    async def test_roots_protocol_beats_repo_root_param(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch, mock_mcp_context
    ):
        """When ctx provides queen root via roots, repo_root param (non-queen) is ignored."""
        from src.mcp_server import list_hives

        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        hive_a = scope_a / "alpha"
        hive_b = scope_b / "beta"
        hive_a.mkdir()
        hive_b.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()
        (queen_root / ".git").mkdir()  # needed so get_repo_root_from_path resolves to queen_root
        # normal_root matches scope_a; NOT in elevated_repos
        normal_root = scope_a

        write_multi_scope_config(
            mock_global_bees_dir,
            {str(scope_a): _scope_entry(hive_a, "alpha"), str(scope_b): _scope_entry(hive_b, "beta")},
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])

        # ctx provides queen_root via roots protocol; repo_root param is the non-queen path
        ctx = mock_mcp_context(queen_root)

        result = await list_hives(ctx=ctx, repo_root=str(normal_root))

        assert result["status"] == "success"
        names = {h["normalized_name"] for h in result["hives"]}
        # Queen sees BOTH hives; roots protocol chose queen over repo_root
        assert "alpha" in names
        assert "beta" in names


class TestQueenQueries:
    """Queen repo executes freeform and named queries spanning all scopes."""

    async def test_queen_freeform_query_finds_tickets_from_non_matching_scope(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Queen freeform query returns a ticket in a hive invisible to normal repos."""
        monkeypatch.chdir(tmp_path)
        scope_other = tmp_path / "other_project"
        scope_other.mkdir()
        hive_other = scope_other / "other_hive"
        hive_other.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()

        write_multi_scope_config(
            mock_global_bees_dir, {str(scope_other): _scope_entry(hive_other, "other_hive")}
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])

        write_ticket_file(hive_other, "b.tst", title="Out-of-Scope Bee")

        with repo_root_context(queen_root):
            result = await _execute_freeform_query("- [type=bee]", resolved_root=queen_root)

        assert result["status"] == "success"
        assert "b.tst" in result["ticket_ids"]

    async def test_queen_named_query_spans_multiple_scopes(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Queen named query returns tickets from all scopes."""
        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        hive_a = scope_a / "hive_a"
        hive_b = scope_b / "hive_b"
        hive_a.mkdir()
        hive_b.mkdir()
        queen_root = tmp_path / "queen"
        queen_root.mkdir()

        write_multi_scope_config(
            mock_global_bees_dir,
            {
                str(scope_a): _scope_entry(hive_a, "hive_a"),
                str(scope_b): _scope_entry(hive_b, "hive_b"),
            },
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), None)])
        write_global_queries(mock_global_bees_dir, {"all_bees": [["type=bee"]]})

        write_ticket_file(hive_a, "b.aaa", title="Scope A Bee")
        write_ticket_file(hive_b, "b.bbb", title="Scope B Bee")

        with repo_root_context(queen_root):
            result = await _execute_named_query("all_bees", resolved_root=queen_root)

        assert result["status"] == "success"
        assert "b.aaa" in result["ticket_ids"]
        assert "b.bbb" in result["ticket_ids"]

    async def test_non_queen_freeform_query_only_sees_matching_scope(
        self, tmp_path: Path, mock_global_bees_dir: Path, monkeypatch
    ):
        """Normal repo freeform query does NOT return tickets from non-matching scope."""
        monkeypatch.chdir(tmp_path)
        scope_a = tmp_path / "project_a"
        scope_b = tmp_path / "project_b"
        scope_a.mkdir()
        scope_b.mkdir()
        hive_a = scope_a / "hive_a"
        hive_b = scope_b / "hive_b"
        hive_a.mkdir()
        hive_b.mkdir()
        # normal_root exactly matches scope_a, NOT in elevated_repos
        normal_root = scope_a

        write_multi_scope_config(
            mock_global_bees_dir,
            {
                str(scope_a): _scope_entry(hive_a, "hive_a"),
                str(scope_b): _scope_entry(hive_b, "hive_b"),
            },
        )

        write_ticket_file(hive_a, "b.aaa", title="Scope A Bee")
        write_ticket_file(hive_b, "b.bbb", title="Scope B Bee")

        with repo_root_context(normal_root):
            result = await _execute_freeform_query("- [type=bee]", resolved_root=normal_root)

        assert result["status"] == "success"
        assert "b.aaa" in result["ticket_ids"]
        assert "b.bbb" not in result["ticket_ids"]


# ---------------------------------------------------------------------------
# Queen write-gate tests
# ---------------------------------------------------------------------------


@pytest.fixture
def queen_write_env(tmp_path, mock_global_bees_dir, monkeypatch):
    """Factory: build a queen repo env with configurable write permission.

    Returns a callable that accepts write=True/False and returns (queen_root, hive_dir).
    """
    def setup(write: bool):
        queen_root = tmp_path / "queen"
        queen_root.mkdir(exist_ok=True)
        (queen_root / ".git").mkdir(exist_ok=True)
        hive_dir = tmp_path / "ext_project" / "test_hive"
        hive_dir.mkdir(parents=True, exist_ok=True)
        write_scoped_config(
            mock_global_bees_dir,
            queen_root,
            {"hives": {"test_hive": {"path": str(hive_dir), "display_name": "Test Hive"}}, "child_tiers": {}},
        )
        write_elevated_repos_config(mock_global_bees_dir, [(str(queen_root), write)])
        monkeypatch.chdir(queen_root)
        return queen_root, hive_dir

    return setup


class TestQueenWriteGateMCP:
    """Queen repo write gate is enforced in create_ticket MCP tool."""

    async def test_queen_without_write_denied_create_ticket(
        self, queen_write_env, mock_mcp_context
    ):
        """Queen without write:true gets permission_denied; no ticket file created."""
        from src.mcp_server import create_ticket

        queen_root, hive_dir = queen_write_env(write=False)
        ctx = mock_mcp_context(queen_root)
        result = await create_ticket(ctx=ctx, ticket_type="bee", title="Should Not Exist", hive="test_hive")

        assert result["error_type"] == "permission_denied"
        assert not list(hive_dir.rglob("*.md"))

    async def test_queen_with_write_allowed_create_ticket(
        self, queen_write_env, mock_mcp_context
    ):
        """Queen with write:true creates a ticket; file exists on disk."""
        from src.mcp_server import create_ticket
        from src.paths import compute_ticket_path

        queen_root, hive_dir = queen_write_env(write=True)
        ctx = mock_mcp_context(queen_root)
        result = await create_ticket(ctx=ctx, ticket_type="bee", title="Queen Ticket", hive="test_hive")

        assert result["status"] == "success"
        ticket_id = result["ticket_id"]
        assert compute_ticket_path(ticket_id, hive_dir).exists()


class TestQueenWriteGateCLI:
    """Queen repo write gate is enforced in create-ticket CLI command."""

    def test_queen_without_write_denied_cli_create(self, queen_write_env, cli_runner):
        """Queen CLI create-ticket without write:true exits 1 with permission_denied."""
        queen_write_env(write=False)
        out, exit_code = cli_runner(["create-ticket", "--ticket-type", "bee", "--title", "X", "--hive", "test_hive"])

        assert exit_code == 1
        assert "permission_denied" in out

    def test_queen_with_write_allowed_cli_create(self, queen_write_env, cli_runner):
        """Queen CLI create-ticket with write:true exits 0 and ticket file exists."""
        from src.paths import compute_ticket_path

        _, hive_dir = queen_write_env(write=True)
        out, exit_code = cli_runner(
            ["create-ticket", "--ticket-type", "bee", "--title", "Queen CLI Ticket", "--hive", "test_hive"]
        )

        assert exit_code == 0
        result = json.loads(out)
        assert result["status"] == "success"
        assert compute_ticket_path(result["ticket_id"], hive_dir).exists()
