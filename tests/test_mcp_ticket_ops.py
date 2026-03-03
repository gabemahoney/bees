"""Unit tests for mcp_ticket_ops per-hive validation support."""

import pytest

from src.mcp_ticket_ops import (
    _create_ticket,
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
from tests.conftest import write_scoped_config
from tests.test_constants import (
    HIVE_BACKEND,
    HIVE_FRONTEND,
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

        result = await _update_ticket(ticket_id=ids, status="in_progress")

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

        result = await _update_ticket(ticket_id=ids, add_tags=[TAG_BATCH_FOO])

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

        result = await _update_ticket(ticket_id=ids, remove_tags=[TAG_BATCH_BAR])

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
            ticket_id=ids,
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
            ticket_id=ids,
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

        result = await _update_ticket(ticket_id=[], status="in_progress")

        assert result == {"status": "success", "updated": [], "not_found": [], "failed": []}

    async def test_batch_duplicate_ids_deduplicated_in_response(self, isolated_bees_env):
        """Duplicate IDs in input — each ID appears once in updated."""
        isolated_bees_env.create_hive(HIVE_BACKEND)
        isolated_bees_env.write_config()

        r = await _create_ticket(ticket_type="bee", title="Dedup Bee", hive_name=HIVE_BACKEND)
        tid = r["ticket_id"]

        result = await _update_ticket(ticket_id=[tid, tid, tid], status="in_progress")

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

        result = await _update_ticket(ticket_id=[real_id, fake_id], status="in_progress")

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

        update_result = await _update_ticket(ticket_id=ids, title="Attempted Title Change")
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

        result = await _update_ticket(ticket_id=tid, status="in_progress")

        assert result["status"] == "success"
        assert "updated" in result
        assert tid in result["updated"]
        assert "not_found" in result
        assert "failed" in result
        # Must NOT be legacy shape
        assert "ticket_type" not in result
        assert "title" not in result


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
            ticket_type="bee", title="Original Title", description="Original desc", hive_name=HIVE_BACKEND
        )
        tid = result["ticket_id"]

        update_result = await _update_ticket(
            tid,
            title="Updated Title",
            description="Updated desc",
            status="in_progress",
            tags=["alpha", "beta"],
            hive_name=HIVE_BACKEND,
        )

        assert update_result["status"] == "success"
        assert tid in update_result["updated"]

        ticket = read_ticket(tid, file_path=get_ticket_path(tid, "bee", HIVE_BACKEND))
        assert ticket.title == "Updated Title"
        assert ticket.description == "Updated desc"
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
            ticket_id=bee_id,
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
            ticket_id=bee_id,
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
            ticket_id=[bee_id],
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
            result = await _update_ticket(ticket_id=ids, status="in_progress")

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

        result = await _update_ticket(ticket_id=_MALFORMED_ID, status="in_progress")

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
