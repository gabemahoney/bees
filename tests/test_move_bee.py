"""Tests for get_scope_key_for_hive() in src/config.py and _move_bee_core() in src/mcp_move_bee.py."""

import json
import shutil

import pytest

from src import cache
from src.config import get_scope_key_for_hive
from src.mcp_move_bee import _move_bee_core
from src.reader import read_ticket
from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_CLONE_DEST,
    HIVE_DESTINATION,
    HIVE_FRONTEND,
    HIVE_OTHER_SCOPE,
    HIVE_TEST,
    TICKET_ID_CORRUPT_BEE,
    TICKET_ID_MOVE_BEE_1,
    TICKET_ID_MOVE_BEE_2,
    TICKET_ID_T1,
)


@pytest.mark.parametrize(
    "global_config,lookup_name,expected_key,expect_raises",
    [
        pytest.param(
            {
                "scopes": {
                    "/repo/scope_a": {
                        "hives": {HIVE_TEST: {"path": "/repo/test_hive", "display_name": "Test Hive"}},
                    }
                }
            },
            HIVE_TEST,
            "/repo/scope_a",
            False,
            id="found_in_first_scope",
        ),
        pytest.param(
            {
                "scopes": {
                    "/repo/scope_a": {
                        "hives": {HIVE_BACKEND: {"path": "/repo/backend", "display_name": "Backend"}},
                    },
                    "/repo/scope_b": {
                        "hives": {HIVE_FRONTEND: {"path": "/repo/frontend", "display_name": "Frontend"}},
                    },
                }
            },
            HIVE_FRONTEND,
            "/repo/scope_b",
            False,
            id="found_in_later_scope",
        ),
        pytest.param(
            {
                "scopes": {
                    "/repo/scope_a": {
                        "hives": {HIVE_TEST: {"path": "/repo/test_hive", "display_name": "Test Hive"}},
                    }
                }
            },
            HIVE_FRONTEND,
            None,
            True,
            id="hive_not_found_raises",
        ),
    ],
)
def test_get_scope_key_for_hive(isolated_bees_env, global_config, lookup_name, expected_key, expect_raises):
    if expect_raises:
        with pytest.raises(ValueError):
            get_scope_key_for_hive(lookup_name, global_config)
    else:
        assert get_scope_key_for_hive(lookup_name, global_config) == expected_key


# ============================================================================
# Move Bee Tests
# ============================================================================


def test_move_bee_happy_path(isolated_bees_env):
    """Single bee moves from source hive to destination; result has bee in moved, dirs updated."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()


def test_move_bee_friendly_destination_hive_name(isolated_bees_env):
    """Friendly hive name (e.g. 'Hive_Dest') is normalized and accepted as destination."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")

    # HIVE_DESTINATION = "hive_dest" → display_name = "Hive_Dest" (via .title())
    friendly_name = HIVE_DESTINATION.title()  # "Hive_Dest"
    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], friendly_name)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()


def test_move_bee_destination_hive_not_found(isolated_bees_env):
    """Destination hive absent from config returns error with hive_not_found error_type."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.write_config()

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"


def test_move_bee_id_unchanged_after_move(isolated_bees_env):
    """After move, ticket file frontmatter id field matches original bee ID."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="ID Check Bee")

    _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    moved_file = dest_dir / TICKET_ID_MOVE_BEE_1 / f"{TICKET_ID_MOVE_BEE_1}.md"
    assert moved_file.exists()
    content = moved_file.read_text()
    assert f"id: {TICKET_ID_MOVE_BEE_1}" in content


def test_move_bee_child_tickets_present_in_destination(isolated_bees_env):
    """Nested child ticket dirs inside bee directory are moved intact to destination."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Parent Bee")
    write_ticket_file(
        source_dir / TICKET_ID_MOVE_BEE_1,
        TICKET_ID_MOVE_BEE_2,
        title="Nested Child",
        type="t1",
    )

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert (dest_dir / TICKET_ID_MOVE_BEE_1 / TICKET_ID_MOVE_BEE_2).exists()


def test_move_bee_already_in_destination_skipped(isolated_bees_env):
    """Bee already in destination hive appears in skipped; directory is untouched."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(dest_dir, TICKET_ID_MOVE_BEE_1, title="Already Here")
    ticket_file = dest_dir / TICKET_ID_MOVE_BEE_1 / f"{TICKET_ID_MOVE_BEE_1}.md"
    content_before = ticket_file.read_text()

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["skipped"] == [TICKET_ID_MOVE_BEE_1]
    assert ticket_file.read_text() == content_before


