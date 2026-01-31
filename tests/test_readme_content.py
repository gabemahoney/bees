"""Unit tests for README.md content validation.

Ensures README.md remains focused on user-facing features and doesn't
contain implementation details like threading, algorithms, or performance
characteristics.
"""

import pytest
import re
from pathlib import Path


class TestReadmeContent:
    """Tests to prevent implementation details from appearing in README."""

    @pytest.fixture
    def readme_path(self):
        """Get path to README.md in project root."""
        return Path(__file__).parent.parent / "README.md"

    @pytest.fixture
    def readme_content(self, readme_path):
        """Read README.md content."""
        return readme_path.read_text()

    def test_no_threading_details(self, readme_content):
        """README should not contain threading implementation details."""
        forbidden_patterns = [
            r'\bthreading\b',
            r'\bTimer\b',
            r'\bthread\s+safety\b',
            r'\bdaemon\s+thread\b',
            r'\bthread\s+pool\b',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            assert not matches, (
                f"Found threading implementation detail in README: {pattern}\n"
                f"Matches: {matches}\n"
                f"README should focus on user-facing features, not implementation."
            )

    def test_no_algorithm_details(self, readme_content):
        """README should not contain algorithm implementation details."""
        forbidden_patterns = [
            r'\bDFS\b',
            r'\bdepth-first\s+search\b',
            r'\bbreadth-first\s+search\b',
            r'\bBFS\b',
            r'\bgraph\s+traversal\b',
            r'\btopological\s+sort\b',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            assert not matches, (
                f"Found algorithm implementation detail in README: {pattern}\n"
                f"Matches: {matches}\n"
                f"README should focus on user-facing features, not algorithms."
            )

    def test_no_performance_sections(self, readme_content):
        """README should not contain performance/optimization sections."""
        forbidden_patterns = [
            r'\btime\s+complexity\b',
            r'\bO\([n2log]\)',  # Big-O notation
            r'\bperformance\s+characteristics\b',
            r'\boptimization\s+strategy\b',
            r'\bfile\s+locking\s+overhead\b',
            r'\bcache\s+invalidation\b',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            assert not matches, (
                f"Found performance detail in README: {pattern}\n"
                f"Matches: {matches}\n"
                f"README should focus on user-facing features, not performance."
            )

    def test_no_debouncing_details(self, readme_content):
        """README should not explain debouncing implementation."""
        forbidden_patterns = [
            r'\bdebouncing\b',
            r'\bdebounce\s+timer\b',
            r'\btimer\s+cancellation\b',
            r'\btimer\s+reset\b',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            assert not matches, (
                f"Found debouncing implementation detail in README: {pattern}\n"
                f"Matches: {matches}\n"
                f"README should focus on user-facing features, not debouncing."
            )

    def test_no_type_inference_details(self, readme_content):
        """README should not explain type inference optimization."""
        forbidden_patterns = [
            r'\btype\s+inference\s+optimization\b',
            r'\bmarkdown\s+parsing\s+optimization\b',
            r'\blightweight\s+type\s+inference\b',
        ]

        for pattern in forbidden_patterns:
            matches = re.findall(pattern, readme_content, re.IGNORECASE)
            assert not matches, (
                f"Found type inference detail in README: {pattern}\n"
                f"Matches: {matches}\n"
                f"README should focus on user-facing features."
            )

    def test_no_implementation_details_section(self, readme_content):
        """README should not have 'Implementation Details' sections."""
        forbidden_headings = [
            r'^#+\s*Implementation\s+Details\s*$',
            r'^#+\s*Technical\s+Implementation\s*$',
            r'^#+\s*Internal\s+Architecture\s*$',
        ]

        lines = readme_content.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern in forbidden_headings:
                if re.match(pattern, line, re.IGNORECASE):
                    pytest.fail(
                        f"Found implementation section heading at line {line_num}: '{line}'\n"
                        f"README should focus on user-facing features, not implementation."
                    )

    def test_readme_has_required_sections(self, readme_content):
        """README should have key user-facing sections."""
        required_sections = [
            r'^#+\s*Overview\s*$',
            r'^#+\s*Installation\s*$',
            r'^#+\s*Usage\s*$',
        ]

        lines = readme_content.split('\n')
        for pattern in required_sections:
            found = any(re.match(pattern, line, re.IGNORECASE) for line in lines)
            assert found, (
                f"README is missing required section: {pattern}\n"
                f"README should have clear user-facing documentation."
            )
