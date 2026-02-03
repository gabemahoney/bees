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
   - Resolves file paths for ticket types (hive-based only)
   - All tickets must reside in hive-specific directories
   - Functions require hive-prefixed IDs (e.g., "backend.bees-abc") or hive_name parameter

4. **Query System** - See [docs/architecture/queries.md](../architecture/queries.md)
   - Multi-stage query pipeline with search and graph terms
   - In-memory ticket filtering and relationship traversal
   - Query parser, search executor, graph executor, pipeline evaluator

5. **Configuration Module** (`src/config.py`)
   - Centralized configuration management
   - Type-safe Config object with attribute access
   - Nested schema support (e.g., http.host, http.port)
   - Default values for missing settings

### Configuration Architecture

Bees uses a centralized configuration system with `.bees/config.json` for hive registry management and system settings. The configuration module provides both type-safe dataclass APIs and flexible dict-based APIs for different use cases.

Key components: hive registration, name normalization, atomic writes, identity markers for hive recovery, and dual API design (dataclass for type safety, dict for flexibility).

See `docs/architecture/configuration.md` for detailed configuration architecture including registry schema, normalization rules, API design decisions, and error handling strategies.

### Hive Colonization Orchestration (Task bees-cv08)

**Purpose**: Provide a single entry point for hive creation that orchestrates validation, directory structure creation, and registration in config.json.

**Architecture Decision**: Orchestration Layer Pattern
- Design choice: `colonize_hive()` acts as an orchestration function that calls config system validation rather than implementing validation inline
- Rationale: Separation of concerns - validation logic lives in config module, orchestration coordinates the workflow
- Benefits: Testable validation logic, reusable validation functions, clear error propagation, consistent return structure
- Alternative rejected: Implementing all validation inline would duplicate code and mix concerns

**Function Signature**: The colonize_hive function accepts a name string and path string as parameters, returning a dictionary containing status information and any validation errors.

**Orchestration Flow**:
1. **Name Normalization** - Calls `normalize_hive_name(name)` from `id_utils.py`
   - Returns error if name normalizes to empty string
   - Uses single source of truth for name normalization across system

2. **Path Validation** - Calls `get_repo_root()` and `validate_hive_path(path, repo_root)` from `mcp_server.py`
   - Validates path is absolute (not relative)
   - Validates path exists on filesystem
   - Validates path is within git repository boundaries
   - Returns normalized path with symlinks resolved

3. **Duplicate Name Check** - Calls `validate_unique_hive_name(normalized_name)` from `config.py`
   - Checks normalized name against existing hives in config
   - Prevents 'Back End' and 'back end' both being registered (normalize to same key)
   - Raises ValueError with existing hive's display name if collision detected

4. **Directory Structure Creation** - Creates `/eggs`, `/evicted`, and `/.hive` directories
   - Uses `Path.mkdir(parents=True, exist_ok=True)` for idempotent creation
   - Returns error dict (not exception) on filesystem errors
   - Writes `identity.json` with normalized name, display name, timestamp, version

5. **Linter Integration (Stubbed)** - Placeholder for future linter check
   - TODO: Add linter validation to check for conflicting tickets across hives
   - Intended behavior: Scan for duplicate ticket IDs, conflicting hive names, cross-hive invariants
   - Implementation deferred to future Epic
   - Current status: Logged as "(stubbed out for now)" in colonize_hive()
   - Rationale: Core colonization functionality needed first; linter complexity deferred

6. **Config Registration** - Calls `init_bees_config_if_needed()` and `save_bees_config(config)`
   - Creates `.bees/config.json` if first hive
   - Adds hive entry with normalized name as key
   - Stores HiveConfig with path and display_name
   - Returns error dict on config save failure

**Return Structure**:
- Success: `{'status': 'success', 'message': str, 'normalized_name': str, 'display_name': str, 'path': str}`
- Error: `{'status': 'error', 'message': str, 'error_type': str, 'validation_details': dict}`

**Error Types**:
- `validation_error`: Name normalizes to empty string (no alphanumeric characters)
- `path_validation_error`: Path is relative, doesn't exist, or outside repository root
- `duplicate_name_error`: Normalized name already exists in hive registry
- `filesystem_error`: Directory creation failed (PermissionError, OSError)
- `config_error`: Failed to write `.bees/config.json` (IOError)
- `unexpected_error`: Catch-all for uncaught exceptions (includes exception type and message)

**Design Decisions**:
- **Error dicts instead of exceptions**: Enables consistent error handling in MCP tools, provides structured validation details to clients
- **Orchestration not implementation**: Validation logic lives in config module where it can be tested and reused independently
- **Explicit validation steps**: Each validation step is a separate function call with clear responsibility
- **Try/except at orchestration level**: Catches all exceptions and wraps in consistent error dict structure
- **Config system integration**: Uses config module functions rather than direct file manipulation

**Integration with Config System** (Epic bees-gkxz):
- `normalize_hive_name()` from `id_utils.py` - Single source of truth for name normalization
- `validate_hive_path()` from `mcp_server.py` - Validates absolute paths within repository
- `validate_unique_hive_name()` from `config.py` - Prevents duplicate normalized names
- `init_bees_config_if_needed()` from `config.py` - Creates config on first use
- `save_bees_config()` from `config.py` - Persists hive registration to disk

**Test Coverage** (`tests/test_colonize_hive.py`):
- 33 tests total passing (19 integration, 6 scan_for_hive, 8 unit tests)
- Unit tests (TestColonizeHiveOrchestrationUnit): Mock config system calls, verify orchestration logic
- Integration tests (TestColonizeHive): Real filesystem operations with git repo fixture
- Test cases: successful colonization, empty name error, invalid path errors, duplicate name error, filesystem errors, config errors
- All tests verify consistent error/success return structure with validation_details

**Why Orchestration Pattern**:
- Keeps `colonize_hive()` focused on workflow coordination
- Validation logic testable in isolation (config module unit tests)
- Error handling centralized at orchestration layer
- Easy to add new validation steps (just call another function)
- MCP tools get consistent error structure across all operations

**Storage Architecture**: See `docs/architecture/storage.md` for detailed documentation of hive directory structure (eggs/, evicted/, .hive/), identity markers, and storage rationale.

### Hive ID System

**Purpose**: Namespace ticket IDs by hive to prevent collisions and enable multi-hive support within a single repository.

**Storage Architecture**: See `docs/architecture/storage.md` for ticket ID format, pattern validation, and hive namespacing overview.

**ID Format**:
- Without hive: `bees-abc` (3 alphanumeric characters)
- With hive: `{normalized_hive}.bees-abc` (hive prefix + dot + base ID)
- Examples: `backend.bees-abc`, `my_hive.bees-123`, `bees-xyz`

**Normalization Rules**: Hive names normalized to lowercase with underscores. See `docs/architecture/configuration.md` for detailed normalization rules.

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

**Hive Name Validation**:
- `generate_ticket_id()` requires valid hive names
- MCP `_create_ticket()` validates hive_name before calling factory functions
- When hive_name contains only special characters (e.g., '@#$%'), normalization returns empty string which is rejected by validation
- Security rationale: Prevents creation of invalid IDs that would fail validation regex check
- Implementation location: `src/mcp_server.py` hive_name validation

