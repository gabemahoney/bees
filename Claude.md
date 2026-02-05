# Purpose of this repo

You are building the bees ticket management system but also using the bees ticket system.
Bear this in mind when talking with the user. Sometimes they will be asking you to just use bees.
Other times they will be asking you to build or debug bees.

## Bees MCP Server Management (for dev and debugging)

**Start server:**
```bash
poetry run python -m src.main > /tmp/bees_server.log 2>&1 &
```

**Stop server:**
```bash
pkill -9 -f "python -m src.main"
```

**Restart server:**
```bash
pkill -9 -f "python -m src.main" && sleep 2 && poetry run python -m src.main > /tmp/bees_server.log 2>&1 &
```

**Check for duplicate servers:**
```bash
ps aux | grep "python.*src.main" | grep -v grep
```
Shows PID and start time. If multiple processes exist, kill old ones before restarting.

**Check server health:**
```bash
curl http://127.0.0.1:8000/health
```

**View logs:**
```bash
tail -f ~/.bees/mcp.log
```


## MCP Roots Protocol and repo_root

**Location**: src/mcp_repo_utils.py, src/repo_context.py

### Architecture Overview

The codebase uses **contextvars** for async-safe, request-scoped management of `repo_root`. This eliminates the need to manually thread `repo_root` through 24+ functions across 6+ files.

### How it Works

**1. MCP Entry Points** (e.g., `_create_ticket` in mcp_ticket_ops.py:98)

Every MCP tool function receives `ctx: Context` from FastMCP and an optional `repo_root: str | None` parameter for non-Roots clients.

```python
async def _create_ticket(
    ctx: Context,
    repo_root: str | None = None,  # Explicit fallback for non-Roots clients
    ...
):
    # Resolve repo_root from Roots protocol or explicit parameter
    resolved_root = await resolve_repo_root(ctx, repo_root)
    
    # Set context once at entry point
    with repo_root_context(resolved_root):
        # All downstream functions can now call get_repo_root()
        create_epic(...)  # No need to pass repo_root!
```

**2. Downstream Functions** (e.g., config.py, paths.py, writer.py)

Core functions simply call `get_repo_root()` from contextvars - no parameters needed:

```python
from .repo_context import get_repo_root

def get_config_path() -> Path:
    repo_root = get_repo_root()  # Gets from context
    return repo_root / ".bees" / "config.json"
```

**3. Repository Root Resolution** (mcp_repo_utils.py:112-159)

`resolve_repo_root(ctx, explicit_root)` handles the detection logic:
- First tries MCP Roots protocol via `ctx.list_roots()`
- Falls back to explicit `repo_root` parameter if provided
- Catches `NotFoundError`/`McpError` for non-Roots clients
- Raises clear error if neither method available

### Key Benefits

**Request-scoped isolation**: `contextvars` provides async-safe, per-request state without global pollution

**No parameter threading**: Eliminates ~30+ function signatures that previously required `repo_root: Path | None = None`

**Clear error handling**: 
- `RuntimeError` if context not set (indicates bug in MCP entry point)
- `ValueError` if neither Roots nor explicit parameter available (user-facing)

**Graceful fallback**: Non-Roots clients can use explicit `repo_root` parameter

### Implementation Files

- `src/repo_context.py` - Context management (get_repo_root, set_repo_root, repo_root_context)
- `src/mcp_repo_utils.py` - Roots protocol detection and resolution
- `src/mcp_ticket_ops.py` - Example MCP entry point pattern
- `src/config.py`, `src/paths.py`, `src/writer.py`, etc. - Downstream consumers