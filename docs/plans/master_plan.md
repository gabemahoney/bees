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
  - Verifies that `normalize_hive_name()` does not return empty string
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
- **Test coverage**: Unit tests in `tests/test_mcp_create_ticket_hive.py` verify validation behavior:
  - Valid hive names pass through successfully
  - Whitespace-only names raise ValueError
  - Special characters only raise ValueError
  - None and empty string are allowed (no validation error)
  - Error messages include original invalid name

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

