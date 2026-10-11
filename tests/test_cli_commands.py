"""
Integration tests for the bees ticket management CLI (src/cli.py).

PURPOSE:
Tests all five CLI commands end-to-end: create-ticket, show-ticket,
update-ticket, delete-ticket, get-types. Uses the cli_runner fixture
to invoke main() with controlled argv and capture JSON output.

SCOPE - Tests that belong here:
- create-ticket / show-ticket / update-ticket / delete-ticket / get-types commands
- add-named-query / execute-named-query / execute-freeform-query commands
- colonize-hive / list-hives / abandon-hive / rename-hive / sanitize-hive commands
- generate-index / move-bee / undertaker commands
- Exit codes (0 success, 1 known error, 2 usage error)
- JSON output structure and field values
- UNSET sentinel behaviour for update-ticket
- JSON flag parsing: --reference-materials null, --tags '["a","b"]'
- The --priority flag on create-ticket and update-ticket (set, clear, batch, rejection, help text)
- No-subcommand invocation

SCOPE - Tests that DON'T belong here:
- Linter CLI -> test_cli.py
- MCP server lifecycle -> test_mcp_server_lifecycle.py
- Internal _create_ticket / _update_ticket logic -> test_mcp_ticket_ops.py
- --test-config on bees serve -> test_cli_serve.py

SCOPE - Also covered here:
- --test-config flag on non-serve subcommands (colonize-hive, abandon-hive, add-named-query)
  - Disk config is byte-for-byte unchanged after CLI call with --test-config
  - --config and --test-config are mutually exclusive (non-zero exit)
"""

import json
import re

import pytest

