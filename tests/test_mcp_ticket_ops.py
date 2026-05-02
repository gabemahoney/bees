"""Unit tests for mcp_ticket_ops per-hive validation support."""

import pytest

from src.mcp_ticket_ops import (
    _append_ticket_body,
    _create_ticket,
    _get_status_values,
    _set_status_values,
    _show_ticket,
    _update_ticket,
    find_hive_for_ticket,
    validate_parent_tier_relationship,
    validate_ticket_type,
)
from src.validator import ValidationError
from src.paths import get_ticket_path
from src.reader import read_ticket
from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config, write_scoped_config
from tests.helpers import make_body_at_cap
from tests.test_constants import (
    BODY_MAX_LENGTH,
    HIVE_BACKEND,
    HIVE_FRONTEND,
    HIVE_TEST,
    TAG_BATCH_BAR,
    TAG_BATCH_BAZ,
    TAG_BATCH_FOO,
    TICKET_ID_NONEXISTENT,
)


@pytest.fixture(autouse=True)
def setup_repo_context(tmp_path, monkeypatch):
    """Set repo_root context and chdir to tmp_path for all tests."""
    monkeypatch.chdir(tmp_path)
    with repo_root_context(tmp_path):
        yield


class TestValidateTicketTypeWithHiveName:
    """Test validate_ticket_type with hive_name parameter for per-hive child_tiers."""

    def test_validate_with_hive_name_resolves_hive_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type uses hive-level child_tiers when hive_name provided."""
        # Setup: scope is bees-only, but hive "backend" has t1+t2
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
            "child_tiers": {},  # Scope is bees-only
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: "bee" is always valid
        validate_ticket_type("bee", hive_name=HIVE_BACKEND)

        # Test: tier IDs from hive config are valid
        validate_ticket_type("t1", hive_name=HIVE_BACKEND)
        validate_ticket_type("t2", hive_name=HIVE_BACKEND)

        # Test: types not in hive config are invalid
        with pytest.raises(ValidationError, match="Invalid type: t3"):
            validate_ticket_type("t3", hive_name=HIVE_BACKEND)

    def test_validate_with_hive_name_bees_only_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type with hive having child_tiers={} (bees-only)."""
        # Setup: hive "frontend" is explicitly bees-only (child_tiers={})
        scope_data = {
            "hives": {
                HIVE_FRONTEND: {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},  # Explicitly bees-only
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: "bee" is valid
        validate_ticket_type("bee", hive_name=HIVE_FRONTEND)

        # Test: all child tiers are invalid (bees-only hive)
        with pytest.raises(ValidationError, match="Invalid type: t1"):
            validate_ticket_type("t1", hive_name=HIVE_FRONTEND)

    def test_validate_with_hive_name_fallback_to_scope(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type falls back to scope-level child_tiers when hive has None."""
        # Setup: hive "frontend" has no child_tiers (None), scope has t1
        scope_data = {
            "hives": {
                HIVE_FRONTEND: {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    # No child_tiers key → falls through to scope level
                },
            },
            "child_tiers": {
                "t1": ["Story", "Stories"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: uses scope-level child_tiers
        validate_ticket_type("bee", hive_name=HIVE_FRONTEND)
        validate_ticket_type("t1", hive_name=HIVE_FRONTEND)

        # Test: t2 not in scope config
        with pytest.raises(ValidationError, match="Invalid type: t2"):
            validate_ticket_type("t2", hive_name=HIVE_FRONTEND)

    def test_validate_with_hive_name_multiple_hives_different_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type resolves different child_tiers per hive."""
        # Setup: two hives with different child_tiers
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                    },
                },
                HIVE_FRONTEND: {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Story", "Stories"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test backend: only t1/Epic valid
        validate_ticket_type("t1", hive_name=HIVE_BACKEND)

        with pytest.raises(ValidationError, match="Invalid type: t2"):
            validate_ticket_type("t2", hive_name=HIVE_BACKEND)

        # Test frontend: t1, t2 valid
        validate_ticket_type("t1", hive_name=HIVE_FRONTEND)
        validate_ticket_type("t2", hive_name=HIVE_FRONTEND)


class TestValidateTicketTypeBackwardCompat:
    """Test validate_ticket_type backward compatibility (no hive_name parameter)."""

    def test_validate_without_hive_name_uses_scope_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type without hive_name uses scope-level child_tiers."""
        # Setup: scope has t1+t2
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Epic", "Epics"],
                "t2": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: scope-level child_tiers are used
        validate_ticket_type("bee")  # No hive_name
        validate_ticket_type("t1")
        validate_ticket_type("t2")

        # Test: t3 not in scope config
        with pytest.raises(ValidationError, match="Invalid type: t3"):
            validate_ticket_type("t3")

    def test_validate_without_hive_name_scope_none_defaults_to_empty(self, tmp_path, mock_global_bees_dir):
        """Test validate_ticket_type without hive_name when scope child_tiers is None."""
        # Setup: scope has no child_tiers (None → should default to {})
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            # No child_tiers key → None → defaults to {}
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: only "bee" is valid (bees-only fallback)
        validate_ticket_type("bee")

        # Test: all child tiers are invalid
        with pytest.raises(ValidationError, match="Invalid type: t1"):
            validate_ticket_type("t1")


class TestValidateParentTierRelationshipWithHiveName:
    """Test validate_parent_tier_relationship with hive_name parameter for per-hive child_tiers."""

    def test_validate_with_hive_name_child_tier_requires_correct_parent(self, tmp_path, mock_global_bees_dir):
        """Test validate_parent_tier_relationship enforces correct parent tier for hive child tiers."""
        # Setup: hive "backend" has t1+t2
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: bee never requires parent
        assert validate_parent_tier_relationship("bee", None, None, hive_name=HIVE_BACKEND)

        # Test: t1 requires bee parent
        assert validate_parent_tier_relationship("t1", "b.Abc", "bee", hive_name=HIVE_BACKEND)

        with pytest.raises(ValueError, match="t1 ticket must have bee parent, got None"):
            validate_parent_tier_relationship("t1", None, None, hive_name=HIVE_BACKEND)

        # Test: t2 requires t1 parent
        assert validate_parent_tier_relationship("t2", "t1.XYZ", "t1", hive_name=HIVE_BACKEND)

        with pytest.raises(ValueError, match="t2 ticket must have t1 parent, got bee"):
            validate_parent_tier_relationship("t2", "b.Abc", "bee", hive_name=HIVE_BACKEND)

    def test_validate_with_hive_name_bees_only_hive(self, tmp_path, mock_global_bees_dir):
        """Test validate_parent_tier_relationship with bees-only hive (child_tiers={})."""
        # Setup: hive "frontend" is bees-only
        scope_data = {
            "hives": {
                HIVE_FRONTEND: {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: bee never requires parent
        assert validate_parent_tier_relationship("bee", None, None, hive_name=HIVE_FRONTEND)

        # Test: unknown types (not in child_tiers) don't trigger validation error
        # since they're not configured child tiers
        assert validate_parent_tier_relationship("t1", None, None, hive_name=HIVE_FRONTEND)

    def test_validate_with_hive_name_fallback_to_scope(self, tmp_path, mock_global_bees_dir):
        """Test validate_parent_tier_relationship falls back to scope-level child_tiers."""
        # Setup: hive has no child_tiers, scope has t1
        scope_data = {
            "hives": {
                HIVE_FRONTEND: {
                    "path": "tickets/frontend/",
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Story", "Stories"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: uses scope-level child_tiers
        assert validate_parent_tier_relationship("t1", "b.Abc", "bee", hive_name=HIVE_FRONTEND)

        with pytest.raises(ValueError, match="t1 ticket must have bee parent, got None"):
            validate_parent_tier_relationship("t1", None, None, hive_name=HIVE_FRONTEND)


class TestValidateParentTierRelationshipBackwardCompat:
    """Test validate_parent_tier_relationship backward compatibility (no hive_name parameter)."""

    def test_validate_without_hive_name_uses_scope_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test validate_parent_tier_relationship without hive_name uses scope-level child_tiers."""
        # Setup: scope has t1+t2
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": "tickets/backend/",
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
            "child_tiers": {
                "t1": ["Epic", "Epics"],
                "t2": ["Task", "Tasks"],
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: scope-level child_tiers enforce parent requirement
        assert validate_parent_tier_relationship("t1", "b.Abc", "bee")  # No hive_name

        with pytest.raises(ValueError, match="t1 ticket must have bee parent, got None"):
            validate_parent_tier_relationship("t1", None, None)


class TestCreateTicketWithPerHiveChildTiers:
    """Test _create_ticket with per-hive child_tiers configurations."""

    async def test_create_ticket_in_hive_with_different_child_tiers_than_scope(self, tmp_path, mock_global_bees_dir):
        """Test _create_ticket in hive with child_tiers different from scope."""
        # Setup: scope is bees-only, backend hive has t1+t2
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
            "child_tiers": {},  # Scope is bees-only
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: can create bee in backend hive
        bee_result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
        )
        assert bee_result["status"] == "success"
        bee_id = bee_result["ticket_id"]

        # Test: can create t1 in backend hive (allowed by hive config)
        t1_result = await _create_ticket(
            ticket_type="t1",
            title="Test Epic",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert t1_result["status"] == "success"
        t1_id = t1_result["ticket_id"]
        assert t1_id.startswith("t1.")

        # Test: can create t2 in backend hive
        t2_result = await _create_ticket(
            ticket_type="t2",
            title="Test Task",
            parent=t1_id,
            hive_name=HIVE_BACKEND,
        )
        assert t2_result["status"] == "success"
        t2_id = t2_result["ticket_id"]
        assert t2_id.startswith("t2.")

        # Verify tickets exist on filesystem
        bee_path = get_ticket_path(bee_id, "bee", HIVE_BACKEND)
        assert bee_path.exists()
        t1_path = get_ticket_path(t1_id, "t1", HIVE_BACKEND)
        assert t1_path.exists()
        t2_path = get_ticket_path(t2_id, "t2", HIVE_BACKEND)
        assert t2_path.exists()

    async def test_create_ticket_in_bees_only_hive_rejects_child_tiers(self, tmp_path, mock_global_bees_dir):
        """Test _create_ticket in bees-only hive rejects child tier types."""
        # Setup: frontend hive is bees-only, scope has t1
        frontend_path = tmp_path / "tickets" / "frontend"
        frontend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_FRONTEND: {
                    "path": str(frontend_path),
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {},  # Bees-only hive
                },
            },
            "child_tiers": {
                "t1": ["Story", "Stories"],  # Scope has t1
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test: can create bee in frontend hive
        bee_result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_FRONTEND,
        )
        assert bee_result["status"] == "success"
        bee_id = bee_result["ticket_id"]

        # Test: cannot create t1 in frontend hive (bees-only)
        result = await _create_ticket(
            ticket_type="t1",
            title="Test Story",
            parent=bee_id,
            hive_name=HIVE_FRONTEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"

    async def test_create_ticket_validates_parent_tier_per_hive(self, tmp_path, mock_global_bees_dir):
        """Test _create_ticket validates parent tier relationship using hive config."""
        # Setup: backend hive has t1+t2
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Create parent tickets
        bee_result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
        )
        bee_id = bee_result["ticket_id"]

        t1_result = await _create_ticket(
            ticket_type="t1",
            title="Test Epic",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        t1_id = t1_result["ticket_id"]

        # Test: t2 with t1 parent succeeds
        t2_result = await _create_ticket(
            ticket_type="t2",
            title="Test Task",
            parent=t1_id,
            hive_name=HIVE_BACKEND,
        )
        assert t2_result["status"] == "success"

        # Test: t2 with bee parent fails (wrong tier)
        result = await _create_ticket(
            ticket_type="t2",
            title="Test Task Wrong Parent",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_parent"

    async def test_create_ticket_with_multiple_hives_different_configs(self, tmp_path, mock_global_bees_dir):
        """Test _create_ticket works correctly with multiple hives having different configs."""
        # Setup: backend has t1 only, frontend has t1+t2
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)
        frontend_path = tmp_path / "tickets" / "frontend"
        frontend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                    },
                },
                HIVE_FRONTEND: {
                    "path": str(frontend_path),
                    "display_name": "Frontend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Story", "Stories"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Test backend: t1 allowed, t2 not allowed
        backend_bee = await _create_ticket(
            ticket_type="bee",
            title="Backend Bee",
            hive_name=HIVE_BACKEND,
        )
        backend_bee_id = backend_bee["ticket_id"]

        backend_t1 = await _create_ticket(
            ticket_type="t1",
            title="Backend Epic",
            parent=backend_bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert backend_t1["status"] == "success"

        result = await _create_ticket(
            ticket_type="t2",
            title="Backend Task",
            parent=backend_t1["ticket_id"],
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"

        # Test frontend: both t1 and t2 allowed
        frontend_bee = await _create_ticket(
            ticket_type="bee",
            title="Frontend Bee",
            hive_name=HIVE_FRONTEND,
        )
        frontend_bee_id = frontend_bee["ticket_id"]

        frontend_t1 = await _create_ticket(
            ticket_type="t1",
            title="Frontend Story",
            parent=frontend_bee_id,
            hive_name=HIVE_FRONTEND,
        )
        frontend_t1_id = frontend_t1["ticket_id"]
        assert frontend_t1["status"] == "success"

        frontend_t2 = await _create_ticket(
            ticket_type="t2",
            title="Frontend Task",
            parent=frontend_t1_id,
            hive_name=HIVE_FRONTEND,
        )
        assert frontend_t2["status"] == "success"


class TestCreateTicketFriendlyNames:
    """Regression tests for b.bAU: create_ticket accepts friendly tier names."""

    @pytest.fixture
    def hive_with_task_tiers(self, tmp_path, mock_global_bees_dir):
        """Backend hive with t1=Task/Tasks and t2=Subtask/Subtasks."""
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)
        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Task", "Tasks"],
                        "t2": ["Subtask", "Subtasks"],
                    },
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

    @pytest.mark.parametrize("ticket_type", [
        pytest.param("Task", id="singular_friendly_name"),
        pytest.param("Tasks", id="plural_friendly_name"),
        pytest.param("t1", id="canonical_tier_id"),
    ])
    async def test_create_ticket_resolves_to_canonical_id(self, ticket_type, hive_with_task_tiers):
        """Task, Tasks, and t1 all succeed and return ticket_type='t1'."""
        bee_result = await _create_ticket(
            ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND
        )
        bee_id = bee_result["ticket_id"]

        result = await _create_ticket(
            ticket_type=ticket_type, title="Test Task", parent=bee_id, hive_name=HIVE_BACKEND
        )
        assert result["status"] == "success"
        assert result["ticket_type"] == "t1"
        assert result["ticket_id"].startswith("t1.")

    async def test_create_ticket_t2_friendly_name_resolves_to_canonical(self, hive_with_task_tiers):
        """'Subtask' friendly name resolves to canonical ticket_type='t2'."""
        bee_result = await _create_ticket(
            ticket_type="bee", title="Parent Bee", hive_name=HIVE_BACKEND
        )
        t1_result = await _create_ticket(
            ticket_type="Task", title="Parent Task", parent=bee_result["ticket_id"], hive_name=HIVE_BACKEND
        )
        result = await _create_ticket(
            ticket_type="Subtask", title="Test Subtask", parent=t1_result["ticket_id"], hive_name=HIVE_BACKEND
        )
        assert result["status"] == "success"
        assert result["ticket_type"] == "t2"
        assert result["ticket_id"].startswith("t2.")

    async def test_create_ticket_invalid_friendly_name_returns_error(self, hive_with_task_tiers):
        """Unknown friendly name 'Bogus' returns error dict."""
        result = await _create_ticket(
            ticket_type="Bogus", title="Test Task", parent="b.fake", hive_name=HIVE_BACKEND
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_type"
        assert "Bogus" in result["message"]


class TestFindHiveForTicketExclusion:
    """Tests for find_hive_for_ticket excluding cemetery and special directories."""

    @pytest.mark.parametrize(
        "subdir,ticket_id,title,body_suffix",
        [
            ("cemetery", "b.ded", "Buried", "Buried."),
            ("eggs", "b.egg", "Egg", "Body."),
        ],
        ids=["cemetery", "eggs"],
    )
    def test_returns_none_for_ticket_in_excluded_subdir(
        self, tmp_path, mock_global_bees_dir, subdir, ticket_id, title, body_suffix
    ):
        """find_hive_for_ticket should not find tickets inside excluded subdirectories."""
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        excluded_dir = backend_path / subdir / ticket_id
        excluded_dir.mkdir(parents=True)
        (excluded_dir / f"{ticket_id}.md").write_text(
            f"---\nid: {ticket_id}\nschema_version: '1.1'\ntype: bee\ntitle: {title}\n---\n{body_suffix}"
        )

        assert find_hive_for_ticket(ticket_id) is None

    def test_returns_hive_for_active_ticket(self, tmp_path, mock_global_bees_dir):
        """find_hive_for_ticket should find tickets at hive root level."""
        backend_path = tmp_path / "tickets" / "backend"
        backend_path.mkdir(parents=True)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                },
            },
        }
        write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)

        # Create active ticket at hive root
        ticket_dir = backend_path / "b.act"
        ticket_dir.mkdir(parents=True)
        (ticket_dir / "b.act.md").write_text(
            "---\nid: b.act\nschema_version: '1.1'\ntype: bee\ntitle: Active\n---\nBody."
        )

        assert find_hive_for_ticket("b.act") == HIVE_BACKEND


