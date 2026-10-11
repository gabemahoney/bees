"""Tests for ticket file reading and parsing."""

from datetime import datetime
from unittest.mock import patch

import pytest

from src import writer
from src.models import Ticket
from src.parser import ParseError, parse_frontmatter
from src.reader import read_ticket
from src.repo_context import repo_root_context
from src.validator import ValidationError, validate_id_format, validate_ticket
from tests.conftest import write_scoped_config
from tests.helpers import write_ticket_file
from tests.test_constants import (
    DASH_VALUES,
    GUID_EXAMPLE_BEE,
    INVALID_PRIORITY_FRONTMATTER,
    TICKET_ID_ABC,
    TICKET_ID_INVALID_TOOLONG,
    TICKET_ID_INVALID_UPPER_PREFIX,
    TICKET_ID_LEGACY_BEE,
    TICKET_ID_LEGACY_BEE_ALT,
    TICKET_ID_LEGACY_SUBTASK,
    TICKET_ID_LEGACY_TASK,
    TITLE_TEST_BEE,
    TITLE_TEST_SUBTASK,
    TITLE_TEST_TASK,
)


def _setup_tiers(tmp_path, mock_global_bees_dir):
    """Configure standard 3-tier hierarchy for validation tests."""
    scope_data = {
        "hives": {},
        "child_tiers": {"t1": ["Task", "Tasks"], "t2": ["Subtask", "Subtasks"]},
    }
    write_scoped_config(mock_global_bees_dir, tmp_path, scope_data)
    ctx = repo_root_context(tmp_path)
    ctx.__enter__()
    return ctx


class TestParseFrontmatter:
    """Tests for frontmatter parsing."""

    def test_parse_valid_frontmatter(self, tmp_path):
        """Should successfully parse valid YAML frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text(f"""---
id: {TICKET_ID_LEGACY_BEE}
type: bee
title: {TITLE_TEST_BEE}
---