from src.parser import parse_frontmatter
from tests.conftest import write_multi_scope_config
from tests.helpers import break_config_with_trailing_comma, snapshot_diff, tree_snapshot
from tests.test_constants import (
    HIVE_FEATURES,
    INVALID_PRIORITY_CLI_ARGS,
    SCOPE_TIER_DEFAULT,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_bee(cli_runner, isolated_bees_env, title="Test Bee"):
    """Create a single bee in the 'test' hive; return ticket_id."""
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()
    stdout, exit_code = cli_runner(
        ["create-ticket", "--ticket-type", "bee", "--title", title, "--hive", "test"]
    )
    assert exit_code == 0, f"create-ticket failed: {stdout}"
    return json.loads(stdout)["ticket_id"]


# ---------------------------------------------------------------------------
# create-ticket
# ---------------------------------------------------------------------------


def test_create_ticket_happy_path(cli_runner, isolated_bees_env):
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(
        ["create-ticket", "--ticket-type", "bee", "--title", "Happy Bee", "--hive", "test"]
    )

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert "ticket_id" in result


@pytest.mark.parametrize(
    "ref_materials_json",
    [
        pytest.param('"just a string"', id="bare_string"),
        pytest.param('["not", "dicts"]', id="list_of_strings"),
        pytest.param('42', id="integer"),
    ],
)
def test_create_ticket_invalid_reference_materials(cli_runner, isolated_bees_env, ref_materials_json):
    """Regression b.h4z: non-dict reference_materials must exit 1 with status=error."""
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(
        [
            "create-ticket",
            "--ticket-type", "bee",
            "--title", "Ref Test",
            "--hive", "test",
            "--reference-materials", ref_materials_json,
        ]
    )

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result.get("error_type") == "invalid_argument"


@pytest.mark.parametrize(
    "ref_materials_json,expected",
    [
        pytest.param("null", None, id="null"),
        # Empty list is serialized as absent (writer skips empty lists); reads back as None.
        pytest.param('[]', None, id="empty_list"),
        pytest.param('[{"url": "https://example.com", "title": "Docs"}]', {"url": "https://example.com", "title": "Docs"}, id="list_of_dicts"),
    ],
)
def test_create_ticket_valid_reference_materials(cli_runner, isolated_bees_env, ref_materials_json, expected):
    """Valid reference_materials values (null, empty list, list of dicts) must succeed with correct stored value."""
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(
        [
            "create-ticket",
            "--ticket-type", "bee",
            "--title", "Ref Test",
            "--hive", "test",
            "--reference-materials", ref_materials_json,
        ]
    )

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"

    ticket_id = result["ticket_id"]
    show_out, _ = cli_runner(["show-ticket", "--ids", ticket_id])
    ticket = json.loads(show_out)["tickets"][0]
    stored = ticket.get("reference_materials")

    if expected is None:
        assert stored is None
    else:
        assert isinstance(stored, list)
        # Each stored entry may be augmented with a 'resolved' key by the resolver pipeline;
        # check that the expected dict is a subset of at least one stored entry.
        assert any(expected.items() <= entry.items() for entry in stored)


def test_create_ticket_json_tags(cli_runner, isolated_bees_env):
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(
        [
            "create-ticket",
            "--ticket-type",
            "bee",
            "--title",
            "Tags Test",
            "--hive",
            "test",
            "--tags",
            '["alpha","beta"]',
        ]
    )

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"


@pytest.mark.parametrize(
    "missing_flag,argv_suffix",
    [
        pytest.param("--title", ["create-ticket", "--ticket-type", "bee", "--hive", "test"], id="missing_title"),
        pytest.param("--ticket-type", ["create-ticket", "--title", "T", "--hive", "test"], id="missing_type"),
        pytest.param("--hive", ["create-ticket", "--ticket-type", "bee", "--title", "T"], id="missing_hive"),
    ],
)
def test_create_ticket_missing_required_flag(cli_runner, missing_flag, argv_suffix):
    stdout, exit_code = cli_runner(argv_suffix)
    assert exit_code == 2
    result = json.loads(stdout)
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# show-ticket
# ---------------------------------------------------------------------------


def test_show_ticket_happy_path(cli_runner, isolated_bees_env):
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(["show-ticket", "--ids", ticket_id])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert any(t["ticket_id"] == ticket_id for t in result["tickets"])


# ---------------------------------------------------------------------------
# update-ticket
# ---------------------------------------------------------------------------


def test_update_ticket_happy_path(cli_runner, isolated_bees_env):
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--status", "worker"])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"


def test_update_ticket_unset_preserves_title(cli_runner, isolated_bees_env):
    """Updating only --status must leave title unchanged."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env, title="Original Title")

    cli_runner(["update-ticket", "--ids", ticket_id, "--status", "worker"])

    stdout, exit_code = cli_runner(["show-ticket", "--ids", ticket_id])
    assert exit_code == 0
    tickets = json.loads(stdout)["tickets"]
    assert tickets[0]["title"] == "Original Title"


@pytest.mark.parametrize(
    "flag,json_val,expected_tags",
    [
        pytest.param(
            "--add-tags", '["urgent","beta"]', {"urgent", "beta"},
            id="add_tags_to_empty",
        ),
        pytest.param(
            "--remove-tags", '["nonexistent"]', set(),
            id="remove_tags_noop_on_empty",
        ),
    ],
)
def test_update_ticket_tag_ops(cli_runner, isolated_bees_env, flag, json_val, expected_tags):
    """--add-tags and --remove-tags flags wire through to _update_ticket."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, flag, json_val])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"

    show_out, _ = cli_runner(["show-ticket", "--ids", ticket_id])
    ticket = json.loads(show_out)["tickets"][0]
    assert set(ticket.get("tags") or []) == expected_tags


def test_update_ticket_add_then_remove_tags(cli_runner, isolated_bees_env):
    """Add tags then remove a subset; verifies both flags mutate tags correctly."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    cli_runner(["update-ticket", "--ids", ticket_id, "--add-tags", '["alpha","beta","gamma"]'])

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--remove-tags", '["beta"]']
    )

    assert exit_code == 0
    show_out, _ = cli_runner(["show-ticket", "--ids", ticket_id])
    ticket = json.loads(show_out)["tickets"][0]
    assert set(ticket.get("tags") or []) == {"alpha", "gamma"}


def test_update_ticket_parent_is_immutable(cli_runner, isolated_bees_env):
    """--parent on update-ticket must exit 1 with status=error and an error_type field (b.ihs)."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--parent", "b.fake"]
    )

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert "error_type" in result


def test_update_ticket_single_id_with_title(cli_runner, isolated_bees_env):
    """Regression: single-ID update with non-batchable field (title) must succeed (b.p1a).

    _update_ticket rejects title/body/reference_materials on batch (multi-ID) calls. The CLI
    must unwrap a single-element --ids list so the backend treats it as a
    single-ticket update and allows the non-batchable field through.
    """
    ticket_id = _create_bee(cli_runner, isolated_bees_env, title="Old Title")

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--title", "New Title"]
    )

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"

    show_out, _ = cli_runner(["show-ticket", "--ids", ticket_id])
    ticket = json.loads(show_out)["tickets"][0]
    assert ticket["title"] == "New Title"


