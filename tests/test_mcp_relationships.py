"""
Unit tests for bidirectional relationship synchronization.

PURPOSE:
Tests the relationship sync logic that maintains bidirectional consistency
between parent/child and dependency relationships when tickets are created.

SCOPE - Tests that belong here:
- _update_bidirectional_relationships(): Main sync orchestration (creation-time)
- _add_child_to_parent(), _remove_child_from_parent(): Parent updates
- _set_parent_on_child(), _remove_parent_from_child(): Child updates
- _add_to_down_dependencies(), _remove_from_down_dependencies(): Dependency sync
- Sync behavior when adding/removing relationships
- Edge cases: orphaned tickets, missing references, circular updates
- Relationship consistency validation
- Multi-ticket sync scenarios

SCOPE - Tests that DON'T belong here:
- Ticket CRUD operations -> test_mcp_server.py, test_create_ticket.py
- Relationship validation at creation -> test_create_ticket.py
- Cycle detection -> test_linter_cycles.py
- Dependency type matching -> test_create_ticket.py
- Cascade deletion -> test_delete_ticket.py

RELATED FILES:
- test_mcp_server.py: Update operations that trigger sync
- test_create_ticket.py: Initial relationship setup
- test_linter.py: Bidirectional validation (verify sync worked)
- test_delete_ticket.py: Cascade deletion and cleanup
"""

from datetime import datetime
from pathlib import Path

import pytest

from src.id_utils import generate_guid

from src.mcp_relationships import (
    _add_child_to_parent,
    _add_to_down_dependencies,
    _add_to_up_dependencies,
    _remove_child_from_parent,
    _remove_from_down_dependencies,
    _remove_from_up_dependencies,
    _remove_parent_from_child,
    _requires_parent,
    _set_parent_on_child,
    _update_bidirectional_relationships,
)
from src.paths import get_ticket_path
from src.reader import read_ticket
from src.repo_context import repo_root_context
from src.writer import write_ticket_file
from tests.conftest import write_scoped_config
from tests.test_constants import (
    TICKET_ID_EP1,
    TICKET_ID_EP2,
    TICKET_ID_MCP_SUBTASK,
    TICKET_ID_MCP_TASK_A,
    TICKET_ID_MCP_TASK_B,
    TICKET_ID_NONEXISTENT,
    TITLE_TEST_BEE,
)


@pytest.fixture
def setup_hive(tmp_path, monkeypatch, mock_global_bees_dir):
    """Create temporary hive directory structure for testing."""
    monkeypatch.chdir(tmp_path)

    # Create default hive directory
    default_dir = tmp_path / "default"
    default_dir.mkdir()

    # Write scoped global config with default hive
    write_scoped_config(mock_global_bees_dir, tmp_path, {
        "hives": {
            "default": {"path": str(default_dir), "display_name": "Default", "created_at": datetime.now().isoformat()},
        },
        "child_tiers": {
            "t1": ["Task", "Tasks"],
            "t2": ["Subtask", "Subtasks"],
        },
    })

    with repo_root_context(tmp_path):
        yield tmp_path


def create_test_bee(ticket_id: str, children: list[str] | None = None):
    """Helper to create a test bee ticket."""
    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    frontmatter = {
        "id": ticket_id,
        "type": "bee",
        "title": f"Test Bee {ticket_id}",
        "children": children or [],
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "schema_version": "0.1",
        "egg": None,
        "guid": generate_guid(short_id),
    }
    write_ticket_file(ticket_id, "bee", frontmatter, f"Description for {ticket_id}", "default")


def create_test_task(ticket_id: str, parent: str | None = None, children: list[str] | None = None):
    """Helper to create a test t1 tier ticket (task equivalent)."""
    from src.config import load_bees_config
    from src.paths import compute_ticket_path

    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    segments = short_id.split(".")
    canonical_parent_bee = f"b.{segments[0]}"

    # Ensure canonical parent bee exists on disk so the file lands at the
    # correct hierarchical path (compute_ticket_path-derived).
    config = load_bees_config()
    hive_root = Path(config.hives["default"].path)
    parent_bee_path = compute_ticket_path(canonical_parent_bee, hive_root)
    if not parent_bee_path.exists():
        create_test_bee(canonical_parent_bee)

    canonical_path = compute_ticket_path(ticket_id, hive_root)
    frontmatter = {
        "id": ticket_id,
        "type": "t1",
        "title": f"Test Task {ticket_id}",
        "parent": parent,
        "children": children or [],
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "schema_version": "0.1",
        "guid": generate_guid(short_id),
    }
    write_ticket_file(ticket_id, "t1", frontmatter, f"Description for {ticket_id}", "default", file_path=canonical_path)


