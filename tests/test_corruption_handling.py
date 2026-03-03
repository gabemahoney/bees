"""Tests for hive behavior when tickets are corrupt.

Verifies that operations succeed even when a hive contains corrupt tickets,
that _sanitize_hive still works, and that healthy hives are unaffected.
"""

import pytest

import src.cache
import src.mcp_index_ops
import src.mcp_move_bee
import src.reader
from src.mcp_egg_ops import _resolve_eggs
from src.mcp_hive_ops import _list_hives, _sanitize_hive
from src.mcp_index_ops import _generate_index
from src.mcp_move_bee import _move_bee
from src.mcp_ticket_ops import _create_ticket, _delete_ticket, _get_types, _show_ticket, _update_ticket
from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_DESTINATION,
    HIVE_FRONTEND,
    TICKET_ID_CORRUPT_BEE,
    TICKET_ID_CORRUPT_TASK,
    TICKET_ID_MOVE_BEE_1,
    TICKET_ID_TEST_BEE,
    TITLE_TEST_BEE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_corrupt_hive(helper) -> None:
    """Register HIVE_BACKEND and inject an orphaned-task corruption."""
    hive_dir = helper.create_hive(HIVE_BACKEND)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
    # Parent lists no children; child claims the parent → orphaned-ticket error
    write_ticket_file(hive_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(hive_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)


# ---------------------------------------------------------------------------
# CRUD operations succeed even when hive has a corrupt sibling ticket
# ---------------------------------------------------------------------------

_CRUD_CALLS = [
    pytest.param(lambda: _create_ticket("bee", "New Bee", HIVE_BACKEND), id="create"),
    pytest.param(lambda: _update_ticket(TICKET_ID_CORRUPT_BEE, status="open", hive_name=HIVE_BACKEND), id="update"),
    pytest.param(lambda: _delete_ticket(TICKET_ID_CORRUPT_BEE, hive_name=HIVE_BACKEND), id="delete"),
    pytest.param(lambda: _show_ticket([TICKET_ID_CORRUPT_BEE]), id="show"),
    pytest.param(lambda: _resolve_eggs(TICKET_ID_CORRUPT_BEE), id="resolve_eggs"),
]


@pytest.mark.parametrize("make_call", _CRUD_CALLS)
async def test_ops_succeed_on_hive_with_corrupt_sibling_ticket(make_call, isolated_bees_env):
    """Operations on a hive with corrupt sibling tickets succeed (no pre-flight gate)."""
    _make_corrupt_hive(isolated_bees_env)
    result = await make_call()
    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# Additional gate tests (t3.VfACqF)
# ---------------------------------------------------------------------------


async def test_healthy_hive_succeeds_when_other_hive_corrupt(isolated_bees_env):
    """Operations on a healthy hive succeed even when another hive is corrupt."""
    helper = isolated_bees_env
    corrupt_dir = helper.create_hive(HIVE_BACKEND)
    healthy_dir = helper.create_hive(HIVE_FRONTEND)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    # Corrupt the backend hive
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)

    # Healthy ticket in frontend hive
    write_ticket_file(healthy_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _show_ticket([TICKET_ID_TEST_BEE])
    assert result["status"] == "success"
    assert result["tickets"][0]["ticket_id"] == TICKET_ID_TEST_BEE


async def test_sanitize_hive_resolves_corruption(isolated_bees_env):
    """_sanitize_hive fixes the orphaned-ticket corruption and reports is_corrupt=False."""
    _make_corrupt_hive(isolated_bees_env)
    result = await _sanitize_hive(HIVE_BACKEND)
    assert result["status"] == "success"
    assert result["is_corrupt"] is False


async def test_show_ticket_succeeds_on_hive_with_orphaned_task(isolated_bees_env):
    """show_ticket succeeds directly on a hive with orphaned-task corruption.

    With no integrity gate, operations proceed regardless of sibling ticket state.
    """
    helper = isolated_bees_env
    hive_dir = helper.create_hive(HIVE_BACKEND)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
    write_ticket_file(hive_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(hive_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)

    result = await _show_ticket([TICKET_ID_CORRUPT_BEE])
    assert result["status"] == "success"
    assert result["tickets"][0]["ticket_id"] == TICKET_ID_CORRUPT_BEE


# ---------------------------------------------------------------------------
# move_bee destination gate tests (t3.Dq729w)
# ---------------------------------------------------------------------------


async def test_move_bee_succeeds_when_destination_hive_has_corrupt_ticket(isolated_bees_env, monkeypatch):
    """Corrupt ticket in destination hive does not block move; bee moves successfully."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_move_bee, "get_repo_root_from_path", lambda _: helper.base_path)

    # Source hive: healthy with a valid bee
    source_dir = helper.create_hive(HIVE_BACKEND)
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")

    # Destination hive: has corrupt ticket (orphaned-task pattern)
    dest_dir = helper.create_hive(HIVE_DESTINATION)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
    write_ticket_file(dest_dir, TICKET_ID_CORRUPT_BEE, title="Corrupt Bee", children=[])
    write_ticket_file(dest_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)

    result = await _move_bee([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert TICKET_ID_MOVE_BEE_1 in result["moved"]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()


async def test_move_bee_succeeds_when_only_source_hive_corrupt(isolated_bees_env, monkeypatch):
    """Corrupt source hive does not block move; bee moves successfully to healthy destination."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_move_bee, "get_repo_root_from_path", lambda _: helper.base_path)

    # Source hive: corrupt (orphaned-task pattern), but contains the bee to move
    source_dir = helper.create_hive(HIVE_BACKEND)
    write_ticket_file(source_dir, TICKET_ID_CORRUPT_BEE, title="Corrupt Bee", children=[])
    write_ticket_file(source_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")

    # Destination hive: healthy (empty)
    dest_dir = helper.create_hive(HIVE_DESTINATION)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    result = await _move_bee([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert TICKET_ID_MOVE_BEE_1 in result["moved"]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()

# ---------------------------------------------------------------------------
# Exempt handler and cache tests (t3.SPjpEu)
# ---------------------------------------------------------------------------


async def test_list_hives_and_get_types_succeed_when_hive_corrupt(isolated_bees_env):
    """_list_hives and _get_types have no integrity gate and succeed with corrupt hive."""
    _make_corrupt_hive(isolated_bees_env)
    list_result = await _list_hives()
    types_result = await _get_types(resolved_root=isolated_bees_env.base_path)
    assert list_result["status"] == "success"
    assert types_result["status"] == "success"


async def test_successful_read_is_cached_and_second_read_hits_cache(isolated_bees_env, monkeypatch):
    """After a healthy show_ticket, the ticket is cached; a second call skips parse_frontmatter."""
    from unittest.mock import MagicMock

    helper = isolated_bees_env
    hive_dir = helper.create_hive(HIVE_BACKEND)
    helper.write_config(child_tiers={})
    write_ticket_file(hive_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    # First call: primes the cache
    result = await _show_ticket([TICKET_ID_TEST_BEE])
    assert result["status"] == "success"
    assert src.cache.get(TICKET_ID_TEST_BEE) is not None

    # Second call: must be a cache hit — parse_frontmatter should not be invoked
    parse_spy = MagicMock(wraps=src.reader.parse_frontmatter)
    monkeypatch.setattr(src.reader, "parse_frontmatter", parse_spy)
    result2 = await _show_ticket([TICKET_ID_TEST_BEE])
    assert result2["status"] == "success"
    parse_spy.assert_not_called()


# ---------------------------------------------------------------------------
# generate_index single-hive tests (t3.8W5xuT)
# ---------------------------------------------------------------------------


async def test_generate_index_single_hive_corrupt_succeeds(isolated_bees_env, monkeypatch):
    """Hive with corrupt ticket: _generate_index succeeds (no gate to block it)."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)
    _make_corrupt_hive(helper)

    result = await _generate_index(hive_name=HIVE_BACKEND)

    assert result["status"] == "success"
    assert result["skipped_hives"] == []


async def test_generate_index_single_hive_healthy_includes_skipped_hives(isolated_bees_env, monkeypatch):
    """Healthy hive: _generate_index returns status=success and skipped_hives=[]."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)
    hive_dir = helper.create_hive(HIVE_BACKEND)
    helper.write_config(child_tiers={})
    write_ticket_file(hive_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _generate_index(hive_name=HIVE_BACKEND)

    assert result["status"] == "success"
    assert result["skipped_hives"] == []


# ---------------------------------------------------------------------------
# generate_index global tests (t3.zPpmvG)
# ---------------------------------------------------------------------------


async def test_global_generate_index_includes_hive_with_corrupt_ticket(isolated_bees_env, monkeypatch):
    """Global _generate_index indexes all hives including those with corrupt tickets."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)

    corrupt_dir = helper.create_hive(HIVE_BACKEND)
    healthy_dir = helper.create_hive(HIVE_FRONTEND)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    # Inject orphaned-task corruption into backend
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)

    # Healthy ticket in frontend
    write_ticket_file(healthy_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _generate_index()

    assert result["status"] == "success"
    assert result["skipped_hives"] == []
    assert (healthy_dir / "index.md").exists()
    assert (corrupt_dir / "index.md").exists()


async def test_global_generate_index_all_healthy_empty_skipped_hives(isolated_bees_env, monkeypatch):
    """Global _generate_index with all healthy hives returns skipped_hives=[]."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)

    backend_dir = helper.create_hive(HIVE_BACKEND)
    frontend_dir = helper.create_hive(HIVE_FRONTEND)
    helper.write_config(child_tiers={})
    write_ticket_file(backend_dir, TICKET_ID_CORRUPT_BEE, title="Backend Bee")
    write_ticket_file(frontend_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _generate_index()

    assert result["status"] == "success"
    assert result["skipped_hives"] == []


async def test_global_generate_index_all_hives_have_corrupt_tickets(isolated_bees_env, monkeypatch):
    """Global _generate_index with all hives having corrupt tickets: indexes all, skipped_hives=[]."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)

    corrupt_dir_1 = helper.create_hive(HIVE_BACKEND)
    corrupt_dir_2 = helper.create_hive(HIVE_FRONTEND)
    helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    # Corrupt both hives with orphaned-task pattern (same IDs work in separate hive dirs)
    for corrupt_dir in (corrupt_dir_1, corrupt_dir_2):
        write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
        write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)

    result = await _generate_index()

    assert result["status"] == "success"
    assert result["skipped_hives"] == []
    assert (corrupt_dir_1 / "index.md").exists()
    assert (corrupt_dir_2 / "index.md").exists()


async def test_global_generate_index_no_hives_configured(isolated_bees_env, monkeypatch):
    """Global _generate_index with no hives configured returns skipped_hives=[] and generates fallback index."""
    helper = isolated_bees_env
    monkeypatch.setattr(src.mcp_index_ops, "get_repo_root_from_path", lambda _: helper.base_path)
    helper.write_config(child_tiers={})  # no hives registered

    result = await _generate_index()

    assert result["status"] == "success"
    assert result["skipped_hives"] == []
    assert "markdown" not in result


# ---------------------------------------------------------------------------
# Query tests (t3.J73Ce5)
# ---------------------------------------------------------------------------


async def test_query_succeeds_on_hive_with_corrupt_ticket(isolated_bees_env):
    """Query executes normally on a hive containing a corrupt ticket."""
    from src.mcp_query_ops import _execute_named_query
    from tests.conftest import write_scoped_config

    helper = isolated_bees_env
    corrupt_dir = helper.create_hive(HIVE_BACKEND)
    healthy_dir = helper.create_hive(HIVE_FRONTEND)
    write_scoped_config(
        helper.global_bees_dir, helper.base_path,
        {"hives": helper.hives, "child_tiers": {"t1": ["Task", "Tasks"]}},
        queries={"all_bees": [["type=bee"]]},
    )

    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)
    write_ticket_file(healthy_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _execute_named_query("all_bees", resolved_root=helper.base_path)

    assert result["status"] == "success"
    assert TICKET_ID_CORRUPT_BEE in result["ticket_ids"]
    assert TICKET_ID_TEST_BEE in result["ticket_ids"]


async def test_query_scoped_to_healthy_hive_succeeds(isolated_bees_env):
    """Query scoped to healthy hive returns success even when another hive has corrupt ticket."""
    from src.mcp_query_ops import _execute_named_query
    from tests.conftest import write_scoped_config

    helper = isolated_bees_env
    corrupt_dir = helper.create_hive(HIVE_BACKEND)
    healthy_dir = helper.create_hive(HIVE_FRONTEND)
    write_scoped_config(
        helper.global_bees_dir, helper.base_path,
        {"hives": helper.hives, "child_tiers": {"t1": ["Task", "Tasks"]}},
        queries={"all_bees": [["type=bee", f"hive={HIVE_FRONTEND}"]]},
    )

    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_BEE, title="Test Bee", children=[])
    write_ticket_file(corrupt_dir, TICKET_ID_CORRUPT_TASK, title="Orphaned Task", type="t1", parent=TICKET_ID_CORRUPT_BEE)
    write_ticket_file(healthy_dir, TICKET_ID_TEST_BEE, title=TITLE_TEST_BEE)

    result = await _execute_named_query("all_bees", resolved_root=helper.base_path)

    assert result["status"] == "success"
