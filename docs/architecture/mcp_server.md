# MCP Server Architecture

## Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket operations while maintaining relationship consistency. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets and hives safely.

## Design Goals

1. **Relationship Consistency**: Automatically maintain reciprocal relationships (see `relationships.md`)
2. **Schema Validation**: Enforce ticket type rules (e.g., subtasks must have parent, epics cannot)
3. **Atomic Operations**: All relationship updates succeed or fail together
4. **Tool-Based Interface**: Standard MCP tool schemas for interoperability
5. **Health Monitoring**: Server lifecycle management and readiness checks
6. **Consistent Error Handling**: All MCP tools raise `ValueError` for errors (validation failures, missing resources, config errors) rather than returning error dicts

## HTTP Transport Architecture

HTTP transport uses uvicorn ASGI server for MCP communication.

**Configuration**: See the README.md Quick Start section for HTTP transport configuration details and the example configuration file at `docs/examples/claude-config-http.json`.

**Implementation**: The FastMCP framework provides HTTP transport through its `mcp.http_app` property, which returns a Starlette ASGI application instance. This application is passed to uvicorn, which handles the HTTP server hosting with configurable host, port, and logging settings. The architecture separates the MCP protocol handling (FastMCP) from the HTTP transport layer (uvicorn), allowing flexible deployment configurations.

```python
uvicorn.run(
    mcp.http_app,
    host=config.http.host,
    port=config.http.port,
    log_level=log_level
)
```

**Documentation Structure**: stdio transport documentation has been archived to `docs/archive/stdio-transport.md`. The README now includes only a brief note about stdio with a link to the archived documentation.

## Repository Root Resolution Strategy

The server implements a flexible fallback chain to support MCP clients with or without roots protocol:

1. **Priority 1**: If `repo_root` parameter is provided, validates and uses it directly
2. **Priority 2**: If `ctx` (FastMCP Context) is provided, attempts to use MCP roots protocol via `get_client_repo_root(ctx)`
3. **Fallback behavior**: If both methods fail, returns None

**MCP Roots Protocol Support**:
- The MCP roots protocol is an optional protocol that allows MCP servers to automatically detect which repository the client is working in
- **Implementation**: `get_client_repo_root(ctx) -> Path | None` in `src/mcp_server.py`
  - Attempts to read `ctx.roots` from FastMCP Context
  - Returns the first root URI from the roots list if available
  - Returns None if roots protocol is not supported by the client
- **Client compatibility**:
  - ✅ Roots-enabled clients (Claude Desktop, OpenCode): Never need to provide `repo_root` parameter
  - ⚠️ Basic MCP clients without roots support: Must provide `repo_root` parameter explicitly

**Parameter Design**:
- All MCP tool functions accept optional `repo_root: str | None = None` parameter
- All MCP tool functions accept `ctx: Context | None = None` to support both client types
- Each tool function passes `repo_root` to `get_repo_root(ctx, repo_root=repo_root)` for consistent fallback behavior
- Prioritizes explicit `repo_root` parameter over automatic detection
- Raises ValueError only for truly invalid inputs (non-absolute paths, invalid git repositories)

## Module Architecture

### mcp_id_utils Module

The `mcp_id_utils` module provides foundational ticket ID parsing utilities extracted from `mcp_server.py` to prevent circular dependencies. This module has zero dependencies on other Bees modules and serves as a base utility layer.

**Design Rationale**:
- Extracted during MCP server refactoring to break circular dependency chains
- Contains frequently-used parsing functions needed by multiple modules
- No external dependencies beyond Python standard library
- Position: Foundational utility with no dependencies

**Functions**:
- `parse_ticket_id(ticket_id: str) -> tuple[str, str]`: Splits ticket ID into (hive_name, base_id). Handles both new format (`backend.bees-abc1`) and legacy format (`bees-abc1`).
- `parse_hive_from_ticket_id(ticket_id: str) -> str | None`: Extracts hive prefix from ticket ID. Returns None for unprefixed/malformed IDs.

**Module Dependencies**:
- Used by: `mcp_server.py`, `paths.py`, validation modules
- Imports: None (Python standard library only)

