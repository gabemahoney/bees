"""b.11s regressions for queen hive writes and ambiguous hive names.

Exercise public MCP tool functions and CLI commands against real, isolated
scopes. TestQueenWriteGuards pins unchanged behaviour; its tests are guards,
not regressions. Per-ticket write coverage belongs to the other test writer,
except the explicit ambiguity and non-queen permission cases assigned here.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import mcp_server
from src.mcp_hive_ops import read_identity, write_identity
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_queen_repos_config
from tests.helpers import tree_snapshot, write_ticket_file


@pytest.fixture
def queen_hives(tmp_path, mock_global_bees_dir, monkeypatch):
    """A write queen with a local hive and two independent foreign scopes."""
    queen = tmp_path / "queen"
    owner = tmp_path / "owner"
    other = tmp_path / "other_owner"
    for root in (queen, owner, other):
        root.mkdir()

    def make_hive(root, name):
        hive = root / name
        (hive / ".hive").mkdir(parents=True)
        write_identity(hive / ".hive", {
            "normalized_name": name,
            "display_name": name.title(),
            "created_at": "2026-02-05T00:00:00",
        })
        return hive

    ideas = make_hive(owner, "ideas")
    local = make_hive(queen, "local")
    other_hive = make_hive(other, "elsewhere")

    def scope(hive, *, statuses):
        return {
            "hives": {hive.name: {"path": str(hive), "display_name": hive.name.title()}},
            "child_tiers": {},
            "status_values": statuses,
        }

    write_multi_scope_config(mock_global_bees_dir, {
        str(owner): scope(ideas, statuses=["open", "done"]),
        str(other): scope(other_hive, statuses=["open", "done"]),
        str(queen): scope(local, statuses=["local_only"]),
    })
    write_queen_repos_config(mock_global_bees_dir, [(str(queen), True)])
    ticket = write_ticket_file(ideas, "b.abc", title="Owner ticket", body="Owner body")
    other_ticket = write_ticket_file(other_hive, "b.def", title="Other ticket")
    monkeypatch.chdir(queen)
    with repo_root_context(queen):
        yield SimpleNamespace(
            queen=queen, owner=owner, other=other, ideas=ideas, local=local,
            other_hive=other_hive, ticket=ticket, other_ticket=other_ticket,
            config=mock_global_bees_dir / "config.json", global_dir=mock_global_bees_dir,
        )


@pytest.fixture(params=[pytest.param("mcp", id="mcp"), pytest.param("cli", id="cli")])
def invoke(request, queen_hives, cli_runner, mock_mcp_context):
    """Call the same operation through each public interface as the queen."""
    def call(operation, **kwargs):
        if request.param == "mcp":
            return asyncio.run(getattr(mcp_server, operation)(
                ctx=mock_mcp_context(queen_hives.queen), repo_root=str(queen_hives.queen), **kwargs,
            ))
        argv = [operation.replace("_", "-")]
        for key, value in kwargs.items():
            flag = "--ids" if key == "ticket_ids" else "--" + key.replace("_", "-")
            argv.extend([flag, json.dumps(value) if isinstance(value, (dict, list)) else str(value)])
        stdout, _ = cli_runner(argv)
        return json.loads(stdout)

    return call


def _config(env):
    return json.loads(env.config.read_text())


def _snapshot(env):
    """Include every scope's files and the isolated registry in refusal checks."""
    return {str(path): tree_snapshot(path) for path in (
        env.owner, env.other, env.queen, env.global_dir,
    )}