class TestBatchUpdateTicket:
    """Tests for the list[str] batch-update path of _update_ticket (SR-9.4)."""

    async def test_batch_status_update_multiple_tickets(self, isolated_bees_env):
        """Batch status update on 3+ ticket IDs returns batch format with all in updated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        ids = []
        for i in range(3):
            result = await _create_ticket(ticket_type="bee", title=f"Batch Bee {i}", hive_name=HIVE_BACKEND)
            ids.append(result["ticket_id"])

        result = await _update_ticket(ticket_ids=ids, status="in_progress")

        assert result["status"] == "success"
        assert set(result["updated"]) == set(ids)
        assert result["not_found"] == []
        assert result["failed"] == []

        for tid in ids:
            ticket_type_str = "bee"
            ticket = read_ticket(tid, file_path=get_ticket_path(tid, ticket_type_str, HIVE_BACKEND))
            assert ticket.status == "in_progress"

    async def test_batch_add_tags_including_duplicate(self, isolated_bees_env):
        """add_tags on a list of IDs; one ticket already has the tag — still in updated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r1 = await _create_ticket(ticket_type="bee", title="Bee One", hive_name=HIVE_BACKEND)
        r2 = await _create_ticket(
            ticket_type="bee", title="Bee Two", tags=[TAG_BATCH_FOO], hive_name=HIVE_BACKEND
        )
        ids = [r1["ticket_id"], r2["ticket_id"]]

        result = await _update_ticket(ticket_ids=ids, add_tags=[TAG_BATCH_FOO])

        assert result["status"] == "success"
        assert set(result["updated"]) == set(ids)
        assert result["not_found"] == []
        assert result["failed"] == []

        for tid in ids:
            ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
            assert TAG_BATCH_FOO in ticket.tags

    async def test_batch_remove_tags_including_missing(self, isolated_bees_env):
        """remove_tags on a list of IDs; one ticket lacks the tag — still in updated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r1 = await _create_ticket(
            ticket_type="bee", title="Has Tag", tags=[TAG_BATCH_BAR], hive_name=HIVE_BACKEND
        )
        r2 = await _create_ticket(ticket_type="bee", title="No Tag", hive_name=HIVE_BACKEND)
        ids = [r1["ticket_id"], r2["ticket_id"]]

        result = await _update_ticket(ticket_ids=ids, remove_tags=[TAG_BATCH_BAR])

        assert result["status"] == "success"
        assert set(result["updated"]) == set(ids)
        assert result["not_found"] == []
        assert result["failed"] == []

        for tid in ids:
            ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
            assert TAG_BATCH_BAR not in (ticket.tags or [])

    async def test_batch_combined_status_add_remove_tags(self, isolated_bees_env):
        """add_tags and remove_tags combined with status change in a single batch call."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r1 = await _create_ticket(
            ticket_type="bee", title="Combo Bee One",
            tags=[TAG_BATCH_BAR], hive_name=HIVE_BACKEND,
        )
        r2 = await _create_ticket(
            ticket_type="bee", title="Combo Bee Two",
            tags=[TAG_BATCH_BAR], hive_name=HIVE_BACKEND,
        )
        ids = [r1["ticket_id"], r2["ticket_id"]]

        result = await _update_ticket(
            ticket_ids=ids,
            status="in_progress",
            add_tags=[TAG_BATCH_FOO],
            remove_tags=[TAG_BATCH_BAR],
        )

        assert result["status"] == "success"
        assert set(result["updated"]) == set(ids)

        for tid in ids:
            ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
            assert ticket.status == "in_progress"
            assert TAG_BATCH_FOO in ticket.tags
            assert TAG_BATCH_BAR not in ticket.tags

    async def test_batch_add_and_remove_same_tag_ends_up_removed(self, isolated_bees_env):
        """Same tag in both add_tags and remove_tags — tag ends up removed."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r1 = await _create_ticket(ticket_type="bee", title="Conflict Bee", hive_name=HIVE_BACKEND)
        ids = [r1["ticket_id"]]

        result = await _update_ticket(
            ticket_ids=ids,
            add_tags=[TAG_BATCH_BAZ],
            remove_tags=[TAG_BATCH_BAZ],
        )

        assert result["status"] == "success"
        assert ids[0] in result["updated"]

        ticket = read_ticket(ids[0], file_path=get_ticket_path(ids[0], "bee", HIVE_BACKEND))
        assert TAG_BATCH_BAZ not in (ticket.tags or [])

    async def test_batch_empty_list_returns_noop_success(self, isolated_bees_env):
        """Empty ticket_id list returns no-op success with all arrays empty."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _update_ticket(ticket_ids=[], status="in_progress")

        assert result == {"status": "success", "updated": [], "not_found": [], "failed": []}

    async def test_batch_duplicate_ids_deduplicated_in_response(self, isolated_bees_env):
        """Duplicate IDs in input — each ID appears once in updated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r = await _create_ticket(ticket_type="bee", title="Dedup Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _update_ticket(ticket_ids=[tid, tid, tid], status="in_progress")

        assert result["status"] == "success"
        assert result["updated"].count(tid) == 1
        assert result["not_found"] == []
        assert result["failed"] == []

    async def test_batch_mix_valid_and_nonexistent_ids(self, isolated_bees_env):
        """Mix of valid and non-existent IDs: valid updated, non-existent in not_found."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r = await _create_ticket(ticket_type="bee", title="Real Bee", hive_name=HIVE_BACKEND)
        real_id = r["ticket_id"]
        fake_id = TICKET_ID_NONEXISTENT

        result = await _update_ticket(ticket_ids=[real_id, fake_id], status="in_progress")

        assert result["status"] == "success"
        assert real_id in result["updated"]
        assert fake_id in result["not_found"]
        assert result["failed"] == []

        ticket = read_ticket(real_id, file_path=get_ticket_path(real_id, "bee", HIVE_BACKEND))
        assert ticket.status == "in_progress"

    async def test_batch_non_batchable_field_returns_error_no_updates(self, isolated_bees_env):
        """Non-batchable field (title) with list of IDs returns error dict; no updates performed."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r1 = await _create_ticket(ticket_type="bee", title="Original One", hive_name=HIVE_BACKEND)
        r2 = await _create_ticket(ticket_type="bee", title="Original Two", hive_name=HIVE_BACKEND)
        ids = [r1["ticket_id"], r2["ticket_id"]]

        update_result = await _update_ticket(ticket_ids=ids, title="Attempted Title Change")
        assert update_result["status"] == "error"
        assert update_result["error_type"] == "invalid_field"
        assert "title" in update_result["message"]

        # Verify no updates were applied
        for tid, original_title in [(r1["ticket_id"], "Original One"), (r2["ticket_id"], "Original Two")]:
            ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
            assert ticket.title == original_title

    async def test_single_string_returns_new_batch_format(self, isolated_bees_env):
        """Single-string ticket_id returns new batch response format, not legacy."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r = await _create_ticket(ticket_type="bee", title="Single Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _update_ticket(ticket_ids=tid, status="in_progress")

        assert result["status"] == "success"
        assert "updated" in result
        assert tid in result["updated"]
        assert "not_found" in result
        assert "failed" in result
        # Must NOT be legacy shape
        assert "ticket_type" not in result
        assert "title" not in result

    async def test_ticket_ids_keyword_accepted(self, isolated_bees_env):
        """Regression: calling _update_ticket with ticket_ids= keyword must succeed."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r = await _create_ticket(ticket_type="bee", title="KW Regression Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _update_ticket(ticket_ids=[tid], status="finished")

        assert result["status"] == "success"
        assert tid in result["updated"]


# ===========================================================================
# Smoke tests: operations on valid ticket succeed when hive has corrupt sibling
# ===========================================================================


from tests.helpers import write_corrupt_ticket as _write_corrupt_ticket


class TestValidateDepsViaUpdate:
    """Tests for dependency validation in single-ticket updates (exercises _validate_deps)."""

    async def test_nonexistent_up_dependency_raises(self, isolated_bees_env):
        """Updating up_dependencies with non-existent ticket ID returns error dict."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _create_ticket(ticket_type="bee", title="Dep Test Bee", hive_name=HIVE_BACKEND)
        tid = result["ticket_id"]

        result = await _update_ticket(tid, up_dependencies=[TICKET_ID_NONEXISTENT], hive_name=HIVE_BACKEND)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_dependency"
        assert "Dependency ticket does not exist" in result["message"]

    async def test_cross_type_up_dependency_raises(self, isolated_bees_env):
        """Updating bee's up_dependencies with a t1 ticket ID returns error dict."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        bee_result = await _create_ticket(ticket_type="bee", title="Bee A", hive_name=HIVE_BACKEND)
        bee_id = bee_result["ticket_id"]

        t1_result = await _create_ticket(
            ticket_type="t1", title="Task A", parent=bee_id, hive_name=HIVE_BACKEND
        )
        t1_id = t1_result["ticket_id"]

        result = await _update_ticket(bee_id, up_dependencies=[t1_id], hive_name=HIVE_BACKEND)
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_dependency"
        assert "Cross-type dependency" in result["message"]


class TestResolveHiveViaUpdate:
    """Tests for hive resolution in single-ticket updates (exercises _resolve_hive)."""

    async def test_invalid_hive_name_raises(self, isolated_bees_env):
        """Explicit hive_name not in config raises ValueError."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _create_ticket(ticket_type="bee", title="Hive Test Bee", hive_name=HIVE_BACKEND)
        tid = result["ticket_id"]

        result = await _update_ticket(tid, status="in_progress", hive_name="nonexistent_hive")
        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"
        assert "not found in configuration" in result["message"]

    async def test_ticket_not_in_any_hive_raises(self, isolated_bees_env):
        """Updating non-existent ticket without hive_name returns error dict."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _update_ticket(TICKET_ID_NONEXISTENT, status="in_progress")
        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "Ticket not found" in result["message"]


class TestUpdateTicketRefactorRegression:
    """Regression tests: ensures refactored _update_ticket_single/_update_ticket_batch preserves original behavior."""

    async def test_single_update_multiple_fields_persisted(self, isolated_bees_env):
        """Regression test: ensures refactored _update_ticket_single preserves original behavior.

        Updates title, description, status, and tags in a single call and verifies
        all changes persist to disk.
        """
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _create_ticket(
            ticket_type="bee", title="Original Title", body="Original desc", hive_name=HIVE_BACKEND
        )
        tid = result["ticket_id"]

        update_result = await _update_ticket(
            tid,
            title="Updated Title",
            body="Updated desc",
            status="in_progress",
            tags=["alpha", "beta"],
            hive_name=HIVE_BACKEND,
        )

        assert update_result["status"] == "success"
        assert tid in update_result["updated"]

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.title == "Updated Title"
        assert ticket.body == "Updated desc"
        assert ticket.status == "in_progress"
        assert set(ticket.tags) == {"alpha", "beta"}

    async def test_single_update_up_dependencies_bidirectional_sync(self, isolated_bees_env):
        """Regression test: ensures refactored _update_ticket_single preserves bidirectional dep sync.

        Sets up_dependencies on ticket A pointing to ticket B, then verifies B's
        down_dependencies includes A.
        """
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r_a = await _create_ticket(ticket_type="bee", title="Bee A", hive_name=HIVE_BACKEND)
        r_b = await _create_ticket(ticket_type="bee", title="Bee B", hive_name=HIVE_BACKEND)
        id_a = r_a["ticket_id"]
        id_b = r_b["ticket_id"]

        await _update_ticket(id_a, up_dependencies=[id_b], hive_name=HIVE_BACKEND)

        # Verify A has up_dependencies = [B]
        ticket_a = read_ticket(id_a, file_path=get_ticket_path(id_a, "bee", HIVE_BACKEND))
        assert id_b in ticket_a.up_dependencies

        # Verify B has down_dependencies = [A] (bidirectional sync)
        ticket_b = read_ticket(id_b, file_path=get_ticket_path(id_b, "bee", HIVE_BACKEND))
        assert id_a in ticket_b.down_dependencies


# ===========================================================================
# Smoke tests: operations on valid ticket succeed when hive has corrupt sibling
# ===========================================================================


class TestTicketOpsWithCorruptSibling:
    """Smoke tests: gate removal lets valid-ticket ops proceed despite corrupt hive siblings."""

    async def test_create_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """create_ticket succeeds when hive contains a corrupt sibling ticket."""
        from src.mcp_ticket_ops import _create_ticket
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        _write_corrupt_ticket(hive_dir, "b.crp")

        result = await _create_ticket("bee", "Valid New Bee", HIVE_BACKEND)
        assert result["status"] == "success"
        assert "ticket_id" in result

    async def test_show_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """show_ticket on a valid ticket succeeds when hive has a corrupt sibling."""
        from src.mcp_ticket_ops import _show_ticket
        from tests.helpers import write_ticket_file
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")
        _write_corrupt_ticket(hive_dir, "b.crp")

        result = await _show_ticket(["b.vet"])
        assert result["status"] == "success"
        assert result["tickets"][0]["ticket_id"] == "b.vet"

    async def test_update_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """update_ticket on a valid ticket succeeds when hive has a corrupt sibling."""
        from src.mcp_ticket_ops import _update_ticket
        from tests.helpers import write_ticket_file
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")
        _write_corrupt_ticket(hive_dir, "b.crp")

        result = await _update_ticket("b.vet", status="in_progress", hive_name=HIVE_BACKEND)
        assert result["status"] == "success"
        assert "b.vet" in result["updated"]

    async def test_delete_succeeds_with_corrupt_sibling(self, isolated_bees_env):
        """delete_ticket on a valid ticket succeeds when hive has a corrupt sibling."""
        from src.mcp_ticket_ops import _delete_ticket
        from tests.helpers import write_ticket_file
        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        write_ticket_file(hive_dir, "b.vet", title="Valid Bee")
        _write_corrupt_ticket(hive_dir, "b.crp")

        result = await _delete_ticket("b.vet", hive_name=HIVE_BACKEND)
        assert result["status"] == "success"
        assert not (hive_dir / "b.vet").exists()


# ===========================================================================
# Tests for _show_ticket invalid ticket ID validation
# ===========================================================================


class TestShowTicketInvalidIdValidation:
    """Tests for _show_ticket rejecting ticket IDs containing path traversal characters."""

    async def test_show_ticket_rejects_path_traversal_id(self, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={})

        result = await _show_ticket(["b.../../etc"])

        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_id"

    async def test_show_ticket_rejects_id_with_forward_slash(self, isolated_bees_env):
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={})

        result = await _show_ticket(["b./etc/passwd"])

        assert result["status"] == "error"
        assert result["error_type"] == "invalid_ticket_id"


class TestUpdateTicketStatusValidation:
    """Tests for status validation in _update_ticket."""

    async def test_single_invalid_status_fails(self, isolated_bees_env):
        """Single-mode update with invalid status returns error dict."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["open", "closed", "in_progress"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="open",
        )
        bee_id = result["ticket_id"]

        update_result = await _update_ticket(
            ticket_ids=bee_id,
            status="bogus",
            hive_name=HIVE_BACKEND,
        )
        assert update_result["status"] == "error"
        assert update_result["error_type"] == "invalid_status"
        assert "Invalid status" in update_result["message"]

    async def test_single_valid_status_passes(self, isolated_bees_env):
        """Single-mode update with valid status succeeds."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["open", "closed", "in_progress"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="open",
        )
        bee_id = result["ticket_id"]

        update_result = await _update_ticket(
            ticket_ids=bee_id,
            status="closed",
            hive_name=HIVE_BACKEND,
        )
        assert update_result["status"] == "success"
        assert bee_id in update_result["updated"]

    async def test_batch_invalid_status_in_failed(self, isolated_bees_env):
        """Batch update with invalid status puts ticket in 'failed' list."""
        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(status_values=["open", "closed", "in_progress"])

        result = await _create_ticket(
            ticket_type="bee",
            title="Test Bee",
            hive_name=HIVE_BACKEND,
            status="open",
        )
        bee_id = result["ticket_id"]

        update_result = await _update_ticket(
            ticket_ids=[bee_id],
            status="bogus",
            hive_name=HIVE_BACKEND,
        )
        assert update_result["status"] == "success"
        assert len(update_result["failed"]) == 1
        assert update_result["failed"][0]["id"] == bee_id
        assert "Invalid status" in update_result["failed"][0]["reason"]
        assert bee_id not in update_result["updated"]


class TestShowTicketWalkCount:
    """Tests for _show_ticket walk-count optimization (b.329)."""

    async def test_show_bulk_uses_single_walk(self, isolated_bees_env):
        """Bulk show of 5 tickets in 2 hives should walk each hive at most once."""
        import os
        from unittest.mock import patch

        helper = isolated_bees_env
        hive1_dir = helper.create_hive(HIVE_BACKEND)
        hive2_dir = helper.create_hive(HIVE_FRONTEND)
        helper.write_config()

        ids = []
        for i, (hive_dir, hive_name) in enumerate([
            (hive1_dir, HIVE_BACKEND),
            (hive1_dir, HIVE_BACKEND),
            (hive1_dir, HIVE_BACKEND),
            (hive2_dir, HIVE_FRONTEND),
            (hive2_dir, HIVE_FRONTEND),
        ]):
            result = await _create_ticket(
                ticket_type="bee", title=f"Show Bee {i}", hive_name=hive_name
            )
            ids.append(result["ticket_id"])

        with patch("os.walk", wraps=os.walk) as mock_walk:
            result = await _show_ticket(ids)

        assert result["status"] == "success"
        assert len(result["tickets"]) == 5
        assert result["not_found"] == []
        # At most one walk per hive (2 hives), not one per ticket (5)
        assert mock_walk.call_count <= 2


class TestBatchUpdateWalkCount:
    """Tests for _update_ticket batch walk-count optimization (b.329)."""

    async def test_batch_update_uses_single_walk(self, isolated_bees_env):
        """Batch update of 5 tickets in 2 hives should walk each hive at most once."""
        import os
        from unittest.mock import patch

        helper = isolated_bees_env
        hive1_dir = helper.create_hive(HIVE_BACKEND)
        hive2_dir = helper.create_hive(HIVE_FRONTEND)
        helper.write_config()

        ids = []
        for i, (hive_dir, hive_name) in enumerate([
            (hive1_dir, HIVE_BACKEND),
            (hive1_dir, HIVE_BACKEND),
            (hive1_dir, HIVE_BACKEND),
            (hive2_dir, HIVE_FRONTEND),
            (hive2_dir, HIVE_FRONTEND),
        ]):
            result = await _create_ticket(
                ticket_type="bee", title=f"Batch Bee {i}", hive_name=hive_name
            )
            ids.append(result["ticket_id"])

        with patch("os.walk", wraps=os.walk) as mock_walk:
            result = await _update_ticket(ticket_ids=ids, status="in_progress")

        assert result["status"] == "success"
        assert set(result["updated"]) == set(ids)
        assert result["not_found"] == []
        assert result["failed"] == []
        # At most one walk per hive (2 hives), not one per ticket (5)
        assert mock_walk.call_count <= 2


# ===========================================================================
# Regression tests: malformed ticket IDs (no dot) return well-formed errors
# ===========================================================================

_MALFORMED_ID = "bAmx"  # no dot — was previously handled by infer_ticket_type_from_id


class TestMalformedIdGracefulErrors:
    """Regression tests: prefix-based type derivation must not raise for IDs with no dot.

    After replacing infer_ticket_type_from_id with ticket_type_from_prefix, a
    no-dot ID like 'bAmx' returns a non-standard prefix string but must never
    raise a Python exception — callers should receive a well-formed error dict.
    """

    async def test_show_malformed_id_returns_error_dict(self, isolated_bees_env):
        """_show_ticket with malformed ID returns status=error, not an exception."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={})

        result = await _show_ticket([_MALFORMED_ID])

        assert result["status"] == "error"
        assert "error_type" in result
        assert "message" in result

    async def test_update_malformed_id_returns_error_dict(self, isolated_bees_env):
        """_update_ticket with malformed ID returns status=error, not an exception."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={})

        result = await _update_ticket(ticket_ids=_MALFORMED_ID, status="in_progress")

        assert result["status"] == "error"
        assert "error_type" in result
        assert "message" in result

    async def test_delete_malformed_id_returns_error_dict(self, isolated_bees_env):
        """_delete_ticket with malformed ID returns status=error, not an exception."""
        from src.mcp_ticket_ops import _delete_ticket

        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config(child_tiers={})

        result = await _delete_ticket(_MALFORMED_ID)

        assert result["status"] == "error"
        assert "error_type" in result
        assert "message" in result


# ===========================================================================
# Tests for _collect_deletion_set (scandir-based subtree collection)
# ===========================================================================


class TestCollectDeletionSet:
    """Tests for _collect_deletion_set() filesystem-based subtree collection."""

    def _setup_ticket(self, hive_dir: "Path", ticket_id: str, **kwargs) -> None:
        """Write a ticket file at its correct nested location within hive_dir."""
        from tests.helpers import write_ticket_file

        parts = ticket_id.split(".")
        prefix = parts[0]
        if prefix == "b":
            directory = hive_dir
        elif prefix == "t1":
            directory = hive_dir / f"b.{parts[1]}"
        elif prefix == "t2":
            directory = hive_dir / f"b.{parts[1]}" / f"t1.{parts[1]}.{parts[2]}"
        else:
            raise ValueError(f"Unsupported tier in test: {ticket_id}")
        t_type = "bee" if prefix == "b" else prefix
        write_ticket_file(directory, ticket_id, type=t_type, **kwargs)

    def test_bee_with_no_children(self, isolated_bees_env):
        """Single bee with no child directories returns just itself."""
        from src.mcp_ticket_ops import _collect_deletion_set

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        self._setup_ticket(hive_dir, "b.ab1")

        result = _collect_deletion_set("b.ab1", HIVE_BACKEND)

        assert result == ["b.ab1"]

    def test_bee_with_one_t1_child_returns_leaf_first(self, isolated_bees_env):
        """t1 child appears before its bee parent (leaves-first order)."""
        from src.mcp_ticket_ops import _collect_deletion_set

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        self._setup_ticket(hive_dir, "b.ab1")
        self._setup_ticket(hive_dir, "t1.ab1.cd")

        result = _collect_deletion_set("b.ab1", HIVE_BACKEND)

        assert result.index("t1.ab1.cd") < result.index("b.ab1")
        assert set(result) == {"b.ab1", "t1.ab1.cd"}

    def test_deep_subtree_leaves_first(self, isolated_bees_env):
        """t2 appears before t1 which appears before bee."""
        from src.mcp_ticket_ops import _collect_deletion_set

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"], "t2": ["Sub", "Subs"]})
        self._setup_ticket(hive_dir, "b.ab1")
        self._setup_ticket(hive_dir, "t1.ab1.cd")
        self._setup_ticket(hive_dir, "t2.ab1.cd.ef")

        result = _collect_deletion_set("b.ab1", HIVE_BACKEND)

        assert result.index("t2.ab1.cd.ef") < result.index("t1.ab1.cd")
        assert result.index("t1.ab1.cd") < result.index("b.ab1")
        assert set(result) == {"b.ab1", "t1.ab1.cd", "t2.ab1.cd.ef"}

    def test_multiple_children_all_included(self, isolated_bees_env):
        """All direct children appear in result before parent."""
        from src.mcp_ticket_ops import _collect_deletion_set

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})
        self._setup_ticket(hive_dir, "b.ab1")
        self._setup_ticket(hive_dir, "t1.ab1.cd")
        self._setup_ticket(hive_dir, "t1.ab1.ef")

        result = _collect_deletion_set("b.ab1", HIVE_BACKEND)

        assert set(result) == {"b.ab1", "t1.ab1.cd", "t1.ab1.ef"}
        assert result.index("t1.ab1.cd") < result.index("b.ab1")
        assert result.index("t1.ab1.ef") < result.index("b.ab1")

    def test_filesystem_overrides_yaml_children_list(self, isolated_bees_env):
        """scandir trusts the filesystem — child dir present but not in YAML is still included."""
        from src.mcp_ticket_ops import _collect_deletion_set
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        # Bee YAML lists no children
        write_ticket_file(hive_dir, "b.ab1", children=[])
        # But t1 directory physically exists inside the bee directory
        write_ticket_file(hive_dir / "b.ab1", "t1.ab1.cd", type="t1")

        result = _collect_deletion_set("b.ab1", HIVE_BACKEND)

        # scandir finds it despite missing from YAML children list
        assert "t1.ab1.cd" in result
        assert result.index("t1.ab1.cd") < result.index("b.ab1")

    def test_nonexistent_ticket_raises_value_error(self, isolated_bees_env):
        """Raises ValueError when root ticket does not exist on disk."""
        from src.mcp_ticket_ops import _collect_deletion_set

        helper = isolated_bees_env
        helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        with pytest.raises(ValueError, match="Ticket does not exist"):
            _collect_deletion_set("b.no1", HIVE_BACKEND)


# ===========================================================================
# Tests for batch parent backlink cleanup in bulk delete
# ===========================================================================


@pytest.mark.asyncio
class TestBulkDeleteBatchParentCleanup:
    """Tests for batch parent cleanup after bulk ticket deletion."""

    async def test_bulk_delete_updates_parent_children_list(self, isolated_bees_env):
        """Bulk deleting children removes them from parent's children field."""
        from src.mcp_ticket_ops import _delete_ticket
        from src.reader import read_ticket
        from src.paths import get_ticket_path
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        write_ticket_file(hive_dir, "b.pr1", children=["t1.pr1.c1", "t1.pr1.c2"])
        write_ticket_file(hive_dir / "b.pr1", "t1.pr1.c1", type="t1", parent="b.pr1")
        write_ticket_file(hive_dir / "b.pr1", "t1.pr1.c2", type="t1", parent="b.pr1")

        result = await _delete_ticket(["t1.pr1.c1", "t1.pr1.c2"])

        assert result["status"] == "success"
        assert set(result["deleted"]) == {"t1.pr1.c1", "t1.pr1.c2"}

        parent_path = get_ticket_path("b.pr1", "bee", HIVE_BACKEND)
        parent = read_ticket("b.pr1", file_path=parent_path)
        assert "t1.pr1.c1" not in (parent.children or [])
        assert "t1.pr1.c2" not in (parent.children or [])

    async def test_bulk_delete_writes_parent_once(self, isolated_bees_env):
        """Parent ticket is written exactly once even when multiple children are deleted."""
        from unittest.mock import patch
        from src.mcp_ticket_ops import _delete_ticket
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        write_ticket_file(hive_dir, "b.pr2", children=["t1.pr2.c1", "t1.pr2.c2", "t1.pr2.c3"])
        write_ticket_file(hive_dir / "b.pr2", "t1.pr2.c1", type="t1", parent="b.pr2")
        write_ticket_file(hive_dir / "b.pr2", "t1.pr2.c2", type="t1", parent="b.pr2")
        write_ticket_file(hive_dir / "b.pr2", "t1.pr2.c3", type="t1", parent="b.pr2")

        write_calls: list = []
        import src.mcp_ticket_ops as ops_module
        original_write = ops_module.write_ticket_file

        def spy_write(*args, **kwargs):
            write_calls.append(kwargs.get("ticket_id"))
            return original_write(*args, **kwargs)

        with patch.object(ops_module, "write_ticket_file", side_effect=spy_write):
            result = await _delete_ticket(["t1.pr2.c1", "t1.pr2.c2", "t1.pr2.c3"])

        assert result["status"] == "success"
        assert write_calls.count("b.pr2") == 1

    async def test_bulk_delete_multiple_parents_each_written_once(self, isolated_bees_env):
        """When children belong to different parents, each parent is written exactly once."""
        from unittest.mock import patch
        from src.mcp_ticket_ops import _delete_ticket
        from src.reader import read_ticket
        from src.paths import get_ticket_path
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        write_ticket_file(hive_dir, "b.p11", children=["t1.p11.c1"])
        write_ticket_file(hive_dir / "b.p11", "t1.p11.c1", type="t1", parent="b.p11")
        write_ticket_file(hive_dir, "b.p22", children=["t1.p22.c1"])
        write_ticket_file(hive_dir / "b.p22", "t1.p22.c1", type="t1", parent="b.p22")

        write_calls: list = []
        import src.mcp_ticket_ops as ops_module
        original_write = ops_module.write_ticket_file

        def spy_write(*args, **kwargs):
            write_calls.append(kwargs.get("ticket_id"))
            return original_write(*args, **kwargs)

        with patch.object(ops_module, "write_ticket_file", side_effect=spy_write):
            result = await _delete_ticket(["t1.p11.c1", "t1.p22.c1"])

        assert result["status"] == "success"
        assert set(result["deleted"]) == {"t1.p11.c1", "t1.p22.c1"}
        assert write_calls.count("b.p11") == 1
        assert write_calls.count("b.p22") == 1

        p1 = read_ticket("b.p11", file_path=get_ticket_path("b.p11", "bee", HIVE_BACKEND))
        assert "t1.p11.c1" not in (p1.children or [])

        p2 = read_ticket("b.p22", file_path=get_ticket_path("b.p22", "bee", HIVE_BACKEND))
        assert "t1.p22.c1" not in (p2.children or [])

    async def test_bulk_delete_bees_have_no_parent_cleanup(self, isolated_bees_env):
        """Deleting bee tickets (no parent) skips parent cleanup — no writes to nonexistent parents."""
        from unittest.mock import patch
        from src.mcp_ticket_ops import _delete_ticket
        from tests.helpers import write_ticket_file

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={})

        write_ticket_file(hive_dir, "b.b11")
        write_ticket_file(hive_dir, "b.b22")

        write_calls: list = []
        import src.mcp_ticket_ops as ops_module
        original_write = ops_module.write_ticket_file

        def spy_write(*args, **kwargs):
            write_calls.append(kwargs.get("ticket_id"))
            return original_write(*args, **kwargs)

        with patch.object(ops_module, "write_ticket_file", side_effect=spy_write):
            result = await _delete_ticket(["b.b11", "b.b22"])

        assert result["status"] == "success"
        assert set(result["deleted"]) == {"b.b11", "b.b22"}
        # No parent writes — bees have no parent
        assert write_calls == []

    async def test_delete_with_dependencies_true_and_batch_cleanup(self, isolated_bees_env):
        """delete_with_dependencies=True combined with bulk delete cleans dep refs and batch-updates parent."""
        from unittest.mock import patch
        from src.mcp_ticket_ops import _delete_ticket
        from src.reader import read_ticket
        from src.paths import get_ticket_path
        from tests.helpers import write_ticket_file
        import src.mcp_ticket_ops as ops_module

        helper = isolated_bees_env
        hive_dir = helper.create_hive(HIVE_BACKEND)
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        # b.dwd has two t1 children; c1 has up_dep on c2 (bidirectional cross-dep within deletion set)
        write_ticket_file(hive_dir, "b.dwd", children=["t1.dwd.c1", "t1.dwd.c2"])
        write_ticket_file(
            hive_dir / "b.dwd", "t1.dwd.c1", type="t1", parent="b.dwd",
            up_dependencies=["t1.dwd.c2"],
        )
        write_ticket_file(
            hive_dir / "b.dwd", "t1.dwd.c2", type="t1", parent="b.dwd",
            down_dependencies=["t1.dwd.c1"],
        )

        with patch.object(ops_module, "load_global_config", return_value={"delete_with_dependencies": True}):
            result = await _delete_ticket(["t1.dwd.c1", "t1.dwd.c2"])

        assert result["status"] == "success"
        assert set(result["deleted"]) == {"t1.dwd.c1", "t1.dwd.c2"}

        # Both t1 tickets are gone from the filesystem
        assert not (hive_dir / "b.dwd" / "t1.dwd.c1").exists()
        assert not (hive_dir / "b.dwd" / "t1.dwd.c2").exists()

        # Batch cleanup correctly removed both from the parent's children list
        parent_path = get_ticket_path("b.dwd", "bee", HIVE_BACKEND)
        parent = read_ticket("b.dwd", file_path=parent_path)
        assert "t1.dwd.c1" not in (parent.children or [])
        assert "t1.dwd.c2" not in (parent.children or [])