**Hive Name Validation in MCP Create Ticket** (Tasks bees-x97h4, bees-uol2):
- **Why validation is needed**: The `_create_ticket()` MCP tool accepts `hive_name` parameter but must
  validate both the format and existence of the hive. Malformed hive names (whitespace-only, special
  characters only) or non-existent hives could lead to confusing behavior or invalid ticket IDs.
- **Where validation occurs**: `_create_ticket()` in `src/mcp_server.py` validates `hive_name` parameter
  before calling `create_epic()`, `create_task()`, or `create_subtask()` factory functions
- **What is validated** (three-stage validation):
  1. **Format validation**: Checks if `hive_name` contains at least one alphanumeric character using `re.search(r'[a-zA-Z0-9]', hive_name)`
  2. **Existence validation** (Task bees-uol2): Verifies hive exists in `.bees/config.json` after normalization
  3. **Path validation** (Task bees-3c0ja): Validates hive path is accessible and writable
  - Raises `ValueError` with descriptive message if any validation fails
- **Validation rules**:
  - Whitespace-only strings (e.g., `"   "`) are rejected (would normalize to underscores)
  - Special characters only (e.g., `"@#$%"`) are rejected (would normalize to empty)
  - Valid names must have at least one alphanumeric character after normalization
  - **Hive must be registered**: Normalized hive name must exist as a key in `config.hives` dictionary
- **Error messages**:
  - Format validation: `"Invalid hive_name: '{hive_name}'. Hive name must contain at least one alphanumeric character"`
  - Existence validation: `"Hive '{hive_name}' (normalized: '{normalized_hive}') does not exist in config. Please create the hive first using colonize_hive."`
  - Path validation (missing): `"Hive path does not exist: '{path}'. Please create the directory before creating tickets."`
  - Path validation (not directory): `"Hive path is not a directory: '{path}'. Path must be a directory, not a file."`
  - Path validation (not writable): `"Hive directory is not writable: '{path}'. Please check directory permissions."`
  - Path validation (resolution failure): `"Failed to resolve hive path '{path}': {error}"`
- **Integration with normalize_hive_name()**: Validation occurs in two steps:
  1. Format check before normalization prevents invalid characters
  2. Existence check after normalization validates against config registry
- **Hive path validation architecture** (Task bees-3c0ja):
  - **When it occurs**: After config existence validation (lines 982-988), before parent validation
  - **Why this order**: Validates hive is registered first, then validates path accessibility, then proceeds with ticket-specific validation
  - **Implementation location**: `src/mcp_server.py` lines 990-1033
  - **Validation steps**:
    1. Get hive path from config: `hive_path = Path(config.hives[normalized_hive].path)`
    2. Resolve symlinks: `resolved_path = hive_path.resolve(strict=False)` - handles symlinks gracefully
    3. Check existence: `resolved_path.exists()` - ensures directory is present
    4. Check is directory: `resolved_path.is_dir()` - ensures path is not a file
    5. Test write permissions: Create and remove test file `{uuid}.write_test` - validates write access
  - **Error handling strategy**:
    - Path resolution errors (OSError, RuntimeError) → ValueError with resolution failure message
    - Missing path → ValueError suggesting to create directory
    - Path is file → ValueError indicating path must be directory
    - Permission errors (PermissionError, OSError) → ValueError with permission details
  - **Edge cases handled**:
    - Symlinks: Resolved to target and validated; broken symlinks caught by existence check
    - Permission errors: Explicit PermissionError catch for write test
    - General I/O errors: OSError catch for filesystem issues
  - **Design rationale**:
    - Path validation after config check ensures we don't attempt filesystem operations on unregistered hives
    - Validation before ticket creation prevents creating ticket objects that can't be persisted
    - Test file approach (vs stat checks) ensures actual write permissions work in practice
    - UUID in test filename prevents conflicts in concurrent operations
  - **Test coverage**: Unit tests in `tests/test_create_ticket_hive_validation.py::TestCreateTicketHivePathValidation`:
    - Missing directory raises ValueError with descriptive message
    - Path is file (not directory) raises ValueError
    - Non-writable directory raises ValueError
    - Valid symlinks succeed (creates ticket in target)
    - Broken symlinks raise ValueError
    - Successful validation passes all checks
    - Error messages are descriptive and actionable
- **Ticket storage routing** (Task bees-l42j): After all validation passes, ticket is stored in hive directory from config:
  - Uses `config.hives[normalized_hive].path` to get hive directory
  - Stores ticket in flat storage at hive root: `{hive_path}/{ticket_id}.md`
  - Path resolution via `get_ticket_path()` in `src/paths.py` loads config and routes to correct hive
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

**ID Requirements**:
- All IDs must have hive prefix
- `hive_name` parameter is REQUIRED in create_ticket() MCP tool
- All factory functions require hive_name for new ticket creation

**Functions Modified**:
- `src/id_utils.py`:
  - `normalize_hive_name()` - Normalizes hive names to standard format
  - `generate_ticket_id()` - Requires `hive_name` parameter (mandatory)
  - `generate_unique_ticket_id()` - Requires `hive_name` parameter (mandatory, first parameter)
  - `is_valid_ticket_id()` - Updated regex to validate both ID formats
  - `ID_PATTERN` - Updated to support optional hive prefix

- `src/ticket_factory.py`:
  - `create_epic()` - Requires `hive_name` parameter (mandatory)
  - `create_task()` - Requires `hive_name` parameter (mandatory)
  - `create_subtask()` - Requires `hive_name` parameter (mandatory)

- `src/mcp_server.py`:
  - `_create_ticket()` - Requires `hive_name` parameter, passes to factory functions

### Mandatory Hive Prefix for ID Generation (Task bees-i4vva, Epic bees-ftl9l)

**Purpose**: Enforce hive-prefixed ticket IDs by making hive_name a required parameter in ID generation functions.

**Architecture Decision**: Required hive_name in ID Generation
- Design choice: Make `hive_name` a required parameter in `generate_ticket_id()` and `generate_unique_ticket_id()`
- Rationale: Enforces hive-based architecture at the lowest level, prevents accidental creation of unprefixed IDs
- Benefits: Simplifies ID generation logic, removes conditional fallback code, ensures all new IDs follow hive-prefixed format
- Alternative rejected: Optional parameter with fallback to unprefixed IDs creates inconsistent behavior and complicates multi-hive support

**Implementation Changes**:

1. **generate_ticket_id() Function** (`src/id_utils.py`):
   - Changed signature from `hive_name: str | None = None` to `hive_name: str` (line 43)
   - Removed default value, making parameter required
   - Removed fallback logic that returned unprefixed `bees-{suffix}` when hive_name was None/empty
   - Added ValueError when hive_name normalizes to empty string
   - Updated docstring to reflect required parameter and hive-prefixed format only
   - Format: Always returns `{normalized_hive}.bees-{suffix}`, never unprefixed format

2. **generate_unique_ticket_id() Function** (`src/id_utils.py`):
   - Changed signature from `existing_ids: set[str] | None = None, max_attempts: int = 100, hive_name: str | None = None` to `hive_name: str, existing_ids: set[str] | None = None, max_attempts: int = 100` (line 100)
   - Moved hive_name to first parameter position (before existing_ids)
   - Removed default value, making parameter required
   - Updated docstring to reflect required parameter
   - Updated examples to show hive-prefixed format only

