# Bees Master Plan

Technical architecture and implementation decisions for the Bees ticket management system.

## Documentation Philosophy

This document focuses on architectural decisions and high-level design concerns. Exhaustive edge case
catalogs and detailed test scenarios belong in test files and code comments where they provide immediate
context to maintainers. This separation keeps architectural documentation concise and maintainable.

## Architecture Overview

Bees is a markdown-based ticket management system with four core modules:

1. **Reader Module** (`src/reader.py`, `src/parser.py`, `src/validator.py`, `src/models.py`)
   - Parses markdown files with YAML frontmatter
   - Validates ticket schema
   - Returns typed ticket objects

2. **Writer Module** (`src/writer.py`, `src/ticket_factory.py`, `src/id_utils.py`)
   - Creates markdown files with YAML frontmatter
   - Factory functions for ticket creation
   - ID generation and collision detection

3. **Path Management** (`src/paths.py`)
   - Resolves file paths for ticket types
   - Manages directory structure

4. **Query System** (`src/query_parser.py`, `src/search_executor.py`)
   - Multi-stage query pipeline with search and graph terms
   - In-memory ticket filtering with AND/OR semantics
   - Regex-based pattern matching

5. **Configuration Module** (`src/config.py`)
   - Centralized configuration management
   - Type-safe Config object with attribute access
   - Nested schema support (e.g., http.host, http.port)
   - Default values for missing settings

### Configuration Architecture

Centralized configuration module with typed Config object.

**Integration**:
- `src/main.py` imports Config and load_config from config module
- Removed duplicate load_config() function that expected flat schema (host/port at root)
- Updated from flat schema to nested schema (http.host, http.port) in config.yaml
- All config access uses attribute access: `config.http_host`, `config.http_port`,
  `config.ticket_directory`

**Migration**: Previously main.py had its own load_config() expecting flat YAML structure. This
was refactored to use the centralized Config class with nested structure, eliminating schema
inconsistencies and improving maintainability.

**Port Validation Implementation**: Added input validation layer to Config class to ensure port
numbers are valid before server startup.

**Implementation Details** (`src/config.py`):
1. **Type Coercion**: Port value is wrapped in `int()` constructor to handle string inputs from YAML
   - Catches `TypeError` and `ValueError` exceptions and re-raises as descriptive `ValueError`
   - Error message format: `"Port must be a valid integer, got: {value}"`
2. **Range Validation**: After type coercion, validates port is in range 1-65535
   - Validation: `if not (1 <= self.http_port <= 65535)`
   - Error message format: `"Port must be an integer between 1 and 65535, got: {value}"`
3. **Exception Chaining**: Uses `raise ... from e` to preserve original exception context for
   debugging

**Host Validation Implementation**: Added IP address validation to Config class to ensure host values
are valid IPv4 or IPv6 addresses before passing to uvicorn.

**Implementation Details** (`src/config.py`):
1. **Validation Method**: Added `_validate_host()` method to Config class
   - Uses `ipaddress.ip_address()` from Python standard library
   - Accepts both IPv4 (127.0.0.1, 0.0.0.0) and IPv6 (::1, ::) formats
   - Raises ValueError for invalid formats with helpful examples
2. **Early Validation**: Host validation occurs in `Config.__init__` before assignment
   - Raw host value from YAML passed to `_validate_host()`
   - Empty string check before IP parsing
3. **Error Messaging**: Clear format with examples of valid IPs
   - Format: `"Invalid host '{host}': must be a valid IPv4 or IPv6 address. Examples: ..."`
   - Includes both IPv4 and IPv6 examples in error message


## Module Integration

### CLI ↔ Linter

The CLI invokes the Linter via `Linter.run()`, passing the tickets directory
path as input. The Linter validates all tickets and returns a `LinterReport`
object containing an errors list and summary statistics. This enables the CLI
to display validation results and determine system health status.

### Linter ↔ Corruption State

When the Linter completes validation, it automatically calls
`mark_corrupt(report)` if errors are found or `mark_clean()` if validation
passes. The corruption state module persists the `LinterReport` to
`.bees/corruption_report.json`, providing a persistent record of the last
validation state that other tools can query.

### MCP Server ↔ Ticket Storage

The MCP Server uses `ticket_factory` functions (`create_epic`, `create_task`,
`create_subtask`) to write YAML frontmatter and markdown content to the
`tickets/` filesystem. For reading, it calls `reader.read_ticket()` to parse
tickets back into typed objects. This bidirectional integration allows MCP tool
calls to create and query tickets seamlessly.

## Ticket Creation Module Architecture

### ID Generation Strategy

**Format**: `bees-<3 alphanumeric chars>`

**Implementation** (`src/id_utils.py`):
- Character set: lowercase letters (a-z) and digits (0-9)
- Total ID space: 46,656 possible IDs (36^3)
- Random selection using Python's `random.choices()`

**Collision Handling**:
- `generate_unique_ticket_id()` checks against existing IDs
- Retries up to 100 times before raising RuntimeError
- `extract_existing_ids_from_directory()` scans tickets/ for existing IDs
- Collision probability is extremely low with current ID space

### YAML Serialization Approach

**Implementation** (`src/writer.py:serialize_frontmatter()`):
- Uses `yaml.safe_dump()` for security and standard compliance
- Converts datetime objects to ISO format strings
- Skips None values and empty lists for clean output
- Block style formatting (default_flow_style=False) for readability

**Key Features**:
- Special character handling via `allow_unicode=True`
- Multiline string preservation using YAML's literal block syntax
- 80-character line wrapping for readability
- Leading and trailing `---` delimiters for frontmatter

### File Writing Patterns

**Atomic Write Operations** (`src/writer.py:write_ticket_file()`):

1. Create temp file in target directory with `.tmp` extension
2. Write content to temp file
3. Use `os.rename()` to atomically move temp file to target path
4. Clean up temp file on error

**Benefits**:
- Prevents partial/corrupted files on write failure
- Ensures consistency in concurrent scenarios
- Matches Unix atomic rename semantics

**Directory Creation**:
- Automatically creates parent directories via `ensure_ticket_directory_exists()`
- Uses `mkdir(parents=True, exist_ok=True)` for idempotency

### Factory Function Design

**Three Factory Functions** (`src/ticket_factory.py`):
- `create_epic()` - Creates Epic tickets
- `create_task()` - Creates Task tickets with optional parent
- `create_subtask()` - Creates Subtask tickets with required parent

**Function Parameters**:
- Required: title (all types), parent (subtasks only)
- Optional: description, labels, dependencies, owner, priority, status, ticket_id
- Defaults: status="open", auto-generated ID if not provided

**Validation**:
- Title required for all ticket types
- Parent required for subtasks
- ValueError raised on validation failures

**ID Generation Integration**:
- Calls `extract_existing_ids_from_directory()` to get current IDs
- Calls `generate_unique_ticket_id()` with existing set
- Supports custom IDs via ticket_id parameter

**Metadata Handling**:
- Automatically sets created_at and updated_at timestamps
- Skips optional fields if not provided (clean frontmatter)
- Normalizes None values for lists to empty lists

### Integration with Path Utilities

**Directory Resolution** (`src/paths.py`):
- `TICKETS_DIR = Path.cwd() / "tickets"` - Base directory in current working directory
- `get_ticket_directory(ticket_type)` - Maps type to subdirectory (epics/tasks/subtasks)
- `get_ticket_path(ticket_id, ticket_type)` - Full file path for ticket
- `infer_ticket_type_from_id(ticket_id)` - Lightweight type inference from file location

**Hierarchical Path Structure**:
Bees uses a hierarchical directory structure for organizing tickets by type:
- **Epics**: `tickets/epics/bees-XXX.md`
- **Tasks**: `tickets/tasks/bees-XXX.md`
- **Subtasks**: `tickets/subtasks/bees-XXX.md`

**Type Inference Function**:
- **Purpose**: Determine ticket type without loading full ticket object
- **Implementation**: Checks file existence in each type directory (epic → task → subtask)
- **Return Value**: 'epic', 'task', 'subtask', or None if not found
- **Performance**: Fast file existence check vs. slow YAML parsing + validation
- **Use Case**: Relationship validation can check type hierarchy without reading ticket content

**Writer Integration**:
- Factory functions call `write_ticket_file()`
- Writer calls `ensure_ticket_directory_exists()` before write
- Writer calls `get_ticket_path()` to determine target location

## Reader Module Architecture

### YAML Frontmatter Parsing

**Implementation** (`src/parser.py:parse_frontmatter()`):
- Reads file content
- Splits on `---` delimiters
- Uses `yaml.safe_load()` to parse frontmatter section
- Returns frontmatter dict and markdown body separately

### Validation Strategy

**Implementation** (`src/validator.py`):
- `validate_ticket()` checks required fields (id, type, title)
- `validate_id_format()` ensures ID matches pattern
- Type-specific validation (e.g., subtask must have parent)
- Field type validation (e.g., labels must be list)

### Data Models

**Implementation** (`src/models.py`):
- Dataclasses for Epic, Task, Subtask
- Shared base Ticket class
- Type enforcement in `__post_init__()` methods
- Subtask validates parent presence

## Design Principles

1. **Markdown-First**: Tickets are human-readable markdown files
2. **Type Safety**: Dataclasses and validation ensure schema compliance
3. **Atomicity**: File operations are atomic to prevent corruption
4. **Simplicity**: Simple factory functions over complex frameworks
5. **Extensibility**: Clean module boundaries support future features

## Sample Ticket Implementation

### Purpose and Goals

Sample tickets serve multiple purposes:
- **Documentation**: Demonstrate the complete ticket schema and all field types
- **Validation**: Provide examples for reader/parser verification
- **Templates**: Serve as reference examples for users creating their own tickets
- **Integration**: Verify end-to-end flow from creation to parsing

### File Organization Structure

**Directory Layout**:
```
/tickets
  /epics
    sample-epic.md        # bees-ep1
  /tasks
    sample-task.md        # bees-tk1
  /subtasks
    sample-subtask.md     # bees-sb1
```

### YAML Frontmatter Format Choices

**Sample Epic Structure**:
```yaml
id: bees-ep1
type: epic
title: Sample Epic - E-commerce Platform
description: Implement a complete e-commerce platform...
labels:
  - feature
  - backend
  - frontend
up_dependencies: []
down_dependencies: []
children: []
status: open
priority: 2
owner: engineering-team
created_at: 2026-01-30T15:00:00Z
updated_at: 2026-01-30T15:00:00Z
```

**Key Decisions**:
- All field types represented (strings, lists, timestamps)
- Empty arrays shown explicitly to demonstrate structure
- ISO timestamp format for consistency
- Realistic content (e-commerce example) more useful than toy data

**Sample Task Structure**:
```yaml
id: bees-tk1
type: task
title: Sample Task - Implement Product Catalog API
parent: bees-ep1                    # Parent reference demonstrates hierarchy
down_dependencies:                  # Non-empty to show dependency format
  - bees-dp1
status: in progress                 # Different status than epic
```