def test_move_bee_not_found(isolated_bees_env):
    """Bee ID absent from all hives appears in not_found; status is success."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["not_found"] == [TICKET_ID_MOVE_BEE_1]


def test_move_bee_simulated_failure(isolated_bees_env, monkeypatch):
    """shutil.move raising an exception puts bee in failed with the exception message as reason."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Will Fail")

    error_msg = "disk full"

    def fail_move(*args, **kwargs):
        raise OSError(error_msg)

    monkeypatch.setattr(shutil, "move", fail_move)

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert len(result["failed"]) == 1
    failed_entry = result["failed"][0]
    assert failed_entry["id"] == TICKET_ID_MOVE_BEE_1
    assert error_msg in failed_entry["reason"]


# ============================================================================
# Batch Move Tests
# ============================================================================


def test_move_bee_multiple_bees_success(isolated_bees_env):
    """Two bees move from source hive to destination; both in moved, source dirs gone, dest dirs exist."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="First Bee")
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_2, title="Second Bee")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1, TICKET_ID_MOVE_BEE_2], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert set(result["moved"]) == {TICKET_ID_MOVE_BEE_1, TICKET_ID_MOVE_BEE_2}
    assert result["skipped"] == []
    assert result["not_found"] == []
    assert result["failed"] == []
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert not (source_dir / TICKET_ID_MOVE_BEE_2).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_2).exists()


def test_move_bee_mixed_results(isolated_bees_env):
    """One bee moved, one already in dest (skipped), one nonexistent (not_found); each in correct list."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")
    write_ticket_file(dest_dir, TICKET_ID_MOVE_BEE_2, title="Already Here")
    nonexistent_id = "b.mv3"

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1, TICKET_ID_MOVE_BEE_2, nonexistent_id], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert result["skipped"] == [TICKET_ID_MOVE_BEE_2]
    assert result["not_found"] == [nonexistent_id]
    assert result["failed"] == []


def test_move_bee_batch_one_failure_continues(isolated_bees_env, monkeypatch):
    """shutil.move raises for first bee; first in failed, second still moves successfully."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Fail Bee")
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_2, title="Success Bee")

    original_move = shutil.move
    call_count = 0

    def fail_first_move(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("simulated failure")
        original_move(*args, **kwargs)

    monkeypatch.setattr(shutil, "move", fail_first_move)

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1, TICKET_ID_MOVE_BEE_2], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == TICKET_ID_MOVE_BEE_1
    assert result["moved"] == [TICKET_ID_MOVE_BEE_2]


def test_move_bee_empty_list(isolated_bees_env):
    """Empty bee_ids returns success immediately with all empty lists."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    result = _move_bee_core([], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["moved"] == []
    assert result["skipped"] == []
    assert result["not_found"] == []
    assert result["failed"] == []


# ============================================================================
# Validation Tests
# ============================================================================


