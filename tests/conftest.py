"""Pytest configuration and fixtures for Bees tests."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from src.repo_context import repo_root_context


@pytest.fixture(autouse=True)
def mock_git_repo_check(request, monkeypatch):
    """
    Mock git repository check and auto-inject repo_root for all tests.

    Tests create temp directories that aren't git repos, but the new
    repo_root parameter validation checks for .git directories.
    This fixture mocks get_repo_root_from_path to return the current
    working directory as if it were a valid git repo.

    Also patches config functions to use Path.cwd() as default repo_root,
    since tests don't have MCP context and should use their tmp_path.

    Tests that need real git validation can use the marker:
        @pytest.mark.needs_real_git_check
    """
    # Skip mocking for tests that need real git validation
    if 'needs_real_git_check' in request.keywords:
        return

    def mock_get_repo_root(start_path: Path) -> Path:
        """Walk up from start_path to find a directory containing .git or .bees, or return cwd."""
        current = start_path.resolve()

        # Walk up looking for .git or .bees directory
        while current != current.parent:
            if (current / '.git').exists() or (current / '.bees').exists():
                return current
            current = current.parent

        # Check root directory
        if (current / '.git').exists() or (current / '.bees').exists():
            return current

        # If no .git or .bees found, assume current working directory is the repo root
        # This handles test cases where we create subdirectories but haven't created .git yet
        return Path.cwd().resolve()

    # Patch both mcp_repo_utils and mcp_server
    # Both patches are required because Python creates name bindings at import time
    # mcp_server.py:32 does: from .mcp_repo_utils import get_repo_root_from_path
    # This creates a local name binding to the original function in mcp_server's namespace
    # Patching only mcp_repo_utils doesn't affect already-imported names in mcp_server
    monkeypatch.setattr(
        "src.mcp_repo_utils.get_repo_root_from_path",
        mock_get_repo_root
    )
    monkeypatch.setattr(
        "src.mcp_server.get_repo_root_from_path",
        mock_get_repo_root
    )
    monkeypatch.setattr(
        "src.mcp_ticket_ops.get_repo_root_from_path",
        mock_get_repo_root
    )

    # Patch get_config_path and ensure_bees_dir to use Path.cwd() when repo_root is None
    from src.config import get_config_path as original_get_config_path
    from src.config import ensure_bees_dir as original_ensure_bees_dir
    from src.config import BEES_CONFIG_DIR, BEES_CONFIG_FILENAME

    def patched_get_config_path(repo_root: Path | None = None) -> Path:
        if repo_root is None:
            repo_root = Path.cwd()
        return repo_root / BEES_CONFIG_DIR / BEES_CONFIG_FILENAME

    def patched_ensure_bees_dir(repo_root: Path | None = None) -> None:
        if repo_root is None:
            repo_root = Path.cwd()
        bees_dir = repo_root / BEES_CONFIG_DIR
        bees_dir.mkdir(exist_ok=True)

    # Patch both in src.config and any places that might have imported it
    import src.config
    monkeypatch.setattr(src.config, "get_config_path", patched_get_config_path)
    monkeypatch.setattr(src.config, "ensure_bees_dir", patched_ensure_bees_dir)


@pytest.fixture(autouse=True)
def set_repo_root_context(request):
    """
    Automatically set repo_root context for all tests.
    
    Uses Path.cwd() as the repo root, which is typically a tmp_path in tests.
    This fixture ensures that functions using get_repo_root() from context
    work correctly in tests without manually wrapping each test.
    
    Tests can skip this fixture using the marker:
        @pytest.mark.no_repo_context
    """
    # Skip for tests that don't want automatic context
    if 'no_repo_context' in request.keywords:
        yield  # Must yield even when skipping
        return
    
    # Set context to current working directory (which is tmp_path in most tests)
    with repo_root_context(Path.cwd()):
        yield


@pytest.fixture
def isolated_bees_env(tmp_path, monkeypatch):
    """
    Create an isolated Bees environment for testing.
    
    Sets up:
    - Changes to tmp_path directory
    - Creates .bees/ directory
    - Returns helper object for creating hives and config
    """
    monkeypatch.chdir(tmp_path)
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir()
    
    class BeesTestHelper:
        def __init__(self, base_path):
            self.base_path = base_path
            self.hives = {}
            
        def create_hive(self, hive_name: str, display_name: str | None = None):
            """Create a hive directory and register it."""
            hive_dir = self.base_path / hive_name
            hive_dir.mkdir(exist_ok=True)
            self.hives[hive_name] = {
                "path": str(hive_dir),
                "display_name": display_name or hive_name.title()
            }
            return hive_dir
            
        def write_config(self):
            """Write .bees/config.json with registered hives."""
            config = {
                "hives": self.hives,
                "allow_cross_hive_dependencies": False,
                "schema_version": "1.0"
            }
            config_path = self.base_path / ".bees" / "config.json"
            config_path.write_text(json.dumps(config, indent=2))
            
        def create_ticket(self, hive_dir: Path, ticket_id: str, ticket_type: str, 
                         title: str, status: str = "open", **extra_fields):
            """Create a ticket file with proper structure."""
            frontmatter = {
                "id": ticket_id,
                "type": ticket_type,
                "title": title,
                "status": status,
                "bees_version": "1.1",
                "created_at": "2026-01-30T10:00:00",
                "updated_at": "2026-01-30T10:00:00",
                **extra_fields
            }
            
            yaml_lines = ["---"]
            for key, value in frontmatter.items():
                if isinstance(value, str):
                    yaml_lines.append(f"{key}: '{value}'" if ':' in value or value.startswith("'") else f"{key}: {value}")
                else:
                    yaml_lines.append(f"{key}: {value}")
            yaml_lines.append("---")
            yaml_lines.append("")
            yaml_lines.append(f"{title} body content.")
            
            ticket_file = hive_dir / f"{ticket_id}.md"
            ticket_file.write_text('\n'.join(yaml_lines))
            return ticket_file
    
    helper = BeesTestHelper(tmp_path)
    yield helper

    # Optional: cleanup happens automatically with tmp_path


@pytest.fixture
def repo_root_ctx(tmp_path):
    """
    Pytest fixture for setting up repo_root context in tests.
    
    This fixture:
    1. Creates a temporary git repo structure using tmp_path
    2. Sets up repo_root_context with the tmp_path
    3. Yields tmp_path for test use
    4. Automatically cleans up context after test
    
    Usage:
        def test_something(repo_root_ctx):
            # repo_root is now set in context to tmp_path
            # Functions can call get_repo_root() successfully
            result = some_function()  # This can use get_repo_root()
            assert result is not None
            
    The tmp_path is a temporary directory that is unique to each test
    and is automatically cleaned up after the test completes.
    """
    # Create .bees directory to mark this as a bees repo
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir(exist_ok=True)
    
    # Set up context with tmp_path as repo_root
    with repo_root_context(tmp_path):
        yield tmp_path
    # Context is automatically cleaned up after yield


@pytest.fixture
def mock_mcp_context(tmp_path):
    """
    Create a mock MCP Context that returns tmp_path as the repo root.

    This is used for testing MCP functions that require a ctx parameter.
    The mock context's list_roots() method returns the tmp_path directory.
    """
    from unittest.mock import Mock

    def create_mock_context(repo_path=None):
        """Create a mock context for the given repo path (defaults to tmp_path)."""
        if repo_path is None:
            repo_path = tmp_path

        ctx = Mock()
        mock_root = Mock()
        mock_root.uri = f"file://{repo_path}"

        # Mock the async list_roots method
        async def mock_list_roots():
            return [mock_root]

        ctx.list_roots = mock_list_roots
        return ctx

    return create_mock_context