def create_test_subtask(ticket_id: str, parent: str):
    """Helper to create a test t2 tier ticket (subtask equivalent)."""
    from src.config import load_bees_config
    from src.paths import compute_ticket_path

    short_id = ticket_id.split(".", 1)[1] if "." in ticket_id else ticket_id
    segments = short_id.split(".")
    canonical_parent_bee = f"b.{segments[0]}"
    canonical_parent_t1 = f"t1.{'.'.join(segments[:2])}"

    config = load_bees_config()
    hive_root = Path(config.hives["default"].path)

    # Ensure canonical parent hierarchy exists on disk
    if not compute_ticket_path(canonical_parent_bee, hive_root).exists():
        create_test_bee(canonical_parent_bee)
    if not compute_ticket_path(canonical_parent_t1, hive_root).exists():
        create_test_task(canonical_parent_t1)

    canonical_path = compute_ticket_path(ticket_id, hive_root)
    frontmatter = {
        "id": ticket_id,
        "type": "t2",
        "title": f"Test Subtask {ticket_id}",
        "parent": parent,
        "up_dependencies": [],
        "down_dependencies": [],
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "schema_version": "0.1",
    }
    write_ticket_file(ticket_id, "t2", frontmatter, f"Description for {ticket_id}", "default", file_path=canonical_path)


