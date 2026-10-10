"""Unit tests for YAML frontmatter serialization in src/writer.py.

PURPOSE:
Tests fast_serialize_frontmatter() and serialize_frontmatter() for correct YAML
output across all supported data types and the yaml.dump fallback path.

SCOPE - Tests that belong here:
- fast_serialize_frontmatter(): Fast hand-written YAML serializer
- serialize_frontmatter(): Serialize with fast path and yaml.dump fallback
- YAML correctness (parseable, round-trips expected values)
- Format specifics (block lists, literal block strings, quoting rules)
- Fallback path behavior for unsupported types

SCOPE - Tests that DON'T belong here:
- write_ticket_file() filesystem operations -> test_writer_factory.py
- Ticket creation and factory logic -> test_writer_factory.py
"""

import random
import re
from datetime import datetime

import pytest
import yaml

from src.parser import ParseError, parse_frontmatter
from src.writer import fast_serialize_frontmatter, serialize_frontmatter
from tests.test_constants import DASH_VALUES, QUOTING_VALUES

# Every line break a ticket file reader sees: universal newlines ("\r\n", "\r", "\n") and YAML (also NEL, LS, PS)
_LINE_BREAK = re.compile("\r\n|[\n\r\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")

# YAML indicators and resolver characters, then tab, line breaks, control and other special characters
_FUZZ_ALPHABET = [*"ab -?:#%.'\"!&*|>{[,@`~=<01exyNnoT\\/+_", "\t", "\n", "\r", "\x00", "\x07", "\x1f", "\x7f",
                  "\x85", "\x9f", "\xa0", "\N{LINE SEPARATOR}", "\N{PARAGRAPH SEPARATOR}", "\N{IDEOGRAPHIC SPACE}",
                  "\ufeff", "\uffff", "\ud800", "\U0001F600"]


def _generated_strings(count: int, seed: int = 4) -> list[str]:
    """Seeded random strings of 0 to 8 characters from _FUZZ_ALPHABET."""
    rnd = random.Random(seed)
    return ["".join(rnd.choices(_FUZZ_ALPHABET, k=rnd.randint(0, 8))) for _ in range(count)]


def _parse_fm(text: str) -> dict:
    """Parse YAML frontmatter between --- delimiters, returning a dict."""
    inner = text.split("---\n", 1)[1].rsplit("\n---\n", 1)[0]
    return yaml.safe_load(inner) or {}


