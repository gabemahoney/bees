"""Tests for the optional priority field: setting and clearing it, surviving every ticket rewrite and show-ticket (b.1zh).

PURPOSE:
priority is an optional integer on every tier. The reader passes any stored value through, so every path that
reads a ticket and saves it again must write the value back exactly, drop a null or empty one, and never add a key
to a ticket that has none.

SCOPE - Tests that belong here:
- create-ticket and update-ticket (single and batch) at the ticket-operation level: set an integer (zero and negative
  included), omit, clear with null, reject every non-integer with invalid_priority and write nothing
- Every rewrite path of a ticket holding a priority: update-ticket (single and batch), append-ticket-body,
  back-link sync, add-child (create-ticket under a parent), delete-ticket parent cleanup, sanitize-hive and the watcher's auto-fix save
- show-ticket returning priority

SCOPE - Tests that DON'T belong here:
- Reading and writing priority in isolation -> test_reader.py, test_writer.py
- The --priority CLI flag -> test_cli_commands.py
- The priority parameter's MCP schema and rejection through mcp.call_tool -> test_mcp_server.py
- The help text -> test_mcp_help.py
- Linting priority -> test_linter.py, test_sanitize_hive.py
- move-bee and clone-bee keeping priority -> test_move_bee.py, test_clone_bee.py
"""

import pytest

from src.mcp_hive_ops import _sanitize_hive
from src.mcp_ticket_ops import _append_ticket_body, _create_ticket, _delete_ticket, _show_ticket, _update_ticket
from src.parser import parse_frontmatter
from src.watcher import TicketChangeHandler
from tests.helpers import snapshot_diff, tree_snapshot, write_ticket_file
from tests.test_constants import INVALID_PRIORITY_INPUTS, PRIORITY_FRONTMATTER

TARGET, CHILD, OTHER = "b.pri", "t1.pri.ab", "b.oth"
_ABSENT = object()  # frontmatter has no priority key


async def _update_other_field(**_):
    await _update_ticket(TARGET, title="Renamed")


async def _update_batch(**_):
    await _update_ticket([TARGET], add_tags=["x"])


async def _append_body(**_):
    await _append_ticket_body(TARGET, " more")


async def _sync_back_link(**_):
    # A ticket blocked by the target: the target gets the down_dependencies back link
    await _update_ticket(OTHER, up_dependencies=[TARGET])


async def _add_child(**_):
    # Creating a t1 under the target (no priority passed) adds it to the target's children
    await _create_ticket("t1", "New child", "backend", parent=TARGET)


async def _delete_child(**_):
    # Deleting the child removes it from the target's children
    await _delete_ticket(CHILD)


async def _sanitize(**_):
    # The target has no guid: sanitize adds one and saves the ticket
    await _sanitize_hive("backend")


async def _watcher_auto_fix(**_):
    TicketChangeHandler()._do_regeneration()


# {pytest id: (action that rewrites TARGET, whether TARGET lacks a guid so the linter's auto-fix saves it)}
REWRITE_PATHS = {
    "update_other_field": (_update_other_field, False),
    "update_batch": (_update_batch, False),
    "append_ticket_body": (_append_body, False),
    "back_link_sync": (_sync_back_link, False),
    "add_child": (_add_child, False),
    "delete_ticket_parent_cleanup": (_delete_child, False),
    "sanitize_hive_save": (_sanitize, True),
    "watcher_auto_fix_save": (_watcher_auto_fix, True),
}

# (raw YAML after "priority:", or None for no key; value the reader returns); the unset ticket is the first case
PRIORITY_CASES = [(None, None), *((raw, stored) for raw, stored, _ in PRIORITY_FRONTMATTER.values())]
PRIORITY_IDS = ["absent", *PRIORITY_FRONTMATTER]


def _fields(raw):
    """write_ticket_file arguments for a priority given as raw YAML (none for an unset ticket)."""
    return {"raw_fields": {"priority": raw}} if raw is not None else {}


def _priority_on_disk(path):
    """The frontmatter priority of a ticket file, read without the ticket cache; _ABSENT when it has no key."""
    return parse_frontmatter(path)[0].get("priority", _ABSENT)


@pytest.fixture
def backend(isolated_bees_env):
    """Hive `backend` with tier t1; returns its path."""
    hive_dir = isolated_bees_env.create_hive("backend")
    isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})
    return hive_dir


