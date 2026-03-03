"""
Unit tests for core linter engine, general ticket validation, report
data structures, and hive-specific validation rules.
"""

import json
import os
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from src.linter import Linter, TicketScanner
from src.linter_report import LinterReport, ValidationError
from tests.helpers import make_ticket, write_ticket_file
from tests.test_constants import (
    DANGLING_BEE_ID,
    GUID_EXAMPLE_T1,
    HIVE_BACKEND,
    TICKET_ID_ABC,
    TICKET_ID_LINTER_CHILD1,
    TICKET_ID_LINTER_CHILD2,
    TICKET_ID_LINTER_CHILD3,
    TICKET_ID_LINTER_CHILD_SUBTASK,
    TICKET_ID_LINTER_DEP_A,
    TICKET_ID_LINTER_DEP_B,
    TICKET_ID_LINTER_DUP,
    TICKET_ID_LINTER_PARENT_TASK,
    TICKET_ID_LINTER_SUBTASK_MAIN,
    TICKET_ID_LINTER_TASK_MAIN,
    TICKET_ID_LINTER_TIER1,
    TICKET_ID_LINTER_TIER2,
    TICKET_ID_LINTER_TIER3,
    TICKET_ID_LINTER_VALID,
    TICKET_ID_NONEXISTENT,
    TICKET_ID_T1,
    TICKET_ID_XYZ,
)


@contextmanager
def mock_empty_config():
    """Mock load_bees_config to return BeesConfig with empty child_tiers."""
    with patch("src.config.load_bees_config") as mock_config:
        from src.config import BeesConfig, HiveConfig

        # Include default hive for per-hive resolution
        mock_config.return_value = BeesConfig(
            hives={
                "default": HiveConfig(
                    path="/tmp/default", display_name="Default", created_at="2026-02-05T00:00:00"
                )
            },
            child_tiers={},
        )
        yield mock_config


@contextmanager
def mock_config_with_tiers(tiers: dict):
    """Mock load_bees_config to return BeesConfig with given child_tiers."""
    with patch("src.config.load_bees_config") as mock_config:
        from src.config import BeesConfig, HiveConfig

        # Include default hive for per-hive resolution
        mock_config.return_value = BeesConfig(
            hives={
                "default": HiveConfig(
                    path="/tmp/default", display_name="Default", created_at="2026-02-05T00:00:00"
                )
            },
            child_tiers=tiers,
        )
        yield mock_config


def _make_subdirs(tmp_path, *names):
    """Create subdirectories and return them as a dict."""
    dirs = {}
    for name in names:
        d = tmp_path / name
        d.mkdir()
        dirs[name] = d
    return dirs


class TestTicketScanner:
    """Tests for TicketScanner class."""

    def test_create_scanner(self, tmp_path):
        """Should create scanner with tickets directory."""
        scanner = TicketScanner(str(tmp_path))
        assert scanner.tickets_dir == tmp_path

    def test_scan_all_empty_directory(self, tmp_path):
        """Should handle empty tickets directory."""
        scanner = TicketScanner(str(tmp_path))
        assert len(list(scanner.scan_all())) == 0

    def test_scan_all_missing_directory_raises_error(self, tmp_path):
        """Should raise error if tickets directory doesn't exist."""
        scanner = TicketScanner(str(tmp_path / "nonexistent"))
        with pytest.raises(FileNotFoundError, match="Tickets directory not found"):
            list(scanner.scan_all())

    def test_scan_all_loads_tickets(self, tmp_path):
        """Should load tickets from hierarchical directory structure."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Test Epic", type="bee", body="Epic description.")
        write_ticket_file(
            tmp_path / TICKET_ID_ABC,
            TICKET_ID_LINTER_TASK_MAIN,
            title="Test Task",
            type="t1",
            parent=TICKET_ID_ABC,
            body="Task description.",
        )
        write_ticket_file(
            tmp_path / TICKET_ID_ABC / TICKET_ID_LINTER_TASK_MAIN,
            TICKET_ID_LINTER_SUBTASK_MAIN,
            title="Test Subtask",
            type="t2",
            parent=TICKET_ID_LINTER_TASK_MAIN,
            body="Subtask description.",
        )

        tickets = list(TicketScanner(str(tmp_path)).scan_all())
        assert len(tickets) == 3
        assert any(t.id == TICKET_ID_ABC and t.type == "bee" for t in tickets)
        assert any(t.id == TICKET_ID_LINTER_TASK_MAIN and t.type == "t1" for t in tickets)
        assert any(t.id == TICKET_ID_LINTER_SUBTASK_MAIN and t.type == "t2" for t in tickets)

    def test_scan_all_excludes_evicted_directory(self, tmp_path):
        """Scanner should not yield tickets inside evicted/ subdirectory."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Active Ticket")

        evicted_dir = tmp_path / "evicted"
        evicted_dir.mkdir()
        write_ticket_file(evicted_dir, TICKET_ID_XYZ, title="Evicted Ticket")

        tickets = list(TicketScanner(str(tmp_path)).scan_all())
        ticket_ids = {t.id for t in tickets}
        assert TICKET_ID_ABC in ticket_ids
        assert TICKET_ID_XYZ not in ticket_ids

    def test_scan_all_excludes_hidden_directories(self, tmp_path):
        """Scanner should not yield tickets inside .hive/ or other hidden directories."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Active Ticket")

        hive_meta_dir = tmp_path / ".hive"
        hive_meta_dir.mkdir()
        write_ticket_file(hive_meta_dir, TICKET_ID_XYZ, title="Hidden Ticket")

        tickets = list(TicketScanner(str(tmp_path)).scan_all())
        ticket_ids = {t.id for t in tickets}
        assert TICKET_ID_ABC in ticket_ids
        assert TICKET_ID_XYZ not in ticket_ids

    def test_scan_all_handles_invalid_tickets(self, tmp_path):
        """Should skip invalid tickets and continue scanning."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Valid")
        # Create hierarchical structure for invalid ticket to be scanned
        invalid_dir = bees_dir / "b.inv"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        (invalid_dir / "b.inv.md").write_text("No frontmatter here")

        tickets = list(TicketScanner(str(tmp_path)).scan_all())
        assert len(tickets) == 1
        assert tickets[0].id == TICKET_ID_ABC


class TestLinter:
    """Tests for Linter class."""

    def test_create_linter(self):
        """Should create linter with tickets directory."""
        linter = Linter("tickets")
        assert linter.tickets_dir == "tickets"
        assert isinstance(linter.scanner, TicketScanner)

    def test_run_empty_tickets(self, tmp_path):
        """Should handle empty tickets directory."""
        report = Linter(str(tmp_path)).run()
        assert isinstance(report, LinterReport)
        assert len(report.errors) == 0
        assert not report.is_corrupt()

    def test_validate_id_format_valid(self, tmp_path):
        """Should pass validation for valid ID format."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test")
        report = Linter(str(tmp_path)).run()
        assert len(report.get_errors(error_type="invalid_id")) == 0

    def test_validate_id_format_invalid(self, tmp_path):
        """Linter detects tickets with invalid IDs loaded permissively by reader."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Valid")
        # Create hierarchical structure for invalid ticket
        invalid_dir = tmp_path / "INVALID-ID"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        (invalid_dir / "INVALID-ID.md").write_text(f"""---
id: INVALID-ID
schema_version: '1.1'
type: t1
title: Invalid
parent: {TICKET_ID_ABC}
---

Body.""")

        report = Linter(str(tmp_path)).run()
        format_errors = report.get_errors(error_type="invalid_id")
        assert len(format_errors) == 1
        assert format_errors[0].ticket_id == "INVALID-ID"

    @pytest.mark.parametrize(
        "title,expect_error",
        [
            pytest.param("Title with newline\n", True, id="title_with_lf"),
            pytest.param("Title with carriage return\r", True, id="title_with_cr"),
            pytest.param("Title without newlines", False, id="title_without_newlines"),
            pytest.param("Title with both\n\r", True, id="title_with_both"),
        ],
    )
    def test_validate_title_format(self, tmp_path, title, expect_error):
        """Should detect multiline titles."""
        import yaml

        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket with properly quoted title to preserve newlines in YAML
        frontmatter = {
            "id": TICKET_ID_ABC,
            "schema_version": "0.1",
            "title": title,
            "type": "bee",
            "status": "open",
            "tags": [],
            "children": [],
            "up_dependencies": [],
            "down_dependencies": [],
            "created_at": "2024-01-01T00:00:00+00:00",
            "egg": None,
        }
        yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        ticket_file.write_text(f"---\n{yaml_content}---\n\nTest body.")

        report = Linter(str(tmp_path)).run()
        multiline_errors = report.get_errors(error_type="multiline_title")
        if expect_error:
            assert len(multiline_errors) == 1
            assert multiline_errors[0].ticket_id == TICKET_ID_ABC
            assert multiline_errors[0].severity == "warning"
        else:
            assert len(multiline_errors) == 0

    @pytest.mark.parametrize(
        "schema_version,expect_error",
        [
            pytest.param("0.1", False, id="valid_xy_0_1"),
            pytest.param("1.0", False, id="valid_xy_1_0"),
            pytest.param("1.0.0", False, id="valid_xyz_1_0_0"),
            pytest.param("2.1.3", False, id="valid_xyz_2_1_3"),
            pytest.param("10.20.30", False, id="valid_xyz_large_numbers"),
            pytest.param("v1.0.0", True, id="invalid_with_v_prefix"),
            pytest.param("1.0.0-beta", True, id="invalid_with_prerelease"),
            pytest.param("1.0.x", True, id="invalid_with_x"),
        ],
    )
    def test_validate_schema_version(self, tmp_path, schema_version, expect_error):
        """Should validate schema_version format (x.y or x.y.z)."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", schema_version=schema_version)
        report = Linter(str(tmp_path)).run()
        version_errors = report.get_errors(error_type="invalid_schema_version")
        if expect_error:
            assert len(version_errors) == 1
            assert version_errors[0].ticket_id == TICKET_ID_ABC
            assert version_errors[0].severity == "error"
        else:
            assert len(version_errors) == 0

    @pytest.mark.parametrize(
        "created_at,expect_error_type",
        [
            pytest.param("not-a-date", "invalid_date_format", id="invalid_string"),
            pytest.param("2026-02-17T10:30:00", None, id="valid_iso_datetime"),
        ],
    )
    def test_validate_created_at_string(self, tmp_path, created_at, expect_error_type):
        """Should validate created_at string format.

        Note: write_ticket_file always provides a default created_at, so we can't test
        missing created_at with this helper. That case is tested in test_validate_created_at_datetime.
        """
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", created_at=created_at)
        report = Linter(str(tmp_path)).run()

        if expect_error_type:
            errors = report.get_errors(error_type=expect_error_type, ticket_id=TICKET_ID_ABC)
            assert len(errors) == 1
            assert errors[0].severity == "warning"
        else:
            missing_errors = report.get_errors(error_type="missing_date", ticket_id=TICKET_ID_ABC)
            format_errors = report.get_errors(error_type="invalid_date_format", ticket_id=TICKET_ID_ABC)
            assert len(missing_errors) == 0
            assert len(format_errors) == 0

    @pytest.mark.parametrize(
        "created_at,expect_error_type",
        [
            pytest.param(None, "missing_date", id="missing_created_at"),
            pytest.param("2026-02-17", None, id="valid_datetime_object"),
            pytest.param("2026-02-17T10:30:00", None, id="valid_datetime_with_time"),
        ],
    )
    def test_validate_created_at_datetime(self, tmp_path, created_at, expect_error_type):
        """Test created_at validation with datetime objects.

        The reader (reader.py:54) converts ISO 8601 date strings to datetime objects.
        The validator correctly handles this by checking isinstance(created_at, datetime)
        and skipping validation for datetime objects (linter.py:409-410).
        """
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket manually to control created_at value precisely
        if created_at is None:
            content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
status: open
egg: null
---

Test body."""
        else:
            # Write a valid ISO date string that reader will parse as datetime object
            content = f"""---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
status: open
created_at: '{created_at}'
egg: null
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()

        if expect_error_type == "missing_date":
            errors = report.get_errors(error_type=expect_error_type, ticket_id=TICKET_ID_ABC)
            assert len(errors) == 1
            assert errors[0].severity == "warning"
        else:
            # No errors expected - datetime objects are handled correctly
            missing_errors = report.get_errors(error_type="missing_date", ticket_id=TICKET_ID_ABC)
            format_errors = report.get_errors(error_type="invalid_date_format", ticket_id=TICKET_ID_ABC)
            assert len(missing_errors) == 0
            assert len(format_errors) == 0

    def test_validate_id_uniqueness_detects_duplicates(self, tmp_path):
        """Should detect duplicate IDs and mark report as corrupt."""
        write_ticket_file(tmp_path, TICKET_ID_LINTER_DUP, title="Dup 1")
        # Create hierarchical structure for duplicate ticket at a different location
        dup_dir = tmp_path / "duplicate" / TICKET_ID_LINTER_DUP
        dup_dir.mkdir(parents=True, exist_ok=True)
        (dup_dir / f"{TICKET_ID_LINTER_DUP}.md").write_text(f"""---