**Key Decisions**:
- Parent field links to sample epic (demonstrates relationship)
- down_dependencies populated to show dependency syntax
- Different status value demonstrates label flexibility
- More specific labels (backend, api, database) show granularity

**Sample Subtask Structure**:
```yaml
id: bees-sb1
type: subtask
title: Sample Subtask - Create database schema...
parent: bees-tk1                    # REQUIRED parent field
owner: alice@example.com            # Individual vs team owner
priority: 0                         # Highest priority
```

**Key Decisions**:
- Parent field is required and links to task
- Individual owner (email) vs team name
- Highest priority (0) demonstrates priority range
- More specific implementation-level content

### Relationship Linking Approach

**Hierarchical Relationships** (Parent-Child):
- Epic has no parent (top level)
- Task has parent: bees-ep1 (belongs to epic)
- Subtask has parent: bees-tk1 (belongs to task)
- Children arrays currently empty (populated when bidirectional sync implemented)

**Dependency Relationships**:
- Task has down_dependencies: [bees-dp1]
- Shows blocking relationship syntax
- Demonstrates that dependencies are same-type only

### Integration with Reader/Parser Module

**Validation Coverage**:
- All required fields present (id, type, title)
- ID format matches bees-XXX pattern
- Type enum values (epic, task, subtask)
- List fields properly formatted
- Subtask parent requirement satisfied

**Parser Testing**:
- YAML frontmatter delimiters (---) correct
- ISO timestamp format parsable by reader
- Multiline descriptions in markdown body
- Unicode content support (no special chars in samples, but format supports)

**Reader Integration**:
```python
from src.reader import read_ticket

epic = read_ticket('tickets/epics/sample-epic.md')
# Returns Epic object with all fields populated
```


**Benefits**:
- Clear separation of concerns (user value → technical work → implementation)
- Enables progress tracking at multiple granularities
- Supports both high-level roadmap and detailed execution planning
- Matches common agile/sprint planning practices

### Bidirectional Relationships

**Current Implementation**:
- Parent → Child: Parent ID stored in child's parent field
- Child → Parent: children array exists but not auto-populated
- Down → Up Dependencies: down_dependencies list in blocker ticket
- Up → Down Dependencies: up_dependencies list in blocked ticket

**Sample Ticket Behavior**:
- Task bees-tk1 has parent: bees-ep1
- Epic bees-ep1 has children: [] (empty)
- Future: Linter/MCP server will populate children automatically

## MCP Server Architecture

### Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket write operations (create, update, delete) while ensuring bidirectional consistency of all relationships. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets safely.

### Design Goals

1. **Bidirectional Consistency**: When a relationship is created/modified in one ticket, automatically update the reciprocal field in related tickets
2. **Schema Validation**: Enforce ticket type rules (e.g., subtasks must have parent, epics cannot)
3. **Atomic Operations**: All relationship updates succeed or fail together
4. **Tool-Based Interface**: Standard MCP tool schemas for interoperability
5. **Health Monitoring**: Server lifecycle management and readiness checks

### HTTP Transport Architecture

HTTP transport uses uvicorn ASGI server for MCP communication.

**Configuration**: See the README.md Quick Start section for HTTP transport configuration
details and the example configuration file at `docs/examples/claude-config-http.json`.

**Documentation Structure**: stdio transport documentation has been archived to
`docs/archive/stdio-transport.md`. This separation keeps the main README focused on the recommended
HTTP transport approach while preserving legacy stdio instructions for users who need them. The
README now includes only a brief note about stdio as a legacy option with a link to the archived
documentation.

**HTTP Transport Testing & Validation** (Task bees-1u88):

End-to-end testing confirmed HTTP transport is production-ready. The testing process validated:

1. **Configuration Migration**: Successfully updated `~/.claude.json` from stdio transport (command,
   args, cwd, env fields) to HTTP transport (url field only)
2. **Server Startup**: `poetry run start-mcp` launches cleanly, binds to configured port (8000),
   accepts connections without errors
3. **Connection Verification**: `claude mcp list` command confirms successful connection with output:
   `bees: http://127.0.0.1:8000/mcp (HTTP) - ✓ Connected`
4. **Tool Execution**: MCP tools execute successfully over HTTP transport, including `health_check`
   tool returning proper server status
5. **Stability**: No latency issues, clean connection lifecycle, stable throughout testing


**Migration Recommendation**: Users can safely migrate to HTTP transport. No additional
troubleshooting steps required beyond standard configuration. HTTP transport is now the recommended
and default approach for connecting Claude Code to the bees MCP server.

**Implementation Details** (`src/main.py`):
```python
import uvicorn
from .mcp_server import mcp

# In main() after loading config:
# Get Starlette app from FastMCP
http_app = mcp.http_app()

# Set up custom HTTP routes
setup_http_routes(http_app)

# Run uvicorn with configured app
uvicorn.run(
    http_app,            # Starlette ASGI application from FastMCP
    host=host,           # From config.yaml: http.host (default: 127.0.0.1)
    port=port,           # From config.yaml: http.port (default: 8000)
    log_level="info"
)
```

**Code Style Notes**:
- **Import Organization**: Follows PEP 8 with standard library imports (logging, signal, sys,
  pathlib, uvicorn) grouped together, followed by a blank line, then minimal Starlette imports
  (starlette.requests, starlette.responses.JSONResponse only), followed by local imports
  (.config, .mcp_server, .corruption_state). Unused Starlette imports (Starlette, Response, Route)
  removed in favor of leveraging FastMCP's built-in HTTP app, maintaining code cleanliness
- **Method Call**: The FastMCP instance exposes `http_app` as a method that returns a Starlette
  ASGI application. Call `mcp.http_app()` to get the application instance
- **Log Message Timing**: The startup log message "Launching HTTP server on {host}:{port}..."
  appears before `uvicorn.run()` is called, indicating startup intention rather than completion.
  This accurately reflects the server state - if uvicorn.run() fails, the "Launching" message was
  truthful
- **Blocking Call**: `uvicorn.run()` is a blocking call that doesn't return until server shutdown.
  Any code after this line only executes during cleanup

**HTTP Endpoint Routing** (Task bees-q5g7):

The server provides custom HTTP endpoints alongside FastMCP's built-in MCP protocol endpoints:

**Endpoint Architecture**:
- `/mcp` - FastMCP's MCP JSON-RPC endpoint (handles MCP tool execution)
- `/health` - Custom health check endpoint (GET/POST)

**Implementation** (`src/main.py`):
```python
async def health_endpoint(request: Request) -> JSONResponse:
    """HTTP endpoint handler for /health route."""
    try:
        health_data = _health_check()
        return JSONResponse(content=health_data, status_code=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )

def setup_http_routes(app):
    """Configure HTTP endpoint routes on the Starlette application."""
    app.add_route("/health", health_endpoint, methods=["GET", "POST"])
    logger.info("HTTP routes configured: /health")
    logger.info("MCP endpoint /mcp provided by FastMCP")
```

**Routing**:
- **Separation of Concerns**: Custom endpoints (health) are added via `setup_http_routes()` while
  MCP protocol endpoints are handled by FastMCP's internal routing
- **Starlette Integration**: Uses Starlette's `add_route()` method to register custom endpoints on
  FastMCP's Starlette app
- **Error Handling**: Each endpoint implements error handling with appropriate HTTP
  status codes (200 for success, 500 for server errors)
- **Method Support**: Health endpoint supports both GET and POST methods for flexibility

**Error Handling**:
- **JSON Responses**: All endpoints return JSON-formatted responses for consistency
- **HTTP Status Codes**: Proper status codes used (200 OK, 500 Internal Server Error)
- **Error Logging**: All errors logged with `logger.error()` before returning error response
- **Graceful Degradation**: Errors don't crash server, appropriate error responses returned

**JSON-RPC Protocol**:
The `/mcp` endpoint is provided by FastMCP and handles MCP JSON-RPC protocol automatically:
- Request format: `{"jsonrpc": "2.0", "method": "tool_name", "params": {...}, "id": 1}`
- Response format: `{"jsonrpc": "2.0", "result": {...}, "id": 1}` or error object
- Error codes follow JSON-RPC 2.0 specification (-32700 parse error, -32600 invalid request, etc.)

**Startup Flow**:
1. Load configuration from `config.yaml` (host, port, ticket_directory)
2. Validate ticket database for corruption (fail-fast if corrupt)
3. Call `start_server()` to set internal running flag
4. Get Starlette app from `mcp.http_app()`
5. Configure custom HTTP routes via `setup_http_routes(app)`
6. Initialize uvicorn with configured Starlette app
7. Bind to configured host:port
8. Accept HTTP connections with MCP JSON-RPC protocol and custom endpoints

**Shutdown Handling** (Task bees-kf30):
- Signal handlers (SIGINT/SIGTERM) registered *after* successful server initialization
- Handlers call `stop_server()` for cleanup but do NOT call `sys.exit(0)`
- Uvicorn's built-in signal handling completes graceful shutdown
- All connections closed cleanly, no resources leaked

**Security Considerations**:
- **Localhost Binding**: Default `127.0.0.1` restricts connections to local machine only
- **No Authentication**: Assumes local-only access; external binding (0.0.0.0) requires additional
  security layers (not implemented)
- **Port Configuration**: User-configurable port prevents conflicts with other services

**HTTP-Specific Error Handling** (Task bees-kf30):
The server provides specific exception handlers for common HTTP errors with actionable guidance:

```python
except OSError as e:
    # Handle HTTP server errors (port in use, permission denied, etc.)
    if "Address already in use" in str(e) or e.errno == 48:
        logger.error(f"Failed to start server: Port {port} is already in use")
        logger.error(f"Please stop the other service using port {port} or change the port in config.yaml")
    elif "Permission denied" in str(e) or e.errno == 13:
        logger.error(f"Failed to start server: Permission denied for {host}:{port}")
        logger.error(f"Try using a port number above 1024 or run with appropriate permissions")
    else:
        logger.error(f"Failed to start server: Network error - {e}")
        logger.error(f"Check that {host}:{port} is a valid address")
except ImportError as e:
    logger.error(f"Failed to start server: Missing dependency - {e}")
    logger.error("Please install required dependencies with: poetry install")
except RuntimeError as e:
    logger.error(f"Failed to start server: Runtime error - {e}")
    logger.error("Check server configuration and logs for details")
except Exception as e:
    # Generic fallback for unexpected errors
    logger.error(f"Failed to start server: {e}", exc_info=True)
```

**Error Handling Hierarchy**:
Specific exceptions are caught before the generic `Exception` handler to provide clear,
actionable error messages:

1. **OSError** - Network-related errors (port conflicts, permission issues, invalid addresses)
2. **ImportError** - Missing dependencies (uvicorn not installed)
3. **RuntimeError** - Server initialization failures
4. **Exception** - Catch-all for unexpected errors with full traceback

### FastMCP Library Choice

**Selected**: FastMCP 2.14.4

**Integration Approach**:
```python
from fastmcp import FastMCP

mcp = FastMCP("Bees Ticket Management Server")

@mcp.tool()
def create_ticket(...):
    # Tool implementation
```

### Server Lifecycle Management