3. **Error Handling** (`src/id_utils.py`):
   - Raises `ValueError` when hive_name normalizes to empty string
   - Error message: `"hive_name '{hive_name}' normalizes to empty string"`
   - Validation occurs after normalization to catch edge cases (special characters only, whitespace only)

**Integration with Hive System**:
- ID generation now enforces hive-based architecture at the foundational level
- All callers of `generate_ticket_id()` must provide valid hive_name
- Normalization via `normalize_hive_name()` ensures consistent format
- Validation prevents empty normalized names from creating invalid IDs

**Rationale for Required hive_name**:
- Removes conditional logic and fallback paths, simplifying codebase
- Enforces consistent ID format across all new ticket creation
- Prevents accidental creation of unprefixed IDs that would violate hive-based architecture
- Aligns with multi-hive design where all tickets must belong to a hive
- Makes hive prefix mandatory in ID generation, not optional at MCP layer only

**Backward Compatibility Removal**:
- Previous behavior: `generate_ticket_id()` would return `bees-{suffix}` when hive_name was None/empty
- New behavior: `generate_ticket_id()` raises ValueError when hive_name is missing or normalizes to empty
- Breaking change: All code calling these functions must now provide hive_name
- Migration path: Update all callers to include hive_name parameter

**Design Rationale**:
- Simplicity: Single code path (always prefixed) is easier to maintain than dual paths (prefixed vs unprefixed)
- Consistency: All IDs follow same format, no exceptions
- Enforcement: Makes hive-based architecture mandatory at ID generation level, not just MCP tool level
- Error detection: Failing fast at ID generation prevents invalid IDs from propagating through system

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
   - No hive_name parameter needed (hive inferred from ticket_id)
   - **Hive Parsing Logic**: Calls `parse_hive_from_ticket_id(ticket_id)` to extract hive prefix
     - Splits ticket_id on first dot: `backend.bees-abc1` → `backend`
     - Returns None for malformed IDs (no dot found)
   - **Hive Validation**: Uses `normalize_hive_name()` for lookup and validates hive exists in config
     - Returns error if hive prefix is None: "Malformed ticket ID: Expected format: hive_name.bees-xxxx"
     - Returns error if hive not found: "Unknown hive: '{hive}' not found in config"
   - Uses `infer_ticket_type_from_id(ticket_id)` to determine ticket type (line 973)
   - Calls `get_ticket_path(ticket_id, ticket_type)` which internally parses hive from ID (line 980)
   - Path resolution automatically routes to correct hive directory based on ID prefix
   - **Integration with normalize_name()**: Hive validation uses `normalize_hive_name()` to handle display name variations (e.g., "Back End" → "back_end")

3. **_delete_ticket() MCP tool** (`src/mcp_server.py`):
   - No hive_name parameter needed (hive inferred from ticket_id)
   - No cascade parameter needed (deletion always cascades)
   - **Hive Parsing Logic**: Calls `parse_hive_from_ticket_id(ticket_id)` to extract hive prefix
     - Splits ticket_id on first dot: `backend.bees-abc1` → `backend`
     - Returns None for malformed IDs (no dot found)
   - **Hive Validation**: Uses `normalize_hive_name()` for lookup and validates hive exists in config
     - Returns error if hive prefix is None: "Malformed ticket ID: Expected format: hive_name.bees-xxxx"
     - Returns error if hive not found: "Hive '{hive_prefix}' not found in configuration"
   - Uses `infer_ticket_type_from_id(ticket_id)` to determine ticket type
   - Calls `get_ticket_path(ticket_id, ticket_type)` which internally parses hive from ID
   - Path resolution automatically routes to correct hive directory based on ID prefix
   - **Always-Cascade Delete**: Recursively calls `_delete_ticket()` for all child tickets, each parsing its own hive prefix
     - Deleting a parent ticket always deletes its entire subtree (children and grandchildren)
     - Simplified API by removing optional cascade parameter - behavior is now consistent and predictable
     - Removed unlink code path that previously allowed keeping children when cascade=False
   - **Design Decision**: Self-routing IDs eliminate need for explicit hive parameter, and always-cascade behavior simplifies the API
   - **Integration with normalize_name()**: Hive validation uses `normalize_hive_name()` to handle display name variations

4. **Bidirectional Relationship Helpers** (`src/mcp_server.py`):
   - All helper functions updated to handle hive-prefixed IDs:
     - `_update_bidirectional_relationships()` - Uses `infer_ticket_type_from_id()` for all ticket lookups (line 369)
     - `_remove_child_from_parent()`, `_add_child_to_parent()` - Hive-aware path resolution (lines 474, 498)
     - `_remove_from_down_dependencies()`, `_add_to_down_dependencies()` - Hive-aware lookups (lines 575, 599)
     - `_remove_from_up_dependencies()`, `_add_to_up_dependencies()` - Hive-aware lookups (lines 624, 648)
   - No explicit hive handling needed; path utilities handle it transparently

**Helper Function: parse_hive_from_ticket_id()** (`src/mcp_server.py`):
- **Purpose**: Extract hive prefix from ticket IDs for self-routing in update/delete operations
- **Signature**: `parse_hive_from_ticket_id(ticket_id: str) -> str | None`
- **Implementation**:
  - Splits ticket_id on first dot using `partition('.')`
  - For prefixed IDs (`backend.bees-abc1`): Returns hive name (`backend`)
  - For unprefixed IDs (`bees-abc1`): Returns None (malformed/legacy format)
  - Example multi-dot ID: `multi.dot.bees-xyz9` → `multi` (only first dot used)
- **Return Value**:
  - `str`: Hive name prefix if dot found
  - `None`: If no dot found (malformed ID)
- **Usage in update_ticket() and delete_ticket()**:
  - Called at start of both functions to validate ticket_id format
  - Result passed to `normalize_hive_name()` for config lookup
  - Enables clear error messages for malformed IDs vs unknown hives
  - Same error handling pattern in both functions for consistency
- **Design Decision**: Separate from `parse_ticket_id()` to provide focused single-responsibility helper
  - `parse_ticket_id()`: Returns tuple (hive_name, base_id) for full parsing
  - `parse_hive_from_ticket_id()`: Returns only hive name for routing validation

**Integration with Path Resolution** (`src/paths.py`):
- `infer_ticket_type_from_id()` internally calls `_parse_ticket_id_for_path()` to extract hive
- `get_ticket_path()` uses parsed hive name to construct correct file paths
- Hive-prefixed IDs with flat storage: `/{hive_name}/{hive_name}.bees-abc1.md`

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

**Parameter Requirements**:
- `hive_name` parameter is REQUIRED in `_create_ticket()` MCP tool
- None or empty string for hive_name raises ValueError
- All tickets must use hive-prefixed format
- Path resolution detects format automatically and routes correctly

**Documentation Updates**:
- README.md updated with hive_name parameter examples and automatic inference notes
- MCP command list explicitly notes which commands infer hive vs require hive parameter
- ID format section documents hive-prefixed format with examples

### Required hive_name Parameter (Task bees-0pe2j, Epic bees-ftl9l)

**Purpose**: Enforce hive-based ticket organization by making hive_name a required parameter in create_ticket MCP interface.