@pytest.mark.parametrize(
    "bad_id,expected_reason_substr",
    [
        pytest.param("not-an-id", "malformed", id="malformed_id"),
        pytest.param(TICKET_ID_T1, "non-bee", id="non_bee_type"),
    ],
)
def test_move_bee_invalid_id_type(isolated_bees_env, bad_id, expected_reason_substr):
    """IDs that fail format or type validation land in failed with the appropriate reason."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    result = _move_bee_core([bad_id], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert len(result["failed"]) == 1
    failed_entry = result["failed"][0]
    assert failed_entry["id"] == bad_id
    assert expected_reason_substr in failed_entry["reason"]


def test_move_bee_cross_scope_rejection(isolated_bees_env):
    """Bee in scope A fails to move to hive in scope B; bee in failed with 'different scopes'."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_OTHER_SCOPE)

    # Write global config with two scope keys:
    # - "/nonexistent/scope_b" (listed first): contains HIVE_OTHER_SCOPE only
    # - str(env.base_path) (matches current repo root): contains BOTH hives
    #
    # load_bees_config() → matches str(env.base_path) → config.hives has both hives ✓
    # get_scope_key_for_hive(HIVE_OTHER_SCOPE) → finds it in "/nonexistent/scope_b" first
    # get_scope_key_for_hive(HIVE_TEST)        → not in scope_b, found in str(env.base_path)
    # source_scope != dest_scope → cross-scope rejection ✓
    global_config = {
        "schema_version": "2.0",
        "scopes": {
            "/nonexistent/scope_b": {
                "hives": {
                    HIVE_OTHER_SCOPE: {
                        "path": str(dest_dir),
                        "display_name": "Other Scope Hive",
                    }
                }
            },
            str(env.base_path): {
                "hives": {
                    HIVE_TEST: {
                        "path": str(source_dir),
                        "display_name": "Test Hive",
                    },
                    HIVE_OTHER_SCOPE: {
                        "path": str(dest_dir),
                        "display_name": "Other Scope Hive",
                    },
                }
            },
        },
    }
    (env.global_bees_dir / "config.json").write_text(json.dumps(global_config, indent=2))

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Cross Scope Bee")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_OTHER_SCOPE)

    assert result["status"] == "success"
    assert len(result["failed"]) == 1
    failed_entry = result["failed"][0]
    assert failed_entry["id"] == TICKET_ID_MOVE_BEE_1
    assert "different scopes" in failed_entry["reason"]


def test_move_bee_evicts_cache_entry_on_success(isolated_bees_env):
    """After successful move, the bee's cache entry is evicted."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_DESTINATION)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Cache Evict Bee")

    # Populate cache
    read_ticket(TICKET_ID_MOVE_BEE_1)
    assert cache.contains(TICKET_ID_MOVE_BEE_1)

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert not cache.contains(TICKET_ID_MOVE_BEE_1)


def test_move_bee_child_self_heals_after_move(isolated_bees_env):
    """Child ticket cache self-heals via stale-path detection after parent bee is moved."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    # Use a proper t1 ID that encodes the parent bee prefix (b.mv1 → t1.mv1.ab)
    child_t1_id = "t1.mv1.ab"

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Parent Bee")
    write_ticket_file(
        source_dir / TICKET_ID_MOVE_BEE_1,
        child_t1_id,
        title="Nested Child",
        type="t1",
    )

    # Populate cache for child (path points into source hive)
    read_ticket(child_t1_id)
    assert cache.contains(child_t1_id)

    # Move parent bee — child moves with it, parent cache evicted
    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]

    # Verify child landed in destination
    assert (dest_dir / TICKET_ID_MOVE_BEE_1 / child_t1_id).exists()

    # Read child by ID only — stale-path detection evicts old entry and discovers new path
    recovered = read_ticket(child_t1_id)
    assert recovered.id == child_t1_id


def test_move_bee_cemetery_destination(isolated_bees_env):
    """Moving to a hive named 'cemetery' returns error with cemetery_destination type; no file ops."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive("cemetery")
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Cemetery Bound")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], "cemetery")

    assert result["status"] == "error"
    assert result["error_type"] == "cemetery_destination"
    assert (source_dir / TICKET_ID_MOVE_BEE_1).exists()


# ===========================================================================
# Smoke tests: move_bee succeeds when destination hive has a corrupt ticket
# ===========================================================================


def test_move_bee_succeeds_when_dest_hive_has_corrupt_ticket(isolated_bees_env):
    """move_bee_core succeeds even when destination hive contains a corrupt sibling ticket."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_DESTINATION)
    env.write_config()

    # Valid bee to move
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Move Me")

    # Corrupt ticket in destination (malformed YAML, missing required fields)
    from tests.helpers import write_corrupt_ticket
    write_corrupt_ticket(dest_dir, TICKET_ID_CORRUPT_BEE)

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_DESTINATION)

    assert result["status"] == "success"
    assert TICKET_ID_MOVE_BEE_1 in result["moved"]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()