**Initialization** (`src/mcp_server.py`):
```python
mcp = FastMCP("Bees Ticket Management Server")
_server_running = False  # Global state flag
```

**start_server() Function**:
- Sets `_server_running` flag to True
- Logs startup messages
- Returns status dict with server metadata
- Raises exception on failure

**stop_server() Function**:
- Sets `_server_running` flag to False
- Logs shutdown messages
- Returns status dict
- Graceful cleanup on error

### MCP Server Startup and CLI Integration

**Entry point architecture** uses `src/main.py` to separate server initialization from tool implementations, enabling configuration-driven deployment via Poetry scripts and clean testing boundaries. YAML configuration was chosen over .env or JSON formats to support comments, human readability, and nested structures without additional dependencies.

**Corruption state validation at startup** checks `.bees/corruption_report.json` before starting the MCP server. If validation errors exist, the server refuses to start, forcing manual fixes before allowing operations. This prevents cascading data corruption from operating on an invalid ticket database.

**Signal handling for graceful shutdown** registers SIGINT and SIGTERM handlers to ensure cleanup before exit, supporting standard Unix process management without requiring asyncio-specific patterns (FastMCP manages async internally).

### Health Check Implementation

**health_check Tool** (`src/mcp_server.py:_health_check()`):
```python
@mcp.tool()
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy" if _server_running else "stopped",
        "server_running": _server_running,
        "ready": _server_running,
        "name": "Bees Ticket Management Server",
        "version": "0.1.0"
    }
```

**Response Fields**:
- `status`: "healthy" or "stopped" (human-readable state)
- `server_running`: Boolean flag for current state
- `ready`: Boolean indicating if server can accept requests
- `name`, `version`: Server identification metadata

**Usage Scenarios**:
- Kubernetes/Docker health probes
- Client connection validation
- Monitoring dashboards
- Debugging server state issues

### Tool Schema Design and Registration

**Registration Pattern**:
FastMCP uses Python decorators to register tools. The implementation exposes both the MCP tool and the underlying function:

```python
def _create_ticket(...):
    # Implementation
    pass

# Register with MCP and create callable reference
create_ticket = mcp.tool()(_create_ticket)
```

**Benefits**:
- `create_ticket` is registered as MCP tool
- FastMCP handles schema generation from function signature
- Type hints automatically generate parameter schemas
- Clean separation between tool registration and implementation logic

**create_ticket Tool Schema**:
```python
def _create_ticket(
    ticket_type: str,           # Required: "epic", "task", or "subtask"
    title: str,                 # Required: ticket title
    description: str = "",      # Optional: detailed description
    parent: str | None = None,  # Required for subtasks
    children: list[str] | None = None,
    up_dependencies: list[str] | None = None,
    down_dependencies: list[str] | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    priority: int | None = None,
    status: str | None = None
) -> Dict[str, Any]:
```

**Validation Rules** (enforced in stub):
- ticket_type must be one of: "epic", "task", "subtask"
- Epics cannot have a parent (ValueError raised)
- Subtasks must have a parent (ValueError raised)
- Title is required (enforced by function signature)

**update_ticket Tool Schema**:
```python
def _update_ticket(
    ticket_id: str,             # Required: ticket to update
    title: str | None = None,   # All other fields optional
    # ... same optional fields as create_ticket
) -> Dict[str, Any]:
```

**delete_ticket Tool Schema**:
```python
def _delete_ticket(
    ticket_id: str,             # Required: ticket to delete
    cascade: bool = False       # Optional: recursive child deletion
) -> Dict[str, Any]:
```

**Schema Evolution**:
- Stub implementations return {"status": "stub"} for testing
- Full implementations (in later Tasks) will use factory/reader/writer modules
- Schema remains unchanged when implementation is added

### create_ticket Tool Implementation

**Overview** (Task bees-7df):

The create_ticket MCP tool creates tickets (epic/task/subtask) with automatic bidirectional relationship management. When creating a ticket with relationships, all related tickets are automatically updated to maintain consistency.

**Architecture and Data Flow**:

```
MCP Tool Invocation
    ↓
Input Validation (ticket_type, title, parent requirements)
    ↓
Related Ticket Existence Validation (parent, children, dependencies)
    ↓
Circular Dependency Check (up_dependencies vs down_dependencies)
    ↓
Factory Function Call (create_epic/create_task/create_subtask)
    ↓
Ticket File Created (via ticket_factory.py → writer.py)
    ↓
Bidirectional Relationship Updates (_update_bidirectional_relationships)
    ↓
Return Success Response with Ticket ID
```

**Implementation Details**:

The tool handler function validates inputs, calls the appropriate factory function, then updates all related tickets bidirectionally:

```python
def _create_ticket(ticket_type, title, description="", parent=None, ...):
    # Phase 1: Validate ticket_type and basic requirements
    if ticket_type not in ["epic", "task", "subtask"]:
        raise ValueError(f"Invalid ticket_type: {ticket_type}")
    if not title or not title.strip():
        raise ValueError("Ticket title cannot be empty")
    if ticket_type == "epic" and parent:
        raise ValueError("Epics cannot have a parent")
    if ticket_type == "subtask" and not parent:
        raise ValueError("Subtasks must have a parent")

    # Phase 2: Validate related tickets exist
    if parent:
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            raise ValueError(f"Parent ticket does not exist: {parent}")
    # ... similar validation for dependencies and children

    # Phase 3: Check for circular dependencies
    if up_dependencies and down_dependencies:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            raise ValueError(f"Circular dependency detected: {circular_deps}")

    # Phase 4: Call factory function to create ticket
    ticket_id = create_epic/create_task/create_subtask(...)

    # Phase 5: Update bidirectional relationships
    _update_bidirectional_relationships(
        new_ticket_id=ticket_id,
        parent=parent,
        children=children,
        up_dependencies=up_dependencies,
        down_dependencies=down_dependencies
    )

    return {"status": "success", "ticket_id": ticket_id, ...}
```

**Bidirectional Relationship Synchronization**:

The `_update_bidirectional_relationships()` helper function ensures reciprocal updates:

1. **Parent → Children**: If parent is set, adds new ticket to parent's children array
2. **Children → Parent**: If children are specified, sets parent field on each child
3. **Up Dependencies → Down Dependencies**: Adds new ticket to each blocking ticket's down_dependencies
4. **Down Dependencies → Up Dependencies**: Adds new ticket to each blocked ticket's up_dependencies

**Integration with Existing Modules**:

- **ticket_factory.py**: Calls `create_epic()`, `create_task()`, or `create_subtask()` based on type
- **reader.py**: Uses `read_ticket()` to load related tickets for updating
- **writer.py**: Uses `write_ticket_file()` to save updated related tickets
- **paths.py**: Uses `infer_ticket_type_from_id()` for lightweight type checking and `get_ticket_path()` for file locations
- **models.py**: Uses `asdict()` to convert dataclass tickets to dictionaries for serialization

**Error Handling Strategy**:

All validation errors are logged and raised as ValueError with descriptive messages:

- "Ticket title cannot be empty"
- "Invalid ticket_type: X. Must be 'epic', 'task', or 'subtask'"
- "Epics cannot have a parent"
- "Subtasks must have a parent"
- "Parent ticket does not exist: X"
- "Dependency ticket does not exist: X"
- "Child ticket does not exist: X"
- "Circular dependency detected: ticket cannot both depend on and be depended on by the same tickets: {set}"

All errors are logged at ERROR level before raising for operational visibility.

**Atomicity Guarantees**:

- Validation completes before any file writes begin
- Ticket creation (factory function) is atomic via write_ticket_file's temp file pattern
- Bidirectional updates write each related ticket atomically
- If relationship update fails, newly created ticket exists but relationships may be incomplete
- Future enhancement: Wrap entire operation in transaction with rollback

**Monitoring and Debugging**:

- All operations logged at INFO level for audit trail
- Validation failures logged at ERROR level with details
- Success messages include ticket_id and type
- Relationship updates logged individually for traceability

### Server Configuration and Extensibility

**Current Configuration**:
```python
mcp = FastMCP("Bees Ticket Management Server")
# Version: 0.1.0 (returned in health_check and start_server)
# Transport: stdio (FastMCP default)
```

**Extensibility Points**:
1. **Additional Tools**: Add new `@mcp.tool()` decorated functions
2. **Validation Rules**: Extend stub validation logic
3. **Transport Options**: FastMCP supports HTTP/WebSocket transports
4. **Middleware**: FastMCP supports request/response middleware

**Configuration Strategy**:
- Hard-coded for v0.1.0 (sufficient for initial implementation)
- Future: Load from config.yaml or environment variables
- Future: Support custom ticket directory paths
- Future: Authentication/authorization middleware

**Integration with Other Modules**:

**Reader Integration** (future):
- update_ticket will use `src.reader.read_ticket()` to load existing ticket
- delete_ticket will use reader to load ticket before deletion
- Validation checks will verify ticket_id exists via reader

**Writer Integration** (future):
- create_ticket will use `src.ticket_factory.create_*()` functions
- update_ticket will use `src.writer.write_ticket_file()` after modification
- All tools use atomic write operations from writer module

**Path Utilities**:
- All tools use `src.paths.get_ticket_path()` for file location
- Directory management handled by existing writer utilities
- Consistent path resolution across all operations

**Relationship Sync** (future Task bees-r10):
- Dedicated module (`src.relationship_sync.py`) will provide helpers
- add_child_to_parent(), add_dependency() functions
- MCP tools will call sync helpers after primary operation
- Ensures bidirectional consistency in all relationship changes

### HTTP Configuration Architecture

**Configuration Schema**:
The MCP server uses a nested YAML configuration schema in `config.yaml`:

```yaml
http:
  host: 127.0.0.1  # Server bind address
  port: 8000       # Server port

ticket_directory: ./tickets  # Ticket storage location
```

**Config Class Design** (`src/config.py`):
- Parses nested YAML structure with `http.*` fields
- Provides attribute-based access: `config.http_host`, `config.http_port`
- Type coercion and validation for port (must be integer 1-65535)
- Default values: host=127.0.0.1, port=8000, ticket_directory=./tickets

**Configuration Loading Strategy** (`get_config()`):
Search order for `config.yaml`:
1. Current working directory
2. Project root (parent of src/ if running from src/)
3. Return default Config object if not found

**Dependencies**:
- `httpx ^0.28.1` - HTTP client library for MCP transport
- `uvicorn[standard] ^0.35.0` - ASGI server for HTTP transport
- `pyyaml ^6.0` - YAML parsing for configuration

**Integration**:
- `src/main.py` calls `load_config()` on startup
- Passes `host` and `port` to FastMCP server initialization
- Server binds to configured address (default localhost-only for security)

### Deployment Considerations

**Running the Server**:
```bash
# Direct execution
python -m src.mcp_server

# Programmatic start
from src.mcp_server import start_server, mcp
start_server()
mcp.run()
```

**Transport Options**:
- Default: HTTP transport (localhost:8000)
- Dependencies: httpx (client), uvicorn with standard extras (server)
- Configuration: host and port via config.yaml http section
- Deprecated: stdio (standard input/output) - removed due to interference issues
- Future: WebSocket for persistent connections