**Architecture Decision**: Required Parameter vs Optional with Default
- Design choice: Make `hive_name` a required parameter (no default value)
- Rationale: Enforces hive-based organization for all new tickets, ensures proper ticket organization
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

**Ticket Management**:
- Creating new tickets: Must provide hive_name, required parameter enforced
- Path resolution: Requires hive-prefixed IDs

**Integration with ID Generation**:
- `hive_name` parameter flows through: MCP tool → factory function → `generate_unique_ticket_id()`
- Normalization via `normalize_hive_name()` still occurs in `generate_ticket_id()`
- ID format: Always `{normalized_hive}.bees-{suffix}` for new tickets
- Validation prevents empty normalized names from creating invalid IDs

**Rationale for Required hive_name**:
- Simplifies codebase by removing conditional logic for optional hive_name
- Enforces consistent ticket organization across all hives
- Prevents accidental creation of tickets without proper hive context
- Makes hive-based architecture mandatory, not optional
- Aligns with multi-hive design where all tickets should belong to a hive

**Usage Requirements**:
- New tickets: Must specify hive_name in create_ticket calls
- Tooling/scripts: Must always provide hive_name parameter
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
get_ticket_path(ticket_id, ticket_type)  # Constructs /path/to/backend/backend.bees-abc1.md (flat storage)
  ↓
File system operation (read/write/delete)
```

**parse_ticket_id() Function** (`src/mcp_server.py`):
- **Signature**: `parse_ticket_id(ticket_id: str) -> tuple[str, str]`
- **Returns**: `(hive_name, base_id)` tuple where hive_name is empty string for IDs without dot separator
- **Edge Cases**:
  - `None` input → raises `ValueError("ticket_id cannot be None")`
  - Empty string → raises `ValueError("ticket_id cannot be empty")`
  - Whitespace-only → raises `ValueError("ticket_id cannot be empty")`
  - No dot → returns `("", "bees-abc1")`
  - Multiple dots → splits on first only: `("multi", "dot.bees-xyz")`
- **Design rationale**: Returns empty string (not None) for IDs without dots to maintain parsing consistency

**Path Resolution Integration** (`src/paths.py`):
- **get_ticket_path() modifications**:
  - Calls `_parse_ticket_id_for_path()` (local copy to avoid circular imports)
  - Hive-prefixed IDs route to: `{cwd}/{hive_name}/{hive_name}.bees-abc1.md` (flat storage)
  - Example: `backend.bees-abc1` → `/path/to/backend/backend.bees-abc1.md`

- **infer_ticket_type_from_id() modifications**:
  - Uses parsed hive name to check correct directory structure
  - Checks `{cwd}/{hive_name}/{epics|tasks|subtasks}/`
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
  /path/to/backend/backend.bees-abc1.md (flat storage)
           ↓
   File System Operations
```

**Path Resolution Requirements**:
- All IDs must be hive-prefixed
- Path resolution rejects unprefixed IDs with ValueError

### Ticket Schema Versioning (Task bees-uwot)

**Purpose**: Add schema versioning to ticket YAML frontmatter for future-proof ticket identification and schema evolution support in flat storage architecture.

**Storage Architecture**: See `docs/architecture/storage.md` for architectural overview of ticket schema versioning, `bees_version` field purpose, and integration with flat storage.

**Architecture Decision**: Version Field in Frontmatter
- Design choice: Add `bees_version` field to ticket YAML frontmatter, automatically set at ticket creation time
- Rationale: Enables ticket identification for flat storage (Epic bees-yuql) and schema version tracking
- Current version: `1.1` (corresponds to flat storage schema)
- Field is required for all tickets

**Implementation Components**:

1. **Schema Version Constant** (`src/constants.py`):
   - `BEES_SCHEMA_VERSION = '1.1'` - Single source of truth for current schema version
   - Version format: String (not semantic versioning) for simplicity
   - Updated when schema changes require ticket identification or migration

2. **Ticket Model Update** (`src/models.py`):
   - Added `bees_version: str | None = None` field to Ticket dataclass
   - Optional field (defaults to None) for backward compatibility
   - Existing tickets without field continue to parse correctly

3. **Ticket Factory Integration** (`src/ticket_factory.py`):
   - All create functions updated: `create_epic()`, `create_task()`, `create_subtask()`
   - Each function imports `BEES_SCHEMA_VERSION` from constants
   - Adds `'bees_version': BEES_SCHEMA_VERSION` to frontmatter_data dictionary
   - Automatically applied to all new tickets - no manual intervention required

4. **Reader Support** (`src/reader.py`):
   - Added `'bees_version'` to `known_fields` set in `_filter_ticket_fields()`
   - Ensures reader preserves field when parsing ticket files
   - Without this, field would be filtered out during ticket object construction

5. **Reader Validation** (`src/reader.py`, Task bees-g31n):
   - `read_ticket()` function validates `bees_version` field presence in frontmatter
   - Validation occurs immediately after `parse_frontmatter()` call, before schema validation
   - Raises `ValidationError` if `bees_version` field is missing
   - Error message: "Markdown file is not a valid Bees ticket: missing 'bees_version' field in frontmatter"
   - Ensures only valid Bees ticket markdown files are processed by the system
   - Critical for flat storage architecture: distinguishes ticket files from other markdown files in hive root

**Integration with Flat Storage (Epic bees-yuql)**:
- Flat storage scans YAML `type` field AND `bees_version` to identify tickets
- Schema version enables queries to distinguish ticket markdown files from other markdown files in hive root
- Future queries can filter by schema version (e.g., "find all v1.0 tickets for migration")
- Validation requirement enforces architectural decision: all ticket files must be identifiable via `bees_version` field

**Validation Architecture (Task bees-g31n)**:
- **Design Decision**: Require `bees_version` field in all ticket markdown files
- **Rationale**: Flat storage places all tickets in hive root alongside other markdown files; `bees_version` field distinguishes ticket files from documentation, READMEs, and other markdown content
- **Implementation**: `read_ticket()` validates field presence before processing frontmatter, ensuring fail-fast behavior for invalid files
- **Error Handling**: Clear, actionable error message guides users to add missing field
- **Integration**: Works with existing schema validation layer (`validate_ticket()`) as pre-validation step

**Version Field Requirement**:
- **Requirement**: All tickets MUST include `bees_version` field (enforced in Task bees-g31n)
- **Rationale**: Field is essential for flat storage architecture ticket identification

**Example Ticket Frontmatter**:
```yaml
---
id: backend.bees-abc1
type: task
title: Example Task
bees_version: '1.1'
status: open
created_at: 2026-02-01T12:00:00
---
```

**Design Rationale**:
- String version (not int) allows flexibility for minor versions or branches (e.g., "1.1.1", "2.0-beta")
- Stored in frontmatter (not body) for efficient scanning without parsing full markdown
- Set at creation time (not dynamically) creates immutable audit trail of when ticket was created
- Enables future schema evolution: queries can filter by version

**Test Coverage** (Task bees-dxqs):
- Tests verify ticket_factory sets version in all three create functions
- Tests verify reader parses and preserves bees_version field
- Tests verify Ticket model accepts bees_version field

### Hive-Prefixed Path Routing (Task bees-sl1u6, Epic bees-ftl9l)

