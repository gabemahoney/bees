Overview
Fix bees MCP server to use MCP roots protocol instead of Path.cwd(), ensuring tools operate on the client's repository, not the server's.
Implementation Approach
- Pattern: Use simple ctx: Context type annotation (FastMCP auto-injects)
- Error Handling: Raise user-friendly error if client doesn't provide roots
- Rollout: Phase-by-phase implementation with testing between phases
- Testing: Basic smoke tests for critical paths
---
Phase 1: Core Infrastructure
Step 1.1: Create Helper Function
File: src/mcp_server.py
Add after existing get_repo_root() function:
def get_client_repo_root(ctx: Context) -> Path:
    """
    Extract repository root from MCP client context.
    
    Args:
        ctx: FastMCP Context object provided by MCP client
        
    Returns:
        Path: Repository root directory from client
        
    Raises:
        ValueError: If client doesn't provide roots or roots list is empty
        
    Example:
        >>> ctx = get_context()  # From MCP client
        >>> repo = get_client_repo_root(ctx)
        >>> print(repo)
        /Users/user/projects/finance-tracker
    """
    roots = ctx.list_roots()
    
    if not roots or len(roots) == 0:
        raise ValueError(
            "Unable to determine repository location. "
            "Please use an MCP client that supports the roots protocol "
            "(like Claude Desktop or OpenCode)."
        )
    
    # Take first root and convert file:// URI to Path
    first_root = roots[0]
    root_uri = first_root.uri
    
    # Strip file:// prefix if present
    if root_uri.startswith("file://"):
        root_path = root_uri[7:]  # Remove "file://"
    else:
        root_path = root_uri
    
    return Path(root_path)
Step 1.2: Update get_repo_root()
File: src/mcp_server.py
Replace current implementation:
def get_repo_root(ctx: Context) -> Path:
    """
    Find the git repository root from MCP client context.
    
    Uses the MCP roots protocol to get the client's working directory,
    then walks up looking for .git directory.
    
    Args:
        ctx: FastMCP Context object provided by MCP client
        
    Returns:
        Path: Absolute path to the git repository root
        
    Raises:
        ValueError: If client doesn't provide roots or not in a git repository
        
    Example:
        >>> ctx = get_context()
        >>> repo_root = get_repo_root(ctx)
        >>> print(repo_root)
        /Users/username/projects/myrepo
    """
    client_root = get_client_repo_root(ctx)
    return get_repo_root_from_path(client_root)
Step 1.3: Update config.py Functions
File: src/config.py
Update these functions to accept Context:
def get_config_path(ctx: Context | None = None) -> Path:
    """Get the path to the .bees/config.json file.
    
    Args:
        ctx: Optional MCP Context. If not provided, falls back to cwd
        
    Returns:
        Path to the config file in the git repository root
    """
    if ctx is not None:
        from .mcp_server import get_repo_root
        try:
            repo_root = get_repo_root(ctx)
        except ValueError:
            # Client doesn't support roots - this is an error
            raise
    else:
        # Fallback for non-MCP usage (tests, CLI tools, etc.)
        from .mcp_server import get_repo_root_from_path
        try:
            repo_root = get_repo_root_from_path(Path.cwd())
        except ValueError:
            repo_root = Path.cwd()
    
    return repo_root / BEES_CONFIG_DIR / BEES_CONFIG_FILENAME
def ensure_bees_dir(ctx: Context | None = None) -> None:
    """Create .bees/ directory if it doesn't exist in the git repository root.
    
    Args:
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    if ctx is not None:
        from .mcp_server import get_repo_root
        try:
            repo_root = get_repo_root(ctx)
        except ValueError:
            raise
    else:
        from .mcp_server import get_repo_root_from_path
        try:
            repo_root = get_repo_root_from_path(Path.cwd())
        except ValueError:
            repo_root = Path.cwd()
    
    bees_dir = repo_root / BEES_CONFIG_DIR
    bees_dir.mkdir(exist_ok=True)
def load_bees_config(ctx: Context | None = None) -> Optional[BeesConfig]:
    """Load BeesConfig from .bees/config.json.
    
    Args:
        ctx: Optional MCP Context. If not provided, falls back to cwd
        
    Returns:
        BeesConfig object if file exists and is valid, None if file not found.
    """
    config_path = get_config_path(ctx)
    # ... rest remains the same
def save_bees_config(config: BeesConfig, ctx: Context | None = None) -> None:
    """Save BeesConfig to .bees/config.json using atomic write.
    
    Args:
        config: BeesConfig object to save
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    ensure_bees_dir(ctx)
    # ... rest remains the same
