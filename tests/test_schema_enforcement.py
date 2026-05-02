"""Tests for schema enforcement.

Guarded commands return schema_outdated when migrations are pending.
Exempt commands (sanitize_hive, colonize_hive) bypass the schema check.
"""

import pytest

import src.migrations.manifest as manifest_mod
from src.migrations.manifest import ManifestEntry
from src.mcp_hive_ops import _list_hives, _sanitize_hive, colonize_hive_core
from src.mcp_index_ops import _generate_index
from src.mcp_move_bee import _move_bee
from src.mcp_ticket_ops import _create_ticket


def _pending_hop():
    """One fake pending migration hop — causes check_schema_version to report outdated."""
    return [ManifestEntry(from_version="1.0", to_version="2.0", upgrade_script=lambda cfg: None)]


# ---------------------------------------------------------------------------
# Guarded commands: outdated schema blocks execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make_coro",
    [
        pytest.param(lambda: _create_ticket("bee", "Test Bee", "backend"), id="create_ticket"),
        pytest.param(lambda: _list_hives(), id="list_hives"),
        pytest.param(lambda: _move_bee([], "dest"), id="move_bee"),
        pytest.param(lambda: _generate_index(), id="generate_index"),
    ],
)
async def test_guarded_commands_return_schema_outdated(make_coro, monkeypatch):
    monkeypatch.setattr(manifest_mod, "find_pending_hops", lambda v: _pending_hop())
    result = await make_coro()
    assert result["status"] == "error"
    assert result["error_type"] == "schema_outdated"


# ---------------------------------------------------------------------------
# Guarded commands: current schema allows execution to proceed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make_coro",
    [
        pytest.param(lambda: _create_ticket("bee", "Test Bee", "backend"), id="create_ticket"),
        pytest.param(lambda: _list_hives(), id="list_hives"),
        pytest.param(lambda: _move_bee([], "dest"), id="move_bee"),
        pytest.param(lambda: _generate_index(), id="generate_index"),
    ],
)
async def test_guarded_commands_proceed_when_schema_current(make_coro, monkeypatch):
    monkeypatch.setattr(manifest_mod, "find_pending_hops", lambda v: [])
    result = await make_coro()
    assert result.get("error_type") != "schema_outdated"


# ---------------------------------------------------------------------------
# Exempt commands: proceed even with an outdated schema
# ---------------------------------------------------------------------------


async def test_sanitize_hive_exempt_from_schema_check(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "find_pending_hops", lambda v: _pending_hop())
    result = await _sanitize_hive("backend", resolved_root=tmp_path)
    assert result.get("error_type") != "schema_outdated"


async def test_colonize_hive_exempt_from_schema_check(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "find_pending_hops", lambda v: _pending_hop())
    hive_path = tmp_path / "new_hive"
    result = await colonize_hive_core("new_hive", str(hive_path), repo_root=tmp_path)
    assert result.get("error_type") != "schema_outdated"