**Purpose**: Enforce hive-prefixed ticket IDs in path resolution functions, implementing hive-based architecture at the path layer.

**Architecture Decision**: Fail Fast on Invalid IDs
- Design choice: Path resolution functions raise ValueError for unprefixed IDs instead of falling back to legacy paths
- Rationale: Eliminates ambiguity in ID format, prevents accidental use of legacy format, simplifies path resolution logic
- Alternative rejected: Supporting dual formats (hive-prefixed and unprefixed) creates maintenance burden and complicates multi-hive architecture

**Implementation Changes**:

1. **_parse_ticket_id_for_path() Function** (`src/paths.py`):
   - Changed from returning `("", ticket_id)` for unprefixed IDs to raising ValueError (lines 36-38 removed)
   - Now requires dot separator in ticket ID (hive prefix mandatory)
   - Error message: `"Invalid ticket ID '{ticket_id}': must have hive prefix (e.g., 'hive_name.bees-abc'). Legacy unprefixed IDs are no longer supported."`
   - Updated docstring to reflect hive-prefixed format requirement

2. **get_ticket_path() Function** (`src/paths.py`):
   - Removed else branch that routed to TICKETS_DIR for unprefixed IDs (lines 113-115 removed in earlier commit)
   - Removed redundant hive_name validation check since `_parse_ticket_id_for_path()` now raises ValueError for unprefixed IDs
   - Function now only handles hive-prefixed IDs via single code path
   - Path format: `/{hive_name}/{hive_name}.bees-abc1.md` (flat storage, no type subdirectories)

3. **infer_ticket_type_from_id() Function** (`src/paths.py`):
   - Wrapped `_parse_ticket_id_for_path()` call in try/except to handle ValueError gracefully
   - Returns None for unprefixed IDs instead of routing to TICKETS_DIR
   - Removed lines 180-182 that checked TICKETS_DIR for legacy IDs (already removed in earlier commit)
   - Updated docstring to remove references to legacy ID support

**Error Handling Strategy**:
- `_parse_ticket_id_for_path()`: Raises ValueError (fails fast)
- `get_ticket_path()`: Propagates ValueError from parsing (fails fast)
- `infer_ticket_type_from_id()`: Catches ValueError and returns None (graceful degradation for type inference)

**Design Rationale**:
- Single code path (hive-prefixed only) eliminates conditional logic and edge cases
- Failing fast prevents invalid IDs from propagating through system
- Consistent with ID generation changes (Task bees-i4vva) that made hive_name required
- Enforces hive-based architecture at foundational path resolution layer
- Error messages guide users toward correct ID format

**ID Format Requirement**:
- Unprefixed IDs raise ValueError or return None (depending on function)
- All path resolution requires hive-prefixed IDs

**Integration with Path Resolution**:
- Path resolution now enforces hive-based architecture uniformly
- No special cases or fallback logic for legacy format
- All tickets must exist in hive root directories (flat storage: `{hive_name}/*.md`)
- TICKETS_DIR constant and type-specific subdirectories completely removed

**Test Coverage**:
- `tests/test_paths.py`: 45 tests passing
- Tests verify ValueError raised for unprefixed IDs
- Tests verify hive-prefixed IDs resolve correctly
- Edge cases tested: None, empty string, whitespace, multiple dots
- Test class `TestParseTicketIdForPath` validates parsing behavior

**Documentation Updates**:
- README.md: Added explicit statement that unprefixed IDs are not supported
- Path Resolution section clarifies ValueError is raised for invalid format
- All examples use hive-prefixed IDs exclusively

**Test Coverage** (`tests/test_mcp_server.py:TestParseTicketId`):
- Valid hive-prefixed IDs parse correctly
- IDs without dots return empty hive name
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
- `get_repo_root(ctx, repo_root) -> Path | None` in `src/mcp_server.py` finds git repository root for boundary validation
- Implements a fallback chain to support MCP clients with or without roots protocol:
  1. **Priority 1**: If `repo_root` parameter is provided, validates and uses it directly
  2. **Priority 2**: If `ctx` (FastMCP Context) is provided, attempts to use MCP roots protocol via `get_client_repo_root(ctx)`
  3. **Fallback behavior**: If both methods fail (no `repo_root` parameter AND no roots support), returns None
- All 11 MCP tool functions accept optional `repo_root: str | None = None` parameter:
  - Ticket operations: `_create_ticket`, `_update_ticket`, `_delete_ticket`, `_show_ticket`
  - Query operations: `_execute_query`, `_execute_freeform_query`
  - Hive operations: `_colonize_hive`, `_list_hives`, `_abandon_hive`, `_rename_hive`, `_sanitize_hive`
- Each tool function passes `repo_root` to `get_repo_root(ctx, repo_root=repo_root)` for consistent fallback behavior
- Design rationale:
  - Prioritizes explicit `repo_root` parameter over automatic detection to support clients without roots protocol
  - Maintains backward compatibility with roots-enabled clients (they never need to provide `repo_root`)
  - Returns None when neither method succeeds, allowing callers to handle unavailable repo root gracefully
  - Raises ValueError only for truly invalid inputs (non-absolute paths, invalid git repositories)
- Used by `validate_hive_path()` to determine allowed path boundaries

**MCP Roots Protocol Support**:
- The MCP roots protocol is an optional protocol that allows MCP servers to automatically detect which repository the client is working in
- **Implementation**: `get_client_repo_root(ctx) -> Path | None` in `src/mcp_server.py`
  - Attempts to read `ctx.roots` from FastMCP Context
  - Returns the first root URI from the roots list if available
  - Returns None if roots protocol is not supported by the client (instead of raising an error)
- **Client compatibility**:
  - ✅ Roots-enabled clients (Claude Desktop, OpenCode): Never need to provide `repo_root` parameter
  - ⚠️ Basic MCP clients without roots support: Must provide `repo_root` parameter explicitly
- **Architecture decision - Optional Context Parameter**:
  - All MCP tool functions accept `ctx: Context | None = None` to support both client types
  - When `ctx=None`, the function falls back to using the explicit `repo_root` parameter
  - This design allows the same function signature to work for all MCP clients
- **Docstring documentation**:
  - All 11 MCP tool functions have been updated with consistent documentation
  - Each docstring includes explanation of both `repo_root` and `ctx` parameters
  - Usage examples show both scenarios (with and without roots protocol support)
  - Standard wording: "For MCP clients that don't support roots protocol, this will be None"
- **How MCP clients should detect and use**:
  - Roots-enabled clients: Simply call tools without any repo_root parameter
  - Non-roots clients: Detect that `ctx.roots` is unavailable and provide `repo_root="/path/to/repo"` in all tool calls
  - The server automatically handles the fallback chain transparently

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


## Hive-Based Architecture

**Core Components**:
- All tickets use hive-prefixed IDs (e.g., "backend.bees-abc")
- Path resolution requires hive-prefixed IDs
- ID generation scans all configured hives for uniqueness
- Index files are per-hive (e.g., `backend/index.md`, `frontend/index.md`)
- Watcher monitors all hive directories simultaneously

**Architecture Requirements**:
- `get_ticket_path()` requires hive-prefixed IDs
- `list_tickets()` returns empty list if no hives configured
- `infer_ticket_type_from_id()` requires hive prefix in ID