@pytest.mark.parametrize(
    "ref_materials_json",
    [
        pytest.param('"just a string"', id="bare_string"),
        pytest.param('["not", "dicts"]', id="list_of_strings"),
        pytest.param('42', id="integer"),
    ],
)
def test_update_ticket_invalid_reference_materials(cli_runner, isolated_bees_env, ref_materials_json):
    """Regression b.h4z: non-dict reference_materials on update-ticket must exit 1 with status=error."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--reference-materials", ref_materials_json]
    )

    assert exit_code == 1
    result = json.loads(stdout)
    assert result["status"] == "error"
    assert result.get("error_type") == "invalid_argument"


@pytest.mark.parametrize(
    "ref_materials_json",
    [
        pytest.param("null", id="null"),
        pytest.param('[]', id="empty_list"),
        pytest.param('[{"url": "https://example.com"}]', id="list_of_dicts"),
    ],
)
def test_update_ticket_valid_reference_materials(cli_runner, isolated_bees_env, ref_materials_json):
    """Valid reference_materials values (null, empty list, list of dicts) must succeed on update-ticket."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(
        ["update-ticket", "--ids", ticket_id, "--reference-materials", ref_materials_json]
    )

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# delete-ticket
# ---------------------------------------------------------------------------


def test_delete_ticket_happy_path(cli_runner, isolated_bees_env):
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    stdout, exit_code = cli_runner(["delete-ticket", "--ids", ticket_id])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"


