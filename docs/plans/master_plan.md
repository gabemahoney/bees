# Bees Master Plan

Technical architecture and implementation decisions for the Bees ticket management system.

_This document was consolidated in January 2026 to serve as a concise architectural reference for LLMs, removing code examples, performance metrics, and duplicated explanations while maintaining complete technical accuracy._

## Design Constraints
- No database
- No daemons
- No caches
- Limit: scales to only tens of directories and 1000s of tickets

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

### Hive Configuration System

**Purpose**: Track hive registrations with normalized names, display names, and cross-hive dependency settings.

**Schema Location**: `.bees/config.json` in client repo root

**Data Structure**:
- `HiveConfig` dataclass: Represents a single hive with `path` and `display_name` fields
- `BeesConfig` dataclass: Container with `hives` dict (normalized_name → HiveConfig),
  `allow_cross_hive_dependencies` bool, and `schema_version` string

**Initialization Strategy**: On-demand creation during first hive registration via `init_bees_config_if_needed()`
- Checks if config exists using `load_bees_config()`
- If not found, creates new BeesConfig with empty hives dict, allow_cross_hive_dependencies=false,
  schema_version='1.0', then calls `save_bees_config()`
- Returns loaded or created config

**Core Functions**:
- `get_config_path()`: Returns Path to `.bees/config.json` in current working directory
- `ensure_bees_dir()`: Creates `.bees/` directory if needed
- `load_bees_config()`: Reads config.json and returns BeesConfig object, handles file-not-found
  (returns None), validates JSON and schema_version, raises ValueError for malformed JSON
- `save_bees_config(config)`: Writes BeesConfig to config.json with indent=2 formatting,
  calls ensure_bees_dir() before writing, sets schema_version to '1.0' if not set
- `init_bees_config_if_needed()`: Creates config on first call, returns existing on subsequent calls

**Error Handling**:
- Malformed JSON raises ValueError with descriptive message
- Invalid schema_version type raises ValueError
- Invalid hive data type raises ValueError
- File write errors raise IOError

**Name Normalization**:
- `normalize_hive_name(name: str) -> str` function in `src/id_utils.py` is the single source of truth for hive name normalization
- Normalization rules: spaces → underscores, hyphens → underscores, special chars removed, convert to lowercase
- Ensures names start with letter or underscore (prefixes with underscore if starts with digit)
- Example: 'Back End' → 'back_end', 'front-end' → 'front_end', 'Multi Word Name' → 'multi_word_name'
- Normalized names serve as dictionary keys in config['hives']
- Original user input preserved in HiveConfig.display_name field
- **Consolidation Note**: Previously had duplicate `normalize_name()` function in `src/mcp_server.py` with simpler normalization (only spaces/lowercase). This was removed to prevent inconsistent behavior. The robust `normalize_hive_name()` function handles hyphens, special characters, and leading numbers correctly, ensuring consistency across ID generation and config management.

**Collision Prevention**:
- `validate_unique_hive_name(normalized_name, config)` in `src/config.py` checks for duplicate normalized names
- Prevents registration of hives with different display names that normalize to same key
- Example: blocks 'Back End' and 'back end' (both normalize to 'back_end')
- Raises ValueError with existing hive's display name if collision detected
- Called during hive registration flow before saving config

**Storage Architecture**:
- Hives dictionary uses normalized names as keys: `config.hives['back_end']`
- Each HiveConfig stores both path and display_name
- JSON structure: `{"hives": {"back_end": {"display_name": "Back End", "path": "/path/to/hive"}}}`
- This design enables case-insensitive, whitespace-normalized lookups while preserving user intent
- Display names shown in UI/reports, normalized names used for internal operations

### Hive ID System

**Purpose**: Namespace ticket IDs by hive to prevent collisions and enable multi-hive support within a single repository.

**ID Format**:
- Without hive: `bees-abc` (3 alphanumeric characters)
- With hive: `{normalized_hive}.bees-abc` (hive prefix + dot + base ID)
- Examples: `backend.bees-abc`, `my_hive.bees-123`, `bees-xyz`

**Normalization Rules**:
- Hive names normalized to lowercase with underscores
- Spaces → underscores, hyphens → underscores
- Non-alphanumeric characters removed (except underscore)
- Must start with letter or underscore
- Examples: "BackEnd" → "backend", "My Hive" → "my_hive", "front-end" → "front_end"

**ID Pattern Validation**:
- Regex: `^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$`
- Supports both formats: with and without hive prefix
- Hive prefix must start with lowercase letter or underscore
- Base ID always follows `bees-` prefix with 3 alphanumeric chars

**Implementation Flow**:
1. MCP tool `_create_ticket()` accepts optional `hive_name` parameter
2. Passes `hive_name` to factory functions (`create_epic`, `create_task`, `create_subtask`)
3. Factory functions pass `hive_name` to `generate_unique_ticket_id()`
4. `generate_unique_ticket_id()` passes to `generate_ticket_id()`
5. `generate_ticket_id()` calls `normalize_hive_name()` if hive provided
6. Returns prefixed ID: `{normalized_hive}.bees-{random_suffix}` or `bees-{random_suffix}`