@pytest.mark.parametrize("path_id", REWRITE_PATHS)
@pytest.mark.parametrize("raw,stored", PRIORITY_CASES, ids=PRIORITY_IDS)
async def test_priority_survives_rewrite(backend, path_id, raw, stored):
    """A rewrite keeps a valid or invalid priority exactly, drops a null or empty one, adds none to an unset ticket."""
    action, guid_missing = REWRITE_PATHS[path_id]
    target = write_ticket_file(backend, TARGET, children=[CHILD], **({"guid": None} if guid_missing else {}), **_fields(raw))
    write_ticket_file(backend / TARGET, CHILD, type="t1", parent=TARGET, **_fields(raw))
    write_ticket_file(backend, OTHER)
    before = target.read_bytes()

    await action()

    assert target.read_bytes() != before  # the target was rewritten, so the value went through the writer
    expected = _ABSENT if stored is None else stored
    on_disk = _priority_on_disk(target)
    assert on_disk == expected and type(on_disk) is type(expected)


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
@pytest.mark.parametrize("raw,stored", PRIORITY_CASES, ids=PRIORITY_IDS)
async def test_show_ticket_returns_priority(backend, ticket_type, raw, stored):
    """show-ticket returns the priority as read: null when unset (absent, null or empty), an invalid one as stored."""
    ticket_id = TARGET if ticket_type == "bee" else CHILD
    write_ticket_file(backend, TARGET, children=[CHILD], **(_fields(raw) if ticket_type == "bee" else {}))
    write_ticket_file(backend / TARGET, CHILD, type="t1", parent=TARGET, **(_fields(raw) if ticket_type == "t1" else {}))

    result = await _show_ticket([ticket_id])

    (entry,) = result["tickets"]
    assert "priority" in entry
    assert entry["priority"] == stored and type(entry["priority"]) is type(stored)


# ---------------------------------------------------------------------------
# create-ticket / update-ticket
# ---------------------------------------------------------------------------

VALID_PRIORITIES = [0, 7, -3]


def _ticket_file(hive_dir, ticket_id):
    """The path of an existing ticket file anywhere below the hive."""
    return next(hive_dir.rglob(f"{ticket_id}.md"))


def _bee_and_t1(hive_dir):
    """Write TARGET (with CHILD) and OTHER, none with a priority; return {tier: ticket id} for the update tests."""
    write_ticket_file(hive_dir, TARGET, children=[CHILD])
    write_ticket_file(hive_dir / TARGET, CHILD, type="t1", parent=TARGET)
    write_ticket_file(hive_dir, OTHER)
    return {"bee": TARGET, "t1": CHILD}


async def _create(ticket_type, **kwargs):
    """_create_ticket of a bee, or of a t1 under TARGET."""
    if ticket_type == "t1":
        kwargs.setdefault("parent", TARGET)
    return await _create_ticket(ticket_type if ticket_type == "t1" else "bee", "New", "backend", **kwargs)


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
@pytest.mark.parametrize("priority", VALID_PRIORITIES)
async def test_create_stores_integer_priority(backend, ticket_type, priority):
    """create-ticket stores an integer priority, zero and negative included, as an int."""
    write_ticket_file(backend, TARGET)

    result = await _create(ticket_type, priority=priority)

    assert result["status"] == "success"
    on_disk = _priority_on_disk(_ticket_file(backend, result["ticket_id"]))
    assert on_disk == priority and type(on_disk) is int


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
@pytest.mark.parametrize("kwargs", [{}, {"priority": None}], ids=["omitted", "null"])
async def test_create_without_priority_has_no_key(backend, ticket_type, kwargs):
    """create-ticket with the priority omitted or null writes no priority key."""
    write_ticket_file(backend, TARGET)

    result = await _create(ticket_type, **kwargs)

    assert result["status"] == "success"
    assert _priority_on_disk(_ticket_file(backend, result["ticket_id"])) is _ABSENT


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
@pytest.mark.parametrize("value", INVALID_PRIORITY_INPUTS.values(), ids=INVALID_PRIORITY_INPUTS)
async def test_create_rejects_invalid_priority_without_writing(backend, ticket_type, value):
    """create-ticket with a non-integer priority returns invalid_priority; no file is written or synced."""
    _bee_and_t1(backend)
    before = tree_snapshot(backend)

    result = await _create(ticket_type, priority=value, up_dependencies=[OTHER], down_dependencies=[TARGET])

    assert result["status"] == "error" and result["error_type"] == "invalid_priority"
    assert snapshot_diff(before, tree_snapshot(backend)) == (set(), set(), set())


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
@pytest.mark.parametrize("priority", VALID_PRIORITIES)
async def test_update_sets_integer_priority(backend, ticket_type, priority):
    """update-ticket sets an integer priority, zero and negative included, as an int."""
    ticket_id = _bee_and_t1(backend)[ticket_type]

    result = await _update_ticket(ticket_id, priority=priority)

    assert result["status"] == "success"
    on_disk = _priority_on_disk(_ticket_file(backend, ticket_id))
    assert on_disk == priority and type(on_disk) is int


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
async def test_update_changes_existing_priority(backend, ticket_type):
    """update-ticket replaces a stored priority."""
    ticket_id = _bee_and_t1(backend)[ticket_type]
    await _update_ticket(ticket_id, priority=5)

    await _update_ticket(ticket_id, priority=-1)

    assert _priority_on_disk(_ticket_file(backend, ticket_id)) == -1


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
async def test_update_omitted_priority_is_unchanged(backend, ticket_type):
    """update-ticket without a priority leaves the stored one alone."""
    ticket_id = _bee_and_t1(backend)[ticket_type]
    await _update_ticket(ticket_id, priority=5)

    result = await _update_ticket(ticket_id, title="Renamed")

    assert result["status"] == "success"
    assert _priority_on_disk(_ticket_file(backend, ticket_id)) == 5


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
async def test_update_null_clears_priority(backend, ticket_type):
    """update-ticket with priority null removes the key."""
    ticket_id = _bee_and_t1(backend)[ticket_type]
    await _update_ticket(ticket_id, priority=5)

    result = await _update_ticket(ticket_id, priority=None)

    assert result["status"] == "success"
    assert _priority_on_disk(_ticket_file(backend, ticket_id)) is _ABSENT


