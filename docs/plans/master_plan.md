# Bees Master Plan

Technical architecture and implementation decisions for the Bees ticket management system.

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

**Design Rationale**:
- Short IDs are easy to reference and type
- Alphanumeric-only ensures URL safety and command-line compatibility
- Random generation avoids predictable sequences
- 3 characters provide sufficient space for most projects

**Alternatives Considered**:
- Sequential IDs (rejected: not suitable for distributed/concurrent creation)
- UUIDs (rejected: too long for human use)
- 4-character IDs (rejected: 3 chars sufficient, keeps IDs shorter)

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

**Design Rationale**:
- PyYAML is the standard Python YAML library
- safe_dump prevents arbitrary code execution
- Clean frontmatter improves human readability
- ISO datetime format is standard and easily parsable

**Alternatives Considered**:
- JSON frontmatter (rejected: less human-readable)
- TOML frontmatter (rejected: less common in markdown ecosystem)
- ruamel.yaml (rejected: PyYAML sufficient for our needs)

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

**Design Rationale**:
- Atomic writes prevent data corruption
- Automatic directory creation improves user experience
- Temp files use file descriptor from tempfile.mkstemp() for security

**Alternatives Considered**:
- Direct write (rejected: not atomic, can corrupt on failure)
- Write + fsync (rejected: unnecessary overhead for our use case)
- File locking (rejected: complexity not needed for write-once tickets)

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

**Design Rationale**:
- Separate functions for each type improve type safety
- Required parent for subtasks enforces hierarchy
- Optional custom IDs support migration scenarios
- Automatic timestamps improve auditability

**Alternatives Considered**:
- Single factory with type parameter (rejected: less type-safe)
- Builder pattern (rejected: overkill for simple creation)
- ORM-style models (rejected: violates markdown-first philosophy)

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

**Design Rationale**:
- **Scalability**: Separating ticket types into subdirectories prevents overcrowding
  as projects grow to hundreds or thousands of tickets
- **Organization**: Clear visual separation makes repository navigation easier
- **Type Safety**: Directory structure reinforces type constraints and makes invalid
  file locations immediately obvious
- **Consistency**: Links in generated index.md use these hierarchical paths,
  ensuring alignment between file system and navigation interface

**Test Coverage**:
The test suite (`tests/test_index_generator.py`) validates that:
- Index generation uses correct hierarchical paths for all ticket types
- Links work correctly with the subdirectory structure
- Path structure remains consistent across different ticket statuses
- Edge cases (empty sections, mixed types) handle paths correctly

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

**Design Rationale**:
- Path utilities centralize directory logic
- Current working directory approach supports multiple projects
- Automatic directory creation simplifies setup
- Type inference optimization reduces unnecessary I/O in validation paths

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

**Design Rationale**:
- Dataclasses provide type hints and automatic initialization
- Inheritance reduces duplication
- Post-init validation catches errors early

## Testing Strategy

### Unit Test Coverage

**ID Generation** (`tests/test_writer.py:TestIdGeneration`):
- Format validation
- Uniqueness testing (100 generated IDs)
- Collision detection
- Edge cases (None, empty, invalid formats)

**YAML Serialization** (`tests/test_writer.py:TestSerializeFrontmatter`):
- Basic fields, lists, multiline strings
- Special characters and unicode
- Datetime conversion
- None/empty value handling

**File Writing** (`tests/test_writer.py:TestWriteTicketFile`):
- Directory creation
- File content verification
- Path resolution
- Empty body handling

**Factory Functions** (`tests/test_writer.py:TestCreate*`):
- Required field validation
- Optional parameter handling
- Custom ID support
- Error cases (missing title/parent)

**Edge Cases** (`tests/test_writer.py:TestEdgeCases`):
- Long strings (500+ chars)
- Unicode and special characters
- Emoji support

### Test Infrastructure

- Uses pytest with tmp_path fixtures for isolation
- Temporary directory override for TICKETS_DIR
- Comprehensive error path testing
- 32 test cases with 100% pass rate

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
- **Testing**: Provide fixtures for reader/parser validation testing
- **Templates**: Serve as reference examples for users creating their own tickets
- **Integration Testing**: Verify end-to-end flow from creation to parsing

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

**Design Rationale**:
- Three-tier hierarchy matches Epic → Task → Subtask relationships
- Separate directories by type enable type-specific queries
- Consistent naming (sample-*.md) makes samples easy to identify
- Each sample in correct directory demonstrates proper file organization

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

**Design Rationale**:
- Sample IDs (bees-ep1, bees-tk1, bees-sb1) are memorable and distinct
- bees-dp1 as down_dependency is referenced but not created (acceptable for docs)
- Empty children arrays show future bidirectional sync without implementing it
- Demonstrates both relationship types in minimal example set

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

**Design Rationale**:
- Samples validate successfully without modification
- Demonstrate all schema requirements
- Test reader error handling paths (missing files, invalid format)
- Serve as regression tests for parser changes

### Three-Tier Hierarchy Design Rationale

**Epic Level** (User-facing features):
- Represents complete user-testable functionality
- High-level scope (e.g., "E-commerce Platform")
- Maps to product roadmap items
- May span multiple sprints/releases

**Task Level** (Implementation work):
- Represents logical units of work
- Technical scope (e.g., "Product Catalog API")
- Maps to pull requests or work assignments
- Typically 1-2 weeks of work

**Subtask Level** (Atomic actions):
- Represents single-responsibility actions
- Specific implementation details (e.g., "Create database schema")
- Maps to individual commits or sub-day work items
- Typically hours to 1 day of work

**Relationship Rules**:
- Epics contain Tasks (via parent field)
- Tasks contain Subtasks (via parent field)
- No cross-level dependencies (Epic cannot depend on Task)
- Same-level dependencies allowed (Task → Task)

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

**Design Rationale**:
- Single source of truth: Parent ID lives in child
- Bidirectional links improve query performance
- Empty children arrays show intent without premature implementation
- Linter enforcement ensures consistency across manual edits

## MCP Server Architecture

### Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket write operations (create, update, delete) while ensuring bidirectional consistency of all relationships. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets safely.

### Design Goals

1. **Bidirectional Consistency**: When a relationship is created/modified in one ticket, automatically update the reciprocal field in related tickets
2. **Schema Validation**: Enforce ticket type rules (e.g., subtasks must have parent, epics cannot)
3. **Atomic Operations**: All relationship updates succeed or fail together
4. **Tool-Based Interface**: Standard MCP tool schemas for interoperability
5. **Health Monitoring**: Server lifecycle management and readiness checks

### FastMCP Library Choice

**Selected**: FastMCP 2.14.4

**Rationale**:
- Production-ready framework (v2.0) with stable API
- Clean decorator-based tool registration
- Built-in validation and type checking
- Standard I/O transport support
- Active maintenance and community support

**Integration Approach**:
```python
from fastmcp import FastMCP

mcp = FastMCP("Bees Ticket Management Server")

@mcp.tool()
def create_ticket(...):
    # Tool implementation
```

**Alternatives Considered**:
- Official MCP Python SDK (rejected: lower-level, requires more boilerplate)
- Custom protocol implementation (rejected: unnecessary complexity)
- FastMCP 3.0 beta (rejected: not production-ready)

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

**Design Rationale**:
- Simple boolean flag sufficient for single-instance server
- Separate start/stop functions enable programmatic control
- Logging provides operational visibility
- Return dicts support monitoring/orchestration

**Alternatives Considered**:
- Class-based server with state machine (rejected: overkill for simple lifecycle)
- Singleton pattern (rejected: global module state cleaner)
- Context manager (rejected: FastMCP manages its own lifecycle)

### MCP Server Startup and CLI Integration

**Entry Point Architecture** (`src/main.py`):

The production entry point for the MCP server is `src/main.py`, which provides:
- Configuration file loading
- Signal handling for graceful shutdown
- Startup validation and error handling
- Integration with FastMCP server lifecycle

**Design Decision: src/main.py as Entry Point**:
- Separates server initialization logic from tool implementations
- Enables configuration-driven deployment
- Provides clean CLI interface via Poetry scripts
- Allows programmatic access to `src/mcp_server` for testing

**Alternatives Considered**:
- scripts/start_mcp.py (rejected: Poetry prefers src/ structure)
- __main__.py in package root (rejected: less explicit, harder to test)
- Entrypoint in mcp_server.py (rejected: mixing concerns, harder to maintain)

**Configuration Management**:

**Format Choice: YAML**
```yaml
# config.yaml
host: localhost
port: 8000
ticket_directory: ./tickets
```

**Rationale for YAML**:
- Human-readable and editable
- Supports comments for documentation
- Standard format for configuration files
- PyYAML is already a dependency
- Better for nested structures than .env files

**Alternatives Considered**:
- .env file (rejected: less structured, no comments, less readable)
- JSON config (rejected: no comments, less human-friendly)
- TOML config (rejected: requires additional dependency)
- Command-line arguments (rejected: too many options, harder to manage)

**Configuration Loading** (`src/main.py:load_config()`):
```python
def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    # Load and validate YAML configuration
    # Checks for required fields: host, port, ticket_directory
    # Raises clear errors for missing/malformed config
```

**Validation Approach**:
- Required field checking (host, port, ticket_directory)
- Automatic ticket directory creation if missing
- Clear error messages for user debugging
- Fail-fast on configuration errors

**Design Rationale**:
- Configuration file enforces explicit settings
- Validation prevents runtime errors from bad config
- Auto-directory creation improves UX
- Default config.yaml path supports standard deployment

**Server Lifecycle Flow**:

1. **Load Configuration**: Parse config.yaml, validate required fields
2. **Validate Environment**: Check ticket directory exists or create it
3. **Setup Signal Handlers**: Register SIGINT/SIGTERM handlers for graceful shutdown
4. **Display Startup Info**: Log host, port, ticket directory for operator visibility
5. **Start Server**: Call `start_server()` to set internal state
6. **Run FastMCP**: Call `mcp.run()` to enter server loop
7. **Handle Shutdown**: Signal handler calls `stop_server()` and exits cleanly

**Signal Handling** (`src/main.py:setup_signal_handlers()`):
```python
def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_callback()  # Calls stop_server()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
```

**Design Rationale**:
- SIGINT (Ctrl+C) and SIGTERM support standard Unix process management
- Graceful shutdown ensures cleanup before exit
- Logging provides operational visibility
- sys.exit(0) indicates clean shutdown

**Alternatives Considered**:
- atexit handlers (rejected: not called on signals)
- asyncio signal handling (rejected: FastMCP manages async internally)
- No signal handling (rejected: kills process without cleanup)

**Poetry Scripts Integration**:

**pyproject.toml Configuration**:
```toml
[tool.poetry.scripts]
start-mcp = "src.main:main"
```

**Usage**:
```bash
poetry run start-mcp
```

**Design Rationale**:
- Standard Poetry scripts mechanism
- Simple, memorable command name
- No need for shell scripts or wrapper files
- Poetry handles virtual environment activation

**Alternatives Considered**:
- Console_scripts entry point (rejected: Poetry scripts cleaner)
- Makefile target (rejected: requires make installed)
- Shell script wrapper (rejected: platform-dependent, unnecessary)
- Direct python -m src.main (rejected: longer, less user-friendly)

**Error Handling Strategy**:

**Error Types and Responses**:
1. **FileNotFoundError** (config.yaml missing): Log clear message, exit with code 1
2. **yaml.YAMLError** (malformed YAML): Log parsing error, exit with code 1
3. **ValueError** (invalid config): Log validation error, exit with code 1
4. **General Exception** (unexpected): Log with traceback, exit with code 1

**Design Rationale**:
- Specific exception handling for common failure modes
- Exit code 1 signals error to shell/orchestration systems
- Detailed logging helps debugging
- No silent failures - always report issues

**Alternatives Considered**:
- Continue with defaults on error (rejected: dangerous, hides config issues)
- Interactive prompts (rejected: breaks automation/containers)
- Fallback to hardcoded defaults (rejected: config file should be explicit)