class TestQueenCrossScopeHiveWrites:
    """Regressions: named hive writes must run in the foreign owning scope."""

    def test_sanitize_repairs_owner_ticket(self, queen_hives, invoke):
        env = queen_hives
        write_ticket_file(env.ideas, "b.abc", title="Owner ticket", guid=None)
        local_before = tree_snapshot(env.queen)
        other_before = tree_snapshot(env.other)

        result = invoke("sanitize_hive", hive="ideas")

        assert result["status"] == "success", result
        assert read_ticket("b.abc", file_path=env.ticket).guid
        assert any(fix["fix_type"] == "add_guid" for fix in result["fixes_applied"])
        assert tree_snapshot(env.queen) == local_before
        assert tree_snapshot(env.other) == other_before

    def test_generate_index_writes_named_owner_hive(self, queen_hives, invoke):
        env = queen_hives
        before = env.ticket.read_bytes()

        result = invoke("generate_index", hive="ideas")

        assert result["status"] == "success", result
        index = env.ideas / "index.md"
        assert index.is_file(), result
        assert "Owner ticket" in index.read_text()
        assert "b.abc" in index.read_text()
        assert env.ticket.read_bytes() == before
        assert not (env.local / "index.md").exists()
        assert not (env.other_hive / "index.md").exists()

    def test_rename_updates_owner_registration_and_folder(self, queen_hives, invoke):
        env = queen_hives
        before = _config(env)
        ticket_bytes = env.ticket.read_bytes()

        result = invoke("rename_hive", old_name="ideas", new_name="Renamed Ideas")

        assert result["status"] == "success", result
        after = _config(env)
        hives = after["scopes"][str(env.owner)]["hives"]
        assert "ideas" not in hives
        renamed = env.owner / "renamed_ideas"
        assert Path(hives["renamed_ideas"]["path"]) == renamed
        assert not env.ideas.exists()
        assert (renamed / "b.abc" / "b.abc.md").read_bytes() == ticket_bytes
        assert read_identity(renamed / ".hive")["normalized_name"] == "renamed_ideas"
        for root in (env.queen, env.other):
            assert after["scopes"][str(root)] == before["scopes"][str(root)]

    def test_abandon_removes_only_owner_registration(self, queen_hives, invoke):
        env = queen_hives
        before = _config(env)
        hive_before = tree_snapshot(env.ideas)

        result = invoke("abandon_hive", hive="ideas")

        assert result["status"] == "success", result
        after = _config(env)
        owner_scope = after["scopes"][str(env.owner)]
        assert "ideas" not in owner_scope["hives"]
        assert owner_scope["child_tiers"] == before["scopes"][str(env.owner)]["child_tiers"]
        assert owner_scope["status_values"] == ["open", "done"]
        for root in (env.queen, env.other):
            assert after["scopes"][str(root)] == before["scopes"][str(root)]
        assert tree_snapshot(env.ideas) == hive_before

    def test_undertaker_archives_in_owner_cemetery(self, queen_hives, invoke):
        env = queen_hives
        guid = read_ticket("b.abc", file_path=env.ticket).guid
        other_before = tree_snapshot(env.other)
        local_before = tree_snapshot(env.queen)

        result = invoke("undertaker", hive="ideas", query_yaml="{stages: [[status=open]]}")

        assert result["status"] == "success", result
        assert result["archived_count"] == 1
        assert guid in result["archived_guids"]
        assert not env.ticket.exists()
        archived = env.ideas / "cemetery" / f"b.{guid}" / f"b.{guid}.md"
        assert archived.is_file()
        assert read_ticket("b.abc", file_path=archived).title == "Owner ticket"
        assert tree_snapshot(env.other) == other_before
        assert tree_snapshot(env.queen) == local_before

    @pytest.mark.parametrize("operation,field,value", [
        pytest.param("set_types", "child_tiers", {"t1": ["Doc", "Docs"]}, id="set_types"),
        pytest.param("set_status_values", "status_values", ["draft", "accepted"], id="set_status_values"),
    ])
    def test_hive_settings_written_to_owner_identity(self, queen_hives, invoke, operation, field, value):
        env = queen_hives
        config_before = env.config.read_bytes()
        local_before = tree_snapshot(env.queen)
        other_before = tree_snapshot(env.other)

        result = invoke(operation, scope="hive", hive="ideas", **{field: value})

        assert result["status"] == "success", result
        assert read_identity(env.ideas / ".hive")[field] == value
        assert env.config.read_bytes() == config_before
        assert tree_snapshot(env.queen) == local_before
        assert tree_snapshot(env.other) == other_before


class TestQueenAmbiguousHiveWrites:
    """Decision 3 regressions: hive= must never choose a foreign scope silently."""

    @pytest.mark.parametrize("operation,kwargs", [
        pytest.param("create_ticket", {"ticket_type": "bee", "title": "Ambiguous create"}, id="create_ticket"),
        pytest.param("update_ticket", {"ticket_ids": "b.abc", "title": "Ambiguous update"}, id="update_ticket"),
    ])
    def test_duplicate_hive_name_refused_with_both_scopes(self, queen_hives, invoke, operation, kwargs):
        env = queen_hives
        # The ticket ID is unique; an explicit ambiguous hive name still needs
        # rejection, rather than first-match lookup or a misleading not-found.
        config = _config(env)
        hives = config["scopes"][str(env.other)]["hives"]
        hives["ideas"] = hives.pop("elsewhere")
        hives["ideas"]["display_name"] = "Ideas"
        write_identity(env.other_hive / ".hive", {
            "normalized_name": "ideas", "display_name": "Ideas", "created_at": "2026-02-05T00:00:00",
        })
        env.config.write_text(json.dumps(config))
        before = _snapshot(env)

        result = invoke(operation, hive="ideas", **kwargs)

        assert _snapshot(env) == before
        assert result["status"] == "error", result
        assert str(env.owner) in result["message"], result
        assert str(env.other) in result["message"], result


class TestQueenWriteGuards:
    """Unchanged-behaviour guards: these must pass before and after b.11s."""

    def test_guard_read_only_queen_denied_without_disk_changes(self, queen_hives, invoke):
        env = queen_hives
        write_queen_repos_config(env.global_dir, [(str(env.queen), False)])
        write_ticket_file(env.ideas, "b.abc", guid=None)
        before = _snapshot(env)

        result = invoke("sanitize_hive", hive="ideas")

        assert result["status"] == "error", result
        assert result["error_type"] == "permission_denied", result
        assert _snapshot(env) == before

    @pytest.mark.parametrize("named_hive", [pytest.param(False, id="by_id"), pytest.param(True, id="hive_named")])
    def test_guard_non_queen_cannot_write_foreign_ticket(self, queen_hives, invoke, named_hive):
        env = queen_hives
        write_queen_repos_config(env.global_dir, [])
        before = _snapshot(env)
        kwargs = {"hive": "ideas"} if named_hive else {}

        result = invoke("update_ticket", ticket_ids="b.abc", title="Forbidden", **kwargs)

        assert result["status"] == "error", result
        assert result["error_type"] == ("hive_not_found" if named_hive else "ticket_not_found"), result
        assert _snapshot(env) == before

    def test_guard_write_queen_can_write_own_scope(self, queen_hives, invoke):
        env = queen_hives
        foreign_before = tree_snapshot(env.owner)
        config_before = env.config.read_bytes()

        result = invoke("set_status_values", scope="hive", hive="local", status_values=["new", "done"])

        assert result["status"] == "success", result
        assert read_identity(env.local / ".hive")["status_values"] == ["new", "done"]
        assert tree_snapshot(env.owner) == foreign_before
        assert env.config.read_bytes() == config_before