This is the body.""")

        frontmatter, body = parse_frontmatter(file_path)
        assert frontmatter["id"] == TICKET_ID_LEGACY_BEE
        assert frontmatter["type"] == "bee"
        assert frontmatter["title"] == TITLE_TEST_BEE
        assert body == "This is the body."

    def test_parse_with_lists(self, tmp_path):
        """Should parse lists in frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text(f"""---
id: {TICKET_ID_ABC}
type: t1
title: Test Task
tags:
  - open
  - p0
children:
  - {TICKET_ID_LEGACY_SUBTASK}
---

Body text.""")

        frontmatter, body = parse_frontmatter(file_path)
        assert frontmatter["tags"] == ["open", "p0"]
        assert frontmatter["children"] == [TICKET_ID_LEGACY_SUBTASK]

    @pytest.mark.parametrize(
        "content,match",
        [
            pytest.param("Just plain text", "does not start with", id="missing_frontmatter"),
            pytest.param(f"---\nid: {TICKET_ID_LEGACY_BEE}\ntitle: [invalid yaml: unclosed\n---\n\nBody.", "Failed to parse YAML", id="malformed_yaml"),
            pytest.param(f"---\nid: {TICKET_ID_LEGACY_BEE}\ntype: bee\n\nBody without closing delimiter.", "invalid frontmatter format", id="missing_closing"),
            # b.5yy: three dashes inside a value, or on an indented line of one, never close the frontmatter
            pytest.param(
                f"---\nid: {TICKET_ID_LEGACY_BEE}\ntitle: a---b\n\nBody.",
                "invalid frontmatter format",
                id="dashes_only_inside_a_value",
            ),
            pytest.param(
                f"---\nid: {TICKET_ID_LEGACY_BEE}\ntitle: |-\n  a\n  ---\n  b\n",
                "invalid frontmatter format",
                id="dashes_only_on_an_indented_line",
            ),
        ],
    )
    def test_parse_errors(self, tmp_path, content, match):
        """Should raise ParseError for various invalid formats."""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)
        with pytest.raises(ParseError, match=match):
            parse_frontmatter(file_path)

    def test_nonexistent_file_raises_error(self, tmp_path):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_frontmatter(tmp_path / "nonexistent.md")

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param("", id="empty"),
            pytest.param("x\n", id="one_trailing_newline"),
            pytest.param("x\n\n", id="two_trailing_newlines"),
            pytest.param("\nx", id="leading_newline"),
            pytest.param("  x  ", id="surrounding_spaces"),
            pytest.param(" ", id="only_a_space"),
            pytest.param("\n", id="only_a_newline"),
            pytest.param("\n\n", id="only_two_newlines"),
            pytest.param("\tindented\n---\nafter a rule\n", id="tab_and_rule_line"),
            pytest.param("literal \\t stays", id="literal_backslash_t"),
        ],
    )
    def test_body_round_trips_through_writer(self, tmp_path, body):
        """A body written by the writer reads back exactly, whitespace included (b.pp8)."""
        path = tmp_path / "ticket.md"
        writer.write_ticket_file(
            TICKET_ID_ABC, "bee", {"id": TICKET_ID_ABC, "type": "bee", "title": "T"}, body, file_path=path
        )

        assert parse_frontmatter(path)[1] == body

    @pytest.mark.parametrize(
        "body,expected_body",
        [
            pytest.param("a\r\nb\r\n", "a\nb\n", id="crlf"),
            pytest.param("a\rb", "a\nb", id="lone_cr"),
            pytest.param("x\r", "x", id="final_cr_merges_with_trailing_newline"),
            pytest.param("\r", "", id="only_a_cr"),
        ],
    )
    def test_cr_line_endings_read_back_as_lf(self, tmp_path, body, expected_body):
        """Pins current universal-newline behaviour, not a requirement: change it on purpose."""
        path = tmp_path / "ticket.md"
        writer.write_ticket_file(
            TICKET_ID_ABC, "bee", {"id": TICKET_ID_ABC, "type": "bee", "title": "T"}, body, file_path=path
        )

        assert parse_frontmatter(path)[1] == expected_body

    @pytest.mark.parametrize("value", list(DASH_VALUES.values()), ids=list(DASH_VALUES))
    @pytest.mark.parametrize("field", ["title", "tags", "reference_materials"])
    def test_value_with_dashes_round_trips_through_writer(self, tmp_path, field, value):
        """A value holding --- never closes the frontmatter: it, every later field and the body read back (b.5yy)."""
        frontmatter = {"id": TICKET_ID_ABC, "type": "bee", "title": "T", "status": "open"}
        frontmatter[field] = {"tags": [value, "next"], "reference_materials": [{"value": value}]}.get(field, value)
        frontmatter.update(schema_version="0.1", guid=GUID_EXAMPLE_BEE)
        body = "Body\n---\nend\n"
        path = tmp_path / "ticket.md"
        writer.write_ticket_file(TICKET_ID_ABC, "bee", frontmatter, body, file_path=path)

        assert parse_frontmatter(path) == (frontmatter, body)

    @pytest.mark.parametrize("last_lines", [
        pytest.param("title: x\t\n", id="tab_after_last_line"),
        pytest.param("title: x\n\t\n", id="tab_only_line_before_closing"),
    ])
    def test_tab_in_hand_edited_frontmatter_end_still_parses(self, tmp_path, last_lines):
        """A tab ending the last frontmatter line, or alone on a line before the closing ---, still parses (b.gg4)."""
        path = tmp_path / "test.md"
        path.write_text(f"---\nid: {TICKET_ID_ABC}\n{last_lines}---\nBody.\n")

        assert parse_frontmatter(path) == ({"id": TICKET_ID_ABC, "title": "x"}, "Body.")

    def test_keep_chomped_last_value_keeps_trailing_newlines(self, tmp_path):
        """A |+ block scalar as the last key keeps its trailing newlines, since the closing line's newline is not stripped."""
        path = tmp_path / "test.md"
        path.write_text(f"---\nid: {TICKET_ID_ABC}\ntitle: |+\n  a\n\n\n---\nBody.\n")

        assert parse_frontmatter(path) == ({"id": TICKET_ID_ABC, "title": "a\n\n\n"}, "Body.")

    @pytest.mark.parametrize(
        "after_closing_delimiter,expected_body",
        [
            pytest.param("\nbody\n", "body", id="no_blank_separator"),
            pytest.param("\n\nbody\n", "body", id="blank_separator"),
            pytest.param("\n\nbody", "body", id="no_final_newline"),
            pytest.param("  \n\nbody\n", "body", id="spaces_after_delimiter"),
            pytest.param("body\nmore\n", "body\nmore", id="text_on_delimiter_line"),
            pytest.param("", "", id="frontmatter_only_no_newline"),
            pytest.param("\n", "", id="frontmatter_only"),
            pytest.param("\n\n", "", id="frontmatter_only_blank_line"),
        ],
    )
    def test_body_layouts_not_written_by_writer(self, tmp_path, after_closing_delimiter, expected_body):
        """Hand-written and older layouts read without the separator and final newline."""
        path = tmp_path / "test.md"
        path.write_text(f"---\nid: {TICKET_ID_LEGACY_BEE}\ntype: bee\n---{after_closing_delimiter}")

        assert parse_frontmatter(path)[1] == expected_body