**Empty Hive Name Validation**:
- Design decision: `generate_ticket_id()` checks if normalized hive name is empty string
- Empty check prevents invalid dot-prefixed IDs (e.g., `.bees-abc`)
- Maintains backward compatibility with unprefixed ID format
- Integration with `normalize_hive_name()`: When hive_name contains only special characters (e.g., '@#$%'),
  normalization returns empty string after stripping all non-alphanumeric characters
- Validation logic: If `normalize_hive_name(hive_name)` returns empty string, treated as `None`
  (generates unprefixed ID in `bees-abc` format)
- Examples: `generate_ticket_id('@#$%')` → `bees-abc`, `generate_ticket_id('')` → `bees-xyz`
- Security rationale: Prevents creation of invalid IDs that would fail validation regex check
- Implementation location: `src/id_utils.py` lines 63-65 in `generate_ticket_id()`

**Hive Name Validation in MCP Create Ticket** (Task bees-x97h4):
- **Why validation is needed**: The `_create_ticket()` MCP tool accepts `hive_name` parameter but previously
  did not validate it before passing to factory functions. Malformed hive names (whitespace-only, special
  characters only) could lead to confusing behavior or invalid ticket IDs.
- **Where validation occurs**: `_create_ticket()` in `src/mcp_server.py` validates `hive_name` parameter
  before calling `create_epic()`, `create_task()`, or `create_subtask()` factory functions
- **What is validated**:
  - Checks if `hive_name` contains at least one alphanumeric character using `re.search(r'[a-zA-Z0-9]', hive_name)`
  - Raises `ValueError` with descriptive message if validation fails
- **Validation rules**:
  - `None` and empty string (`""`) are allowed (treated as no hive prefix)
  - Whitespace-only strings (e.g., `"   "`) are rejected (would normalize to underscores)
  - Special characters only (e.g., `"@#$%"`) are rejected (would normalize to empty)
  - Valid names must have at least one alphanumeric character after normalization
- **Error messages**: Include the original invalid hive name in error message for debugging:
  `"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"`
- **Integration with normalize_hive_name()**: Validation occurs before normalization is used for ID generation,
  preventing edge cases where normalized names become empty or invalid
- **Validation simplification** (Task bees-ur1t5): Originally included redundant check for empty normalized name
  (lines 804-808) after alphanumeric check (lines 798-801). This was removed because `normalize_hive_name()` can
  only return empty string if input has no alphanumeric characters, which is already validated by the regex check.
  Single alphanumeric validation is sufficient - if the check passes, the normalized result is guaranteed to be
  non-empty.
- **Test coverage**: Unit tests in `tests/test_mcp_create_ticket_hive.py` verify validation behavior:
  - Valid hive names pass through successfully
  - Whitespace-only names raise ValueError
  - Special characters only raise ValueError
  - None and empty string are allowed (no validation error)
  - Error messages include original invalid name
  - Edge cases confirmed: hive names with special chars but containing alphanumeric pass validation
  - Verified normalized result is never empty when alphanumeric check passes

**Backward Compatibility**:
- IDs without hive prefix remain valid
- All existing tickets continue to work
- `hive_name` parameter is optional in all functions
- Default behavior (no hive_name) generates unprefixed IDs

**Functions Modified**:
- `src/id_utils.py`:
  - `normalize_hive_name()` - Normalizes hive names to standard format
  - `generate_ticket_id()` - Accepts optional `hive_name`, generates prefixed IDs
  - `generate_unique_ticket_id()` - Passes `hive_name` through to ID generation
  - `is_valid_ticket_id()` - Updated regex to validate both ID formats
  - `ID_PATTERN` - Updated to support optional hive prefix

- `src/ticket_factory.py`:
  - `create_epic()` - Accepts optional `hive_name` parameter
  - `create_task()` - Accepts optional `hive_name` parameter
  - `create_subtask()` - Accepts optional `hive_name` parameter

- `src/mcp_server.py`:
  - `_create_ticket()` - Accepts optional `hive_name` parameter, passes to factory functions

### MCP Commands with Hive Support (Task bees-oljn)

**Purpose**: Update MCP command interfaces to support hive-based ticket management with automatic hive inference from ticket IDs.

**Architecture Decision**: Create vs Update/Delete Asymmetry
- **create_ticket()**: Requires explicit `hive_name` parameter to generate prefixed IDs
- **update_ticket() / delete_ticket()**: No hive parameter needed; automatically infer from ticket_id
- Rationale: Ticket IDs are self-routing (contain hive prefix), so update/delete operations extract hive from the ID itself
- Benefits: Simpler API (fewer parameters), impossible to specify mismatched hive+ID, consistent with ID-based routing architecture

**Implementation Details**:

1. **_create_ticket() MCP tool** (`src/mcp_server.py`):
   - Added optional `hive_name: str | None` parameter to function signature (line 753)
   - Parameter accepts both display names and normalized forms
   - Validation ensures hive_name contains at least one alphanumeric character (lines 790-804)
   - Passes hive_name to factory functions: `create_epic()`, `create_task()`, `create_subtask()` (lines 871, 884, 897)
   - Factory functions pass hive_name to `generate_unique_ticket_id()` for prefixed ID generation

