"""
Pytest configuration and fixtures for Bees tests.

FIXTURE OVERVIEW
================

This module provides fixtures for testing the Bees ticket management system.
Fixtures are organized into three categories: autouse, opt-in context, and
test data builders.

Autouse Fixtures (Apply to All Tests)
--------------------------------------
These fixtures run automatically for every test unless explicitly opted out:

1. backup_project_config (session scope)
   - Backs up .bees/config.json before tests, restores after
   - Prevents test pollution of development environment
   - Session-scoped: runs once per pytest session

2. mock_git_repo_check (function scope)
   - Mocks git repo validation to accept tmp_path directories
   - Patches get_repo_root_from_path() and config functions
   - Opt-out: @pytest.mark.needs_real_git_check

3. set_repo_root_context (function scope)
   - Sets repo_root context to Path.cwd() for all tests
   - Enables get_repo_root() calls in production code
   - Opt-out: @pytest.mark.no_repo_context

Opt-In Context Fixtures
------------------------
Use these when you need explicit control over context or MCP mocking:

4. repo_root_ctx
   - Sets context to tmp_path (not Path.cwd())
   - Use when you need specific path without chdir
   - Creates .bees directory automatically

5. mock_mcp_context
   - Factory for creating mock MCP Context objects
   - Returns create_mock_context(repo_path=None) function
   - Use for testing MCP tool functions (_create_ticket, etc.)

6. isolated_bees_env
   - Complete isolated environment with BeesTestHelper
   - Changes to tmp_path, creates .bees, returns helper
   - Helper methods: create_hive(), write_config(), create_ticket()
   - Use for integration tests with complex setup

Test Data Builder Fixtures
---------------------------
These fixtures create pre-configured test scenarios:

7. bees_repo
   - Minimal setup: tmp_path with .bees directory
   - Foundation for single_hive, multi_hive, etc.

8. single_hive
   - Builds on bees_repo
   - Creates one hive ("backend") with config
   - Returns (repo_root, hive_path)

9. multi_hive
   - Builds on bees_repo
   - Creates two hives ("backend", "frontend") with config
   - Returns (repo_root, backend_path, frontend_path)

10. hive_with_tickets
    - Builds on single_hive
    - Creates Epic → Task → Subtask hierarchy
    - Returns (repo_root, hive_path, epic_id, task_id, subtask_id)

FIXTURE RELATIONSHIPS
=====================

Dependency Hierarchy:
    tmp_path (pytest built-in)
        │
        ├─→ bees_repo
        │   ├─→ single_hive
        │   │   └─→ hive_with_tickets
        │   └─→ multi_hive
        │
        ├─→ repo_root_ctx
        ├─→ mock_mcp_context
        └─→ isolated_bees_env

Autouse fixtures work alongside any of these fixtures.

QUICK START GUIDE
=================

Simple Unit Test (Uses Autouse Fixtures Only)
----------------------------------------------
def test_create_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()
    
    # Autouse fixtures provide context and mock git validation
    create_config()  # Works! Context is set to Path.cwd()
    assert (tmp_path / ".bees" / "config.json").exists()

Integration Test with Isolated Environment
-------------------------------------------
def test_query_across_hives(isolated_bees_env):
    helper = isolated_bees_env
    
    backend = helper.create_hive("backend")
    frontend = helper.create_hive("frontend")
    helper.write_config()
    
    helper.create_ticket(backend, "backend.bees-abc", "epic", "Epic")
    
    results = execute_query("all_epics")
    assert len(results) == 1

Testing MCP Functions
----------------------
async def test_mcp_create_ticket(mock_mcp_context, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()
    
    ctx = mock_mcp_context()  # Creates mock Context
    
    result = await _create_ticket(
        ctx=ctx,
        ticket_type="epic",
        title="Test",
        hive_name="backend"
    )
    assert result["status"] == "success"

Testing Core Functions with Explicit Context
---------------------------------------------
def test_with_explicit_context(repo_root_ctx):
    # Context is set to tmp_path (from fixture)
    config_path = get_config_path()
    assert config_path == repo_root_ctx / ".bees" / "config.json"

Pre-Built Test Scenario
------------------------
def test_ticket_relationships(hive_with_tickets):
    repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
    
    # Epic → Task → Subtask hierarchy already created
    epic = show_ticket(epic_id)
    assert task_id in epic["children"]

DECISION TREE: CHOOSING THE RIGHT FIXTURE
==========================================

Question 1: What are you testing?
    ├─ MCP tool function (_create_ticket, _show_ticket, etc.)
    │  └─→ Use: mock_mcp_context
    │
    ├─ Core function (create_epic, get_config_path, etc.)
    │  ├─ Need custom environment setup?
    │  │  └─→ Use: isolated_bees_env (for complex scenarios)
    │  └─ Simple test?
    │     └─→ Use: tmp_path + monkeypatch.chdir (autouse handles rest)
    │
    └─ Testing ticket operations/queries?
       ├─ Need pre-existing tickets?
       │  └─→ Use: hive_with_tickets (or single_hive + manual tickets)
       └─ Need multiple hives?
          └─→ Use: multi_hive

Question 2: Do you need to override autouse fixtures?
    ├─ Need real git validation?
    │  └─→ Add: @pytest.mark.needs_real_git_check
    │
    └─ Need to control context manually?
       └─→ Add: @pytest.mark.no_repo_context + repo_root_ctx

Question 3: What's the simplest fixture for your needs?
    Always prefer simpler fixtures:
    - tmp_path + autouse > repo_root_ctx
    - single_hive > isolated_bees_env
    - Pre-built fixtures > manual setup
"""

