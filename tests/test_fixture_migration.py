"""
Tests to verify fixture migration completeness.

Validates that migrated test files use centralized fixtures from conftest.py
instead of local fixture definitions. This ensures consistency and prevents
duplication of fixture code.
"""

import ast
import pytest
from pathlib import Path


# List of test files that should use centralized fixtures
MIGRATED_TEST_FILES = [
    "tests/test_paths.py",
    "tests/test_ticket_factory_hive.py",
    "tests/test_pipeline.py",
    "tests/test_generate_demo_tickets.py",
]

# Allowed local fixtures that build on centralized fixtures
# These are test-specific fixtures that compose centralized fixtures
ALLOWED_LOCAL_FIXTURES = {
    "tests/test_pipeline.py": ["pipeline"],  # Builds on isolated_bees_env
    "tests/test_generate_demo_tickets.py": ["generated_tickets"],  # Builds on isolated_bees_env
}


class FixtureDefinitionVisitor(ast.NodeVisitor):
    """AST visitor to find pytest fixture definitions in a test file."""
    
    def __init__(self):
        self.fixtures = []
    
    def visit_FunctionDef(self, node):
        """Check if function is decorated with @pytest.fixture."""
        for decorator in node.decorator_list:
            # Handle both @pytest.fixture and @pytest.fixture(...)
            if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                self.fixtures.append(node.name)
            elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                self.fixtures.append(node.name)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name) and decorator.func.id == "fixture":
                    self.fixtures.append(node.name)
                elif isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                    self.fixtures.append(node.name)
        self.generic_visit(node)


class TestFixtureMigration:
    """Tests for fixture migration validation."""
    
    @pytest.mark.parametrize("test_file", MIGRATED_TEST_FILES)
    def test_no_local_fixtures_in_migrated_files(self, test_file):
        """Verify migrated test files have no disallowed local fixture definitions."""
        file_path = Path(test_file)
        
        # Read and parse the file
        with open(file_path, 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        visitor = FixtureDefinitionVisitor()
        visitor.visit(tree)
        
        # Check for disallowed fixtures
        allowed_fixtures = ALLOWED_LOCAL_FIXTURES.get(test_file, [])
        disallowed_fixtures = [f for f in visitor.fixtures if f not in allowed_fixtures]
        
        # Should have no disallowed fixture definitions
        assert len(disallowed_fixtures) == 0, (
            f"{test_file} contains disallowed local fixture definitions: {disallowed_fixtures}. "
            f"All fixtures should be imported from conftest.py or listed in ALLOWED_LOCAL_FIXTURES."
        )
    
    def test_conftest_has_required_fixtures(self):
        """Verify conftest.py provides the expected centralized fixtures."""
        conftest_path = Path("tests/conftest.py")
        
        with open(conftest_path, 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        visitor = FixtureDefinitionVisitor()
        visitor.visit(tree)
        
        # Required fixtures that should exist in conftest.py
        required_fixtures = [
            "bees_repo",
            "single_hive",
            "multi_hive",
            "hive_with_tickets",
            "isolated_bees_env",
            "repo_root_ctx",
            "mock_mcp_context",
        ]
        
        for fixture_name in required_fixtures:
            assert fixture_name in visitor.fixtures, (
                f"Required fixture '{fixture_name}' not found in conftest.py"
            )
    
    def test_migrated_files_import_from_conftest(self):
        """Verify migrated files don't explicitly import fixture definitions."""
        # This test checks that migrated files don't have imports like:
        # from .conftest import fixture_name
        # (which would be redundant since pytest auto-discovers fixtures)
        
        for test_file in MIGRATED_TEST_FILES:
            file_path = Path(test_file)
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Check for explicit fixture imports from conftest
            # (these would be redundant and indicate potential confusion)
            assert "from conftest import" not in content, (
                f"{test_file} explicitly imports from conftest. "
                f"Fixtures are auto-discovered by pytest; explicit imports are unnecessary."
            )
            assert "from .conftest import" not in content, (
                f"{test_file} explicitly imports from conftest. "
                f"Fixtures are auto-discovered by pytest; explicit imports are unnecessary."
            )
    
    @pytest.mark.parametrize("test_file", MIGRATED_TEST_FILES)
    def test_migrated_files_use_fixture_parameters(self, test_file):
        """Verify migrated files use fixture parameters in test functions."""
        file_path = Path(test_file)
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Look for test functions or fixtures that use centralized fixtures
        has_fixture_usage = False
        expected_fixtures = {
            "single_hive", "multi_hive", "hive_with_tickets", 
            "isolated_bees_env", "bees_repo"
        }
        # Also check for allowed local fixtures
        allowed_local = ALLOWED_LOCAL_FIXTURES.get(test_file, [])
        all_expected = expected_fixtures | set(allowed_local)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check test functions or fixture definitions
                if node.name.startswith("test_") or node.name in allowed_local:
                    # Check if any parameters match expected fixtures
                    for arg in node.args.args:
                        if arg.arg in expected_fixtures:
                            has_fixture_usage = True
                            break
                if has_fixture_usage:
                    break
        
        # Each migrated file should use at least one centralized fixture
        assert has_fixture_usage, (
            f"{test_file} doesn't use any centralized fixtures. "
            f"Expected usage of: {expected_fixtures}"
        )


class TestFixtureEdgeCases:
    """Test edge cases in fixture usage patterns."""
    
    def test_isolated_bees_env_usage(self):
        """Verify isolated_bees_env is used correctly in migrated files."""
        # test_pipeline.py and test_generate_demo_tickets.py should use isolated_bees_env
        files_using_isolated_env = [
            "tests/test_pipeline.py",
            "tests/test_generate_demo_tickets.py",
        ]
        
        for test_file in files_using_isolated_env:
            file_path = Path(test_file)
            
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Should reference isolated_bees_env
            assert "isolated_bees_env" in content, (
                f"{test_file} should use isolated_bees_env fixture for complex setup"
            )
    
    def test_single_and_multi_hive_usage(self):
        """Verify single_hive and multi_hive fixtures are used appropriately."""
        # test_paths.py should use multi_hive (needs backend and frontend)
        paths_file = Path("tests/test_paths.py")
        with open(paths_file, 'r') as f:
            content = f.read()
        assert "multi_hive" in content, "test_paths.py should use multi_hive fixture"
        
        # test_ticket_factory_hive.py should use both single_hive and multi_hive
        factory_file = Path("tests/test_ticket_factory_hive.py")
        with open(factory_file, 'r') as f:
            content = f.read()
        assert "single_hive" in content or "multi_hive" in content, (
            "test_ticket_factory_hive.py should use single_hive or multi_hive fixtures"
        )