id: {TICKET_ID_LINTER_DUP}
schema_version: '1.1'
type: bee
title: Dup 2
---

Body.""")

        report = Linter(str(tmp_path)).run()
        assert len(report.get_errors(error_type="duplicate_id")) == 1
        assert report.is_corrupt()


class TestBidirectionalValidation:
    """Tests for bidirectional relationship validation."""

    def test_orphaned_ticket_child_missing_from_parent_children(self, tmp_path):
        """Child lists parent but parent missing child in children array → orphaned_ticket error."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Parent Epic", children=[], body="Parent.")
        write_ticket_file(
            tmp_path / TICKET_ID_ABC,
            TICKET_ID_LINTER_TASK_MAIN,
            title="Child Task",
            type="t1",
            parent=TICKET_ID_ABC,
            body="Child.",
        )

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="orphaned_ticket")
        assert len(errors) == 1
        assert "does not list" in errors[0].message

    def test_asymmetric_policy_parent_lists_child_without_backlink_no_error(self, tmp_path):
        """Parent lists child but child missing parent field → NO error (asymmetric policy)."""
        write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Parent Epic", children=[TICKET_ID_LINTER_TASK_MAIN], body="Parent."
        )
        write_ticket_file(tmp_path / TICKET_ID_ABC, TICKET_ID_LINTER_TASK_MAIN, title="Child Task", type="t1", body="Child.")

        report = Linter(str(tmp_path)).run()
        # Asymmetric policy: parent→child direction NOT enforced, no "orphaned_parent" error
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 0

    def test_parent_children_multiple_children_asymmetric_policy(self, tmp_path):
        """Parent listing child without backlink → NO error (asymmetric policy)."""
        write_ticket_file(
            tmp_path,
            TICKET_ID_ABC,
            title="Parent",
            children=[TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD2, TICKET_ID_LINTER_CHILD3],
            body="Parent.",
        )
        write_ticket_file(
            tmp_path / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child 1",
            type="t1",
            parent=TICKET_ID_ABC,
            body="Child 1.",
        )
        write_ticket_file(
            tmp_path / TICKET_ID_ABC, TICKET_ID_LINTER_CHILD2, title="Child 2", type="t1", body="Child 2."
        )  # Missing parent
        write_ticket_file(
            tmp_path / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD3,
            title="Child 3",
            type="t1",
            parent=TICKET_ID_ABC,
            body="Child 3.",
        )

        report = Linter(str(tmp_path)).run()
        # Asymmetric policy: parent→child NOT enforced, no "orphaned_parent" error
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 0

    @pytest.mark.parametrize(
        "error_type,upstream_down_deps,downstream_up_deps",
        [
            pytest.param("orphaned_dependency", None, [TICKET_ID_LINTER_DEP_A], id="missing_down_dep"),
            pytest.param("missing_backlink", [TICKET_ID_LINTER_DEP_B], None, id="missing_up_dep"),
        ],
    )
    def test_orphaned_dependencies(self, tmp_path, error_type, upstream_down_deps, downstream_up_deps):
        """Should detect orphaned dependencies in both directions."""
        up_kwargs = {"title": "Upstream", "type": "t1", "body": "Up."}
        if upstream_down_deps:
            up_kwargs["down_dependencies"] = upstream_down_deps
        write_ticket_file(tmp_path, TICKET_ID_LINTER_DEP_A, **up_kwargs)

        down_kwargs = {"title": "Downstream", "type": "t1", "body": "Down."}
        if downstream_up_deps:
            down_kwargs["up_dependencies"] = downstream_up_deps
        write_ticket_file(tmp_path, TICKET_ID_LINTER_DEP_B, **down_kwargs)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type=error_type)
        assert len(errors) == 1
        assert "does not list" in errors[0].message

    @pytest.mark.parametrize(
        "parent_id,expected_error",
        [
            pytest.param("INVALID-ID", "invalid_parent_id", id="invalid_parent_id_format"),
            pytest.param(TICKET_ID_NONEXISTENT, "orphaned_ticket", id="parent_does_not_exist"),
            pytest.param(TICKET_ID_ABC, None, id="valid_parent"),
        ],
    )
    def test_validate_parent_field(self, tmp_path, parent_id, expected_error):
        """validate_parent_field should check parent ID format and existence."""
        # Create parent bee if testing valid case (with bidirectional relationship)
        if parent_id == TICKET_ID_ABC:
            write_ticket_file(
                tmp_path, TICKET_ID_ABC, title="Valid Parent", children=[TICKET_ID_LINTER_TASK_MAIN], body="Parent."
            )

        # Create child in appropriate location to avoid directory moves
        child_dir = tmp_path / parent_id if parent_id == TICKET_ID_ABC else tmp_path
        write_ticket_file(
            child_dir,
            TICKET_ID_LINTER_TASK_MAIN,
            title="Child Task",
            type="t1",
            parent=parent_id,
            body="Child.",
        )

        report = Linter(str(tmp_path)).run()

        if expected_error:
            errors = report.get_errors(error_type=expected_error, ticket_id=TICKET_ID_LINTER_TASK_MAIN)
            assert len(errors) >= 1
            if expected_error == "invalid_parent_id":
                assert any("invalid parent ID format" in e.message for e in errors)
            elif expected_error == "orphaned_ticket":
                assert any("non-existent parent" in e.message or "does not list" in e.message for e in errors)
        else:
            # Valid parent - no errors (both parent exists AND bidirectional relationship is valid)
            parent_errors = report.get_errors(error_type="invalid_parent_id", ticket_id=TICKET_ID_LINTER_TASK_MAIN)
            orphaned_errors = report.get_errors(error_type="orphaned_ticket", ticket_id=TICKET_ID_LINTER_TASK_MAIN)
            assert len(parent_errors) == 0
            assert len(orphaned_errors) == 0

    def test_validate_parent_field_bee_with_no_parent_skipped(self, tmp_path):
        """Bee tickets have no parent field - validation skipped."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Bee", body="Bee ticket.")

        report = Linter(str(tmp_path)).run()

        # No parent validation errors for bees
        parent_errors = report.get_errors(error_type="invalid_parent_id", ticket_id=TICKET_ID_ABC)
        orphaned_errors = report.get_errors(error_type="orphaned_ticket", ticket_id=TICKET_ID_ABC)
        assert len(parent_errors) == 0
        assert len(orphaned_errors) == 0

    @pytest.mark.parametrize(
        "child_id,child_type,expected_error",
        [
            pytest.param("INVALID-ID", "t1", "invalid_child_id", id="invalid_child_id_format"),
            pytest.param(TICKET_ID_LINTER_SUBTASK_MAIN, "t2", "invalid_child_type", id="invalid_child_type_bee_expects_t1"),
            pytest.param(TICKET_ID_LINTER_TASK_MAIN, "t1", None, id="valid_child_type"),
        ],
    )
    def test_validate_children_field(self, tmp_path, child_id, child_type, expected_error):
        """validate_children_field should check child ID format and type hierarchy."""
        with mock_config_with_tiers({"t1": {}, "t2": {}}):
            # Create parent bee
            write_ticket_file(tmp_path, TICKET_ID_ABC, title="Parent Bee", children=[child_id], body="Parent.")

            # Create child if valid ID
            if child_id == TICKET_ID_LINTER_TASK_MAIN or child_id == TICKET_ID_LINTER_SUBTASK_MAIN:
                write_ticket_file(
                    tmp_path / TICKET_ID_ABC,
                    child_id,
                    title="Child",
                    type=child_type,
                    parent=TICKET_ID_ABC,
                    body="Child.",
                )

            report = Linter(str(tmp_path)).run()

            if expected_error:
                # For invalid_child_type, the error appears on the CHILD ticket, not parent
                if expected_error == "invalid_child_type":
                    # Check for invalid_tier_parent error on child ticket (t2 expects t1 parent, not bee)
                    errors = report.get_errors(error_type="invalid_tier_parent", ticket_id=child_id)
                    assert len(errors) >= 1
                    assert "expected t1" in errors[0].message
                else:
                    errors = report.get_errors(error_type=expected_error, ticket_id=TICKET_ID_ABC)
                    assert len(errors) >= 1
                    if expected_error == "invalid_child_id":
                        assert "invalid child ID format" in errors[0].message
            else:
                # Valid child - no errors
                child_id_errors = report.get_errors(error_type="invalid_child_id", ticket_id=TICKET_ID_ABC)
                child_type_errors = report.get_errors(error_type="invalid_child_type", ticket_id=TICKET_ID_ABC)
                tier_parent_errors = report.get_errors(error_type="invalid_tier_parent", ticket_id=TICKET_ID_LINTER_TASK_MAIN)
                assert len(child_id_errors) == 0
                assert len(child_type_errors) == 0
                assert len(tier_parent_errors) == 0

    def test_validate_children_field_missing_child_no_error_asymmetric(self, tmp_path):
        """Parent references child that doesn't exist → NO error (asymmetric policy)."""
        # Parent lists child that doesn't exist
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Parent Bee", children=["t1.zzz.ab"], body="Parent.")

        report = Linter(str(tmp_path)).run()

        # Asymmetric policy: missing children don't cause errors (only invalid format/type do)
        # The child won't be validated since it doesn't exist in the hive
        errors = report.get_errors(ticket_id=TICKET_ID_ABC)
        # Should have no child-related errors (invalid_child_id, invalid_child_type)
        assert all(e.error_type not in ["invalid_child_id", "invalid_child_type"] for e in errors)

    @pytest.mark.parametrize(
        "dependency_id,expect_error",
        [
            pytest.param("INVALID-ID", True, id="invalid_id_format"),
            pytest.param(TICKET_ID_LINTER_DEP_B, False, id="valid_id_format_same_type"),
        ],
    )
    def test_validate_up_dependencies_id_format(self, tmp_path, dependency_id, expect_error):
        """validate_up_dependencies_field should check ID format."""
        # Create upstream ticket (if valid ID)
        if dependency_id == TICKET_ID_LINTER_DEP_B:
            write_ticket_file(tmp_path, TICKET_ID_LINTER_DEP_B, title="Upstream", type="t1", body="Up.")

        # Create downstream ticket with up_dependency
        write_ticket_file(
            tmp_path, TICKET_ID_LINTER_DEP_A, title="Downstream", type="t1", up_dependencies=[dependency_id], body="Down."
        )

        report = Linter(str(tmp_path)).run()

        if expect_error:
            errors = report.get_errors(error_type="invalid_dependency_id", ticket_id=TICKET_ID_LINTER_DEP_A)
            assert len(errors) == 1
            assert "invalid up_dependencies ID format" in errors[0].message
            assert dependency_id in errors[0].message
        else:
            errors = report.get_errors(error_type="invalid_dependency_id", ticket_id=TICKET_ID_LINTER_DEP_A)
            assert len(errors) == 0

    @pytest.mark.parametrize(
        "dependency_id,expect_error",
        [
            pytest.param("INVALID-ID", True, id="invalid_id_format"),
            pytest.param(TICKET_ID_LINTER_DEP_A, False, id="valid_id_format_same_type"),
        ],
    )
    def test_validate_down_dependencies_id_format(self, tmp_path, dependency_id, expect_error):
        """validate_down_dependencies_field should check ID format."""
        # Create downstream ticket (if valid ID)
        if dependency_id == TICKET_ID_LINTER_DEP_A:
            write_ticket_file(tmp_path, TICKET_ID_LINTER_DEP_A, title="Downstream", type="t1", body="Down.")

        # Create upstream ticket with down_dependency
        write_ticket_file(
            tmp_path, TICKET_ID_LINTER_DEP_B, title="Upstream", type="t1", down_dependencies=[dependency_id], body="Up."
        )

        report = Linter(str(tmp_path)).run()

        if expect_error:
            errors = report.get_errors(error_type="invalid_dependency_id", ticket_id=TICKET_ID_LINTER_DEP_B)
            assert len(errors) == 1
            assert "invalid down_dependencies ID format" in errors[0].message
            assert dependency_id in errors[0].message
        else:
            errors = report.get_errors(error_type="invalid_dependency_id", ticket_id=TICKET_ID_LINTER_DEP_B)
            assert len(errors) == 0

    def test_validate_up_dependencies_cross_type(self, tmp_path):
        """Bee with up_dependency pointing to t1 ticket → cross_type_dependency error."""
        # Create t1 ticket (upstream)
        write_ticket_file(tmp_path, TICKET_ID_LINTER_TASK_MAIN, title="Upstream T1", type="t1", body="T1 task.")

        # Create bee ticket with up_dependency pointing to t1 (type mismatch)
        write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Bee", up_dependencies=[TICKET_ID_LINTER_TASK_MAIN], body="Bee."
        )

        report = Linter(str(tmp_path)).run()

        errors = report.get_errors(error_type="cross_type_dependency", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "types must match" in errors[0].message
        assert TICKET_ID_LINTER_TASK_MAIN in errors[0].message
        assert "type bee" in errors[0].message
        assert "type t1" in errors[0].message

    def test_validate_down_dependencies_cross_type(self, tmp_path):
        """Bee with down_dependency pointing to t1 ticket → cross_type_dependency error."""
        # Create t1 ticket (downstream)
        write_ticket_file(tmp_path, TICKET_ID_LINTER_TASK_MAIN, title="Downstream T1", type="t1", body="T1 task.")

        # Create bee ticket with down_dependency pointing to t1 (type mismatch)
        write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Bee", down_dependencies=[TICKET_ID_LINTER_TASK_MAIN], body="Bee."
        )

        report = Linter(str(tmp_path)).run()

        errors = report.get_errors(error_type="cross_type_dependency", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "types must match" in errors[0].message
        assert TICKET_ID_LINTER_TASK_MAIN in errors[0].message
        assert "type bee" in errors[0].message
        assert "type t1" in errors[0].message

    def test_validate_dependencies_same_type_no_error(self, tmp_path):
        """Same-type dependencies (two bees with up/down deps) → no cross_type_dependency error."""
        # Create two bee tickets with bidirectional dependency
        write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Bee A", up_dependencies=[TICKET_ID_LINTER_VALID], body="Bee A depends on Bee B."
        )
        write_ticket_file(
            tmp_path, TICKET_ID_LINTER_VALID, title="Bee B", down_dependencies=[TICKET_ID_ABC], body="Bee B is upstream of Bee A."
        )

        report = Linter(str(tmp_path)).run()

        # No cross_type_dependency errors (both are bees)
        errors = report.get_errors(error_type="cross_type_dependency")
        assert len(errors) == 0

    @pytest.mark.parametrize(
        "parent_lists_child,child_lists_parent,expected_error_type",
        [
            pytest.param(True, False, None, id="parent_lists_child_without_backlink_no_error"),
            pytest.param(False, True, "orphaned_ticket", id="child_lists_parent_without_backlink_error"),
            pytest.param(True, True, None, id="bidirectional_valid_no_error"),
        ],
    )
    def test_asymmetric_policy_enforcement(self, tmp_path, parent_lists_child, child_lists_parent, expected_error_type):
        """Verify asymmetric policy: child→parent enforced, parent→child NOT enforced."""
        parent_kwargs = {"title": "Parent", "body": "Parent."}
        if parent_lists_child:
            parent_kwargs["children"] = [TICKET_ID_LINTER_TASK_MAIN]
        write_ticket_file(tmp_path, TICKET_ID_ABC, **parent_kwargs)

        child_kwargs = {"title": "Child", "type": "t1", "body": "Child."}
        if child_lists_parent:
            child_kwargs["parent"] = TICKET_ID_ABC
        write_ticket_file(tmp_path / TICKET_ID_ABC, TICKET_ID_LINTER_TASK_MAIN, **child_kwargs)

        report = Linter(str(tmp_path)).run()

        if expected_error_type:
            errors = report.get_errors(error_type=expected_error_type)
            assert len(errors) == 1
            assert "does not list" in errors[0].message
        else:
            # No errors expected
            orphaned_errors = report.get_errors(error_type="orphaned_ticket")
            orphaned_parent_errors = report.get_errors(error_type="orphaned_parent")
            assert len(orphaned_errors) == 0
            assert len(orphaned_parent_errors) == 0

    def test_edge_case_self_reference(self, tmp_path):
        """Self-referencing ticket has no errors under asymmetric policy."""
        write_ticket_file(
            tmp_path, TICKET_ID_LINTER_DEP_A, title="Self Reference", type="t1", children=[TICKET_ID_LINTER_DEP_A]
        )

        report = Linter(str(tmp_path)).run()
        # Asymmetric policy: parent→child NOT enforced, no error for self-reference in children
        errors = report.get_errors(error_type="orphaned_parent")
        assert len(errors) == 0


