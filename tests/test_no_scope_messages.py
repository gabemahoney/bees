"""Messages for a directory that no scope in ~/.bees/config.json matches (b.7cu).

Hive 'bugs' is registered under a scope for ``<tmp>/repo/**``; commands run from
``<tmp>/wt``, which no scope matches. The hive_not_found errors and list-hives
must name that directory, say no scope matched it and give the general hint,
on the CLI and through the MCP tools.
"""

import json

import pytest

from tests.conftest import write_multi_scope_config

NO_SCOPE_PHRASE = "No scope in ~/.bees/config.json matches"
HINT_PHRASE = "wildcard scope over its parent"


@pytest.fixture
def unmatched_dir(tmp_path, monkeypatch, mock_global_bees_dir):
    """Register hive 'bugs' for <tmp>/repo/** and chdir to <tmp>/wt, which no scope matches."""
    repo = tmp_path / "repo"
    hive_dir = repo / ".bees" / "bugs"
    hive_dir.mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    write_multi_scope_config(mock_global_bees_dir, {
        f"{repo}/**": {
            "hives": {"bugs": {"path": str(hive_dir), "display_name": "Bugs"}},
            "child_tiers": {},
        },
    })
    monkeypatch.chdir(wt)
    return wt


def assert_names_unmatched_dir(message: str, directory) -> None:
    assert str(directory) in message
    assert NO_SCOPE_PHRASE in message
    assert HINT_PHRASE in message
    assert f"{directory.parent}/**" in message
    assert "None" not in message
    assert "MCP context" not in message


# Every CLI command that reports hive_not_found for a hive named with --hive (or --old-name)
HIVE_NOT_FOUND_COMMANDS = [
    pytest.param(["create-ticket", "--ticket-type", "bee", "--title", "T", "--hive", "bugs"], id="create-ticket"),
    pytest.param(["create-ticket", "--ticket-type", "t1", "--title", "T", "--hive", "bugs"], id="create-ticket-t1"),
    pytest.param(["create-ticket", "--ticket-type", "Task", "--title", "T", "--hive", "bugs"], id="create-ticket-task"),
    pytest.param(["update-ticket", "--ids", "b.abc", "--title", "X", "--hive", "bugs"], id="update-ticket"),
    pytest.param(
        ["update-ticket", "--ids", "b.abc", "b.abd", "--status", "done", "--hive", "bugs"], id="update-ticket-batch"
    ),
    pytest.param(["append-ticket-body", "--ticket-id", "b.abc", "--chunk", "x", "--hive", "bugs"], id="append-body"),
    pytest.param(["delete-ticket", "--ids", "b.abc", "--hive", "bugs"], id="delete-ticket"),
    pytest.param(["delete-ticket", "--ids", "b.abc", "b.abd", "--hive", "bugs"], id="delete-ticket-bulk"),
    pytest.param(["move-bee", "--ids", "b.abc", "--hive", "bugs"], id="move-bee"),
    pytest.param(["abandon-hive", "--hive", "bugs"], id="abandon-hive"),
    pytest.param(["rename-hive", "--old-name", "bugs", "--new-name", "other"], id="rename-hive"),
    pytest.param(["sanitize-hive", "--hive", "bugs"], id="sanitize-hive"),
]


class TestCliFromUnmatchedDir:
    @pytest.mark.parametrize("argv", HIVE_NOT_FOUND_COMMANDS)
    def test_hive_not_found_explains_unmatched_scope(self, cli_runner, unmatched_dir, argv):
        stdout, exit_code = cli_runner(argv)
        result = json.loads(stdout)
        assert exit_code == 1
        assert result["error_type"] == "hive_not_found"
        assert_names_unmatched_dir(result["message"], unmatched_dir)

    def test_clone_explains_unmatched_scope(self, cli_runner, unmatched_dir):
        stdout, exit_code = cli_runner(["clone", "--bee-id", "b.abc", "--hive", "bugs"])
        result = json.loads(stdout)
        assert exit_code == 1
        assert result["error_type"] == "bee_not_found"
        assert "no hives configured" not in result["message"]
        assert_names_unmatched_dir(result["message"], unmatched_dir)

    def test_undertaker_explains_unmatched_scope(self, cli_runner, unmatched_dir):
        stdout, exit_code = cli_runner(["undertaker", "--hive", "bugs", "--query-yaml", "{stages: [[type=bee]]}"])
        result = json.loads(stdout)
        assert exit_code == 1
        assert_names_unmatched_dir(result["message"], unmatched_dir)

    def test_list_hives_says_no_scope_matches(self, cli_runner, unmatched_dir):
        stdout, exit_code = cli_runner(["list-hives"])
        result = json.loads(stdout)
        assert exit_code == 0
        assert result["hives"] == []
        assert result["message"] != "No hives configured"
        assert_names_unmatched_dir(result["message"], unmatched_dir)

    def test_list_hives_with_empty_config_keeps_no_hives_configured(self, cli_runner, tmp_path, mock_global_bees_dir):
        write_multi_scope_config(mock_global_bees_dir, {})
        stdout, _ = cli_runner(["list-hives"])
        assert json.loads(stdout)["message"] == "No hives configured"