@pytest.mark.parametrize("ticket_type", ["bee", "t1"])
async def test_update_null_on_unprioritised_ticket_leaves_no_key(backend, ticket_type):
    """Clearing the priority of a ticket that has none succeeds and adds no key."""
    ticket_id = _bee_and_t1(backend)[ticket_type]

    result = await _update_ticket(ticket_id, priority=None)

    assert result["status"] == "success" and result["updated"] == [ticket_id]
    assert _priority_on_disk(_ticket_file(backend, ticket_id)) is _ABSENT


@pytest.mark.parametrize("value", INVALID_PRIORITY_INPUTS.values(), ids=INVALID_PRIORITY_INPUTS)
async def test_update_rejects_invalid_priority_without_writing(backend, value):
    """update-ticket with a non-integer priority returns invalid_priority; no field is written, no link synced."""
    _bee_and_t1(backend)
    await _update_ticket(TARGET, priority=5)
    before = tree_snapshot(backend)

    result = await _update_ticket(TARGET, priority=value, title="Renamed", up_dependencies=[OTHER])

    assert result["status"] == "error" and result["error_type"] == "invalid_priority"
    assert snapshot_diff(before, tree_snapshot(backend)) == (set(), set(), set())


@pytest.mark.parametrize("priority", VALID_PRIORITIES)
async def test_batch_update_sets_priority_on_every_ticket(backend, priority):
    """A batch update with a priority sets it on every ticket, across tiers."""
    ids = list(_bee_and_t1(backend).values()) + [OTHER]

    result = await _update_ticket(ids, priority=priority)

    assert result["status"] == "success" and sorted(result["updated"]) == sorted(ids)
    for ticket_id in ids:
        on_disk = _priority_on_disk(_ticket_file(backend, ticket_id))
        assert on_disk == priority and type(on_disk) is int


async def test_batch_update_null_clears_every_ticket(backend):
    """A batch update with priority null removes the key from every ticket."""
    ids = list(_bee_and_t1(backend).values()) + [OTHER]
    await _update_ticket(ids, priority=4)

    result = await _update_ticket(ids, priority=None)

    assert result["status"] == "success"
    assert [_priority_on_disk(_ticket_file(backend, i)) for i in ids] == [_ABSENT] * 3


async def test_batch_update_omitted_priority_is_unchanged(backend):
    """A batch update of another field leaves each stored priority alone."""
    ids = list(_bee_and_t1(backend).values())
    await _update_ticket(ids, priority=4)

    result = await _update_ticket(ids, status="closed")

    assert result["status"] == "success"
    assert [_priority_on_disk(_ticket_file(backend, i)) for i in ids] == [4, 4]


@pytest.mark.parametrize("value", INVALID_PRIORITY_INPUTS.values(), ids=INVALID_PRIORITY_INPUTS)
async def test_batch_update_rejects_invalid_priority_before_any_write(backend, value):
    """A batch with an invalid priority returns invalid_priority and writes none of its tickets."""
    ids = list(_bee_and_t1(backend).values()) + [OTHER]
    before = tree_snapshot(backend)

    result = await _update_ticket(ids, priority=value, status="closed", add_tags=["x"])

    assert result["status"] == "error" and result["error_type"] == "invalid_priority"
    assert snapshot_diff(before, tree_snapshot(backend)) == (set(), set(), set())