class TestValidateTicket:
    """Tests for ticket validation."""

    def test_validate_valid_epic(self):
        """Should pass validation for valid epic."""
        validate_ticket({"id": TICKET_ID_LEGACY_BEE, "type": "bee", "title": TITLE_TEST_BEE})

    def test_validate_valid_task(self, tmp_path, mock_global_bees_dir):
        """Should pass validation for valid task."""
        ctx = _setup_tiers(tmp_path, mock_global_bees_dir)
        try:
            validate_ticket({"id": TICKET_ID_LEGACY_TASK, "type": "t1", "title": TITLE_TEST_TASK, "parent": TICKET_ID_LEGACY_BEE})
        finally:
            ctx.__exit__(None, None, None)

    def test_validate_valid_subtask(self, tmp_path, mock_global_bees_dir):
        """Should pass validation for valid subtask with parent."""
        ctx = _setup_tiers(tmp_path, mock_global_bees_dir)
        try:
            validate_ticket({"id": TICKET_ID_LEGACY_SUBTASK, "type": "t2", "title": TITLE_TEST_SUBTASK, "parent": TICKET_ID_LEGACY_TASK})
        finally:
            ctx.__exit__(None, None, None)

    @pytest.mark.parametrize(
        "ticket,match",
        [
            pytest.param({"id": TICKET_ID_LEGACY_BEE, "title": "Missing type"}, "Missing required field: type", id="missing_type"),
            pytest.param({"id": TICKET_ID_LEGACY_BEE, "type": "invalid", "title": "Test"}, "Invalid type", id="invalid_type"),
            pytest.param({"id": "INVALID-ID", "type": "bee", "title": "Test"}, "Invalid ID format", id="invalid_id"),
            pytest.param({"id": TICKET_ID_LEGACY_BEE, "type": "bee", "title": "Test", "tags": "not-a-list"}, "must be list", id="tags_not_list"),
        ],
    )
    def test_validation_errors(self, ticket, match):
        """Should raise ValidationError for invalid tickets."""
        with pytest.raises(ValidationError, match=match):
            validate_ticket(ticket)

    def test_subtask_without_parent_raises_error(self, tmp_path, mock_global_bees_dir):
        """Business validation should raise error if subtask has no parent."""
        ctx = _setup_tiers(tmp_path, mock_global_bees_dir)
        try:
            with pytest.raises(ValidationError, match="must have a parent"):
                validate_ticket({"id": TICKET_ID_LEGACY_SUBTASK, "type": "t2", "title": "Test"})
        finally:
            ctx.__exit__(None, None, None)