class TestTierValidation:
    """Tests for validate_tier_exists() functionality."""

    def test_linter_catches_multiple_invalid_types(self, tmp_path):
        """Linter should detect all tickets with invalid types."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_LINTER_VALID, title="Valid")
        for i, t in enumerate(["t99", "foo", "bar"]):
            write_ticket_file(bees_dir, f"b.bad{i + 1}", title=f"Bad {i + 1}", type=t)

        with mock_empty_config():
            report = Linter(str(tmp_path)).run()
        assert len(report.get_errors(error_type="unknown_tier")) == 3


class TestTierHierarchyValidation:
    """Tests for tier hierarchy parent type validation."""

    @pytest.mark.parametrize(
        "tiers,tickets,expect_errors",
        [
            pytest.param(
                {"t1": {}},
                [
                    (TICKET_ID_ABC, {"title": "Bee", "children": [TICKET_ID_LINTER_TIER1]}),
                    (TICKET_ID_LINTER_TIER1, {"title": "T1", "type": "t1", "parent": TICKET_ID_ABC}),
                ],
                0,
                id="valid_two_tier",
            ),
            pytest.param(
                {"t1": {}, "t2": {}},
                [
                    (TICKET_ID_ABC, {"title": "Bee", "children": [TICKET_ID_LINTER_TIER1]}),
                    (
                        TICKET_ID_LINTER_TIER1,
                        {"title": "T1", "type": "t1", "parent": TICKET_ID_ABC, "children": [TICKET_ID_LINTER_TIER2]},
                    ),
                    (TICKET_ID_LINTER_TIER2, {"title": "T2", "type": "t2", "parent": TICKET_ID_LINTER_TIER1}),
                ],
                0,
                id="valid_three_tier",
            ),
            pytest.param(
                {"t1": {}, "t2": {}},
                [
                    (TICKET_ID_LINTER_TIER2, {"title": "T2", "type": "t2", "children": [TICKET_ID_LINTER_TIER1]}),
                    (TICKET_ID_LINTER_TIER1, {"title": "T1", "type": "t1", "parent": TICKET_ID_LINTER_TIER2}),
                ],
                1,
                id="invalid_t2_parent_of_t1",
            ),
            pytest.param(
                {"t1": {}, "t2": {}},
                [
                    (TICKET_ID_ABC, {"title": "Bee", "children": [TICKET_ID_LINTER_TIER2]}),
                    (TICKET_ID_LINTER_TIER2, {"title": "T2", "type": "t2", "parent": TICKET_ID_ABC}),
                ],
                1,
                id="invalid_t2_expects_t1_not_bee",
            ),
            pytest.param(
                {"t1": {}, "t2": {}, "t3": {}},
                [
                    (TICKET_ID_ABC, {"title": "Bee", "children": [TICKET_ID_LINTER_TIER1]}),
                    (
                        TICKET_ID_LINTER_TIER1,
                        {"title": "T1", "type": "t1", "parent": TICKET_ID_ABC, "children": [TICKET_ID_LINTER_TIER2]},
                    ),
                    (
                        TICKET_ID_LINTER_TIER2,
                        {
                            "title": "T2",
                            "type": "t2",
                            "parent": TICKET_ID_LINTER_TIER1,
                            "children": [TICKET_ID_LINTER_TIER3],
                        },
                    ),
                    (TICKET_ID_LINTER_TIER3, {"title": "T3", "type": "t3", "parent": TICKET_ID_LINTER_TIER2}),
                ],
                0,
                id="valid_four_tier",
            ),
        ],
    )
    def test_tier_hierarchy(self, tmp_path, tiers, tickets, expect_errors):
        """Should validate tier parent hierarchy correctly."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        for tid, kwargs in tickets:
            write_ticket_file(bees_dir, tid, **kwargs)

        with mock_config_with_tiers(tiers):
            report = Linter(str(tmp_path)).run()
        assert len(report.get_errors(error_type="invalid_tier_parent")) == expect_errors


# ============================================================================
# OLD-FORMAT ID REJECTION
# ============================================================================


class TestLintOldFormatIdRejection:
    """IDs with uppercase chars (old format) are rejected by validation."""

    @pytest.mark.parametrize(
        "old_id",
        [
            pytest.param("b.AMX", id="bee_all_uppercase"),
            pytest.param("t1.X4F2a", id="t1_mixed_case"),
            pytest.param("b.Amx", id="bee_initial_cap"),
            pytest.param("t2.R8P2kAb", id="t2_mixed_case"),
        ],
    )
    def test_old_format_id_rejected(self, old_id):
        """Ticket IDs containing uppercase characters must be rejected as id_format errors."""
        from src.validator import ValidationError, validate_ticket_business

        data = {
            "id": old_id,
            "schema_version": "0.1",
            "title": "Old Format Test",
            "type": "bee" if old_id.startswith("b.") else old_id.split(".")[0],
            "status": "open",
        }
        with pytest.raises(ValidationError, match="Invalid ID format"):
            validate_ticket_business(data)


# ============================================================================
# REPORT DATA STRUCTURES
# ============================================================================


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_create_validation_error(self):
        """Should create validation error with required fields."""
        error = ValidationError(
            ticket_id=TICKET_ID_ABC, error_type="id_format", message="Invalid ID format", severity="error"
        )
        assert error.ticket_id == TICKET_ID_ABC
        assert error.error_type == "id_format"
        assert error.severity == "error"

    @pytest.mark.parametrize(
        "severity,expected",
        [
            pytest.param(None, "error", id="default_severity"),
            pytest.param("warning", "warning", id="warning_severity"),
        ],
    )
    def test_severity_values(self, severity, expected):
        """Should handle valid severity values and defaults."""
        kwargs = {"ticket_id": TICKET_ID_ABC, "error_type": "test", "message": "Test"}
        if severity:
            kwargs["severity"] = severity
        error = ValidationError(**kwargs)
        assert error.severity == expected

    def test_invalid_severity_raises_error(self):
        """Should raise error for invalid severity."""
        with pytest.raises(ValueError, match="Invalid severity"):
            ValidationError(ticket_id=TICKET_ID_ABC, error_type="test", message="Test", severity="invalid")