# ===========================================================================
# Compatibility Check Tests
# ===========================================================================


def test_move_bee_incompatible_status_values(isolated_bees_env):
    """Cross-hive move fails with compatibility_error when dest has restricted status_values
    and the source bee has a status not in that list. Bee is not moved."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open", "done"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Compat Test", status="worker")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert len(result["failed_bees"]) == 1
    failed = result["failed_bees"][0]
    assert failed["bee_id"] == TICKET_ID_MOVE_BEE_1
    assert "worker" in failed["incompatible_status_values"]
    assert failed["incompatible_tier_types"] == []
    assert (source_dir / TICKET_ID_MOVE_BEE_1).exists()


def test_move_bee_incompatible_tier_types(isolated_bees_env):
    """Cross-hive move fails with compatibility_error when dest hive has restricted
    child_tiers and source bee has a child with a tier type not in that config."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    # Dest hive only allows t1; source bee has a t2 child
    env.hives[HIVE_CLONE_DEST]["child_tiers"] = {"t1": ["Epic", "Epics"]}
    # Scope-level tiers include t2 so the child ticket can exist in source
    env.write_config(child_tiers={"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]})

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Parent Bee")
    write_ticket_file(
        source_dir / TICKET_ID_MOVE_BEE_1,
        TICKET_ID_MOVE_BEE_2,
        title="T2 Child",
        type="t2",
    )

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert len(result["failed_bees"]) == 1
    failed = result["failed_bees"][0]
    assert failed["bee_id"] == TICKET_ID_MOVE_BEE_1
    assert "t2" in failed["incompatible_tier_types"]
    assert failed["incompatible_status_values"] == []
    assert (source_dir / TICKET_ID_MOVE_BEE_1).exists()


def test_move_bee_batch_abort_on_one_failing(isolated_bees_env):
    """With three bees and one having an incompatible status, all moves are aborted.
    Error lists only the failing bee ID with its incompatible values."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open", "done"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Bee One", status="open")
    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_2, title="Bee Two", status="worker")
    write_ticket_file(source_dir, "b.mv3", title="Bee Three", status="open")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1, TICKET_ID_MOVE_BEE_2, "b.mv3"], HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert len(result["failed_bees"]) == 1
    assert result["failed_bees"][0]["bee_id"] == TICKET_ID_MOVE_BEE_2
    assert "worker" in result["failed_bees"][0]["incompatible_status_values"]
    # All bees remain in source — zero moves performed
    assert (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (source_dir / TICKET_ID_MOVE_BEE_2).exists()
    assert (source_dir / "b.mv3").exists()


def test_move_bee_force_bypass(isolated_bees_env):
    """With force=True, compatibility check is skipped and incompatible bee moves successfully."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open", "done"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Force Move", status="worker")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_CLONE_DEST, force=True)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()


def test_move_bee_same_hive_unaffected(isolated_bees_env):
    """Moving to same hive skips compatibility check; bee with non-allowed status is still skipped."""
    env = isolated_bees_env
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.write_config()

    # Bee already in dest hive with status not in allowed list
    write_ticket_file(dest_dir, TICKET_ID_MOVE_BEE_1, title="Same Hive Bee", status="worker")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_CLONE_DEST)

    assert result["status"] == "success"
    assert result["skipped"] == [TICKET_ID_MOVE_BEE_1]
    assert result["moved"] == []


def test_move_bee_compatible_cross_hive_unaffected(isolated_bees_env):
    """Compatible cross-hive move proceeds normally; no regression from compatibility check."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open", "done", "worker"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_MOVE_BEE_1, title="Compatible Bee", status="open")

    result = _move_bee_core([TICKET_ID_MOVE_BEE_1], HIVE_CLONE_DEST)

    assert result["status"] == "success"
    assert result["moved"] == [TICKET_ID_MOVE_BEE_1]
    assert not (source_dir / TICKET_ID_MOVE_BEE_1).exists()
    assert (dest_dir / TICKET_ID_MOVE_BEE_1).exists()