import json
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch
from src.repo_context import repo_root_context


@pytest.fixture(scope="session", autouse=True)
def backup_project_config():
    """
    Backup and restore the project's .bees/config.json to prevent test pollution.
    
    Purpose:
        Ensures the actual project's config.json is preserved during test runs.
        Without this, tests that modify config (e.g., colonize_hive tests) would
        corrupt the development environment's hive registry.
    
    Scope & Behavior:
        - Session-scoped: Runs once at test session start/end
        - Autouse: Applies to all tests automatically (no explicit declaration needed)
        - Backs up .bees/config.json before any tests run
        - Restores original config after all tests complete
    
    When This Matters:
        - Tests that call colonize_hive() or modify .bees/config.json
        - Running pytest from within the actual bees project directory
        - Development workflow where you're actively using bees to track tasks
    
    Usage Example:
        # No explicit usage needed - this fixture is autouse
        def test_colonize_hive(tmp_path):
            # This test modifies config, but backup_project_config
            # ensures the real project config is restored afterward
            colonize_hive("test_hive", str(tmp_path / "hive"))
    
    Note:
        Most tests run in isolated tmp_path environments and won't affect the
        project config. This is a safety net for integration tests or accidental
        mutations to the real project state.
    """
    project_root = Path(__file__).parent.parent
    config_path = project_root / ".bees" / "config.json"
    backup_path = project_root / ".bees" / "config.json.test_backup"
    
    # Backup if config exists
    if config_path.exists():
        shutil.copy2(config_path, backup_path)
    
    yield
    
    # Restore from backup
    if backup_path.exists():
        shutil.copy2(backup_path, config_path)
        backup_path.unlink()


