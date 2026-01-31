"""Unit tests for query parser and validator."""

import pytest
from src.query_parser import QueryParser, QueryValidationError


class TestQueryParserBasics:
    """Tests for basic query parsing."""

    def test_parse_simple_query(self):
        """Should parse simple single-stage query."""
        parser = QueryParser()
        query = [['type=epic']]

        stages = parser.parse(query)

        assert len(stages) == 1
        assert stages[0] == ['type=epic']

    def test_parse_multi_stage_query(self):
        """Should parse multi-stage query."""
        parser = QueryParser()
        query = [
            ['type=epic', 'label~beta'],
            ['children'],
            ['label~open']
        ]

        stages = parser.parse(query)

        assert len(stages) == 3
        assert stages[0] == ['type=epic', 'label~beta']
        assert stages[1] == ['children']
        assert stages[2] == ['label~open']

    def test_parse_yaml_string(self):
        """Should parse YAML string input."""
        parser = QueryParser()
        yaml_query = """
        - ['type=task']
        - ['parent']
        """

        stages = parser.parse(yaml_query)

        assert len(stages) == 2
        assert stages[0] == ['type=task']
        assert stages[1] == ['parent']

    def test_empty_query_raises_error(self):
        """Should raise error for empty query."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="cannot be empty"):
            parser.parse([])

    def test_non_list_query_raises_error(self):
        """Should raise error if query is not a list."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="must be a list"):
            parser.parse("not-a-list")

    def test_non_list_stage_raises_error(self):
        """Should raise error if stage is not a list."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="Stage 0 must be a list"):
            parser.parse(["not-a-list"])

    def test_empty_stage_raises_error(self):
        """Should raise error for empty stage."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="Stage 0 cannot be empty"):
            parser.parse([[]])

    def test_non_string_term_raises_error(self):
        """Should raise error if term is not a string."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="must be a string"):
            parser.parse([[123]])

    def test_invalid_yaml_raises_error(self):
        """Should raise error for invalid YAML."""
        parser = QueryParser()

        with pytest.raises(QueryValidationError, match="Invalid YAML"):
            parser.parse("[invalid: yaml: syntax")


class TestSearchTermValidation:
    """Tests for search term validation."""

    def test_valid_type_term(self):
        """Should accept valid type= terms."""
        parser = QueryParser()
        queries = [
            [['type=epic']],
            [['type=task']],
            [['type=subtask']]
        ]

        for query in queries:
            stages = parser.parse(query)
            parser.validate(stages)  # Should not raise

    def test_invalid_type_value_raises_error(self):
        """Should reject invalid type values."""
        parser = QueryParser()
        query = [['type=invalid']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Invalid type"):
            parser.validate(stages)

    def test_empty_type_value_raises_error(self):
        """Should reject empty type value."""
        parser = QueryParser()
        query = [['type=']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="type= term missing value"):
            parser.validate(stages)

    def test_valid_id_term(self):
        """Should accept valid id= terms."""
        parser = QueryParser()
        query = [['id=bees-250']]

        stages = parser.parse(query)
        parser.validate(stages)

    def test_empty_id_value_raises_error(self):
        """Should reject empty id value."""
        parser = QueryParser()
        query = [['id=']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="id= term missing value"):
            parser.validate(stages)

    def test_valid_title_regex_term(self):
        """Should accept valid title~ regex terms."""
        parser = QueryParser()
        queries = [
            [['title~test']],
            [['title~^Test']],
            [['title~(?i)beta']],
            [['title~beta|alpha']],
            [['title~^(?!.*preview).*']]
        ]

        for query in queries:
            stages = parser.parse(query)
            parser.validate(stages)

    def test_empty_title_regex_raises_error(self):
        """Should reject empty title~ pattern."""
        parser = QueryParser()
        query = [['title~']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="title~ term missing regex pattern"):
            parser.validate(stages)

    def test_invalid_title_regex_raises_error(self):
        """Should reject invalid title~ regex."""
        parser = QueryParser()
        query = [['title~[unclosed']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Invalid regex pattern"):
            parser.validate(stages)

    def test_valid_label_regex_term(self):
        """Should accept valid label~ regex terms."""
        parser = QueryParser()
        queries = [
            [['label~open']],
            [['label~(?i)beta']],
            [['label~beta|preview']],
            [['label~^(?!.*closed).*']]
        ]

        for query in queries:
            stages = parser.parse(query)
            parser.validate(stages)

    def test_empty_label_regex_raises_error(self):
        """Should reject empty label~ pattern."""
        parser = QueryParser()
        query = [['label~']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="label~ term missing regex pattern"):
            parser.validate(stages)

    def test_invalid_label_regex_raises_error(self):
        """Should reject invalid label~ regex."""
        parser = QueryParser()
        query = [['label~(?P<invalid']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Invalid regex pattern"):
            parser.validate(stages)

    def test_multiple_search_terms_same_type(self):
        """Should allow multiple search terms of same type in stage."""
        parser = QueryParser()
        query = [['type=task', 'label~open', 'label~p0']]

        stages = parser.parse(query)
        parser.validate(stages)


class TestGraphTermValidation:
    """Tests for graph term validation."""

    def test_valid_graph_terms(self):
        """Should accept valid graph terms."""
        parser = QueryParser()
        queries = [
            [['down_dependencies']],
            [['up_dependencies']],
            [['parent']],
            [['children']]
        ]

        for query in queries:
            stages = parser.parse(query)
            parser.validate(stages)

    def test_invalid_graph_term_raises_error(self):
        """Should reject invalid graph term names."""
        parser = QueryParser()
        query = [['invalid_term']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Unknown term"):
            parser.validate(stages)


class TestStagePurityEnforcement:
    """Tests for stage purity (no mixing search and graph terms)."""

    def test_pure_search_stage(self):
        """Should accept stage with only search terms."""
        parser = QueryParser()
        query = [['type=epic', 'label~beta', 'title~test']]

        stages = parser.parse(query)
        parser.validate(stages)

    def test_pure_graph_stage(self):
        """Should accept stage with only graph terms."""
        parser = QueryParser()
        query = [['children']]

        stages = parser.parse(query)
        parser.validate(stages)

    def test_mixed_stage_raises_error(self):
        """Should reject stage mixing search and graph terms."""
        parser = QueryParser()
        query = [['type=epic', 'children']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError, match="Cannot mix search and graph terms"):
            parser.validate(stages)

    def test_multiple_stages_different_types(self):
        """Should allow different stage types in different stages."""
        parser = QueryParser()
        query = [
            ['type=epic', 'label~beta'],
            ['children'],
            ['label~open']
        ]

        stages = parser.parse(query)
        parser.validate(stages)


class TestPRDExampleQueries:
    """Tests for example queries from PRD."""

    def test_open_beta_work_items(self):
        """Should validate open_beta_work_items query from PRD."""
        parser = QueryParser()
        query = [
            ['type=epic', 'label~(?i)(beta|preview)'],
            ['children'],
            ['label~(?i)(open|in progress)']
        ]

        stages = parser.parse_and_validate(query)

        assert len(stages) == 3
        assert stages[0] == ['type=epic', 'label~(?i)(beta|preview)']
        assert stages[1] == ['children']
        assert stages[2] == ['label~(?i)(open|in progress)']

    def test_non_beta_items(self):
        """Should validate non_beta_items query from PRD."""
        parser = QueryParser()
        query = [
            ['label~^(?!.*beta).*']
        ]

        stages = parser.parse_and_validate(query)

        assert len(stages) == 1
        assert stages[0] == ['label~^(?!.*beta).*']

    def test_open_non_preview_tasks(self):
        """Should validate open_non_preview_tasks query from PRD."""
        parser = QueryParser()
        query = [
            ['type=task', 'label~^(?!.*preview).*', 'label~(?i)(open|in progress)']
        ]

        stages = parser.parse_and_validate(query)

        assert len(stages) == 1
        assert stages[0] == ['type=task', 'label~^(?!.*preview).*', 'label~(?i)(open|in progress)']


class TestParseAndValidate:
    """Tests for combined parse_and_validate method."""

    def test_parse_and_validate_valid_query(self):
        """Should parse and validate in one step."""
        parser = QueryParser()
        query = [['type=epic', 'label~beta']]

        stages = parser.parse_and_validate(query)

        assert len(stages) == 1
        assert stages[0] == ['type=epic', 'label~beta']

    def test_parse_and_validate_invalid_query(self):
        """Should raise error on invalid query."""
        parser = QueryParser()
        query = [['type=invalid']]

        with pytest.raises(QueryValidationError):
            parser.parse_and_validate(query)

    def test_parse_and_validate_yaml_string(self):
        """Should parse and validate YAML string."""
        parser = QueryParser()
        yaml_query = """
        - ['type=task', 'label~open']
        - ['parent']
        """

        stages = parser.parse_and_validate(yaml_query)

        assert len(stages) == 2


class TestRegexPatterns:
    """Tests for specific regex patterns."""

    def test_case_insensitive_flag(self):
        """Should accept case insensitive regex flag."""
        parser = QueryParser()
        query = [['label~(?i)beta']]

        stages = parser.parse_and_validate(query)
        assert stages[0] == ['label~(?i)beta']

    def test_negative_lookahead(self):
        """Should accept negative lookahead patterns."""
        parser = QueryParser()
        query = [['label~^(?!.*closed).*']]

        stages = parser.parse_and_validate(query)
        assert stages[0] == ['label~^(?!.*closed).*']

    def test_alternation_or_pattern(self):
        """Should accept alternation (OR) patterns."""
        parser = QueryParser()
        query = [['label~beta|alpha|preview']]

        stages = parser.parse_and_validate(query)
        assert stages[0] == ['label~beta|alpha|preview']

    def test_complex_regex_patterns(self):
        """Should accept complex regex patterns."""
        parser = QueryParser()
        queries = [
            [['label~^(?!.*(closed|done)).*']],
            [['title~(?i)^(task|epic):']],
            [['label~p[0-4]']]
        ]

        for query in queries:
            stages = parser.parse_and_validate(query)
            assert len(stages) > 0


class TestErrorMessages:
    """Tests for clear error messages."""

    def test_stage_mixing_error_message(self):
        """Should provide clear error for mixing stage types."""
        parser = QueryParser()
        query = [['type=epic', 'children']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)

        assert "Cannot mix search and graph terms" in str(exc_info.value)
        assert "Stage 0" in str(exc_info.value)

    def test_invalid_type_error_message(self):
        """Should provide clear error for invalid type."""
        parser = QueryParser()
        query = [['type=invalid']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)

        assert "Invalid type" in str(exc_info.value)
        assert "epic" in str(exc_info.value)
        assert "task" in str(exc_info.value)
        assert "subtask" in str(exc_info.value)

    def test_unknown_term_error_message(self):
        """Should provide clear error for unknown terms."""
        parser = QueryParser()
        query = [['unknown_term']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)

        assert "Unknown term" in str(exc_info.value)
        assert "unknown_term" in str(exc_info.value)

    def test_invalid_regex_error_message(self):
        """Should provide clear error for invalid regex."""
        parser = QueryParser()
        query = [['label~[unclosed']]

        stages = parser.parse(query)
        with pytest.raises(QueryValidationError) as exc_info:
            parser.validate(stages)

        assert "Invalid regex pattern" in str(exc_info.value)
        assert "label~" in str(exc_info.value)