class TestLinterReport:
    """Tests for LinterReport class."""

    def test_add_and_retrieve_errors(self):
        """Should add errors and retrieve them with various filters."""
        report = LinterReport()
        assert not report.is_corrupt()

        report.add_error(TICKET_ID_ABC, "id_format", "Error 1", severity="error")
        report.add_error(TICKET_ID_LINTER_TASK_MAIN, "duplicate_id", "Error 2", severity="error")
        report.add_error(TICKET_ID_ABC, "missing_parent", "Error 3", severity="error")
        report.add_error(TICKET_ID_LINTER_SUBTASK_MAIN, "minor", "Warning", severity="warning")

        assert len(report.get_errors()) == 4
        assert report.is_corrupt()  # Has errors (not just warnings)

        # Filter by ticket_id
        assert len(report.get_errors(ticket_id=TICKET_ID_ABC)) == 2

        # Filter by error_type
        assert len(report.get_errors(error_type="id_format")) == 1

        # Filter by severity
        assert len(report.get_errors(severity="error")) == 3
        assert len(report.get_errors(severity="warning")) == 1

        # Multiple filters
        assert len(report.get_errors(ticket_id=TICKET_ID_ABC, severity="error")) == 2

    @pytest.mark.parametrize(
        "add_errors,expected_corrupt",
        [
            pytest.param([(TICKET_ID_ABC, "id_format", "Error", "error")], True, id="with_errors"),
            pytest.param([(TICKET_ID_ABC, "minor", "Warning", "warning")], False, id="only_warnings"),
            pytest.param([], False, id="empty_report"),
        ],
    )
    def test_is_corrupt(self, add_errors, expected_corrupt):
        """Should correctly determine corruption status."""
        report = LinterReport()
        for args in add_errors:
            report.add_error(*args)
        assert report.is_corrupt() == expected_corrupt

    def test_to_dict_and_json(self):
        """Should convert report to dict and valid JSON."""
        report = LinterReport()
        report.add_error(TICKET_ID_ABC, "id_format", "Error 1", severity="error")
        report.add_error(TICKET_ID_LINTER_TASK_MAIN, "minor", "Warning 1", severity="warning")

        result = report.to_dict()
        assert result["is_corrupt"] is True
        assert result["error_count"] == 1
        assert result["warning_count"] == 1

        parsed = json.loads(report.to_json())
        assert parsed["is_corrupt"] is True

    def test_get_summary(self):
        """Should return summary statistics."""
        report = LinterReport()
        report.add_error(TICKET_ID_ABC, "id_format", "Error 1", severity="error")
        report.add_error(TICKET_ID_LINTER_TASK_MAIN, "id_format", "Error 2", severity="error")
        report.add_error(TICKET_ID_LINTER_SUBTASK_MAIN, "duplicate_id", "Error 3", severity="error")
        report.add_error(TICKET_ID_ABC, "minor", "Warning", severity="warning")

        summary = report.get_summary()
        assert summary["total_errors"] == 3
        assert summary["total_warnings"] == 1
        assert summary["affected_tickets"] == 3
        assert summary["by_type"]["id_format"]["errors"] == 2

    def test_to_markdown(self):
        """Should generate correct markdown for various report states."""
        # Empty report
        assert "No validation errors found" in LinterReport().to_markdown()

        # Report with errors
        report = LinterReport()
        report.add_error(TICKET_ID_ABC, "id_format", "Invalid format", severity="error")
        report.add_error(TICKET_ID_LINTER_SUBTASK_MAIN, "duplicate_id", "Duplicate", severity="error")
        markdown = report.to_markdown()
        assert "CORRUPT" in markdown
        assert TICKET_ID_ABC in markdown


# ============================================================================
# HIVE VALIDATION
# ============================================================================


class TestLinterValidateHivePrefix:
    """Tests for linter hive prefix validation."""

    @pytest.mark.parametrize(
        "validate_prefix,expect_errors",
        [
            pytest.param(True, 0, id="enabled"),  # No-op with new ID system
            pytest.param(False, 0, id="disabled"),
        ],
    )
    def test_linter_hive_prefix_validation(self, hive_env, validate_prefix, expect_errors):
        """Test that linter hive prefix validation is a no-op with new ID system."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Correct Prefix", type="bee", status="open")
        # Create hierarchical structure for test ticket
        task_dir = tickets_dir / TICKET_ID_LINTER_TASK_MAIN
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / f"{TICKET_ID_LINTER_TASK_MAIN}.md").write_text(f"""---
id: {TICKET_ID_LINTER_TASK_MAIN}
schema_version: '1.1'
type: bee
title: Wrong Prefix
status: open
---
""")

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND)
        report = linter.run()
        prefix_errors = [e for e in report.errors if e.error_type == "invalid_hive_prefix"]
        # validate_prefix parameter removed - hive prefix validation is no-op with new ID system
        assert len(prefix_errors) == expect_errors


class TestLinterAutoFixMode:
    """Tests for linter auto-fix functionality."""

    def test_linter_auto_fix_orphaned_relationships(self, hive_env):
        """Test that auto-fix mode repairs orphaned parent/child relationships."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent Epic", type="bee", status="open", children=[])
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_TASK_MAIN,
            title="Child Task",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        assert len(report.fixes) > 0
        assert "add_child" in [f.fix_type for f in report.fixes]

    def test_linter_tracks_fixes_in_report(self, hive_env):
        """Test that auto-fix mode tracks all fixes in report."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(
            tickets_dir,
            TICKET_ID_ABC,
            title="Task A",
            type="t1",
            status="open",
            up_dependencies=[TICKET_ID_LINTER_TASK_MAIN],
        )
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_TASK_MAIN, title="Task B", type="t1", status="open", down_dependencies=[]
        )

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        assert len(report.fixes) > 0
        add_dep_fixes = [f for f in report.fixes if f.fix_type == "add_down_dependency"]
        assert len(add_dep_fixes) > 0


# ============================================================================
# DIRECTORY STRUCTURE ENFORCEMENT
# ============================================================================


class TestDirectoryStructureEnforcement:
    """Tests for enforce_directory_structure() auto-fix functionality."""

    def test_child_misplaced_under_wrong_parent_gets_moved(self, hive_env):
        """Child directory under wrong parent is moved to correct parent directory."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create parent bee and two children
        write_ticket_file(
            tickets_dir,
            TICKET_ID_ABC,
            title="Parent Bee",
            status="open",
            children=[TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD2],
        )

        # Create child1 in correct location (under TICKET_ID_ABC)
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child 1",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        # Create child2 in WRONG location (at hive root instead of under parent)
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_CHILD2, title="Child 2", type="t1", status="open", parent=TICKET_ID_ABC
        )

        # Verify initial state: child2 is at wrong location
        wrong_location = tickets_dir / TICKET_ID_LINTER_CHILD2 / f"{TICKET_ID_LINTER_CHILD2}.md"
        correct_location = tickets_dir / TICKET_ID_ABC / TICKET_ID_LINTER_CHILD2 / f"{TICKET_ID_LINTER_CHILD2}.md"
        assert wrong_location.exists()
        assert not correct_location.exists()

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify fix was applied
        move_fixes = [
            f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_LINTER_CHILD2
        ]
        assert len(move_fixes) == 1
        assert "under parent" in move_fixes[0].description.lower()

        # Verify child2 is now in correct location
        assert not wrong_location.exists()
        assert correct_location.exists()

    def test_child_already_in_correct_location_no_action(self, hive_env):
        """Child directory already in correct location triggers no action, no errors."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create parent bee and child in correct location
        write_ticket_file(
            tickets_dir, TICKET_ID_ABC, title="Parent Bee", status="open", children=[TICKET_ID_LINTER_CHILD1]
        )
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child 1",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        # Run linter
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify no move fixes applied for child1
        move_fixes = [
            f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_LINTER_CHILD1
        ]
        assert len(move_fixes) == 0

        # Verify no errors related to child1
        child_errors = [e for e in report.errors if e.ticket_id == TICKET_ID_LINTER_CHILD1]
        assert len(child_errors) == 0

    def test_nested_subtree_moved_as_unit(self, hive_env):
        """Nested subtree (child with grandchildren) is moved as a unit."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create 3-level hierarchy: bee → child → grandchild
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee", status="open", children=[TICKET_ID_LINTER_CHILD1])

        # Create child at WRONG location (hive root) with its own child
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_CHILD1,
            title="Child",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
            children=[TICKET_ID_LINTER_CHILD_SUBTASK],
        )

        # Create grandchild under misplaced child
        write_ticket_file(
            tickets_dir / TICKET_ID_LINTER_CHILD1,
            TICKET_ID_LINTER_CHILD_SUBTASK,
            title="Grandchild",
            type="t2",
            status="open",
            parent=TICKET_ID_LINTER_CHILD1,
        )

        # Verify initial state
        wrong_child_location = tickets_dir / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md"
        wrong_grandchild_location = (
            tickets_dir
            / TICKET_ID_LINTER_CHILD1
            / TICKET_ID_LINTER_CHILD_SUBTASK
            / f"{TICKET_ID_LINTER_CHILD_SUBTASK}.md"
        )
        correct_child_location = tickets_dir / TICKET_ID_ABC / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md"
        correct_grandchild_location = (
            tickets_dir
            / TICKET_ID_ABC
            / TICKET_ID_LINTER_CHILD1
            / TICKET_ID_LINTER_CHILD_SUBTASK
            / f"{TICKET_ID_LINTER_CHILD_SUBTASK}.md"
        )

        assert wrong_child_location.exists()
        assert wrong_grandchild_location.exists()
        assert not correct_child_location.exists()

        # Run linter
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify both child and grandchild were moved together
        assert not wrong_child_location.exists()
        assert not wrong_grandchild_location.exists()
        assert correct_child_location.exists()
        assert correct_grandchild_location.exists()

        # Verify only one move fix (for the parent directory)
        move_fixes = [
            f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_LINTER_CHILD1
        ]
        assert len(move_fixes) == 1

    def test_bee_at_wrong_location_moved_to_hive_root(self, hive_env):
        """Bee (ticket with no parent) moved to hive root if misplaced."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create a bee at wrong location (nested under non-existent directory)
        nested_dir = tickets_dir / "wrong_location"
        nested_dir.mkdir(parents=True, exist_ok=True)
        write_ticket_file(nested_dir, TICKET_ID_ABC, title="Misplaced Bee", status="open")

        # Verify initial state
        wrong_location = nested_dir / TICKET_ID_ABC / f"{TICKET_ID_ABC}.md"
        correct_location = tickets_dir / TICKET_ID_ABC / f"{TICKET_ID_ABC}.md"
        assert wrong_location.exists()
        assert not correct_location.exists()

        # Run linter
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify bee was moved to hive root
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_ABC]
        assert len(move_fixes) == 1
        assert "hive root" in move_fixes[0].description.lower()

        assert not wrong_location.exists()
        assert correct_location.exists()

    def test_bee_already_at_hive_root_no_action(self, hive_env):
        """Bee already at hive root triggers no move action."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create bee at correct location (hive root)
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee at Root", status="open")

        # Run linter
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify no move fixes
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory" and f.ticket_id == TICKET_ID_ABC]
        assert len(move_fixes) == 0

    def test_multiple_misplaced_directories_all_corrected(self, hive_env):
        """Multiple misplaced directories are all corrected in single linter run."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create parent bee
        write_ticket_file(
            tickets_dir,
            TICKET_ID_ABC,
            title="Parent",
            status="open",
            children=[TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD2, TICKET_ID_LINTER_CHILD3],
        )

        # Create 3 children, all at WRONG locations
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_CHILD1, title="Child 1", type="t1", status="open", parent=TICKET_ID_ABC
        )
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_CHILD2, title="Child 2", type="t1", status="open", parent=TICKET_ID_ABC
        )
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_CHILD3, title="Child 3", type="t1", status="open", parent=TICKET_ID_ABC
        )

        # Run linter once
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify all 3 children were moved
        move_fixes = [f for f in report.fixes if f.fix_type == "move_directory"]
        moved_tickets = {f.ticket_id for f in move_fixes}
        assert TICKET_ID_LINTER_CHILD1 in moved_tickets
        assert TICKET_ID_LINTER_CHILD2 in moved_tickets
        assert TICKET_ID_LINTER_CHILD3 in moved_tickets

        # Verify all are now in correct locations
        for child_id in [TICKET_ID_LINTER_CHILD1, TICKET_ID_LINTER_CHILD2, TICKET_ID_LINTER_CHILD3]:
            correct_path = tickets_dir / TICKET_ID_ABC / child_id / f"{child_id}.md"
            assert correct_path.exists()


# ============================================================================
# BIDIRECTIONAL FIELD REPAIR IN HIERARCHICAL CONTEXT
# ============================================================================


class TestBidirectionalRepairHierarchical:
    """Tests for bidirectional relationship repair with hierarchical directory storage."""

    def test_parent_missing_child_in_children_array_auto_fix(self, hive_env):
        """Parent's children array missing a child is reported as auto-fixable."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create parent with EMPTY children array (orphaned child scenario)
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent", status="open", children=[])

        # Create child that correctly lists parent (child references parent but parent doesn't reference child)
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify fix was reported for parent
        add_child_fixes = [f for f in report.fixes if f.fix_type == "add_child"]
        assert len(add_child_fixes) == 1
        assert add_child_fixes[0].ticket_id == TICKET_ID_ABC
        assert TICKET_ID_LINTER_CHILD1 in add_child_fixes[0].description

    def test_asymmetric_policy_parent_lists_child_no_auto_fix(self, hive_env):
        """Parent listing child without backlink → NO auto-fix (asymmetric policy)."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create parent with child in children array
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent", status="open", children=[TICKET_ID_LINTER_CHILD1])

        # Create child WITHOUT parent field (parent references child but child doesn't reference parent)
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC, TICKET_ID_LINTER_CHILD1, title="Child", type="t1", status="open"
        )

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Asymmetric policy: parent→child direction NOT enforced, no "set_parent" fix
        set_parent_fixes = [f for f in report.fixes if f.fix_type == "set_parent"]
        assert len(set_parent_fixes) == 0

        # Also verify no errors for this scenario
        orphaned_parent_errors = report.get_errors(error_type="orphaned_parent")
        assert len(orphaned_parent_errors) == 0

    def test_asymmetric_policy_auto_fix_child_to_parent_only(self, hive_env):
        """Only child→parent direction auto-fixed under asymmetric policy."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create first parent-child pair: child has parent, parent missing child in array (auto-fixable)
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent Bee", status="open", children=[])
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child 1",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        # Create second parent-child pair: parent has child in array, child missing parent field (NOT auto-fixable)
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_PARENT_TASK,
            title="Parent Task",
            type="t1",
            status="open",
            children=[TICKET_ID_LINTER_CHILD2],
        )
        write_ticket_file(
            tickets_dir / TICKET_ID_LINTER_PARENT_TASK,
            TICKET_ID_LINTER_CHILD2,
            title="Child 2",
            type="t1",
            status="open",
        )

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify only child→parent direction was fixed
        add_child_fixes = [f for f in report.fixes if f.fix_type == "add_child"]
        set_parent_fixes = [f for f in report.fixes if f.fix_type == "set_parent"]

        # First pair: parent missing child in array (child→parent enforced, AUTO-FIXED)
        assert any(f.ticket_id == TICKET_ID_ABC for f in add_child_fixes)

        # Second pair: child missing parent field (parent→child NOT enforced, NO FIX)
        assert len(set_parent_fixes) == 0

    def test_dependency_missing_down_dep_auto_fix_hierarchical(self, hive_env):
        """Upstream ticket missing down_dependency is reported as auto-fixable."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create two tasks: downstream has up_dep, upstream missing down_dep
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_DEP_A, title="Upstream", type="t1", status="open", down_dependencies=[]
        )
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_DEP_B,
            title="Downstream",
            type="t1",
            status="open",
            up_dependencies=[TICKET_ID_LINTER_DEP_A],
        )

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify fix was reported for upstream ticket
        add_dep_fixes = [f for f in report.fixes if f.fix_type == "add_down_dependency"]
        assert len(add_dep_fixes) == 1
        assert add_dep_fixes[0].ticket_id == TICKET_ID_LINTER_DEP_A
        assert TICKET_ID_LINTER_DEP_B in add_dep_fixes[0].description

    def test_dependency_missing_up_dep_auto_fix_hierarchical(self, hive_env):
        """Downstream ticket missing up_dependency is reported as auto-fixable."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create two tasks: upstream has down_dep, downstream missing up_dep
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_DEP_A,
            title="Upstream",
            type="t1",
            status="open",
            down_dependencies=[TICKET_ID_LINTER_DEP_B],
        )
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_DEP_B, title="Downstream", type="t1", status="open", up_dependencies=[]
        )

        # Run linter with auto-fix
        linter = Linter(tickets_dir=str(tickets_dir), hive_name=HIVE_BACKEND, auto_fix=True)
        report = linter.run()

        # Verify fix was reported for downstream ticket
        add_dep_fixes = [f for f in report.fixes if f.fix_type == "add_up_dependency"]
        assert len(add_dep_fixes) == 1
        assert add_dep_fixes[0].ticket_id == TICKET_ID_LINTER_DEP_B
        assert TICKET_ID_LINTER_DEP_A in add_dep_fixes[0].description