2. **_update_ticket() MCP tool** (`src/mcp_server.py`):
   - No hive_name parameter added (intentional design choice)
   - Uses `infer_ticket_type_from_id(ticket_id)` to determine ticket type (line 973)
   - Calls `get_ticket_path(ticket_id, ticket_type)` which internally parses hive from ID (line 980)
   - Path resolution automatically routes to correct hive directory based on ID prefix
   - Backward compatible with legacy unprefixed IDs (routes to default tickets directory)

3. **_delete_ticket() MCP tool** (`src/mcp_server.py`):
   - No hive_name parameter added (intentional design choice)
   - Uses same pattern as update_ticket: `infer_ticket_type_from_id()` + `get_ticket_path()` (lines 1173, 1180)
   - Automatic hive inference from ticket_id for path resolution
   - Cascade delete recursively uses same pattern for child tickets

4. **Bidirectional Relationship Helpers** (`src/mcp_server.py`):
   - All helper functions updated to handle hive-prefixed IDs:
     - `_update_bidirectional_relationships()` - Uses `infer_ticket_type_from_id()` for all ticket lookups (line 369)
     - `_remove_child_from_parent()`, `_add_child_to_parent()` - Hive-aware path resolution (lines 474, 498)
     - `_remove_from_down_dependencies()`, `_add_to_down_dependencies()` - Hive-aware lookups (lines 575, 599)
     - `_remove_from_up_dependencies()`, `_add_to_up_dependencies()` - Hive-aware lookups (lines 624, 648)
   - No explicit hive handling needed; path utilities handle it transparently

**Integration with Path Resolution** (`src/paths.py`):
- `infer_ticket_type_from_id()` internally calls `_parse_ticket_id_for_path()` to extract hive (line 174)
- `get_ticket_path()` uses parsed hive name to construct correct file paths (lines 106, 109-115)
- Hive-prefixed IDs: `/{hive_name}/epics/{hive_name}.bees-abc1.md`
- Legacy IDs: `/tickets/epics/bees-abc1.md`

**ID Normalization Flow**:
```
User provides hive_name: "Back End"
  ↓
_create_ticket() validates hive_name (lines 790-804)
  ↓
Passes to factory function: create_epic(..., hive_name="Back End")
  ↓
Factory calls generate_unique_ticket_id(existing_ids, hive_name="Back End")
  ↓
normalize_hive_name("Back End") → "back_end"
  ↓
generate_ticket_id(hive_name="back_end") → "back_end.bees-abc"
```

**Backward Compatibility**:
- `hive_name` parameter is optional in all functions (defaults to None)
- When None or empty string provided, generates unprefixed IDs in legacy format
- Existing tickets without hive prefixes continue to work
- Mixed usage supported: some tickets with hive prefixes, some without
- Path resolution detects format automatically and routes correctly

**Documentation Updates**:
- README.md updated with hive_name parameter examples and automatic inference notes
- MCP command list explicitly notes which commands infer hive vs require hive parameter
- ID format section documents both prefixed and legacy formats with examples

### Required hive_name Parameter (Task bees-0pe2j, Epic bees-ftl9l)

**Purpose**: Remove backward compatibility for unprefixed ticket IDs by making hive_name a required parameter in create_ticket MCP interface.

**Architecture Decision**: Required Parameter vs Optional with Default
- Design choice: Make `hive_name` a required parameter (no default value)
- Rationale: Enforces hive-based organization for all new tickets, prevents creation of legacy format tickets
- Benefits: Simplifies codebase by removing fallback logic, ensures all new tickets have proper hive context
- Alternative rejected: Optional parameter with default hive would hide configuration issues and create inconsistent ticket organization

**Implementation Changes**:

1. **Parameter Signature** (`src/mcp_server.py`):
   - Changed from `hive_name: str | None = None` to `hive_name: str` (line 753)
   - Removed default value, making parameter required in function signature
   - MCP tool interface now requires hive_name for all create_ticket calls

2. **Docstring Updates** (`src/mcp_server.py`):
   - Updated parameter documentation from "Optional hive name" to "Hive name (required)"
   - Removed references to optional behavior and default values
   - Clarified that hive_name is mandatory for ticket creation
   - **Parameter Order Fix** (Task bees-irbfa): Reordered docstring parameters to match function signature
     - Moved `hive_name` documentation from last position to third position (after `title`)
     - Ensures docstring parameter order matches function signature: `ticket_type, title, hive_name, description, ...`
     - Improves code readability and maintains consistency between signature and documentation

3. **Validation Logic** (`src/mcp_server.py`):
   - Updated validation to check for empty/missing hive_name (lines 790-807)
   - Changed from `if hive_name is not None and hive_name != ""` to explicit required check
   - Added error for empty/missing hive_name: `"hive_name is required and cannot be empty"`
   - Existing alphanumeric validation remains unchanged

4. **Documentation Updates**:
   - **README.md**: Updated to state hive_name is required, not optional
   - Removed statements about empty strings and None being allowed
   - Updated all examples to include hive_name parameter
   - Modified ID format section to clarify new tickets require hive prefix
   - **master_plan.md**: Added this section documenting the architectural decision and implementation