## Flat Storage Architecture (bees_version 1.1)

**Storage Architecture**: See `docs/architecture/storage.md` for comprehensive documentation of hive directory structure, identity markers, ticket schema versioning, and flat storage design.

**Key Points for Implementation**:
- All tickets stored at hive root: `{hive_root}/{ticket_id}.md`
- Type information comes from YAML frontmatter, not directory location
- `bees_version` field required in all ticket frontmatter for identification
- Functions like `get_ticket_path()`, `list_tickets()`, `infer_ticket_type_from_id()` implement flat storage
- Legacy hierarchical storage (epics/, tasks/, subtasks/ subdirectories) no longer supported

## Design Principles

1. **Markdown-First**: Tickets are human-readable markdown files
2. **Type Safety**: Dataclasses and validation ensure schema compliance
3. **Atomicity**: File operations are atomic to prevent corruption
4. **Simplicity**: Simple factory functions over complex frameworks
5. **Extensibility**: Clean module boundaries support future features
6. **Explicit Write Operations**: Write operations (create/update/delete) fail fast without recovery attempts

## Error Handling Architecture

### Design Decision: Strict Validation for Write Operations

**Context:** The system has two approaches to hive resolution:
- `scan_for_hive()`: Recovery mechanism that searches for relocated hives using `.hive` markers
- Config-based lookup: Direct hive resolution using `.bees/config.json`

**Decision:** Write operations (`create_ticket`, `update_ticket`, `delete_ticket`) use STRICT validation and do NOT attempt automatic hive recovery via `scan_for_hive()`.

**Rationale:**

1. **Write vs Read Philosophy:**
   - Write operations should be explicit and fail fast to prevent unintended data mutations
   - Read operations can be more forgiving and attempt recovery
   - Creating tickets in the wrong location due to auto-recovery could cause data integrity issues

2. **Consistency Across Operations:**
   - `update_ticket()` and `delete_ticket()` already fail fast when hive not in config (via `get_ticket_path()`)
   - `create_ticket()` follows the same pattern for consistent behavior
   - All write operations have uniform error handling semantics

3. **Recovery Scope:**
   - `scan_for_hive()` is designed as a recovery tool for exceptional scenarios (hive relocation)
   - Normal operations should use registered hives from config
   - Auto-recovery during writes could mask configuration issues

4. **Error Clarity:**
   - Explicit errors guide users to fix configuration (run `colonize_hive` to register)
   - Clear distinction: "hive not registered" vs "hive not found anywhere"
   - Enhanced error messages provide actionable guidance

**Implementation:**

In `_create_ticket()` (line 982-993):
```python
# Validate hive exists in config
# Design Decision: create_ticket is STRICT and does not attempt hive recovery via scan_for_hive.
normalized_hive = normalize_hive_name(hive_name)
config = load_bees_config()
if not config or normalized_hive not in config.hives:
    error_msg = (
        f"Hive '{hive_name}' (normalized: '{normalized_hive}') does not exist in config. "
        f"Please create the hive first using colonize_hive. "
        f"If the hive directory exists but isn't registered, you may need to run colonize_hive to register it."
    )
    raise ValueError(error_msg)
```

**Consistency:**

- `get_ticket_path()` in `src/paths.py` (line 75-76): Raises `ValueError` if hive not in config
- `infer_ticket_type_from_id()` in `src/paths.py` (line 140-141): Returns `None` if hive not in config
- All path resolution functions fail fast without recovery attempts

**Future Considerations:**

If scan_for_hive recovery is needed for write operations, it should be:
- Opt-in via explicit parameter (e.g., `allow_recovery=True`)
- Logged prominently when recovery is attempted
- Limited to specific use cases (e.g., migration tools, recovery commands)


## MCP Server Architecture

See [docs/architecture/mcp_server.md](../architecture/mcp_server.md) for complete MCP server architecture documentation, including HTTP transport, available tools, repo_root resolution strategy, and integration patterns.


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


## Query System Architecture

The query system implements a multi-stage pipeline for filtering and traversing tickets. Queries consist of sequential stages, with each stage either filtering tickets using search terms (type=, id=, title~, label~, parent=) or traversing relationships using graph terms (parent, children, up_dependencies, down_dependencies). All tickets are loaded once into memory for efficient execution. The system includes query parser validation, search executor (AND logic filtering), graph executor (relationship traversal), and pipeline evaluator (orchestration).

**For complete architecture details, see [docs/architecture/queries.md](../architecture/queries.md)**


## Pipeline Evaluator Architecture

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
  - Scans hive root directories (flat storage: `{hive_name}/*.md`)
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
  - Returns last generated markdown
  - Requires at least one configured hive (TICKETS_DIR removed)

**scan_tickets() Function** (`src/index_generator.py`):
- Uses updated `list_tickets()` from `paths.py` which scans hive root directories (flat storage)
- `list_tickets()` validates `bees_version` field presence and filters by YAML `type` field
- Excludes `/eggs` and `/evicted` subdirectories automatically via `list_tickets()`
- Groups tickets by type using YAML frontmatter `type` field, not directory structure
- Added `hive_name: str | None` parameter for filtering
- When hive_name provided: only returns tickets with matching hive prefix
- Hive prefix extraction: splits ticket ID on first dot (e.g., `backend.bees-abc1` → `backend`)
- Tickets without dots excluded when filtering by hive
- When hive_name omitted: returns all tickets from all hives (no filtering)

**MCP Tool Integration** (`src/mcp_server.py`):
- `_generate_index()` tool accepts optional `hive_name` parameter
- Passes parameter through to `generate_index()` function
- Updated tool docstring to describe hive_name behavior

**Index Location Strategy**:
- Hive-specific indexes: `{hive_path}/index.md` (e.g., `/path/to/backend/index.md`)
- Each hive's index is independent and only contains tickets from that hive

**Integration with Hive Config**:
- Loads `.bees/config.json` to get hive paths via `load_bees_config()`
- Looks up hive path using normalized hive name as key
- Falls back to `{cwd}/{hive_name}/` if hive not in config
- Creates hive directory if needed before writing index

**Index Requirements**:
- All indexes must be generated for configured hives
- Hive configuration is required for index generation

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

### Index Link Generation and Flat Storage (Task bees-qjt92)

**Purpose**: Fix index markdown link generation to work with flat storage architecture where all tickets are stored in hive root instead of type-specific subdirectories.

**Problem**: Links in `index.md` were pointing to non-existent type subdirectories (`tickets/{type}s/`) after migration to flat storage architecture. Example broken link: `tickets/tasks/bees-abc1.md`.

**Architecture Decision**: Relative Path Links
- Design choice: Use relative paths from index location to ticket files
- Link format: `{ticket_id}.md` (e.g., `backend.bees-abc1.md`)
- Rationale: Simple, works with flat storage, no redundant path information
- Alternative rejected: Absolute paths would require hardcoded hive paths and break portability

**Implementation Changes**:

**format_index_markdown() Function** (`src/index_generator.py`, line 150):
- **Before**: `tickets/{ticket.type}s/{ticket.id}.md`
- **After**: `{ticket.id}.md`
- Link format: `[ticket-id: title](ticket-id.md)`
- Works from `{hive_name}/index.md` to `{hive_name}/{ticket_id}.md`
- No type subdirectories in path