# ============================================================================
# INTEGRATION TEST: SANITIZE_HIVE
# ============================================================================


class TestEggFieldValidation:
    """Tests for validate_egg_field_presence() functionality."""

    def test_bee_without_egg_field_validation_error(self, hive_env):
        """Bee without egg field in frontmatter triggers validation error and marks corrupt."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create bee ticket file WITHOUT egg field using omit_egg=True
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee Without Egg", omit_egg=True)

        report = Linter(str(tickets_dir), hive_name=hive_name).run()
        egg_errors = report.get_errors(error_type="missing_egg_field")
        assert len(egg_errors) == 1
        assert egg_errors[0].ticket_id == TICKET_ID_ABC
        assert "must have 'egg' field" in egg_errors[0].message
        assert report.is_corrupt()

    def test_bee_with_egg_null_passes(self, hive_env):
        """Bee with egg: null in frontmatter passes validation."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee With Null Egg", egg=None)

        report = Linter(str(tickets_dir), hive_name=hive_name).run()
        egg_errors = report.get_errors(error_type="missing_egg_field")
        assert len(egg_errors) == 0

    def test_bee_with_egg_string_passes(self, hive_env):
        """Bee with egg: "string" in frontmatter passes validation."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee With String Egg", egg="https://example.com/spec.md")

        report = Linter(str(tickets_dir), hive_name=hive_name).run()
        egg_errors = report.get_errors(error_type="missing_egg_field")
        assert len(egg_errors) == 0

    def test_t1_ticket_without_egg_no_error(self, hive_env):
        """t1 ticket without egg field has no validation error (only bees require egg)."""
        repo_root, tickets_dir, hive_name = hive_env

        write_ticket_file(tickets_dir, TICKET_ID_LINTER_TASK_MAIN, title="Task Without Egg", type="t1")

        report = Linter(str(tickets_dir), hive_name=hive_name).run()
        egg_errors = report.get_errors(error_type="missing_egg_field")
        assert len(egg_errors) == 0

    @pytest.mark.asyncio
    async def test_sanitize_hive_with_bee_missing_egg_reports_error(self, hive_env):
        """sanitize_hive detects bee missing egg field and reports error."""
        from src.mcp_hive_ops import _sanitize_hive

        repo_root, tickets_dir, hive_name = hive_env

        # Create bee without egg field using omit_egg=True
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Bee Missing Egg", omit_egg=True)

        # Run sanitize_hive
        result = await _sanitize_hive(hive_name)

        # Verify error was detected (sanitize_hive returns "error" status when corrupt)
        assert result["status"] == "error"
        assert result["is_corrupt"] is True
        assert len(result["errors_remaining"]) > 0

        # Verify missing_egg_field error is in the report
        error_types = [err["error_type"] for err in result["errors_remaining"]]
        assert "missing_egg_field" in error_types


class TestSanitizeHiveIntegration:
    """Integration tests for _sanitize_hive() that trigger multiple fix types."""

    @pytest.mark.asyncio
    async def test_sanitize_hive_reports_multiple_fix_types(self, hive_env):
        """Create error conditions (misplaced dir + missing bidirectional refs), verify both reported."""
        from src.mcp_hive_ops import _sanitize_hive

        repo_root, tickets_dir, hive_name = hive_env

        # Error condition 1: Misplaced child directory (at hive root instead of under parent)
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent", status="open", children=[TICKET_ID_LINTER_CHILD1])
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_CHILD1, title="Child", type="t1", status="open", parent=TICKET_ID_ABC
        )

        # Error condition 2: Orphaned dependency (missing backlink)
        write_ticket_file(
            tickets_dir, TICKET_ID_LINTER_DEP_A, title="Upstream", type="t1", status="open", down_dependencies=[]
        )
        write_ticket_file(
            tickets_dir,
            TICKET_ID_LINTER_DEP_B,
            title="Downstream",
            type="t1",
            status="open",
            up_dependencies=[TICKET_ID_LINTER_DEP_A],
        )

        # Run sanitize_hive
        result = await _sanitize_hive(hive_name)

        # Verify success
        assert result["status"] == "success"
        assert "fixes_applied" in result
        assert len(result["fixes_applied"]) >= 2

        # Verify both types of fixes reported
        fix_types = {fix["fix_type"] for fix in result["fixes_applied"]}
        assert "move_directory" in fix_types
        assert "add_down_dependency" in fix_types

        # Verify directory was moved (this fix actually works since it's not using write_ticket_file)
        correct_child_location = tickets_dir / TICKET_ID_ABC / TICKET_ID_LINTER_CHILD1 / f"{TICKET_ID_LINTER_CHILD1}.md"
        assert correct_child_location.exists()

    @pytest.mark.asyncio
    async def test_sanitize_hive_no_errors_no_fixes(self, hive_env):
        """Clean hive with no errors results in no fixes applied."""
        from src.mcp_hive_ops import _sanitize_hive

        repo_root, tickets_dir, hive_name = hive_env

        # Create properly structured tickets
        write_ticket_file(tickets_dir, TICKET_ID_ABC, title="Parent", status="open", children=[TICKET_ID_LINTER_CHILD1])
        write_ticket_file(
            tickets_dir / TICKET_ID_ABC,
            TICKET_ID_LINTER_CHILD1,
            title="Child",
            type="t1",
            status="open",
            parent=TICKET_ID_ABC,
        )

        # Run sanitize_hive
        result = await _sanitize_hive(hive_name)

        # Verify success with no fixes
        assert result["status"] == "success"
        assert len(result["fixes_applied"]) == 0
        assert result["is_corrupt"] is False


def setup_multi_hive_config(tmp_path, hive_configs):
    """Helper to set up multiple hives with per-hive child_tiers.

    Args:
        tmp_path: Test tmp_path fixture
        hive_configs: Dict of {hive_name: {"child_tiers": {...}, "display_name": str (optional)}}

    Returns:
        Tuple of (hive_paths dict, BeesConfig object)
    """
    from src.config import BeesConfig, ChildTierConfig, HiveConfig

    hive_paths = {}
    hives_config = {}

    for hive_name, hive_spec in hive_configs.items():
        # Create hive directory
        hive_path = tmp_path / hive_name
        hive_path.mkdir()
        hive_paths[hive_name] = hive_path

        # Create .hive identity marker
        hive_identity_dir = hive_path / ".hive"
        hive_identity_dir.mkdir()
        identity_data = {
            "normalized_name": hive_name,
            "display_name": hive_spec.get("display_name", hive_name.title()),
            "created_at": "2026-02-05T00:00:00",
        }
        (hive_identity_dir / "identity.json").write_text(json.dumps(identity_data, indent=2))

        # Parse child_tiers from list format to ChildTierConfig objects
        child_tiers_data = hive_spec.get("child_tiers")
        child_tiers = None
        if child_tiers_data is not None:
            if isinstance(child_tiers_data, dict):
                child_tiers = {}
                for tier_id, names in child_tiers_data.items():
                    if isinstance(names, list):
                        child_tiers[tier_id] = ChildTierConfig(singular=names[0], plural=names[1])
                    else:
                        child_tiers[tier_id] = ChildTierConfig(singular=names, plural=names)

        hives_config[hive_name] = HiveConfig(
            path=str(hive_path),
            display_name=hive_spec.get("display_name", hive_name.title()),
            created_at="2026-02-05T00:00:00",
            child_tiers=child_tiers,
        )

    # Create BeesConfig with global child_tiers if provided
    global_child_tiers = hive_configs.get("__global_child_tiers__")
    global_child_tiers_parsed = None
    if global_child_tiers is not None:
        global_child_tiers_parsed = {}
        for tier_id, names in global_child_tiers.items():
            if isinstance(names, list):
                global_child_tiers_parsed[tier_id] = ChildTierConfig(singular=names[0], plural=names[1])

    config = BeesConfig(hives=hives_config, child_tiers=global_child_tiers_parsed)

    return hive_paths, config


class TestPerHiveLinterValidation:
    """Tests for per-hive child_tiers resolution in linter validation methods."""

    def test_validate_tier_exists_uses_hive_child_tiers(self, tmp_path, monkeypatch):
        """validate_tier_exists should use hive-level child_tiers, not global."""
        monkeypatch.chdir(tmp_path)

        # Set up two hives with different child_tiers
        # hive1: 2-tier (t1 only), hive2: 3-tier (t1, t2)
        hive_paths, config = setup_multi_hive_config(
            tmp_path,
            {
                "hive1": {"child_tiers": {"t1": ["Task", "Tasks"]}},
                "hive2": {
                    "child_tiers": {
                        "t1": ["Task", "Tasks"],
                        "t2": ["Subtask", "Subtasks"],
                    }
                },
            },
        )

        # Create tickets: hive1 has t2 ticket (invalid for hive1), hive2 has t2 ticket (valid for hive2)
        write_ticket_file(hive_paths["hive1"], "b.abc", title="Hive1 Bee")
        write_ticket_file(hive_paths["hive1"] / "b.abc", "t2.xyz.ab.cd", title="Invalid T2", type="t2", parent="b.abc")

        write_ticket_file(hive_paths["hive2"], "b.def", title="Hive2 Bee")
        write_ticket_file(hive_paths["hive2"] / "b.def", "t1.ghi.ab", title="Valid T1", type="t1", parent="b.def")
        write_ticket_file(
            hive_paths["hive2"] / "b.def" / "t1.ghi.ab", "t2.jkm.ab.cd", title="Valid T2", type="t2", parent="t1.ghi.ab"
        )

        # Mock load_bees_config to return our custom config
        with patch("src.config.load_bees_config", return_value=config):
            # Run linter on hive1
            report_hive1 = Linter(str(hive_paths["hive1"]), hive_name="hive1").run()
            # Run linter on hive2
            report_hive2 = Linter(str(hive_paths["hive2"]), hive_name="hive2").run()

        # hive1 should have error for t2.xyz.ab.cd (unknown_tier error)
        hive1_tier_errors = report_hive1.get_errors(error_type="unknown_tier")
        assert len(hive1_tier_errors) == 1
        assert hive1_tier_errors[0].ticket_id == "t2.xyz.ab.cd"
        assert "t2" in hive1_tier_errors[0].message

        # hive2 should have no tier errors
        hive2_tier_errors = report_hive2.get_errors(error_type="unknown_tier")
        assert len(hive2_tier_errors) == 0

    def test_validate_tier_hierarchy_uses_hive_child_tiers(self, tmp_path, monkeypatch):
        """validate_parent_children_bidirectional tier hierarchy should use hive-level child_tiers."""
        monkeypatch.chdir(tmp_path)

        # Set up two hives with different tier hierarchies
        # hive1: 2-tier (t1 only), hive2: 3-tier (t1, t2)
        hive_paths, config = setup_multi_hive_config(
            tmp_path,
            {
                "hive1": {"child_tiers": {"t1": ["Task", "Tasks"]}},
                "hive2": {
                    "child_tiers": {
                        "t1": ["Task", "Tasks"],
                        "t2": ["Subtask", "Subtasks"],
                    }
                },
            },
        )

        # hive1: Create t1 with t1 parent (invalid - t1 should have bee parent)
        write_ticket_file(hive_paths["hive1"], "b.abc", title="Hive1 Bee", children=["t1.xyz.ab"])
        write_ticket_file(
            hive_paths["hive1"] / "b.abc", "t1.xyz.ab", title="T1 Parent", type="t1", parent="b.abc", children=["t1.def.ab"]
        )
        # Invalid: t1.def.ab has t1.xyz.ab as parent (should be bee)
        write_ticket_file(
            hive_paths["hive1"] / "b.abc" / "t1.xyz.ab", "t1.def.ab", title="T1 Child", type="t1", parent="t1.xyz.ab"
        )

        # hive2: Create valid hierarchy (bee -> t1 -> t2)
        write_ticket_file(hive_paths["hive2"], "b.ghi", title="Hive2 Bee", children=["t1.jkm.ab"])
        write_ticket_file(
            hive_paths["hive2"] / "b.ghi", "t1.jkm.ab", title="T1", type="t1", parent="b.ghi", children=["t2.mno.ab.cd"]
        )
        write_ticket_file(hive_paths["hive2"] / "b.ghi" / "t1.jkm.ab", "t2.mno.ab.cd", title="T2", type="t2", parent="t1.jkm.ab")

        # Mock load_bees_config to return our custom config
        with patch("src.config.load_bees_config", return_value=config):
            # Run linter on hive1
            report_hive1 = Linter(str(hive_paths["hive1"]), hive_name="hive1").run()
            # Run linter on hive2
            report_hive2 = Linter(str(hive_paths["hive2"]), hive_name="hive2").run()

        # hive1 should have error for t1.def.ab (invalid_tier_parent error - t1 should have bee parent, not t1)
        hive1_tier_errors = report_hive1.get_errors(error_type="invalid_tier_parent")
        assert len(hive1_tier_errors) == 1
        assert hive1_tier_errors[0].ticket_id == "t1.def.ab"
        assert "expected bee" in hive1_tier_errors[0].message

        # hive2 should have no tier hierarchy errors
        hive2_tier_errors = report_hive2.get_errors(error_type="invalid_tier_parent")
        assert len(hive2_tier_errors) == 0

    def test_bees_only_hive_rejects_child_tiers(self, tmp_path, monkeypatch):
        """Hive configured as bees-only (empty child_tiers) should reject all child tier tickets."""
        monkeypatch.chdir(tmp_path)

        # Set up bees-only hive with global config having t1
        hive_paths, config = setup_multi_hive_config(
            tmp_path,
            {
                "hive_bees_only": {"child_tiers": {}, "display_name": "Bees Only"},
                "__global_child_tiers__": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create bee (valid) and t1 ticket (invalid for bees-only hive)
        write_ticket_file(hive_paths["hive_bees_only"], "b.abc", title="Valid Bee")
        write_ticket_file(
            hive_paths["hive_bees_only"] / "b.abc", "t1.xyz.ab", title="Invalid T1", type="t1", parent="b.abc"
        )

        # Mock load_bees_config to return our custom config
        with patch("src.config.load_bees_config", return_value=config):
            report = Linter(str(hive_paths["hive_bees_only"]), hive_name="hive_bees_only").run()

        # Should have error for t1.xyz.ab (unknown_tier)
        tier_errors = report.get_errors(error_type="unknown_tier")
        assert len(tier_errors) == 1
        assert tier_errors[0].ticket_id == "t1.xyz.ab"
        assert "not defined in child_tiers" in tier_errors[0].message

    def test_hive_without_child_tiers_falls_back_to_global(self, tmp_path, monkeypatch):
        """Hive without child_tiers should fall back to global config."""
        monkeypatch.chdir(tmp_path)

        # Set up hive without child_tiers (None) and global config with t1
        hive_paths, config = setup_multi_hive_config(
            tmp_path,
            {
                "hive_fallback": {"child_tiers": None},
                "__global_child_tiers__": {"t1": ["Task", "Tasks"]},
            },
        )

        # Create tickets: bee and t1 (should be valid via global fallback)
        write_ticket_file(hive_paths["hive_fallback"], "b.abc", title="Fallback Bee")
        write_ticket_file(
            hive_paths["hive_fallback"] / "b.abc", "t1.xyz.ab", title="Fallback T1", type="t1", parent="b.abc"
        )

        # Mock load_bees_config to return our custom config
        with patch("src.config.load_bees_config", return_value=config):
            report = Linter(str(hive_paths["hive_fallback"]), hive_name="hive_fallback").run()

        # Should have no tier errors (t1 is valid via global fallback)
        tier_errors = report.get_errors(error_type="unknown_tier")
        assert len(tier_errors) == 0


# ============================================================================
# STATUS AND EGG FIELD VALIDATION
# ============================================================================


class TestStatusFieldValidation:
    """Tests for validate_status_field() functionality."""

    def test_status_invalid_type_integer(self, tmp_path):
        """Status with integer value triggers invalid_field_type error."""

        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket manually with integer status
        content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
status: 123
egg: null
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "status" in errors[0].message.lower()
        assert "must be string" in errors[0].message

    def test_status_freeform_no_config(self, tmp_path):
        """Status with any string value passes when no config is provided."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", status="open")

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_status", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 0

    def test_status_valid_with_config(self, tmp_path):
        """Status with value in configured status_values passes validation."""
        from src.config import BeesConfig, HiveConfig

        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", status="open")

        config = BeesConfig(
            hives={
                "default": HiveConfig(
                    path=str(tmp_path),
                    display_name="Default",
                    created_at="2026-02-05T00:00:00",
                    status_values=["open", "closed"],
                )
            },
            child_tiers={},
            status_values=["open", "closed"],
        )

        report = Linter(str(tmp_path), hive_name="default", config=config).run()
        errors = report.get_errors(error_type="invalid_status", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 0

    def test_status_invalid_with_config(self, tmp_path):
        """Status with value NOT in configured status_values triggers invalid_status error."""
        from src.config import BeesConfig, HiveConfig

        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", status="bad_value")

        config = BeesConfig(
            hives={
                "default": HiveConfig(
                    path=str(tmp_path),
                    display_name="Default",
                    created_at="2026-02-05T00:00:00",
                    status_values=["open", "closed"],
                )
            },
            child_tiers={},
            status_values=["open", "closed"],
        )

        report = Linter(str(tmp_path), hive_name="default", config=config).run()
        errors = report.get_errors(error_type="invalid_status", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "bad_value" in errors[0].message
        assert "not in configured status_values" in errors[0].message

    def test_status_none_no_errors(self, tmp_path):
        """Status with None value (missing) does not trigger errors."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        # Pass status=None explicitly to test None handling
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", status=None)

        report = Linter(str(tmp_path)).run()
        status_errors = report.get_errors(ticket_id=TICKET_ID_ABC)
        # Filter for status-related errors only (invalid_field_type, invalid_status)
        status_related = [
            e for e in status_errors if e.error_type in ["invalid_field_type", "invalid_status"] and "status" in e.message.lower()
        ]
        assert len(status_related) == 0


class TestEggJsonSerializableValidation:
    """Tests for validate_egg_json_serializable() functionality."""

    def test_egg_null_passes(self, tmp_path):
        """Bee ticket with egg=None passes validation."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", egg=None)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        egg_errors = [e for e in errors if "egg" in e.message.lower()]
        assert len(egg_errors) == 0

    def test_egg_string_passes(self, tmp_path):
        """Bee ticket with string egg passes validation."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        write_ticket_file(bees_dir, TICKET_ID_ABC, title="Test", egg="https://example.com/spec.md")

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        egg_errors = [e for e in errors if "egg" in e.message.lower()]
        assert len(egg_errors) == 0

    def test_egg_integer_passes(self, tmp_path):
        """Bee ticket with integer egg passes validation."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket with integer egg
        content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
egg: 42
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        egg_errors = [e for e in errors if "egg" in e.message.lower()]
        assert len(egg_errors) == 0

    def test_egg_dict_passes(self, tmp_path):
        """Bee ticket with dict egg passes validation."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket with dict egg
        content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
egg:
  key: value
  nested:
    data: test
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        egg_errors = [e for e in errors if "egg" in e.message.lower()]
        assert len(egg_errors) == 0

    def test_egg_list_passes(self, tmp_path):
        """Bee ticket with list egg passes validation."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"

        # Write ticket with list egg
        content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
egg:
  - 1
  - 2
  - 3
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="invalid_field_type", ticket_id=TICKET_ID_ABC)
        egg_errors = [e for e in errors if "egg" in e.message.lower()]
        assert len(egg_errors) == 0

    def test_egg_non_serializable_direct_call(self, tmp_path):
        """Non-serializable egg triggers error when tested directly."""
        from src.models import Ticket

        # Create a non-serializable object (e.g., a set or custom class)
        class NonSerializable:
            pass

        ticket = Ticket(id=TICKET_ID_ABC, type="bee", title="Test", egg=NonSerializable())
        linter = Linter(str(tmp_path))
        report = LinterReport()

        linter.validate_egg_json_serializable(ticket, report)

        errors = report.get_errors(error_type="invalid_field_type")
        assert len(errors) == 1
        assert "egg field must be JSON-serializable" in errors[0].message

    def test_egg_validation_only_for_bee_tickets(self, tmp_path):
        """Egg validation only applies to bee tickets, not t1/t2 tickets."""
        from src.models import Ticket

        # Create a t1 ticket with non-serializable egg (should be ignored)
        class NonSerializable:
            pass

        ticket = Ticket(id=TICKET_ID_LINTER_TASK_MAIN, type="t1", title="Test", egg=NonSerializable())
        linter = Linter(str(tmp_path))
        report = LinterReport()

        linter.validate_egg_json_serializable(ticket, report)

        # No errors should be added for non-bee tickets
        errors = report.get_errors(error_type="invalid_field_type")
        assert len(errors) == 0