**Error Messages**:
- Missing/empty hive_name: `"hive_name is required and cannot be empty"`
- Invalid hive_name (no alphanumeric): `"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"`

**Backward Compatibility**:
- Reading existing tickets: Unprefixed IDs (bees-abc) still supported for reading/updating/deleting
- Creating new tickets: Must provide hive_name, no fallback to unprefixed format
- Path resolution: Continues to handle both formats automatically
- Mixed usage: Existing unprefixed tickets coexist with new hive-prefixed tickets

**Integration with ID Generation**:
- `hive_name` parameter flows through: MCP tool → factory function → `generate_unique_ticket_id()`
- Normalization via `normalize_hive_name()` still occurs in `generate_ticket_id()`
- ID format: Always `{normalized_hive}.bees-{suffix}` for new tickets
- Validation prevents empty normalized names from creating invalid IDs

**Rationale for Removal of Backward Compatibility**:
- Simplifies codebase by removing conditional logic for optional hive_name
- Enforces consistent ticket organization across all hives
- Prevents accidental creation of tickets without proper hive context
- Makes hive-based architecture mandatory, not optional
- Aligns with multi-hive design where all tickets should belong to a hive

**Migration Strategy**:
- Existing tickets: No changes required, continue to work as-is
- New tickets: Must specify hive_name in create_ticket calls
- Tooling/scripts: Update to always provide hive_name parameter
- Error messages: Guide users to provide required hive_name

**Test Fixes** (Task bees-uu7nz):
After making hive_name required, 42 existing tests needed updates to include the parameter:
- `tests/test_create_ticket.py`: Updated all `_create_ticket()` calls to include `hive_name='default'`
- `tests/test_delete_ticket.py`: Updated all `_create_ticket()` calls to include `hive_name='default'`
- `tests/test_mcp_hive_inference.py`: All calls already included hive_name (no changes needed)
- `tests/test_mcp_server.py`: Updated 4 `_create_ticket()` calls to include `hive_name='default'`

All tests now explicitly specify hive_name, ensuring compatibility with the required parameter change.
The test fixes validate that existing code patterns can be easily updated to comply with the new requirement.

### Ticket ID Parsing and Routing (Task bees-3zqk)

**Purpose**: Extract hive name from ticket IDs for internal routing to correct hive directories, enabling self-routing IDs in multi-hive systems.

**Architecture Decision**: Split on First Dot
- Design choice: `parse_ticket_id()` splits ticket IDs on the first dot only using `str.partition('.')`
- Rationale: Allows dots in base ID portion (e.g., `multi.dot.bees-xyz` → hive="multi", base_id="dot.bees-xyz")
- Alternative rejected: Split on all dots would require escaping dots in base IDs, adding complexity
- Edge cases handled: Dot at start (`.bees-123` → hive="", base_id="bees-123"), dot at end (`hive.` → hive="hive", base_id="")

**Implementation Flow**:
```
MCP tool call (ticket_id="backend.bees-abc1")
  ↓
parse_ticket_id(ticket_id)  # Returns ("backend", "bees-abc1")
  ↓
get_ticket_path(ticket_id, ticket_type)  # Constructs /path/to/backend/epics/backend.bees-abc1.md
  ↓
File system operation (read/write/delete)
```

**parse_ticket_id() Function** (`src/mcp_server.py`):
- **Signature**: `parse_ticket_id(ticket_id: str) -> tuple[str, str]`
- **Returns**: `(hive_name, base_id)` tuple where hive_name is empty string for legacy IDs
- **Edge Cases**:
  - `None` input → raises `ValueError("ticket_id cannot be None")`
  - Empty string → raises `ValueError("ticket_id cannot be empty")`
  - Whitespace-only → raises `ValueError("ticket_id cannot be empty")`
  - No dot (legacy ID) → returns `("", "bees-abc1")`
  - Multiple dots → splits on first only: `("multi", "dot.bees-xyz")`
- **Design rationale**: Returns empty string (not None) for legacy IDs to simplify conditional logic in callers
- **Backward compatibility**: Legacy IDs without dots continue to work, path resolution falls back to default tickets directory

**Path Resolution Integration** (`src/paths.py`):
- **get_ticket_path() modifications**:
  - Calls `_parse_ticket_id_for_path()` (local copy to avoid circular imports)
  - Hive-prefixed IDs route to: `{cwd}/{hive_name}/epics/{hive_name}.bees-abc1.md`
  - Legacy IDs route to: `{TICKETS_DIR}/epics/bees-abc1.md`
  - Example: `backend.bees-abc1` → `/path/to/backend/epics/backend.bees-abc1.md`
  - Example: `bees-abc1` → `/path/to/tickets/epics/bees-abc1.md`

- **infer_ticket_type_from_id() modifications**:
  - Uses parsed hive name to check correct directory structure
  - Hive-prefixed: checks `{cwd}/{hive_name}/{epics|tasks|subtasks}/`
  - Legacy: checks `{TICKETS_DIR}/{epics|tasks|subtasks}/`
  - Returns ticket type if file exists, None otherwise