class TestUpdateBidirectionalRelationships:
    """Tests for _update_bidirectional_relationships main function."""

    def test_update_with_parent(self, setup_hive):
        """Test updating parent relationship adds child to parent's children."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _update_bidirectional_relationships(new_ticket_id=TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1)

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A in parent_ticket.children

    def test_update_with_children(self, setup_hive):
        """Test updating children relationship sets parent on each child."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)
        create_test_task(TICKET_ID_MCP_TASK_B)

        _update_bidirectional_relationships(
            new_ticket_id=TICKET_ID_EP1, children=[TICKET_ID_MCP_TASK_A, TICKET_ID_MCP_TASK_B]
        )

        for child_id in [TICKET_ID_MCP_TASK_A, TICKET_ID_MCP_TASK_B]:
            child_path = get_ticket_path(child_id, "t1", "default")
            child_ticket = read_ticket(child_id, file_path=child_path)
            assert child_ticket.parent == TICKET_ID_EP1

    def test_update_with_up_dependencies(self, setup_hive):
        """Test updating up_dependencies adds to blocking ticket's down_dependencies."""
        create_test_bee(TICKET_ID_EP1)
        create_test_bee(TICKET_ID_EP2)

        _update_bidirectional_relationships(new_ticket_id=TICKET_ID_EP2, up_dependencies=[TICKET_ID_EP1])

        blocking_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        blocking_ticket = read_ticket(TICKET_ID_EP1, file_path=blocking_path)
        assert TICKET_ID_EP2 in blocking_ticket.down_dependencies

    def test_update_with_down_dependencies(self, setup_hive):
        """Test updating down_dependencies adds to blocked ticket's up_dependencies."""
        create_test_bee(TICKET_ID_EP1)
        create_test_bee(TICKET_ID_EP2)

        _update_bidirectional_relationships(new_ticket_id=TICKET_ID_EP1, down_dependencies=[TICKET_ID_EP2])

        blocked_path = get_ticket_path(TICKET_ID_EP2, "bee", "default")
        blocked_ticket = read_ticket(TICKET_ID_EP2, file_path=blocked_path)
        assert TICKET_ID_EP1 in blocked_ticket.up_dependencies

    def test_update_with_parent_and_hive_name(self, setup_hive):
        """Test _update_bidirectional_relationships works when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _update_bidirectional_relationships(
            new_ticket_id=TICKET_ID_MCP_TASK_A,
            parent=TICKET_ID_EP1,
            hive_name="default",
        )

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A in parent_ticket.children

    @pytest.mark.parametrize(
        "field,kwargs,match",
        [
            pytest.param("parent", {"parent": TICKET_ID_NONEXISTENT}, "Parent ticket not found", id="nonexistent_parent"),
            pytest.param("children", {"children": [TICKET_ID_NONEXISTENT]}, "Child ticket not found", id="nonexistent_child"),
        ],
    )
    def test_update_nonexistent_reference_raises_error(self, setup_hive, field, kwargs, match):
        """Test that referencing nonexistent parent/child raises ValueError."""
        if field == "parent":
            create_test_task(TICKET_ID_MCP_TASK_A)
            kwargs["new_ticket_id"] = TICKET_ID_MCP_TASK_A
        else:
            create_test_bee(TICKET_ID_EP1)
            kwargs["new_ticket_id"] = TICKET_ID_EP1

        with pytest.raises(ValueError, match=match):
            _update_bidirectional_relationships(**kwargs)


class TestAddChildToParent:
    """Tests for _add_child_to_parent helper function."""

    def test_add_child_to_parent_success(self, setup_hive):
        """Test successfully adding child to parent's children array."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _add_child_to_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1)

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A in parent_ticket.children

    def test_add_child_to_parent_with_hive_name(self, setup_hive):
        """Test _add_child_to_parent works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _add_child_to_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1, hive_name="default")

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A in parent_ticket.children

    def test_add_child_nonexistent_parent_raises_error(self, setup_hive):
        """Test that adding child to nonexistent parent raises ValueError."""
        create_test_task(TICKET_ID_MCP_TASK_A)

        with pytest.raises(ValueError, match="Parent ticket not found"):
            _add_child_to_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_NONEXISTENT)


class TestRemoveChildFromParent:
    """Tests for _remove_child_from_parent helper function."""

    def test_remove_child_from_parent_success(self, setup_hive):
        """Test successfully removing child from parent's children array."""
        create_test_bee(TICKET_ID_EP1, children=[TICKET_ID_MCP_TASK_A])
        create_test_task(TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1)

        _remove_child_from_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1)

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A not in parent_ticket.children

    def test_remove_child_from_parent_with_hive_name(self, setup_hive):
        """Test _remove_child_from_parent works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1, children=[TICKET_ID_MCP_TASK_A])
        create_test_task(TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1)

        _remove_child_from_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1, hive_name="default")

        parent_path = get_ticket_path(TICKET_ID_EP1, "bee", "default")
        parent_ticket = read_ticket(TICKET_ID_EP1, file_path=parent_path)
        assert TICKET_ID_MCP_TASK_A not in parent_ticket.children


class TestSetParentOnChild:
    """Tests for _set_parent_on_child helper function."""

    def test_set_parent_on_child_success(self, setup_hive):
        """Test successfully setting parent on child ticket."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _set_parent_on_child(TICKET_ID_EP1, TICKET_ID_MCP_TASK_A)

        child_path = get_ticket_path(TICKET_ID_MCP_TASK_A, "t1", "default")
        child_ticket = read_ticket(TICKET_ID_MCP_TASK_A, file_path=child_path)
        assert child_ticket.parent == TICKET_ID_EP1

    def test_set_parent_on_child_with_hive_name(self, setup_hive):
        """Test _set_parent_on_child works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A)

        _set_parent_on_child(TICKET_ID_EP1, TICKET_ID_MCP_TASK_A, hive_name="default")

        child_path = get_ticket_path(TICKET_ID_MCP_TASK_A, "t1", "default")
        child_ticket = read_ticket(TICKET_ID_MCP_TASK_A, file_path=child_path)
        assert child_ticket.parent == TICKET_ID_EP1


class TestRemoveParentFromChild:
    """Tests for _remove_parent_from_child helper function."""

    @pytest.mark.parametrize(
        "child_type,child_id,parent_id,parent_type,create_parent,create_child",
        [
            pytest.param("t1", TICKET_ID_MCP_TASK_A, TICKET_ID_EP1, "bee", create_test_bee, create_test_task, id="t1"),
            pytest.param("t2", TICKET_ID_MCP_SUBTASK, TICKET_ID_MCP_TASK_A, "t1", create_test_task, None, id="t2"),
        ],
    )
    def test_remove_parent_from_child_tier_not_allowed(self, setup_hive, child_type, child_id, parent_id, parent_type, create_parent, create_child):
        """Test that removing parent from child tiers is not allowed."""
        create_parent(parent_id)
        if child_type == "t1":
            create_child(child_id, parent=parent_id)
        else:
            create_test_subtask(child_id, parent=parent_id)

        _remove_parent_from_child(child_id)

        child_path = get_ticket_path(child_id, child_type, "default")
        child_ticket = read_ticket(child_id, file_path=child_path)
        assert child_ticket.parent == parent_id

    def test_remove_parent_from_child_with_hive_name(self, setup_hive):
        """Test _remove_parent_from_child works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_task(TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1)

        # t1 tickets require a parent — function is a no-op but must not raise
        _remove_parent_from_child(TICKET_ID_MCP_TASK_A, hive_name="default")

        child_path = get_ticket_path(TICKET_ID_MCP_TASK_A, "t1", "default")
        child_ticket = read_ticket(TICKET_ID_MCP_TASK_A, file_path=child_path)
        assert child_ticket.parent == TICKET_ID_EP1  # parent preserved (requires_parent)