# ===========================================================================
# Tests for _sanitize_escape_sequences applied via _create_ticket / _update_ticket
# ===========================================================================


class TestSanitizeEscapeSequencesViaCreate:
    """Verify that literal \\n and \\t in body are expanded when creating a ticket."""

    @pytest.mark.parametrize(
        "raw_body,expected_body",
        [
            pytest.param("line1\\nline2", "line1\nline2", id="literal_backslash_n"),
            pytest.param("col1\\tcol2", "col1\tcol2", id="literal_backslash_t"),
            pytest.param("line1\nline2", "line1\nline2", id="real_newline_passthrough"),
        ],
    )
    async def test_create_ticket_sanitizes_body(self, isolated_bees_env, raw_body, expected_body):
        """Body escape sequences are expanded (or left alone) on ticket creation."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _create_ticket(
            ticket_type="bee",
            title="Escape Test",
            hive_name=HIVE_BACKEND,
            body=raw_body,
        )

        assert result["status"] == "success"
        tid = result["ticket_id"]
        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.body == expected_body


class TestSanitizeEscapeSequencesViaUpdate:
    """Verify that literal escape sequences in body are expanded when updating a ticket."""

    @pytest.mark.parametrize(
        "input_body,expected_body",
        [
            ("first\\nsecond", "first\nsecond"),
            ("col1\\tcol2", "col1\tcol2"),
        ],
        ids=["literal_backslash_n", "literal_backslash_t"],
    )
    async def test_update_ticket_sanitizes_body(self, isolated_bees_env, input_body, expected_body):
        """Updating body with literal escape sequences stores real characters on disk."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        result = await _create_ticket(
            ticket_type="bee", title="Update Escape Test", hive_name=HIVE_BACKEND
        )
        tid = result["ticket_id"]

        update_result = await _update_ticket(
            ticket_ids=tid,
            body=input_body,
            hive_name=HIVE_BACKEND,
        )
        assert update_result["status"] == "success"

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.body == expected_body


