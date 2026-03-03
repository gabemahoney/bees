"""Tests for _clone_bee_core() in src/mcp_clone_bee.py."""

import json

from src.mcp_clone_bee import _clone_bee_core
from src.reader import read_ticket
from tests.helpers import write_ticket_file
from tests.test_constants import (
    HIVE_CLONE_DEST,
    HIVE_TEST,
    TICKET_ID_CLONE_BEE_ROOT,
    TICKET_ID_CLONE_T1_1,
    TICKET_ID_CLONE_T1_2,
    TICKET_ID_NONEXISTENT,
    TICKET_ID_T1,
)

# ============================================================================
# Happy Path Tests
# ============================================================================


def test_clone_flat_bee(isolated_bees_env):
    """Clone a bee with no children: new ID, new GUID, new created_at; title/status/tags/description/egg identical."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(
        hive_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Clone Source",
        status="open",
        egg="https://example.com/spec.md",
        body="Source body content.",
        tags=["alpha", "beta"],
    )

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT)

    assert result["status"] == "success"
    assert result["written"] == 1
    assert result["failed"] == []

    new_id = result["ticket_id"]
    assert new_id != TICKET_ID_CLONE_BEE_ROOT
    assert new_id.startswith("b.")

    # Read cloned ticket and compare fields
    cloned = read_ticket(new_id)
    source = read_ticket(TICKET_ID_CLONE_BEE_ROOT)

    assert cloned.title == source.title
    assert cloned.status == source.status
    assert cloned.tags == source.tags
    assert cloned.egg == source.egg
    assert cloned.description == source.description

    # New values: id, guid, created_at must differ
    assert cloned.id != source.id
    assert cloned.guid != source.guid
    assert cloned.created_at != source.created_at


def test_clone_tree_with_children(isolated_bees_env):
    """Clone a bee with t1 children: all-new IDs; children list remapped; parent remapped."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    # Write source bee with children
    write_ticket_file(
        hive_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Parent Bee",
        children=[TICKET_ID_CLONE_T1_1, TICKET_ID_CLONE_T1_2],
    )

    # Write child tickets inside the bee directory
    bee_dir = hive_dir / TICKET_ID_CLONE_BEE_ROOT
    write_ticket_file(
        bee_dir,
        TICKET_ID_CLONE_T1_1,
        title="Child Task 1",
        type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT,
    )
    write_ticket_file(
        bee_dir,
        TICKET_ID_CLONE_T1_2,
        title="Child Task 2",
        type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT,
    )

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT)

    assert result["status"] == "success"
    assert result["written"] == 3
    assert result["failed"] == []

    new_root_id = result["ticket_id"]
    assert new_root_id != TICKET_ID_CLONE_BEE_ROOT

    # Read cloned root and verify children list has new IDs
    cloned_root = read_ticket(new_root_id)
    assert len(cloned_root.children) == 2
    for child_id in cloned_root.children:
        assert child_id != TICKET_ID_CLONE_T1_1
        assert child_id != TICKET_ID_CLONE_T1_2
        assert child_id.startswith("t1.")

    # Read cloned children and verify parent points to new root
    for child_id in cloned_root.children:
        cloned_child = read_ticket(child_id)
        assert cloned_child.parent == new_root_id
        assert cloned_child.guid != ""
        assert cloned_child.id != TICKET_ID_CLONE_T1_1
        assert cloned_child.id != TICKET_ID_CLONE_T1_2


def test_clone_preserves_external_cross_references(isolated_bees_env):
    """External up_dependencies and down_dependencies outside the tree are copied unchanged."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    external_dep = TICKET_ID_NONEXISTENT  # external reference, not in tree

    write_ticket_file(
        hive_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Dep Bee",
        up_dependencies=[external_dep],
        children=[TICKET_ID_CLONE_T1_1],
    )

    bee_dir = hive_dir / TICKET_ID_CLONE_BEE_ROOT
    write_ticket_file(
        bee_dir,
        TICKET_ID_CLONE_T1_1,
        title="Dep Child",
        type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT,
        down_dependencies=[external_dep],
    )

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT)

    assert result["status"] == "success"

    # External dep should be preserved unchanged on cloned root
    cloned_root = read_ticket(result["ticket_id"])
    assert external_dep in cloned_root.up_dependencies

    # External dep should be preserved unchanged on cloned child
    cloned_child_id = cloned_root.children[0]
    cloned_child = read_ticket(cloned_child_id)
    assert external_dep in cloned_child.down_dependencies


# ============================================================================
# Error Path Tests
# ============================================================================


def test_invalid_source_type(isolated_bees_env):
    """Passing a t1 ID returns invalid_source_type error."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.write_config()

    result = _clone_bee_core(TICKET_ID_T1)

    assert result["status"] == "error"
    assert result["error_type"] == "invalid_source_type"


