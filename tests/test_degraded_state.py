"""Tests for degraded state behavior when hive-name conflicts exist across scopes.

When the same hive name appears in multiple overlapping scopes, the system enters
a degraded state. Most operations are blocked with a config_conflict error, but
abandon_hive remains functional so users can resolve the conflict. Operations must
work normally when conflicts exist only in non-overlapping scopes.
"""

from pathlib import Path

import pytest

from src.repo_context import repo_root_context
from tests.conftest import write_multi_scope_config

# Operations that must be blocked in degraded state
BLOCKED_OPERATIONS = [
    pytest.param("_create_ticket", id="create_ticket"),
    pytest.param("_show_ticket", id="show_ticket"),
    pytest.param("_execute_freeform_query", id="execute_freeform_query"),
    pytest.param("_list_hives", id="list_hives"),
    pytest.param("_rename_hive", id="rename_hive"),
    pytest.param("_sanitize_hive", id="sanitize_hive"),
    pytest.param("_move_bee", id="move_bee"),
    pytest.param("_generate_index", id="generate_index"),
]


def _overlapping_scope_patterns(tmp_path: Path) -> tuple[str, str]:
    """Derive two overlapping scope patterns from tmp_path.

    Returns (wildcard_parent, exact_child) where wildcard_parent matches
    tmp_path and exact_child also matches tmp_path, creating overlap.
    """
    wildcard_parent = str(tmp_path.parent) + "/**"
    exact_child = str(tmp_path) + "/"
    return wildcard_parent, exact_child


def _conflicting_scopes_config(tmp_path: Path) -> dict:
    """Build scopes dict with same hive name in two overlapping scopes."""
    wildcard, exact = _overlapping_scope_patterns(tmp_path)
    hive_path = str(tmp_path / "backend")
    return {
        wildcard: {
            "hives": {"backend": {"path": hive_path, "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
        },
        exact: {
            "hives": {"backend": {"path": hive_path, "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
        },
    }


def _single_scope_config(tmp_path: Path) -> dict:
    """Build scopes dict with a single scope (no conflict possible)."""
    exact = str(tmp_path) + "/"
    hive_path = str(tmp_path / "backend")
    return {
        exact: {
            "hives": {"backend": {"path": hive_path, "display_name": "Backend"}},
            "child_tiers": {"t1": ["Task", "Tasks"]},
        },
    }


async def _call_operation(op_name: str, tmp_path: Path):
    """Call a guarded operation with minimal valid arguments."""
    if op_name == "_create_ticket":
        from src.mcp_ticket_ops import _create_ticket
        return await _create_ticket(
            ticket_type="bee", title="Test", hive_name="backend",
            resolved_root=tmp_path,
        )
    elif op_name == "_show_ticket":
        from src.mcp_ticket_ops import _show_ticket
        return await _show_ticket(ticket_ids=["b.abc"], resolved_root=tmp_path)
    elif op_name == "_execute_freeform_query":
        from src.mcp_query_ops import _execute_freeform_query
        return await _execute_freeform_query(
            query_yaml="- ['type=bee']", resolved_root=tmp_path,
        )
    elif op_name == "_list_hives":
        from src.mcp_hive_ops import _list_hives
        return await _list_hives(resolved_root=tmp_path)
    elif op_name == "_rename_hive":
        from src.mcp_hive_ops import _rename_hive
        return await _rename_hive(
            old_name="backend", new_name="new_backend", resolved_root=tmp_path,
        )
    elif op_name == "_sanitize_hive":
        from src.mcp_hive_ops import _sanitize_hive
        return await _sanitize_hive(hive_name="backend", resolved_root=tmp_path)
    elif op_name == "_move_bee":
        from src.mcp_move_bee import _move_bee
        return await _move_bee(
            bee_ids=["b.abc"], destination_hive="frontend", resolved_root=tmp_path,
        )
    elif op_name == "_generate_index":
        from src.mcp_index_ops import _generate_index
        return await _generate_index(resolved_root=tmp_path)
    else:
        raise ValueError(f"Unknown operation: {op_name}")


class TestDegradedState:
    """Test that degraded state (config conflicts) blocks operations correctly."""

    @pytest.mark.parametrize("op_name", BLOCKED_OPERATIONS)
    async def test_blocked_operations_return_config_conflict(
        self, op_name, tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """All 8 guarded operations return config_conflict in degraded state."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        write_multi_scope_config(mock_global_bees_dir, _conflicting_scopes_config(tmp_path))
        with repo_root_context(tmp_path):
            result = await _call_operation(op_name, tmp_path)
            assert result["status"] == "error"
            assert result["error_type"] == "config_conflict"

    @pytest.mark.parametrize("op_name", [
        pytest.param("_list_hives", id="list_hives"),
        pytest.param("_generate_index", id="generate_index"),
    ])
    async def test_operations_work_with_non_overlapping_scopes(
        self, op_name, tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """Operations work normally when only one scope matches (no conflict)."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        hive_path = tmp_path / "backend"
        hive_path.mkdir(parents=True)
        # Create .hive identity marker
        hive_identity = hive_path / ".hive"
        hive_identity.mkdir()
        identity_data = '{"normalized_name": "backend", "display_name": "Backend", "created_at": "2026-02-05T00:00:00"}'
        (hive_identity / "identity.json").write_text(identity_data)
        write_multi_scope_config(mock_global_bees_dir, _single_scope_config(tmp_path))
        with repo_root_context(tmp_path):
            result = await _call_operation(op_name, tmp_path)
            # Should NOT be config_conflict
            assert result.get("error_type") != "config_conflict"

    async def test_abandon_hive_not_blocked_in_degraded_state(
        self, tmp_path, monkeypatch, mock_global_bees_dir,
    ):
        """abandon_hive must work even in degraded state (so users can fix conflicts)."""
        from src.mcp_hive_ops import _abandon_hive

        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        hive_path = tmp_path / "backend"
        hive_path.mkdir()
        write_multi_scope_config(mock_global_bees_dir, _conflicting_scopes_config(tmp_path))
        with repo_root_context(tmp_path):
            result = await _abandon_hive("backend", resolved_root=tmp_path)
            assert result["status"] == "success"
            assert result["scopes_modified"] == 2
