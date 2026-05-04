"""Tests for the v3 → v4 migration: move hive-level child_tiers / status_values
from config.json hive entries to each hive's identity.json."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path

import pytest

from src.migrations.upgrade_v3_to_v4 import upgrade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hive(tmp_path: Path, name: str, identity: dict | None = None) -> Path:
    """Create a hive directory with .hive marker and optional identity.json."""
    hive_dir = tmp_path / name
    marker = hive_dir / ".hive"
    marker.mkdir(parents=True)
    if identity is not None:
        (marker / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    return hive_dir


def _read_identity(hive_dir: Path) -> dict:
    """Read identity.json from a hive's .hive directory."""
    return json.loads((hive_dir / ".hive" / "identity.json").read_text())


def _config_with_hive(hive_path: str, hive_name: str = "my_hive", **extra) -> dict:
    """Minimal config with one hive in one scope."""
    hive_data = {"path": hive_path, "display_name": "My Hive", "created_at": "2026-01-01"}
    hive_data.update(extra)
    return {"scopes": {"/repo/**": {"hives": {hive_name: hive_data}}}}


# ---------------------------------------------------------------------------
# 1. Successful migration
# ---------------------------------------------------------------------------


class TestSuccessfulMigration:
    """child_tiers/status_values moved from config.json hive entry to identity.json,
    removed from config.json."""

    def test_child_tiers_and_status_values_copied_to_identity(self, tmp_path):
        hive_dir = _make_hive(tmp_path, "bugs", identity={
            "normalized_name": "bugs",
            "display_name": "Bugs",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="bugs",
            child_tiers={"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]},
            status_values=["open", "closed", "in-progress"],
        )

        upgrade(config)

        identity = _read_identity(hive_dir)
        assert identity["child_tiers"] == {"t1": ["Epic", "Epics"], "t2": ["Task", "Tasks"]}
        assert identity["status_values"] == ["open", "closed", "in-progress"]

    def test_migrated_keys_removed_from_config(self, tmp_path):
        hive_dir = _make_hive(tmp_path, "bugs", identity={
            "normalized_name": "bugs",
            "display_name": "Bugs",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="bugs",
            child_tiers={"t1": ["Epic", "Epics"]},
            status_values=["open", "closed"],
        )

        upgrade(config)

        hive_entry = config["scopes"]["/repo/**"]["hives"]["bugs"]
        assert "child_tiers" not in hive_entry
        assert "status_values" not in hive_entry
        assert "status_values_explicitly_null" not in hive_entry

    def test_non_migrated_keys_preserved(self, tmp_path):
        hive_dir = _make_hive(tmp_path, "bugs", identity={
            "normalized_name": "bugs",
            "display_name": "Bugs",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="bugs",
            child_tiers={"t1": ["Epic", "Epics"]},
            allowed_resolvers=["file-path"],
        )

        upgrade(config)

        hive_entry = config["scopes"]["/repo/**"]["hives"]["bugs"]
        assert hive_entry["path"] == str(hive_dir)
        assert hive_entry["display_name"] == "My Hive"
        assert hive_entry["allowed_resolvers"] == ["file-path"]

    def test_creates_identity_when_none_exists(self, tmp_path):
        """When no identity.json exists, migration creates one from scratch."""
        hive_dir = tmp_path / "fresh"
        (hive_dir / ".hive").mkdir(parents=True)

        config = _config_with_hive(
            str(hive_dir),
            hive_name="fresh",
            child_tiers={"t1": ["Epic", "Epics"]},
        )

        upgrade(config)

        identity = _read_identity(hive_dir)
        assert identity["normalized_name"] == "fresh"
        assert identity["child_tiers"] == {"t1": ["Epic", "Epics"]}


# ---------------------------------------------------------------------------
# 2. Inaccessible hive path
# ---------------------------------------------------------------------------


class TestInaccessibleHive:
    """Hive entry removed from config.json, no identity.json written, warning logged."""

    def test_hive_without_marker_deregistered(self, tmp_path):
        """Hive path exists but has no .hive directory → deregistered."""
        bad_path = tmp_path / "gone"
        bad_path.mkdir()

        config = _config_with_hive(
            str(bad_path),
            hive_name="dead_hive",
            child_tiers={"t1": ["Epic", "Epics"]},
        )

        upgrade(config)

        assert "dead_hive" not in config["scopes"]["/repo/**"]["hives"]

    def test_nonexistent_path_deregistered(self, tmp_path):
        """Hive path doesn't exist at all → deregistered."""
        config = _config_with_hive(str(tmp_path / "nonexistent"), hive_name="ghost")

        upgrade(config)

        assert "ghost" not in config["scopes"]["/repo/**"]["hives"]

    def test_no_identity_json_written(self, tmp_path):
        """No identity.json is created for inaccessible hives."""
        bad_path = tmp_path / "nope"
        bad_path.mkdir()

        config = _config_with_hive(
            str(bad_path),
            hive_name="nope",
            child_tiers={"t1": ["Epic", "Epics"]},
        )

        upgrade(config)

        assert not (bad_path / ".hive" / "identity.json").exists()

    def test_warning_logged(self, tmp_path, caplog):
        """A warning is logged when deregistering an inaccessible hive."""
        bad_path = tmp_path / "missing"
        bad_path.mkdir()

        config = _config_with_hive(str(bad_path), hive_name="missing_hive")

        with caplog.at_level(logging.WARNING):
            upgrade(config)

        assert any(
            "deregistering" in rec.message.lower() and "missing_hive" in rec.message
            for rec in caplog.records
        )


# ---------------------------------------------------------------------------
# 3. status_values_explicitly_null preservation
# ---------------------------------------------------------------------------


class TestStatusValuesExplicitlyNull:
    """Explicit null in config.json written as null to identity.json (not omitted)."""

    def test_explicit_null_written_as_null_in_identity(self, tmp_path):
        """status_values_explicitly_null=True in config → status_values: null in identity.json."""
        hive_dir = _make_hive(tmp_path, "plans", identity={
            "normalized_name": "plans",
            "display_name": "Plans",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="plans",
            status_values_explicitly_null=True,
        )

        upgrade(config)

        identity = _read_identity(hive_dir)
        # Key must be present with null value — not omitted
        assert "status_values" in identity
        assert identity["status_values"] is None

    def test_explicit_null_flag_removed_from_config(self, tmp_path):
        hive_dir = _make_hive(tmp_path, "plans", identity={
            "normalized_name": "plans",
            "display_name": "Plans",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="plans",
            status_values_explicitly_null=True,
        )

        upgrade(config)

        hive_entry = config["scopes"]["/repo/**"]["hives"]["plans"]
        assert "status_values_explicitly_null" not in hive_entry
        assert "status_values" not in hive_entry


# ---------------------------------------------------------------------------
# 4. Config.json precedence (SR-6.2)
# ---------------------------------------------------------------------------


class TestConfigJsonPrecedence:
    """When identity.json already has values AND config.json has different values,
    config.json values WIN (overwrite marker). Per SRD SR-6.2, config.json is
    authoritative pre-migration."""

    def test_config_child_tiers_overwrite_marker_values(self, tmp_path):
        """Config.json child_tiers OVERWRITE existing identity.json child_tiers."""
        marker_tiers = {"t1": ["OldEpic", "OldEpics"], "t2": ["OldTask", "OldTasks"]}
        config_tiers = {"t1": ["NewEpic", "NewEpics"]}

        hive_dir = _make_hive(tmp_path, "backend", identity={
            "normalized_name": "backend",
            "display_name": "Backend",
            "created_at": "2026-01-01",
            "child_tiers": marker_tiers,
        })
        config = _config_with_hive(str(hive_dir), hive_name="backend", child_tiers=config_tiers)

        upgrade(config)

        identity = _read_identity(hive_dir)
        # Config.json values WIN — marker values are overwritten
        assert identity["child_tiers"] == config_tiers
        assert identity["child_tiers"] != marker_tiers

    def test_config_status_values_overwrite_marker_values(self, tmp_path):
        """Config.json status_values OVERWRITE existing identity.json status_values."""
        marker_statuses = ["old_open", "old_closed"]
        config_statuses = ["open", "in_progress", "done"]

        hive_dir = _make_hive(tmp_path, "backend", identity={
            "normalized_name": "backend",
            "display_name": "Backend",
            "created_at": "2026-01-01",
            "status_values": marker_statuses,
        })
        config = _config_with_hive(str(hive_dir), hive_name="backend", status_values=config_statuses)

        upgrade(config)

        identity = _read_identity(hive_dir)
        # Config.json values WIN — marker values are overwritten
        assert identity["status_values"] == config_statuses
        assert identity["status_values"] != marker_statuses

    def test_config_explicit_null_overwrites_marker_list(self, tmp_path):
        """Config.json status_values_explicitly_null=True overwrites marker's non-null list."""
        hive_dir = _make_hive(tmp_path, "backend", identity={
            "normalized_name": "backend",
            "display_name": "Backend",
            "created_at": "2026-01-01",
            "status_values": ["was_open", "was_closed"],
        })
        config = _config_with_hive(str(hive_dir), hive_name="backend", status_values_explicitly_null=True)

        upgrade(config)

        identity = _read_identity(hive_dir)
        # Config.json null wins — overwrites marker's list
        assert identity["status_values"] is None


# ---------------------------------------------------------------------------
# 5. Preview mode — dry-run reports without writing
# ---------------------------------------------------------------------------


class TestPreviewMode:
    """Dry-run reports what would change without writing any files."""

    def test_preview_shows_v3_to_v4_hop(self, mock_global_bees_dir):
        """preview_pending_migrations reports the v3→v4 hop when at schema 3.0."""
        from src.migrations.runner import preview_pending_migrations

        config_data = {"scopes": {}, "schema_version": "3.0"}
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config_data))

        result = preview_pending_migrations()

        assert result["status"] == "success"
        assert result["current_version"] == "3.0"
        hops = result["pending_hops"]
        assert len(hops) >= 1
        v3_hop = next(h for h in hops if h["from_version"] == "3.0")
        assert v3_hop["to_version"] == "4.0"

    def test_preview_does_not_modify_files(self, tmp_path, mock_global_bees_dir):
        """Preview does not write identity.json or modify config."""
        hive_dir = _make_hive(tmp_path, "preview_hive", identity={
            "normalized_name": "preview_hive",
            "display_name": "Preview Hive",
            "created_at": "2026-01-01",
        })
        config_data = {
            "scopes": {
                "/repo/**": {
                    "hives": {
                        "preview_hive": {
                            "path": str(hive_dir),
                            "display_name": "Preview Hive",
                            "created_at": "2026-01-01",
                            "child_tiers": {"t1": ["Epic", "Epics"]},
                        }
                    }
                }
            },
            "schema_version": "3.0",
        }
        (mock_global_bees_dir / "config.json").write_text(json.dumps(config_data))

        from src.migrations.runner import preview_pending_migrations

        identity_before = _read_identity(hive_dir)
        preview_pending_migrations()
        identity_after = _read_identity(hive_dir)

        # No changes written
        assert identity_before == identity_after
        assert "child_tiers" not in identity_after

        # Config file unchanged
        config_on_disk = json.loads((mock_global_bees_dir / "config.json").read_text())
        assert "child_tiers" in config_on_disk["scopes"]["/repo/**"]["hives"]["preview_hive"]


# ---------------------------------------------------------------------------
# 6. Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Running migration twice produces identical result."""

    def test_second_run_is_noop(self, tmp_path):
        hive_dir = _make_hive(tmp_path, "work", identity={
            "normalized_name": "work",
            "display_name": "Work",
            "created_at": "2026-01-01",
        })
        config = _config_with_hive(
            str(hive_dir),
            hive_name="work",
            child_tiers={"t1": ["Story", "Stories"]},
            status_values=["todo", "done"],
        )

        # First run migrates keys
        upgrade(config)
        config_after_first = copy.deepcopy(config)
        identity_after_first = _read_identity(hive_dir)

        # Second run — config has no migrated keys → no-op
        upgrade(config)
        identity_after_second = _read_identity(hive_dir)

        assert config == config_after_first
        assert identity_after_second == identity_after_first

    def test_already_clean_config_unchanged(self, tmp_path):
        """Config with no hive-level migrated keys is unchanged by upgrade."""
        hive_dir = _make_hive(tmp_path, "clean", identity={
            "normalized_name": "clean",
            "display_name": "Clean",
            "created_at": "2026-01-01",
            "child_tiers": {"t1": ["Epic", "Epics"]},
        })
        config = _config_with_hive(str(hive_dir), hive_name="clean")
        before = copy.deepcopy(config)

        upgrade(config)

        assert config == before


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_scopes_noop():
    config = {"scopes": {}}
    upgrade(config)
    assert config == {"scopes": {}}


def test_no_scopes_key_noop():
    config = {}
    upgrade(config)
    assert config == {}


def test_multiple_hives_migrated_independently(tmp_path):
    """Multiple hives in same scope all get migrated."""
    dir_a = _make_hive(tmp_path, "hive_a", identity={
        "normalized_name": "hive_a", "display_name": "A", "created_at": "2026-01-01",
    })
    dir_b = _make_hive(tmp_path, "hive_b", identity={
        "normalized_name": "hive_b", "display_name": "B", "created_at": "2026-01-01",
    })
    config = {
        "scopes": {
            "/repo/**": {
                "hives": {
                    "hive_a": {"path": str(dir_a), "display_name": "A", "created_at": "2026-01-01", "child_tiers": {"t1": ["Epic", "Epics"]}},
                    "hive_b": {"path": str(dir_b), "display_name": "B", "created_at": "2026-01-01", "status_values": ["open", "done"]},
                }
            }
        }
    }

    upgrade(config)

    assert _read_identity(dir_a)["child_tiers"] == {"t1": ["Epic", "Epics"]}
    assert _read_identity(dir_b)["status_values"] == ["open", "done"]
    assert "child_tiers" not in config["scopes"]["/repo/**"]["hives"]["hive_a"]
    assert "status_values" not in config["scopes"]["/repo/**"]["hives"]["hive_b"]