**is_index_stale() Function** (`src/index_generator.py`, lines 216-223):
- **Before**: Scanned type-specific subdirectories (`/epics`, `/tasks`, `/subtasks`)
- **After**: Scans hive root directory directly with glob pattern `*.md`
- Skips `index.md` itself when checking modification times
- Compares all ticket files in hive root against index modification time
- Returns `True` if any ticket file is newer than index

**Integration with Flat Storage**:
- All tickets stored as `{ticket_id}.md` in hive root directory
- `bees_version: 1.1` field in YAML frontmatter identifies ticket files
- No directory structure based on ticket type
- Ticket type determined from YAML `type` field, not file location

**Benefits**:
- Links work correctly with flat storage architecture
- Simpler link format (no redundant type information)
- Consistent with hive root storage model
- Portable across different hive locations

### Test Architecture for Flat Storage (Task bees-kr4km)

**Purpose**: Update test_generate_demo_tickets.py to validate flat storage architecture where all ticket types are stored in hive root directory instead of type-specific subdirectories.

**Problem**: Tests were checking for tickets in subdirectories (`default/epics/`, `default/tasks/`, `default/subtasks/`) but the flat storage architecture (Epic bees-yuql) stores all tickets in hive root (`default/`).

**Architecture Decision**: Single Directory Location Testing
- Design choice: Verify all ticket types exist in hive root directory, not in type subdirectories
- Rationale: Aligns with flat storage architecture where ticket type is determined from YAML `type` field, not file location
- Keeps tests simple by checking single directory location
- Alternative rejected: Testing both locations would be redundant and fail to catch regressions

**Implementation Changes**:

**Path Updates** (`tests/test_generate_demo_tickets.py`):
- Line 94: `epics_dir = setup_tickets_dir / "default" / "epics"` → `default_dir = setup_tickets_dir / "default"`
- Line 154: `tasks_dir = setup_tickets_dir / "default" / "tasks"` → `default_dir = setup_tickets_dir / "default"`
- Line 223: `subtasks_dir = setup_tickets_dir / "default" / "subtasks"` → `default_dir = setup_tickets_dir / "default"`
- All file existence assertions now check `default_dir / f"{ticket_id}.md"`

**New Test Class** (`TestFlatStorageArchitecture`):
1. **test_fixtures_use_flat_storage_paths**: Verifies tickets exist in hive root, not in subdirectories
   - Checks all epics, tasks, subtasks are in `default/` root
   - Verifies tickets NOT in old subdirectories (`/epics`, `/tasks`, `/subtasks`)
   - Validates bidirectional constraints (exists in root AND not in subdirs)

2. **test_missing_ticket_in_root_directory**: Tests edge case of missing ticket files
   - Uses hive-prefixed ticket ID format (`default.bees-fake123`)
   - Verifies graceful handling of FileNotFoundError or ValueError
   - Ensures reader doesn't falsely succeed for non-existent tickets

3. **test_tickets_not_in_wrong_subdirectories**: Validates subdirectories are empty or non-existent
   - Checks old subdirectories (`epics/`, `tasks/`, `subtasks/`) contain no `.md` files
   - Verifies all generated tickets exist in hive root
   - Catches regressions where code accidentally creates tickets in old locations

**Integration with Flat Storage Architecture**:
- Tests now validate flat storage requirements (Epic bees-yuql):
  - All tickets in hive root directory
  - Ticket type determined from YAML `type` field
  - No type-specific subdirectories used
  - `bees_version: 1.1` identifies markdown files as tickets
- Test fixture creates hive root structure matching production architecture
- Supports multi-hive testing (fixture creates `default` hive with proper config)

**Test Coverage**:
- `tests/test_generate_demo_tickets.py`: 28 tests passing (100% pass rate)
- Validates demo ticket generation for epics, tasks, subtasks
- Verifies relationships, dependencies, and metadata diversity
- Confirms flat storage path resolution

## Future Considerations

- MCP server delete tool implementation (Task bees-49g)
- MCP server startup script and configuration (Task bees-nas)
- Change tracking/audit log

## Named Query System

Allows registration of reusable static queries. Queries stored persistently in `.bees/queries.yaml` with YAML format.

### Components

**Query Storage** (`src/query_storage.py`): Manages `.bees/queries.yaml` with save/load/list operations. All queries are validated at registration time to provide immediate feedback on structural errors.

**MCP Tools**: The add_named_query function registers static queries and validates them at registration time. This ensures immediate feedback on any structural errors, making query registration safer and providing clearer error messages. Query execution returns a result dictionary containing the count of matching tickets and a sorted list of ticket IDs. Execution failures due to missing queries raise ValueError exceptions.

### Multi-Hive Query Filtering (Task bees-062t)

**Purpose**: Enable filtering query results to only tickets from specified hives, supporting multi-hive repository setups where different teams or projects maintain separate ticket collections.

**Architecture Decision**: Filter at Pipeline Entry Point
- Design choice: Apply hive filter at the start of pipeline execution, before any stage processing
- Rationale: Reduces work for all subsequent stages, provides consistent semantics across search/graph operations
- Alternative rejected: Per-stage filtering would complicate executor logic and create inconsistent behavior

**Implementation Flow**:
```
execute_query(query_name, hive_names)
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
- Tickets without dots are excluded from filtered results
- Applied to initial result set before stage execution begins

**Integration with PipelineEvaluator**:
- Parameter passed from MCP tool through to PipelineEvaluator.execute_query()
- Filter applied once at pipeline initialization, not re-applied per stage
- Uses same ticket ID parsing logic as path resolution (split on first dot)
- Default behavior: omitting hive_names includes all tickets (not a compatibility feature)

### Free-Form Query Execution (Task bees-1ircz, Epic bees-dgen1)

**Purpose**: Enable one-step ad-hoc query execution without persisting queries to the registry. Complements named queries by providing exploratory query capability without cluttering `.bees/queries.yaml` with temporary or single-use queries.

**Design Decision: Ad-Hoc vs Reusable Queries**
- Named queries (`add_named_query` + `execute_query`): Two-step process, persists to disk, suitable for reusable queries
- Freeform queries (`execute_freeform_query`): One-step process, no disk persistence, suitable for ad-hoc exploration
- Rationale: Separates exploratory workflows from production query registry, prevents registry pollution with temporary queries
- Alternative rejected: Auto-cleaning temporary queries would add complexity and potential race conditions

**Architecture: Reuse Existing Components**
- Uses `QueryParser.parse_and_validate()` for validation (same as `add_named_query`)
- Uses `PipelineEvaluator.execute_query()` for execution (same as `execute_query`)
- No new validation or execution logic required
- Only difference: skip the `save_query()` step in workflow

**Implementation Flow**:
```
execute_freeform_query(query_yaml, hive_names)
  ↓
QueryParser.parse_and_validate(query_yaml)
  ↓
[NO disk write - skip save_query()]
  ↓
Validate hive existence in .bees/config.json
  ↓
PipelineEvaluator.execute_query(stages, hive_names)
  ↓
