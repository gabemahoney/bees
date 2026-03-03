"""
Unit tests for fast_parse_frontmatter in src/fast_parser.py.

PURPOSE:
Tests the line-based frontmatter parser that extracts pipeline-relevant
ticket fields without using a YAML library.

SCOPE - Tests that belong here:
- fast_parse_frontmatter(): All field patterns (scalar, list, null, quoted)
- All pipeline fields correctly extracted and typed
- Invalid format handling (no ---, truncated, missing schema_version)
- Compatibility with parse_frontmatter for standard ticket files

SCOPE - Tests that DON'T belong here:
- Full ticket loading/construction -> test_ticket_factory.py
- YAML linting -> test_linter.py
"""

import pytest
from pathlib import Path

from src.fast_parser import fast_parse_frontmatter
from src.parser import parse_frontmatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, content: str, name: str = "ticket.md") -> Path:
    """Write content to a temp .md file and return the path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReturnNoneConditions:
    """fast_parse_frontmatter returns None in error/invalid cases."""

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Should return None when the file does not exist."""
        result = fast_parse_frontmatter(tmp_path / "missing.md")
        assert result is None

    def test_no_leading_delimiter_returns_none(self, tmp_path):
        """Should return None when file doesn't start with ---."""
        path = _write(tmp_path, "Just plain text\nno frontmatter.\n")
        result = fast_parse_frontmatter(path)
        assert result is None

    def test_truncated_no_closing_delimiter_returns_none(self, tmp_path):
        """Should return None when the closing --- is missing."""
        content = "---\nid: b.abc\nschema_version: '0.1'\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is None

    def test_missing_schema_version_returns_none(self, tmp_path):
        """Should return None when schema_version is absent."""
        content = "---\nid: b.abc\ntype: bee\ntitle: Test\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is None

    def test_empty_frontmatter_block_returns_none(self, tmp_path):
        """Should return None for a --- --- block with no fields."""
        path = _write(tmp_path, "---\n---\nBody.\n")
        result = fast_parse_frontmatter(path)
        assert result is None

    @pytest.mark.parametrize(
        "content",
        [
            pytest.param("id: b.abc\n---\nschema_version: '0.1'\n---\n", id="no_opening_dashes"),
            pytest.param("plain text file\n", id="plain_text"),
            pytest.param("\n\n---\nschema_version: '0.1'\n---\n", id="leading_newline_before_dashes"),
        ],
    )
    def test_various_no_frontmatter_formats(self, tmp_path, content):
        """Should return None for any file not starting with ---."""
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is None


class TestScalarFields:
    """Tests for scalar field extraction."""

    @pytest.mark.parametrize(
        "field,yaml_value,expected",
        [
            pytest.param("id", "b.abc", "b.abc", id="id"),
            pytest.param("type", "bee", "bee", id="type"),
            pytest.param("title", "My Ticket", "My Ticket", id="title"),
            pytest.param("status", "worker", "worker", id="status"),
            pytest.param("guid", "abcdef1234567890abcdef1234567890ab", "abcdef1234567890abcdef1234567890ab", id="guid"),
        ],
    )
    def test_scalar_string_fields(self, tmp_path, field, yaml_value, expected):
        """Should correctly extract simple unquoted string scalar fields."""
        content = f"---\n{field}: {yaml_value}\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result[field] == expected

    @pytest.mark.parametrize(
        "yaml_value,expected",
        [
            pytest.param("null", None, id="explicit_null"),
            pytest.param("~", None, id="tilde_null"),
            pytest.param("", None, id="bare_empty"),
        ],
    )
    def test_null_scalar_values(self, tmp_path, yaml_value, expected):
        """Should parse null, ~, and bare empty as None for scalar fields."""
        content = f"---\nparent: {yaml_value}\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result.get("parent") == expected

    @pytest.mark.parametrize(
        "quoted,expected",
        [
            pytest.param("'hello world'", "hello world", id="single_quoted"),
            pytest.param('"hello world"', "hello world", id="double_quoted"),
            pytest.param("'0.1'", "0.1", id="version_string_single_quoted"),
        ],
    )
    def test_quoted_strings_are_unquoted(self, tmp_path, quoted, expected):
        """Should strip surrounding single or double quotes from scalar values."""
        content = f"---\ntitle: {quoted}\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["title"] == expected

    def test_schema_version_single_quoted(self, tmp_path):
        """Schema version quoted as string should be returned without quotes."""
        content = "---\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["schema_version"] == "0.1"

    def test_schema_version_unquoted(self, tmp_path):
        """Schema version without quotes should still be returned as string."""
        content = "---\nschema_version: 0.1\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["schema_version"] == "0.1"

    @pytest.mark.parametrize(
        "yaml_value,expected",
        [
            pytest.param("true", True, id="lowercase_true"),
            pytest.param("True", True, id="capitalized_true"),
            pytest.param("false", False, id="lowercase_false"),
            pytest.param("False", False, id="capitalized_false"),
        ],
    )
    def test_boolean_scalar_values(self, tmp_path, yaml_value, expected):
        """Should parse true/True/false/False as Python booleans."""
        # Use status field (a known scalar field) to test boolean parsing
        content = f"---\nstatus: {yaml_value}\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["status"] is expected