def test_bee_not_found(isolated_bees_env):
    """Passing a nonexistent bee ID returns bee_not_found error."""
    env = isolated_bees_env
    env.create_hive(HIVE_TEST)
    env.write_config()

    result = _clone_bee_core(TICKET_ID_NONEXISTENT)

    assert result["status"] == "error"
    assert result["error_type"] == "bee_not_found"


# ============================================================================
# Write Failure Tests
# ============================================================================


def test_root_write_failure(isolated_bees_env, monkeypatch):
    """Root write failure returns clone_write_error; zero children written."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(hive_dir, TICKET_ID_CLONE_BEE_ROOT, title="Write Fail Bee")

    import src.mcp_clone_bee as clone_mod

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(clone_mod, "write_ticket_file", fail_write)

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT)

    assert result["status"] == "error"
    assert result["error_type"] == "clone_write_error"


def test_child_write_failure_best_effort(isolated_bees_env, monkeypatch):
    """Child write failure: status success, failed list has one entry, written count correct."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

    write_ticket_file(
        hive_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Parent Bee",
        children=[TICKET_ID_CLONE_T1_1],
    )

    bee_dir = hive_dir / TICKET_ID_CLONE_BEE_ROOT
    write_ticket_file(
        bee_dir,
        TICKET_ID_CLONE_T1_1,
        title="Child Task",
        type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT,
    )

    import src.mcp_clone_bee as clone_mod

    original_write = clone_mod.write_ticket_file
    call_count = 0

    def fail_second_write(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("child write failed")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(clone_mod, "write_ticket_file", fail_second_write)

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT)

    assert result["status"] == "success"
    assert result["written"] == 1  # only root written
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == TICKET_ID_CLONE_T1_1


# ============================================================================
# Cross-Hive Clone Tests
# ============================================================================


def test_clone_cross_hive_happy_path(isolated_bees_env):
    """Clone to compatible destination hive succeeds; source bee unchanged."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Cross Hive Source")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST)

    assert result["status"] == "success"
    assert result["written"] == 1
    assert result["failed"] == []

    new_id = result["ticket_id"]
    assert new_id.startswith("b.")
    assert new_id != TICKET_ID_CLONE_BEE_ROOT

    # Cloned bee in destination; source still exists
    assert (dest_dir / new_id).exists()
    assert (source_dir / TICKET_ID_CLONE_BEE_ROOT).exists()


def test_clone_incompatible_status_values(isolated_bees_env):
    """Dest hive restricts status values; source has status not in list -> compatibility_error."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Status Incompatible Bee", status="pupa")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert "pupa" in result["incompatible_status_values"]
    assert result["incompatible_tier_types"] == []