class TestCliFromMatchedDir:
    def test_unknown_hive_has_no_scope_explanation(self, cli_runner, unmatched_dir, monkeypatch):
        """A directory a scope matches gets the plain hive_not_found text, no unmatched-scope hint."""
        monkeypatch.chdir(unmatched_dir.parent / "repo")
        stdout, _ = cli_runner(["update-ticket", "--ids", "b.abc", "--title", "X", "--hive", "nope"])
        result = json.loads(stdout)
        assert result["error_type"] == "hive_not_found"
        assert result["message"] == "Hive 'nope' not found in configuration"

    def test_create_child_tier_in_unknown_hive_is_hive_not_found(self, cli_runner, unmatched_dir, monkeypatch):
        """t1 into an unregistered hive returns hive_not_found instead of crashing on type validation."""
        monkeypatch.chdir(unmatched_dir.parent / "repo")
        stdout, exit_code = cli_runner(["create-ticket", "--ticket-type", "t1", "--title", "T", "--hive", "nope"])
        result = json.loads(stdout)
        assert exit_code == 1
        assert result["error_type"] == "hive_not_found"
        assert NO_SCOPE_PHRASE not in result["message"]

    def test_list_hives_with_empty_matching_scope(self, cli_runner, unmatched_dir, mock_global_bees_dir):
        """A matched scope with no hives, while another scope holds some, says so instead of 'No hives configured'."""
        write_multi_scope_config(mock_global_bees_dir, {
            f"{unmatched_dir.parent / 'repo'}/**": {
                "hives": {"bugs": {"path": str(unmatched_dir.parent / "repo" / ".bees" / "bugs"), "display_name": "B"}},
            },
            str(unmatched_dir): {"hives": {}},
        })
        stdout, _ = cli_runner(["list-hives"])
        result = json.loads(stdout)
        assert result["hives"] == []
        assert result["message"] == f"No hives in the scopes matching '{unmatched_dir}'"


class TestMcpFromUnmatchedDir:
    async def test_create_ticket(self, unmatched_dir, mock_mcp_context):
        from src.mcp_server import create_ticket

        result = await create_ticket(ctx=mock_mcp_context(unmatched_dir), ticket_type="bee", title="T", hive="bugs")
        assert result["error_type"] == "hive_not_found"
        assert_names_unmatched_dir(result["message"], unmatched_dir)

    async def test_list_hives(self, unmatched_dir, mock_mcp_context):
        from src.mcp_server import list_hives

        result = await list_hives(ctx=mock_mcp_context(unmatched_dir))
        assert result["status"] == "success"
        assert result["hives"] == []
        assert result["message"] != "No hives configured"
        assert_names_unmatched_dir(result["message"], unmatched_dir)


@pytest.fixture
def malformed_identity_dir(unmatched_dir, monkeypatch):
    """chdir to the matched repo whose 'bugs' hive has malformed child_tiers in identity.json."""
    repo = unmatched_dir.parent / "repo"
    marker = repo / ".bees" / "bugs" / ".hive"
    marker.mkdir()
    (marker / "identity.json").write_text(json.dumps(
        {"normalized_name": "bugs", "display_name": "Bugs", "child_tiers": {"t1": "Task"}}
    ))
    monkeypatch.chdir(repo)
    return repo


class TestCreateBeeWithMalformedIdentityChildTiers:
    """A bee create in a hive whose identity.json child_tiers is malformed returns a JSON error, not a traceback."""

    def test_cli(self, cli_runner, malformed_identity_dir):
        stdout, exit_code = cli_runner(["create-ticket", "--ticket-type", "bee", "--title", "T", "--hive", "bugs"])
        result = json.loads(stdout)
        assert exit_code == 1
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    async def test_mcp(self, malformed_identity_dir, mock_mcp_context):
        from src.mcp_server import create_ticket

        result = await create_ticket(
            ctx=mock_mcp_context(malformed_identity_dir), ticket_type="bee", title="T", hive="bugs"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