**Extensibility Considerations**:

**Future Configuration Options**:
- TLS/SSL settings for secure connections
- Authentication/authorization configuration
- Rate limiting settings
- Logging level control
- Backup/recovery settings

**Design for Extension**:
- YAML format easily accommodates nested configuration
- load_config() validates only required fields, allows additional fields
- Configuration object passed through initialization chain
- Easy to add environment variable overrides

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

**Design Rationale**:
- Registered as MCP tool for standard access
- Returns rich status info for monitoring
- Simple implementation - checks global state flag
- No external dependencies to validate

**Usage Scenarios**:
- Kubernetes/Docker health probes
- Client connection validation
- Monitoring dashboards
- Debugging server state issues

**Alternatives Considered**:
- HTTP endpoint (rejected: MCP stdio transport doesn't support HTTP)
- Separate health check mechanism (rejected: MCP tool standard is sufficient)
- Dependency checks (deferred: current implementation has no external deps)

### Tool Schema Design and Registration

**Registration Pattern**:
FastMCP uses Python decorators to register tools. To expose both the MCP tool and the underlying function for testing:

```python
def _create_ticket(...):
    # Implementation
    pass

# Register with MCP and create callable reference
create_ticket = mcp.tool()(_create_ticket)
```

**Benefits**:
- `_create_ticket()` can be called directly in unit tests
- `create_ticket` is registered as MCP tool
- FastMCP handles schema generation from function signature
- Type hints automatically generate parameter schemas

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

**Design Rationale**:
- Type hints enable FastMCP to generate JSON schema automatically
- Optional parameters use Python defaults (None, False, "")
- Docstrings provide tool descriptions visible to clients
- Return type Dict[str, Any] supports flexible response formats

**Schema Evolution**:
- Stub implementations return {"status": "stub"} for testing
- Full implementations (in later Tasks) will use factory/reader/writer modules
- Schema remains unchanged when implementation is added

**Alternatives Considered**:
- Pydantic models for schemas (rejected: FastMCP uses type hints)
- JSON schema files (rejected: FastMCP generates from code)
- Separate schema definitions (rejected: duplicates function signatures)

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

**Design Rationale**:

**Why Validate Before Factory Call**:
- Fail fast before creating orphan tickets
- Clear error messages guide users to fix issues
- Prevents inconsistent state from partial failures
- Avoids creating ticket that must be manually cleaned up

**Why Separate Bidirectional Update Function**:
- Reusable across create/update/delete tools
- Testable independently of MCP server
- Clear separation of concerns (creation vs. sync)
- Centralized relationship logic

**Why Use infer_ticket_type_from_id for Validation**:
- Fast file existence check vs. full ticket parsing
- Don't need full ticket object just to validate existence
- Consistent with relationship_sync module patterns
- Performance optimization for validation-heavy operations

**Why Check Circular Dependencies Early**:
- Simplest case: same ticket in both up and down arrays
- More complex transitive cycles handled later if needed
- Prevents obvious errors before file writes
- Clear error message for common mistake

**Alternatives Considered**:

- **Validate after creation** (rejected: creates orphan tickets on validation failure)
- **No relationship updates** (rejected: violates bidirectional consistency goal)
- **Load full tickets for validation** (rejected: unnecessary overhead, slow)
- **Batch all writes** (deferred: would add complexity, current approach sufficient)

**Testing Strategy** (Task bees-0xl):

Comprehensive unit tests covering:
- Success cases: epic without parent, task with parent, subtask with required parent
- Bidirectional updates: parent/children, up/down dependencies
- Error cases: empty title, epic with parent, subtask without parent
- Validation errors: non-existent parent, non-existent dependencies
- Edge cases: circular dependencies, invalid ticket_type

**Performance Considerations**:

- Validation phase: O(R) where R = number of related tickets (parent + children + dependencies)
- Creation phase: O(1) - single file write via factory
- Sync phase: O(R) - one file write per related ticket
- Total: O(R) file writes, acceptable for typical relationship counts (<10)
- Future optimization: Batch relationship updates if R is large

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

**Design Rationale**:
- Start simple with sensible defaults
- FastMCP handles complex protocol details
- Configuration deferred until needed
- Module-level server instance enables easy testing

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

### Testing Strategy

**Test Coverage** (`tests/test_mcp_server.py`):

1. **Server Initialization** (3 tests):
   - Server instance creation
   - Configuration validation (name, version)
   - Required attribute presence

2. **Lifecycle Management** (5 tests):
   - start_server() success
   - stop_server() success
   - Multiple start/stop cycles
   - Logging verification
   - Exception handling

3. **Health Check** (3 tests):
   - Health check when running
   - Health check when stopped
   - Response structure validation

4. **Tool Registration** (8 tests):
   - All tools callable
   - create_ticket stub response
   - Validation: ticket_type enum
   - Validation: epic parent rule
   - Validation: subtask parent requirement

5. **Error Handling** (2 tests):
   - Exception handling in start_server
   - Exception handling in stop_server

6. **Configuration** (2 tests):
   - Version presence and format
   - Name presence and format

**Test Infrastructure**:
- Direct function calls to `_health_check()`, `_create_ticket()`, etc.
- Mock logger for logging verification
- pytest fixtures for isolation
- 23 tests with 100% pass rate

**Design Rationale**:
- Test underlying functions, not FastMCP tool wrappers
- Comprehensive validation testing for schema enforcement
- Lifecycle testing ensures state management works
- Error path testing prevents production failures

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
- Default: stdio (standard input/output)
- Future: HTTP transport for web clients
- Future: WebSocket for persistent connections

**Logging**:
- Python logging module with INFO level
- Timestamps and module names in format
- Critical for debugging tool calls
- Future: Structured logging for log aggregation

**Monitoring**:
- health_check tool for operational status
- Logging provides call traces
- Future: Metrics (request count, latency, errors)
- Future: OpenTelemetry integration

**Design Rationale**:
- stdio transport simplest for agent integration
- Logging essential for operational visibility
- Health check enables automated monitoring
- Extensibility for future production needs

## Relationship Synchronization Module

### Overview

The relationship synchronization module (`src/relationship_sync.py`) provides core functionality for maintaining bidirectional consistency of all ticket relationships. When a relationship is added or modified in one ticket, this module ensures the reciprocal relationship is automatically updated in related tickets.

### Design Goals

1. **Bidirectional Consistency**: Parent/child and dependency relationships are always synchronized in both directions
2. **Validation**: Prevent invalid relationships (circular dependencies, type hierarchy violations)
3. **Atomicity**: Relationship operations update all affected tickets or fail cleanly
4. **Reusability**: Shared by create/update/delete MCP tools
5. **Performance**: Batch operations minimize file I/O overhead

### Core Helper Functions

**add_child_to_parent(parent_id, child_id)**:
- Updates parent's `children` array with child_id
- Sets child's `parent` field to parent_id
- Validates ticket existence and type hierarchy
- Idempotent: safe to call multiple times

**remove_child_from_parent(parent_id, child_id)**:
- Removes child_id from parent's `children` array
- Clears child's `parent` field (sets to None)
- Safe to call even if relationship doesn't exist

**add_dependency(dependent_id, blocking_id)**:
- Adds blocking_id to dependent's `up_dependencies` array (what blocks this ticket)
- Adds dependent_id to blocking's `down_dependencies` array (what this ticket blocks)
- Validates tickets exist and checks for circular dependencies
- Idempotent: prevents duplicate entries

**remove_dependency(dependent_id, blocking_id)**:
- Removes blocking_id from dependent's `up_dependencies` array
- Removes dependent_id from blocking's `down_dependencies` array
- Safe to call even if dependency doesn't exist

### Validation Functions

**validate_ticket_exists(ticket_id)**:
- Checks if ticket file exists before modifying relationships
- Searches all ticket type directories (epics/tasks/subtasks)
- Raises `FileNotFoundError` if ticket doesn't exist
- Called by all relationship operations to fail fast

**validate_parent_child_relationship(parent_id, child_id)**:
- Ensures type hierarchy is valid:
  - Epic can parent Task
  - Task can parent Subtask
  - Epic cannot parent Subtask directly
- Raises `ValueError` for invalid combinations
- Raises `FileNotFoundError` if either ticket doesn't exist
- Enforces three-tier hierarchy design
- **Performance Optimization**: Uses `infer_ticket_type_from_id()` instead of loading full tickets
  - Old approach: Load both tickets, parse YAML, extract type field
  - New approach: Check file location for type inference
  - Benefit: Avoids unnecessary YAML parsing and ticket object creation
  - Impact: Significantly faster validation, especially in bulk operations

**check_for_circular_dependency(ticket_id, new_dependency_id)**:
- Prevents dependency cycles using depth-first search
- Detects direct cycles (A depends on B, B depends on A)
- Detects transitive cycles (A → B → C → A)
- Prevents self-dependencies (A depends on A)
- Raises `ValueError` with descriptive error message

**_has_transitive_dependency(ticket_id, target_id, visited)**:
- Helper function for circular dependency detection
- Recursively explores dependency graph
- Uses visited set to prevent infinite loops
- Returns True if ticket_id transitively depends on target_id

### Batch Operations

**sync_relationships_batch(updates)**:
- Efficiently handles multiple relationship updates in a single operation
- Updates parameter format: `List[Tuple[ticket_id, field_name, operation, value]]`
  - `ticket_id`: The ticket to update
  - `field_name`: 'children', 'parent', 'up_dependencies', or 'down_dependencies'
  - `operation`: 'add' or 'remove'
  - `value`: The ID to add/remove

**Seven-Phase Execution with Atomicity Guarantees**:

1. **Validation Phase**: Check all tickets exist before making changes
2. **Loading Phase**: Load all affected tickets into memory once
3. **Deduplication Phase**: Remove duplicate operations to prevent redundant I/O
4. **Backup Phase (WAL)**: Create in-memory backup copies of original ticket state
5. **Update Phase**: Apply all changes to loaded ticket objects
6. **Write Phase with Rollback**: Write all modified tickets to disk
   - If any write fails, restore all tickets from backups
   - Log error details for debugging
   - Raise RuntimeError with original failure cause
7. **Cleanup Phase**: Clear backup references in finally block

**Transaction-Like Semantics**:
- If any validation fails, no changes are made
- If any update fails, error is raised before writes
- **Automatic deduplication**: Duplicate operations removed before execution using set conversion
- **Write-ahead logging (WAL)** enables rollback on partial failure
- **Atomicity guarantee**: All tickets written successfully or all restored to original state
- Reduces file I/O overhead when many relationships change (e.g., ticket deletion)

**Deduplication Design**:
- **Implementation**: Phase 3 converts update list to set, then back to list
- **Rationale**: Prevent redundant I/O operations (e.g., adding same child multiple times)
- **Performance Benefit**: Reduces file writes when duplicate operations batched together
- **Semantics Preserved**: Deduplication maintains batch correctness - final state identical
- **Example**: Adding same child twice results in single add operation

**Usage Example**:
```python
# When deleting a ticket, remove it from all related tickets
updates = [
    ("bees-ep1", "children", "remove", "bees-tk1"),
    ("bees-tk1", "parent", "remove", "bees-ep1"),
    ("bees-tk2", "up_dependencies", "remove", "bees-tk1"),
    ("bees-tk1", "down_dependencies", "remove", "bees-tk2"),
]
sync_relationships_batch(updates)
```

### Internal Helper Functions

**_load_ticket_by_id(ticket_id)**:
- Loads a ticket by ID, searching all type directories
- Tries each ticket type (epic, task, subtask) sequentially
- **Early Return Optimization**: Returns immediately when ticket found, skipping remaining directory checks
- Returns typed Ticket object (Epic, Task, or Subtask)
- Raises `FileNotFoundError` if ticket doesn't exist
- Used by all relationship operations to read current state

**Performance Optimization Details**:
The function uses an early return pattern to minimize filesystem access:
```python
for ticket_type in ["epic", "task", "subtask"]:
    try:
        path = get_ticket_path(ticket_id, ticket_type)
        ticket = read_ticket(path)
        return ticket  # Early return - no more directory checks
    except Exception:
        continue
```

**Performance Impact**:
- Epic tickets: Only 1 directory check (best case)
- Task tickets: Maximum 2 directory checks (epic fails, task succeeds)
- Subtask tickets: Maximum 3 directory checks (all directories searched)
- Average improvement: ~33% reduction in filesystem operations compared to checking all directories
- Especially beneficial during dependency validation and batch operations that load many tickets

This optimization was identified in code review (bees-r10) and implemented in Task bees-6xs.

**_save_ticket(ticket)**:
- Saves a ticket object back to its markdown file
- Builds frontmatter dictionary from ticket dataclass
- Preserves all ticket metadata (timestamps, owner, etc.)
- Uses atomic write operations from writer module
- Filters None and empty array values for clean YAML

### Integration with MCP Tools

**create_ticket Tool**:
- Calls relationship sync functions after creating ticket file
- If parent specified: calls `add_child_to_parent(parent, new_ticket_id)`
- If dependencies specified: calls `add_dependency()` for each
- Ensures parent and dependencies are updated immediately

**update_ticket Tool**:
- Compares old and new relationship values
- Adds new relationships: calls `add_child_to_parent()` or `add_dependency()`
- Removes old relationships: calls `remove_child_from_parent()` or `remove_dependency()`
- Handles partial updates (only specified fields changed)

**delete_ticket Tool**:
- Loads ticket to find all relationships
- Builds update list for batch cleanup:
  - Remove from parent's children array
  - Remove from children's parent fields
  - Remove from all dependency relationships
- Uses `sync_relationships_batch()` for efficiency
- Cascade mode: recursively deletes children

### Data Flow Diagram

```
MCP Tool (create/update/delete)
    ↓
Relationship Sync Module
    ↓
Validation Functions (check existence, hierarchy, cycles)
    ↓
_load_ticket_by_id (read current state)
    ↓
Relationship Modification (update in-memory objects)
    ↓
_save_ticket (atomic write to disk)
    ↓
Return to MCP Tool
```

### Error Handling Strategy

**Validation Errors**:
- Raised early before any file writes
- Clear error messages indicate what failed and why
- Examples:
  - "Ticket bees-xyz not found. Cannot modify relationships."
  - "Invalid parent-child relationship: epic cannot parent subtask"
  - "Circular dependency detected: bees-b already depends on bees-a"

**File I/O Errors**:
- Reader raises `ParseError` for malformed YAML
- Writer raises `OSError` if disk write fails
- Atomic writes prevent partial file corruption
- Callers can catch and retry or report to user

**Idempotency**:
- All operations safe to call multiple times
- Prevents duplicate entries in arrays
- Safe to call remove operations on nonexistent relationships
- Supports retry logic in higher-level orchestration

### Performance Considerations

**File I/O Optimization**:
- Each relationship operation requires 2 file reads + 2 file writes (parent and child)
- Batch operations load all tickets once, then write all modified tickets
- For ticket deletion with N relationships, batch reduces from 2N to N operations

**Caching Strategy** (future):
- Current implementation loads from disk for every operation
- Future: In-memory cache with timestamp-based invalidation
- Future: Write-behind buffer for batching writes
- Trade-off: Simplicity now vs. performance optimization later

**Scalability**:
- Linear performance with number of relationships
- Circular dependency check is O(E) where E is edges in dependency graph
- Typical graphs are small (10-100 tickets), so performance is acceptable
- For large graphs (1000+ tickets), consider graph database backend

### Testing Coverage

**Unit Tests** (`tests/test_relationship_sync.py`):
- 28 comprehensive tests with 100% pass rate
- 6 test classes covering all major functionality

**Test Categories**:
1. **Parent-Child Operations** (6 tests):
   - Add task to epic, subtask to task
   - Remove child from parent
   - Idempotent adds
   - Invalid hierarchy rejection
   - Nonexistent ticket handling

2. **Dependency Operations** (6 tests):
   - Add/remove dependency bidirectionally
   - Idempotent adds
   - Circular dependency prevention (direct and transitive)
   - Self-dependency prevention

3. **Batch Operations** (5 tests):
   - Add multiple children efficiently
   - Remove operations in batch
   - Invalid operation handling
   - Transaction-like failure semantics

4. **Validation Functions** (7 tests):
   - Ticket existence checking
   - Parent-child type hierarchy validation
   - Circular dependency detection (direct and transitive)

5. **Edge Cases** (4 tests):
   - Empty relationship arrays
   - Multiple children for same parent
   - Duplicate operations
   - Missing tickets

**Test Infrastructure**:
- Uses pytest fixtures with monkeypatched tmp_path
- Creates temporary ticket files with valid 3-character IDs
- Tests both success and failure paths
- Validates bidirectional updates by reading both tickets

### Design Rationale

**Why Separate Module**:
- Shared by all MCP tools (create/update/delete)
- Testable independently of MCP server infrastructure
- Clear separation of concerns (sync vs. tool logic)
- Reusable for future features (linter, migration scripts)

**Why Bidirectional Updates**:
- Query performance: Can find ticket's children without scanning all tickets
- Data integrity: Both sides of relationship always consistent
- User experience: Parent-child links visible when viewing either ticket
- Debugging: Easier to trace relationships and find orphans

**Why Validation First**:
- Fail fast before modifying any files
- Clear error messages guide users to fix issues
- Prevents inconsistent state from partial failures
- Type hierarchy enforcement at sync layer, not just schema

**Why Batch Operations**:
- Ticket deletion requires updating many related tickets
- Reduces file I/O from O(2N) to O(N) for N relationships
- Transaction-like semantics improve reliability
- Performance optimization without complexity

**Alternatives Considered**:
- **Graph database backend** (rejected: markdown-first philosophy, added complexity)
- **Async writes** (rejected: stdio transport is synchronous, premature optimization)
- **Event sourcing** (rejected: overkill for current scale)
- **Manual relationship management** (rejected: error-prone, inconsistent)

### Integration with Reader/Writer Modules

**Path Utilities Module** (`src/paths.py`):
- `validate_parent_child_relationship()` uses `infer_ticket_type_from_id()` for lightweight type checking
- Type inference checks file existence in type directories without parsing content
- Significantly faster than loading full ticket objects for validation
- Integration approach: Import function, call for both parent_id and child_id, validate hierarchy
- Returns None for nonexistent tickets, triggering FileNotFoundError in validation

**Reader Module** (`src/reader.py`):
- `_load_ticket_by_id()` uses `read_ticket()` to parse markdown files
- Validates YAML frontmatter and returns typed ticket objects
- Handles datetime parsing and field filtering
- Propagates `ParseError` and `ValidationError` to callers

**Writer Module** (`src/writer.py`):
- `_save_ticket()` uses `write_ticket_file()` for atomic writes
- Serializes frontmatter with `serialize_frontmatter()`
- Creates directories automatically via `ensure_ticket_directory_exists()`
- Uses temp file + rename pattern for atomicity

**Path Utilities** (`src/paths.py`):
- `_load_ticket_by_id()` uses `get_ticket_path()` to construct file paths
- Searches across all ticket type directories (epics/tasks/subtasks)
- Consistent path resolution across all operations

### File Locking Implementation

**Purpose**: Prevent concurrent modification issues when multiple processes access the same ticket files simultaneously.

**Implementation Location**: `src/relationship_sync.py:_save_ticket()`

**Platform-Specific Locking**:
- **Unix/macOS**: Uses `fcntl.flock()` with `LOCK_EX | LOCK_NB` flags
  - Exclusive lock prevents other processes from reading or writing
  - Non-blocking mode allows immediate failure detection
  - Lock automatically released when file handle closes
- **Windows**: Uses `msvcrt.locking()` with `LK_NBLCK` mode
  - Equivalent behavior to Unix fcntl
  - Non-blocking exclusive lock
  - Released on file close

**Retry Logic with Exponential Backoff**:
- **Max Retries**: 3 attempts per save operation
- **Retry Delays**: [0.1s, 0.2s, 0.4s] - exponential backoff
- **Total Max Wait**: ~0.7 seconds before failure
- **Logging**: WARNING level for each retry attempt with attempt count and delay

**Lock Acquisition Flow**:
1. Open file for read+write (or create if doesn't exist)
2. Attempt to acquire non-blocking exclusive lock
3. If successful: write ticket data and close (lock auto-released)
4. If failed: log warning, sleep for backoff duration, retry
5. After max retries: raise `RuntimeError` with clear error message

**Error Handling**:
- **Lock Acquisition Failure**: Raises `RuntimeError` after max retries
  - Message: "Failed to acquire file lock for {ticket_id} after 3 attempts. Another process may be modifying this ticket."
  - Caller should report to user and potentially retry after brief delay
- **Unexpected Errors**: Log error and re-raise exception for handling by caller
- **Debug Logging**: Successful saves logged at DEBUG level

**Design Rationale**:

**Why OS-Level File Locking**:
- Native OS primitives are battle-tested and reliable
- Cross-platform support via Python standard library (fcntl, msvcrt)
- No external dependencies (no lock server, no database)
- Integrates seamlessly with existing file-based architecture
- Atomic at file descriptor level - survives process crashes

**Why Not Database Transactions**:
- Violates markdown-first design philosophy
- Requires external database server (adds complexity)
- Harder to version control and diff
- Not human-readable in raw form
- Overkill for current scale and use case

**Why Not Lock Files (.lock)**:
- Requires manual cleanup on crash (stale lock detection)
- Race condition between checking and creating lock file
- Not atomic without additional OS-level locking anyway
- More complexity for same result

**Why Not Optimistic Locking**:
- Requires version numbers/timestamps in ticket files
- Conflict resolution logic complex and error-prone
- User experience poor when conflicts occur frequently
- Doesn't prevent concurrent writes, just detects them

**Why Non-Blocking Mode**:
- Blocking mode would hang indefinitely on high contention
- Non-blocking + retry allows controlled timeout behavior
- Retry logic gives user clear feedback about delays
- Prevents deadlocks in complex scenarios

**Performance Implications**:
- **Single Process**: Minimal overhead (~microseconds to acquire lock)
- **Low Contention**: Brief delay if lock held, typically acquires on first retry
- **High Contention**: Up to 0.7s delay before failure, prevents resource exhaustion
- **Scalability**: Linear performance degradation with concurrent writers
- **File I/O**: No additional disk operations beyond existing writes

**Cross-Platform Considerations**:
- Platform detection via `platform.system() == "Windows"`
- Conditional import of `msvcrt` on Windows only
- `fcntl` imported by default (Unix/macOS)
- Lock semantics identical across platforms (exclusive, non-blocking)
- Tested on macOS (Darwin), expected to work on Linux and Windows

**Integration with Relationship Sync Module**:
- All relationship sync operations (`add_child_to_parent`, `add_dependency`, etc.) automatically use file locking
- No changes needed to calling code - locking is transparent
- Batch operations (`sync_relationships_batch`) acquire locks per-ticket during write phase
- Lock granularity: per-file (not per-directory or per-relationship)

**Alternatives Considered**:
- **Advisory vs Mandatory Locking**: Advisory locking chosen (standard Unix practice)
  - Mandatory locking requires mount options and is OS-dependent
  - Advisory locks sufficient when all code uses same locking protocol
- **Shared vs Exclusive Locks**: Exclusive locks chosen for simplicity
  - Could optimize with shared locks for reads, exclusive for writes
  - Current read-modify-write pattern requires exclusive locks anyway
- **Lock Scope**: File-level locking chosen over finer granularity
  - Could lock individual relationship fields with complex protocol
  - File-level is simple, atomic, and sufficient for current workload

**Testing Strategy** (covered in Task bees-8hdo):
- Successful lock acquisition and release
- Concurrent access simulation with multiple processes
- Lock acquisition retry with exponential backoff verification
- Max retry exhaustion raises correct exception
- Cross-platform compatibility testing (Unix/Windows mocking)
- Integration with existing relationship sync tests

**Monitoring and Debugging**:
- Lock acquisition failures logged at WARNING level with retry count
- Successful operations logged at DEBUG level
- RuntimeError message includes ticket ID and max retry count
- Logs suitable for alerting on repeated lock contention

### Atomicity Implementation Details

**Problem**: Partial Write Failures

The original batch sync implementation had a critical flaw: if a write operation failed partway through Phase 4 (writing modified tickets), some tickets would be updated while others remained in their original state. This partial write problem could lead to data loss and inconsistent relationship state.

**Solution**: Write-Ahead Logging (WAL) with Rollback

Implemented in Task bees-792, the solution adds transaction-like semantics using write-ahead logging:

**Phase 3 - Backup Creation (WAL)**:
```python
# Store original ticket state in memory before modifications
backups = {}
for ticket_id, ticket in tickets.items():
    backups[ticket_id] = _load_ticket_by_id(ticket_id)  # Deep copy via reload
```

**Design Rationale**:
- In-memory backups avoid additional disk I/O overhead
- Reloading tickets creates independent copies (avoids reference aliasing)
- Dict structure enables O(1) lookup by ticket_id for rollback

**Phase 5 - Write with Rollback Protection**:
```python
try:
    for ticket in tickets.values():
        _save_ticket(ticket)
except Exception as e:
    # Rollback: restore all tickets from backups
    logger.error(f"Write failure during batch sync, rolling back: {e}")
    for ticket_id, backup_ticket in backups.items():
        try:
            _save_ticket(backup_ticket)
        except Exception as rollback_error:
            logger.error(f"Rollback failed for {ticket_id}: {rollback_error}")
    raise RuntimeError(f"Batch write failed and rollback attempted. Original error: {e}") from e
```

**Rollback Behavior**:
- **Immediate Rollback**: On first write failure, rollback begins immediately
- **Best-Effort Restoration**: Each backup is written individually with error logging
- **Error Propagation**: Original error wrapped in RuntimeError for caller
- **Logging Strategy**: Separate errors logged for main failure and any rollback failures

**Phase 6 - Cleanup**:
```python
finally:
    # Clear backup references to prevent memory leaks
    backups.clear()
```

**Design Rationale**:
- `finally` block ensures cleanup happens even on exception
- `clear()` releases all references for garbage collection
- Prevents memory leaks in long-running processes

**Atomicity Guarantees**:

1. **All-or-Nothing Writes**: Either all tickets commit or all are restored to original state
2. **No Partial State**: If any write fails, rollback ensures consistency
3. **Idempotent Operations**: Rollback writes are safe to retry (atomic file writes)
4. **Error Transparency**: Original failure cause preserved and re-raised

**Error Handling Scenarios**:

**Scenario 1: Successful Batch**
- All writes succeed
- Backups cleared in finally block
- No exceptions raised

**Scenario 2: Single Write Failure**
- Write fails on ticket N
- Rollback restores all tickets (1 through N)
- RuntimeError raised with original error
- All tickets remain in pre-batch state

**Scenario 3: Write + Rollback Failure**
- Write fails on ticket N
- Rollback fails on ticket M (rare)
- Both errors logged separately
- RuntimeError raised with original error
- Some tickets may be corrupted (rollback failure is exceptional)

**Performance Implications**:

**Time Complexity**:
- Original: O(N) file writes where N = number of modified tickets
- With WAL: O(N) backups + O(N) writes = O(2N) best case, O(3N) worst case (with rollback)
- Acceptable trade-off for atomicity guarantees

**Space Complexity**:
- O(N) additional memory for backups
- Each backup is a full Ticket object with all fields
- Typical ticket size: <2KB, so even 100 tickets = <200KB memory overhead

**Alternatives Considered**:

**Database Transactions** (rejected):
- Requires external database (violates markdown-first philosophy)
- Added complexity and operational overhead
- Not human-readable or version-controllable

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

**Testing Coverage**:

Comprehensive test suite in `tests/test_relationship_sync.py:TestAtomicityGuarantees`:

1. **test_successful_batch_update_commits_all_changes**: Verifies all changes committed on success
2. **test_partial_write_failure_triggers_rollback**: Mocks write failure, verifies rollback
3. **test_all_tickets_restored_on_failure**: Ensures original state restored after error
4. **test_no_partial_state_after_error**: Verifies no tickets partially updated
5. **test_wal_cleanup_after_success**: Confirms backups cleared on success
6. **test_wal_cleanup_after_rollback**: Confirms backups cleared even after failure

**Design Rationale Summary**:

**Why In-Memory WAL**:
- Simple implementation without external dependencies
- Fast - no additional disk I/O during backup phase
- Sufficient for current scale (typical batch <100 tickets)
- Easy to test and reason about

**Why Best-Effort Rollback**:
- Rollback failures are exceptional (disk full, filesystem errors)
- Logging provides visibility for manual recovery if needed
- Alternative (aborting rollback) leaves more tickets corrupted
- Better to attempt restoration of all tickets than fail fast

**Why RuntimeError Wrapping**:
- Original exception preserved in `__cause__` attribute
- Clear message indicates rollback was attempted
- Distinguishes batch failures from validation failures (ValueError)
- Stack trace includes both original and rollback context

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

**Design Rationale**:

**Why Diff-Based Sync**:
- Only updates changed relationships, not all relationships

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

**Design Decision**: Keep subtasks as orphaned rather than:
- Deleting them automatically (user may not expect this)
- Allowing invalid state (breaks validation)
- Promoting to tasks (changes ticket type semantics)

This is documented in README and error handling guides users to use `cascade=True` if they want subtasks deleted.

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

**Design Rationale**:

**Why Cleanup Before Delete**:
- Maintains referential integrity across all related tickets
- Prevents dangling references to deleted ticket
- Allows related tickets to remain valid after deletion
- Standard database cascade delete pattern

**Why Recursive Cascade**:
- Handles arbitrary depth hierarchies (Epic→Task→Subtask)
- Ensures all descendants cleaned up consistently
- Each ticket in hierarchy has relationships cleaned before deletion
- Natural depth-first traversal

**Why Not Unlink Subtasks**:
- Subtask validation requires parent (cannot be None)
- Allowing invalid state breaks schema consistency
- Forcing cascade delete would surprise users
- Orphaned subtasks are edge case, documented solution exists

**Why Depth-First Deletion**:
- Leaf nodes deleted first (bottom-up)
- Parent references valid until children deleted
- Matches database foreign key cascade behavior
- Simplifies recursion logic

**Alternatives Considered**:

- **Delete without cleanup** (rejected: creates dangling references, violates consistency)
- **Prevent delete if children exist** (rejected: requires cascade=True, less flexible)
- **Auto-promote subtasks to tasks** (rejected: changes semantics, confusing)
- **Batch relationship cleanup** (deferred: current approach sufficient, could optimize later)
- **Transaction wrapper with rollback** (deferred: complex, would add significant overhead)

**Testing Strategy** (Task bees-49g):

Comprehensive unit tests in `tests/test_delete_ticket.py`:
- Basic deletion: file removal, nonexistent ticket errors
- Parent cleanup: removing from parent's children array
- Dependency cleanup: removing from up_dependencies and down_dependencies arrays
- Cascade delete: recursive deletion of children
- Unlink behavior: cascade=false unlinks children (except subtasks)
- Edge cases: ticket with all relationship types, complex hierarchies

**Performance Considerations**:

- Deletion: O(1) - single file unlink
- Parent cleanup: O(1) - single file write to parent
- Dependency cleanup: O(D) where D = number of dependency relationships (typically <10)
- Cascade delete: O(N) where N = total descendants in hierarchy
- Total: O(N + D) - linear in number of affected tickets
- Worst case: Large epic with many tasks/subtasks and dependencies

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
- Testable independently
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

**Alternatives Considered**:

- **Separate add/remove relationship tools** (rejected: more verbose API, update is natural operation)
- **Load all related tickets upfront** (rejected: unnecessary overhead if not changing relationships)
- **Transaction wrapper** (deferred: added complexity, current approach sufficient)
- **Delta parameter format** (rejected: diff calculation is simpler than complex delta DSL)

**Testing Strategy** (Task bees-08d):

Comprehensive unit tests covering:
- Update basic fields (title, labels, status, owner, priority)
- Add parent relationship
- Remove parent relationship (set to None)
- Add children
- Remove children
- Add dependencies (up and down)
- Remove dependencies
- Bidirectional consistency verification for all relationship changes
- Error cases: non-existent ticket, invalid relationship IDs, empty title, circular dependencies

**Performance Considerations**:

- Validation phase: O(R) where R = number of new relationship IDs to validate
- Read phase: O(1) - single ticket read
- Update phase: O(1) - single ticket write
- Sync phase: O(C) where C = number of changed relationships
- Total: O(R + C) operations, acceptable for typical updates (<10 changes)
- Future optimization: Batch relationship updates if C is large

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

**Design Rationale**:
- Search terms need values (type=epic), so use prefix matching
- Graph terms have no parameters, so use exact matching
- Clear distinction prevents ambiguity
- Enables straightforward stage type detection

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

**Design Rationale**:
- Early validation prevents runtime regex errors
- Clear error messages guide users to fix patterns
- Supports complex filtering without structural OR operator
- Follows PRD specification for OR/NOT via regex

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

**Design Rationale**:
- Clear errors reduce debugging time
- Stage indices help locate issues in multi-stage queries
- Showing valid options guides users toward correct syntax
- Detailed messages enable self-service problem resolution

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

### Testing Strategy

**Test Coverage** (tests/test_query_parser.py):
- Basic parsing (single/multi-stage queries)
- YAML string parsing
- Search term validation (all term types)
- Graph term validation
- Stage purity enforcement
- Regex pattern validation (valid, invalid, complex patterns)
- All PRD example queries
- Error message clarity
- parse_and_validate() convenience method

**Test Structure**:
- TestQueryParserBasics: Core parsing functionality
- TestSearchTermValidation: All search term types
- TestGraphTermValidation: Graph term validation
- TestStagePurityEnforcement: Mixed stage detection
- TestPRDExampleQueries: Real-world query examples
- TestParseAndValidate: Combined parse+validate
- TestRegexPatterns: Complex regex patterns
- TestErrorMessages: Error message quality

**Coverage**: 41 tests, 100% pass rate

### Performance Considerations

**Parse Phase**:
- O(S × T) where S = stages, T = terms per stage
- YAML parsing is fast (uses PyYAML C extensions when available)
- Minimal memory overhead (stages stored as simple lists)

**Validation Phase**:
- O(S × T) for term validation
- Regex compilation adds overhead per regex term
- Compiled patterns not cached (validation is one-time operation)
- Acceptable performance for typical queries (< 10 stages, < 5 terms/stage)

**Future Optimizations** (if needed):
- Cache compiled regex patterns if query executed multiple times
- Lazy validation mode (validate on first error only)
- Schema-based validation with jsonschema (more structured, potentially faster)

### Design Decisions

**Why YAML for Queries**:
- Human-readable and editable
- Supports lists and nesting naturally
- Standard format in markdown ecosystem
- PyYAML is stable and widely used

**Why AND-only Within Stages**:
- Simpler mental model (stages are filters)
- OR expressed via regex (keeps structure simple)
- Matches PRD requirement for AND semantics
- Stage composition provides flexibility

**Why Stage Purity Requirement**:
- Clear execution semantics (filter vs traverse)
- Simplifies pipeline routing logic
- Prevents ambiguous term ordering
- Matches PRD design specification

**Why Prefix-based Search Term Detection**:
- Search terms need values (type=epic)
- Prefix distinguishes term type from value
- Extensible (new search terms can be added)
- Clear syntax for users

**Why Exact-match Graph Term Detection**:
- Graph terms have no parameters
- Exact match prevents typos/variations
- Simple and unambiguous
- Maps directly to relationship field names

**Alternatives Considered**:
- **JSON query format** (rejected: less human-readable)
- **SQL-like DSL** (rejected: too complex for simple filtering)
- **GraphQL-style syntax** (rejected: overkill for our use case)
- **Separate OR operator** (rejected: regex alternation sufficient per PRD)
- **Stage type annotation** (rejected: auto-detection simpler, less verbose)

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

Design rationale:
- Simple exact match, no regex needed
- Fast O(N) linear scan
- Missing field treated as non-match (defensive)

**2. filter_by_id(tickets, id_value) → Set[str]**

Exact match on ticket ID (dict key).

Implementation:
- Check if `id_value` exists as key in tickets dict
- Return singleton set if found, empty set otherwise
- O(1) constant time lookup via dict membership test

Design rationale:
- Simplest filter - direct dict lookup
- No iteration needed
- Natural short-circuit for single-ID queries

**3. filter_by_title_regex(tickets, regex_pattern) → Set[str]**

Regex match on `title` field.

Implementation:
- Compile regex with `re.IGNORECASE` flag (case-insensitive)
- Iterate all tickets
- Use `pattern.search()` on ticket title
- Handle missing title field (exclude from results)
- Raise re.error on invalid regex pattern

Design rationale:
- Case-insensitive by default (matches user expectations)
- search() not match() (allows partial matches)
- Regex compilation validated at filter time (fail fast)

**4. filter_by_label_regex(tickets, regex_pattern) → Set[str]**

Regex match on ANY label in `labels` array.

Implementation:
- Compile regex with `re.IGNORECASE` flag
- Iterate all tickets
- For each ticket, iterate labels array
- Match if ANY label matches regex
- Break early on first label match (optimization)
- Handle missing/empty labels (exclude from results)

Design rationale:
- ANY semantics (one matching label sufficient)
- Early break optimization (no need to check remaining labels)
- Empty labels list treated as non-match

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

### Design Decisions

**Why In-Memory Filtering**:
- Query pipeline loads all tickets once into memory
- Avoids repeated disk I/O per filter operation
- Enables efficient multi-stage pipelines
- Acceptable memory usage (tickets are metadata, not full content)

**Why AND Logic via Intersection**:
- Set intersection is O(min(|A|, |B|)) - efficient
- Natural representation of AND constraint accumulation
- Short-circuit opportunity (empty set detected early)
- Matches PRD requirement for AND semantics within stages

**Why Separate Filter Methods**:
- Single Responsibility Principle
- Easier to test in isolation
- Clearer code (each method focused on one task)
- Extensible (new filter types add new methods)

**Why Case-Insensitive Regex Default**:
- Matches user expectations (most searches case-insensitive)
- Users can override with regex flags if needed
- Consistent with query parser design
- Reduces user friction

**Why Set Return Types**:
- Natural deduplication (no duplicate IDs)
- Efficient set operations (intersection, union)
- Clear semantics (unordered collection of IDs)
- Matches pipeline evaluator expectations

**Why No Regex Caching**:
- Regex patterns compiled once per execute() call
- Query execution is typically one-shot (not repeated)
- Caching adds complexity with minimal benefit
- Can be added later if profiling shows bottleneck

**Alternatives Considered**:
- **Database-style query engine** (rejected: overkill, adds dependencies)
- **Filter chaining with lazy evaluation** (rejected: premature optimization)
- **Compiled query plans** (rejected: adds complexity for marginal benefit)
- **Case-sensitive default** (rejected: poor user experience)
- **OR logic support** (rejected: handled via regex alternation per PRD)

### Performance Characteristics

**Time Complexity**:
- filter_by_type: O(N) where N = number of tickets
- filter_by_id: O(1) via dict lookup
- filter_by_title_regex: O(N × M) where M = avg title length
- filter_by_label_regex: O(N × L) where L = avg labels per ticket
- execute: O(T × N) where T = number of terms

**Space Complexity**:
- O(N) for result sets (worst case: all tickets match)
- O(1) additional space per filter operation
- No intermediate data structures (filters return sets directly)

**Optimization Opportunities** (if needed):
- Compile regex patterns once and reuse for multiple queries
- Index tickets by type/label for faster exact match lookups
- Parallel filtering for independent terms (requires thread safety)
- Bloom filters for early rejection of non-matching tickets

### Integration with Pipeline

**Pipeline Evaluator responsibilities**:
1. Load all tickets into memory once (dict of ticket_id → ticket data)
2. Parse query into stages
3. Identify search stages (contain search terms)
4. Create SearchExecutor instance
5. Call executor.execute(tickets, search_terms) for each search stage
6. Pass result IDs to next stage or return final results

**Data flow**:
```
PipelineEvaluator
  ↓ (loads tickets)
In-memory tickets dict
  ↓ (passes to executor)
SearchExecutor.execute()
  ↓ (calls filter methods)
filter_by_type, filter_by_id, filter_by_title_regex, filter_by_label_regex
  ↓ (returns matching IDs)
Set[str] of ticket IDs
  ↓ (returned to pipeline)
PipelineEvaluator (passes to next stage)
```

**Error propagation**:
- Executor raises ValueError/re.error on invalid input
- Pipeline catches and wraps with query context
- User sees clear error with stage number and term

### Testing Strategy

**Test Coverage** (tests/test_search_executor.py):
- All four filter methods (various cases each)
- execute() with AND logic (2-3 term combinations)
- Short-circuit behavior (empty intermediate results)
- Edge cases (missing fields, empty tickets, invalid regex)
- Error handling (invalid terms, malformed patterns)

**Test Structure**:
- TestFilterByType: 5 tests (epic, task, subtask, nonexistent, empty)
- TestFilterById: 3 tests (exists, not exists, empty)
- TestFilterByTitleRegex: 7 tests (simple, case, patterns, errors)
- TestFilterByLabelRegex: 8 tests (single, OR, multiple, errors)
- TestExecute: 15 tests (single terms, AND logic, short-circuit, errors)
- TestEdgeCases: 5 tests (missing fields, special chars, negation)

**Coverage**: 43 tests, 100% pass rate, comprehensive edge case coverage

### Future Enhancements

**Potential additions**:
- status= exact match filter (when status field formalized)
- owner= exact match filter (when owner field standardized)
- created_at/updated_at date range filters
- Numeric range filters (priority=0..2)
- Full-text search across title + description
- Cached compiled regex patterns for repeated queries

**Not planned**:
- OR logic support (use regex alternation)
- Complex boolean expressions (use multiple stages)
- Aggregation/grouping (out of scope)
- Sorting/ranking (handled by client)

## Graph Executor Architecture

The Graph Executor (`src/graph_executor.py`) implements in-memory traversal of ticket
relationships for the query pipeline system. Part of Task bees-7b8n.

### Design Overview

**Purpose**: Execute graph stages from query pipeline by traversing ticket relationships
(parent, children, up_dependencies, down_dependencies) using in-memory data structures.

**Key Principle**: No disk I/O during traversal - all operations use pre-loaded ticket data.

**Integration**: Called by PipelineEvaluator when executing graph stages
(stages containing relationship traversal terms).

### Architecture Components

**GraphExecutor Class**:
- Single traverse() method handles all relationship types
- Stateless design (no instance state)
- Pure function (no side effects beyond logging)
- Graceful error handling (returns empty sets vs raising exceptions)

**Data Structure**:
- Input: `Dict[str, Dict[str, Any]]` - ticket_id → ticket data
- Input: `Set[str]` - ticket IDs to traverse from
- Output: `Set[str]` - set of related ticket IDs
- In-memory operation (zero disk I/O)

### Traverse Method

**traverse(tickets, input_ticket_ids, graph_term) → Set[str]**

Single method handles all four relationship types via parameterization.

**Algorithm**:
```python
1. Validate graph_term (must be: parent, children, up_dependencies, down_dependencies)
2. Initialize empty result set
3. For each ticket_id in input_ticket_ids:
    a. Check if ticket_id is None/empty (skip with warning)
    b. Check if ticket exists in tickets dict (skip with warning)
    c. Load relationship field based on graph_term
    d. Add related IDs to result set
4. Return result set (deduplicated by set nature)
```

**Design rationale**:
- Single method reduces code duplication (all traversals follow same pattern)
- Graph term parameterization keeps API simple
- Set accumulation automatically deduplicates related IDs
- Early validation catches invalid graph terms before iteration

### Relationship Type Handling

**1. parent** - Single value traversal

Implementation:
```python
parent_id = ticket_data.get('parent')
if parent_id:
    related_ids.add(parent_id)
```

Design notes:
- parent field is string or None (single parent)
- Missing/None parent → no ID added (returns empty)
- Multiple input tickets can have same parent (deduplicated)

**2. children** - List traversal

Implementation:
```python
children = ticket_data.get('children', [])
if children:
    related_ids.update(children)
```

Design notes:
- children field is list of strings (multiple children)
- Missing field defaults to empty list (safe)
- update() adds all children at once (efficient)

**3. up_dependencies** - List traversal (blockers)

Implementation:
```python
up_deps = ticket_data.get('up_dependencies', [])
if up_deps:
    related_ids.update(up_deps)
```

Design notes:
- Tickets this ticket depends on (what blocks me)
- Same pattern as children (list traversal)
- Empty list handled gracefully

**4. down_dependencies** - List traversal (blocked)

Implementation:
```python
down_deps = ticket_data.get('down_dependencies', [])
if down_deps:
    related_ids.update(down_deps)
```

Design notes:
- Tickets that depend on this ticket (what I block)
- Same pattern as children and up_dependencies
- Symmetric to up_dependencies (bidirectional relationship)

### Edge Case Handling

**Invalid graph terms**:
```python
if graph_term not in valid_terms:
    logger.warning(f"Invalid graph term '{graph_term}', returning empty set")
    return set()
```

Design rationale:
- Return empty set (graceful degradation)
- Log warning for debugging
- Pipeline continues executing (doesn't crash)

**Missing ticket IDs**:
```python
if ticket_id not in tickets:
    logger.warning(f"Ticket {ticket_id} not found in ticket data, skipping")
    continue
```

Design rationale:
- Skip missing ticket, process remaining
- Log warning for debugging
- Return partial results (tickets that were found)

**None/empty ticket IDs**:
```python
if not ticket_id:
    logger.warning("Encountered None or empty ticket ID in input set, skipping")
    continue
```

Design rationale:
- Defensive check for invalid input
- Prevents KeyError on None lookup
- Continues processing valid IDs

**Missing relationship fields**:
```python
parent = ticket_data.get('parent')  # Returns None if missing
children = ticket_data.get('children', [])  # Returns [] if missing
```

Design rationale:
- Use .get() with defaults (never KeyError)
- Treat missing field as empty relationship
- Graceful degradation (no crashes on incomplete data)

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

**Design decisions**:
- Dict key is ticket ID (O(1) lookup)
- All relationship fields stored as parsed data (no YAML parsing needed)
- Relationship fields are IDs only (no nested objects)
- Missing fields return None or empty list (defensive)

**Why this structure**:
- Fast lookup by ID (dict key access)
- No disk I/O during traversal (all data in memory)
- Simple relationship field access (direct dict lookup)
- Compatible with ticket file YAML structure

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

### Integration with Pipeline Evaluator

**Pipeline responsibilities**:
1. Load all tickets from disk into memory (once per query execution)
2. Parse YAML frontmatter for all tickets (extract relationship fields)
3. Build tickets dict (ticket_id → ticket data)
4. Identify graph stages (contain graph terms)
5. Call executor.traverse(tickets, input_ids, graph_term) for each graph stage
6. Pass result IDs to next stage

**Stage type routing**:
```python
if stage_type == 'graph':
    result_ids = graph_executor.traverse(tickets, input_ids, graph_term)
elif stage_type == 'search':
    result_ids = search_executor.execute(tickets, search_terms)
```

**Data flow**:
```
PipelineEvaluator
  ↓ (loads tickets once)
In-memory tickets dict
  ↓ (passes to executor with input IDs)
GraphExecutor.traverse()
  ↓ (looks up relationship fields)
ticket_data[relationship_field]
  ↓ (accumulates related IDs)
Set[str] of related ticket IDs
  ↓ (returned to pipeline)
PipelineEvaluator (passes to next stage)
```

### Performance Characteristics

**Time Complexity**:
- traverse(): O(n) where n = number of input ticket IDs
- Each input ticket: O(1) dict lookup + O(k) to add k related IDs
- Overall: O(n × k_avg) where k_avg = average relationships per ticket
- Typical k_avg: 1-5, so effectively O(n)

**Space Complexity**:
- O(m) where m = number of related ticket IDs found
- No intermediate data structures
- Result set size bounded by total ticket count

**Disk I/O**:
- Zero disk reads during traversal (all data in memory)
- Critical for multi-stage queries (avoid repeated disk access)
- Enables efficient multi-hop graph traversal

**Comparison to disk-based approach**:
- In-memory: O(n) with no I/O
- Disk-based: O(n × D) where D = disk read latency (~10ms)
- Performance gain: 100-1000x for typical queries

### Design Decision: Separation from SearchExecutor

**Why separate classes**:
- Clear separation of concerns (attribute filtering vs relationship traversal)
- Different data access patterns (field matching vs field lookup)
- Different error handling (search strict, graph graceful)
- Different performance characteristics (search O(N), graph O(n))
- Easier to test independently

**Why not unified executor**:
- Search and graph have different semantics
- Stage purity rule enforced at parser level (no mixing)
- Separate routing in pipeline is explicit and clear

### Design Decision: No Disk I/O

**Rationale**:
- Pipeline loads all tickets once at start
- Relationship traversal doesn't need fresh data
- Eliminates disk latency bottleneck
- Enables efficient multi-hop queries

**Tradeoff**:
- Must load all tickets upfront (memory cost)
- Query sees snapshot of data (no mid-query updates)
- Acceptable: queries are read-only, data set small (<10K tickets)

### Logging Strategy

**Log levels**:
- WARNING: Invalid graph terms, missing tickets, None IDs
- DEBUG: Successful traversals (if needed for debugging)

**Log format**:
```python
logger.warning(f"Ticket {ticket_id} not found in ticket data, skipping")
logger.warning(f"Invalid graph term '{graph_term}', returning empty set")
logger.warning("Encountered None or empty ticket ID in input set, skipping")
```

**Why log warnings**:
- Helps debug incomplete data issues
- Shows when queries reference nonexistent tickets
- Doesn't fail query (returns partial results)
- User can investigate if results unexpected

**Why not log successes**:
- Would be very noisy (every traversal logs)
- Performance impact for large queries
- SUCCESS is implicit (result set returned)

### Error Handling Philosophy

**Graceful degradation vs fail-fast**:
- GraphExecutor: graceful (returns partial results)
- SearchExecutor: fail-fast (raises exceptions)

**Why different approaches**:
- Graph queries often have incomplete data (missing relationships normal)
- Search queries have invalid syntax (bad regex should fail immediately)
- Graph: best effort results (some tickets might be orphaned)
- Search: correct or error (can't filter with invalid pattern)

### Testing Strategy

**Test Coverage** (tests/test_graph_executor.py):
- All four relationship types (parent, children, up_dependencies, down_dependencies)
- Edge cases (missing tickets, None IDs, empty relationships)
- Invalid graph terms (returns empty set)
- Multiple input tickets (deduplication, aggregation)
- Complex traversals (multi-hop via chaining)

**Test Structure**:
- TestTraverseParent: 5 tests (single, multiple, different parents, no parent)
- TestTraverseChildren: 5 tests (single, multiple, no children, mixed)
- TestTraverseUpDependencies: 5 tests (single, multiple, chains)
- TestTraverseDownDependencies: 4 tests (single, multiple, empty)
- TestInvalidGraphTerms: 3 tests (invalid, empty, misspelled)
- TestMissingTickets: 3 tests (nonexistent, mixed, all missing)
- TestMissingRelationshipFields: 4 tests (each field type missing)
- TestEmptyRelationshipLists: 3 tests (empty children, deps)
- TestNoneAndEmptyInputs: 3 tests (None, empty string, only None)
- TestEmptyTicketsDict: 4 tests (empty tickets with each graph term)
- TestComplexTraversals: 4 tests (multi-hop chains)
- TestCoverageEdgeCases: 3 tests (all terms, all empty, duplicates)

**Coverage**: 46 tests, 100% pass rate, 100% code coverage

**Testing multi-hop traversal**:
```python
# Get children of epic (tasks)
tasks = executor.traverse(tickets, {'bees-ep1'}, 'children')
# Get children of tasks (subtasks)
subtasks = executor.traverse(tickets, tasks, 'children')
```

Validates that executor can be chained for multi-hop queries.

### Alternative Designs Considered

**Recursive traversal** (rejected):
- Would automatically traverse N hops
- Less control over traversal depth
- Harder to implement pipeline stages
- Circular dependency risk

**Bidirectional traversal validation** (rejected):
- Could verify parent.children ↔ child.parent consistency
- Out of scope for executor (validator's job)
- Performance cost for every query
- Assumes data is already consistent

**Caching relationship lookups** (rejected):
- Could cache parent/children for repeated queries
- Premature optimization (queries are already fast)
- Memory overhead for cache
- Complexity not justified by current use case

**Parallel traversal** (rejected):
- Could parallelize processing of input tickets
- Thread overhead worse than O(n) lookup time
- Python GIL limits parallelism benefit
- Complexity not worth marginal gain

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

**Design rationale**:
- Flat structure for O(1) field access
- Lists for relationships (support multiple children/deps)
- Separate up/down dependency fields for bidirectional traversal
- All fields present (empty lists, not None) to avoid KeyError

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

### Short-Circuit Optimization

**Algorithm**:
```python
for stage in stages:
    result = execute_stage(stage)
    if not result:  # Empty set check
        logger.info("Short-circuit: empty result")
        break
    current_results = result
```

**When short-circuit triggers**:
1. Search stage matches zero tickets
2. Graph stage traverses to zero related tickets
3. Stage result is empty set

**Performance benefit**:
- Avoids executing remaining stages (wasted work)
- Common case: intermediate filter eliminates all tickets
- Example: 5-stage query, stage 2 returns empty → save 3 stage executions

**Logging**:
- Log each stage result count
- Log short-circuit event
- Helps debug why query returned no results

### Batch Execution Design

**Algorithm**:
```python
def execute_batch(queries):
    results = []
    for query in queries:
        result = execute_query(query)
        results.append(result)
    return results
```

**Optimization**: Tickets loaded once in __init__, reused for all queries

**Use cases**:
- Named query collections (execute 5 related queries)
- Query comparison (run multiple variants, compare results)
- Dashboard queries (load all dashboard data in single batch)

**Performance**: O(q × s × m) where:
- q = number of queries
- s = avg stages per query
- m = avg tickets per stage

**Memory**: O(m) - no additional ticket copies

### Integration with SearchExecutor

**Interface**:
```python
class SearchExecutor:
    def execute(self, tickets: dict, search_terms: list[str]) -> set[str]:
        """Filter tickets by search terms with AND logic."""
```

**Data flow**:
1. Pipeline passes tickets dict + search terms
2. SearchExecutor applies filters sequentially
3. Returns set of matching ticket IDs
4. Pipeline stores as current_results

**Search terms handled**:
- `type=value` → exact match on issue_type
- `id=value` → exact match on ticket ID
- `title~pattern` → regex match on title
- `label~pattern` → regex match on any label

### Integration with GraphExecutor

**Interface**:
```python
class GraphExecutor:
    def traverse(self, tickets: dict, input_ids: set[str], graph_term: str) -> set[str]:
        """Traverse relationships from input tickets."""
```

**Data flow**:
1. Pipeline passes tickets dict + current result IDs + graph term
2. GraphExecutor looks up relationships in ticket metadata
3. Returns set of related ticket IDs
4. Pipeline stores as current_results

**Graph terms handled**:
- `parent` → get parent of each input ticket
- `children` → get children of each input ticket
- `up_dependencies` → get tickets input tickets depend on
- `down_dependencies` → get tickets depending on input tickets

### Error Handling

**Initialization errors**:
- FileNotFoundError: tickets/ directory not found → clear message with path
- ValueError: invalid YAML frontmatter in file → clear message with filename
- Tickets without ID: skip with warning (don't crash)

**Stage execution errors**:
- ValueError: mixed stage types → detect in get_stage_type()
- ValueError: empty stage → detect in get_stage_type()
- ValueError: unrecognized terms → detect in get_stage_type()
- SearchExecutor errors: bubble up (regex errors, invalid term format)
- GraphExecutor errors: graceful (returns empty set with warnings)

**Consistency with philosophy**:
- Pipeline: fail-fast on structural issues (mixed stages)
- Executors: SearchExecutor fail-fast, GraphExecutor graceful
- User gets clear feedback on query structure problems
- Partial results for incomplete data (not errors)

### Performance Characteristics

**Initialization**: O(n) where n = total tickets
- Read markdown files: O(n) file I/O
- Normalize: O(n) YAML parsing + field extraction
- Reverse relationships: O(r) where r = total relationships
- Total: O(n + r), typically r ≈ 2n → O(3n) ≈ O(n)

**Single query execution**: O(s × m × f) where:
- s = number of stages
- m = avg tickets per stage
- f = filter complexity (regex, relationship lookup)
- Typically: 3-5 stages, 10-100 tickets/stage → 30-500 operations

**Batch query execution**: O(q × s × m × f) where q = queries
- Tickets loaded once (initialization cost paid once)
- Each query: O(s × m × f)
- Total: q queries × stage execution cost

**Space complexity**: O(n + m) where:
- n = total tickets in memory
- m = max result set size (typically m << n)

### Optimization Decisions

**Why load all tickets vs on-demand**:
- Pro: Single disk I/O (markdown files read once)
- Pro: Predictable performance (no I/O during queries)
- Pro: Enables batch queries (amortize load cost)
- Con: Higher memory usage (all tickets in RAM)
- Con: Slower initialization (load everything upfront)
- Decision: Memory trade-off worth it for query performance

**Why normalize vs raw markdown format**:
- Pro: Executor code simpler (expects consistent structure)
- Pro: Relationship lookups O(1) (not parsing dependencies array each time)
- Pro: Bidirectional traversal works (children populated from parent references)
- Con: Memory overhead (duplicate relationship data)
- Con: Normalization cost upfront (O(n) processing)
- Decision: Query performance > initialization cost

**Why build reverse relationships**:
- Pro: Graph traversal works in both directions (children, parent)
- Pro: Single lookup per traversal (not scanning all tickets for children)
- Pro: Consistent with bidirectional relationship model
- Con: Duplicate data (parent in child, child in parent.children)
- Con: Memory overhead (2x relationship storage)
- Decision: Correct graph traversal requires it

**Why set operations for deduplication**:
- Pro: Automatic (no explicit dedup code)
- Pro: Efficient (O(1) per add, O(m) total)
- Pro: Natural for ticket IDs (unordered, unique)
- Con: None (sets are perfect for this use case)

### Testing Strategy

**Test Coverage** (tests/test_pipeline.py):
- TestPipelineEvaluatorInit: 8 tests (loading, normalization, errors)
- TestStageTypeDetection: 10 tests (search, graph, mixed, errors)
- TestQueryExecution: 6 tests (single stage, multi-stage, dedup, short-circuit)
- TestBatchExecution: 3 tests (multiple queries, data reuse, complex)
- TestEdgeCases: 4 tests (empty, no matches, missing relationships, no labels)

**Coverage**: 31 tests, 100% pass rate, 100% code coverage

**Test data approach**:
- Use pytest fixtures to create temporary tickets/ directory with epics/, tasks/, subtasks/
  subdirectories
- Generate markdown test fixtures dynamically with YAML frontmatter in the `temp_tickets_dir`
  fixture
- Test fixtures match production Bees ticket format (markdown with YAML frontmatter) rather
  than legacy Beads JSONL format
- Test both success paths and error paths
- Verify relationship building (parent↔children)

**Example test structure**:
```python
def test_sequential_stage_execution(pipeline):
    """Test stages pass results to next stage."""
    stages = [
        ['type=epic'],      # Get epics
        ['children'],       # Get their children
    ]
    results = pipeline.execute_query(stages)
    assert 'bees-tk1' in results  # Task child of epic
```

### Alternative Designs Considered

**On-demand ticket loading** (rejected):
- Would load tickets as needed during query execution
- Pro: Lower memory usage (only load referenced tickets)
- Con: Multiple disk I/O operations (slower queries)
- Con: Complex caching logic (when to load, when cached?)
- Con: Batch queries lose efficiency (reload tickets per query)
- Rejected: Query performance priority > memory usage

**Stream processing** (rejected):
- Would process tickets one at a time through pipeline
- Pro: Constant memory usage (O(1) instead of O(n))
- Con: Multiple file scans (one per stage)
- Con: Can't do graph traversal (need relationships in memory)
- Con: Complex stage result caching
- Rejected: Graph queries require all tickets in memory

**Parallel stage execution** (rejected):
- Would execute independent stages in parallel
- Pro: Faster for multi-stage queries (concurrent execution)
- Con: Stages are sequential (output of N → input of N+1)
- Con: No parallelism opportunity (data dependency)
- Rejected: Pipeline is inherently sequential

**Lazy evaluation** (rejected):
- Would defer stage execution until results accessed
- Pro: Skip work if results never used
- Con: Complexity (tracking what's evaluated)
- Con: Unclear benefit (queries always want results)
- Rejected: Premature optimization (no use case for lazy)

**Query compilation** (rejected):
- Would pre-compile query into optimized execution plan
- Pro: Could reorder stages for optimization
- Con: Query structure is fixed (sequential stages required)
- Con: Compilation overhead not worth it (queries run once)
- Rejected: No optimization opportunities in current model

### Future Enhancements

**Query optimization**:
- Analyze stage selectivity (run most restrictive first)
- Requires statistics on ticket data (label distributions)
- Trade-off: optimization cost vs query execution time

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

### Design Decisions

**Separation of Concerns**:
- Scanner handles file I/O and ticket loading
- Validator implements validation logic
- Reporter handles error collection and formatting
- This separation allows each component to be tested independently
- Other tasks can extend validation by adding methods to Linter class

**Error Collection Strategy**:
- Structured error format with severity levels enables:
  - Filtering by severity (errors vs warnings)
  - Grouping by error type for report generation
  - Programmatic processing of validation results
  - Human-readable markdown output
- All errors collected before reporting (don't fail fast)
  - Provides complete picture of database issues in one scan
  - User can see all problems at once instead of fixing one at a time

**Extensibility for New Validation Rules**:
- `Linter.validate_ticket()` stub method provides extension point
- Other tasks will add validation logic:
  - Bidirectional relationship validation (parent/children consistency)
  - Cyclical dependency detection
  - Missing reference validation
  - Schema compliance checks
- Each validation rule adds errors to the shared `LinterReport`

**Report Formats**:
- JSON format: For programmatic processing and corruption state storage
- Markdown format: For human-readable output with visual indicators (❌/⚠️)
- Dictionary format: For internal processing and testing
- Design choice: Structured data model supports multiple output formats

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

Implemented cycle detection to prevent invalid dependency configurations by detecting cycles
in both blocking dependencies (up_dependencies/down_dependencies) and hierarchical
relationships (parent/children). Uses depth-first search with path tracking to efficiently
detect and report cycles with complete cycle paths.

### Implementation Architecture

**Algorithm Choice: Depth-First Search (DFS)**

Selected DFS with path tracking as the cycle detection algorithm for the following reasons:
- **Time Complexity**: O(V + E) where V is number of tickets and E is number of dependencies -
  optimal for this problem
- **Space Complexity**: O(V) for visited set and path tracking - reasonable for ticket databases
- **Cycle Path Extraction**: DFS naturally maintains the path from root to current node, making
  it trivial to extract and report the exact cycle when detected
- **Well-Established**: DFS is a standard algorithm for cycle detection in directed graphs, with
  proven correctness

**Main Entry Point** (`Linter.detect_cycles()`):
- Called from `Linter.run()` after other validation checks
- Takes list of all tickets as input
- Returns list of ValidationError objects for each cycle found
- Runs two independent DFS passes:
  1. Detect cycles in blocking dependencies (up_dependencies/down_dependencies)
  2. Detect cycles in hierarchical relationships (parent/children)
- Uses separate visited sets for each relationship type to track processed nodes

**DFS Helper Method** (`Linter._detect_cycle_dfs()`):
- Parameters:
  - `ticket_id`: Current node being explored
  - `ticket_map`: Dict mapping ticket IDs to Ticket objects (O(1) lookup)
  - `visited`: Global visited set to avoid redundant cycle detection
  - `path`: Current path from root to current node (List[str])
  - `path_set`: Set representation of path for O(1) cycle detection
  - `get_neighbors`: Lambda function to extract neighbor IDs based on relationship type
    - For blocking: `lambda t: t.up_dependencies`
    - For hierarchical: `lambda t: [t.parent] if t.parent else []`
  - `relationship_type`: String for error messages ("blocking dependency" or "parent/child")
- Return value: List[str] representing cycle path if found, None otherwise
- Key logic:
  1. Check if current node is in `path_set` (cycle detection - O(1))
  2. If cycle found, extract cycle portion of path and return
  3. Mark current node as visited globally
  4. Add node to current path (both list and set)
  5. Recursively explore each neighbor
  6. Remove node from path_set when backtracking (allows other branches to visit)

### Data Structures

**Path Tracking**:
- `path: List[str]` - Ordered list of ticket IDs from search root to current node
  - Used to extract cycle path when cycle is detected
  - Provides human-readable cycle paths in error messages (e.g., "A -> B -> C -> A")
- `path_set: Set[str]` - Set representation of current path
  - Enables O(1) cycle detection by checking if current node is in path
  - Avoids O(n) list search for each node visited

**Global Visited Tracking**:
- `visited: Set[str]` - Tracks all nodes visited across all DFS traversals
  - Prevents redundant cycle detection for nodes already processed
  - Essential for performance when graph has disconnected components
  - Separate visited sets for blocking dependencies and hierarchical relationships

### Error Types and Reporting

**Blocking Dependency Cycles**:
- Error type: `dependency_cycle`
- Detects cycles in up_dependencies/down_dependencies fields
- Example: Ticket A depends on B, B depends on C, C depends on A
- Error message format: "Cycle detected in blocking dependencies: bees-aa1 -> bees-bb1 ->
  bees-cc1 -> bees-aa1"

**Hierarchical Relationship Cycles**:
- Error type: `hierarchy_cycle`
- Detects cycles in parent/children fields
- Example: Ticket A's parent is B, B's parent is C, C's parent is A
- Error message format: "Cycle detected in parent/child hierarchy: bees-aa1 -> bees-bb1 ->
  bees-cc1 -> bees-aa1"

**ValidationError Structure**:
- `ticket_id`: First ticket ID in the cycle path
- `error_type`: "dependency_cycle" or "hierarchy_cycle"
- `message`: Human-readable description with full cycle path
- `severity`: "error" (marks database as corrupt)

### Integration with Linter Workflow

**Execution Order in `Linter.run()`**:
1. ID format validation
2. ID uniqueness validation
3. Bidirectional relationship validation
4. **Cycle detection** ← Added here
5. Report generation

**Integration Points**:
- Cycle errors collected into shared `LinterReport` object
- Errors cause database to be marked as corrupt
- MCP server will refuse to start with cycle errors present
- Forces manual fix before allowing ticket operations

### Design Decisions

**Separate Passes for Relationship Types**:
- Run independent DFS passes for blocking vs hierarchical relationships
- Rationale: Different relationship types have different semantics
- Allows targeted error messages specific to relationship type
- Prevents false positives from mixing relationship types
- Each pass uses its own visited set to ensure complete coverage

**Global Visited Set Optimization**:
- Track visited nodes globally across all DFS calls
- Prevents redundant work when graph has multiple connected components
- Critical for performance on large ticket databases
- Node visited in one DFS call is never revisited in subsequent calls
- Trade-off: O(V) space for O(V+E) time instead of O(V*E) worst case

**Path Tracking with List and Set**:
- Maintain both `path` (list) and `path_set` (set) representations
- List provides ordering for cycle path extraction
- Set provides O(1) cycle detection instead of O(n) list search
- Small memory overhead (2x instead of 1x) for significant performance gain
- Essential when cycle detection happens deep in graph traversal

**Graceful Handling of Missing Tickets**:
- Skip validation when referenced ticket doesn't exist
- Rationale: Missing references are a different class of error
- Will be handled by future validators (reference existence validation)
- Prevents cascading errors for same underlying issue
- Returns None from DFS when ticket not found instead of raising exception

**Cycle Path Format**:
- Include all nodes in cycle plus repeat of first node to close loop
- Format: "A -> B -> C -> A" clearly shows cycle structure
- Makes fix action obvious: break any edge in the reported path
- Human-readable format aids manual debugging

### Edge Cases Handled

1. **Self-cycles**: Ticket depends on itself (A -> A)
   - Detected when ticket_id already in path_set
   - Reported as single-node cycle: "A -> A"
2. **Missing tickets**: Referenced ticket IDs that don't exist
   - Gracefully skip with None return value
   - Prevents false positive cycles from broken references
3. **Disconnected components**: Multiple independent subgraphs
   - Global visited set ensures all components checked
   - Each component's root triggers new DFS traversal
4. **Empty graph**: No tickets in database
   - Returns empty error list (no cycles possible)
5. **Single node**: One ticket with no dependencies
   - Marked as visited, no neighbors to explore, returns None
6. **Mixed relationship cycles**: Separate detection for blocking vs hierarchical
   - No cross-contamination between relationship types
   - Each type validated independently with appropriate error messages

### Performance Characteristics

- **Best case**: O(V) - All tickets in linear chain, no cycles
- **Average case**: O(V + E) - Standard graph traversal with visited tracking
- **Worst case**: O(V + E) - Must explore entire graph, but each edge visited at most once
- **Space**: O(V) - Visited set and maximum path depth (equal to V in worst case)

For typical ticket databases (hundreds to thousands of tickets), performance is excellent
with subsecond cycle detection. The global visited set ensures each node is processed at
most once per relationship type, preventing exponential blowup in graphs with high
connectivity.

### Testing Strategy

Comprehensive test coverage in `tests/test_linter_cycles.py`:

**Test Coverage**:
1. Three-node blocking dependency cycle (A -> B -> C -> A)
2. Two-node blocking dependency cycle (A -> B -> A)
3. Self-cycle in blocking dependencies (A -> A)
4. Three-node hierarchical cycle (A parent of B, B parent of C, C parent of A)
5. Two-node hierarchical cycle (A parent of B, B parent of A)
6. Self-cycle in hierarchical relationships (A parent of A - edge case)
7. Acyclic graph - should pass without errors
8. Multiple independent cycles in same graph
9. Nested cycles (cycle within larger cycle structure)
10. Empty graph (no tickets)
11. Single node (one ticket, no dependencies)
12. Disconnected components (multiple independent subgraphs)
13. Mixed cycles (both blocking and hierarchical cycles in same database)
14. Error message format validation (verify cycle paths reported correctly)

**Test Approach**:
- Use temporary filesystem with synthetic ticket files
- Create tickets with specific dependency patterns
- Run linter and verify expected errors
- Check error types, ticket IDs, cycle paths, and error messages
- Cover happy path, error cases, and edge cases
- All test cases pass with 100% success rate

**Test Validation**:
- Verify correct error type returned (dependency_cycle vs hierarchy_cycle)
- Verify cycle path includes all nodes in cycle plus closing node
- Verify first ticket ID in cycle is reported as ticket_id
- Verify no false positives on acyclic graphs
- Verify all cycles detected in graphs with multiple cycles

## Bidirectional Relationship Validation (bees-ivvz)

Implemented validation to enforce bidirectional consistency in parent/children and
dependency relationships. This ensures the integrity of the ticket relationship graph
by detecting orphaned references and missing backlinks.

### Implementation Architecture

**Parent/Children Validation** (`validate_parent_children_bidirectional()`):
- Algorithm approach:
  1. Build ticket lookup map (id -> Ticket) for O(1) access
  2. For each ticket with a parent field:
     - Verify parent ticket exists (skip if missing - handled by other validators)
     - Check parent's children list contains this ticket ID
     - Add "orphaned_child" error if backlink missing
  3. For each ticket with children:
     - Iterate through each child ID in children list
     - Verify child ticket exists (skip if missing)
     - Check child's parent field equals this ticket ID
     - Add "orphaned_parent" error if backlink missing
- Error types:
  - `orphaned_child`: Child lists parent, but parent doesn't list child
  - `orphaned_parent`: Parent lists child, but child doesn't list parent
- Complexity: O(n + e) where n=tickets, e=total parent/child edges
- Validates all relationships in single pass through tickets

**Dependency Validation** (`validate_dependencies_bidirectional()`):
- Algorithm approach:
  1. Build ticket lookup map (id -> Ticket) for O(1) access
  2. For each ticket with up_dependencies:
     - Iterate through each upstream dependency ID
     - Verify upstream ticket exists (skip if missing)
     - Check upstream's down_dependencies list contains this ticket ID
     - Add "orphaned_dependency" error if backlink missing
  3. For each ticket with down_dependencies:
     - Iterate through each downstream dependency ID
     - Verify downstream ticket exists (skip if missing)
     - Check downstream's up_dependencies list contains this ticket ID
     - Add "missing_backlink" error if backlink missing
- Error types:
  - `orphaned_dependency`: Ticket lists upstream dependency, but upstream doesn't have
    backlink
  - `missing_backlink`: Ticket lists downstream dependency, but downstream doesn't have
    backlink
- Complexity: O(n + e) where n=tickets, e=total dependency edges
- Validates all dependencies in single pass

**Integration into Linter Workflow**:
- Both validators added to `Linter.run()` method as cross-ticket validations
- Execute after all tickets loaded, alongside `validate_id_uniqueness()`
- Validators access complete ticket set for relationship verification
- Errors collected into shared `LinterReport` for unified reporting

### Design Decisions

**Ticket Lookup Map**:
- Use dict lookup (O(1)) instead of linear search (O(n)) for each reference check
- Built once per validation run, reused for all relationship checks
- Trade memory for speed: O(n) space for O(1) lookup time
- Critical for performance when validating large ticket databases

**Graceful Handling of Missing References**:
- Skip validation when referenced ticket doesn't exist
- Rationale: Missing references are a different class of error (broken references)
- Will be handled by future validators (reference existence validation)
- Prevents cascading duplicate errors for same underlying issue
- Allows validators to focus on single responsibility

**Error Type Granularity**:
- Four distinct error types instead of generic "relationship_error"
- Enables targeted error messages with specific fix instructions
- Users can quickly identify which direction the relationship is broken
- Supports filtered error queries (e.g., show only parent/child issues)

**Bidirectional Enforcement Strategy**:
- Check both directions of each relationship type
- Parent->child check AND child->parent check (not just one)
- Catches asymmetric corruption regardless of which side is broken
- Example: If only child is corrupted, parent->child check finds it
- Example: If only parent is corrupted, child->parent check finds it

**Error Message Format**:
- Includes both ticket IDs involved in broken relationship
- States expected relationship clearly
- Makes fix action obvious from error message alone
- Example: "Ticket 'bees-xyz' lists 'bees-abc' as parent, but 'bees-abc' does not
  list 'bees-xyz' in its children"

### Data Structures

**Validation Error Types**:
```python
# Parent/Children errors
error_type="orphaned_child"     # Child -> parent link exists, parent -> child missing
error_type="orphaned_parent"    # Parent -> child link exists, child -> parent missing

# Dependency errors
error_type="orphaned_dependency"  # up_dep exists, down_dep backlink missing
error_type="missing_backlink"     # down_dep exists, up_dep backlink missing
```

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

### Testing Strategy

**Test Coverage** (11 tests in `tests/test_linter.py::TestBidirectionalValidation`):
1. Valid bidirectional relationships (both relationship types)
2. Orphaned child detection
3. Orphaned parent detection
4. Multiple children with mixed valid/invalid relationships
5. Valid bidirectional dependencies
6. Orphaned dependency detection
7. Missing backlink detection
8. Multiple dependencies with mixed valid/invalid relationships
9. Empty relationships (no errors for tickets without relationships)
10. Nonexistent ticket references (graceful skip)
11. Self-references (edge case handling)

**Test Approach**:
- Use temporary filesystem with synthetic ticket files
- Create tickets with specific relationship patterns
- Run linter and verify expected errors
- Check error types, ticket IDs, and error messages
- Cover happy path, error cases, and edge cases

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

### Design Rationale

**Why Check Both Directions**:
- Manual ticket editing can corrupt either side of relationship
- User might edit parent without updating child, or vice versa
- Checking both directions catches corruption regardless of source
- Provides complete validation coverage

**Why Separate Parent/Child from Dependencies**:
- Different semantic meaning (hierarchy vs blocking)
- Different field names and data structures
- Allows separate error categorization
- Enables targeted fix instructions
- Could have different fix strategies in future

**Why Error Severity is "error" not "warning"**:
- Broken relationships cause incorrect graph traversal
- Query results would be incomplete or incorrect
- Blocking/unblocking logic would fail
- Critical for system integrity, not just cosmetic
- Database cannot be trusted with broken relationships

### Design Rationale

**Why Structured Error Reporting vs Simple Logging**:
- Logging would require parsing log messages to extract error data
- Structured errors enable:
  - Programmatic filtering and analysis
  - Persistent corruption state tracking
  - MCP server integration (refuse to start when corrupt)
  - Rich formatted reports (JSON, Markdown)

**Why Run All Validations Instead of Failing Fast**:
- Users benefit from seeing all issues at once
- Enables comprehensive corruption reports
- Reduces iteration time (fix all issues in one pass)
- No performance penalty (single scan already loads all tickets)

**Why Extensible Design with Stub Methods**:
- Allows incremental implementation across multiple tasks
- Each task can add validation rules independently
- Core infrastructure (scanner, reporter) shared by all validation rules
- Tests can verify each validation rule in isolation

## Future Considerations

- MCP server delete tool implementation (Task bees-49g)
- MCP server startup script and configuration (Task bees-nas)
- Change tracking/audit log
- Migration utilities for existing ticket systems

## Named Query System

The Named Query System allows LLMs and users to register reusable query templates via MCP tools,
store them persistently, and execute them by name with parameter substitution.

### Architecture Components

**Query Storage Module** (`src/query_storage.py`):
- Manages persistent storage of named queries in `.bees/queries.yaml`
- Provides save, load, and list operations for queries
- Integrates with QueryParser for validation
- Supports optional validation bypass for parameterized queries

**MCP Tools** (`src/mcp_server.py`):
- `add_named_query(name, query_yaml, validate)` - Register new named queries
- `execute_query(query_name, params)` - Execute queries by name with parameters
- `_substitute_query_params(stages, params)` - Internal parameter substitution

**Query Pipeline Integration**:
- Uses existing PipelineEvaluator for query execution
- Loads tickets from `tickets/` directory (markdown files with YAML frontmatter)
- Executes multi-stage queries with search and graph terms

### Query Storage Design

**File Structure** (`.bees/queries.yaml`):
```yaml
# Named Queries for Bees Query System
# Each query is a list of stages for the pipeline evaluator
---
beta_tasks:
  - - type=task
    - label~beta
  - - parent

open_work_items:
  - - type={type}
    - label~(?i)(open|in progress)
```

**Storage Implementation**:
- YAML format for human readability and editability
- Header comments for documentation
- Sorted keys for consistent output
- Module-level singleton pattern for default storage instance

**Directory Creation**:
- Automatically creates `.bees/` directory if missing
- Initializes queries.yaml with header on first use
- Uses `mkdir(parents=True, exist_ok=True)` for idempotency

### Parameter Substitution

**Placeholder Syntax**:
- Use `{param_name}` in query terms for dynamic values
- Example: `type={ticket_type}`, `label~{label}`, `title~{pattern}`

**Substitution Algorithm**:
1. Parse query to find all placeholders using regex `\{(\w+)\}`
2. Validate all required parameters are provided
3. Replace each `{param}` with corresponding value from params dict
4. Return substituted query stages for execution

**Implementation** (`_substitute_query_params`):
```python
import re

# Find placeholders
placeholders = re.findall(r'\{(\w+)\}', term)

# Validate params
for placeholder in placeholders:
    if placeholder not in params:
        raise ValueError(f"Missing required parameter: {placeholder}")

# Substitute
for param_name, param_value in params.items():
    term = term.replace(f"{{{param_name}}}", str(param_value))
```

### Validation Strategy

**Two-Mode Validation**:

1. **Full Validation** (default, `validate=True`):
   - Parses YAML structure
   - Validates all search terms (type=, id=, title~, label~)
   - Validates all graph terms (parent, children, dependencies)
   - Validates regex patterns compile successfully
   - Validates no mixing of search/graph terms in same stage
   - Used for non-parameterized queries

2. **Parse-Only** (`validate=False`):
   - Parses YAML structure only
   - Skips term validation (allows placeholders like `{type}`)
   - Used for parameterized queries that won't validate until substitution
   - Validation happens at execution time after substitution

**Design Rationale**:
- Parameterized queries fail validation because `{type}` is not in VALID_TYPES
- Skipping validation for parameterized queries allows storage
- Runtime validation after substitution catches invalid param values
- Non-parameterized queries validated at save time for early error detection

### MCP Tool Interfaces

**add_named_query Tool**:
```python
def _add_named_query(name: str, query_yaml: str, validate: bool = True) -> Dict[str, Any]:
    """
    Register a new named query for reuse.
    
    Parameters:
    - name: Query identifier (used for execute_query)
    - query_yaml: YAML string defining query stages
    - validate: Whether to validate query structure (False for parameterized)
    
    Returns:
    - status: "success"
    - query_name: Name of registered query
    - message: Confirmation message
    
    Raises:
    - ValueError: If name empty or query invalid
    """
```

**execute_query Tool**:
```python
def _execute_query(query_name: str, params: str | None = None) -> Dict[str, Any]:
    """
    Execute a named query with optional parameter substitution.
    
    Parameters:
    - query_name: Name of registered query
    - params: JSON string of parameters (e.g., '{"type": "task", "label": "beta"}')
    
    Returns:
    - status: "success"
    - query_name: Name of executed query
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

### Design Decisions

**YAML Storage vs Database**:
- Chose YAML for human readability and editability
- Easy version control integration
- Simple backup and sharing
- Sufficient for expected query volume (<100 queries)
- Future: Consider DB for >1000 queries or complex permissions

**Parameter Format (JSON String)**:
- FastMCP doesn't support **kwargs or Dict parameters
- JSON string is standard format for key-value data
- Easy to serialize/deserialize
- Supports nested structures if needed
- Alternative considered: URL query string (rejected: less structured)

**Validation Bypass Flag**:
- Parameterized queries need placeholders that won't validate
- Two-mode approach: strict validation for regular queries, bypass for templates
- Runtime validation after substitution catches invalid param values
- Alternative considered: allow placeholders in validator (rejected: adds complexity)

**Module-Level Functions**:
- Convenience functions use singleton storage instance
- Reduces boilerplate for common operations
- Explicit QueryStorage class for custom storage locations
- Pattern: `save_query()` uses default, `QueryStorage().save_query()` for custom

**No Query Versioning**:
- Overwrites existing queries with same name
- Relies on version control for history
- Future: Add version field if needed for migration/rollback

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

**Query Testing Framework**:
- Unit tests for parameterized queries
- Test data fixtures for query validation
- Expected result assertions