class TestValidateIdFormat:
    """Tests for ID format validation."""

    def test_valid_ids(self):
        """Should accept valid ID formats."""
        for id_ in [TICKET_ID_LEGACY_BEE, TICKET_ID_ABC, TICKET_ID_LEGACY_BEE_ALT, TICKET_ID_LEGACY_TASK]:
            assert validate_id_format(id_)

    def test_invalid_ids(self):
        """Should reject invalid ID formats."""
        for id_ in [TICKET_ID_INVALID_UPPER_PREFIX, "x.25a", "b.", TICKET_ID_INVALID_TOOLONG, "25a"]:
            assert not validate_id_format(id_)


class TestReadTicket:
    """Tests for read_ticket function."""

    @pytest.mark.parametrize(
        "ticket_id,title,type,extra_kwargs,check_fields",
        [
            pytest.param(
                TICKET_ID_LEGACY_BEE, "Core Schema", "bee",
                {"tags": ["open", "p0"], "children": [TICKET_ID_LEGACY_TASK], "body": "Implementation of the core schema."},
                {"tags": ["open", "p0"], "children": [TICKET_ID_LEGACY_TASK]},
                id="epic",
            ),
            pytest.param(
                TICKET_ID_LEGACY_TASK, "Design Schema", "t1",
                {"parent": TICKET_ID_LEGACY_BEE, "up_dependencies": [TICKET_ID_ABC], "body": "Design the ticket schema."},
                {"parent": TICKET_ID_LEGACY_BEE, "up_dependencies": [TICKET_ID_ABC]},
                id="t1",
            ),
            pytest.param(
                TICKET_ID_LEGACY_SUBTASK, "Write code", "t2",
                {"parent": TICKET_ID_LEGACY_TASK, "body": "Write the implementation."},
                {"parent": TICKET_ID_LEGACY_TASK},
                id="t2",
            ),
        ],
    )
    def test_read_ticket_types(self, tmp_path, ticket_id, title, type, extra_kwargs, check_fields):
        """Should read and return correct ticket type with all fields."""
        file_path = write_ticket_file(tmp_path, ticket_id, title=title, type=type, **extra_kwargs)
        ticket = read_ticket(ticket_id, file_path=file_path)

        assert isinstance(ticket, Ticket)
        assert ticket.id == ticket_id
        assert ticket.type == type
        assert ticket.title == title
        for field, value in check_fields.items():
            assert getattr(ticket, field) == value

    def test_read_with_datetime(self, tmp_path):
        """Should parse datetime fields."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_LEGACY_BEE, created_at="2026-01-30T10:00:00")
        ticket = read_ticket(TICKET_ID_LEGACY_BEE, file_path=file_path)
        assert isinstance(ticket.created_at, datetime)
        assert ticket.created_at.year == 2026

    def test_invalid_file_raises_error(self, tmp_path):
        """Should raise error for invalid files."""
        file_path = tmp_path / "test.md"
        file_path.write_text("Invalid content")
        with pytest.raises(ParseError):
            read_ticket("test", file_path=file_path)

    def test_read_with_extra_fields(self, tmp_path):
        """Should ignore extra fields not in Ticket model."""
        file_path = tmp_path / "test.md"
        file_path.write_text(f"---\nid: {TICKET_ID_LEGACY_BEE}\ntype: bee\ntitle: {TITLE_TEST_BEE}\nschema_version: '0.1'\ncustom_field: some_value\ntags:\n  - open\n---\n\nBody text.")

        ticket = read_ticket(TICKET_ID_LEGACY_BEE, file_path=file_path)
        assert ticket.id == TICKET_ID_LEGACY_BEE
        assert not hasattr(ticket, "custom_field")

    def test_schema_version_handling(self, tmp_path):
        """Should parse schema_version and reject tickets without it."""
        # Valid schema_version
        file_path = write_ticket_file(tmp_path, TICKET_ID_LEGACY_BEE, title="Versioned Epic")
        ticket = read_ticket(TICKET_ID_LEGACY_BEE, file_path=file_path)
        assert ticket.schema_version == "0.1"

        # Missing schema_version
        file_path2 = tmp_path / "no_version.md"
        file_path2.write_text(f"---\nid: {TICKET_ID_ABC}\ntype: bee\ntitle: Epic Without Version\n---\n\nBody content.")
        with pytest.raises(ValidationError) as exc_info:
            read_ticket(TICKET_ID_ABC, file_path=file_path2)
        assert "schema_version" in str(exc_info.value)
        assert "not a valid Bees ticket" in str(exc_info.value)

    def test_id_only_cold_cache_discovery(self, isolated_bees_env):
        """ID-only read discovers ticket from hive config without file_path."""
        hive_dir = isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        isolated_bees_env.create_ticket(hive_dir, TICKET_ID_LEGACY_BEE, "bee", TITLE_TEST_BEE)
        ticket = read_ticket(TICKET_ID_LEGACY_BEE)
        assert isinstance(ticket, Ticket)
        assert ticket.id == TICKET_ID_LEGACY_BEE
        assert ticket.title == TITLE_TEST_BEE

    def test_id_only_warm_cache_skips_discovery(self, isolated_bees_env):
        """ID-only read after warm cache hit does not call find_ticket_file."""
        hive_dir = isolated_bees_env.create_hive("backend")
        file_path = isolated_bees_env.create_ticket(hive_dir, TICKET_ID_LEGACY_BEE, "bee", TITLE_TEST_BEE)
        read_ticket(TICKET_ID_LEGACY_BEE, file_path=file_path)
        with patch("src.paths.find_ticket_file") as mock_find:
            ticket = read_ticket(TICKET_ID_LEGACY_BEE)
            mock_find.assert_not_called()
        assert ticket.title == TITLE_TEST_BEE

    def test_id_not_found_raises_file_not_found(self, isolated_bees_env):
        """ID-only read for non-existent ticket raises FileNotFoundError."""
        isolated_bees_env.create_hive("backend")
        isolated_bees_env.write_config()
        with pytest.raises(FileNotFoundError):
            read_ticket("b.ZZZZ")


class TestPermissiveReader:
    """Tests for permissive reader behavior (loads corrupt tickets for linter)."""

    @pytest.mark.parametrize(
        "ticket_id,type,title,check_field,check_value",
        [
            pytest.param(TICKET_ID_ABC, "t99", "Corrupt Ticket", "type", "t99", id="invalid_type_t99"),
            pytest.param(TICKET_ID_LEGACY_SUBTASK, "foo", "Another Corrupt", "type", "foo", id="invalid_type_foo"),
            pytest.param("THIS-IS-WRONG", "t1", "Bad ID Ticket", "id", "THIS-IS-WRONG", id="malformed_id"),
        ],
    )
    def test_read_ticket_with_invalid_values(self, tmp_path, ticket_id, type, title, check_field, check_value):
        """Reader should load tickets with invalid type/ID values permissively."""
        file_path = write_ticket_file(tmp_path, ticket_id, type=type, title=title)
        ticket = read_ticket(ticket_id, file_path=file_path)
        assert getattr(ticket, check_field) == check_value

    def test_read_bee_with_parent(self, tmp_path):
        """Reader should load bees with parent fields (business rule violation)."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_ABC, title="Bee with Parent", parent=TICKET_ID_LEGACY_SUBTASK)
        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)
        assert ticket.type == "bee"
        assert ticket.parent == TICKET_ID_LEGACY_SUBTASK

    def test_read_orphaned_subtask(self, tmp_path):
        """Reader should load subtasks without parent (business rule violation)."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_LEGACY_SUBTASK, type="t2", title="Orphaned Subtask")
        ticket = read_ticket(TICKET_ID_LEGACY_SUBTASK, file_path=file_path)
        assert ticket.type == "t2"
        assert ticket.parent is None

    @pytest.mark.parametrize(
        "content,match",
        [
            pytest.param("---\ntype: t1\ntitle: Missing ID\nschema_version: '0.1'\n---\n\nBody.", "Missing required field: id", id="missing_id"),
            pytest.param(f"---\nid: {TICKET_ID_ABC}\ntype: \ntitle: Empty Type\nschema_version: '0.1'\n---\n\nBody.", "cannot be empty", id="empty_type"),
            pytest.param("---\nid: 12345\ntype: t1\ntitle: Numeric ID\nschema_version: '0.1'\n---\n\nBody.", "must be string", id="non_string_id"),
        ],
    )
    def test_reader_rejects_structural_errors(self, tmp_path, content, match):
        """Reader should still reject missing/empty/non-string required fields."""
        file_path = tmp_path / "test.md"
        file_path.write_text(content)
        with pytest.raises(ValidationError, match=match):
            read_ticket("test", file_path=file_path)


class TestRawKeysCapture:
    """Tests for _raw_keys frontmatter key capture in read_ticket()."""

    def test_raw_keys_contains_frontmatter_keys(self, tmp_path):
        """_raw_keys should contain exactly the keys from raw frontmatter."""
        file_path = write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Test", status="open", tags=["bug"]
        )
        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)
        assert isinstance(ticket._raw_keys, frozenset)
        for key in ("id", "schema_version", "title", "type", "status", "tags"):
            assert key in ticket._raw_keys

    def test_raw_keys_excludes_description(self, tmp_path):
        """_raw_keys should NOT contain 'description' for normal tickets (body-based)."""
        file_path = write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Test", body="Some body content"
        )
        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)
        assert "description" not in ticket._raw_keys

    def test_raw_keys_includes_description_when_in_frontmatter(self, tmp_path):
        """_raw_keys SHOULD contain 'description' if explicitly in frontmatter."""
        file_path = tmp_path / "test.md"
        file_path.write_text(
            f"---\nid: {TICKET_ID_ABC}\ntype: bee\ntitle: Test\n"
            f"schema_version: '0.1'\ndescription: inline desc\n---\n\nBody."
        )
        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)
        assert "description" in ticket._raw_keys

    def test_raw_keys_includes_disallowed_fields(self, tmp_path):
        """_raw_keys should capture disallowed fields present in frontmatter."""
        file_path = write_ticket_file(
            tmp_path, TICKET_ID_ABC, title="Test", owner="someone", created_by="someone"
        )
        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)
        assert "owner" in ticket._raw_keys
        assert "created_by" in ticket._raw_keys


class TestPriorityRead:
    """Tests for the optional priority field in read_ticket()."""

    @pytest.mark.parametrize("ticket_type", ["bee", "t1", "t2"])
    @pytest.mark.parametrize("priority", [0, 3, -4, 2**70], ids=["zero", "positive", "negative", "beyond_64_bit"])
    def test_integer_priority_read_as_stored(self, tmp_path, ticket_type, priority):
        """An integer priority reads back unchanged on every tier."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_ABC, type=ticket_type, priority=priority)

        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)

        assert ticket.priority == priority
        assert type(ticket.priority) is int
        assert "priority" in ticket._raw_keys

    @pytest.mark.parametrize("ticket_type", ["bee", "t1"])
    @pytest.mark.parametrize("raw,stored,_", INVALID_PRIORITY_FRONTMATTER.values(), ids=list(INVALID_PRIORITY_FRONTMATTER))
    def test_priority_read_without_validation(self, tmp_path, ticket_type, raw, stored, _):
        """A non-integer priority loads as stored (the linter flags it); null and empty read as unset."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_ABC, type=ticket_type, raw_fields={"priority": raw})

        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)

        assert ticket.priority == stored
        assert type(ticket.priority) is type(stored)
        assert "priority" in ticket._raw_keys

    @pytest.mark.parametrize("ticket_type", ["bee", "t1"])
    def test_absent_priority_is_unset(self, tmp_path, ticket_type):
        """A ticket without the key reads as unset and does not record the key."""
        file_path = write_ticket_file(tmp_path, TICKET_ID_ABC, type=ticket_type)

        ticket = read_ticket(TICKET_ID_ABC, file_path=file_path)

        assert ticket.priority is None
        assert "priority" not in ticket._raw_keys



# get_ticket_type() is tested in tests/test_paths.py::TestGetTicketType