class TestDependencyHelpers:
    """Tests for dependency helper functions."""

    @pytest.mark.parametrize(
        "add_fn,field",
        [
            pytest.param("down", "down_dependencies", id="add_down"),
            pytest.param("up", "up_dependencies", id="add_up"),
        ],
    )
    def test_add_dependency(self, setup_hive, add_fn, field):
        """Test adding ticket to dependency arrays."""
        create_test_bee(TICKET_ID_EP1)
        create_test_bee(TICKET_ID_EP2)

        if add_fn == "down":
            _add_to_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1)
            target_id, target_type = TICKET_ID_EP1, "bee"
            expected_value = TICKET_ID_EP2
        else:
            _add_to_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2)
            target_id, target_type = TICKET_ID_EP2, "bee"
            expected_value = TICKET_ID_EP1

        ticket = read_ticket(target_id, file_path=get_ticket_path(target_id, target_type, "default"))
        assert expected_value in getattr(ticket, field)

    @pytest.mark.parametrize(
        "remove_fn,field,pre_existing_field",
        [
            pytest.param("down", "down_dependencies", "down_dependencies", id="remove_down"),
            pytest.param("up", "up_dependencies", "up_dependencies", id="remove_up"),
        ],
    )
    def test_remove_dependency(self, setup_hive, remove_fn, field, pre_existing_field):
        """Test removing ticket from dependency arrays."""
        if remove_fn == "down":
            frontmatter = {
                "id": TICKET_ID_EP1, "type": "bee", "title": TITLE_TEST_BEE,
                "children": [], "up_dependencies": [], "down_dependencies": [TICKET_ID_EP2],
                "created_at": datetime.now().isoformat(),
                "status": "open", "schema_version": "0.1",
            }
            write_ticket_file(TICKET_ID_EP1, "bee", frontmatter, "Description", hive_name="default")
            create_test_bee(TICKET_ID_EP2)
            _remove_from_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1)
            target_id, removed_value = TICKET_ID_EP1, TICKET_ID_EP2
        else:
            frontmatter = {
                "id": TICKET_ID_EP2, "type": "bee", "title": TITLE_TEST_BEE,
                "children": [], "up_dependencies": [TICKET_ID_EP1], "down_dependencies": [],
                "created_at": datetime.now().isoformat(),
                "status": "open", "schema_version": "0.1",
            }
            write_ticket_file(TICKET_ID_EP2, "bee", frontmatter, "Description", hive_name="default")
            create_test_bee(TICKET_ID_EP1)
            _remove_from_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2)
            target_id, removed_value = TICKET_ID_EP2, TICKET_ID_EP1

        ticket = read_ticket(target_id, file_path=get_ticket_path(target_id, "bee", "default"))
        assert removed_value not in getattr(ticket, field)

    def test_add_down_dependency_with_hive_name(self, setup_hive):
        """Test _add_to_down_dependencies works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_bee(TICKET_ID_EP2)

        _add_to_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1, hive_name="default")

        ticket = read_ticket(TICKET_ID_EP1, file_path=get_ticket_path(TICKET_ID_EP1, "bee", "default"))
        assert TICKET_ID_EP2 in ticket.down_dependencies

    def test_add_up_dependency_with_hive_name(self, setup_hive):
        """Test _add_to_up_dependencies works correctly when hive_name is provided."""
        create_test_bee(TICKET_ID_EP1)
        create_test_bee(TICKET_ID_EP2)

        _add_to_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2, hive_name="default")

        ticket = read_ticket(TICKET_ID_EP2, file_path=get_ticket_path(TICKET_ID_EP2, "bee", "default"))
        assert TICKET_ID_EP1 in ticket.up_dependencies

    def test_remove_down_dependency_with_hive_name(self, setup_hive):
        """Test _remove_from_down_dependencies works correctly when hive_name is provided."""
        frontmatter = {
            "id": TICKET_ID_EP1, "type": "bee", "title": TITLE_TEST_BEE,
            "children": [], "up_dependencies": [], "down_dependencies": [TICKET_ID_EP2],
            "created_at": datetime.now().isoformat(),
            "status": "open", "schema_version": "0.1",
        }
        write_ticket_file(TICKET_ID_EP1, "bee", frontmatter, "Description", hive_name="default")
        create_test_bee(TICKET_ID_EP2)

        _remove_from_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1, hive_name="default")

        ticket = read_ticket(TICKET_ID_EP1, file_path=get_ticket_path(TICKET_ID_EP1, "bee", "default"))
        assert TICKET_ID_EP2 not in ticket.down_dependencies

    def test_remove_up_dependency_with_hive_name(self, setup_hive):
        """Test _remove_from_up_dependencies works correctly when hive_name is provided."""
        frontmatter = {
            "id": TICKET_ID_EP2, "type": "bee", "title": TITLE_TEST_BEE,
            "children": [], "up_dependencies": [TICKET_ID_EP1], "down_dependencies": [],
            "created_at": datetime.now().isoformat(),
            "status": "open", "schema_version": "0.1",
        }
        write_ticket_file(TICKET_ID_EP2, "bee", frontmatter, "Description", hive_name="default")
        create_test_bee(TICKET_ID_EP1)

        _remove_from_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2, hive_name="default")

        ticket = read_ticket(TICKET_ID_EP2, file_path=get_ticket_path(TICKET_ID_EP2, "bee", "default"))
        assert TICKET_ID_EP1 not in ticket.up_dependencies


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"parent": None}, id="null_parent"),
            pytest.param({"children": []}, id="empty_children"),
            pytest.param({"up_dependencies": [], "down_dependencies": []}, id="empty_deps"),
        ],
    )
    def test_empty_or_null_relationships_handled(self, setup_hive, kwargs):
        """Test that null/empty relationship values are handled gracefully."""
        if "parent" in kwargs:
            create_test_task(TICKET_ID_MCP_TASK_A)
            kwargs["new_ticket_id"] = TICKET_ID_MCP_TASK_A
        else:
            create_test_bee(TICKET_ID_EP1)
            kwargs["new_ticket_id"] = TICKET_ID_EP1

        # Should not raise error
        _update_bidirectional_relationships(**kwargs)


class TestRequiresParent:
    """Tests for _requires_parent helper function."""

    @pytest.mark.parametrize(
        "ticket_type,expected",
        [
            pytest.param("bee", False, id="bee"),
            pytest.param("unknown_type", False, id="unknown"),
        ],
    )
    def test_requires_parent_basic(self, setup_hive, ticket_type, expected):
        """Test _requires_parent for bee and unknown types."""
        assert _requires_parent(ticket_type) is expected

    def test_dynamic_tier_requires_parent_with_config(self, tmp_path, monkeypatch, mock_global_bees_dir):
        """Test that dynamic tiers (t1, t2) require parent based on config."""
        monkeypatch.chdir(tmp_path)

        default_dir = tmp_path / "default"
        default_dir.mkdir()

        write_scoped_config(mock_global_bees_dir, tmp_path, {
            "hives": {
                "default": {"path": str(default_dir), "display_name": "Default", "created_at": datetime.now().isoformat()},
            },
            "child_tiers": {
                "t1": ["Task", "Tasks"],
                "t2": ["Subtask", "Subtasks"],
            },
        })

        with repo_root_context(tmp_path):
            assert _requires_parent("t1") is True
            assert _requires_parent("t2") is True

    @pytest.mark.parametrize(
        "ticket_type,expected",
        [
            pytest.param("t1", False, id="t1_no_config"),
            pytest.param("t2", False, id="t2_no_config"),
        ],
    )
    def test_requires_parent_in_bees_only_system(self, tmp_path, monkeypatch, mock_global_bees_dir, ticket_type, expected):
        """Test _requires_parent in bees-only system (empty child_tiers)."""
        monkeypatch.chdir(tmp_path)

        default_dir = tmp_path / "default"
        default_dir.mkdir()

        write_scoped_config(mock_global_bees_dir, tmp_path, {
            "hives": {
                "default": {"path": str(default_dir), "display_name": "Default", "created_at": datetime.now().isoformat()},
            },
            "child_tiers": {},
        })

        with repo_root_context(tmp_path):
            assert _requires_parent(ticket_type) is expected


class TestHiveNameSkipsScan:
    """_find_hive_for_ticket is never called when hive_name is provided to any relationship helper."""

    @pytest.mark.parametrize(
        "setup_fn,call_fn",
        [
            pytest.param(
                lambda: (create_test_bee(TICKET_ID_EP1), create_test_task(TICKET_ID_MCP_TASK_A)),
                lambda: _update_bidirectional_relationships(
                    new_ticket_id=TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1, hive_name="default"
                ),
                id="update_bidirectional_relationships",
            ),
            pytest.param(
                lambda: (create_test_bee(TICKET_ID_EP1), create_test_task(TICKET_ID_MCP_TASK_A)),
                lambda: _add_child_to_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1, hive_name="default"),
                id="add_child_to_parent",
            ),
            pytest.param(
                lambda: (
                    create_test_bee(TICKET_ID_EP1, children=[TICKET_ID_MCP_TASK_A]),
                    create_test_task(TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1),
                ),
                lambda: _remove_child_from_parent(TICKET_ID_MCP_TASK_A, TICKET_ID_EP1, hive_name="default"),
                id="remove_child_from_parent",
            ),
            pytest.param(
                lambda: (create_test_bee(TICKET_ID_EP1), create_test_task(TICKET_ID_MCP_TASK_A)),
                lambda: _set_parent_on_child(TICKET_ID_EP1, TICKET_ID_MCP_TASK_A, hive_name="default"),
                id="set_parent_on_child",
            ),
            pytest.param(
                lambda: (
                    create_test_bee(TICKET_ID_EP1),
                    create_test_task(TICKET_ID_MCP_TASK_A, parent=TICKET_ID_EP1),
                ),
                lambda: _remove_parent_from_child(TICKET_ID_MCP_TASK_A, hive_name="default"),
                id="remove_parent_from_child",
            ),
            pytest.param(
                lambda: (create_test_bee(TICKET_ID_EP1), create_test_bee(TICKET_ID_EP2)),
                lambda: _add_to_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1, hive_name="default"),
                id="add_to_down_dependencies",
            ),
            pytest.param(
                lambda: (create_test_bee(TICKET_ID_EP1), create_test_bee(TICKET_ID_EP2)),
                lambda: _add_to_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2, hive_name="default"),
                id="add_to_up_dependencies",
            ),
            pytest.param(
                lambda: (
                    write_ticket_file(
                        TICKET_ID_EP1, "bee",
                        {
                            "id": TICKET_ID_EP1, "type": "bee", "title": TITLE_TEST_BEE,
                            "children": [], "up_dependencies": [], "down_dependencies": [TICKET_ID_EP2],
                            "created_at": datetime.now().isoformat(),
                            "status": "open", "schema_version": "0.1",
                        },
                        "Description",
                        hive_name="default",
                    ),
                    create_test_bee(TICKET_ID_EP2),
                ),
                lambda: _remove_from_down_dependencies(TICKET_ID_EP2, TICKET_ID_EP1, hive_name="default"),
                id="remove_from_down_dependencies",
            ),
            pytest.param(
                lambda: (
                    write_ticket_file(
                        TICKET_ID_EP2, "bee",
                        {
                            "id": TICKET_ID_EP2, "type": "bee", "title": TITLE_TEST_BEE,
                            "children": [], "up_dependencies": [TICKET_ID_EP1], "down_dependencies": [],
                            "created_at": datetime.now().isoformat(),
                            "status": "open", "schema_version": "0.1",
                        },
                        "Description",
                        hive_name="default",
                    ),
                    create_test_bee(TICKET_ID_EP1),
                ),
                lambda: _remove_from_up_dependencies(TICKET_ID_EP1, TICKET_ID_EP2, hive_name="default"),
                id="remove_from_up_dependencies",
            ),
        ],
    )
    def test_hive_name_skips_scan(self, setup_hive, setup_fn, call_fn):
        """When hive_name is provided, _find_hive_for_ticket is never called."""
        from unittest.mock import patch

        setup_fn()
        with patch("src.mcp_relationships._find_hive_for_ticket") as mock_scan:
            call_fn()
            mock_scan.assert_not_called()