def init_bees_config_if_needed(ctx: Context | None = None) -> BeesConfig:
    """Initialize .bees/config.json on-demand if it doesn't exist.
    
    Args:
        ctx: Optional MCP Context. If not provided, falls back to cwd
        
    Returns:
        BeesConfig object (either loaded from file or newly created)
    """
    config = load_bees_config(ctx)
    if config is None:
        config = BeesConfig(...)
        save_bees_config(config, ctx)
    return config
def validate_unique_hive_name(normalized_name: str, ctx: Context | None = None) -> None:
    """Validate that a normalized hive name is unique.
    
    Args:
        normalized_name: The normalized name to check (e.g., 'back_end')
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    config = load_bees_config(ctx)
    # ... rest remains the same
def load_hive_config_dict(ctx: Context | None = None) -> dict:
    """Load hive configuration from .bees/config.json as dict.
    
    Args:
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    config_path = get_config_path(ctx)
    # ... rest remains the same
def write_hive_config_dict(config: dict, ctx: Context | None = None) -> None:
    """Write hive configuration from dict to .bees/config.json.
    
    Args:
        config: Configuration dictionary
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    ensure_bees_dir(ctx)
    # ... rest remains the same
def register_hive_dict(normalized_name: str, display_name: str, path: str, 
                       timestamp, ctx: Context | None = None) -> dict:
    """Register a new hive entry in the configuration and return updated dict.
    
    Args:
        normalized_name: Normalized hive name (e.g., 'back_end')
        display_name: Display name for the hive
        path: Absolute path to the hive directory
        timestamp: Creation timestamp (datetime object)
        ctx: Optional MCP Context. If not provided, falls back to cwd
    """
    config = load_hive_config_dict(ctx)
    # ... rest remains the same
Phase 1 Testing
Create: tests/test_mcp_roots.py
"""Tests for MCP roots protocol integration."""
import pytest
from pathlib import Path
from unittest.mock import Mock
from src.mcp_server import get_client_repo_root, get_repo_root
from src.config import get_config_path, load_bees_config
def test_get_client_repo_root_with_valid_context():
    """Test extracting repo root from context with roots."""
    ctx = Mock()
    mock_root = Mock()
    mock_root.uri = "file:///Users/test/projects/finance-tracker"
    ctx.list_roots.return_value = [mock_root]
    
    result = get_client_repo_root(ctx)
    assert result == Path("/Users/test/projects/finance-tracker")
def test_get_client_repo_root_raises_on_empty_roots():
    """Test error when client doesn't provide roots."""
    ctx = Mock()
    ctx.list_roots.return_value = []
    
    with pytest.raises(ValueError, match="Unable to determine repository location"):
        get_client_repo_root(ctx)
def test_get_repo_root_with_context():
    """Test get_repo_root uses context to find .git directory."""
    ctx = Mock()
    mock_root = Mock()
    # Use actual test repo path
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"
    ctx.list_roots.return_value = [mock_root]
    
    result = get_repo_root(ctx)
    assert result == test_repo
    assert (result / ".git").exists()
Expected Result: All Phase 1 tests pass
---
Phase 2: Update Critical MCP Tools
Focus on the two tools mentioned in the bug report:
Step 2.1: Update _list_hives()
File: src/mcp_server.py
Current signature (~line 1440):
def _list_hives() -> Dict[str, Any]:
New signature:
def _list_hives(ctx: Context) -> Dict[str, Any]:
    """
    List all registered hives in the repository.
    
    Args:
        ctx: FastMCP Context (auto-injected, gets client's repo root)
    
    Returns:
        dict: List of hives with their display names and paths
    """
    config = load_bees_config(ctx)
    # ... rest of implementation uses config from correct repo
