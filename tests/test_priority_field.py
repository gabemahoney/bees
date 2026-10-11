"""Tests for the optional priority field surviving every ticket rewrite, show-ticket and the tier rules (b.1zh).

PURPOSE:
priority is an optional integer on every tier. The reader passes any stored value through, so every path that
reads a ticket and saves it again must write the value back exactly, drop a null or empty one, and never add a key
to a ticket that has none.

SCOPE - Tests that belong here:
- Every rewrite path of a ticket holding a priority: update-ticket (single and batch), append-ticket-body,
  back-link sync, add-child (create-ticket under a parent), delete-ticket parent cleanup, sanitize-hive and the watcher's auto-fix save
- show-ticket returning priority

SCOPE - Tests that DON'T belong here:
- Reading and writing priority in isolation -> test_reader.py, test_writer.py
- Linting priority -> test_linter.py, test_sanitize_hive.py
- move-bee and clone-bee keeping priority -> test_move_bee.py, test_clone_bee.py
"""

import pytest

from src.mcp_hive_ops import _sanitize_hive
from src.mcp_ticket_ops import _append_ticket_body, _create_ticket, _delete_ticket, _show_ticket, _update_ticket
from src.parser import parse_frontmatter
from src.watcher import TicketChangeHandler
from tests.helpers import write_ticket_file
from tests.test_constants import PRIORITY_FRONTMATTER

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