**Circular Import Prevention**:
- Design decision: `src/paths.py` needs ID parsing but cannot import from `src/mcp_server.py` (circular dependency)
- Solution: Duplicate `parse_ticket_id()` as `_parse_ticket_id_for_path()` in `paths.py`
- Alternative rejected: Extracting to separate module adds unnecessary complexity for simple 10-line function
- Maintenance strategy: Both functions have identical logic; tests verify consistency

**Self-Routing ID Design**:
- Ticket IDs contain all information needed to locate the ticket file
- No need for separate hive name parameters in read/update/delete operations
- Simplifies MCP tool signatures: `update_ticket(ticket_id="backend.bees-abc")` vs `update_ticket(ticket_id="bees-abc", hive_name="backend")`
- Reduces error potential: Cannot specify mismatched ticket ID and hive name

**Integration Points**:
- All ticket operations (read, update, delete, query) use `infer_ticket_type_from_id()` which calls `_parse_ticket_id_for_path()`
- Path resolution automatically routes to correct hive directory based on ID prefix
- No changes needed to MCP tool signatures (except create_ticket which needs hive_name for ID generation)

**Architecture Diagram - ID Parsing Flow**:
```
ticket_id: "backend.bees-abc1"
           ↓
    parse_ticket_id()
           ↓
  ("backend", "bees-abc1")
           ↓
    Path Resolution
           ↓
  /path/to/backend/epics/backend.bees-abc1.md
           ↓
   File System Operations
```

**Backward Compatibility**:
- Legacy IDs (without dots) return empty string for hive name
- Path resolution checks for empty hive name and uses default tickets directory
- All existing tickets continue to work without changes
- Mixed usage supported: Some tickets with hive prefixes, some without

**Test Coverage** (`tests/test_mcp_server.py:TestParseTicketId`):
- Valid hive-prefixed IDs parse correctly
- Legacy IDs without dots return empty hive name
- Multiple dots split on first dot only
- Edge cases (None, empty, whitespace, dots at boundaries) handled
- Error messages are descriptive

**Path Validation**:
- `validate_hive_path(path: str, repo_root: Path) -> Path` in `src/mcp_server.py` validates and normalizes hive paths
- Validation rules enforce security and consistency:
  - **Absolute path requirement**: Rejects relative paths like `tickets/backend` using `Path.is_absolute()`
  - **Existence check**: Verifies path exists using `Path.exists()` before accepting registration
  - **Repository boundary check**: Uses `Path.resolve()` and `relative_to()` to ensure path is within repo root
  - **Trailing slash normalization**: `Path.resolve()` automatically removes trailing slashes
- Returns normalized absolute Path object on success
- Raises ValueError with descriptive error messages for validation failures
- Security rationale: Repository boundary check prevents hives from pointing outside the git repository,
  which could lead to unintended file modifications or security vulnerabilities
- Design decision: Trailing slash normalization ensures consistent path comparisons and prevents duplicate
  hive registrations that differ only by trailing slash
- Integration: Called during hive colonization via `colonize_hive()` before config updates

**Repository Root Detection**:
- `get_repo_root() -> Path` in `src/mcp_server.py` finds git repository root for boundary validation
- Algorithm: Walks up directory tree from `Path.cwd()` using `.parent` until `.git` directory found
- Returns absolute Path to repository root
- Raises ValueError if not in a git repository (no .git directory found)
- Used by `validate_hive_path()` to determine allowed path boundaries

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
tickets back into typed objects, enabling both read and write operations.


## Design Principles

1. **Markdown-First**: Tickets are human-readable markdown files
2. **Type Safety**: Dataclasses and validation ensure schema compliance
3. **Atomicity**: File operations are atomic to prevent corruption
4. **Simplicity**: Simple factory functions over complex frameworks
5. **Extensibility**: Clean module boundaries support future features


## MCP Server Architecture

### Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket write operations (create, update, delete) while maintaining relationship consistency. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets safely.

### Design Goals

1. **Relationship Consistency**: Automatically maintain reciprocal relationships (see Relationship Synchronization Module)
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

**Implementation Details** (`src/main.py`):
The `mcp.http_app()` property retrieves the Starlette ASGI application from FastMCP for HTTP transport. This property returns the underlying Starlette app instance that can be passed to uvicorn for serving:

```python
# Get the Starlette app from FastMCP
http_app = mcp.http_app()

# Run the FastMCP server with HTTP transport via uvicorn
uvicorn.run(
    http_app,
    host=host,
    port=port,
    log_level="info"
)
```

Reference: `src/main.py` lines 158-175.

**HTTP Transport Testing & Validation** (Task bees-1u88):

End-to-end testing confirmed HTTP transport is production-ready. The testing process validated:

1. Server startup: `poetry run start-mcp` launches cleanly and binds to configured port
2. Connection verification: `claude mcp list` confirms successful connection
3. Tool execution: MCP tools execute successfully over HTTP transport
4. Stability: Clean connection lifecycle throughout testing

**HTTP Endpoint Routing** (Task bees-q5g7):

The server provides custom HTTP endpoints alongside FastMCP's built-in MCP protocol endpoints:

## MCP Server Startup and CLI Integration

**Entry point architecture** uses `src/main.py` to separate server initialization from tool implementations, enabling configuration-driven deployment via Poetry scripts and clean testing boundaries. YAML configuration was chosen over .env or JSON formats to support comments, human readability, and nested structures without additional dependencies.