Step 2.2: Update _create_ticket()
File: src/mcp_server.py
Current signature (~line 990):
def _create_ticket(
    ticket_type: str,
    title: str,
    hive_name: str,
    ...
) -> Dict[str, Any]:
New signature:
def _create_ticket(
    ticket_type: str,
    title: str,
    hive_name: str,
    description: str = "",
    parent: str | None = None,
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str | None = None,
    ctx: Context = None  # Auto-injected by FastMCP
) -> Dict[str, Any]:
    """Create a new ticket.
    
    Args:
        ctx: FastMCP Context (auto-injected, gets client's repo root)
        ... (other params remain the same)
    """
    # Line 1060: Change this
    config = load_bees_config()
    
    # To this:
    config = load_bees_config(ctx)
Step 2.3: Update _colonize_hive()
File: src/mcp_server.py
Current implementation (~line 357):
def colonize_hive(name: str, path: str) -> Dict[str, Any]:
    # Step 2: Validate path and find repo root from the hive path
    try:
        hive_path = Path(path)
        repo_root = get_repo_root_from_path(hive_path)
        validated_path = validate_hive_path(path, repo_root)
New implementation:
def colonize_hive(name: str, path: str, ctx: Context) -> Dict[str, Any]:
    """Create a new hive directory structure at the specified path.
    
    Args:
        name: Display name for the hive
        path: Absolute path where the hive should be created
        ctx: FastMCP Context (auto-injected, gets client's repo root)
    """
    # Step 2: Validate path using client's repo root from context
    try:
        hive_path = Path(path)
        repo_root = get_repo_root(ctx)  # Use context instead of hive path
        validated_path = validate_hive_path(path, repo_root)
        logger.info(f"Validated hive path: {validated_path}")
        logger.info(f"Found repo root from context: {repo_root}")
    except ValueError as e:
        return {
            "status": "error",
            "message": str(e),
            ...
        }
    
    # Step 5: Register hive using context for correct repo
    try:
        config = register_hive_dict(
            normalized_name=normalized_name,
            display_name=name,
            path=str(validated_path),
            timestamp=creation_timestamp,
            ctx=ctx  # Pass context instead of repo_root
        )
        
        write_hive_config_dict(config, ctx)
        logger.info(f"Registered hive '{normalized_name}' in config.json")
    except (IOError, PermissionError, OSError) as e:
        return {
            "status": "error",
            ...
        }
Phase 2 Testing
Add to tests/test_mcp_roots.py:
def test_list_hives_uses_context():
    """Test that list_hives uses client context to find hives."""
    from src.mcp_server import _list_hives
    
    ctx = Mock()
    mock_root = Mock()
    # Point to a test repo with .bees/config.json
    mock_root.uri = "file:///path/to/test/repo"
    ctx.list_roots.return_value = [mock_root]
    
    # This should not raise and should use the context
    result = _list_hives(ctx)
    assert "hives" in result
def test_create_ticket_uses_context():
    """Test that create_ticket uses client context."""
    from src.mcp_server import _create_ticket
    
    ctx = Mock()
    mock_root = Mock()
    test_repo = Path(__file__).parent.parent
    mock_root.uri = f"file://{test_repo}"
    ctx.list_roots.return_value = [mock_root]
    
    # Should use context to find hive config
    # Note: This will fail if hive doesn't exist, but that's expected
    with pytest.raises(ValueError, match="does not exist in config"):
        _create_ticket(
            ticket_type="task",
            title="Test",
            hive_name="nonexistent",
            ctx=ctx
        )