class TestDisallowedFieldsDetection:
    """Tests for validate_disallowed_fields() functionality."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "owner",
            "priority",
            "description",
            "created_by",
            "updated_at",
            "bees_version",
            "ticket_status",
        ],
    )
    def test_single_disallowed_field(self, tmp_path, field_name):
        """Each disallowed field generates 'disallowed_field' error."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Test", **{field_name: "some_value"})

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert field_name in errors[0].message

    def test_multiple_disallowed_fields(self, tmp_path):
        """Multiple disallowed fields generate separate errors."""
        write_ticket_file(
            tmp_path,
            TICKET_ID_ABC,
            title="Test",
            owner="test_user",
            priority="high",
            created_by="admin",
        )

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 3
        error_messages = " ".join(e.message for e in errors)
        assert "owner" in error_messages
        assert "priority" in error_messages
        assert "created_by" in error_messages

    def test_allowed_fields_pass(self, tmp_path):
        """Normal ticket with only allowed fields generates no errors."""
        write_ticket_file(
            tmp_path,
            TICKET_ID_ABC,
            title="Test",
            status="open",
            tags=["bug", "urgent"],
        )

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 0

    def test_disallowed_field_with_null_value(self, tmp_path):
        """Disallowed field with null value still triggers error (field presence matters)."""
        write_ticket_file(tmp_path, TICKET_ID_ABC, title="Test", owner=None)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "owner" in errors[0].message

    def test_disallowed_field_with_integer_value(self, tmp_path):
        """Disallowed field with integer value triggers error."""
        bees_dir = tmp_path / "bees"
        bees_dir.mkdir()

        # Create ticket file manually with integer priority to ensure proper YAML
        ticket_dir = bees_dir / TICKET_ID_ABC
        ticket_dir.mkdir()
        ticket_file = ticket_dir / f"{TICKET_ID_ABC}.md"
        content = """---
id: b.abc
schema_version: '0.1'
title: Test
type: bee
status: open
egg: null
priority: 5
---

Test body."""
        ticket_file.write_text(content)

        report = Linter(str(tmp_path)).run()
        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert "priority" in errors[0].message