**Corruption state validation at startup** checks `.bees/corruption_report.json` before starting the MCP server. If validation errors exist, the server refuses to start, forcing manual fixes before allowing operations. This prevents cascading data corruption from operating on an invalid ticket database.

**Signal handling for graceful shutdown** registers SIGINT and SIGTERM handlers to ensure cleanup before exit, supporting standard Unix process management without requiring asyncio-specific patterns (FastMCP manages async internally).


## Relationship Synchronization Module

### Overview

The relationship synchronization module (`src/relationship_sync.py`) provides core functionality for maintaining bidirectional consistency of all ticket relationships. Shared by create/update/delete MCP tools to ensure atomicity and data integrity.

**Bidirectional Relationship Management**: When a relationship is created or modified (e.g., adding a child to a parent, or setting up a dependency), both sides of the relationship must be updated. For example:
- Adding ticket B as a child of ticket A requires updating both A's `children` list and B's `parent` field
- Adding ticket B as dependent on ticket A requires updating both A's `down_dependencies` and B's `up_dependencies`

This bidirectional synchronization prevents relationship inconsistencies and ensures graph traversal works correctly in both directions.

### Core Functions

**Relationship Operations**: `add_child_to_parent()`, `remove_child_from_parent()`, `add_dependency()`, `remove_dependency()` handle bidirectional updates with idempotency guarantees.

**Validation Functions**: `validate_ticket_exists()`, `validate_parent_child_relationship()`, `check_for_circular_dependency()` enforce type hierarchy rules and prevent cycles using DFS traversal. Validation uses `infer_ticket_type_from_id()` for lightweight type checking without full ticket parsing.

### Batch Operations

**sync_relationships_batch()** handles multiple relationship updates atomically using seven-phase execution: validation, loading, deduplication, backup (WAL), update, write-with-rollback, and cleanup. If any write fails, all tickets are restored from in-memory backups. Deduplication prevents redundant I/O by converting operations to a set before execution.

### Internal Helpers

**_load_ticket_by_id()** searches ticket type directories with early return optimization. **_save_ticket()** uses atomic writes from writer module with file locking.

### Integration Points

**MCP Tools**: create_ticket, update_ticket, and delete_ticket all use relationship sync functions. delete_ticket uses `sync_relationships_batch()` for efficient cleanup of all relationships in a single atomic operation.

### Module Integration

Uses `infer_ticket_type_from_id()` from paths module for lightweight type checking, `read_ticket()` from reader for parsing, and `write_ticket_file()` from writer for atomic writes.

### Future Enhancements