class TestTitleWithColons:
    """Tests for values containing colons — first colon determines key split."""

    def test_title_with_url(self, tmp_path):
        """Should extract a title that contains a URL with colons."""
        content = "---\ntitle: See https://example.com for details\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["title"] == "See https://example.com for details"

    def test_title_with_colon_in_middle(self, tmp_path):
        """Should extract a title containing a colon after the first field separator."""
        content = "---\ntitle: Part one: part two\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["title"] == "Part one: part two"

    @pytest.mark.parametrize(
        "title_value,expected",
        [
            pytest.param("Error: something failed", "Error: something failed", id="error_colon"),
            pytest.param("http://old-style-url", "http://old-style-url", id="http_url"),
            pytest.param("a:b:c:d", "a:b:c:d", id="multiple_colons"),
        ],
    )
    def test_values_with_various_colon_patterns(self, tmp_path, title_value, expected):
        """Should correctly parse title values with multiple or unusual colon placements."""
        content = f"---\ntitle: {title_value}\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["title"] == expected


class TestListFields:
    """Tests for inline and multi-line list field extraction."""

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("tags", id="tags"),
            pytest.param("children", id="children"),
            pytest.param("up_dependencies", id="up_dependencies"),
            pytest.param("down_dependencies", id="down_dependencies"),
        ],
    )
    def test_inline_empty_list_for_all_list_fields(self, tmp_path, field):
        """Should parse [] as empty list for all four list fields."""
        content = f"---\n{field}: []\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result[field] == []

    def test_multiline_list_collects_items(self, tmp_path):
        """Should collect multi-line list items under the correct key."""
        content = (
            "---\n"
            "tags:\n"
            "  - alpha\n"
            "  - beta\n"
            "  - gamma\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["tags"] == ["alpha", "beta", "gamma"]

    def test_multiline_list_ends_at_next_field(self, tmp_path):
        """Multi-line list collection stops when the next YAML key appears."""
        content = (
            "---\n"
            "tags:\n"
            "  - alpha\n"
            "  - beta\n"
            "status: open\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["tags"] == ["alpha", "beta"]
        assert result["status"] == "open"

    def test_multiline_list_with_quoted_items(self, tmp_path):
        """Should strip quotes from quoted multi-line list items."""
        content = (
            "---\n"
            "tags:\n"
            "  - 'my-tag'\n"
            "  - \"another-tag\"\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["tags"] == ["my-tag", "another-tag"]

    def test_multiline_list_bare_hyphen_appends_none(self, tmp_path):
        """A bare - (no value) in a multi-line list should append None."""
        content = (
            "---\n"
            "tags:\n"
            "  - valid-item\n"
            "  -\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["tags"] == ["valid-item", None]

    def test_absent_list_fields_default_to_empty_list(self, tmp_path):
        """All four list fields should default to [] when absent from frontmatter."""
        content = "---\nid: b.abc\ntitle: Minimal\nschema_version: '0.1'\n---\nBody.\n"
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        for field in ("tags", "children", "up_dependencies", "down_dependencies"):
            assert result[field] == [], f"Expected {field} to default to []"

    def test_children_and_dependencies_multiline(self, tmp_path):
        """Should parse multi-line children and dependency lists correctly."""
        content = (
            "---\n"
            "children:\n"
            "  - t1.abc.de\n"
            "  - t1.abc.fg\n"
            "up_dependencies:\n"
            "  - b.xyz\n"
            "down_dependencies: []\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["children"] == ["t1.abc.de", "t1.abc.fg"]
        assert result["up_dependencies"] == ["b.xyz"]
        assert result["down_dependencies"] == []


class TestAllPipelineFields:
    """Tests for complete pipeline field extraction."""

    def test_all_known_fields_extracted(self, tmp_path):
        """Should extract all 11 known pipeline fields from a complete ticket file."""
        content = (
            "---\n"
            "id: b.abc\n"
            "type: bee\n"
            "title: Full Ticket\n"
            "status: open\n"
            "tags:\n"
            "  - tag1\n"
            "  - tag2\n"
            "parent: null\n"
            "children: []\n"
            "up_dependencies: []\n"
            "down_dependencies: []\n"
            "guid: abcdef1234567890abcdef1234567890ab\n"
            "schema_version: '0.1'\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert result["id"] == "b.abc"
        assert result["type"] == "bee"
        assert result["title"] == "Full Ticket"
        assert result["status"] == "open"
        assert result["tags"] == ["tag1", "tag2"]
        assert result["parent"] is None
        assert result["children"] == []
        assert result["up_dependencies"] == []
        assert result["down_dependencies"] == []
        assert result["guid"] == "abcdef1234567890abcdef1234567890ab"
        assert result["schema_version"] == "0.1"

    def test_unknown_fields_ignored(self, tmp_path):
        """Should silently ignore fields not in the known pipeline field set."""
        content = (
            "---\n"
            "id: b.abc\n"
            "schema_version: '0.1'\n"
            "created_at: 2026-01-01T00:00:00\n"
            "egg: null\n"
            "custom_field: whatever\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        assert "created_at" not in result
        assert "egg" not in result
        assert "custom_field" not in result
        assert result["id"] == "b.abc"

    def test_result_keys_are_only_known_fields(self, tmp_path):
        """Result dict should contain only fields from the known pipeline set."""
        known_fields = frozenset(
            ["id", "type", "title", "status", "tags", "parent",
             "children", "up_dependencies", "down_dependencies", "guid", "schema_version"]
        )
        content = (
            "---\n"
            "id: b.abc\n"
            "type: bee\n"
            "title: Test\n"
            "status: open\n"
            "schema_version: '0.1'\n"
            "egg: null\n"
            "extra: value\n"
            "---\nBody.\n"
        )
        path = _write(tmp_path, content)
        result = fast_parse_frontmatter(path)
        assert result is not None
        for key in result:
            assert key in known_fields, f"Unexpected key '{key}' in result"


class TestPathArgumentTypes:
    """Tests that both Path objects and strings are accepted."""

    def test_accepts_path_object(self, tmp_path):
        """Should accept a pathlib.Path argument."""
        path = _write(tmp_path, "---\nschema_version: '0.1'\n---\nBody.\n")
        result = fast_parse_frontmatter(path)
        assert result is not None

    def test_accepts_string_path(self, tmp_path):
        """Should accept a string path argument."""
        path = _write(tmp_path, "---\nschema_version: '0.1'\n---\nBody.\n")
        result = fast_parse_frontmatter(str(path))
        assert result is not None


class TestCompatibilityWithParseFrontmatter:
    """Fast parser pipeline field output should match parse_frontmatter for well-formed tickets."""

    _PIPELINE_FIELDS = [
        "id", "type", "title", "status", "tags", "parent",
        "children", "up_dependencies", "down_dependencies", "guid",
    ]

    @pytest.mark.parametrize(
        "label,content",
        [
            pytest.param(
                "minimal_bee",
                (
                    "---\n"
                    "id: b.abc\n"
                    "type: bee\n"
                    "title: Minimal Bee\n"
                    "status: open\n"
                    "tags: []\n"
                    "children: []\n"
                    "up_dependencies: []\n"
                    "down_dependencies: []\n"
                    "parent: null\n"
                    "guid: abcdef1234567890abcdef1234567890ab\n"
                    "schema_version: '0.1'\n"
                    "---\nBody.\n"
                ),
                id="minimal_bee",
            ),
            pytest.param(
                "bee_with_tags",
                (
                    "---\n"
                    "id: b.xyz\n"
                    "type: bee\n"
                    "title: Tagged Bee\n"
                    "status: pupa\n"
                    "tags:\n"
                    "  - alpha\n"
                    "  - beta\n"
                    "children: []\n"
                    "up_dependencies: []\n"
                    "down_dependencies: []\n"
                    "parent: null\n"
                    "guid: xyzdef1234567890abcdef1234567890xy\n"
                    "schema_version: '0.1'\n"
                    "---\nBody.\n"
                ),
                id="bee_with_tags",
            ),
            pytest.param(
                "task_with_parent",
                (
                    "---\n"
                    "id: t1.abc.de\n"
                    "type: t1\n"
                    "title: A Task\n"
                    "status: worker\n"
                    "tags: []\n"
                    "children: []\n"
                    "up_dependencies: []\n"
                    "down_dependencies: []\n"
                    "parent: b.abc\n"
                    "guid: abcde1f234567890abcdef1234567890de\n"
                    "schema_version: '0.1'\n"
                    "---\nBody.\n"
                ),
                id="task_with_parent",
            ),
        ],
    )
    def test_pipeline_fields_match(self, tmp_path, label, content):
        """Pipeline fields returned by fast parser should equal parse_frontmatter for each field."""
        path = _write(tmp_path, content, f"{label}.md")
        fast_result = fast_parse_frontmatter(path)
        yaml_result, _ = parse_frontmatter(path)

        assert fast_result is not None
        for field in self._PIPELINE_FIELDS:
            if field in yaml_result:
                fast_val = fast_result.get(field)
                yaml_val = yaml_result[field]
                assert fast_val == yaml_val, (
                    f"Field '{field}': fast={fast_val!r} != yaml={yaml_val!r}"
                )