def test_delete_ticket_single_id_passes_list(cli_runner, isolated_bees_env, monkeypatch):
    """Regression: handle_delete_ticket must pass args.ids as a list even for a single ID (b.p1a)."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)

    captured = {}
    from src.mcp_ticket_ops import _delete_ticket as real_delete

    async def spy_delete(ticket_ids, **kwargs):
        captured["ticket_ids"] = ticket_ids
        return await real_delete(ticket_ids=ticket_ids, **kwargs)

    monkeypatch.setattr("src.cli._delete_ticket", spy_delete)

    stdout, exit_code = cli_runner(["delete-ticket", "--ids", ticket_id])

    assert exit_code == 0
    assert isinstance(captured["ticket_ids"], list), (
        f"Expected list, got {type(captured['ticket_ids']).__name__}: {captured['ticket_ids']}"
    )
    assert captured["ticket_ids"] == [ticket_id]


@pytest.mark.parametrize("flag", ["--clean-dependencies", "--no-clean-dependencies"], ids=["clean", "no_clean"])
def test_delete_ticket_clean_dependencies_flag_removed(flag, cli_runner, isolated_bees_env):
    """--clean-dependencies and --no-clean-dependencies are removed; argparse must exit non-zero."""
    ticket_id = _create_bee(cli_runner, isolated_bees_env)
    _stdout, exit_code = cli_runner(["delete-ticket", "--ids", ticket_id, flag])
    assert exit_code != 0


def test_delete_ticket_multiple_ids(cli_runner, isolated_bees_env):
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    def _create(title):
        stdout, _ = cli_runner(
            ["create-ticket", "--ticket-type", "bee", "--title", title, "--hive", "test"]
        )
        return json.loads(stdout)["ticket_id"]

    id1 = _create("Bee One")
    id2 = _create("Bee Two")

    stdout, exit_code = cli_runner(["delete-ticket", "--ids", id1, id2])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert set(result.get("deleted", [])) == {id1, id2}


# ---------------------------------------------------------------------------
# get-types
# ---------------------------------------------------------------------------


def test_get_types_happy_path(cli_runner, isolated_bees_env):
    isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config()

    stdout, exit_code = cli_runner(["get-types"])

    assert exit_code == 0
    result = json.loads(stdout)
    assert result["status"] == "success"
    assert "global" in result
    assert "scope" in result
    assert "hives" in result
    assert isinstance(result["hives"], dict)


# ---------------------------------------------------------------------------
# No subcommand
# ---------------------------------------------------------------------------


def test_no_subcommand_exits_2(cli_runner):
    _stdout, exit_code = cli_runner([])
    assert exit_code == 2


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------


class TestQueryCommands:
    def test_add_named_query_happy_path(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        stdout, exit_code = cli_runner(
            ["add-named-query", "--query-name", "my-query", "--query-yaml", "stages:\n- ['type=bee']"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["query_name"] == "my-query"

    def test_execute_freeform_query_happy_path(self, cli_runner, isolated_bees_env):
        _create_bee(cli_runner, isolated_bees_env)

        stdout, exit_code = cli_runner(
            ["execute-freeform-query", "--query-yaml", "stages:\n- ['type=bee']"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert "ticket_ids" in result

    def test_execute_freeform_query_priority_terms(self, cli_runner, priority_tickets):
        """execute-freeform-query with priority terms returns the matching IDs."""
        stdout, exit_code = cli_runner(
            ["execute-freeform-query", "--query-yaml", "stages:\n- [type=bee, 'priority>=0', 'priority<2']"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        expected = {tid for tid, p in priority_tickets.items() if tid.startswith("b.") and p is not None and 0 <= p < 2}
        assert set(result["ticket_ids"]) == expected
        assert expected

    def test_execute_named_query_happy_path(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        cli_runner(["add-named-query", "--query-name", "bee-query", "--query-yaml", "stages:\n- ['type=bee']"])

        stdout, exit_code = cli_runner(["execute-named-query", "--query-name", "bee-query"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_list_named_queries_happy_path(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        cli_runner(["add-named-query", "--query-name", "my-query", "--query-yaml", "stages:\n- ['type=bee']"])

        stdout, exit_code = cli_runner(["list-named-queries"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert any(q["name"] == "my-query" for q in result["queries"])

    def test_list_named_queries_rejects_all_flag(self, cli_runner, isolated_bees_env):
        """--all flag is no longer registered on list-named-queries (b.RLg fix)."""
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        _stdout, exit_code = cli_runner(["list-named-queries", "--all"])

        assert exit_code == 2  # argparse usage error

    @pytest.mark.parametrize("command", ["execute-freeform-query", "add-named-query"])
    @pytest.mark.parametrize(
        "report_yaml",
        [
            pytest.param("[[title]]", id="nested_list"),
            pytest.param("[1]", id="number"),
            pytest.param("[null]", id="null"),
            pytest.param("[{title: x}]", id="dict"),
        ],
    )
    def test_non_string_report_entry_rejected(self, cli_runner, isolated_bees_env, command, report_yaml):
        """A non-string report entry exits 1 with a parse_error, and no query is saved (b.hmr)."""
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()
        argv = [command, "--query-yaml", f"{{stages: [[type=bee]], report: {report_yaml}}}"]
        if command == "add-named-query":
            argv += ["--query-name", "bad-report"]

        stdout, exit_code = cli_runner(argv)

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["error_type"] == "parse_error"
        assert 'each "report" entry must be a field name (a string)' in result["message"]
        listed, _ = cli_runner(["list-named-queries"])
        assert json.loads(listed)["queries"] == []


# ---------------------------------------------------------------------------
# Hive commands
# ---------------------------------------------------------------------------


@pytest.fixture
def create_hive(cli_runner, isolated_bees_env, tmp_path):
    """Helper to create a hive directory and colonize it."""
    def _create(name):
        hive_path = tmp_path / name
        hive_path.mkdir(exist_ok=True)
        stdout, exit_code = cli_runner(
            ["colonize-hive", "--name", name, "--path", str(hive_path)]
        )
        assert exit_code == 0
        return hive_path
    return _create


class TestHiveCommands:
    def test_colonize_hive_happy_path(self, cli_runner, isolated_bees_env, tmp_path):
        hive_path = tmp_path / "myhive"
        hive_path.mkdir()

        stdout, exit_code = cli_runner(
            ["colonize-hive", "--name", "My Hive", "--path", str(hive_path)]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["normalized_name"] == "my_hive"

    def test_colonize_hive_child_tiers_json(self, cli_runner, isolated_bees_env, tmp_path):
        hive_path = tmp_path / "tiered_hive"
        hive_path.mkdir()

        stdout, exit_code = cli_runner(
            [
                "colonize-hive",
                "--name", "Tiered",
                "--path", str(hive_path),
                "--child-tiers", '{"t1": ["Task", "Tasks"]}',
            ]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result.get("child_tiers") == {"t1": ["Task", "Tasks"]}

    def test_list_hives_happy_path(self, cli_runner, isolated_bees_env, create_hive):
        create_hive("listed")

        stdout, exit_code = cli_runner(["list-hives"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        hive_names = [h["normalized_name"] for h in result["hives"]]
        assert "listed" in hive_names
        for hive in result["hives"]:
            assert "scope" in hive

    def test_list_hives_shows_scope_from_multiple_scopes(self, cli_runner, isolated_bees_env, mock_global_bees_dir, tmp_path):
        """list-hives merges hives from multiple scopes with correct scope values."""
        scope_wildcard = str(tmp_path.parent) + "/**"
        scope_exact = str(isolated_bees_env.base_path)

        hive_path_a = tmp_path / "hive_a"
        hive_path_a.mkdir(exist_ok=True)

        write_multi_scope_config(mock_global_bees_dir, {
            scope_wildcard: {
                "hives": {
                    "alpha_hive": {"path": str(hive_path_a), "display_name": "Alpha Hive", "created_at": "2024-01-01T00:00:00"},
                },
            },
            scope_exact: {
                "hives": {
                    "beta_hive": {"path": str(tmp_path / "hive_b"), "display_name": "Beta Hive", "created_at": "2024-01-01T00:00:00"},
                },
            },
        })

        stdout, exit_code = cli_runner(["list-hives"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        hives = {h["normalized_name"]: h for h in result["hives"]}
        assert "alpha_hive" in hives
        assert "beta_hive" in hives
        assert hives["alpha_hive"]["scope"] == scope_wildcard
        assert hives["beta_hive"]["scope"] == scope_exact

    def test_abandon_hive_happy_path(self, cli_runner, isolated_bees_env, create_hive):
        create_hive("myabandoned")

        stdout, exit_code = cli_runner(["abandon-hive", "--hive", "myabandoned"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_rename_hive_happy_path(self, cli_runner, isolated_bees_env, create_hive):
        create_hive("sourcehive")

        stdout, exit_code = cli_runner(["rename-hive", "--old-name", "sourcehive", "--new-name", "targethive"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_sanitize_hive_happy_path(self, cli_runner, isolated_bees_env, create_hive):
        create_hive("cleanhive")

        stdout, exit_code = cli_runner(["sanitize-hive", "--hive", "cleanhive"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result.get("errors_remaining", []) == []

    def test_colonize_hive_scope_creates_new_scope(self, cli_runner, isolated_bees_env, tmp_path):
        """--scope registers hive under the given pattern key; exits 0 with success."""
        hive_path = tmp_path / "scoped_hive"
        scope = str(tmp_path.parent) + "/*"

        stdout, exit_code = cli_runner(
            ["colonize-hive", "--name", "Scoped Hive", "--path", str(hive_path), "--scope", scope]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_colonize_hive_scope_invalid_pattern(self, cli_runner, isolated_bees_env, tmp_path):
        """--scope with mid-path wildcard exits 1 with invalid_scope_pattern error."""
        hive_path = tmp_path / "bad_hive"

        stdout, exit_code = cli_runner(
            ["colonize-hive", "--name", "Bad Hive", "--path", str(hive_path), "--scope", "/tmp/*/bad"]
        )

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["error_type"] == "invalid_scope_pattern"

    def test_colonize_hive_scope_different_bare_prefix_no_conflict(self, cli_runner, isolated_bees_env, tmp_path, mock_global_bees_dir):
        """Different bare prefixes at the same tier do NOT conflict (regression for false-positive bug).

        Previously the algorithm compared segment counts; /foo/bar/* and /baz/qux/* have the
        same segment count (2) and tier (1) so they incorrectly conflicted.  The fix compares
        bare prefix strings instead, so different prefixes succeed.
        """
        write_multi_scope_config(mock_global_bees_dir, {"/foo/bar/*": {"hives": {}}})

        hive_path = tmp_path / "no_conflict_hive"
        stdout, exit_code = cli_runner(
            ["colonize-hive", "--name", "No Conflict Hive", "--path", str(hive_path), "--scope", "/baz/qux/*"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------


class TestUtilityCommands:
    def test_generate_index_no_filters(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        stdout, exit_code = cli_runner(["generate-index"])

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_move_bee_single_id(self, cli_runner, isolated_bees_env, tmp_path):
        src_path = tmp_path / "srchive"
        src_path.mkdir()
        cli_runner(["colonize-hive", "--name", "srchive", "--path", str(src_path)])

        create_stdout, _ = cli_runner(
            ["create-ticket", "--ticket-type", "bee", "--title", "Move Me", "--hive", "srchive"]
        )
        ticket_id = json.loads(create_stdout)["ticket_id"]

        dest_path = tmp_path / "desthive"
        dest_path.mkdir()
        cli_runner(["colonize-hive", "--name", "desthive", "--path", str(dest_path)])

        stdout, exit_code = cli_runner(
            ["move-bee", "--ids", ticket_id, "--hive", "desthive"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert ticket_id in result.get("moved", [])

    def test_move_bee_variadic_ids(self, cli_runner, isolated_bees_env, tmp_path):
        src_path = tmp_path / "multisrc"
        src_path.mkdir()
        cli_runner(["colonize-hive", "--name", "multisrc", "--path", str(src_path)])

        def _make(title):
            stdout, _ = cli_runner(
                ["create-ticket", "--ticket-type", "bee", "--title", title, "--hive", "multisrc"]
            )
            return json.loads(stdout)["ticket_id"]

        id1 = _make("Bee One")
        id2 = _make("Bee Two")

        dest_path = tmp_path / "multidest"
        dest_path.mkdir()
        cli_runner(["colonize-hive", "--name", "multidest", "--path", str(dest_path)])

        stdout, exit_code = cli_runner(
            ["move-bee", "--ids", id1, id2, "--hive", "multidest"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert set(result.get("moved", [])) == {id1, id2}

    def test_undertaker_with_yaml(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        stdout, exit_code = cli_runner(
            ["undertaker", "--hive", "test", "--query-yaml", "stages:\n- ['status=finished']"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"

    def test_undertaker_mutual_exclusivity(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        _stdout, exit_code = cli_runner(
            [
                "undertaker",
                "--hive", "test",
                "--query-yaml", "stages:\n- ['type=bee']",
                "--query-name", "some-query",
            ]
        )

        assert exit_code == 2

    def test_undertaker_with_query_name(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive("test", "Test")
        isolated_bees_env.write_config()

        cli_runner(["add-named-query", "--query-name", "archive-finished", "--query-yaml", "stages:\n- ['status=finished']"])

        stdout, exit_code = cli_runner(
            ["undertaker", "--hive", "test", "--query-name", "archive-finished"]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"


# ---------------------------------------------------------------------------
# set-types commands
# ---------------------------------------------------------------------------


class TestSetTypesCommands:
    def test_set_types_global(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(SCOPE_TIER_DEFAULT)

        stdout, exit_code = cli_runner(
            ["set-types", "--scope", "global", "--child-tiers", json.dumps(SCOPE_TIER_DEFAULT)]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["scope"] == "global"
        assert result["child_tiers"] == SCOPE_TIER_DEFAULT

    def test_set_types_repo_scope(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(SCOPE_TIER_DEFAULT)

        new_tiers = {"t1": ["Story", "Stories"]}
        stdout, exit_code = cli_runner(
            ["set-types", "--scope", "repo_scope", "--child-tiers", json.dumps(new_tiers)]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"
        assert result["child_tiers"] == new_tiers

    def test_set_types_hive(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(SCOPE_TIER_DEFAULT)

        hive_tiers = {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]}
        stdout, exit_code = cli_runner(
            [
                "set-types",
                "--scope", "hive",
                "--hive", HIVE_FEATURES,
                "--child-tiers", json.dumps(hive_tiers),
            ]
        )

        assert exit_code == 0
        result = json.loads(stdout)
        assert result["status"] == "success"
        assert result["scope"] == "hive"
        assert result["hive_name"] == HIVE_FEATURES

    def test_set_types_conflicting_params(self, cli_runner, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_FEATURES)
        isolated_bees_env.write_config(SCOPE_TIER_DEFAULT)

        stdout, exit_code = cli_runner(
            [
                "set-types",
                "--scope", "global",
                "--child-tiers", json.dumps(SCOPE_TIER_DEFAULT),
                "--unset",
            ]
        )

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["status"] == "error"
        assert result["error_type"] == "conflicting_params"

    def test_set_types_invalid_json_tiers(self, cli_runner, isolated_bees_env):
        _stdout, exit_code = cli_runner(
            ["set-types", "--scope", "global", "--child-tiers", "{not valid json}"]
        )

        assert exit_code == 2


# ---------------------------------------------------------------------------
# --test-config flag (non-serve subcommands)
# ---------------------------------------------------------------------------


class TestTestConfigFlag:
    """Tests that --test-config prevents disk mutations on non-serve subcommands."""

    @pytest.mark.parametrize(
        "cmd_case",
        [
            pytest.param("colonize", id="colonize_hive"),
            pytest.param("abandon", id="abandon_hive"),
            pytest.param("add_query", id="add_named_query"),
        ],
    )
    def test_test_config_disk_unchanged(
        self, cmd_case, cli_runner, isolated_bees_env, mock_global_bees_dir
    ):
        """Disk config is byte-for-byte unchanged after a CLI call with --test-config."""
        isolated_bees_env.create_hive("testhive", "Test Hive")
        isolated_bees_env.write_config()

        config_file = mock_global_bees_dir / "config.json"
        before_bytes = config_file.read_bytes()

        if cmd_case == "colonize":
            hive_path = isolated_bees_env.base_path / "newhive"
            argv = [
                "colonize-hive", "--name", "New Hive", "--path", str(hive_path),
                "--test-config", str(config_file),
            ]
        elif cmd_case == "abandon":
            argv = ["abandon-hive", "--hive", "testhive", "--test-config", str(config_file)]
        else:  # add_query
            argv = [
                "add-named-query", "--query-name", "myquery",
                "--query-yaml", "stages:\n- ['type=bee']",
                "--test-config", str(config_file),
            ]

        stdout, exit_code = cli_runner(argv)
        after_bytes = config_file.read_bytes()

        assert exit_code == 0, f"Expected exit 0, got {exit_code}: {stdout}"
        assert before_bytes == after_bytes

    def test_mutual_exclusion(self, cli_runner, isolated_bees_env):
        """--config and --test-config are mutually exclusive; expect non-zero exit."""
        hive_path = isolated_bees_env.base_path / "foo"
        _stdout, exit_code = cli_runner(
            [
                "colonize-hive", "--name", "Foo", "--path", str(hive_path),
                "--config", "/some/path",
                "--test-config",
            ]
        )
        assert exit_code != 0


# ---------------------------------------------------------------------------
# Malformed global config (b.cyd)
# ---------------------------------------------------------------------------


class TestMalformedGlobalConfig:
    """A global config that cannot be loaded is a JSON error with exit 1, and the file is never rewritten."""

    @pytest.mark.parametrize(
        "argv",
        [
            pytest.param(["colonize-hive", "--name", "Beta", "--path", "{base}/beta"], id="colonize_hive"),
            pytest.param(["abandon-hive", "--hive", "testhive"], id="abandon_hive"),
            pytest.param(["add-named-query", "--query-name", "q", "--query-yaml", "stages:\n- ['type=bee']"], id="add_named_query"),
            pytest.param(["create-ticket", "--ticket-type", "bee", "--title", "T", "--hive", "testhive"], id="create_ticket"),
            pytest.param(["list-hives"], id="list_hives"),
            pytest.param(["get-types"], id="get_types"),
        ],
    )
    def test_command_errors_and_leaves_config_unchanged(self, cli_runner, isolated_bees_env, mock_global_bees_dir, argv):
        """Every command that loads the config reports config_load_error naming the file, exit 1, no save."""
        isolated_bees_env.create_hive("testhive", "Test Hive")
        isolated_bees_env.write_config()
        config_path = mock_global_bees_dir / "config.json"
        damaged = break_config_with_trailing_comma(config_path)
        before = tree_snapshot(isolated_bees_env.base_path)

        stdout, exit_code = cli_runner([a.format(base=isolated_bees_env.base_path) for a in argv])

        assert exit_code == 1
        result = json.loads(stdout)  # the whole stdout is one JSON document
        assert result["status"] == "error"
        assert result["error_type"] == "config_load_error"
        assert result["path"] == str(config_path)
        assert str(config_path) in result["message"]
        assert config_path.read_bytes() == damaged
        assert tree_snapshot(isolated_bees_env.base_path) == before


# ---------------------------------------------------------------------------
# --priority on create-ticket and update-ticket
# ---------------------------------------------------------------------------

_NO_KEY = "<no priority key>"


@pytest.fixture
def priority_hive(isolated_bees_env):
    """Hive `test` with a t1 tier; returns its path."""
    hive_dir = isolated_bees_env.create_hive("test", "Test")
    isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
    return hive_dir


def _stored_priority(hive_dir, ticket_id):
    """The frontmatter priority of a ticket file, or _NO_KEY when the file has no priority key."""
    path = next(hive_dir.rglob(f"{ticket_id}.md"))
    return parse_frontmatter(path)[0].get("priority", _NO_KEY)


def _create_via_cli(cli_runner, *extra, ticket_type="bee"):
    """create-ticket in hive `test` with extra argv; returns (parsed output, exit code)."""
    stdout, exit_code = cli_runner(["create-ticket", "--ticket-type", ticket_type, "--title", "P", "--hive", "test", *extra])
    return json.loads(stdout), exit_code


@pytest.mark.parametrize(
    "priority_argv,expected",
    [
        pytest.param(["--priority", "-3"], -3, id="negative"),
        pytest.param(["--priority=-3"], -3, id="negative_equals"),
        pytest.param(["--priority", "0"], 0, id="zero"),
        pytest.param(["--priority", "12"], 12, id="positive"),
        pytest.param(["--priority", "null"], _NO_KEY, id="null"),
        pytest.param([], _NO_KEY, id="omitted"),
    ],
)
def test_create_ticket_bee_priority(cli_runner, priority_hive, priority_argv, expected):
    result, exit_code = _create_via_cli(cli_runner, *priority_argv)

    assert exit_code == 0 and result["status"] == "success"
    stored = _stored_priority(priority_hive, result["ticket_id"])
    assert stored == expected and type(stored) is type(expected)


@pytest.mark.parametrize(
    "priority_argv,expected",
    [
        pytest.param(["--priority", "-3"], -3, id="negative"),
        pytest.param(["--priority=-3"], -3, id="negative_equals"),
        pytest.param(["--priority", "0"], 0, id="zero"),
        pytest.param(["--priority", "5"], 5, id="positive"),
    ],
)
def test_update_ticket_sets_priority(cli_runner, priority_hive, priority_argv, expected):
    target = _create_via_cli(cli_runner, "--priority", "99")[0]["ticket_id"]

    stdout, exit_code = cli_runner(["update-ticket", "--ids", target, *priority_argv])

    assert exit_code == 0 and json.loads(stdout)["updated"] == [target]
    stored = _stored_priority(priority_hive, target)
    assert stored == expected and type(stored) is int


def test_update_ticket_null_priority_removes_the_key(cli_runner, priority_hive):
    ticket_id = _create_via_cli(cli_runner, "--priority", "4")[0]["ticket_id"]

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--priority", "null"])

    assert exit_code == 0 and json.loads(stdout)["status"] == "success"
    assert _stored_priority(priority_hive, ticket_id) == _NO_KEY


def test_update_ticket_without_priority_flag_leaves_priority(cli_runner, priority_hive):
    ticket_id = _create_via_cli(cli_runner, "--priority=-3")[0]["ticket_id"]

    stdout, exit_code = cli_runner(["update-ticket", "--ids", ticket_id, "--status", "worker"])

    assert exit_code == 0 and json.loads(stdout)["status"] == "success"
    assert _stored_priority(priority_hive, ticket_id) == -3


def test_update_ticket_priority_applies_to_every_id(cli_runner, priority_hive):
    first = _create_via_cli(cli_runner)[0]["ticket_id"]
    second = _create_via_cli(cli_runner, "--priority", "9")[0]["ticket_id"]

    stdout, exit_code = cli_runner(["update-ticket", "--ids", first, second, "--priority=-2"])

    assert exit_code == 0 and sorted(json.loads(stdout)["updated"]) == sorted([first, second])
    assert [_stored_priority(priority_hive, i) for i in (first, second)] == [-2, -2]


def test_update_ticket_null_priority_clears_every_id(cli_runner, priority_hive):
    ids = [_create_via_cli(cli_runner, "--priority", str(n))[0]["ticket_id"] for n in (1, 2)]

    stdout, exit_code = cli_runner(["update-ticket", "--ids", *ids, "--priority", "null"])

    assert exit_code == 0 and json.loads(stdout)["status"] == "success"
    assert [_stored_priority(priority_hive, i) for i in ids] == [_NO_KEY, _NO_KEY]


@pytest.mark.parametrize("bad", INVALID_PRIORITY_CLI_ARGS.values(), ids=INVALID_PRIORITY_CLI_ARGS)
def test_create_ticket_rejects_invalid_priority(cli_runner, priority_hive, bad):
    before = tree_snapshot(priority_hive)

    result, exit_code = _create_via_cli(cli_runner, "--priority", bad)

    assert exit_code == 1
    assert result["status"] == "error" and result["error_type"] == "invalid_priority"
    assert snapshot_diff(before, tree_snapshot(priority_hive)) == (set(), set(), set())


@pytest.mark.parametrize("bad", INVALID_PRIORITY_CLI_ARGS.values(), ids=INVALID_PRIORITY_CLI_ARGS)
def test_update_ticket_rejects_invalid_priority(cli_runner, priority_hive, bad):
    first = _create_via_cli(cli_runner, "--priority", "5")[0]["ticket_id"]
    second = _create_via_cli(cli_runner)[0]["ticket_id"]
    before = tree_snapshot(priority_hive)

    for ids in ([first], [first, second]):
        stdout, exit_code = cli_runner(["update-ticket", "--ids", *ids, "--priority", bad, "--title", "Renamed"])

        assert exit_code == 1
        result = json.loads(stdout)
        assert result["status"] == "error" and result["error_type"] == "invalid_priority"
    assert snapshot_diff(before, tree_snapshot(priority_hive)) == (set(), set(), set())


@pytest.mark.parametrize(
    "command,expected_words",
    [
        pytest.param("create-ticket", ("integer", "negative", "null"), id="create"),
        pytest.param("update-ticket", ("integer", "negative", "null", "clears", "several"), id="update"),
    ],
)
def test_priority_help_text_documents_the_flag(cli_runner, command, expected_words):
    stdout, exit_code = cli_runner([command, "--help"])

    assert exit_code == 0
    # The option's own entry: from its 2-space-indented line up to the next option line
    match = re.search(r"^ {2}--priority\b.*?(?=^ {2}-|\Z)", stdout, re.S | re.M)
    assert match, "--priority option not listed in help"
    option_help = " ".join(match.group(0).split()).lower()
    assert all(word in option_help for word in expected_words)