Expected Result: Critical tools now use client's repo root
---
Phase 3: Update Remaining Tools
Update all other MCP tool functions to accept ctx: Context:
Tools to Update:
- _update_ticket() - Add ctx: Context, pass to load_bees_config(ctx)
- _delete_ticket() - Add ctx: Context, pass to load_bees_config(ctx)
- _show_ticket() - Add ctx: Context, pass to load_bees_config(ctx)
- _abandon_hive() - Add ctx: Context, pass to config functions
- _rename_hive() - Add ctx: Context, pass to config functions
- _sanitize_hive() - Add ctx: Context, pass to config functions
- _generate_index() - Add ctx: Context, pass to config functions
- _add_named_query() - Add ctx: Context, pass to config functions
- _execute_query() - Add ctx: Context, pass to config functions
- _execute_freeform_query() - Add ctx: Context, pass to config functions
Pattern for Each Tool:
def _tool_name(...params..., ctx: Context) -> Dict[str, Any]:
    """Tool description.
    
    Args:
        ctx: FastMCP Context (auto-injected)
        ...other params...
    """
    # Change all instances of:
    config = load_bees_config()
    
    # To:
    config = load_bees_config(ctx)
    
    # Similarly for save_bees_config, validate_unique_hive_name, etc.
Phase 3 Testing
Add one integration test to verify end-to-end:
def test_integration_tools_from_different_repo():
    """Integration test: verify tools work when called from different repo."""
    # This would require setting up a test MCP client
    # and verifying it can manipulate a different repo's hives
    # For now, this is a placeholder for manual testing
    pass
Expected Result: All tools consistently use context
---
Phase 4: Documentation & Cleanup
Step 4.1: Update README.md
Add section about MCP roots protocol requirement:
 Requirements
 MCP Client Requirements
The bees MCP server requires clients to support the **MCP Roots Protocol**. This protocol allows the server to know which repository the client is working in.
**Supported Clients:**
- ✅ OpenCode (Claude Desktop)
- ✅ Claude Desktop (official)
- ❌ Basic MCP clients without roots support
If you see an error like "Unable to determine repository location", ensure your MCP client supports and is configured to send roots.
Step 4.2: Add Docstring Notes
Update docstrings for affected functions to mention context:
def get_repo_root(ctx: Context) -> Path:
    """
    Find the git repository root from MCP client context.
    
    This function uses the MCP roots protocol to determine the client's
    working directory. The server MUST receive roots from the client,
    otherwise a ValueError is raised.
    
    Args:
        ctx: FastMCP Context object (auto-injected by FastMCP)
        
    Returns:
        Path: Absolute path to the git repository root
        
    Raises:
        ValueError: If client doesn't provide roots via MCP roots protocol
                   or if not in a git repository
    """
Step 4.3: Update CHANGELOG or Release Notes
Document the breaking change:
 [Version X.X.X] - YYYY-MM-DD
 Breaking Changes
- **MCP Roots Protocol Required**: The bees MCP server now requires clients to support the MCP roots protocol. This fixes a bug where operations would target the server's repository instead of the client's repository. Clients that don't support roots (like basic test clients) will receive a clear error message.
 Bug Fixes
- Fixed bug where `list_hives` and `create_ticket` would operate on wrong repository when server and client were in different repos
- All MCP tools now correctly use client's repository root instead of server's cwd
 Migration Guide
- **For MCP Clients**: Ensure your client supports and sends roots. OpenCode and Claude Desktop both support this.
- **For Direct Function Calls**: If calling bees functions directly (not via MCP), pass `ctx=None` to use cwd fallback behavior (for testing/scripts only)
---
Testing Strategy
Manual Testing Checklist:
1. From bees repo: Run OpenCode with bees MCP server, verify list_hives shows bees hives
2. From finance-tracker repo: Run OpenCode with bees MCP server, verify list_hives shows finance-tracker hives (not bees hives)
3. Create ticket from finance-tracker: Verify it creates in finance-tracker's hive
4. Colonize hive from finance-tracker: Verify it creates in finance-tracker's directory structure
Automated Tests:
- Phase 1: Unit tests for helper functions
- Phase 2: Integration tests for critical tools
- Phase 3: Ensure no regressions in other tools