**Refactoring History**:
- 2026-02-03: Removed duplicate implementation `_parse_ticket_id_for_path()` from `paths.py`
- `paths.py` now imports and uses `parse_ticket_id()` from this module, adding hive prefix validation where needed
- Design decision: Centralized ticket ID parsing in `mcp_id_utils` prevents circular imports and ensures consistent parsing logic across the codebase

**File Location**: `src/mcp_id_utils.py`

## Available MCP Tools

### Ticket Operations
- **create_ticket**: Create new ticket (epic/task/subtask) with automatic relationship synchronization. Requires `hive_name` parameter.
- **update_ticket**: Update existing ticket fields with bidirectional relationship updates
- **delete_ticket**: Delete ticket with cascade deletion of all children and automatic relationship cleanup
- **show_ticket**: Retrieve complete ticket data by ID

### Query Operations
- **execute_query**: Execute a named query previously registered in `.bees/queries/`
- **execute_freeform_query**: Execute ad-hoc YAML query pipeline without persisting
- **add_named_query**: Register a new named query for reuse

### Hive Management
- **colonize_hive**: Create and register new hive directory with validation
- **list_hives**: List all registered hives with display names, normalized names, and paths
- **abandon_hive**: Stop tracking a hive without deleting ticket files
- **rename_hive**: Rename hive with ID regeneration and cross-reference updates
- **sanitize_hive**: Validate and auto-fix malformed tickets in a hive

### Utility
- **generate_index**: Generate markdown index of all tickets with optional filters
- **health_check**: Check server health status and readiness
- **help**: Display available MCP tools and their parameters

## Server Startup and CLI Integration

**Entry point architecture** uses `src/main.py` to separate server initialization from tool implementations, enabling configuration-driven deployment via Poetry scripts. YAML configuration was chosen over .env or JSON formats to support comments, human readability, and nested structures.

**Corruption state validation** checks `.bees/corruption_report.json` before starting the MCP server. If validation errors exist, the server refuses to start, forcing manual fixes before allowing operations. This prevents cascading data corruption.

**Signal handling** registers SIGINT and SIGTERM handlers to ensure cleanup before exit, supporting standard Unix process management.

## Relationship Synchronization

The relationship synchronization module (`src/relationship_sync.py`) provides core functionality for maintaining bidirectional consistency of all ticket relationships. Shared by create/update/delete MCP tools to ensure atomicity and data integrity.

**Key Functions**:
- `add_child_to_parent()`, `remove_child_from_parent()`: Handle parent-child relationships with idempotency
- `add_dependency()`, `remove_dependency()`: Handle dependency relationships bidirectionally
- `validate_ticket_exists()`, `validate_parent_child_relationship()`, `check_for_circular_dependency()`: Enforce rules and prevent cycles

**Batch Operations**: `sync_relationships_batch()` handles multiple relationship updates atomically using seven-phase execution: validation, loading, deduplication, backup (WAL), update, write-with-rollback, and cleanup.

For complete details, see `relationships.md`.

## Query System Integration

The MCP server exposes query operations through `execute_query()` and `execute_freeform_query()` tools. The query system implements a multi-stage pipeline for filtering and traversing tickets using search terms (type=, id=, title~, label~, parent=) and graph terms (parent, children, up_dependencies, down_dependencies).

For complete architecture details, see `queries.md`.

## Major Architectural Changes

**Error Handling for `get_repo_root()` (2026-02-03)**:
- Changed to return None instead of raising ValueError when roots protocol is unavailable
- Rationale: All MCP tool callers expect None as valid return; ValueError reserved for invalid inputs
- Returns `Path` when repo root successfully determined, `None` when roots protocol unavailable, raises `ValueError` only for invalid inputs

**Test Coverage for `repo_root` Parameter (2026-02-03)**:
- Added comprehensive test coverage for repo_root parameter across all MCP functions
- All tests verify functions accept `repo_root` parameter with `ctx=None` (simulating roots protocol unavailable)
- Tests use actual test repository hive to pass hive validation
- Test file: `tests/test_mcp_roots.py`

**File Encoding for Cross-Platform Compatibility**:
- All file operations in `rename_hive()` use explicit `encoding='utf-8'` parameter
- Prevents `UnicodeDecodeError` on systems with non-UTF-8 default encodings
- Test coverage: `tests/test_rename_hive_encoding.py`