Return results with stages_executed count
```

**MCP Tool Interface** (`src/mcp_server.py`):
- Function: `_execute_freeform_query(query_yaml: str, hive_names: list[str] | None = None)`
- Returns: `{status, result_count, ticket_ids, stages_executed}`
- Registered with FastMCP via `mcp.tool()` decorator
- Parameters identical to `execute_query` except `query_yaml` replaces `query_name`

**Error Handling**:
- Query validation errors: Raises `ValueError` with message "Invalid query structure: {error}"
- Hive validation errors: Raises `ValueError` with message "Hive not found: {hive_name}. Available hives: {list}"
- Execution errors: Raises `ValueError` with message "Failed to execute freeform query: {error}"
- Same error semantics as `execute_query` for consistency

**Integration with Existing Query Infrastructure**:
- Shares same validation rules as `add_named_query` (no syntax differences)
- Shares same execution engine as `execute_query` (identical query semantics)
- Supports hive filtering identically to `execute_query` (same validation and filtering logic)
- Logging: Info-level for successful execution, error-level for failures

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
- `_execute_query(query_name: str, hive_names: list[str] | None = None)`
- Parameter order: query_name (required), hive_names (optional list)
- Returns: Dict with status, query_name, result_count, ticket_ids (filtered by hive if specified)
- **Design Decision**: Removed params parameter (Epic bees-94krc) for simplicity. This reduces complexity with zero production usage impact.

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

## Test Architecture

**Task**: bees-f3emd - Update all tests to use hive-prefixed IDs

**Rationale**: Enforce consistent hive-based architecture. All tickets must have hive prefixes (e.g., `default.bees-abc`).

**Architecture Decision**: Mandatory Hive Prefixes
- `hive_name` parameter is REQUIRED for all `create_ticket()` calls
- Path resolution requires hive-prefixed IDs with ValueError for invalid format
- All tests use hive-prefixed format

**Test Strategy**:
1. **Test fixtures** - All mock ticket data uses `default.bees-xyz` format
2. **Validation tests** - Tests verify `hive_name` is required and raises clear errors when missing
3. **Hive-based architecture** - All tests use hive-based architecture

**Files Modified**:
- **tests/test_reader.py** - Updated all ticket IDs to hive-prefixed format
- **tests/test_corruption_state.py** - Updated sample ticket IDs
- **tests/test_graph_executor.py** - Updated all fixture IDs to `default.bees-*` format
- **tests/test_cli.py** - Updated assertions to expect hive-prefixed IDs
- **tests/test_create_ticket.py** - Fixed fixture to use `tmp_path`
- Multiple test files - Batch updated ticket IDs in mock data

**Test Results**:
- 750 tests passing (80% pass rate)

**Documentation**:
- README.md documents hive_name requirement
- master_plan.md updated with test architecture details

### Test Architecture for rename_hive() MCP Command

**Task**: bees-b87t3 - Add unit tests for rename_hive() MCP command

**Purpose**: Comprehensive test coverage for the 10-step hive rename operation that updates config, regenerates ticket IDs, renames files, updates frontmatter, and patches cross-references across all hives.

**Test File**: `tests/test_mcp_rename_hive.py`

**Fixture Strategy**:
- **temp_hive_setup**: Creates isolated temporary directory with multiple hives (backend, frontend, api_layer)
- Config-based setup: Initializes `.bees/config.json` with test hives using `BeesConfig` and `HiveConfig`
- Pre-populated tickets: Creates sample tickets with various reference types (parent, children, dependencies, up_dependencies, down_dependencies)
- Cross-hive references: Frontend tickets reference backend tickets to validate cross-hive update logic
- Identity markers: Creates `.hive/identity.json` files with normalized_name and display_name
- Isolation: Each test gets fresh temporary directory via pytest's `tmp_path` fixture

**Test Organization**:

1. **TestRenameHiveSuccess** - Success cases for rename operations
   - Basic rename: Validates config update, file renaming, ID regeneration
   - Frontmatter updates: Verifies 'id' field updated in ticket YAML
   - Cross-hive references: Confirms references in other hives are updated
   - Parent references: Validates child tickets' parent field updated
   - Hive marker updates: Checks `.hive/identity.json` updated with new names
   - Empty hive: Tests rename with no tickets
   - Complex dependencies: Multiple dependency types (parent, children, dependencies, up_dependencies, down_dependencies)

2. **TestRenameHiveErrors** - Error handling and validation
   - Missing hive: Returns `hive_not_found` error
   - Name conflict: Returns `name_conflict` when new name exists
   - Invalid names: Handles names that normalize to empty string
   - File conflicts: Detects when renamed file would overwrite existing file

3. **TestRenameHiveEdgeCases** - Edge cases and special scenarios
   - Special characters: Normalization of hyphens, spaces, case
   - Display name preservation: Preserves original case in display_name
   - Missing marker file: Creates new `.hive/identity.json` if missing
   - No cross-references: Handles rename when no references exist
   - Malformed frontmatter: Skips tickets with invalid YAML gracefully
   - Linter integration: Notes that linter validation is deferred (stubbed)
   - Name normalization: Both old_name and new_name normalized before lookup
   - Children field: Updates parent tickets' children list

4. **TestRenameHiveIntegration** - End-to-end workflow validation
   - Full rename workflow: Validates all 10 steps complete successfully
   - Isolation verification: Confirms other hives unaffected except for reference updates

**Coverage Strategy for 10-Step Operation**:
1. Config update (step 1-3): Validate old hive removed, new hive added with correct display_name
2. ID regeneration (step 5): Check id_mapping dict created correctly
3. File rename (step 6): Verify old files gone, new files exist with new IDs
4. Frontmatter update (step 7): Read files and confirm 'id' field matches new ID
5. Cross-reference update (step 8): Scan all hives and verify dependencies/parent/children updated
6. Marker update (step 9): Check `.hive/identity.json` has new normalized_name and display_name
7. Linter validation (step 10): Note stubbed - deferred per implementation comments

**Mocking Approach**:
- **No mocking for core operations**: Tests use real filesystem operations in temporary directories
- **Minimal mocking**: Only linter integration test attempted mocking (but linter doesn't exist, so test updated to validate stub behavior)
- **Real config I/O**: Tests read/write actual `.bees/config.json` files
- **Real YAML parsing**: Tests parse actual YAML frontmatter using production parser

**Integration with Existing MCP Test Patterns**:
- Follows pattern from `test_mcp_create_ticket_hive.py`: Config-based setup, temporary directories, fixture per test class
- Uses same imports: `BeesConfig`, `HiveConfig`, `save_bees_config`, `load_bees_config`
- Consistent fixture naming: `temp_hive_setup` similar to `temp_tickets_dir`
- Import pattern: Imports `_rename_hive` (internal function) not `rename_hive` (FunctionTool wrapper)

**Key Implementation Details**:
- Tests import `_rename_hive` directly (the implementation function), not `rename_hive` (the FastMCP tool wrapper)
- Fixture uses `monkeypatch.chdir(tmp_path)` to ensure config writes to test directory
- All tests validate return dict structure: `{'status': 'success'/'error', 'message': str, ...}`
- Error tests check both `status` and `error_type` fields
- Cross-reference tests verify updates in multiple files across different hives

**Test Execution**:
- 22 tests total covering success, error, edge cases, and integration scenarios
- All tests pass with 100% success rate
- Tests run in ~1 second (fast due to small test data and no external dependencies)