def test_clone_incompatible_tier_types(isolated_bees_env):
    """Dest hive restricts child_tiers; source tree has tier type not in config -> compatibility_error."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    # Scope has t1+t2; source tree has t2 grandchildren; dest hive only supports t1 -> t2 incompatible
    env.hives[HIVE_CLONE_DEST]["child_tiers"] = {"t1": ["Task", "Tasks"]}
    env.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Sub", "Subs"]})

    # Build: bee -> t1 child -> t2 grandchild
    t2_child_id = "t2.cn1.ab.cd"
    write_ticket_file(
        source_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Tier Incompatible Bee",
        children=[TICKET_ID_CLONE_T1_1],
    )
    bee_dir = source_dir / TICKET_ID_CLONE_BEE_ROOT
    write_ticket_file(
        bee_dir, TICKET_ID_CLONE_T1_1, title="Child Task", type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT, children=[t2_child_id],
    )
    t1_dir = bee_dir / TICKET_ID_CLONE_T1_1
    write_ticket_file(t1_dir, t2_child_id, title="Grandchild Sub", type="t2", parent=TICKET_ID_CLONE_T1_1)

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert "t2" in result["incompatible_tier_types"]
    assert result["incompatible_status_values"] == []


def test_clone_both_checks_fail(isolated_bees_env):
    """Both status and tier checks fail -> single compatibility_error with both lists populated."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.hives[HIVE_CLONE_DEST]["child_tiers"] = {"t1": ["Task", "Tasks"]}
    env.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Sub", "Subs"]})

    # Build: bee -> t1 child -> t2 grandchild; bee has incompatible status "pupa"
    t2_child_id = "t2.cn1.ab.cd"
    write_ticket_file(
        source_dir,
        TICKET_ID_CLONE_BEE_ROOT,
        title="Both Fail Bee",
        status="pupa",
        children=[TICKET_ID_CLONE_T1_1],
    )
    bee_dir = source_dir / TICKET_ID_CLONE_BEE_ROOT
    write_ticket_file(
        bee_dir, TICKET_ID_CLONE_T1_1, title="Child Task", type="t1",
        parent=TICKET_ID_CLONE_BEE_ROOT, children=[t2_child_id],
    )
    t1_dir = bee_dir / TICKET_ID_CLONE_T1_1
    write_ticket_file(t1_dir, t2_child_id, title="Grandchild Sub", type="t2", parent=TICKET_ID_CLONE_T1_1)

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "compatibility_error"
    assert "pupa" in result["incompatible_status_values"]
    assert "t2" in result["incompatible_tier_types"]


def test_clone_force_bypass(isolated_bees_env):
    """force=True bypasses compatibility check; clone succeeds despite incompatible dest."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)
    env.hives[HIVE_CLONE_DEST]["status_values"] = ["open"]
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Force Bypass Bee", status="pupa")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST, force=True)

    assert result["status"] == "success"
    assert result["written"] == 1
    assert (dest_dir / result["ticket_id"]).exists()


def test_clone_cross_scope_error(isolated_bees_env):
    """Cloning to hive in different scope returns cross_scope_error."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    dest_dir = env.create_hive(HIVE_CLONE_DEST)

    # Write global config with two scope keys:
    # - "/nonexistent/scope_b" (listed first): contains HIVE_CLONE_DEST only
    # - str(env.base_path): contains BOTH hives (used by load_bees_config)
    # get_scope_key_for_hive(HIVE_CLONE_DEST) finds it in "/nonexistent/scope_b" first
    # get_scope_key_for_hive(HIVE_TEST) not in scope_b, found in str(env.base_path)
    # source_scope != dest_scope -> cross_scope_error
    global_config = {
        "schema_version": "2.0",
        "scopes": {
            "/nonexistent/scope_b": {
                "hives": {
                    HIVE_CLONE_DEST: {"path": str(dest_dir), "display_name": "Clone Dest"},
                }
            },
            str(env.base_path): {
                "hives": {
                    HIVE_TEST: {"path": str(source_dir), "display_name": "Test Hive"},
                    HIVE_CLONE_DEST: {"path": str(dest_dir), "display_name": "Clone Dest"},
                },
                "child_tiers": {},
            },
        },
    }
    (env.global_bees_dir / "config.json").write_text(json.dumps(global_config, indent=2))

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Cross Scope Bee")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=HIVE_CLONE_DEST)

    assert result["status"] == "error"
    assert result["error_type"] == "cross_scope_error"


def test_clone_hive_not_found(isolated_bees_env):
    """Non-existent destination hive returns hive_not_found."""
    env = isolated_bees_env
    source_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(source_dir, TICKET_ID_CLONE_BEE_ROOT, title="Hive Not Found Bee")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive="nonexistent_hive")

    assert result["status"] == "error"
    assert result["error_type"] == "hive_not_found"


def test_clone_no_destination_same_hive(isolated_bees_env):
    """destination_hive=None clones into source hive (regression from Epic 1)."""
    env = isolated_bees_env
    hive_dir = env.create_hive(HIVE_TEST)
    env.write_config()

    write_ticket_file(hive_dir, TICKET_ID_CLONE_BEE_ROOT, title="Same Hive Source", status="open")

    result = _clone_bee_core(TICKET_ID_CLONE_BEE_ROOT, destination_hive=None)

    assert result["status"] == "success"
    assert result["written"] == 1
    assert (hive_dir / result["ticket_id"]).exists()
    assert (hive_dir / TICKET_ID_CLONE_BEE_ROOT).exists()
