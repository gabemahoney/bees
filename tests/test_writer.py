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

from datetime import datetime

import pytest
import yaml

from src.writer import fast_serialize_frontmatter, serialize_frontmatter


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

    def test_plain_string(self):
        """Plain strings without special characters emit without quoting."""
        result = fast_serialize_frontmatter({"title": "Hello World"})
        assert "title: Hello World\n" in result
        assert _parse_fm(result)["title"] == "Hello World"

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

    @pytest.mark.parametrize("body,expected_marker", [
        pytest.param("Line one\nLine two", "description: |-\n", id="no_trailing_newline"),
        pytest.param("Line one\nLine two\n", "description: |\n", id="with_trailing_newline"),
    ])
    def test_multiline_string_literal_block(self, body, expected_marker):
        """Multi-line strings use literal block style with correct chomp marker."""
        result = fast_serialize_frontmatter({"description": body})
        assert expected_marker in result
        assert "  Line one\n" in result
        assert "  Line two\n" in result

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

    def test_multiline_blank_line_no_trailing_whitespace(self):
        """Blank lines in multiline strings emit as bare newlines, not indented whitespace."""
        result = fast_serialize_frontmatter({"description": "First\n\nSecond"})
        assert "  First\n\n  Second\n" in result
        assert _parse_fm(result)["description"] == "First\n\nSecond"


class TestSerializeFrontmatter:
    """Tests for serialize_frontmatter() — fast path + yaml.dump fallback."""

    @pytest.mark.parametrize("data,label", [
        pytest.param({"id": "b.abc", "title": "Test"}, "plain_scalars"),
        pytest.param({"parent": None, "title": "X"}, "null_field"),
        pytest.param({"tags": ["a", "b"]}, "nonempty_list"),
        pytest.param({"tags": []}, "empty_list"),
        pytest.param({"status": "true"}, "yaml_keyword_string"),
        pytest.param({"description": "Line one\nLine two"}, "multiline"),
        pytest.param({"description": "First\n\nSecond"}, "multiline_blank_line"),
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