class TestFastSerializeFrontmatter:
    """Tests for fast_serialize_frontmatter() — the hand-written fast path."""

    def test_delimiters(self):
        """Output is wrapped in --- delimiters."""
        result = fast_serialize_frontmatter({"id": "b.abc"})
        assert result.startswith("---\n")
        assert result.endswith("---\n")

    @pytest.mark.parametrize("key,value,expected_line", [
        pytest.param("schema_version", 1, "schema_version: 1\n", id="int"),
        pytest.param("score", 2.5, "score: 2.5\n", id="float"),
        pytest.param("parent", None, "parent: null\n", id="null"),
        pytest.param("active", True, "active: true\n", id="bool_true"),
        pytest.param("active", False, "active: false\n", id="bool_false"),
    ])
    def test_scalar_types(self, key, value, expected_line):
        """Scalars (int, float, None, bool) serialize to expected YAML lines."""
        result = fast_serialize_frontmatter({key: value})
        assert expected_line in result

    @pytest.mark.parametrize("value", [
        pytest.param("true", id="yaml_true"),
        pytest.param("null", id="yaml_null"),
        pytest.param("yes", id="yaml_yes"),
        pytest.param("no", id="yaml_no"),
        pytest.param("on", id="yaml_on"),
        pytest.param("off", id="yaml_off"),
        pytest.param("Fix: the bug", id="colon_space"),
        pytest.param("[DRAFT]", id="leading_bracket"),
        pytest.param("", id="empty_string"),
    ])
    def test_strings_requiring_quotes_round_trip(self, value):
        """Strings needing quoting are single-quoted and parse back to the original value."""
        result = fast_serialize_frontmatter({"field": value})
        assert _parse_fm(result).get("field") == value

    def test_datetime_quoted_iso(self):
        """Datetime values are emitted as single-quoted ISO strings."""
        dt = datetime(2024, 6, 15, 10, 30, 0)
        result = fast_serialize_frontmatter({"created_at": dt})
        assert f"created_at: '{dt.isoformat()}'\n" in result

    def test_empty_list_skipped(self):
        """Empty lists are omitted from the output."""
        result = fast_serialize_frontmatter({"tags": [], "title": "Test"})
        assert "tags:" not in result
        assert "title: Test\n" in result

    def test_nonempty_list_block_style(self):
        """Non-empty lists use block sequence style and round-trip correctly."""
        result = fast_serialize_frontmatter({"tags": ["alpha", "beta"]})
        assert "tags:\n- alpha\n- beta\n" in result
        assert _parse_fm(result)["tags"] == ["alpha", "beta"]

    def test_key_ordering_preserved(self):
        """Key insertion order from the input dict is preserved in the output."""
        data = {"id": "b.abc", "type": "bee", "title": "Test"}
        result = fast_serialize_frontmatter(data)
        assert result.index("id:") < result.index("type:") < result.index("title:")

    def test_nested_dict_raises_value_error(self):
        """Nested dicts are unsupported and raise ValueError."""
        with pytest.raises(ValueError, match="Nested dict not supported"):
            fast_serialize_frontmatter({"meta": {"key": "value"}})

    def test_list_with_dict_item_raises_value_error(self):
        """Lists containing dict items raise ValueError."""
        with pytest.raises(ValueError):
            fast_serialize_frontmatter({"items": [{"k": "v"}]})

    @pytest.mark.parametrize("value,expected", [
        pytest.param("Hello World", "title: Hello World\n", id="plain"),
        pytest.param("Line one\nLine two", "title: |-\n  Line one\n  Line two\n", id="multiline_no_trailing_newline"),
        pytest.param("Line one\nLine two\n", "title: |\n  Line one\n  Line two\n", id="multiline_trailing_newline"),
        pytest.param("First\n\nSecond", "title: |-\n  First\n\n  Second\n", id="multiline_blank_line_bare"),
        pytest.param("1e3", "title: '1e3'\n", id="float_literal_quoted"),
        pytest.param("nan", "title: 'nan'\n", id="nan_quoted"),
        pytest.param("inf", "title: 'inf'\n", id="inf_quoted"),
        pytest.param("yEs", "title: 'yEs'\n", id="keyword_mixed_case_quoted"),
        pytest.param("NULL", "title: 'NULL'\n", id="keyword_upper_case_quoted"),
        pytest.param("-x", "title: -x\n", id="dash_text_plain"),
        pytest.param("2024-01-15 sync", "title: 2024-01-15 sync\n", id="date_then_text_plain"),
        pytest.param("-", "title: '-'\n", id="lone_dash_quoted"),
        pytest.param("- x", "title: '- x'\n", id="dash_space_quoted"),
        pytest.param("a:\tb", "title: 'a:\tb'\n", id="tab_quoted"),
        pytest.param("=", "title: '='\n", id="value_key_quoted"),
        pytest.param("1:20", "title: '1:20'\n", id="sexagesimal_quoted"),
        pytest.param(" a\nb", "title: |2-\n   a\n  b\n", id="space_first_line_indent_indicator"),
        pytest.param("a\n\n\n", "title: |+\n  a\n\n\n", id="trailing_newlines_keep"),
        pytest.param("\n", "title: |+\n\n", id="only_a_newline_keep"),
    ])
    def test_string_style(self, value, expected):
        """A string takes the first style that reads back exactly: plain, single-quoted, literal block (b.gg4)."""
        result = fast_serialize_frontmatter({"title": value, "guid": "g"})

        assert result == f"---\n{expected}guid: g\n---\n"
        assert _parse_fm(result)["title"] == value

    @pytest.mark.parametrize("data", [
        pytest.param({"title": "a\x07b"}, id="control_character"),
        pytest.param({"title": "\ufeffa"}, id="byte_order_mark"),
        pytest.param({"title": "a\x85b"}, id="nel"),
        pytest.param({"title": "a\uffffb"}, id="noncharacter"),
        pytest.param({"title": "a\ud800b"}, id="lone_surrogate"),
        pytest.param({"title": "a\n\x07"}, id="control_character_in_block"),
        pytest.param({"tags": ["a\x07b"]}, id="control_character_list_item"),
        pytest.param({"tags": ["a\nb"]}, id="multi_line_list_item"),
    ])
    def test_unwritable_strings_fall_back_to_yaml_dump(self, data):
        """A string the fast path cannot write safely raises ValueError; the yaml.dump fallback reads back (b.gg4)."""
        with pytest.raises(ValueError):
            fast_serialize_frontmatter(data)

        assert _parse_fm(serialize_frontmatter(data)) == data