**Additional Validation**:
- Prevent orphan tickets (parent doesn't exist)
- Validate dependency types (same-type only)
- Check for dependency cycles at ticket level
- Enforce maximum children/dependencies limits

**Extended Functionality**:
- Bulk relationship import/export
- Relationship visualization (graph rendering)
- Automatic relationship repair (fix inconsistencies)
- Relationship history/audit log


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


**Design Principles**:
- Stages evaluated sequentially in order
- Results from stage N passed to stage N+1
- Terms within a stage are ANDed together
- Results deduplicated after each stage
- Empty result set short-circuits pipeline


**Regex Features Supported**:
- Case-insensitive flags: `(?i)beta`
- Alternation (OR): `beta|alpha|preview`
- Negative lookahead (NOT): `^(?!.*closed).*`
- Character classes: `p[0-4]`
- Anchors: `^start`, `end$`


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


**2. filter_by_id(tickets, id_value) → Set[str]**

Exact match on ticket ID (dict key).


**3. filter_by_title_regex(tickets, regex_pattern) → Set[str]**

Regex match on `title` field.


**4. filter_by_label_regex(tickets, regex_pattern) → Set[str]**

Regex match on ANY label in `labels` array.


### Execute Method AND Logic

**execute(tickets, search_terms) → Set[str]**

Orchestrates multi-term filtering with AND semantics.


## Graph Executor Architecture

The Graph Executor (`src/graph_executor.py`) implements in-memory traversal of ticket relationships (parent, children, up_dependencies, down_dependencies) for the query pipeline. Zero disk I/O - all operations use pre-loaded ticket data. Single `traverse()` method handles all relationship types via parameterization with graceful error handling.

### Relationship Type Handling

**1. parent** - Single value traversal


**2. children** - List traversal


**3. up_dependencies** - List traversal (blockers)


**4. down_dependencies** - List traversal (blocked)


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

### Integration

Pipeline loads all tickets once and routes to appropriate executor based on stage type. Graceful error handling returns partial results for missing tickets rather than failing query. Time complexity is O(n) where n is input ticket count.


### Overview

The Pipeline Evaluator (`src/pipeline.py`) is the central orchestrator for executing multi-stage query pipelines. It implements the complete pipeline execution workflow from ticket loading through stage execution to result collection.

**Core Responsibility**: Load tickets once, execute stages sequentially with result passing, deduplicate, short-circuit, and return final matching ticket IDs.


**Pass 2 - Reverse Relationships** (in-memory):
1. For each ticket with parent:
   - Add ticket to parent's children list
2. For each ticket with up_dependencies:
   - Add ticket to blocker's down_dependencies list

**Why two passes**: Markdown files store some relationships in one direction only (child→parent, blocked→blocker). Building the reverse relationships during load enables efficient graph traversal in both directions without multiple file scans.

**Memory usage**: O(n) where n = total tickets × avg ticket size


**Why not regex for detection**:
- Simple string prefix matching faster than regex
- Fixed set of terms (no variability)
- Clear error messages for invalid terms


**Search stage routing**:
- Passes entire ticket dict + search terms
- SearchExecutor applies AND logic across terms
- Returns set of matching ticket IDs

**Graph stage routing**:
- Multiple graph terms in stage ANDed via sequential execution
- Each term filters previous results
- Short-circuit within stage if empty

**Why different routing**:
- Search: all terms processed together (AND logic in executor)
- Graph: terms chained (each narrows result set)
- Graph terms independent (children≠parent≠dependencies)


**Automatic deduplication via sets**:
- Executor return type: `set[str]` (ticket IDs)
- Set operations inherently remove duplicates
- No explicit dedup needed in pipeline code


### Execution Optimization

Short-circuit optimization stops execution when any stage returns empty results, saving unnecessary work. Batch execution loads tickets once in __init__ and reuses for all queries. Set-based deduplication automatically handles multiple paths to same ticket.

### Executor Integration

SearchExecutor handles type/id/title/label filtering with AND logic. GraphExecutor traverses parent/children/up_dependencies/down_dependencies relationships. Pipeline routes stages to appropriate executor and chains results.

### Error Handling

Pipeline fails fast on structural issues while GraphExecutor handles missing tickets gracefully. Initialization is O(n) for loading all tickets. Query execution is O(s × m) where s is stages and m is tickets per stage.


## Linter Infrastructure Architecture

The linter validates ticket schema compliance and relationship consistency, providing
structured error reporting to identify database corruption issues. It is designed to
be extensible, allowing additional validation rules to be added by other tasks.


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


### Algorithm Choice

**DFS with path tracking** was selected for cycle detection because it achieves optimal O(V+E) time complexity while naturally maintaining the path from root to current node, making cycle extraction trivial. DFS is a well-established algorithm for detecting cycles in directed graphs with proven correctness.

### Data Structure Design

**Path tracking with dual representation** uses both a list (for ordered cycle extraction) and a set (for O(1) cycle detection) to balance human-readable error reporting with performance. The global visited set prevents redundant traversals across disconnected components, avoiding exponential blowup in highly connected graphs.

**Separate passes for relationship types** run independent DFS traversals for blocking dependencies versus hierarchical relationships, enabling targeted error messages and preventing false positives from mixing relationship semantics.


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


### Per-Hive Index Generation (Task bees-26x4)

**Purpose**: Enable generation of separate index.md files for each hive, providing isolated ticket indexes that live at hive roots rather than a global index.

**Architecture Decision**: Index per Hive vs Global Index
- Design choice: Each hive maintains its own index.md at hive root directory
- Rationale: Hives represent separate ticket collections; each should have independent indexing
- Benefits: Enables per-project ticket visibility, avoids mixing concerns across hives
- Alternative rejected: Single global index would require filtering and complicate multi-project workflows

**Implementation Flow**:
```
generate_index(hive_name="backend")
  ↓
scan_tickets(hive_name="backend")
  ↓
Filter tickets by hive prefix (backend.bees-*)
  ↓
format_index_markdown(tickets)
  ↓
Write to {hive_path}/index.md
```

**generate_index() Function** (`src/index_generator.py`):
- **Signature**: `generate_index(status_filter, type_filter, hive_name) -> str`
- **Behavior with hive_name provided**:
  - Generates index only for specified hive
  - Writes to `{hive_path}/index.md` where hive_path comes from `.bees/config.json`
  - Returns markdown content as string
- **Behavior with hive_name omitted**:
  - Iterates all registered hives from `.bees/config.json`
  - Generates separate index.md for each hive at its root
  - Returns last generated markdown (for backward compatibility)
  - Falls back to default tickets directory if no hives configured

**scan_tickets() Function** (`src/index_generator.py`):
- Added `hive_name: str | None` parameter for filtering
- When hive_name provided: only returns tickets with matching hive prefix
- Hive prefix extraction: splits ticket ID on first dot (e.g., `backend.bees-abc1` → `backend`)
- Legacy tickets without dots excluded when filtering by hive
- When hive_name omitted: returns all tickets from all hives (no filtering)

**MCP Tool Integration** (`src/mcp_server.py`):
- `_generate_index()` tool accepts optional `hive_name` parameter
- Passes parameter through to `generate_index()` function
- Updated tool docstring to describe hive_name behavior

**Index Location Strategy**:
- Hive-specific indexes: `{hive_path}/index.md` (e.g., `/path/to/backend/index.md`)
- Default location (no hives): `tickets/index.md` (legacy behavior)
- Each hive's index is independent and only contains tickets from that hive

**Integration with Hive Config**:
- Loads `.bees/config.json` to get hive paths via `load_bees_config()`
- Looks up hive path using normalized hive name as key
- Falls back to `{cwd}/{hive_name}/` if hive not in config
- Creates hive directory if needed before writing index

**Backward Compatibility**:
- When no hives configured: generates index at `tickets/index.md` (unchanged behavior)
- Existing single-hive setups continue to work without changes
- Mixed usage supported: can have some hives with indexes, others without

**Design Rationale - Per-Hive vs Global**:
- Per-hive indexes provide isolation between independent ticket collections
- Enables teams to view only their relevant tickets without cross-hive clutter
- Simplifies ticket discovery within a specific project context
- Each hive's index.md serves as entry point for that hive's documentation
- Global index would require filtering logic in readers and complicate navigation

**Use Cases**:
- Regenerate index for specific hive after bulk ticket updates: `generate_index(hive_name="backend")`
- Regenerate all hive indexes after configuration changes: `generate_index()`
- Generate filtered index for single hive: `generate_index(hive_name="backend", status="open")`

## Future Considerations

- MCP server delete tool implementation (Task bees-49g)
- MCP server startup script and configuration (Task bees-nas)
- Change tracking/audit log

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

### Multi-Hive Query Filtering (Task bees-062t)

**Purpose**: Enable filtering query results to only tickets from specified hives, supporting multi-hive repository setups where different teams or projects maintain separate ticket collections.

**Architecture Decision**: Filter at Pipeline Entry Point
- Design choice: Apply hive filter at the start of pipeline execution, before any stage processing
- Rationale: Reduces work for all subsequent stages, provides consistent semantics across search/graph operations
- Alternative rejected: Per-stage filtering would complicate executor logic and create inconsistent behavior

**Implementation Flow**:
```
execute_query(query_name, params, hive_names)
  ↓
Load query stages from .bees/queries.yaml
  ↓
Validate hive existence in .bees/config.json
  ↓
PipelineEvaluator.execute_query(stages, hive_names)
  ↓
Filter initial ticket set by hive prefix
  ↓
Execute stages on filtered set
  ↓
Return results
```

**Hive Validation** (`src/mcp_server.py`):
- Validates hive_names parameter before query execution
- Checks each hive exists in `.bees/config.json` using `load_bees_config()`
- Returns error listing available hives if specified hive not found
- Error format: `"Hive not found: {hive_name}. Available hives: {list}"`
- Handles edge case where no config exists (returns "Available hives: none")
- Validation occurs after query loading but before pipeline execution

**Hive Filtering Logic** (`src/pipeline.py`):
- `execute_query()` method accepts optional `hive_names: list[str] | None` parameter
- Default behavior when `hive_names=None`: include all tickets (no filtering)
- Filtering extracts hive prefix from ticket IDs using split on first dot
- Format: `backend.bees-abc1` → hive prefix is `backend`
- Legacy tickets without dots are excluded from filtered results
- Applied to initial result set before stage execution begins

**Integration with PipelineEvaluator**:
- Parameter passed from MCP tool through to PipelineEvaluator.execute_query()
- Filter applied once at pipeline initialization, not re-applied per stage
- Uses same ticket ID parsing logic as path resolution (split on first dot)
- Maintains backward compatibility: omitting hive_names includes all tickets

**Default Behavior**:
- When `hive_names` parameter omitted: all hives included (no filtering)
- When `hive_names` is empty list: filters to tickets without hive prefix
- When `hive_names` has values: filters to only tickets from specified hives
- Multi-hive support: can specify multiple hives in single query

**Performance Characteristics**:
- Validation: O(h) where h = number of hives in hive_names parameter
- Filtering: O(n) where n = total number of tickets in memory
- One-time cost at pipeline start, not repeated per stage
- No disk I/O (operates on pre-loaded ticket data)

**Error Handling**:
- Invalid hive name → ValueError with available hives listed
- No config exists → ValueError with "Available hives: none"
- Missing ticket IDs → gracefully handled (partial results)
- Malformed ticket IDs → gracefully excluded from results

**Example Usage**:
```python
# Query all hives
execute_query("open_tasks")

# Query single hive
execute_query("open_tasks", hive_names=["backend"])

# Query multiple hives
execute_query("open_tasks", hive_names=["backend", "frontend"])

# Error case
execute_query("open_tasks", hive_names=["nonexistent"])
# Raises: ValueError: Hive not found: nonexistent. Available hives: backend, frontend
```

**MCP Tool Signature**:
- `_execute_query(query_name: str, params: str | None = None, hive_names: list[str] | None = None)`
- Parameter order: query_name (required), params (optional JSON), hive_names (optional list)
- Returns: Dict with status, query_name, result_count, ticket_ids (filtered by hive if specified)

**Documentation Updates**:
- README.md includes hive_names parameter documentation with examples
- Shows default behavior (all hives), single hive, and multi-hive usage
- Documents error handling when hive not found
- Examples demonstrate practical use cases


**Why This Order Matters**:
1. `cleanup()` first - Ensures timer won't fire during shutdown
2. `observer.stop()` second - Signals watchdog to stop processing events
3. `observer.join()` last - Blocks until observer thread terminates cleanly


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


**Timer Execution Failures**:
When `_do_regeneration()` encounters an exception during index regeneration (e.g., file I/O
errors, parsing failures), the error is caught and logged at line 72 in `src/watcher.py`:

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

