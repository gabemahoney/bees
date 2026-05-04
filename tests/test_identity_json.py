"""
Unit tests for identity.json read/write utilities.

PURPOSE:
Tests the read_identity and write_identity helper functions that handle
atomic reads and writes of .hive/identity.json marker files.

SCOPE - Tests that belong here:
- read_identity(): Missing file, valid JSON, corrupt JSON, all field variants
- write_identity(): File creation, overwrite, atomicity, cleanup on error

SCOPE - Tests that DON'T belong here:
- colonize_hive identity handling -> test_colonize_hive.py
- scan_for_hive identity parsing -> test_mcp_scan_validate.py
- Hive marker directory creation -> test_colonize_hive.py

RELATED FILES:
- src/mcp_hive_ops.py: Contains read_identity and write_identity
- test_colonize_hive.py: Integration tests that exercise identity via colonize_hive
"""

import json

import pytest

from src.mcp_hive_ops import read_identity, write_identity


# -- Fixtures -----------------------------------------------------------------

IDENTITY_ALL_FIELDS = {
    "normalized_name": "back_end",
    "display_name": "Back End",
    "created_at": "2026-01-15T10:30:00",
    "version": "0.1",
    "child_tiers": {"t1": ["Epic", "Epics"]},
    "status_values": ["open", "closed", "in_progress"],
    "description": "Backend services hive",
}

IDENTITY_MINIMAL = {
    "normalized_name": "bugs",
    "display_name": "Bugs",
    "created_at": "2026-01-01T00:00:00",
    "version": "0.1",
}


# -- read_identity tests ------------------------------------------------------


class TestReadIdentity:
    """Tests for read_identity() function."""

    def test_returns_none_when_file_missing(self, tmp_path):
        """read_identity returns None when identity.json does not exist."""
        result = read_identity(tmp_path)
        assert result is None

    def test_returns_dict_for_valid_json_all_fields(self, tmp_path):
        """read_identity returns parsed dict when file has all 7 fields."""
        (tmp_path / "identity.json").write_text(json.dumps(IDENTITY_ALL_FIELDS))

        result = read_identity(tmp_path)

        assert result == IDENTITY_ALL_FIELDS
        assert result["normalized_name"] == "back_end"
        assert result["child_tiers"] == {"t1": ["Epic", "Epics"]}
        assert result["status_values"] == ["open", "closed", "in_progress"]
        assert result["description"] == "Backend services hive"

    def test_returns_dict_for_valid_json_minimal_fields(self, tmp_path):
        """read_identity returns parsed dict with only the 4 original required fields (backward compat)."""
        (tmp_path / "identity.json").write_text(json.dumps(IDENTITY_MINIMAL))

        result = read_identity(tmp_path)

        assert result == IDENTITY_MINIMAL
        assert "child_tiers" not in result
        assert "status_values" not in result

    def test_raises_on_corrupt_json(self, tmp_path):
        """read_identity raises ValueError when file contains invalid JSON."""
        (tmp_path / "identity.json").write_text("{ invalid json !!!")

        with pytest.raises(ValueError, match="Corrupt identity file"):
            read_identity(tmp_path)

    def test_raises_on_empty_file(self, tmp_path):
        """read_identity raises ValueError for an empty file (invalid JSON)."""
        (tmp_path / "identity.json").write_text("")

        with pytest.raises(ValueError, match=str(tmp_path / "identity.json")):
            read_identity(tmp_path)

    def test_returns_dict_with_extra_unknown_fields(self, tmp_path):
        """read_identity returns the full dict even if it contains unexpected keys."""
        data = {**IDENTITY_MINIMAL, "unknown_future_field": 42}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        result = read_identity(tmp_path)

        assert result is not None
        assert result["unknown_future_field"] == 42

    def test_raises_on_missing_normalized_name(self, tmp_path):
        """read_identity raises ValueError when normalized_name field is absent."""
        data = {"display_name": "Bugs", "created_at": "2026-01-01T00:00:00", "version": "0.1"}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        with pytest.raises(ValueError, match="missing required field 'normalized_name'"):
            read_identity(tmp_path)

    def test_raises_on_wrong_type_normalized_name(self, tmp_path):
        """read_identity raises ValueError when normalized_name is not a string."""
        data = {**IDENTITY_MINIMAL, "normalized_name": 123}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        with pytest.raises(ValueError, match="'normalized_name' must be a string"):
            read_identity(tmp_path)

    def test_raises_on_invalid_child_tiers_shape(self, tmp_path):
        """read_identity raises ValueError when child_tiers is not a dict."""
        data = {**IDENTITY_MINIMAL, "child_tiers": "not a dict"}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        with pytest.raises(ValueError, match="child_tiers"):
            read_identity(tmp_path)

    def test_raises_on_invalid_status_values_shape(self, tmp_path):
        """read_identity raises ValueError when status_values is a dict instead of list."""
        data = {**IDENTITY_MINIMAL, "status_values": {"not": "a list"}}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        with pytest.raises(ValueError, match="status_values"):
            read_identity(tmp_path)

    def test_valid_status_values_null_is_allowed(self, tmp_path):
        """read_identity accepts status_values=null without raising."""
        data = {**IDENTITY_MINIMAL, "status_values": None}
        (tmp_path / "identity.json").write_text(json.dumps(data))

        result = read_identity(tmp_path)

        assert result is not None
        assert result["status_values"] is None