@pytest.fixture(autouse=True)
def mock_git_repo_check(request, monkeypatch):
    """
    Mock git repository detection to allow tests in non-git temporary directories.
    
    Purpose:
        Production code validates repo_root by checking for .git directories.
        Tests run in temporary directories (tmp_path) that aren't git repos.
        This fixture mocks get_repo_root_from_path() to treat tmp_path as valid.
    
    What Gets Mocked:
        1. get_repo_root_from_path() - Returns path with .git/.bees or falls back to cwd
        2. get_config_path() - Uses Path.cwd() when repo_root is None
        3. ensure_bees_dir() - Uses Path.cwd() when repo_root is None
    
    Why Multiple Patches Are Needed:
        Python creates name bindings at import time. When mcp_server.py does:
            from .mcp_repo_utils import get_repo_root_from_path
        
        It creates a local binding in mcp_server's namespace. Patching only
        mcp_repo_utils won't affect the already-imported name in mcp_server.
        
        We must patch all 4 import locations:
        - src.mcp_repo_utils.get_repo_root_from_path
        - src.mcp_server.get_repo_root_from_path
        - src.mcp_ticket_ops.get_repo_root_from_path
        - src.mcp_query_ops.get_repo_root_from_path
    
    Interaction with set_repo_root_context:
        This fixture mocks the repo detection logic, while set_repo_root_context
        sets the contextvars for get_repo_root(). They work together:
        - mock_git_repo_check: Makes validation functions accept tmp_path
        - set_repo_root_context: Provides context for get_repo_root() calls
    
    Using @pytest.mark.needs_real_git_check Marker:
        Tests that require real git repository checks can opt-out of mocking by using
        the @pytest.mark.needs_real_git_check decorator. This is useful when:
        - Testing actual git repository detection logic
        - Verifying behavior that depends on real .git directory structure
        - Integration testing with real git commands
        
        Example:
            @pytest.mark.needs_real_git_check
            def test_requires_real_git():
                # This test will use actual get_repo_root_from_path logic
                # The mock_git_repo_check fixture skips patching for this test
                result = get_repo_root_from_path(Path.cwd())
                assert (result / '.git').exists()
        
        When the marker is present:
        - All git-related mocking is skipped (get_repo_root_from_path, config functions)
        - Test runs against real filesystem and git validation
        - Test will fail if not run in a git repository
        
        When to use this marker:
        - Testing get_repo_root_from_path() function itself
        - Testing error handling for non-git directories
        - Integration tests that interact with real git repos
    
    Usage Example:
        # No explicit usage needed - this fixture is autouse
        def test_colonize_hive(tmp_path):
            # tmp_path has no .git directory, but mock allows it
            colonize_hive("backend", str(tmp_path / "backend"))
            # Without this mock, colonize_hive would reject tmp_path
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
    monkeypatch.setattr(
        "src.mcp_query_ops.get_repo_root_from_path",
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
    Automatically set repo_root context for all tests using contextvars.
    
    Purpose:
        Many core functions call get_repo_root() from src.repo_context to access
        the repository root. Tests need this context set, but manually wrapping
        every test with repo_root_context() is verbose and error-prone.
        
        This autouse fixture automatically sets the context to Path.cwd() for
        all tests, enabling seamless use of context-dependent functions.
    
    What It Does:
        - Sets repo_root_context to Path.cwd() (typically a tmp_path in tests)
        - Wraps the entire test in a context manager
        - Automatically cleans up context after test completes
    
    Interaction with mock_git_repo_check:
        These two autouse fixtures work together to make tests seamless:
        - mock_git_repo_check: Mocks validation to accept non-git directories
        - set_repo_root_context: Provides context for get_repo_root() calls
        
        Together they allow tests to call production code that both validates
        repo_root and retrieves it from context, without manual setup.
    
    Opt-Out with Marker:
        Tests that need to manage context manually (e.g., testing context behavior):
        
        @pytest.mark.no_repo_context
        def test_context_behavior():
            # This test manages repo_root_context manually
            with repo_root_context(some_path):
                assert get_repo_root() == some_path
            # Outside context, get_repo_root() raises RuntimeError
    
    Usage Example:
        # No explicit usage needed - this fixture is autouse
        def test_create_ticket(tmp_path, monkeypatch):
            monkeypatch.chdir(tmp_path)
            # Context is already set to Path.cwd() == tmp_path
            ticket_id = create_epic("Test Epic", hive_name="backend")
            # create_epic internally calls get_repo_root() and it works!
    
    Common Pattern:
        Most tests combine this with monkeypatch.chdir(tmp_path):
        
        def test_something(tmp_path, monkeypatch):
            monkeypatch.chdir(tmp_path)  # Sets cwd to tmp_path
            # set_repo_root_context uses Path.cwd(), so context = tmp_path
            result = some_function()  # Can safely call get_repo_root()
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
    Create isolated Bees environment with helper for building test scenarios.
    
    Purpose:
        Provides a complete, isolated Bees environment with a helper object
        that simplifies creating hives, config, and tickets for integration tests.
        
        Use this for tests that need full environment setup: multiple hives,
        complex ticket hierarchies, or testing cross-hive operations.
    
    What It Provides:
        1. Changes cwd to tmp_path (isolated from project)
        2. Creates .bees/ directory
        3. Returns BeesTestHelper with methods for building test data
    
    BeesTestHelper Methods:
        
        create_hive(hive_name: str, display_name: str | None = None) -> Path
            - Creates hive directory at base_path / hive_name
            - Registers hive in internal registry (call write_config() after)
            - Returns Path to hive directory
            - Example: hive_dir = helper.create_hive("backend", "Backend")
        
        write_config() -> None
            - Writes .bees/config.json with all registered hives
            - Call after creating all hives
            - Sets allow_cross_hive_dependencies=False by default
            - Example: helper.write_config()
        
        create_ticket(hive_dir: Path, ticket_id: str, ticket_type: str,
                     title: str, status: str = "open", **extra_fields) -> Path
            - Creates ticket markdown file with YAML frontmatter
            - Writes to hive_dir / "{ticket_id}.md"
            - Returns Path to created ticket file
            - Example: helper.create_ticket(hive_dir, "backend.bees-abc", 
                                           "epic", "Test Epic", parent=None)
    
    When to Use vs Other Fixtures:
        - repo_root_ctx: Simple tests needing context only
        - mock_mcp_context: Testing MCP functions with minimal setup
        - isolated_bees_env: Integration tests needing hives + tickets + config
        - single_hive/multi_hive: Prefer these for common scenarios (simpler)
    
    Directory Structure Created:
        tmp_path/
        ├── .bees/
        │   └── config.json      # Created by helper.write_config()
        ├── backend/              # Created by helper.create_hive("backend")
        │   └── backend.bees-abc.md  # Created by helper.create_ticket()
        └── frontend/             # Created by helper.create_hive("frontend")
    
    Complete Usage Example:
        def test_cross_hive_query(isolated_bees_env):
            helper = isolated_bees_env
            
            # Create hives
            backend_dir = helper.create_hive("backend", "Backend")
            frontend_dir = helper.create_hive("frontend", "Frontend")
            helper.write_config()
            
            # Create tickets
            helper.create_ticket(
                backend_dir, 
                "backend.bees-abc", 
                "epic", 
                "Backend Epic",
                status="open",
                children=[]
            )
            helper.create_ticket(
                frontend_dir,
                "frontend.bees-xyz",
                "task",
                "Frontend Task",
                parent="frontend.bees-001"
            )
            
            # Test query across hives
            results = execute_query("open_tickets")
            assert len(results) == 2
    
    Typical Workflow:
        1. helper.create_hive() for each hive (registers in memory)
        2. helper.write_config() to persist config.json
        3. helper.create_ticket() for each ticket needed
        4. Run test assertions
    
    Note:
        Cleanup happens automatically via tmp_path. No manual teardown needed.
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
    Opt-in fixture for explicitly managing repo_root context in tests.
    
    Purpose:
        Provides explicit control over repo_root context when you need to:
        - Override the autouse set_repo_root_context fixture
        - Use a specific path different from Path.cwd()
        - Test context behavior with controlled setup
    
    What It Provides:
        1. Creates .bees directory in tmp_path
        2. Sets repo_root_context to tmp_path (not Path.cwd())
        3. Yields tmp_path for test use
        4. Automatically cleans up context after test
    
    When to Use repo_root_ctx vs Autouse Fixtures:
        - Most tests: Use autouse fixtures (no explicit fixture needed)
        - Need specific path: Use repo_root_ctx when tmp_path != Path.cwd()
        - Override autouse: Use @pytest.mark.no_repo_context + repo_root_ctx
    
    Difference from set_repo_root_context (autouse):
        - set_repo_root_context: Uses Path.cwd() as repo_root (autouse)
        - repo_root_ctx: Uses tmp_path directly as repo_root (opt-in)
        
        This matters when you don't call monkeypatch.chdir(tmp_path).
    
    Usage Example:
        @pytest.mark.no_repo_context  # Disable autouse context
        def test_specific_context(repo_root_ctx):
            # Context is explicitly set to tmp_path (from fixture)
            # Not using Path.cwd(), using the tmp_path directly
            result = some_function()
            assert get_repo_root() == repo_root_ctx
    
    Typical Pattern (without opt-out):
        def test_simple_case(repo_root_ctx):
            # Both autouse and repo_root_ctx set context
            # repo_root_ctx wins because it's innermost
            # Context = tmp_path from this fixture
            config_path = get_config_path()
            assert config_path == repo_root_ctx / ".bees" / "config.json"
    
    Note:
        If you're using monkeypatch.chdir(tmp_path), the autouse fixture
        (set_repo_root_context) is sufficient. Use this fixture when you
        need explicit tmp_path context without changing cwd.
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
    Factory fixture for creating mock MCP Context objects for testing MCP tool functions.
    
    Purpose:
        MCP tool functions (in mcp_ticket_ops.py, mcp_query_ops.py) receive a
        ctx: Context parameter from FastMCP. This fixture creates mock Context
        objects that implement the MCP Roots protocol for testing.
    
    What It Provides:
        Returns a factory function: create_mock_context(repo_path=None)
        - repo_path: Optional path to use as repo root (defaults to tmp_path)
        - Returns: Mock Context object with list_roots() method
    
    Mock Context Behavior:
        ctx.list_roots() returns a list with one mock root:
        - root.uri = "file://{repo_path}"
        
        This allows resolve_repo_root(ctx) to extract repo_path from the URI.
    
    When to Use vs repo_root_ctx:
        - repo_root_ctx: Testing core functions (ticket_factory.py, config.py)
        - mock_mcp_context: Testing MCP tool functions (_create_ticket, _show_ticket)
        
        MCP functions need ctx parameter; core functions use get_repo_root().
    
    Difference from isolated_bees_env:
        - mock_mcp_context: Creates mock Context only (lightweight)
        - isolated_bees_env: Creates full environment + helper + chdir (heavyweight)
        
        Use mock_mcp_context when you just need ctx for MCP function calls.
    
    Usage Example:
        async def test_create_ticket_mcp(mock_mcp_context, tmp_path, monkeypatch):
            # Setup environment
            monkeypatch.chdir(tmp_path)
            (tmp_path / ".bees").mkdir()
            
            # Create mock context
            ctx = mock_mcp_context()  # Uses tmp_path by default
            
            # Call MCP tool function
            result = await _create_ticket(
                ctx=ctx,
                ticket_type="epic",
                title="Test Epic",
                hive_name="backend"
            )
            
            assert result["status"] == "success"
    
    Advanced Usage (Custom Path):
        def test_with_custom_path(mock_mcp_context, tmp_path):
            custom_path = tmp_path / "custom_repo"
            custom_path.mkdir()
            
            # Create context for custom path
            ctx = mock_mcp_context(repo_path=custom_path)
            
            # ctx.list_roots() will return custom_path
            result = await some_mcp_function(ctx)
    
    Factory Pattern:
        The fixture returns a factory function, not a Context object.
        Call it to create Context instances:
        
        ctx1 = mock_mcp_context()           # Uses tmp_path
        ctx2 = mock_mcp_context(other_path) # Uses other_path
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


@pytest.fixture(scope="function")
def bees_repo(tmp_path):
    """
    Base fixture for all test scenarios - creates minimal bees repository structure.
    
    Creates:
    - Temporary directory with .bees/ subdirectory
    - Yields the repo root Path object
    - Cleans up temp directory after test (automatic via tmp_path)
    
    This is the foundation fixture used by single_hive, multi_hive, and other tiered fixtures.
    """
    bees_dir = tmp_path / ".bees"
    bees_dir.mkdir(parents=True, exist_ok=True)
    yield tmp_path


@pytest.fixture(scope="function")
def single_hive(bees_repo):
    """
    Builds on bees_repo fixture - adds single configured hive for simple test scenarios.
    
    Creates:
    - 'backend' hive directory structure
    - .hive/identity.json with normalized and display names
    - Registers hive in .bees/config.json
    - Yields tuple of (repo_root, hive_path)
    
    Use this fixture for tests that need a single hive with proper configuration.
    """
    repo_root = bees_repo
    hive_path = repo_root / "backend"
    hive_path.mkdir(parents=True, exist_ok=True)
    
    # Create .hive directory with identity marker
    hive_identity_dir = hive_path / ".hive"
    hive_identity_dir.mkdir(parents=True, exist_ok=True)
    
    identity_data = {
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00"
    }
    identity_file = hive_identity_dir / "identity.json"
    identity_file.write_text(json.dumps(identity_data, indent=2))
    
    # Register hive in config
    config_path = repo_root / ".bees" / "config.json"
    config_data = {
        "hives": {
            "backend": {
                "path": str(hive_path),
                "display_name": "Backend"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    config_path.write_text(json.dumps(config_data, indent=2))
    
    yield (repo_root, hive_path)


@pytest.fixture(scope="function")
def multi_hive(bees_repo):
    """
    Builds on bees_repo fixture - adds multiple hives for cross-hive test scenarios.
    
    Creates:
    - 'backend' and 'frontend' hive directories
    - .hive/identity.json for both hives
    - Registers both hives in .bees/config.json
    - Yields tuple of (repo_root, backend_path, frontend_path)
    
    Use this fixture for tests that need to verify cross-hive operations or multi-hive queries.
    """
    repo_root = bees_repo
    backend_path = repo_root / "backend"
    frontend_path = repo_root / "frontend"
    
    # Create backend hive
    backend_path.mkdir(parents=True, exist_ok=True)
    backend_identity_dir = backend_path / ".hive"
    backend_identity_dir.mkdir(parents=True, exist_ok=True)
    backend_identity = {
        "normalized_name": "backend",
        "display_name": "Backend",
        "created_at": "2026-02-05T00:00:00"
    }
    (backend_identity_dir / "identity.json").write_text(json.dumps(backend_identity, indent=2))
    
    # Create frontend hive
    frontend_path.mkdir(parents=True, exist_ok=True)
    frontend_identity_dir = frontend_path / ".hive"
    frontend_identity_dir.mkdir(parents=True, exist_ok=True)
    frontend_identity = {
        "normalized_name": "frontend",
        "display_name": "Frontend",
        "created_at": "2026-02-05T00:00:00"
    }
    (frontend_identity_dir / "identity.json").write_text(json.dumps(frontend_identity, indent=2))
    
    # Register both hives in config
    config_path = repo_root / ".bees" / "config.json"
    config_data = {
        "hives": {
            "backend": {
                "path": str(backend_path),
                "display_name": "Backend"
            },
            "frontend": {
                "path": str(frontend_path),
                "display_name": "Frontend"
            }
        },
        "allow_cross_hive_dependencies": False,
        "schema_version": "1.0"
    }
    config_path.write_text(json.dumps(config_data, indent=2))
    
    yield (repo_root, backend_path, frontend_path)


@pytest.fixture(scope="function")
def hive_with_tickets(single_hive, monkeypatch):
    """
    Builds on single_hive fixture - pre-creates ticket hierarchy for relationship testing.
    
    Creates:
    - Epic ticket (backend.bees-xxx)
    - Task ticket with epic as parent
    - Subtask ticket with task as parent
    - Uses create_ticket() functions to ensure proper structure
    - Yields tuple of (repo_root, hive_path, epic_id, task_id, subtask_id)
    
    Use this fixture for tests that need to verify ticket relationships, queries, or operations
    on existing ticket hierarchies.
    """
    from src.ticket_factory import create_epic, create_task, create_subtask
    
    repo_root, hive_path = single_hive
    
    # Change to repo_root directory so Path.cwd() returns correct path
    monkeypatch.chdir(repo_root)
    
    # Set repo context for ticket creation
    with repo_root_context(repo_root):
        # Create epic
        epic_id = create_epic(
            title="Test Epic",
            description="Epic for testing",
            hive_name="backend"
        )
        
        # Create task with epic as parent
        task_id = create_task(
            title="Test Task",
            description="Task for testing",
            parent=epic_id,
            hive_name="backend"
        )
        
        # Create subtask with task as parent
        subtask_id = create_subtask(
            title="Test Subtask",
            description="Subtask for testing",
            parent=task_id,
            hive_name="backend"
        )
    
    yield (repo_root, hive_path, epic_id, task_id, subtask_id)