class TestAppendTicketBody:
    """Tests for `_append_ticket_body` core function (Epics 1 and 2).

    Covers SR-10.6 cases: #1 happy path, #2 empty-chunk no-op skip-write,
    #3 empty-chunk against missing ticket, #4 ordering, #5 large-body,
    #10 not-found, #11 hive hint routes correctly, #12 unknown hive hint,
    #13 frontmatter preservation, #14 tier-agnostic. Also covers the
    Epic 2 forced-write-failure structured `write_error` return (SR-7.5).
    """

    async def _read_frontmatter_dict(self, ticket_id: str, ticket_type: str, hive: str) -> dict:
        """Return the ticket's frontmatter as a dict (excluding body) for comparison."""
        from dataclasses import asdict

        ticket = read_ticket(
            ticket_id, file_path=get_ticket_path(ticket_id, ticket_type, hive)
        )
        data = asdict(ticket)
        data.pop("body", None)
        return data

    async def test_happy_path_small_append(self, isolated_bees_env):
        """SR-10.6 #1 — small append returns success shape and body is exact concat."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        create_result = await _create_ticket(
            ticket_type="bee",
            title="Append Target",
            body="Hello",
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        frontmatter_before = await self._read_frontmatter_dict(tid, "bee", HIVE_BACKEND)

        result = await _append_ticket_body(
            ticket_id=tid,
            chunk=" World",
            hive_name=HIVE_BACKEND,
        )

        assert result["status"] == "success"
        assert result["appended"] == [tid]
        assert result["not_found"] == []
        assert result["failed"] == []

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.body == "Hello World"

        frontmatter_after = await self._read_frontmatter_dict(tid, "bee", HIVE_BACKEND)
        assert frontmatter_before == frontmatter_after

    async def test_ordering_across_sequential_appends(self, isolated_bees_env):
        """SR-10.6 #4 — five sequential appends produce the exact concatenation in order."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        create_result = await _create_ticket(
            ticket_type="bee",
            title="Ordering Bee",
            body="A",
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        for ch in ["B", "C", "D", "E", "F"]:
            result = await _append_ticket_body(
                ticket_id=tid, chunk=ch, hive_name=HIVE_BACKEND
            )
            assert result["status"] == "success"

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.body == "ABCDEF"

    async def test_large_body_workflow(self, isolated_bees_env):
        """SR-10.6 #5 — loop appends of BODY_MAX_LENGTH until >= 1M chars accumulated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        stub = "STUB-"
        create_result = await _create_ticket(
            ticket_type="bee",
            title="Large Body Bee",
            body=stub,
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        chunk = make_body_at_cap("x")
        assert len(chunk) == BODY_MAX_LENGTH

        # N such that N * BODY_MAX_LENGTH >= 1_000_000
        n = (1_000_000 + BODY_MAX_LENGTH - 1) // BODY_MAX_LENGTH
        assert n * BODY_MAX_LENGTH >= 1_000_000

        for _ in range(n):
            result = await _append_ticket_body(
                ticket_id=tid, chunk=chunk, hive_name=HIVE_BACKEND
            )
            assert result["status"] == "success"

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert len(ticket.body) == len(stub) + n * BODY_MAX_LENGTH
        assert ticket.body == stub + chunk * n

    async def test_not_found_append(self, isolated_bees_env):
        """SR-10.6 #10 — unknown ticket id returns ticket_not_found and does not create files."""
        hive_dir = isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        files_before = sorted(p for p in hive_dir.rglob("*") if p.is_file())

        result = await _append_ticket_body(
            ticket_id=TICKET_ID_NONEXISTENT,
            chunk="nope",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "message" in result

        files_after = sorted(p for p in hive_dir.rglob("*") if p.is_file())
        assert files_before == files_after

    async def test_hive_hint_routes_correctly(self, isolated_bees_env):
        """SR-10.6 #11 — hive hint selects the right hive when same ticket exists in both."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.create_hive(HIVE_FRONTEND)
        isolated_bees_env.write_config()

        backend_result = await _create_ticket(
            ticket_type="bee",
            title="Shared Title",
            body="backend-",
            hive_name=HIVE_BACKEND,
        )
        frontend_result = await _create_ticket(
            ticket_type="bee",
            title="Shared Title",
            body="frontend-",
            hive_name=HIVE_FRONTEND,
        )

        backend_tid = backend_result["ticket_id"]
        frontend_tid = frontend_result["ticket_id"]

        backend_ticket = read_ticket(
            backend_tid, file_path=get_ticket_path(backend_tid, "bee", HIVE_BACKEND)
        )
        frontend_ticket = read_ticket(
            frontend_tid, file_path=get_ticket_path(frontend_tid, "bee", HIVE_FRONTEND)
        )
        # Capture body strings eagerly: read_ticket may return a cached ticket
        # object whose .body mutates when _append_ticket_body rewrites it.
        backend_body_before = backend_ticket.body
        frontend_body_before = frontend_ticket.body

        result = await _append_ticket_body(
            ticket_id=backend_tid,
            chunk="APPENDED",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"
        assert result["appended"] == [backend_tid]

        backend_ticket_after = read_ticket(
            backend_tid, file_path=get_ticket_path(backend_tid, "bee", HIVE_BACKEND)
        )
        frontend_ticket_after = read_ticket(
            frontend_tid, file_path=get_ticket_path(frontend_tid, "bee", HIVE_FRONTEND)
        )

        assert backend_ticket_after.body == backend_body_before + "APPENDED"
        assert frontend_ticket_after.body == frontend_body_before

    async def test_unknown_hive_hint(self, isolated_bees_env):
        """SR-10.6 #12 — hive hint pointing at unknown hive returns hive_not_found."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        create_result = await _create_ticket(
            ticket_type="bee",
            title="Known Hive Bee",
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        result = await _append_ticket_body(
            ticket_id=tid,
            chunk="data",
            hive_name="no_such_hive",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    async def test_frontmatter_preservation(self, isolated_bees_env):
        """SR-10.6 #13 — frontmatter (tags, status, children, reference_materials) unchanged after append."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        # Seed a bee with tags + status + reference_materials.
        create_result = await _create_ticket(
            ticket_type="bee",
            title="Frontmatter Bee",
            body="initial-",
            hive_name=HIVE_BACKEND,
            tags=["alpha", "beta"],
            status="in_progress",
            reference_materials=[{"value": "docs/spec.md"}],
        )
        assert create_result["status"] == "success"
        tid = create_result["ticket_id"]

        frontmatter_before = await self._read_frontmatter_dict(tid, "bee", HIVE_BACKEND)

        result = await _append_ticket_body(
            ticket_id=tid,
            chunk="APPENDED-CHUNK",
            hive_name=HIVE_BACKEND,
        )
        assert result["status"] == "success"

        frontmatter_after = await self._read_frontmatter_dict(tid, "bee", HIVE_BACKEND)
        assert frontmatter_before == frontmatter_after

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.body == "initial-APPENDED-CHUNK"
        assert ticket.tags == ["alpha", "beta"]
        assert ticket.status == "in_progress"
        assert ticket.reference_materials == [{"value": "docs/spec.md"}]

    async def test_tier_agnostic_append(self, isolated_bees_env):
        """SR-10.6 #14 — append path works for both bee and t1 tiers."""
        backend_path = isolated_bees_env.base_path / HIVE_BACKEND
        if not backend_path.exists():
            isolated_bees_env.create_hive(HIVE_BACKEND)

        scope_data = {
            "hives": {
                HIVE_BACKEND: {
                    "path": str(backend_path),
                    "display_name": "Backend",
                    "created_at": "2026-02-01T12:00:00",
                    "child_tiers": {
                        "t1": ["Epic", "Epics"],
                        "t2": ["Task", "Tasks"],
                    },
                },
            },
            "child_tiers": {},
        }
        write_scoped_config(
            isolated_bees_env.global_bees_dir,
            isolated_bees_env.base_path,
            scope_data,
        )

        # Bee-tier append.
        bee_create = await _create_ticket(
            ticket_type="bee",
            title="Tier Bee",
            body="bee-",
            hive_name=HIVE_BACKEND,
        )
        assert bee_create["status"] == "success"
        bee_id = bee_create["ticket_id"]

        bee_append = await _append_ticket_body(
            ticket_id=bee_id, chunk="append", hive_name=HIVE_BACKEND
        )
        assert bee_append["status"] == "success"
        bee_ticket = read_ticket(bee_id, file_path=get_ticket_path(bee_id, "bee", HIVE_BACKEND))
        assert bee_ticket.body == "bee-append"

        # t1-tier append.
        t1_create = await _create_ticket(
            ticket_type="t1",
            title="Tier Task",
            body="task-",
            parent=bee_id,
            hive_name=HIVE_BACKEND,
        )
        assert t1_create["status"] == "success"
        t1_id = t1_create["ticket_id"]
        assert t1_id.startswith("t1.")

        t1_append = await _append_ticket_body(
            ticket_id=t1_id, chunk="append", hive_name=HIVE_BACKEND
        )
        assert t1_append["status"] == "success"
        t1_ticket = read_ticket(t1_id, file_path=get_ticket_path(t1_id, "t1", HIVE_BACKEND))
        assert t1_ticket.body == "task-append"

    async def test_empty_chunk_noop_skip_write(self, isolated_bees_env):
        """SR-10.6 #2 — empty chunk is a success no-op that does NOT touch the file on disk.

        Asserts the success return shape AND that the file's mtime, size,
        and content hash are byte-identical before and after the call.
        Mtime is the strongest signal that the write path was truly skipped:
        if `_append_ticket_body` had called `write_ticket_file`, the atomic
        rename would have updated the inode's mtime even though the bytes
        themselves are unchanged.
        """
        import hashlib

        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        create_result = await _create_ticket(
            ticket_type="bee",
            title="Empty Chunk No-Op Bee",
            body="seed-body-content",
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        ticket_path = get_ticket_path(tid, "bee", HIVE_BACKEND)
        before_bytes = ticket_path.read_bytes()
        before_stat = ticket_path.stat()
        before_hash = hashlib.sha256(before_bytes).hexdigest()

        result = await _append_ticket_body(
            ticket_id=tid,
            chunk="",
            hive_name=HIVE_BACKEND,
        )

        assert result == {
            "status": "success",
            "appended": [tid],
            "not_found": [],
            "failed": [],
        }

        after_stat = ticket_path.stat()
        after_bytes = ticket_path.read_bytes()
        after_hash = hashlib.sha256(after_bytes).hexdigest()

        assert after_bytes == before_bytes
        assert after_hash == before_hash
        assert after_stat.st_size == before_stat.st_size
        # Strongest signal: mtime unchanged proves no atomic-rename occurred.
        assert after_stat.st_mtime_ns == before_stat.st_mtime_ns

    async def test_empty_chunk_against_missing_ticket(self, isolated_bees_env):
        """SR-10.6 #3 — empty chunk on an unknown ticket id still returns ticket_not_found.

        Empty-chunk no-op must not bypass the existence check. Also asserts
        no new files were created in the hive directory as a side effect.
        """
        hive_dir = isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        files_before = sorted(p for p in hive_dir.rglob("*") if p.is_file())

        result = await _append_ticket_body(
            ticket_id=TICKET_ID_NONEXISTENT,
            chunk="",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ticket_not_found"
        assert "message" in result

        files_after = sorted(p for p in hive_dir.rglob("*") if p.is_file())
        assert files_before == files_after

    async def test_write_error_structured_return(self, isolated_bees_env, monkeypatch):
        """SR-7.5 — `write_ticket_file` exceptions are caught and converted to write_error.

        Forces the writer to raise `OSError("disk full")` and asserts the
        exception does NOT propagate out of `_append_ticket_body`. Instead
        the function must return the structured `write_error` shape and
        leave the on-disk file byte-identical (the patched writer never
        runs, so this is trivially true; the assertion documents the
        contract).
        """
        import hashlib

        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        create_result = await _create_ticket(
            ticket_type="bee",
            title="Write Error Bee",
            body="initial-",
            hive_name=HIVE_BACKEND,
        )
        tid = create_result["ticket_id"]

        ticket_path = get_ticket_path(tid, "bee", HIVE_BACKEND)
        before_bytes = ticket_path.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("src.mcp_ticket_ops.write_ticket_file", _boom)

        # Must NOT raise — wrap in try to make a propagated exception a
        # test failure with a useful message rather than an error.
        try:
            result = await _append_ticket_body(
                ticket_id=tid,
                chunk="APPEND-PAYLOAD",
                hive_name=HIVE_BACKEND,
            )
        except Exception as exc:  # pragma: no cover - failure path
            pytest.fail(
                f"_append_ticket_body must not propagate write exceptions, "
                f"but raised: {type(exc).__name__}: {exc}"
            )

        assert result["status"] == "error"
        assert result["error_type"] == "write_error"
        assert "message" in result
        assert "disk full" in result["message"]
        assert tid in result["message"]

        after_bytes = ticket_path.read_bytes()
        after_hash = hashlib.sha256(after_bytes).hexdigest()
        assert after_bytes == before_bytes
        assert after_hash == before_hash


# ---------------------------------------------------------------------------
# Tests for _get_status_values / _set_status_values glob-scope hive resolution
# (regression tests for bug b.7qj)
# ---------------------------------------------------------------------------

def _make_glob_and_exact_scopes():
    """Return a scopes dict with a glob scope owning 'shared_hive' and an exact scope owning 'local_hive'."""
    return {
        "/test/project/**": {
            "hives": {
                "shared_hive": {
                    "path": "tickets/shared/",
                    "display_name": "Shared",
                    "created_at": "2026-01-01T00:00:00",
                    "status_values": ["open", "in-progress", "done"],
                },
            },
        },
        "/test/project/main": {
            "hives": {
                "local_hive": {
                    "path": "tickets/local/",
                    "display_name": "Local",
                    "created_at": "2026-01-01T00:00:00",
                },
            },
            "status_values": ["alpha", "beta"],
        },
    }


class TestGetStatusValuesGlobScope:
    """_get_status_values must aggregate hives across all matching scopes."""

    @pytest.mark.asyncio
    async def test_glob_scope_hive_visible(self, mock_global_bees_dir):
        """Hive registered under glob scope appears in hives dict when queried from a more-specific path."""
        from pathlib import Path

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _get_status_values(resolved_root=Path("/test/project/main"))

        assert result["status"] == "success"
        # Both hives should be present
        assert "shared_hive" in result["hives"]
        assert "local_hive" in result["hives"]
        # Glob-scope hive should carry its status_values
        assert result["hives"]["shared_hive"] == ["open", "in-progress", "done"]
        # Local hive has no explicit status_values
        assert result["hives"]["local_hive"] is None

    @pytest.mark.asyncio
    async def test_scope_status_values_from_most_specific(self, mock_global_bees_dir):
        """The scope-level status_values should come from the most-specific matching scope."""
        from pathlib import Path

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _get_status_values(resolved_root=Path("/test/project/main"))

        assert result["status"] == "success"
        # Most-specific scope (/test/project/main) has status_values ["alpha", "beta"]
        assert result["scope"] == ["alpha", "beta"]

    @pytest.mark.asyncio
    async def test_most_specific_hive_wins_on_overlap(self, mock_global_bees_dir):
        """When the same hive appears in both glob and exact scopes, most-specific wins."""
        from pathlib import Path

        scopes = {
            "/test/project/**": {
                "hives": {
                    "overlap_hive": {
                        "path": "tickets/overlap-glob/",
                        "display_name": "Overlap Glob",
                        "created_at": "2026-01-01T00:00:00",
                        "status_values": ["glob-val"],
                    },
                },
            },
            "/test/project/main": {
                "hives": {
                    "overlap_hive": {
                        "path": "tickets/overlap-exact/",
                        "display_name": "Overlap Exact",
                        "created_at": "2026-01-01T00:00:00",
                        "status_values": ["exact-val"],
                    },
                },
            },
        }
        write_multi_scope_config(mock_global_bees_dir, scopes)

        result = await _get_status_values(resolved_root=Path("/test/project/main"))

        assert result["status"] == "success"
        # Most-specific scope wins
        assert result["hives"]["overlap_hive"] == ["exact-val"]


class TestSetStatusValuesGlobScope:
    """_set_status_values with scope='hive' must find hives across all matching scopes."""

    @pytest.mark.asyncio
    async def test_set_on_glob_scope_hive_succeeds(self, mock_global_bees_dir):
        """Setting status_values on a hive registered under a glob scope should succeed."""
        from pathlib import Path

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _set_status_values(
            scope="hive",
            hive_name="shared_hive",
            status_values=["open", "closed"],
            resolved_root=Path("/test/project/main"),
        )

        assert result["status"] == "success"
        assert result["hive_name"] == "shared_hive"
        assert result["status_values"] == ["open", "closed"]

    @pytest.mark.asyncio
    async def test_set_on_glob_scope_hive_writes_to_correct_scope(self, mock_global_bees_dir):
        """Status values should be written to the glob scope entry, not the exact scope."""
        from pathlib import Path
        from src.config import load_global_config

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        await _set_status_values(
            scope="hive",
            hive_name="shared_hive",
            status_values=["open", "closed"],
            resolved_root=Path("/test/project/main"),
        )

        # Reload config and verify the write landed in the glob scope
        config = load_global_config()
        glob_hive = config["scopes"]["/test/project/**"]["hives"]["shared_hive"]
        assert glob_hive["status_values"] == ["open", "closed"]

        # The exact scope should NOT have gained the hive
        exact_hives = config["scopes"]["/test/project/main"].get("hives", {})
        assert "shared_hive" not in exact_hives

    @pytest.mark.asyncio
    async def test_set_on_nonexistent_hive_fails(self, mock_global_bees_dir):
        """Setting status_values on a hive that doesn't exist in any scope should fail."""
        from pathlib import Path

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _set_status_values(
            scope="hive",
            hive_name="ghost_hive",
            status_values=["open"],
            resolved_root=Path("/test/project/main"),
        )

        assert result["status"] == "error"
        assert result["error_type"] == "hive_not_found"

    @pytest.mark.asyncio
    async def test_repo_scope_still_works(self, mock_global_bees_dir):
        """Regression: scope='repo_scope' case must still work correctly (uses find_matching_scope)."""
        from pathlib import Path
        from src.config import load_global_config

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _set_status_values(
            scope="repo_scope",
            status_values=["new-a", "new-b"],
            resolved_root=Path("/test/project/main"),
        )

        assert result["status"] == "success"
        assert result["scope"] == "repo_scope"
        assert result["status_values"] == ["new-a", "new-b"]

        # Verify it wrote to the most-specific scope
        config = load_global_config()
        assert config["scopes"]["/test/project/main"]["status_values"] == ["new-a", "new-b"]

    @pytest.mark.asyncio
    async def test_unset_on_glob_scope_hive_succeeds(self, mock_global_bees_dir):
        """Unsetting status_values on a glob-scope hive should succeed and write null."""
        from pathlib import Path
        from src.config import load_global_config

        write_multi_scope_config(mock_global_bees_dir, _make_glob_and_exact_scopes())

        result = await _set_status_values(
            scope="hive",
            hive_name="shared_hive",
            unset=True,
            resolved_root=Path("/test/project/main"),
        )

        assert result["status"] == "success"
        assert result["hive_name"] == "shared_hive"

        # Verify null was written to the glob scope
        config = load_global_config()
        glob_hive = config["scopes"]["/test/project/**"]["hives"]["shared_hive"]
        assert glob_hive["status_values"] is None
