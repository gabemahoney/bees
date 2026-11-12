"""b.11s: a write queen mutates tickets using their owning scope's configuration.

Exercise MCP server functions and CLI main from a queen with no matching scope.
Hive management, ambiguous names, and permission regressions live in other files.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from src import mcp_server
from src.paths import compute_ticket_path, iter_ticket_files
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_global_settings, write_multi_scope_config, write_queen_repos_config
from tests.helpers import write_ticket_file


@pytest.fixture
def queen_owner(tmp_path, mock_global_bees_dir, monkeypatch):
    """An unscoped write queen and two hives owned by a different scope."""
    owner, queen = tmp_path / "owner", tmp_path / "queen"
    owner.mkdir()
    queen.mkdir()
    ideas, backlog = owner / "ideas", owner / "backlog"
    ideas.mkdir()
    backlog.mkdir()
    write_multi_scope_config(
        mock_global_bees_dir,
        {
            str(owner): {
                "hives": {
                    "ideas": {"path": str(ideas), "display_name": "Ideas"},
                    "backlog": {"path": str(backlog), "display_name": "Backlog"},
                },
                "child_tiers": {"t1": ["Deliverable", "Deliverables"]},
                "status_values": ["open", "owner_review", "done"],
            },
        },
    )
    write_global_settings(
        mock_global_bees_dir,
        status_values=["open", "global_only", "done"],
        child_tiers={"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    )
    write_queen_repos_config(mock_global_bees_dir, [(str(queen), True)])
    write_ticket_file(ideas, "b.aaa", title="Owner idea", body="Original body.", tags=["seed"])
    write_ticket_file(backlog, "b.bbb", title="Owner backlog", body="Second body.")
    monkeypatch.chdir(queen)
    with repo_root_context(queen):
        yield SimpleNamespace(owner=owner, queen=queen, ideas=ideas, backlog=backlog)


@pytest.fixture(params=["mcp", "cli"])
def queen_write(request, queen_owner, cli_runner, mock_mcp_context):
    """Call a public write surface from the queen and return its actual result."""
    ctx = mock_mcp_context(queen_owner.queen)

    def invoke(tool, kwargs, argv, *, success=True):
        if request.param == "mcp":
            result = asyncio.run(
                getattr(mcp_server, tool)(ctx=ctx, repo_root=str(queen_owner.queen), **kwargs)
            )
        else:
            stdout, exit_code = cli_runner(argv)
            result = json.loads(stdout)
            assert exit_code == (0 if result["status"] == "success" else 1), result
        if success:
            assert result["status"] == "success", result
        return result

    return invoke


def _stored(hive, ticket_id):
    return read_ticket(ticket_id, file_path=compute_ticket_path(ticket_id, hive))


@pytest.mark.parametrize("hive", [None, "ideas"], ids=["by_id", "explicit_hive"])
def test_queen_updates_owner_ticket(queen_owner, queen_write, hive):
    kwargs = {"ticket_ids": "b.aaa", "add_tags": ["approved:yes"], "status": "done"}
    argv = ["update-ticket", "--ids", "b.aaa", "--add-tags", '["approved:yes"]', "--status", "done"]
    if hive is not None:
        kwargs["hive"] = hive
        argv += ["--hive", hive]

    queen_write("update_ticket", kwargs, argv)

    ticket = _stored(queen_owner.ideas, "b.aaa")
    assert set(ticket.tags) == {"seed", "approved:yes"}
    assert ticket.status == "done"


def test_queen_batch_updates_two_owner_tickets(queen_owner, queen_write):
    result = queen_write(
        "update_ticket",
        {"ticket_ids": ["b.aaa", "b.bbb"], "status": "done", "add_tags": ["reviewed"]},
        ["update-ticket", "--ids", "b.aaa", "b.bbb", "--status", "done", "--add-tags", '["reviewed"]'],
    )

    for hive, ticket_id in [(queen_owner.ideas, "b.aaa"), (queen_owner.backlog, "b.bbb")]:
        ticket = _stored(hive, ticket_id)
        assert ticket.status == "done", result
        assert "reviewed" in ticket.tags, result
    assert not result["not_found"]


def test_queen_appends_owner_ticket_body(queen_owner, queen_write):
    queen_write(
        "append_ticket_body",
        {"ticket_id": "b.aaa", "chunk": "\nQueen addition."},
        ["append-ticket-body", "--ticket-id", "b.aaa", "--chunk", "\nQueen addition."],
    )

    ticket = _stored(queen_owner.ideas, "b.aaa")
    assert ticket.body == "Original body.\nQueen addition."
    assert ticket.tags == ["seed"]


def test_queen_deletes_owner_ticket(queen_owner, queen_write):
    result = queen_write(
        "delete_ticket",
        {"ticket_ids": ["b.aaa"]},
        ["delete-ticket", "--ids", "b.aaa"],
    )

    assert not compute_ticket_path("b.aaa", queen_owner.ideas).parent.exists(), result
    assert compute_ticket_path("b.bbb", queen_owner.backlog).is_file()
    assert not result["not_found"]


def test_queen_creates_ticket_in_owner_hive(queen_owner, queen_write):
    result = queen_write(
        "create_ticket",
        {"ticket_type": "bee", "title": "From queen", "body": "Owner data", "hive": "ideas", "status": "open"},
        [
            "create-ticket", "--ticket-type", "bee", "--title", "From queen", "--body", "Owner data",
            "--hive", "ideas", "--status", "open",
        ],
    )

    ticket_id = result["ticket_id"]
    assert compute_ticket_path(ticket_id, queen_owner.ideas).is_file()
    ticket = _stored(queen_owner.ideas, ticket_id)
    assert (ticket.title, ticket.body, ticket.status) == ("From queen", "Owner data", "open")
    assert not list(iter_ticket_files(queen_owner.queen))


def test_queen_clones_owner_bee(queen_owner, queen_write):
    source = _stored(queen_owner.ideas, "b.aaa")
    result = queen_write("clone_bee", {"bee_id": "b.aaa"}, ["clone", "--bee-id", "b.aaa"])

    clone_id = result["ticket_id"]
    assert clone_id != "b.aaa"
    assert compute_ticket_path(clone_id, queen_owner.ideas).is_file()
    clone = _stored(queen_owner.ideas, clone_id)
    assert (clone.title, clone.body, clone.tags, clone.status) == (
        source.title, source.body, source.tags, source.status,
    )
    assert clone.guid != source.guid
    assert compute_ticket_path("b.aaa", queen_owner.ideas).is_file()
    assert not result["failed"]


def test_queen_moves_bee_between_owner_hives(queen_owner, queen_write):
    source = compute_ticket_path("b.aaa", queen_owner.ideas)
    original = source.read_bytes()
    result = queen_write(
        "move_bee",
        {"bee_ids": ["b.aaa"], "hive": "backlog"},
        ["move-bee", "--ids", "b.aaa", "--hive", "backlog"],
    )

    assert not source.parent.exists(), result
    destination = compute_ticket_path("b.aaa", queen_owner.backlog)
    assert destination.read_bytes() == original
    assert compute_ticket_path("b.bbb", queen_owner.backlog).is_file()
    assert result["moved"] == ["b.aaa"]


def test_queen_adds_dependency_between_owner_tickets(queen_owner, queen_write):
    queen_write(
        "update_ticket",
        {"ticket_ids": "b.aaa", "up_deps": ["b.bbb"]},
        ["update-ticket", "--ids", "b.aaa", "--up-deps", '["b.bbb"]'],
    )

    assert _stored(queen_owner.ideas, "b.aaa").up_dependencies == ["b.bbb"]
    assert _stored(queen_owner.backlog, "b.bbb").down_dependencies == ["b.aaa"]


def test_queen_update_enforces_owner_status_values(queen_owner, queen_write):
    queen_write(
        "update_ticket",
        {"ticket_ids": "b.aaa", "status": "owner_review"},
        ["update-ticket", "--ids", "b.aaa", "--status", "owner_review"],
    )
    assert _stored(queen_owner.ideas, "b.aaa").status == "owner_review"
    path = compute_ticket_path("b.aaa", queen_owner.ideas)
    before = path.read_bytes()

    result = queen_write(
        "update_ticket",
        {"ticket_ids": "b.aaa", "status": "global_only"},
        ["update-ticket", "--ids", "b.aaa", "--status", "global_only"],
        success=False,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_status"
    assert path.read_bytes() == before


def test_queen_create_enforces_owner_child_tiers(queen_owner, queen_write):
    result = queen_write(
        "create_ticket",
        {"ticket_type": "Deliverable", "title": "Owner child", "hive": "ideas", "parent": "b.aaa", "status": "open"},
        [
            "create-ticket", "--ticket-type", "Deliverable", "--title", "Owner child", "--hive", "ideas",
            "--parent", "b.aaa", "--status", "open",
        ],
    )
    child_id = result["ticket_id"]
    child = _stored(queen_owner.ideas, child_id)
    assert child.type == "t1"
    assert child.parent == "b.aaa"
    assert child_id in _stored(queen_owner.ideas, "b.aaa").children
    before = {path: path.read_bytes() for path in iter_ticket_files(queen_owner.ideas)}

    result = queen_write(
        "create_ticket",
        {"ticket_type": "t2", "title": "Invalid child", "hive": "ideas", "parent": child_id, "status": "open"},
        [
            "create-ticket", "--ticket-type", "t2", "--title", "Invalid child", "--hive", "ideas",
            "--parent", child_id, "--status", "open",
        ],
        success=False,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_ticket_type"
    assert {path: path.read_bytes() for path in iter_ticket_files(queen_owner.ideas)} == before