class TestDisallowedFieldsUnit:
    """Unit tests for validate_disallowed_fields using constructed Ticket objects (no disk)."""

    def _run_disallowed_check(self, tickets):
        """Create linter/report, run validate_disallowed_fields, return report."""
        linter = Linter("/nonexistent")
        report = LinterReport()
        linter.validate_disallowed_fields(tickets, report)
        return report

    @pytest.mark.parametrize(
        "disallowed_key",
        ["owner", "priority", "description", "created_by", "updated_at", "bees_version"],
    )
    def test_detects_disallowed_key_via_raw_keys(self, disallowed_key):
        """Each disallowed key in _raw_keys triggers an error without disk access."""
        ticket = make_ticket(id=TICKET_ID_ABC)
        ticket._raw_keys = frozenset({"id", "type", "title", disallowed_key})

        report = self._run_disallowed_check([ticket])

        errors = report.get_errors(error_type="disallowed_field", ticket_id=TICKET_ID_ABC)
        assert len(errors) == 1
        assert disallowed_key in errors[0].message

    def test_no_error_when_raw_keys_clean(self):
        """Ticket with only allowed keys in _raw_keys produces no disallowed_field errors."""
        ticket = make_ticket(id=TICKET_ID_ABC)
        ticket._raw_keys = frozenset({"id", "type", "title", "status", "tags", "schema_version"})

        report = self._run_disallowed_check([ticket])

        assert len(report.get_errors(error_type="disallowed_field")) == 0

    def test_description_not_flagged_for_normal_ticket(self):
        # description is in DISALLOWED_FIELDS but should not fire when absent from _raw_keys
        """Normal ticket (description from body, not frontmatter) has no false positive."""
        ticket = make_ticket(id=TICKET_ID_ABC)
        ticket._raw_keys = frozenset({"id", "type", "title", "schema_version", "status"})

        report = self._run_disallowed_check([ticket])

        assert len(report.get_errors(error_type="disallowed_field")) == 0

    def test_empty_raw_keys_no_errors(self):
        """Ticket with empty _raw_keys (default) produces no errors."""
        ticket = make_ticket(id=TICKET_ID_ABC)

        report = self._run_disallowed_check([ticket])

        assert len(report.get_errors(error_type="disallowed_field")) == 0


class TestEggFieldPresenceUnit:
    """Unit tests for validate_egg_field_presence using constructed Ticket objects (no disk)."""

    def _run_egg_check(self, ticket):
        """Create linter/report, run validate_egg_field_presence, return report."""
        linter = Linter("/nonexistent")
        report = LinterReport()
        linter.validate_egg_field_presence(ticket, report)
        return report

    def test_bee_missing_egg_in_raw_keys_reports_error(self):
        """Bee with _raw_keys not containing 'egg' triggers missing_egg_field error."""
        ticket = make_ticket(id=TICKET_ID_ABC, type="bee")
        ticket._raw_keys = frozenset({"id", "type", "title", "status"})

        report = self._run_egg_check(ticket)

        errors = report.get_errors(error_type="missing_egg_field")
        assert len(errors) == 1
        assert TICKET_ID_ABC in errors[0].message

    @pytest.mark.parametrize("egg_value", [None, "https://example.com"], ids=["null_value", "with_value"])
    def test_bee_egg_present_no_error(self, egg_value):
        """Bee with 'egg' in _raw_keys (null or valued) passes validation."""
        ticket = make_ticket(id=TICKET_ID_ABC, type="bee", egg=egg_value)
        ticket._raw_keys = frozenset({"id", "type", "title", "status", "egg"})

        report = self._run_egg_check(ticket)

        assert len(report.get_errors(error_type="missing_egg_field")) == 0

    @pytest.mark.parametrize("ticket_type", ["t1", "t2"], ids=["t1_skipped", "t2_skipped"])
    def test_non_bee_skipped_regardless_of_raw_keys(self, ticket_type):
        """Non-bee tickets are skipped entirely, even without 'egg' in _raw_keys."""
        ticket = make_ticket(id=TICKET_ID_XYZ, type=ticket_type, parent=TICKET_ID_ABC)
        ticket._raw_keys = frozenset({"id", "type", "title", "status"})

        report = self._run_egg_check(ticket)

        assert len(report.get_errors(error_type="missing_egg_field")) == 0

    def test_no_raw_keys_attr_reports_error(self):
        """Ticket without _raw_keys attr falls back to empty frozenset → missing_egg_field."""
        ticket = make_ticket(id=TICKET_ID_ABC, type="bee")
        # Explicitly remove _raw_keys if make_ticket sets one
        if hasattr(ticket, "_raw_keys"):
            delattr(ticket, "_raw_keys")

        report = self._run_egg_check(ticket)

        errors = report.get_errors(error_type="missing_egg_field")
        assert len(errors) == 1


class TestGuidValidation:
    """Unit tests for validate_guid() using constructed Ticket objects (no disk)."""

    def _run_guid_check(self, ticket):
        """Create linter/report, run validate_guid, return report."""
        linter = Linter("/nonexistent")
        report = LinterReport()
        linter.validate_guid(ticket, report)
        return report

    def test_missing_guid_reports_error(self):
        """Ticket with guid=None triggers missing_guid error."""
        ticket = make_ticket(id=TICKET_ID_ABC, guid=None)
        report = self._run_guid_check(ticket)
        errors = report.get_errors(error_type="missing_guid")
        assert len(errors) == 1
        assert TICKET_ID_ABC in errors[0].message

    @pytest.mark.parametrize(
        "bad_guid",
        [
            pytest.param("short", id="too_short"),
            pytest.param("a" * 40, id="too_long"),
            pytest.param("", id="empty"),
        ],
    )
    def test_invalid_guid_length_reports_error(self, bad_guid):
        """Ticket with guid of wrong length triggers invalid_guid_length error."""
        ticket = make_ticket(id=TICKET_ID_ABC, guid=bad_guid)
        report = self._run_guid_check(ticket)
        errors = report.get_errors(error_type="invalid_guid_length")
        assert len(errors) == 1

    @pytest.mark.parametrize(
        "bad_char",
        [
            pytest.param("0", id="zero"),
            pytest.param("O", id="uppercase_O"),
            pytest.param("I", id="uppercase_I"),
            pytest.param("l", id="lowercase_l"),
        ],
    )
    def test_invalid_guid_charset_reports_error(self, bad_char):
        """Ticket with guid containing excluded char triggers invalid_guid_charset error."""
        # Build a 32-char GUID with the bad char injected at position 3 (after short_id)
        guid = "abc" + bad_char + "a" * 28
        ticket = make_ticket(id=TICKET_ID_ABC, guid=guid)
        report = self._run_guid_check(ticket)
        errors = report.get_errors(error_type="invalid_guid_charset")
        assert len(errors) == 1

    def test_invalid_guid_prefix_reports_error(self):
        """Ticket with guid not starting with short_id triggers invalid_guid_prefix error."""
        # TICKET_ID_ABC = "b.abc", so short_id = "abc" — use "xyz" prefix instead
        guid = "xyz" + "a" * 29
        ticket = make_ticket(id=TICKET_ID_ABC, guid=guid)
        report = self._run_guid_check(ticket)
        errors = report.get_errors(error_type="invalid_guid_prefix")
        assert len(errors) == 1

    def test_valid_guid_no_errors(self):
        """Ticket with correctly formed guid produces no GUID-related errors."""
        ticket = make_ticket(id=TICKET_ID_ABC)  # auto-generates valid guid
        report = self._run_guid_check(ticket)
        guid_error_types = {"missing_guid", "invalid_guid_length", "invalid_guid_charset", "invalid_guid_prefix"}
        guid_errors = [e for e in report.errors if e.error_type in guid_error_types]
        assert len(guid_errors) == 0

    def test_missing_guid_autofix(self, hive_env):
        """auto_fix=True generates and saves a valid guid when guid is None."""
        from src.reader import read_ticket

        repo_root, hive_dir, hive_name = hive_env

        # Write a bee ticket with guid=null to disk
        ticket_file = write_ticket_file(hive_dir, TICKET_ID_ABC, title="Autofix Bee", guid=None)

        # Read the ticket back from disk (guid should be None)
        ticket = read_ticket(TICKET_ID_ABC, file_path=ticket_file)
        assert ticket.guid is None

        linter = Linter(tickets_dir=str(hive_dir), hive_name=hive_name, auto_fix=True)
        report = LinterReport()
        linter.validate_guid(ticket, report)

        # No missing_guid error — auto-fix suppresses it
        assert report.get_errors(error_type="missing_guid") == []

        # Exactly one add_guid fix recorded
        add_guid_fixes = [f for f in report.fixes if f.fix_type == "add_guid"]
        assert len(add_guid_fixes) == 1

        # Ticket object was updated in-memory
        assert ticket.guid is not None
        assert isinstance(ticket.guid, str)

        # GUID starts with the ticket's short_id ("abc" for "b.abc")
        short_id = TICKET_ID_ABC.split(".", 1)[1]
        assert ticket.guid.startswith(short_id)

        # Guid was persisted to disk — re-read the file and verify
        persisted = read_ticket(TICKET_ID_ABC, file_path=ticket_file)
        assert persisted.guid == ticket.guid

    def test_missing_guid_autofix_preserves_all_fields(self, hive_env):
        """auto_fix=True preserves created_at and egg when writing guid fix."""
        from src.reader import read_ticket

        repo_root, hive_dir, hive_name = hive_env

        ticket_file = write_ticket_file(
            hive_dir, TICKET_ID_ABC, title="Preserve Fields Bee", guid=None,
            created_at="2025-06-01T12:00:00+00:00", egg="b.XYZ",
        )

        ticket = read_ticket(TICKET_ID_ABC, file_path=ticket_file)
        assert ticket.guid is None

        linter = Linter(tickets_dir=str(hive_dir), hive_name=hive_name, auto_fix=True)
        report = LinterReport()
        linter.validate_guid(ticket, report)

        persisted = read_ticket(TICKET_ID_ABC, file_path=ticket_file)
        assert persisted.created_at == ticket.created_at
        assert persisted.egg == "b.XYZ"


# ============================================================================
# CROSS-SCOPE MAP BUILDING AND HIVE LOAD FAILURE HANDLING
# ============================================================================


class TestSanitizeHiveCrossScopeMap:
    """Integration tests for _sanitize_hive() cross-scope map building and hive load failure handling."""

    @pytest.mark.asyncio
    async def test_sanitize_hive_multi_hive_no_load_failure(self, isolated_bees_env):
        """sanitize_hive on valid multi-hive setup reports no hive_load_failure errors."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        frontend_dir = helper.create_hive("frontend")
        helper.write_config(child_tiers={})

        helper.create_ticket(backend_dir, TICKET_ID_ABC, "bee", "Backend Bee")
        helper.create_ticket(frontend_dir, TICKET_ID_XYZ, "bee", "Frontend Bee")

        result = await _sanitize_hive("backend")

        assert result["status"] == "success"
        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "hive_load_failure" not in error_types

    @pytest.mark.asyncio
    async def test_sanitize_hive_hive_load_failure_with_other_errors(self, isolated_bees_env):
        """sanitize_hive reports hive_load_failure for missing hive dir; valid hive errors still appear."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        # Register ghost hive in config without creating its directory
        helper.hives["ghost"] = {"path": str(helper.base_path / "ghost"), "display_name": "Ghost"}
        helper.write_config(child_tiers={})

        # Bee missing egg field → unfixable missing_egg_field error from backend
        write_ticket_file(backend_dir, TICKET_ID_ABC, title="Missing Egg Bee", omit_egg=True)

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "hive_load_failure" in error_types
        # Errors from the valid hive's tickets still appear alongside the load failure
        assert any(et != "hive_load_failure" for et in error_types)