class TestSerializeFrontmatter:
    """Tests for serialize_frontmatter() — fast path + yaml.dump fallback."""

    @pytest.mark.parametrize("data,label", [
        pytest.param({"id": "b.abc", "title": "Test"}, "plain_scalars"),
        pytest.param({"parent": None, "title": "X"}, "null_field"),
        pytest.param({"tags": ["a", "b"]}, "nonempty_list"),
        pytest.param({"tags": []}, "empty_list"),
        pytest.param({"status": "true"}, "yaml_keyword_string"),
        pytest.param({"body": "Line one\nLine two"}, "multiline"),
        pytest.param({"body": "First\n\nSecond"}, "multiline_blank_line"),
        pytest.param({"created_at": datetime(2024, 1, 1)}, "datetime"),
    ])
    def test_uses_fast_path_for_standard_types(self, data, label):
        """serialize_frontmatter delegates to the fast path for standard ticket data."""
        assert serialize_frontmatter(data) == fast_serialize_frontmatter(data)

    def test_nested_dict_falls_back_to_yaml_dump(self):
        """Nested dicts trigger yaml.dump fallback producing valid parseable YAML."""
        data = {"id": "b.abc", "meta": {"key": "value"}}
        result = serialize_frontmatter(data)
        assert result.startswith("---\n")
        assert result.endswith("---\n")
        parsed = _parse_fm(result)
        assert parsed["id"] == "b.abc"
        assert parsed["meta"] == {"key": "value"}

    def test_fallback_empty_list_omitted(self):
        """In the yaml.dump fallback, empty lists are omitted."""
        data = {"tags": [], "meta": {"k": "v"}}
        result = serialize_frontmatter(data)
        parsed = _parse_fm(result)
        assert "tags" not in parsed
        assert parsed["meta"] == {"k": "v"}

    def test_fallback_datetime_serialized(self):
        """In the yaml.dump fallback, datetime is converted to ISO string before serialization."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        data = {"created_at": dt, "meta": {"k": "v"}}
        result = serialize_frontmatter(data)
        assert result.startswith("---\n")
        parsed = _parse_fm(result)
        assert parsed["meta"] == {"k": "v"}
        assert parsed.get("created_at") == dt.isoformat()

    @pytest.mark.parametrize("value", list(DASH_VALUES.values()), ids=list(DASH_VALUES))
    @pytest.mark.parametrize("field", ["title", "tags"])
    def test_no_frontmatter_line_starts_with_dashes(self, value, field):
        """In the yaml.dump fallback, no line between the delimiters starts with ---, at any line break (b.5yy)."""
        # The nested dict forces yaml.dump; test_reader.py's writer round trip covers the fast path
        data = {"id": "b.abc", field: [value] if field == "tags" else value, "guid": "g", "meta": {"key": value}}

        result = serialize_frontmatter(data)

        lines = _LINE_BREAK.split(result)
        assert lines[0] == "---" and lines[-2:] == ["---", ""]
        assert [line for line in lines[1:-2] if line.startswith("---")] == []
        assert _parse_fm(result) == data

    @pytest.mark.parametrize("shape", ["middle_key", "last_key", "list_item", "last_list_item"])
    def test_generated_strings_round_trip_through_parser(self, tmp_path, shape):
        """Every string, named or seeded-random, reads back exactly through parse_frontmatter, fast path or fallback,
        and no frontmatter line starts with --- (b.gg4, b.5yy)."""
        path = tmp_path / "ticket.md"
        failures = []
        for value in [*QUOTING_VALUES.values(), *DASH_VALUES.values(), *_generated_strings(2000)]:
            data = {
                "middle_key": {"id": "b.abc", "title": value, "guid": "g"},
                "last_key": {"id": "b.abc", "status": value},
                "list_item": {"id": "b.abc", "tags": [value, "z"], "guid": "g"},
                "last_list_item": {"id": "b.abc", "tags": ["z", value]},
            }[shape]
            text = serialize_frontmatter(data)
            path.write_text(f"{text}\nbody\n", encoding="utf-8")
            try:
                read_back = parse_frontmatter(path)
            except ParseError as e:
                read_back = e
            dash_lines = [line for line in _LINE_BREAK.split(text)[1:-2] if line.startswith("---")]
            if read_back != (data, "body") or dash_lines:
                failures.append((value, text))

        assert failures == []