# -- write_identity tests -----------------------------------------------------


class TestWriteIdentity:
    """Tests for write_identity() function."""

    def test_creates_file_with_correct_content(self, tmp_path):
        """write_identity creates identity.json with the provided data."""
        write_identity(tmp_path, IDENTITY_ALL_FIELDS)

        identity_file = tmp_path / "identity.json"
        assert identity_file.exists()

        with open(identity_file) as f:
            written = json.load(f)
        assert written == IDENTITY_ALL_FIELDS

    def test_overwrites_existing_file(self, tmp_path):
        """write_identity atomically replaces an existing identity.json."""
        old_data = IDENTITY_MINIMAL
        new_data = IDENTITY_ALL_FIELDS

        # Write initial file
        write_identity(tmp_path, old_data)
        assert json.loads((tmp_path / "identity.json").read_text()) == old_data

        # Overwrite with new data
        write_identity(tmp_path, new_data)
        assert json.loads((tmp_path / "identity.json").read_text()) == new_data

    def test_no_temp_files_left_after_write(self, tmp_path):
        """No .identity.json.* temp files remain after a successful write."""
        write_identity(tmp_path, IDENTITY_MINIMAL)

        temp_files = list(tmp_path.glob(".identity.json.*"))
        assert temp_files == [], f"Temp files left behind: {temp_files}"

    def test_round_trip_all_fields(self, tmp_path):
        """write_identity followed by read_identity returns identical data."""
        write_identity(tmp_path, IDENTITY_ALL_FIELDS)
        result = read_identity(tmp_path)
        assert result == IDENTITY_ALL_FIELDS

    def test_round_trip_minimal_fields(self, tmp_path):
        """write_identity followed by read_identity works with minimal 4-field dict."""
        write_identity(tmp_path, IDENTITY_MINIMAL)
        result = read_identity(tmp_path)
        assert result == IDENTITY_MINIMAL

    def test_file_ends_with_newline(self, tmp_path):
        """write_identity produces a file ending in a newline (POSIX convention)."""
        write_identity(tmp_path, IDENTITY_MINIMAL)
        raw = (tmp_path / "identity.json").read_text()
        assert raw.endswith("\n")

    def test_raises_oserror_on_write_failure(self, tmp_path):
        """write_identity raises OSError when the target directory is not writable."""
        # Create a read-only directory
        readonly_dir = tmp_path / "readonly_marker"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        try:
            with pytest.raises(OSError, match="Failed to write identity"):
                write_identity(readonly_dir, IDENTITY_MINIMAL)
        finally:
            readonly_dir.chmod(0o755)

    def test_no_temp_files_left_after_write_failure(self, tmp_path):
        """On write failure, no partial temp files are left behind."""
        readonly_dir = tmp_path / "readonly_marker"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)

        try:
            with pytest.raises(OSError):
                write_identity(readonly_dir, IDENTITY_MINIMAL)

            # Restore permissions to inspect directory
            readonly_dir.chmod(0o755)
            temp_files = list(readonly_dir.glob(".identity.json.*"))
            assert temp_files == [], f"Temp files left after failure: {temp_files}"
        finally:
            readonly_dir.chmod(0o755)

    def test_omits_optional_none_fields(self, tmp_path):
        """write_identity omits optional fields whose value is None."""
        data = {
            **IDENTITY_MINIMAL,
            "child_tiers": None,
            "description": None,
            "allowed_resolvers": None,
        }
        write_identity(tmp_path, data)

        written = json.loads((tmp_path / "identity.json").read_text())
        assert "child_tiers" not in written
        assert "description" not in written
        assert "allowed_resolvers" not in written
        # Required fields still present
        assert written["normalized_name"] == "bugs"

    def test_writes_status_values_null_when_explicitly_null(self, tmp_path):
        """write_identity writes status_values: null when status_values_explicitly_null is True."""
        data = {
            **IDENTITY_MINIMAL,
            "status_values": None,
            "status_values_explicitly_null": True,
        }
        write_identity(tmp_path, data)

        written = json.loads((tmp_path / "identity.json").read_text())
        assert "status_values" in written
        assert written["status_values"] is None

    def test_omits_status_values_when_not_explicit(self, tmp_path):
        """write_identity omits status_values when None and no explicitly_null flag."""
        data = {**IDENTITY_MINIMAL, "status_values": None}
        write_identity(tmp_path, data)

        written = json.loads((tmp_path / "identity.json").read_text())
        assert "status_values" not in written

    def test_status_values_explicitly_null_not_written_to_json(self, tmp_path):
        """The control flag status_values_explicitly_null never appears in the written JSON."""
        data = {
            **IDENTITY_MINIMAL,
            "status_values": None,
            "status_values_explicitly_null": True,
        }
        write_identity(tmp_path, data)

        written = json.loads((tmp_path / "identity.json").read_text())
        assert "status_values_explicitly_null" not in written