# ============================================================================
# DANGLING REFERENCE DETECTION
# ============================================================================


class TestDanglingReferenceDetection:
    """Tests for dangling_dependency and dangling_parent detection via _sanitize_hive."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "field,dangling_id",
        [
            pytest.param("up_dependencies", DANGLING_BEE_ID, id="up_dep_dangling_bee"),
            pytest.param("down_dependencies", "t1.zzz.ab", id="down_dep_dangling_t1"),
        ],
    )
    async def test_dangling_dependency_detected(self, isolated_bees_env, field, dangling_id):
        """Ticket referencing a non-existent ticket ID in a dep field → dangling_dependency error."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={})

        write_ticket_file(backend_dir, TICKET_ID_ABC, title="Bee With Dangling Dep", **{field: [dangling_id]})

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_dependency" in error_types

    @pytest.mark.asyncio
    async def test_dangling_parent_detected(self, isolated_bees_env):
        """t1 ticket with parent pointing to a non-existent bee → dangling_parent error."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        write_ticket_file(
            backend_dir, TICKET_ID_LINTER_TASK_MAIN, title="Task With Dangling Parent",
            type="t1", parent=DANGLING_BEE_ID,
        )

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_parent" in error_types

    @pytest.mark.asyncio
    async def test_cross_hive_dependency_no_dangling(self, isolated_bees_env):
        """Ticket in hive A depending on ticket in hive B (same scope) → no dangling_dependency."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        frontend_dir = helper.create_hive("frontend")
        helper.write_config(child_tiers={})

        # Target ticket exists in frontend hive
        write_ticket_file(frontend_dir, TICKET_ID_XYZ, title="Frontend Bee")
        # Backend bee depends on the frontend bee
        write_ticket_file(backend_dir, TICKET_ID_ABC, title="Backend Bee", up_dependencies=[TICKET_ID_XYZ])

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_dependency" not in error_types


# ============================================================================
# AUTO-FIX DANGLING REFS
# ============================================================================


class TestAutoFixDanglingRefs:
    """Tests for auto_fix_dangling_refs global config flag via _sanitize_hive."""

    @pytest.mark.asyncio
    async def test_auto_fix_disabled_keeps_dangling_dep_error(self, isolated_bees_env):
        """auto_fix_dangling_refs absent → dangling_dependency error retained; ticket file unchanged."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={})

        ticket_path = write_ticket_file(
            backend_dir, TICKET_ID_ABC, title="Bee With Dangling Dep",
            up_dependencies=[DANGLING_BEE_ID],
        )
        original_content = ticket_path.read_text()

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_dependency" in error_types
        assert ticket_path.read_text() == original_content

    @pytest.mark.asyncio
    async def test_auto_fix_enabled_removes_dangling_dep(self, isolated_bees_env):
        """auto_fix_dangling_refs: true → no dangling_dependency error; fix applied; ticket cleaned."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={})

        config_path = helper.global_bees_dir / "config.json"
        config_data = json.loads(config_path.read_text())
        config_data["auto_fix_dangling_refs"] = True
        config_path.write_text(json.dumps(config_data))

        ticket_path = write_ticket_file(
            backend_dir, TICKET_ID_ABC, title="Bee With Dangling Dep",
            up_dependencies=[DANGLING_BEE_ID],
        )

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_dependency" not in error_types
        fix_types = [f["fix_type"] for f in result["fixes_applied"]]
        assert "remove_dangling_dependency" in fix_types
        assert DANGLING_BEE_ID not in ticket_path.read_text()

    @pytest.mark.asyncio
    async def test_auto_fix_enabled_clears_dangling_parent(self, isolated_bees_env):
        """auto_fix_dangling_refs: true + dangling parent → clear_dangling_parent fix; parent cleared."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")
        helper.write_config(child_tiers={"t1": ["Task", "Tasks"]})

        config_path = helper.global_bees_dir / "config.json"
        config_data = json.loads(config_path.read_text())
        config_data["auto_fix_dangling_refs"] = True
        config_path.write_text(json.dumps(config_data))

        ticket_path = write_ticket_file(
            backend_dir, TICKET_ID_LINTER_TASK_MAIN, title="Task With Dangling Parent",
            type="t1", parent=DANGLING_BEE_ID,
        )

        result = await _sanitize_hive("backend")

        fix_types = [f["fix_type"] for f in result["fixes_applied"]]
        assert "clear_dangling_parent" in fix_types
        assert DANGLING_BEE_ID not in ticket_path.read_text()

    @pytest.mark.asyncio
    async def test_auto_fix_hive_level_only_no_fix(self, isolated_bees_env):
        """auto_fix_dangling_refs at hive level only → no auto-fix; global-level key is required."""
        from src.mcp_hive_ops import _sanitize_hive

        helper = isolated_bees_env
        backend_dir = helper.create_hive("backend")

        # Write config with auto_fix_dangling_refs only inside hive entry, not at global level
        scope_data = {
            "hives": {
                "backend": {
                    "path": str(backend_dir),
                    "display_name": "Backend",
                    "auto_fix_dangling_refs": True,
                }
            },
            "child_tiers": {},
        }
        global_config = {
            "scopes": {str(helper.base_path): scope_data},
            "schema_version": "2.0",
        }
        (helper.global_bees_dir / "config.json").write_text(json.dumps(global_config))

        write_ticket_file(
            backend_dir, TICKET_ID_ABC, title="Bee With Dangling Dep",
            up_dependencies=[DANGLING_BEE_ID],
        )

        result = await _sanitize_hive("backend")

        error_types = [e["error_type"] for e in result["errors_remaining"]]
        assert "dangling_dependency" in error_types


# ============================================================================
# DETECT EMPTY TICKET DIRS
# ============================================================================


class TestDetectEmptyTicketDirs:
    """Tests for detect_empty_ticket_dirs() — orphaned ticket directories with no .md file."""

    @pytest.mark.parametrize(
        "dir_name",
        [
            pytest.param("b.abc", id="bee_dir"),
            pytest.param("t1.abc.de", id="t1_dir"),
        ],
    )
    def test_empty_ticket_dir_older_than_10min_reported(self, hive_env, dir_name):
        """Empty ticket-ID-named dir older than 10 minutes is reported as empty_ticket_dir."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / dir_name
        dir_path.mkdir()
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(dir_path, (old_time, old_time))

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=False)
        report = linter.run()

        errors = report.get_errors(error_type="empty_ticket_dir")
        assert any(e.ticket_id == dir_name for e in errors)

    def test_empty_ticket_dir_older_than_10min_removed_in_autofix(self, hive_env):
        """Empty ticket-ID-named dir older than 10 minutes is removed in auto_fix mode."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / "b.abc"
        dir_path.mkdir()
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(dir_path, (old_time, old_time))

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=True)
        report = linter.run()

        assert not dir_path.exists()
        fix_types = [f.fix_type for f in report.fixes]
        assert "remove_empty_dir" in fix_types

    def test_empty_ticket_dir_younger_than_10min_skipped(self, hive_env):
        """Empty ticket-ID-named dir created recently is skipped (in-flight creation)."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / "b.abc"
        dir_path.mkdir()
        # Default mtime is just now — no utime call needed

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=False)
        report = linter.run()

        errors = report.get_errors(error_type="empty_ticket_dir")
        assert not any(e.ticket_id == "b.abc" for e in errors)

    def test_dir_with_md_file_not_flagged(self, hive_env):
        """Ticket-ID-named dir containing a .md file is not flagged as empty."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / "b.abc"
        dir_path.mkdir()
        (dir_path / "b.abc.md").write_text("---\nid: b.abc\n---\n")
        old_time = time.time() - 1200
        os.utime(dir_path, (old_time, old_time))

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=False)
        report = linter.run()

        errors = report.get_errors(error_type="empty_ticket_dir")
        assert not any(e.ticket_id == "b.abc" for e in errors)

    def test_rmdir_oserror_logged_but_does_not_crash(self, hive_env):
        """OSError from dir_path.rmdir() in auto-fix mode is logged but doesn't raise."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / "b.abc"
        dir_path.mkdir()
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(dir_path, (old_time, old_time))

        with patch("pathlib.Path.rmdir", side_effect=OSError("permission denied")):
            linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=True)
            report = linter.run()  # Must not raise

        # Directory was not removed (rmdir was mocked to fail)
        assert dir_path.exists()
        # No fix was recorded
        assert not any(f.fix_type == "remove_empty_dir" for f in report.fixes)

    def test_empty_ticket_dir_reported_in_detect_only_mode(self, hive_env):
        """Old empty ticket-ID-named dir is reported even when detect_only=True."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / "b.abc"
        dir_path.mkdir()
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(dir_path, (old_time, old_time))

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=False)
        report = linter.run(detect_only=True)

        errors = report.get_errors(error_type="empty_ticket_dir")
        assert any(e.ticket_id == "b.abc" for e in errors)

    @pytest.mark.parametrize(
        "dir_name",
        [
            pytest.param("notes", id="plain_word"),
            pytest.param("archive", id="archive_dir"),
            pytest.param(".git", id="dotgit"),
        ],
    )
    def test_non_ticket_id_dir_ignored(self, hive_env, dir_name):
        """Directory whose name does not match a ticket ID pattern is ignored entirely."""
        repo_root, tickets_dir, hive_name = hive_env

        dir_path = tickets_dir / dir_name
        dir_path.mkdir()
        old_time = time.time() - 1200  # 20 minutes ago
        os.utime(dir_path, (old_time, old_time))

        linter = Linter(tickets_dir=str(tickets_dir), hive_name=hive_name, auto_fix=False)
        report = linter.run()

        errors = report.get_errors(error_type="empty_ticket_dir")
        assert not any(e.ticket_id == dir_name for e in errors)


class TestValidatePathMatchesId:
    """Tests for SR-7.3 path/ID consistency validation (validate_path_matches_id)."""

    def test_consistent_path_and_id_no_errors(self, hive_env):
        """Ticket with directory t1.xyz.ab/ and frontmatter id: t1.xyz.ab produces no path_id_mismatch."""
        repo_root, tickets_dir, hive_name = hive_env
        write_ticket_file(tickets_dir, TICKET_ID_LINTER_TASK_MAIN, title="Task", type="t1")

        linter = Linter(str(tickets_dir), hive_name=hive_name)
        report = linter.run()

        errors = report.get_errors(error_type="path_id_mismatch")
        assert len(errors) == 0

    def test_old_format_directory_name_flags_path_id_mismatch(self, hive_env):
        """Ticket in t1.abcde/ (old format) with frontmatter id: t1.abc.de (new format) flags path_id_mismatch."""
        repo_root, tickets_dir, hive_name = hive_env

        # Create file in old-format directory (concatenated, no period) but frontmatter uses new period-separated id
        old_dir = tickets_dir / "t1.abcde"
        old_dir.mkdir(parents=True)
        (old_dir / "t1.abcde.md").write_text(
            "---\n"
            f"id: {TICKET_ID_T1}\n"
            "schema_version: '1.1'\n"
            "type: t1\n"
            "title: Task\n"
            "status: open\n"
            "tags: []\n"
            "children: []\n"
            "up_dependencies: []\n"
            "down_dependencies: []\n"
            "created_at: '2024-01-01T00:00:00+00:00'\n"
            f"guid: {GUID_EXAMPLE_T1}\n"
            "---\n\nTask body.\n"
        )

        linter = Linter(str(tickets_dir), hive_name=hive_name)
        report = linter.run()

        errors = report.get_errors(error_type="path_id_mismatch")
        assert len(errors) >= 1
        assert any(e.ticket_id == TICKET_ID_T1 for e in errors)

    def test_filename_stem_mismatch_flags_path_id_mismatch(self, tmp_path):
        """validate_path_matches_id flags mismatch when filename stem doesn't match ticket id."""
        linter = Linter(str(tmp_path))
        report = LinterReport()
        ticket = make_ticket(id=TICKET_ID_LINTER_TASK_MAIN, type="t1", title="Task")

        # File in correct directory but with wrong filename stem
        file_path = tmp_path / TICKET_ID_LINTER_TASK_MAIN / "wrongname.md"
        linter.validate_path_matches_id(ticket, report, file_path)

        errors = report.get_errors(error_type="path_id_mismatch")
        assert len(errors) == 1
        assert "wrongname" in errors[0].message