**Logging**:
- Python logging module with INFO level
- Timestamps and module names in format
- Logs written to ~/.bees/mcp.log (HTTP transport doesn't use stdout)
- Critical for debugging tool calls
- Future: Structured logging for log aggregation

**Monitoring**:
- health_check tool for operational status
- Logging provides call traces
- Future: Metrics (request count, latency, errors)
- Future: OpenTelemetry integration

## Relationship Synchronization Module

### Overview

The relationship synchronization module (`src/relationship_sync.py`) provides core functionality for maintaining bidirectional consistency of all ticket relationships. Shared by create/update/delete MCP tools to ensure atomicity and data integrity.

### Core Functions

**Relationship Operations**: `add_child_to_parent()`, `remove_child_from_parent()`, `add_dependency()`, `remove_dependency()` handle bidirectional updates with idempotency guarantees.

**Validation Functions**: `validate_ticket_exists()`, `validate_parent_child_relationship()`, `check_for_circular_dependency()` enforce type hierarchy rules and prevent cycles using DFS traversal. Validation uses `infer_ticket_type_from_id()` for lightweight type checking without full ticket parsing.

### Batch Operations

**sync_relationships_batch()** handles multiple relationship updates atomically using seven-phase execution: validation, loading, deduplication, backup (WAL), update, write-with-rollback, and cleanup. If any write fails, all tickets are restored from in-memory backups. Deduplication prevents redundant I/O by converting operations to a set before execution.

### Internal Helpers

**_load_ticket_by_id()** searches ticket type directories with early return optimization (~33% reduction in filesystem operations). **_save_ticket()** uses atomic writes from writer module with file locking.

### Integration Points

**MCP Tools**: create_ticket, update_ticket, and delete_ticket all use relationship sync functions. delete_ticket uses `sync_relationships_batch()` for efficient cleanup of all relationships in a single atomic operation.

### Error Handling

Validation errors raised early before writes with clear messages. File I/O errors propagate from reader/writer modules. All operations are idempotent and support retry logic.

### Module Integration

Uses `infer_ticket_type_from_id()` from paths module for lightweight type checking, `read_ticket()` from reader for parsing, and `write_ticket_file()` from writer for atomic writes.

### File Locking Implementation

Prevents concurrent modification using platform-specific OS-level locking (fcntl on Unix/macOS, msvcrt on Windows). Non-blocking mode with exponential backoff retry (3 attempts, ~0.7s total) provides controlled timeout behavior. Lock granularity is per-file, transparent to callers.

### Atomicity Implementation Details

Batch sync creates in-memory backups before modifications. On write failure, all tickets are restored from backups via best-effort rollback. Cleanup happens in finally block to prevent memory leaks. Provides all-or-nothing semantics with O(2N) time complexity and O(N) space overhead.

**Two-Phase Commit** (rejected):
- Requires coordinator process
- Complex rollback protocol
- Overkill for single-process file writes

**Optimistic Locking** (rejected):
- Detects conflicts but doesn't prevent them
- Poor user experience when conflicts occur
- Requires version tracking in ticket files

**Temp File Staging** (rejected):
- Write all tickets to temp files first, then rename all atomically
- OS rename atomicity only applies per-file, not across multiple files
- Cleanup of temp files on failure is complex

**Monitoring and Debugging**:
- Write failures logged at ERROR level with original error
- Rollback failures logged at ERROR level per-ticket
- RuntimeError message includes summary of failure
- All logging includes ticket IDs for troubleshooting

### Future Enhancements

**Performance Optimizations**:
- In-memory ticket cache with LRU eviction
- Write-behind buffer for batching synchronous writes
- Parallel file I/O for batch operations
- Database backend for large-scale deployments
- WAL persistence to disk for recovery after process crash

**Additional Validation**:
- Prevent orphan tickets (parent doesn't exist)
- Validate dependency types (same-type only)
- Check for dependency cycles at ticket level
- Enforce maximum children/dependencies limits

**Monitoring and Metrics**:
- Count relationship operations for debugging
- Track sync performance (latency, throughput)
- Log validation failures for analysis
- Alert on high error rates
- Track file locking contention and retry rates
- Monitor rollback frequency and success rate

**Extended Functionality**:
- Bulk relationship import/export
- Relationship visualization (graph rendering)
- Automatic relationship repair (fix inconsistencies)
- Relationship history/audit log
- Distributed transaction coordinator for multi-process scenarios

### update_ticket Tool Implementation

**Overview** (Task bees-91v):

The update_ticket MCP tool modifies existing tickets with automatic bidirectional relationship management. When updating relationships (parent, children, dependencies), all related tickets are automatically synchronized to maintain consistency.

**Architecture and Data Flow**:

```
MCP Tool Invocation
    ↓
Ticket Existence Validation (ticket_id must exist)
    ↓
Read Existing Ticket (via reader.py)
    ↓
Related Ticket Existence Validation (new parent/children/dependencies)
    ↓
Circular Dependency Check (if both up/down deps updated)
    ↓
Update Basic Fields (title, description, labels, owner, priority, status)
    ↓
Track Old Relationships (for diff calculation)
    ↓
Update Relationship Fields (parent, children, dependencies)
    ↓
Write Updated Ticket (atomic write via writer.py)
    ↓
Sync Bidirectional Changes (add/remove from related tickets)
    ↓
Return Success Response
```

**Implementation Details**:

The tool handler validates the ticket exists, reads current state, validates changes, applies updates, and synchronizes relationship changes bidirectionally:

```python
def _update_ticket(ticket_id, title=None, description=None, parent=None, ...):
    # Phase 1: Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        raise ValueError(f"Ticket does not exist: {ticket_id}")

    # Phase 2: Read existing ticket
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    ticket = read_ticket(ticket_path)

    # Phase 3: Validate new relationship ticket IDs exist
    if parent is not None and parent:
        parent_type = infer_ticket_type_from_id(parent)
        if not parent_type:
            raise ValueError(f"Parent ticket does not exist: {parent}")
    # ... similar validation for children and dependencies

    # Phase 4: Check for circular dependencies
    if up_dependencies is not None and down_dependencies is not None:
        circular_deps = set(up_dependencies) & set(down_dependencies)
        if circular_deps:
            raise ValueError(f"Circular dependency detected: {circular_deps}")

    # Phase 5: Update basic fields
    if title is not None:
        if not title.strip():
            raise ValueError("Ticket title cannot be empty")
        ticket.title = title
    # ... update other basic fields

    # Phase 6: Track old relationships for diff
    old_parent = ticket.parent
    old_children = set(ticket.children or [])
    old_up_deps = set(ticket.up_dependencies or [])
    old_down_deps = set(ticket.down_dependencies or [])

    # Phase 7: Update relationship fields
    if parent is not None:
        ticket.parent = parent if parent else None
    # ... update other relationship fields

    # Phase 8: Write updated ticket
    ticket.updated_at = datetime.now()
    write_ticket_file(ticket_id, ticket_type, asdict(ticket), ticket.description)

    # Phase 9: Sync bidirectional relationships
    new_parent = ticket.parent
    new_children = set(ticket.children or [])
    # ... calculate added/removed relationships
    # ... call helper functions to sync related tickets

    return {"status": "success", "ticket_id": ticket_id, ...}
```

**Bidirectional Relationship Synchronization**:

The update logic calculates diffs between old and new relationship values, then calls helper functions to maintain bidirectional consistency:

1. **Parent Changes**:
   - Remove from old parent's children array (if parent changed)
   - Add to new parent's children array (if new parent set)

2. **Children Changes**:
   - Remove parent field from removed children
   - Set parent field on added children

3. **Up Dependencies Changes**:
   - Remove ticket from removed blocking tickets' down_dependencies
   - Add ticket to added blocking tickets' down_dependencies

4. **Down Dependencies Changes**:
   - Remove ticket from removed blocked tickets' up_dependencies
   - Add ticket to added blocked tickets' up_dependencies

**Helper Functions for Bidirectional Updates**:

Eight helper functions handle relationship synchronization:

- `_remove_child_from_parent(child_id, parent_id)`: Removes child from parent's children array
- `_add_child_to_parent(child_id, parent_id)`: Adds child to parent's children array
- `_remove_parent_from_child(child_id)`: Clears parent field on child ticket
- `_set_parent_on_child(parent_id, child_id)`: Sets parent field on child ticket
- `_remove_from_down_dependencies(ticket_id, blocking_id)`: Removes from blocking ticket's down_dependencies
- `_add_to_down_dependencies(ticket_id, blocking_id)`: Adds to blocking ticket's down_dependencies
- `_remove_from_up_dependencies(ticket_id, blocked_id)`: Removes from blocked ticket's up_dependencies
- `_add_to_up_dependencies(ticket_id, blocked_id)`: Adds to blocked ticket's up_dependencies

Each helper function:
- Uses `infer_ticket_type_from_id()` for lightweight type checking
- Loads the related ticket via `read_ticket()`
- Modifies the appropriate relationship field
- Updates the `updated_at` timestamp
- Writes the ticket atomically via `write_ticket_file()`
- Logs the operation for audit trail

**Integration with Existing Modules**:

- **reader.py**: Uses `read_ticket()` to load current ticket and related tickets
- **writer.py**: Uses `write_ticket_file()` for atomic writes of all modified tickets
- **paths.py**: Uses `infer_ticket_type_from_id()` for validation and `get_ticket_path()` for file locations
- **models.py**: Uses `asdict()` to convert ticket dataclass to dictionary for serialization

**Update Flow for Relationships**:

When updating a relationship field, the flow is:

1. Read current ticket to get old relationship values
2. Apply new relationship values to ticket object
3. Calculate diff: added = new - old, removed = old - new
4. For each added relationship: call appropriate helper to add reciprocal link
5. For each removed relationship: call appropriate helper to remove reciprocal link
6. All affected tickets written atomically with updated timestamps

**Error Handling Strategy**:

All validation errors are logged and raised as ValueError:

- "Ticket does not exist: X"
- "Ticket file not found: X"
- "Ticket title cannot be empty"
- "Parent ticket does not exist: X"
- "Child ticket does not exist: X"
- "Dependency ticket does not exist: X"
- "Circular dependency detected: {set}"

**Edge Cases Handled**:

1. **Removing Parent**: Setting parent to None or empty string removes parent-child relationship
2. **Removing Children**: Setting children to empty list removes all children (clears parent on each)
3. **Removing Dependencies**: Setting dependencies to empty list removes all dependency links
4. **Partial Updates**: Only specified fields are modified, others remain unchanged
5. **Empty String Parent**: Treated as None (removes parent relationship)
6. **Idempotency**: Setting relationship that already exists is safe (no duplicate entries)

**Concurrency Considerations**:

- Each file write is atomic via temp file + rename pattern
- Relationship updates are not wrapped in a transaction (future enhancement)
- If update fails partway through sync, some tickets may be updated while others aren't
- File locking prevents concurrent modifications to same ticket file
- Retry logic handles transient lock contention

### delete_ticket Tool Implementation

**Overview** (Task bees-49g):

The delete_ticket MCP tool removes tickets from the system and automatically cleans up all relationships in related tickets. When a ticket is deleted, all references to it are removed from parent, children, and dependency arrays across all affected tickets.

**Architecture and Data Flow**:

```
                         ┌─────────────────┐
                         │ MCP Tool Call   │
                         │ delete_ticket() │
                         └────────┬────────┘
                                  │
                   ┌──────────────▼──────────────┐
                   │ Phase 1: Validate & Load   │
                   │ - Check ticket exists       │
                   │ - Read ticket with reader   │
                   └──────────────┬──────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
┌───────▼────────┐       ┌────────▼────────┐      ┌───────▼────────┐
│ Phase 2:       │       │ Phase 3:        │      │ Phase 4:       │
│ Handle         │       │ Cleanup Parent  │      │ Cleanup        │
│ Children       │       │ - Remove from   │      │ Dependencies   │
│ - If cascade   │       │   children[]    │      │ - up_deps      │
│   delete all   │       └─────────────────┘      │ - down_deps    │
│ - Else unlink  │                                 └────────────────┘
└────────────────┘                                          │
        │                                                   │
        └─────────────────────┬─────────────────────────────┘
                              │
                     ┌────────▼────────┐
                     │ Phase 5: Delete │
                     │ ticket file     │
                     │ (unlink())      │
                     └─────────────────┘
```

**Implementation Details**:

The `_delete_ticket()` function in `src/mcp_server.py` performs these steps:

1. **Validation**: Verify ticket exists using `infer_ticket_type_from_id()`
2. **Load Ticket**: Read ticket data to access relationships
3. **Handle Children** (based on cascade parameter):
   - If `cascade=True`: Recursively call `_delete_ticket()` for each child
   - If `cascade=False`: Call `_remove_parent_from_child()` to unlink children
     - Note: Subtasks cannot be unlinked (require parent), so they remain orphaned
4. **Cleanup Parent**: Call `_remove_child_from_parent()` if ticket has parent
5. **Cleanup Dependencies**:
   - For each ticket in `up_dependencies`: call `_remove_from_down_dependencies()`
   - For each ticket in `down_dependencies`: call `_remove_from_up_dependencies()`
6. **Delete File**: Use `Path.unlink()` to remove ticket file from filesystem

**Tool Handler Function**:

```python
def _delete_ticket(ticket_id: str, cascade: bool = False) -> Dict[str, Any]:
    # Validate ticket exists
    ticket_type = infer_ticket_type_from_id(ticket_id)
    if not ticket_type:
        raise ValueError(f"Ticket does not exist: {ticket_id}")

    # Read ticket to get relationships
    ticket_path = get_ticket_path(ticket_id, ticket_type)
    ticket = read_ticket(ticket_path)

    # Handle children based on cascade parameter
    if ticket.children:
        if cascade:
            for child_id in ticket.children:
                _delete_ticket(child_id, cascade=True)  # Recursive
        else:
            for child_id in ticket.children:
                _remove_parent_from_child(child_id)

    # Clean up parent's children array
    if ticket.parent:
        _remove_child_from_parent(ticket_id, ticket.parent)

    # Clean up dependencies in related tickets
    if ticket.up_dependencies:
        for blocking_id in ticket.up_dependencies:
            _remove_from_down_dependencies(ticket_id, blocking_id)

    if ticket.down_dependencies:
        for blocked_id in ticket.down_dependencies:
            _remove_from_up_dependencies(ticket_id, blocked_id)

    # Delete the ticket file
    ticket_path.unlink()

    return {
        "status": "success",
        "ticket_id": ticket_id,
        "ticket_type": ticket_type,
        "message": f"Successfully deleted ticket {ticket_id}"
    }
```

**Integration with Existing Modules**:

- **reader.py**: Uses `read_ticket()` to load ticket data and access relationships
- **paths.py**: Uses `infer_ticket_type_from_id()` for validation and `get_ticket_path()` for file location
- **mcp_server.py helpers**: Reuses existing helper functions for relationship cleanup:
  - `_remove_child_from_parent()`: Removes ticket from parent's children array
  - `_remove_parent_from_child()`: Clears parent field on child ticket
  - `_remove_from_down_dependencies()`: Removes ticket from blocking ticket's down_dependencies
  - `_remove_from_up_dependencies()`: Removes ticket from blocked ticket's up_dependencies

**Cascade Delete Behavior**:

When `cascade=True`, deletion is recursive and depth-first:

```
Epic (deleted)
├── Task 1 (deleted)
│   ├── Subtask 1a (deleted)
│   └── Subtask 1b (deleted)
└── Task 2 (deleted)
    └── Subtask 2a (deleted)

Order of deletion: 1a, 1b, Task 1, 2a, Task 2, Epic
```

Each deleted ticket has its relationships cleaned up before deletion, ensuring all parent, dependency references are removed from related tickets.

**Subtask Unlinking Limitation**:

Subtasks have a validation requirement that they must always have a parent. When deleting a parent with `cascade=False`:
- Task and Epic children: Parent field set to None (successfully unlinked)
- Subtask children: Parent field unchanged (cannot be set to None without violating validation)
- Result: Subtasks remain as "orphaned" records pointing to deleted parent

**Error Handling Strategy**:

All validation errors are logged and raised as ValueError:

- "Ticket does not exist: X"
- "Ticket file not found: X" (if file system access fails)
- "Failed to read ticket X: {error}" (if parsing fails)
- "Failed to delete ticket file X: {error}" (if unlink fails)

Cascade delete errors:
- If a child ticket fails to delete during cascade, log warning but continue
- Parent ticket still gets deleted (children cleanup is best-effort)
- This prevents orphaned parent from blocking deletion

**Atomicity Considerations**:

Delete operation is NOT fully atomic:
1. Relationship cleanup happens first (multiple file writes)
2. Ticket file deletion happens last
3. If operation fails partway through:
   - Some related tickets may have cleaned-up relationships
   - Original ticket may still exist
   - Partial cleanup state possible

**Future Enhancement**: Implement transaction log for rollback capability.

**File System Operations**:

- Uses `Path.unlink()` for file deletion (raises OSError on failure)
- No explicit file locking during delete (relies on OS-level atomic unlink)
- Related ticket updates use existing file locking from writer module

**Monitoring and Debugging**:

- All operations logged at INFO level
- Validation failures logged at ERROR level
- Each relationship cleanup logged individually
- Cascade delete logs each deleted ticket
- Warnings for failed child deletions (non-fatal)

**Integration with MCP Server Lifecycle**:

- Delete tool available immediately after server startup
- No additional initialization required
- Uses same logging and error handling as other tools
- Returns standard success/error response format
- Efficient for partial updates (e.g., only changing title)
- Clear logic: added items get added, removed items get removed
- Supports incremental relationship changes

**Why Separate Helper Functions**:
- Reusable across update scenarios
- Clear single responsibility
- Centralized logging and error handling

**Why Update Ticket Before Sync**:
- Fail fast if ticket write fails
- Primary ticket is source of truth
- Related tickets sync from primary state
- Avoids orphan relationship updates if primary write fails

**Why Allow None/Empty String for Removal**:
- Intuitive API: None means "remove this relationship"
- Supports both explicit removal (None) and clearing (empty list)
- Flexible for different client patterns
- Consistent with Python conventions

**Monitoring and Debugging**:

- All operations logged at INFO level
- Validation failures logged at ERROR level with details
- Relationship sync operations logged individually
- Success response includes ticket_id and type for traceability

## Query Parser Architecture

### Overview (Task bees-j15d)

The Query Parser (`src/query_parser.py`) validates YAML query structures for the multi-stage
query pipeline system. It enforces strict validation rules to ensure queries are well-formed
before execution, preventing runtime errors and providing clear error messages.

**Core Responsibilities**:
- Parse YAML query structure into list of stages
- Validate search terms (type=, id=, title~, label~)
- Validate graph terms (children, parent, up_dependencies, down_dependencies)
- Enforce stage purity (no mixing search and graph terms)
- Validate regex patterns are compilable

### Query Structure

**Multi-Stage Pipeline**:
```python
query = [
    ['type=epic', 'label~beta'],    # Stage 0: Search stage (2 terms ANDed)
    ['children'],                    # Stage 1: Graph stage (relationship traversal)
    ['label~open']                   # Stage 2: Search stage (filter results)
]
```

**Design Principles**:
- Stages evaluated sequentially in order
- Results from stage N passed to stage N+1
- Terms within a stage are ANDed together
- Results deduplicated after each stage
- Empty result set short-circuits pipeline

### Parsing Strategy

**Two-Phase Approach**:

1. **Parse Phase** (`parse()` method):
   - Accepts YAML string or already-parsed list structure
   - Uses `yaml.safe_load()` for security
   - Validates basic structure (list of lists of strings)
   - Returns normalized stage structure
   - No semantic validation at this stage

2. **Validation Phase** (`validate()` method):
   - Validates each term within each stage
   - Determines term type (search vs graph)
   - Enforces stage purity rules
   - Validates term-specific constraints
   - Compiles regex patterns to catch errors early

**Why Two Phases**:
- Separation of concerns (structure vs semantics)
- Allows parse-only operation for some use cases
- Clear error categorization (structure vs validation)
- Easier to test each phase independently

### Term Type Detection

**Search Terms** - Detected by prefix:
- `type=` - Ticket type filter
- `id=` - Ticket ID filter
- `title~` - Title regex filter
- `label~` - Label regex filter

**Graph Terms** - Detected by exact match:
- `children` - Traverse to child tickets
- `parent` - Traverse to parent ticket
- `up_dependencies` - Traverse to blocking tickets
- `down_dependencies` - Traverse to blocked tickets

**Detection Method**:
```python
def _is_search_term(self, term: str) -> bool:
    return any(term.startswith(prefix) for prefix in self.SEARCH_TERMS)

def _is_graph_term(self, term: str) -> bool:
    return term in self.GRAPH_TERMS
```

### Stage Purity Enforcement

**Rule**: Each stage must contain ONLY search terms OR ONLY graph terms, never both.

**Implementation**:
```python
def _validate_stage(self, stage: list[str], stage_idx: int) -> None:
    stage_types = set()
    for term in stage:
        if self._is_search_term(term):
            stage_types.add('search')
        elif self._is_graph_term(term):
            stage_types.add('graph')

    if len(stage_types) > 1:
        raise QueryValidationError(
            f"Stage {stage_idx}: Cannot mix search and graph terms"
        )
```

**Why Enforce Purity**:
- Maintains clear stage semantics (filter vs traverse)
- Simplifies pipeline executor routing logic
- Prevents ambiguous execution order within stage
- Matches PRD requirements for clean separation

**Error Message Example**:
```
Stage 0: Cannot mix search and graph terms in same stage. Found both: search, graph
```

### Search Term Validation

**Type Term Validation**:
- Format: `type=<value>`
- Valid values: epic, task, subtask
- Rejects empty value, invalid type names
- Case-sensitive matching

**ID Term Validation**:
- Format: `id=<value>`
- Rejects empty value
- No format validation at this level (executor handles ID lookup)

**Regex Term Validation** (title~, label~):
- Format: `title~<pattern>` or `label~<pattern>`
- Rejects empty pattern
- Compiles pattern using `re.compile()` to validate
- Catches regex syntax errors early
- Supports full Python regex syntax

**Implementation**:
```python
def _validate_regex_pattern(self, pattern: str, term_type: str, stage_idx: int):
    try:
        re.compile(pattern)
    except re.error as e:
        raise QueryValidationError(
            f"Stage {stage_idx}: Invalid regex pattern in {term_type} term: {e}"
        )
```

**Regex Features Supported**:
- Case-insensitive flags: `(?i)beta`
- Alternation (OR): `beta|alpha|preview`
- Negative lookahead (NOT): `^(?!.*closed).*`
- Character classes: `p[0-4]`
- Anchors: `^start`, `end$`

### Graph Term Validation

**Simple Exact Matching**:
- Terms must exactly match one of: children, parent, up_dependencies, down_dependencies
- No parameters allowed (graph terms are pure traversal operations)
- Unknown term names rejected with clear error

**Implementation**:
```python
def _validate_graph_term(self, term: str, stage_idx: int):
    if term not in self.GRAPH_TERMS:
        raise QueryValidationError(
            f"Stage {stage_idx}: Invalid graph term '{term}'. "
            f"Valid graph terms: {', '.join(self.GRAPH_TERMS)}"
        )
```

**Why So Simple**:
- Graph terms have no configuration (they traverse fixed relationships)
- Validation is just name checking
- Complexity handled by graph executor, not parser

### Error Handling Strategy

**Informative Error Messages**:
- Include stage index for multi-stage queries
- Show valid options for enum-like fields
- Include original error for regex compilation failures
- Specific messages for each validation rule

**Error Message Examples**:
```python
# Structure error
"Query must be a list, got dict"

# Empty stage
"Stage 2 cannot be empty"

# Invalid type
"Stage 0: Invalid type 'invalid'. Valid types: epic, task, subtask"

# Invalid regex
"Stage 1: Invalid regex pattern in label~ term: unterminated character set"

# Mixed stage
"Stage 0: Cannot mix search and graph terms in same stage. Found both: search, graph"
```

### Integration with Pipeline Evaluator

**Parser Role**:
- Validates query structure and semantics
- Returns normalized stage structure
- Does NOT execute queries (that's pipeline evaluator's job)

**Integration Points**:
1. Pipeline evaluator calls `parse_and_validate()` on query
2. Parser returns list of validated stages
3. Pipeline executor determines stage type (search vs graph) using same logic
4. Pipeline routes each stage to appropriate executor

**Separation of Concerns**:
- Parser: Structure and semantic validation
- Pipeline: Query execution orchestration
- Search Executor: Executes search stages (Task bees-u7v)
- Graph Executor: Executes graph stages (Task bees-s98)

## Search Executor Architecture

The Search Executor (`src/search_executor.py`) implements in-memory filtering of
tickets using search terms with AND semantics. Part of the query pipeline system.

### Design Overview

**Purpose**: Execute search stages from query pipeline by filtering in-memory
ticket data using exact match and regex patterns.

**Key Principle**: All search terms in a stage are ANDed together - a ticket must
match ALL terms to be included in results.

**Integration**: Called by PipelineEvaluator when executing search stages
(stages containing type=, id=, title~, label~ terms).

### Architecture Components

**SearchExecutor Class**:
- Four filter methods (one per search term type)
- One execute method (orchestrates AND logic)
- Stateless design (no instance state)
- Pure functions (no side effects)

**Data Structure**:
- Input: `Dict[str, Dict[str, Any]]` - ticket_id → ticket data
- Output: `Set[str]` - set of matching ticket IDs
- In-memory operation (no disk I/O)

### Filter Methods

**1. filter_by_type(tickets, type_value) → Set[str]**

Exact match on `issue_type` field.

Implementation:
- Iterate all tickets
- Compare `ticket['issue_type']` to `type_value`
- Return set of matching ticket IDs
- Handle missing issue_type field (exclude from results)


**2. filter_by_id(tickets, id_value) → Set[str]**

Exact match on ticket ID (dict key).

Implementation:
- Check if `id_value` exists as key in tickets dict
- Return singleton set if found, empty set otherwise
- O(1) constant time lookup via dict membership test


**3. filter_by_title_regex(tickets, regex_pattern) → Set[str]**

Regex match on `title` field.

Implementation:
- Compile regex with `re.IGNORECASE` flag (case-insensitive)
- Iterate all tickets
- Use `pattern.search()` on ticket title
- Handle missing title field (exclude from results)
- Raise re.error on invalid regex pattern


**4. filter_by_label_regex(tickets, regex_pattern) → Set[str]**

Regex match on ANY label in `labels` array.

Implementation:
- Compile regex with `re.IGNORECASE` flag
- Iterate all tickets
- For each ticket, iterate labels array
- Match if ANY label matches regex
- Break early on first label match (optimization)
- Handle missing/empty labels (exclude from results)


### Execute Method AND Logic

**execute(tickets, search_terms) → Set[str]**

Orchestrates multi-term filtering with AND semantics.

**Algorithm**:
```python
1. Start with all ticket IDs (result_ids = set(tickets.keys()))
2. For each search term:
   a. Parse term format (= for exact, ~ for regex)
   b. Route to appropriate filter method
   c. Get matching IDs from filter
   d. Intersect with current result_ids (AND logic)
   e. Short-circuit if result_ids becomes empty
3. Return final result_ids set
```

**AND Logic via Set Intersection**:
- Start with universal set (all tickets)
- Each filter produces constraint set (matching tickets)
- Intersection accumulates constraints: `result &= filter_result`
- Final result contains only tickets matching ALL constraints

**Short-circuit Optimization**:
- If any filter returns empty set, remaining filters skipped
- Saves computation when early term eliminates all candidates
- Common case: specific ID lookup eliminates all but one ticket

**Term Parsing**:
- Split on `=` for exact match terms (type=, id=)
- Split on `~` for regex terms (title~, label~)
- Validate term name (reject unknown terms)
- Raise ValueError on invalid format

**Error Handling**:
- ValueError: Invalid term format or unknown term name
- re.error: Invalid regex pattern (propagated from filter methods)
- Clear error messages indicating which term failed

### Performance

Time complexity is O(T × N) where T is terms and N is tickets. filter_by_id uses O(1) dict lookup. Short-circuit optimization stops processing when intermediate results become empty.

## Graph Executor Architecture

The Graph Executor (`src/graph_executor.py`) implements in-memory traversal of ticket relationships (parent, children, up_dependencies, down_dependencies) for the query pipeline. Zero disk I/O - all operations use pre-loaded ticket data. Single `traverse()` method handles all relationship types via parameterization with graceful error handling.

### Relationship Type Handling

**1. parent** - Single value traversal

Implementation:
```python
parent_id = ticket_data.get('parent')
if parent_id:
    related_ids.add(parent_id)
```


**2. children** - List traversal

Implementation:
```python
children = ticket_data.get('children', [])
if children:
    related_ids.update(children)
```


**3. up_dependencies** - List traversal (blockers)

Implementation:
```python
up_deps = ticket_data.get('up_dependencies', [])
if up_deps:
    related_ids.update(up_deps)
```


**4. down_dependencies** - List traversal (blocked)

Implementation:
```python
down_deps = ticket_data.get('down_dependencies', [])
if down_deps:
    related_ids.update(down_deps)
```


### Edge Case Handling

**Invalid graph terms**:
```python
if graph_term not in valid_terms:
    logger.warning(f"Invalid graph term '{graph_term}', returning empty set")
    return set()
```

**Missing ticket IDs**:
```python
if ticket_id not in tickets:
    logger.warning(f"Ticket {ticket_id} not found in ticket data, skipping")
    continue
```

**None/empty ticket IDs**:
```python
if not ticket_id:
    logger.warning("Encountered None or empty ticket ID in input set, skipping")
    continue
```

**Missing relationship fields**:
```python
parent = ticket_data.get('parent')  # Returns None if missing
children = ticket_data.get('children', [])  # Returns [] if missing
```

### In-Memory Data Structure Design

**Ticket Dictionary Format**:
```python
tickets = {
    'ticket_id': {
        'id': 'ticket_id',
        'issue_type': 'epic|task|subtask',
        'title': 'Ticket Title',
        'parent': 'parent_id' or None,
        'children': ['child_id1', 'child_id2'],
        'up_dependencies': ['blocking_id1'],
        'down_dependencies': ['blocked_id1'],
        # ... other fields
    }
}
```


### Relationship Field Lookup Strategy

**Direct field access** (no iteration):
```python
# Parent lookup: O(1)
parent = tickets[ticket_id].get('parent')

# Children lookup: O(1) field access, O(k) to add k children
children = tickets[ticket_id].get('children', [])
related_ids.update(children)
```

**Why not recursive traversal**:
- Graph executor only does single-hop traversal
- Multi-hop queries use multiple graph stages
- Keeps executor simple and predictable
- Allows pipeline to control traversal depth

**Why no disk I/O**:
- All tickets pre-loaded by PipelineEvaluator
- Relationship data already parsed from YAML
- Executor just looks up fields in memory
- Orders of magnitude faster than disk reads

### Performance and Integration

Time complexity O(n) where n is input ticket count. Zero disk I/O during traversal - 100-1000x faster than disk-based approach. Pipeline loads all tickets once and routes to appropriate executor based on stage type. Graceful error handling returns partial results for missing tickets rather than failing query.


## Pipeline Evaluator Architecture

### Overview

The Pipeline Evaluator (`src/pipeline.py`) is the central orchestrator for executing multi-stage query pipelines. It implements the complete pipeline execution workflow from ticket loading through stage execution to result collection.

**Core Responsibility**: Load tickets once, execute stages sequentially with result passing, deduplicate, short-circuit, and return final matching ticket IDs.

### Component Architecture

```
PipelineEvaluator
├── Ticket Loading (initialization)
│   ├── Scan tickets/ directory (epics/, tasks/, subtasks/ subdirectories)
│   ├── Parse markdown files with YAML frontmatter
│   ├── Normalize ticket structure
│   └── Build reverse relationships
├── Stage Type Detection
│   ├── Search terms: type=, id=, title~, label~
│   └── Graph terms: parent, children, up_dependencies, down_dependencies
├── Executor Routing
│   ├── SearchExecutor (search stages)
│   └── GraphExecutor (graph stages)
└── Query Execution
    ├── Sequential stage processing
    ├── Result passing between stages
    ├── Deduplication after each stage
    └── Short-circuit on empty results
```

### In-Memory Data Structure Design

**Normalized ticket format** (executor-friendly):
```python
{
    'ticket_id': {
        'id': str,                       # Ticket identifier
        'title': str,                    # Ticket title
        'issue_type': str,               # epic|task|chore
        'status': str,                   # open|closed|in_progress
        'labels': list[str],             # Categorization labels
        'parent': str | None,            # Parent ticket ID (single)
        'children': list[str],           # Child ticket IDs (multiple)
        'up_dependencies': list[str],    # Blocking tickets (dependencies)
        'down_dependencies': list[str],  # Blocked tickets (dependents)
    }
}
```


### Ticket Loading Process

**Two-pass loading algorithm**:

**Pass 1 - Normalization** (load from tickets/ directory):
1. Read markdown files from tickets/epics/, tickets/tasks/, tickets/subtasks/
2. Parse YAML frontmatter to extract ticket metadata
3. Extract ticket ID (skip if missing with warning)
4. Convert YAML format → executor format:
   - Copy: id, title, issue_type, status, labels
   - Initialize: parent=None, children=[], up_dependencies=[], down_dependencies=[]
   - Parse dependencies from frontmatter:
     - parent field → set parent field
     - blocked_by array → append to up_dependencies
     - blocks array → append to down_dependencies
5. Store in tickets dict

**Pass 2 - Reverse Relationships** (in-memory):
1. For each ticket with parent:
   - Add ticket to parent's children list
2. For each ticket with up_dependencies:
   - Add ticket to blocker's down_dependencies list

**Why two passes**:
- Markdown files store relationships unidirectionally (child→parent, blocked→blocker)
- Graph traversal needs bidirectional (children, parent both directions work)
- Building reverse during load more efficient than on-demand during queries
- Single pass approach would require multiple file scans

**Memory usage**: O(n) where n = total tickets × avg ticket size

### Stage Execution Flow

**Sequential pipeline execution**:
```
Input: List of stages (from QueryParser)
Output: Set of ticket IDs matching all stages

1. Initialize current_results = all ticket IDs
2. For each stage:
   a. Detect stage type (search or graph)
   b. Route to appropriate executor
   c. Executor returns filtered/traversed ticket IDs
   d. Set current_results = executor result
   e. Deduplicate (set operations inherently dedupe)
   f. If current_results empty, break (short-circuit)
3. Return current_results
```

**Stage execution example**:
```yaml
Query: [['type=epic', 'label~beta'], ['children'], ['label~open']]

Stage 0 (search):
  Input: {all 100 tickets}
  Execute: SearchExecutor.execute(tickets, ['type=epic', 'label~beta'])
  Output: {bees-ep1, bees-ep2}  # 2 epics

Stage 1 (graph):
  Input: {bees-ep1, bees-ep2}
  Execute: GraphExecutor.traverse(tickets, input, 'children')
  Output: {bees-tk1, bees-tk2, bees-tk3, bees-tk4}  # 4 tasks

Stage 2 (search):
  Input: {bees-tk1, bees-tk2, bees-tk3, bees-tk4}
  Execute: SearchExecutor.execute(tickets, ['label~open'])
  Output: {bees-tk1, bees-tk3}  # 2 open tasks

Final result: {bees-tk1, bees-tk3}
```

### Stage Type Detection Logic

**Algorithm**:
```python
def get_stage_type(stage):
    search_prefixes = {'type=', 'id=', 'title~', 'label~'}
    graph_terms = {'parent', 'children', 'up_dependencies', 'down_dependencies'}

    has_search = any(any(term.startswith(p) for p in search_prefixes) for term in stage)
    has_graph = any(term in graph_terms for term in stage)

    if has_search and has_graph:
        raise ValueError("Mixed stage types")
    elif has_search:
        return 'search'
    elif has_graph:
        return 'graph'
    else:
        raise ValueError("Unrecognized terms")
```

**Why not regex for detection**:
- Simple string prefix matching faster than regex
- Fixed set of terms (no variability)
- Clear error messages for invalid terms

### Routing to Executors

**Search stage routing**:
```python
if stage_type == 'search':
    current_results = self.search_executor.execute(self.tickets, stage)
```
- Passes entire ticket dict + search terms
- SearchExecutor applies AND logic across terms
- Returns set of matching ticket IDs

**Graph stage routing**:
```python
else:  # graph
    for term in stage:
        current_results = self.graph_executor.traverse(
            self.tickets,
            current_results,
            term
        )
        if not current_results:
            break
```
- Multiple graph terms in stage ANDed via sequential execution
- Each term filters previous results
- Short-circuit within stage if empty

**Why different routing**:
- Search: all terms processed together (AND logic in executor)
- Graph: terms chained (each narrows result set)
- Graph terms independent (children≠parent≠dependencies)

### Deduplication Strategy

**Automatic deduplication via sets**:
- Executor return type: `set[str]` (ticket IDs)
- Set operations inherently remove duplicates
- No explicit dedup needed in pipeline code

**When duplication occurs**:
```python
# Multiple children have same parent
Stage 1: Get tasks → {tk1, tk2}
Stage 2: Get parent → returns [ep1, ep1]  # Duplicates!
Stage 2 result: {ep1}  # Set automatically dedupes
```

**Performance**: O(1) per insertion, O(m) total where m = result size

### Execution Optimization

Short-circuit optimization stops execution when any stage returns empty results, saving unnecessary work. Batch execution loads tickets once in __init__ and reuses for all queries. Set-based deduplication automatically handles multiple paths to same ticket.

### Executor Integration

SearchExecutor handles type/id/title/label filtering with AND logic. GraphExecutor traverses parent/children/up_dependencies/down_dependencies relationships. Pipeline routes stages to appropriate executor and chains results.

### Performance and Error Handling

Initialization is O(n) for loading all tickets. Query execution is O(s × m) where s is stages and m is tickets per stage. Pipeline fails fast on structural issues while GraphExecutor handles missing tickets gracefully.

### Future Enhancements

**Query optimization**:
- Analyze stage selectivity (run most restrictive first)
- Requires statistics on ticket data (label distributions)

**Incremental updates**:
- Watch tickets/ directory for changes
- Update in-memory tickets incrementally
- Avoids full reload on every change

**Query caching**:
- Cache query results keyed by query hash
- Invalidate on ticket updates
- Requires change detection mechanism

**Distributed execution**:
- Split ticket data across multiple processes
- Aggregate results from parallel executors
- Benefit for very large ticket sets (>10K tickets)

## Linter Infrastructure Architecture

The linter validates ticket schema compliance and relationship consistency, providing
structured error reporting to identify database corruption issues. It is designed to
be extensible, allowing additional validation rules to be added by other tasks.

### Architectural Components

**Linter Report Module** (`src/linter_report.py`):
- `ValidationError` dataclass: Represents a single validation error
  - Fields: `ticket_id`, `error_type`, `message`, `severity`
  - Severity levels: `error` (critical) or `warning` (non-critical)
- `LinterReport` class: Collection of validation errors with query and formatting capabilities
  - Error collection: `add_error()` method for adding validation errors
  - Error querying: `get_errors()` with filters by ticket_id, error_type, severity
  - Corruption check: `is_corrupt()` returns true if database has critical errors
  - Report generation: `to_json()`, `to_markdown()`, `to_dict()` for formatted output
  - Summary statistics: `get_summary()` returns error counts by type and severity

**Linter Module** (`src/linter.py`):
- `TicketScanner` class: Loads tickets from filesystem
  - Uses existing `src/reader.py` module to load ticket markdown files
  - Scans `tickets/epics/`, `tickets/tasks/`, `tickets/subtasks/` directories
  - Returns generator of `Ticket` objects (Epic, Task, or Subtask)
  - Handles filesystem errors gracefully, logging and skipping invalid files
  - Tickets with invalid schemas (caught by reader's validator) are skipped during load
- `Linter` class: Orchestrates validation checks
  - `run()` method: Main entry point for linting
    - Loads all tickets via TicketScanner
    - Runs per-ticket validations via `validate_ticket()`
    - Runs cross-ticket validations (e.g., uniqueness checks)
    - Returns `LinterReport` with all collected errors
  - `validate_ticket()` stub method: Extensible validation entry point
    - Currently calls `validate_id_format()`
    - Other tasks will extend this method with additional validation rules
  - `validate_id_format()`: Validates ticket ID matches `bees-[a-z0-9]{3}` pattern
    - Reuses `is_valid_ticket_id()` from `src/id_utils.py`
    - Adds validation error for malformed IDs
  - `validate_id_uniqueness()`: Detects duplicate IDs across all ticket types
    - Scans all loaded tickets, tracking seen IDs
    - Adds validation error for each duplicate found

### Integration Points

**Integration with Ticket Store**:
- Linter uses `src/reader.py` to load tickets
- Reuses existing `Ticket`, `Epic`, `Task`, `Subtask` models from `src/models.py`
- No need for separate data structures
- Reader's validator catches schema violations during load
  - Invalid tickets never reach the linter
  - Linter focuses on cross-ticket validation issues

**Integration with ID Utilities**:
- Reuses `is_valid_ticket_id()` from `src/id_utils.py`
- Avoids duplicating ID format validation logic
- Ensures consistent ID validation across codebase

**Extension by Other Tasks**:
- Task bees-ivvz (Bidirectional Relationship Validation): ✅ COMPLETED
  - Added `validate_parent_children_bidirectional()` method for parent/children consistency
  - Added `validate_dependencies_bidirectional()` method for dependency consistency
  - Integrated validators into main `run()` workflow
  - See detailed implementation below
- Task bees-2u6v (Cyclical Dependency Detection): ✅ COMPLETED
  - Added `detect_cycles()` method using DFS graph traversal
  - Detects cycles in both blocking dependencies and hierarchical relationships
  - Integrated into main `run()` workflow after all tickets loaded
  - See detailed implementation below
- Task bees-qcx7 (CLI Integration and Corruption State):
  - Will create CLI command to run linter
  - Will save corruption reports to `.bees/corruption_report.json`
  - Will add MCP server startup check that refuses to run if database corrupt

## Cyclical Dependency Detection (bees-2u6v)

### Algorithm Choice

**DFS with path tracking** was selected for cycle detection because it achieves optimal O(V+E) time complexity while naturally maintaining the path from root to current node, making cycle extraction trivial. DFS is a well-established algorithm for detecting cycles in directed graphs with proven correctness.

### Data Structure Design

**Path tracking with dual representation** uses both a list (for ordered cycle extraction) and a set (for O(1) cycle detection) to balance human-readable error reporting with performance. The global visited set prevents redundant traversals across disconnected components, avoiding exponential blowup in highly connected graphs.

**Separate passes for relationship types** run independent DFS traversals for blocking dependencies versus hierarchical relationships, enabling targeted error messages and preventing false positives from mixing relationship semantics.

## Bidirectional Relationship Validation (bees-ivvz)

### Validation Strategy

**Bidirectional consistency enforcement** validates both directions of parent/child and dependency relationships to catch asymmetric corruption regardless of which side is broken. Uses ticket lookup maps (O(1) access) instead of linear search for performance on large databases.

**Granular error types** (orphaned_child, orphaned_parent, orphaned_dependency, missing_backlink) enable targeted error messages with specific fix instructions, helping users quickly identify which direction the relationship is broken.

**Graceful handling of missing references** skips validation when referenced tickets don't exist, treating broken references as a separate error class to prevent cascading duplicate errors for the same underlying issue.

**Error Message Templates**:
- Orphaned child: "Ticket '{child_id}' lists '{parent_id}' as parent, but
  '{parent_id}' does not list '{child_id}' in its children"
- Orphaned parent: "Ticket '{parent_id}' lists '{child_id}' as child, but
  '{child_id}' does not list '{parent_id}' as its parent"
- Orphaned dependency: "Ticket '{ticket_id}' lists '{upstream_id}' in
  up_dependencies, but '{upstream_id}' does not list '{ticket_id}' in its
  down_dependencies"
- Missing backlink: "Ticket '{ticket_id}' lists '{downstream_id}' in
  down_dependencies, but '{downstream_id}' does not list '{ticket_id}' in its
  up_dependencies"

### Integration Points

**Relationship Sync Tools**:
- Future enhancement: Auto-fix capability using relationship sync functions
- Can leverage existing `update_ticket()` from `src/writer.py`
- Linter detects issues, sync tools can repair them
- Two-phase approach: detect (linter) then fix (sync)

**MCP Server Validation**:
- Relationship errors mark database as corrupt
- MCP server will refuse to start with corrupt relationships
- Forces manual fix before allowing ticket operations
- Prevents propagating bad data through API

## File System Watcher Architecture

## Future Considerations

- MCP server delete tool implementation (Task bees-49g)
- MCP server startup script and configuration (Task bees-nas)
- Change tracking/audit log
- Migration utilities for existing ticket systems

## Named Query System

Allows registration of reusable query templates with parameter substitution. Queries stored persistently in `.bees/queries.yaml` with YAML format. Uses `{param_name}` placeholders for dynamic values.

### Components

**Query Storage** (`src/query_storage.py`): Manages `.bees/queries.yaml` with save/load/list operations. Two-mode validation: full validation for static queries, parse-only for parameterized queries (validates at execution after substitution).

**MCP Tools**: `add_named_query()` registers queries with optional validation bypass. `execute_query()` executes by name with JSON parameter substitution using regex pattern matching.
    - result_count: Number of matching tickets
    - ticket_ids: Sorted list of matching ticket IDs
    
    Raises:
    - ValueError: If query not found or execution fails
    """
```

### Integration with Query Pipeline

**Execution Flow**:

1. **Load Query**: `load_query(query_name)` retrieves stages from queries.yaml
2. **Parameter Substitution**: If params provided, substitute placeholders
3. **Pipeline Execution**:
   - Initialize PipelineEvaluator (loads tickets from tickets/ directory)
   - Call `execute_query(stages)`
   - Stages evaluated sequentially with result passing
4. **Return Results**: Sorted list of matching ticket IDs

**No Caching**:
- Each execution loads fresh ticket data from tickets/ directory
- Ensures results reflect current ticket state
- Future optimization: cache PipelineEvaluator instance

**Query Reuse**:
- Queries persisted to disk survive server restarts
- Can be shared via version control (queries.yaml in .bees/)
- Queries accessible across all MCP sessions

### Error Handling

**Save Time Errors**:
- Empty query name: "Query name cannot be empty"
- Invalid YAML: "Invalid YAML: ..."
- Invalid query structure: "Invalid query structure: Stage 0: ..."
- File I/O errors: "Failed to save query: ..."

**Execution Time Errors**:
- Query not found: "Query not found: X. Available queries: A, B, C"
- Missing parameters: "Missing required parameter: Y. Provided: Z"
- Invalid JSON params: "Invalid JSON in params: ..."
- Execution failure: "Failed to execute query 'X': ..."

**Graceful Degradation**:
- If queries.yaml missing or corrupted, returns empty query list
- If tickets/ directory missing, raises clear error with directory path
- All errors logged for debugging

### Future Enhancements

**Query Metadata**:
- Add description, author, created_at fields to queries
- Display metadata in list_queries()
- Searchable query registry

**Query Composition**:
- Allow queries to reference other queries
- Example: `- ref:open_items` expands to referenced query stages
- Enables building complex queries from simple parts

**Query Validation on Load**:
- Validate all stored queries on server startup
- Detect and report invalid queries early
- Optional: Auto-fix common issues

**Query Analytics**:
- Track query execution frequency and performance
- Identify slow queries for optimization
- Usage metrics for popular queries

**Query Permissions**:
- Read-only vs read-write queries
- User-specific query namespaces
- Shared vs private queries

**Query Result Caching**:
- Cache query results keyed by (query_name, params, tickets_hash)
- Invalidate on ticket updates (watch tickets/ directory modification time)
- Significant speedup for repeated executions


## File System Watcher - Timer Cleanup Mechanism

### Overview

The file system watcher (`src/watcher.py`) monitors the tickets directory and automatically
regenerates the index when ticket files change. It uses `threading.Timer` with a debounce
mechanism to batch rapid file changes into a single regeneration. To prevent resource leaks
and ensure graceful shutdown, a cleanup mechanism cancels any pending timer when the watcher
stops.

**Related Task**: bees-yzc2

### Architecture

**Problem Statement**:
When `observer.stop()` is called during shutdown (e.g., Ctrl+C), any pending `threading.Timer`
continues running until it fires or the process exits. This causes two issues:
1. Timer thread may fire after observer is stopped, causing errors
2. Resources (timer thread) are not properly cleaned up during graceful shutdown

**Solution**: Add a `cleanup()` method to `TicketChangeHandler` that cancels any pending timer,
and call it before `observer.stop()` in the shutdown path.

### Threading Considerations

**Timer Management**:
- `self._timer: threading.Timer | None` - Active timer instance or None
- `self._timer_lock: threading.Lock` - Protects timer state from race conditions
- All timer operations (create, cancel, clear) must acquire the lock

**Thread Creation Overhead**:
Each `threading.Timer` creates a new daemon thread when started. The timer thread waits for
the specified delay, then executes the callback function (`_do_regeneration`) in that thread
context. While this adds thread creation overhead, it's acceptable for this use case because:
- Index regeneration events are relatively infrequent (typically seconds or minutes apart)
- Thread creation cost (~milliseconds) is negligible compared to index regeneration time
- Daemon threads automatically terminate when the main program exits

**Thread Safety Requirements**:
1. Timer creation in `_trigger_regeneration()` must be atomic with timer cancellation
2. Cleanup must safely cancel timer even if regeneration callback is executing
3. Multiple calls to `cleanup()` must be idempotent and thread-safe

**Lock Usage Pattern**:
```python
with self._timer_lock:
    if self._timer is not None:
        self._timer.cancel()  # Stops timer if not yet fired
        self._timer = None
    self.pending_regeneration = False
```

### Graceful Shutdown Pattern

**Shutdown Sequence** (in `start_watcher()`):
```python
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logger.info("Stopping watcher...")
    event_handler.cleanup()      # Cancel pending timer first
    observer.stop()              # Stop watchdog observer
observer.join()                  # Wait for observer thread to finish
```

**Why This Order Matters**:
1. `cleanup()` first - Ensures timer won't fire during shutdown
2. `observer.stop()` second - Signals watchdog to stop processing events
3. `observer.join()` last - Blocks until observer thread terminates cleanly

### Integration with Watchdog Observer Lifecycle

**Observer States**:
- `observer.start()` - Starts file monitoring thread
- `observer.stop()` - Signals observer to stop (non-blocking)
- `observer.join()` - Waits for observer thread to finish (blocking)

**Event Handler Lifecycle**:
- Created before observer starts
- Receives events while observer is running
- Must cleanup resources before observer stops
- Should not create new timers after `cleanup()` is called

**Timer Lifecycle**:
1. File event triggers `_trigger_regeneration()`
2. Timer is created and scheduled to fire after debounce_seconds
3. If another event arrives, old timer is cancelled and new one is created
4. When timer fires, `_do_regeneration()` runs and clears timer reference
5. On shutdown, `cleanup()` cancels any pending timer before it fires

### Error Handling and Failure Modes

**Timer Execution Failures**:
When `_do_regeneration()` encounters an exception during index regeneration (e.g., file I/O
errors, parsing failures), the error is caught and logged at line 72 in `src/watcher.py`:
```python
except Exception as e:
    logger.error(f"Failed to regenerate index: {e}", exc_info=True)
finally:
    with self._timer_lock:
        self.pending_regeneration = False
        self._timer = None
```

The `finally` block ensures that even if regeneration fails, the pending state is reset and
the timer reference is cleared. This prevents the system from getting stuck in a "pending"
state and allows subsequent file changes to trigger new regeneration attempts.

**Lock Acquisition Behavior**:
The `threading.Lock` used for timer state protection (`self._timer_lock`) operates with
indefinite blocking by default. When a thread calls `with self._timer_lock:`, it will wait
indefinitely until the lock becomes available. This is acceptable because:
- Lock hold times are extremely brief (nanoseconds to microseconds)
- Lock is only held during timer state mutations (create, cancel, clear)
- Multiple threads queuing for the lock indicates rapid file changes, which is handled by
  the debounce mechanism cancelling and replacing timers

No explicit timeout is configured because lock contention is minimal and indefinite blocking
ensures no regeneration events are dropped due to lock unavailability.

**Why thread lock is necessary**:
- `_trigger_regeneration()` can be called from watchdog thread
- `cleanup()` is called from main thread during shutdown
- Without lock, race conditions could cause:
  - Timer cancelled after being checked for None
  - New timer created after cleanup completes
  - Double-cancel attempts on same timer

**Why cleanup is idempotent**:
- Can be called multiple times safely
- Handles case where no timer is pending
- Simplifies cleanup logic in complex shutdown scenarios

### Exception Handling Architecture

**Related Task**: bees-5oyn

**Problem Statement**:
In the `_do_regeneration()` method, timer state cleanup (lines 71-73 in the original implementation)
only executed on success. If `generate_index()` or `write_text()` raised an exception, the
`pending_regeneration` flag and `_timer` reference remained set, causing incorrect state that would
block future regenerations.

**Solution**: Move timer state cleanup into a `finally` block to ensure it always executes, even when
regeneration fails.

**Implementation Pattern**:
```python
def _do_regeneration(self):
    """Perform the actual index regeneration."""
    try:
        logger.info("Regenerating index due to ticket changes...")
        index_content = generate_index()
        index_path = get_index_path()
        index_path.write_text(index_content)
        logger.info(f"Index regenerated: {index_path}")
    except Exception as e:
        logger.error(f"Failed to regenerate index: {e}", exc_info=True)
    finally:
        with self._timer_lock:
            self.pending_regeneration = False
            self._timer = None
```

**Exception Safety Guarantees**:
- `pending_regeneration` flag is always reset, even if regeneration fails
- `_timer` reference is always cleared, preventing memory leaks
- Future regenerations can proceed normally after a failed regeneration
- The timer can still be cancelled or replaced by new events, even after a failure

**Thread Safety**:
- The `finally` block still acquires `_timer_lock` before updating state
- This ensures that state updates are synchronized with timer creation/cancellation in
  `_trigger_regeneration()` and cleanup in `cleanup()`
- Lock is only held for the brief state update, not during the regeneration work

