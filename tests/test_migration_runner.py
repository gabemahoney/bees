"""Unit tests for migrations.runner — run_pending_migrations()."""

import json

import pytest

import src.migrations.runner as runner_mod
from src.migrations.manifest import ManifestEntry
from src.migrations.runner import run_pending_migrations


def _noop(cfg: dict) -> None:
    """Upgrade script stub — mutates nothing."""


def _make_entry(from_v: str, to_v: str, script=None) -> ManifestEntry:
    return ManifestEntry(from_version=from_v, to_version=to_v, upgrade_script=script or _noop)


def _write_config(global_bees_dir, schema_version: str) -> None:
    """Write a minimal config.json with the given schema_version."""
    (global_bees_dir / "config.json").write_text(
        json.dumps({"scopes": {}, "schema_version": schema_version})
    )


def _read_version(global_bees_dir) -> str:
    return json.loads((global_bees_dir / "config.json").read_text())["schema_version"]


# ---------------------------------------------------------------------------
# No pending hops
# ---------------------------------------------------------------------------


def test_already_up_to_date(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "2.0")
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: [])

    result = run_pending_migrations()

    assert result == {"status": "success", "message": "Already up to date", "version": "2.0"}


# ---------------------------------------------------------------------------
# Single hop
# ---------------------------------------------------------------------------


def test_single_hop_applied_and_saved(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "1.0")
    hop = _make_entry("1.0", "2.0")
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: [hop])

    result = run_pending_migrations()

    assert result["status"] == "success"
    assert result["message"] == "Applied 1 migration(s)"
    assert result["final_version"] == "2.0"
    assert result["applied_hops"] == [{"from_version": "1.0", "to_version": "2.0"}]
    assert _read_version(mock_global_bees_dir) == "2.0"


# ---------------------------------------------------------------------------
# Multi-hop chain
# ---------------------------------------------------------------------------


def test_multi_hop_chain_applied_in_order(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "1.0")
    hops = [_make_entry("1.0", "2.0"), _make_entry("2.0", "3.0")]
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: hops)

    result = run_pending_migrations()

    assert result["final_version"] == "3.0"
    assert len(result["applied_hops"]) == 2
    assert result["applied_hops"][-1] == {"from_version": "2.0", "to_version": "3.0"}
    assert _read_version(mock_global_bees_dir) == "3.0"


# ---------------------------------------------------------------------------
# Exception mid-chain — schema_version stays at last successful hop
# ---------------------------------------------------------------------------


def test_exception_mid_chain_persists_last_good_version(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "1.0")

    def _boom(cfg: dict) -> None:
        raise RuntimeError("migration failed")

    hops = [_make_entry("1.0", "2.0"), _make_entry("2.0", "3.0", script=_boom)]
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: hops)

    with pytest.raises(RuntimeError, match="migration failed"):
        run_pending_migrations()

    assert _read_version(mock_global_bees_dir) == "2.0"


# ---------------------------------------------------------------------------
# ValueError mid-chain — returns clean error result, does not raise
# ---------------------------------------------------------------------------


def test_value_error_returns_clean_error_result(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "1.0")

    def _collision(cfg: dict) -> None:
        raise ValueError("collision detected in migration")

    hops = [_make_entry("1.0", "2.0", script=_collision)]
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: hops)

    result = run_pending_migrations()

    assert result["status"] == "error"
    assert "collision" in result["message"]
    assert _read_version(mock_global_bees_dir) == "1.0"


# ---------------------------------------------------------------------------
# Idempotency — running twice when already up to date is safe
# ---------------------------------------------------------------------------


def test_idempotent_when_already_up_to_date(mock_global_bees_dir, monkeypatch):
    _write_config(mock_global_bees_dir, "2.0")
    monkeypatch.setattr(runner_mod, "find_pending_hops", lambda v: [])

    result1 = run_pending_migrations()
    result2 = run_pending_migrations()

    assert result1["message"] == "Already up to date"
    assert result2["message"] == "Already up to date"
    assert _read_version(mock_global_bees_dir) == "2.0"
