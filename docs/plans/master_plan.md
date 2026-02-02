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
- `HiveConfig` dataclass: Represents a single hive with `path`, `display_name`, and `created_at` fields
  - `path` (str): Absolute path to hive directory
  - `display_name` (str): Original user-provided display name
  - `created_at` (str): ISO 8601 timestamp when hive was created
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
  (returns None), validates JSON and schema_version, raises ValueError for malformed JSON.
  Parses all HiveConfig fields including `created_at` timestamp from JSON.
- `save_bees_config(config)`: Writes BeesConfig to config.json using atomic write pattern,
  calls ensure_bees_dir() before writing, sets schema_version to '1.0' if not set.
  Serializes all HiveConfig fields including `created_at` to JSON.
- `init_bees_config_if_needed()`: Creates config on first call, returns existing on subsequent calls

**Atomic Write Implementation** (Task bees-dpxir):
- `save_bees_config()` uses atomic write pattern to prevent config corruption if process crashes during write
- Architecture: `tempfile.mkstemp()` → `os.fdopen()` → `json.dump()` → `os.replace()`
- Implementation details:
  - Creates temp file in `.bees/` directory with prefix `.config.json.`
  - Writes JSON to temp file with indent=2 formatting
  - Adds trailing newline after JSON content
  - Uses `os.replace()` to atomically rename temp file to `config.json`
  - Cleanup: Deletes temp file on write failure in except block
- Design decision: Temp file + rename pattern prevents partial writes if process crashes or disk fills
- Rationale: Config corruption could make entire system unusable; atomic writes ensure either old config remains intact or new config is complete
- Error handling: Raises IOError with descriptive message, cleans up temp file on any exception
- POSIX guarantee: `os.replace()` is atomic on POSIX systems (rename syscall), ensuring no partial file states

**Error Handling**:
- Malformed JSON raises ValueError with descriptive message
- Invalid schema_version type raises ValueError
- Invalid hive data type raises ValueError
- File write errors raise IOError

**Error Handling Design - load_hive_config_dict()** (Task bees-jav9h):
- `load_hive_config_dict()` in `src/config.py` returns default structure on JSON/IO errors for graceful degradation
- Behavior: Catches `json.JSONDecodeError` and `IOError`, logs warning, returns default `{'hives': {}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}` structure
- Warning messages logged: `"Malformed JSON in {config_path}: {e}. Returning default structure."` and `"IO error reading {config_path}: {e}. Returning default structure."`
- Rationale: Dict API provides graceful degradation for flexibility, while dataclass API (`load_bees_config()`) raises ValueError for strict validation
- Benefits: Prevents application crashes while making errors visible through logs, suitable for scripts and MCP layer requiring robustness
- Design contrast: `load_bees_config()` raises ValueError on malformed JSON for strict type-safe validation, while `load_hive_config_dict()` returns defaults for flexible operations

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

**Duplicate Name Validation Implementation** (Task bees-qzkp):
- Validation occurs in `colonize_hive()` orchestration function (Step 3)
- Calls `validate_unique_hive_name(normalized_name)` from config module
- Checks normalized name against existing hives in `.bees/config.json`
- Returns error dict (not exception) on duplicate with `error_type: "duplicate_name_error"`
- Error message format: `"A hive with normalized name '{normalized_name}' already exists. Display name: '{existing_display_name}'"`
- Validation functions: `normalize_hive_name()` (src/id_utils.py), `load_bees_config()` (src/config.py), `validate_unique_hive_name()` (src/config.py)
- Test coverage: 16 tests for `normalize_hive_name()` in tests/test_id_utils.py, 8 tests for duplicate validation in tests/test_colonize_hive.py::TestColonizeHiveOrchestrationUnit
- All tests passing as of Task bees-qzkp completion

**Storage Architecture**:
- Hives dictionary uses normalized names as keys: `config.hives['back_end']`
- Each HiveConfig stores both path and display_name
- JSON structure: `{"hives": {"back_end": {"display_name": "Back End", "path": "/path/to/hive"}}}`
- This design enables case-insensitive, whitespace-normalized lookups while preserving user intent
- Display names shown in UI/reports, normalized names used for internal operations

**Dict vs Dataclass API Architecture**:

The config module (`src/config.py`) provides two parallel APIs for configuration management:

1. **Dataclass-based API** (Primary, type-safe):
   - `load_bees_config() -> BeesConfig | None`: Returns typed BeesConfig object with attribute access
   - `save_bees_config(config: BeesConfig) -> None`: Writes BeesConfig object to disk
   - `register_hive(normalized_name, display_name, path, timestamp) -> BeesConfig`: Returns updated BeesConfig
   - **Use when**: You need type safety, attribute access (e.g., `config.hives['backend'].path`), or working with the core config module
   - **Benefits**: Type checking, IDE autocomplete, validation through dataclass fields
   - **Error handling**: Raises ValueError on malformed JSON, returns None if file doesn't exist

2. **Dict-based API** (Wrapper functions for flexibility):
   - `load_hive_config_dict() -> dict`: Returns config as dictionary
   - `write_hive_config_dict(config: dict) -> None`: Writes dict to disk
   - `register_hive_dict(normalized_name, display_name, path, timestamp) -> dict`: Returns updated dict
   - **Use when**: You need flexible dict operations, JSON-like manipulation, or backward compatibility
   - **Benefits**: No type constraints, direct JSON mapping, easier for dynamic config operations
   - **Error handling**: Returns default structure `{'hives': {}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}` on malformed JSON or missing file (with logged warning)

**Design Decisions**:
- Both APIs operate on the same `.bees/config.json` file with identical structure
- Dict API wraps the dataclass API internally for core operations (NOT used yet, but designed for this)
- Dict API provides graceful degradation (returns defaults) while dataclass API provides strict validation (raises errors)
- Choose dataclass API for internal modules requiring type safety; dict API for MCP layer or scripts requiring flexibility
- All functions preserve `created_at` timestamps in ISO 8601 format

**Trade-offs**:
- Dataclass API: Type safety and validation come at cost of less flexibility for dynamic operations
- Dict API: Flexibility and graceful error handling come at cost of losing type safety and IDE support
- Maintaining two APIs adds some code duplication but provides best tool for each use case

### Config Registration Functions (Task bees-svir)

**Purpose**: Implement local config load/write/register functions in `mcp_server.py` for hive registration during colonization, providing atomic writes and clear error handling.

**Architecture Decision**: Parallel Config System at MCP Layer
- Design choice: Implement `load_hive_config()`, `write_hive_config()`, and `register_hive_in_config()` in `mcp_server.py` alongside existing `src/config.py` module functions
- Rationale: MCP server layer needs direct control over config I/O with explicit error handling, atomic writes, and timestamp management
- Benefits: Clear separation of concerns (config module for validation/data structures, mcp_server for I/O), atomic write safety, detailed error responses for MCP clients
- Alternative rejected: Using only `src/config.py` functions would require changing their signatures and error handling patterns, affecting other parts of the codebase

**Implementation**:

1. **load_hive_config() Function** (`src/mcp_server.py`):
   - Returns dict (not BeesConfig object) with structure: `{'hives': {}, 'allow_cross_hive_dependencies': False, 'schema_version': '1.0'}`
   - Reads `.bees/config.json` if it exists, returns empty structure if file not found
   - Handles JSON parse errors gracefully (logs warning, returns default structure)
   - Handles I/O errors gracefully (logs warning, returns default structure)
   - No exceptions raised (returns default instead)

2. **write_hive_config(config: dict) Function** (`src/mcp_server.py`):
   - Creates `.bees/` directory if needed using `Path.mkdir(parents=True, exist_ok=True)`
   - Performs atomic write using temporary file + rename strategy:
     - `tempfile.mkstemp()` creates temp file in `.bees/` directory
     - Writes JSON with `indent=2` formatting + trailing newline
     - `os.replace()` atomically renames temp file to `config.json`
   - Raises `IOError` for all error cases (directory creation, file write, permissions, disk space)
   - Cleanup: Deletes temp file on write failure (best effort in except block)
   - Error messages include context: `"Cannot write config file: {original_error}"`

3. **register_hive_in_config(normalized_name, display_name, path, timestamp) Function** (`src/mcp_server.py`):
   - Loads current config using `load_hive_config()`
   - Adds new hive entry to `config['hives'][normalized_name]`
   - Entry structure: `{'path': path, 'display_name': display_name, 'created_at': timestamp.isoformat()}`
   - Returns updated config dict (does not persist to disk)
   - Caller's responsibility to call `write_hive_config()` to persist changes
   - This separation enables transaction-like behavior (load → modify → write with error handling)

**Integration with colonize_hive() Workflow**:
- Step 5 (config registration) updated to use new functions instead of `src/config.py` functions
- Flow: `register_hive_in_config()` → `write_hive_config()` wrapped in try/except
- Catches `IOError`, `PermissionError`, `OSError` and returns error dict
- Error types: `config_write_error`, `config_error`
- Timestamp generated once in colonize_hive using `datetime.now()`, passed to register function

**Atomic Write Strategy**:
- Purpose: Prevent config corruption if write interrupted (crash, disk full, etc.)
- Implementation: Write to temp file (`.config.json.XXXXXX`) → rename to `config.json`
- `os.replace()` is atomic on POSIX systems (rename syscall)
- Guarantees: Either old config intact or new config complete (no partial writes)
- Temp file cleanup: Best effort deletion on error, but temp files in `.bees/` won't affect functionality

**Error Handling Philosophy**:
- `load_hive_config()`: Returns default structure on any error (graceful degradation)
- `write_hive_config()`: Raises IOError on any error (fail-fast for write operations)
- `register_hive_in_config()`: Pure function, no I/O, no exceptions
- `colonize_hive()`: Catches all exceptions and wraps in error dict for MCP clients

**Timestamp Format**:
- Uses ISO 8601 format via `datetime.isoformat()` (e.g., `"2026-02-01T12:00:00.123456"`)
- Stored in `created_at` field of each hive entry
- Provides audit trail of when hives were registered
- Format chosen for: human-readability, sortability, timezone-aware capability

**Test Coverage** (`tests/test_config_registration.py`):
- 20 tests passing covering all three functions and colonize_hive integration
- Load tests: missing file, valid JSON, malformed JSON, I/O errors
- Write tests: valid config, directory creation, formatting, atomic behavior, permissions, overwrite
- Register tests: adds entry, preserves existing, returns config, doesn't persist
- Integration tests: colonize_hive registration, error handling, timestamps, multiple hives
- All error paths tested with mocked failures

**Why Separate from src/config.py**:
- Different return types: `load_hive_config()` returns dict, `load_bees_config()` returns BeesConfig
- Different error handling: MCP functions for operational errors (I/O), config module for data validation
- Different concerns: MCP layer focuses on HTTP/MCP error responses, config module on data structures
- Both systems coexist: `src/config.py` for validation/types, `mcp_server.py` for I/O operations
- No duplication of logic: Normalization and validation still in `src/config.py`, only I/O duplicated

### Config Module Consolidation (Task bees-gsitz)

**Purpose**: Standardize JSON error handling across config loading functions and consolidate config operations into `src/config.py` for maintainability.

**Architecture Decision**: Unified Config Module
- Design choice: Consolidate all config loading functions into `src/config.py` with consistent error handling strategy
- Rationale: Previously `load_hive_config()` in `mcp_server.py` caught `json.JSONDecodeError` and returned defaults (lines 332-338), while `load_bees_config()` in `config.py` raised `ValueError` (line 180). This inconsistency made error behavior unpredictable.
- Benefits: Single source of truth for config operations, predictable error handling, easier testing and debugging
- Error handling strategy: Return default structure on JSON errors for better UX (graceful degradation)

**Implementation Changes**:

1. **Moved load_hive_config() to config.py**:
   - Relocated from `src/mcp_server.py` (lines 321-345) to `src/config.py`
   - Function renamed to `load_hive_config_dict()` to clarify dict return type
   - Maintains backward compatibility via wrapper function if needed
   - Updated to use consistent error handling (return default dict on JSONDecodeError)

2. **Standardized load_bees_config() Error Handling**:
   - Changed from raising `ValueError` on JSON errors to returning default `BeesConfig` structure
   - Logs warning on malformed JSON: `"Malformed JSON in {config_path}: {e}. Returning default structure."`
   - Default structure: `BeesConfig(hives={}, allow_cross_hive_dependencies=False, schema_version='1.0')`
   - Matches behavior of `load_hive_config_dict()` for consistency

3. **Updated mcp_server.py Imports**:
   - Added `load_hive_config_dict` to imports from `config.py`
   - Removed duplicate function definition from `mcp_server.py`
   - All calls to `load_hive_config()` now use imported function from `config.py`
   - No functional changes to calling code

**Error Handling Strategy**:
- **Prefer returning defaults over raising exceptions** for config loading operations
- Rationale: Better user experience - malformed config shouldn't crash the application
- Logging strategy: Warning logs make errors visible without breaking functionality
- Applies to both `load_hive_config_dict()` and `load_bees_config()`
- Distinguishes between missing files (expected, return None or default) and malformed files (unexpected, log warning and return default)

**Integration Points**:
- `load_hive_config_dict()` called in:
  - `colonize_hive()` for hive registration
  - `register_hive_dict()` for adding new hive entries
  - MCP server initialization for loading existing hives
- `load_bees_config()` called in:
  - `init_bees_config_if_needed()` for on-demand initialization
  - `validate_unique_hive_name()` for duplicate checking
  - Query executor for hive path resolution

**Test Coverage**:
- Added tests in `tests/test_config.py` for JSON error handling
- Test cases: malformed JSON, valid JSON, missing files, default returns
- Verified warning logs on errors
- 100% coverage of error paths in both functions
- All tests passing after consolidation

### Hive Directory Structure (Task bees-55b6)

**Purpose**: Establish standardized directory layout for hive file organization and provide identity markers for hive recovery when directories are moved.

**Architecture Decision**: Three-Subdirectory Layout
- Design choice: Each hive contains `/eggs`, `/evicted`, and `/.hive` subdirectories with specific purposes
- Rationale: Separates future features from archived tickets, provides identity tracking for resilient path management
- Benefits: Clean organization, automatic hive recovery via markers, extensibility for future features
- Alternative rejected: Single flat directory would mix active and archived tickets, complicate cleanup

**Directory Structure**:
```
{hive_path}/
  ├── eggs/           # Reserved for future features (templates, workflows)
  ├── evicted/        # Archived/completed tickets for historical reference
  ├── .hive/          # Identity marker directory
  │   └── identity.json  # Hive metadata for recovery
  └── *.md            # Ticket files (flat storage - all types in root)
```

**Subdirectory Purposes**:
- `/eggs`: Reserved namespace for future feature expansion (e.g., ticket templates, pre-configured workflows, automation scripts)
- `/evicted`: Storage for archived or completed tickets, enabling historical reference without cluttering active ticket directories

**Flat Storage (bees_version 1.1)**:
- All ticket files stored in hive root directory (no type-specific subdirectories)
- Ticket type determined from YAML frontmatter `type` field
- Files named `{ticket_id}.md` (e.g., `backend.bees-abc1.md`)
- `/.hive/identity.json`: Identity marker containing hive metadata for automatic path recovery if hive is moved

**Identity Marker Format** (`/.hive/identity.json`):
```json
{
  "normalized_name": "back_end",
  "display_name": "Back End",
  "created_at": "2026-02-01T13:15:30.123456",
  "version": "1.0.0"
}
```

**Metadata Fields**:
- `normalized_name`: Normalized hive identifier for config lookups (e.g., "back_end")
- `display_name`: Original user-provided display name (e.g., "Back End")
- `created_at`: ISO 8601 timestamp of hive creation for auditing
- `version`: Hive format version for future schema evolution (currently "1.0.0")

**Implementation** (`src/mcp_server.py`):
- `colonize_hive(name: str, path: str) -> Dict[str, Any]` creates directory structure
- Uses `pathlib.Path.mkdir(parents=True, exist_ok=True)` for idempotent directory creation
- Error handling: Catches and re-raises `PermissionError` and `OSError` with informative messages
- Creates identity marker with metadata immediately after directory creation

**Error Handling Strategy**:
- Each directory creation wrapped in separate try/except blocks
- Errors include context about which directory failed and why
- Permission errors distinguished from general OS errors for clearer debugging
- All errors logged via standard logging module before re-raising

**Idempotency**:
- `exist_ok=True` parameter ensures repeated colonization calls don't fail
- Safe to call `colonize_hive()` multiple times on same path
- Existing directories and marker files are preserved, not overwritten
- Second call overwrites `.hive/identity.json` with fresh timestamp (acceptable design choice)

**Integration with Hive Recovery** (`scan_for_hive()` in `src/mcp_server.py`):
- Recursively scans repository for `.hive/identity.json` markers
- Extracts `normalized_name` from marker to identify moved hives
- Updates `.bees/config.json` with recovered hive path automatically
- Enables automatic path recovery when hives are moved within repository

**Error Handling for Config Updates** (Task bees-4rxaq):
- When `scan_for_hive()` finds a moved hive, it attempts to update `.bees/config.json` with the new path
- Previously: Config update failures were logged but silently suppressed, leading to config inconsistencies
- Now: Config update failures raise exceptions after logging, ensuring callers are aware of issues
- Exception types caught and re-raised: `IOError`, `json.JSONDecodeError`, `AttributeError`
- Design rationale: Fail-fast approach prevents config drift when filesystem or JSON errors occur
- Callers must handle exceptions appropriately, ensuring config consistency is maintained
- Exception flow: log error → re-raise → caller handles (cannot continue with stale config)
- Security benefit: Prevents silent config corruption that could lead to incorrect hive routing

**Design Rationale - Directory Layout**:
- `/eggs` provides forward compatibility without schema changes
- `/evicted` separates completed work from active tickets, improving scan performance
- `.hive/identity.json` enables self-describing directories independent of config.json
- Marker file approach more resilient than relying solely on path-based configuration

**Test Coverage** (`tests/test_colonize_hive.py`):
- 25 tests passing covering directory creation, marker creation, error handling
- Tests verify idempotent behavior, parent directory creation, metadata format
- Error handling tests confirm `PermissionError` and `OSError` raised with informative messages
- Marker tests validate all required metadata fields (normalized_name, display_name, created_at, version)

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

**Design Decision**: Bees version 1.1 migrated from hierarchical storage (type-specific subdirectories) to flat storage where all tickets are stored in hive root directory.

**Implementation Changes**:

1. **get_ticket_path()** (`src/paths.py`):
   - Returns: `{hive_root}/{ticket_id}.md` (e.g., `backend/backend.bees-abc1.md`)
   - Ticket type parameter is kept for API compatibility but no longer affects path resolution
   - No subdirectories: all tickets (epics, tasks, subtasks) in same directory

2. **infer_ticket_type_from_id()** (`src/paths.py`):
   - Reads ticket file from hive root: `{hive_root}/{ticket_id}.md`
   - Parses YAML frontmatter to extract `type` field
   - Validates `bees_version` field presence to confirm file is a valid ticket
   - Returns type from frontmatter, not from directory location
   - Returns None if file doesn't exist, YAML cannot be parsed, or `bees_version` field is missing

3. **list_tickets()** (`src/paths.py`):
   - Scans hive root directory directly: `{hive_root}/*.md`
   - No subdirectory traversal
   - Validates `bees_version` field presence for all markdown files
   - Only returns files with valid `bees_version` field (ignores non-ticket markdown files)
   - When filtering by type, reads YAML frontmatter from each file and checks `type` field
   - Uses `yaml.safe_load()` to parse frontmatter between `---` delimiters

4. **ensure_ticket_directory_exists()** (`src/paths.py`):
   - Simplified to create hive root directory only
   - Signature: `ensure_ticket_directory_exists(hive_name: str) -> None`
   - No ticket_type parameter (removed in flat storage)

5. **_load_tickets()** (`src/pipeline.py`):
   - Scans hive root directory only: `{hive_root}/*.md`
   - No recursive subdirectory scanning (removes subdirs list: ['epics', 'tasks', 'subtasks'])
   - Filters files by `bees_version` field presence (skips markdown files without it)
   - Explicitly skips subdirectories like `/eggs` and `/evicted` via parent directory check
   - Preserves existing YAML parsing and normalization logic
   - Calls `_build_reverse_relationships()` after loading to establish bidirectional links
   - **Performance**: O(n) where n = number of .md files in hive root (no recursion overhead)
   - **Design rationale**: Flat scanning faster than recursive traversal, simpler logic, bees_version field provides reliable ticket identification

6. **Type-Specific Directory References Removed**:
   - Removed `get_ticket_directory()` function and `type_to_dir` mapping
   - Updated docstrings in `src/writer.py`, `src/pipeline.py`, `src/reader.py`, `src/parser.py`
   - Updated `extract_existing_ids_from_directory()` to scan hive root instead of subdirectories
   - Removed all references to epics/, tasks/, subtasks/ subdirectories in error messages and comments

**Rationale**:
- Simplifies path resolution logic (no type-to-directory mapping needed)
- Reduces directory nesting (one less level)
- Type information now comes from YAML frontmatter (single source of truth)
- All ticket types treated uniformly by filesystem
- Enables easier migration and refactoring (type changes don't require file moves)

**Schema Version Field**:
- All tickets include `bees_version: 1.1` in YAML frontmatter
- Identifies markdown files as Bees tickets
- Enables backward compatibility if future schema changes are needed
- Automatically set during ticket creation via `create_ticket()`

**Path Examples**:
```
# Flat storage (bees_version 1.1)
backend/backend.bees-abc1.md
backend/backend.bees-xyz9.md
frontend/frontend.bees-250.md

# Legacy hierarchical (bees_version 1.0) - no longer supported
backend/epics/backend.bees-abc1.md
backend/tasks/backend.bees-xyz9.md
frontend/epics/frontend.bees-250.md
```

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

### Overview

The Bees MCP (Model Context Protocol) server provides a standardized interface for ticket write operations (create, update, delete) while maintaining relationship consistency. Built with FastMCP 2.14.4, the server exposes tools that AI agents and clients can use to manipulate tickets safely.

### Design Goals

1. **Relationship Consistency**: Automatically maintain reciprocal relationships (see Relationship Synchronization Module)
2. **Schema Validation**: Enforce ticket type rules (e.g., subtasks must have parent, epics cannot)
3. **Atomic Operations**: All relationship updates succeed or fail together
4. **Tool-Based Interface**: Standard MCP tool schemas for interoperability
5. **Health Monitoring**: Server lifecycle management and readiness checks
6. **Consistent Error Handling**: All MCP tools raise `ValueError` for errors (validation failures, missing resources, config errors) rather than returning error dicts. This provides consistent error propagation through the MCP protocol and simplifies error handling for clients.

### HTTP Transport Architecture

HTTP transport uses uvicorn ASGI server for MCP communication.

**Configuration**: See the README.md Quick Start section for HTTP transport configuration
details and the example configuration file at `docs/examples/claude-config-http.json`.

**Documentation Structure**: stdio transport documentation has been archived to
`docs/archive/stdio-transport.md`. This separation keeps the main README focused on the recommended
HTTP transport approach while preserving stdio instructions for users who need them. The
README now includes only a brief note about stdio with a link to the archived documentation.

**Implementation Details** (`src/main.py`):
The FastMCP framework provides HTTP transport through its `mcp.http_app` property, which returns a Starlette ASGI application instance. This application is passed to uvicorn, which handles the HTTP server hosting with configurable host, port, and logging settings. The architecture separates the MCP protocol handling (FastMCP) from the HTTP transport layer (uvicorn), allowing flexible deployment configurations. Reference: `src/main.py` lines 158-175.

```python
uvicorn.run(
    mcp.http_app,
    host=config.http.host,
    port=config.http.port,
    log_level=log_level
)
```

**HTTP Transport Testing & Validation** (Task bees-1u88):

End-to-end testing confirmed HTTP transport is production-ready. The testing process validated:

1. Server startup: `poetry run start-mcp` launches cleanly and binds to configured port
2. Connection verification: `claude mcp list` confirms successful connection
3. Tool execution: MCP tools execute successfully over HTTP transport
4. Stability: Clean connection lifecycle throughout testing

**HTTP Endpoint Routing** (Task bees-q5g7):

The server provides custom HTTP endpoints alongside FastMCP's built-in MCP protocol endpoints:

### Hive Colonization MCP Tool

**colonize_hive MCP Tool** (`_colonize_hive()` in `src/mcp_server.py`) exposes hive creation functionality via the MCP protocol, enabling AI agents to create and register new hive directories programmatically.

**MCP Tool Registration**: The tool is registered with FastMCP using the `mcp.tool()` decorator pattern, following the same registration approach as other MCP tools (create_ticket, update_ticket, delete_ticket). Registration occurs immediately after the function definition to ensure tool availability at server startup.

**Parameter Validation**: The wrapper validates two required parameters:
- `name` (string): Display name for the hive (e.g., "Back End", "Frontend")
- `path` (string): Absolute directory path where hive should be created

Path validation enforces three requirements:
1. Path must be absolute (not relative)
2. Path must exist on filesystem
3. Path must be within repository root (prevents hives outside git repo)

**Name Normalization**: Display names are normalized using the config system's `normalize_hive_name()` function. Normalization converts to lowercase, replaces non-alphanumeric characters with underscores, and validates the result is non-empty. This ensures consistent hive identification across the system.

**Uniqueness Check**: Before creating a hive, the tool verifies that the normalized name doesn't already exist in the hive registry using `validate_unique_hive_name()` from the config module. This prevents duplicate hive names that would cause ID collision.

**Directory Structure Creation**: Successful validation triggers creation of three components:
1. `/eggs` subdirectory for future feature storage
2. `/evicted` subdirectory for completed/archived tickets
3. `.hive/identity.json` marker file containing:
   - `normalized_name`: Internal identifier (e.g., "back_end")
   - `display_name`: Original name provided (e.g., "Back End")
   - `created_at`: ISO 8601 timestamp
   - `version`: Schema version for future compatibility

**Config Registration**: After directory structure creation, the hive is registered in `.bees/config.json` using the config module's `register_hive_dict()` and `write_hive_config_dict()` functions. This integration ensures the new hive is immediately available for ticket operations.

**Error Handling**: The wrapper returns structured error responses for validation failures:
- `validation_error`: Name normalizes to empty string
- `path_validation_error`: Path is relative, doesn't exist, or outside repo
- `duplicate_name_error`: Normalized name already exists in registry
- `filesystem_error`: Cannot create directories or write files
- `config_error`: Cannot read or write `.bees/config.json`

All errors are raised as `ValueError` to propagate through MCP protocol, with descriptive messages for client-side debugging.

**Linter Integration Stub**: The colonize_hive core function includes a placeholder for future linter integration. The linter will validate that no conflicting tickets exist across hives during colonization (e.g., duplicate ticket IDs, conflicting hive names). This is currently stubbed out and logged for future implementation.

### list_hives MCP Tool

**list_hives MCP Tool** (`_list_hives()` in `src/mcp_server.py`) provides visibility into all registered hives in the repository, returning their display names, normalized identifiers, and paths. This tool serves as the foundation for hive management operations, enabling AI agents and users to query existing hive configuration.

**MCP Tool Registration**: The tool is registered with FastMCP using the `mcp.tool()` decorator pattern, following the same approach as other MCP tools. The tool takes no parameters and returns structured hive data.

**Configuration Reading**: The tool reads `.bees/config.json` using `load_bees_config()` from the config module to retrieve all registered hives. This leverages the existing config infrastructure for consistent data access.

**Return Structure**: The tool returns structured JSON with three possible outcomes:

1. **Success with hives**:
   ```python
   {
     'status': 'success',
     'hives': [
       {
         'display_name': 'Back End',       # User-facing name
         'normalized_name': 'back_end',    # Internal identifier
         'path': '/absolute/path/to/hive'  # Hive directory location
       },
       ...
     ]
   }
   ```

2. **Success with no hives (config exists but empty)**:
   ```python
   {
     'status': 'success',
     'hives': [],
     'message': 'No hives configured'
   }
   ```

3. **Success with no hives (config doesn't exist)**:
   ```python
   {
     'status': 'success',
     'hives': [],
     'message': 'No hives configured'
   }
   ```

**Data Fields**: Each hive entry includes three fields:
- `display_name`: The original display name provided during colonization (preserves capitalization and spaces)
- `normalized_name`: The internal identifier used in ticket IDs (lowercased, underscored)
- `path`: Absolute path to the hive directory as registered in config

**Error Handling**: The tool gracefully handles missing or malformed configuration:
- Missing config file: Returns empty list with "No hives configured" message
- Empty hives in config: Returns empty list with "No hives configured" message
- Malformed config (exception): Raises ValueError with "Failed to list hives: {error}" message

This error handling ensures the tool never crashes and provides useful feedback to clients.

**Integration with Hive Management**: The list_hives tool is the first step in the hive management workflow:
- **list_hives()** → Discover existing hives
- **abandon_hive()** → Remove from config without deleting files
- **rename_hive()** → Modify hive names and update all references
- **sanitize_hive()** → Validate and repair (future)

### rename_hive MCP Tool

**rename_hive MCP Tool** (`_rename_hive()` in `src/mcp_server.py`) provides comprehensive hive renaming functionality that updates configuration, regenerates ticket IDs, renames files, updates frontmatter, and scans all hives to update cross-references. This is a complex operation that ensures database consistency across the entire multi-hive system.

**MCP Tool Registration**: The tool is registered with FastMCP using the `mcp.tool()` decorator pattern, following the same approach as other MCP tools.

**Parameters**:
- `old_name` (string, required): Current hive name (display or normalized)
- `new_name` (string, required): Desired new hive name

**Multi-Step Process**: The rename operation follows a strict sequence to maintain consistency:

1. **Name Normalization and Validation**:
   - Both `old_name` and `new_name` are normalized using `normalize_hive_name()`
   - Validates normalized names are not empty strings
   - Loads config and verifies `old_name` exists as a registered hive
   - Validates `new_name` doesn't conflict with existing hive keys
   - Returns error if validation fails

2. **Config Update**:
   - Retrieves hive configuration for `old_name`
   - Updates `display_name` field to `new_name`
   - Removes old hive entry from config dict
   - Adds new entry under `new_name` key
   - Saves updated config using `save_bees_config()`

3. **ID Regeneration**:
   - Scans hive directory for all `.md` files
   - Filters for ticket files matching `{old_normalized}.bees-*` pattern
   - Builds mapping: `old_id → new_id` by replacing hive prefix
   - Example: `backend.bees-abc1` → `api_layer.bees-abc1`
   - Preserves `bees-xxxx` suffix unchanged

4. **File Renaming**:
   - Iterates through ID mapping
   - Renames each file from `{old_id}.md` to `{new_id}.md`
   - Checks for filename conflicts before renaming
   - Returns error if any new filename already exists

5. **Frontmatter Update**:
   - Reads each renamed ticket file
   - Parses YAML frontmatter between `---` delimiters
   - Updates `id` field from old_id to new_id
   - Serializes updated frontmatter using `yaml.dump()`
   - Writes back to file with preserved body content

6. **Cross-Reference Update (All Hives)**:
   - Iterates through ALL hives in config (not just renamed hive)
   - Scans all ticket files in each hive
   - Parses frontmatter and checks relationship fields:
     - `parent` (string): Updates if matches old_id
     - `children` (list): Updates any matching old_ids
     - `dependencies` (list): Updates any matching old_ids
     - `up_dependencies` (list): Updates any matching old_ids
     - `down_dependencies` (list): Updates any matching old_ids
   - Writes back only files with changes
   - Tracks count of tickets updated for reporting

7. **.hive Marker Update**:
   - Locates `.hive/identity.json` in hive directory
   - Updates `normalized_name` and `display_name` fields
   - Creates marker if missing (recovery scenario)
   - Writes JSON with proper formatting

8. **Linter Validation (Stubbed)**:
   - Placeholder for running linter to validate database integrity
   - Future implementation will:
     - Import `Linter` from `src.linter`
     - Import `mark_corrupt` from `src.corruption_state`
     - Run linter on all hives
     - Call `mark_corrupt(report)` if errors found
     - Return error response with linter details if validation fails
   - Currently logged as stubbed for future work

**Return Structure**:
- **Success**:
  ```python
  {
    'status': 'success',
    'message': 'Hive renamed successfully from {old_name} to {new_name}',
    'old_name': str,
    'old_normalized': str,
    'new_name': str,
    'new_normalized': str,
    'tickets_updated': int,      # Tickets in renamed hive
    'cross_references_updated': int,  # Tickets in other hives updated
    'path': str
  }
  ```

- **Error**:
  ```python
  {
    'status': 'error',
    'message': str,
    'error_type': str  # One of: validation_error, hive_not_found, name_conflict,
                       # config_save_error, id_generation_error, file_rename_error,
                       # frontmatter_update_error, cross_reference_update_error,
                       # marker_update_error
  }
  ```

**Error Handling**: The operation can fail at multiple stages:
- `validation_error`: Name normalizes to empty string
- `hive_not_found`: old_name doesn't exist in config
- `name_conflict`: new_name already exists as registered hive
- `config_save_error`: Failed to persist config changes
- `id_generation_error`: Failed to build ID mapping
- `file_rename_error`: File conflict or rename failure
- `frontmatter_update_error`: Failed to parse or write frontmatter
- `cross_reference_update_error`: Failed to update references in other hives
- `marker_update_error`: Failed to update .hive marker file

**Atomicity Considerations**: The rename operation is NOT atomic - if it fails partway through, the database may be left in an inconsistent state. Future work could add transaction-like rollback support or pre-validation checks. Users should back up before renaming.

**Cross-Hive Impact**: This operation scans and potentially updates ALL hives in the system, not just the renamed hive. This ensures no dangling references remain, but means the operation's scope extends beyond the target hive. The `cross_references_updated` count in the response indicates how many tickets in OTHER hives were modified.

**Design Rationale**: The rename operation updates references even when `allow_cross_hive_dependencies` is disabled. This catches legacy references from before the setting was enabled, ensuring database consistency regardless of configuration changes over time.

**File Encoding for Cross-Platform Compatibility** (Task bees-vibje):
- All file operations in `rename_hive()` use explicit `encoding='utf-8'` parameter
- Implementation: All four `open()` calls (lines 2216, 2240, 2272, 2354) specify UTF-8 encoding
- Rationale: Without explicit encoding, Python uses platform default (e.g., cp1252 on Windows, potentially non-UTF-8 on some Linux systems), causing failures when ticket content contains non-ASCII characters
- Cross-platform guarantee: UTF-8 encoding ensures consistent behavior on Windows, macOS, Linux, and other platforms regardless of system locale settings
- Test coverage: `tests/test_rename_hive_encoding.py` includes unit tests for UTF-8 encoding enforcement and Unicode content handling (emoji, CJK characters, accented letters, CRLF line endings)
- Design decision: Explicit encoding applied to ALL file reads/writes (not just some), preventing edge case failures when users create tickets with special characters or when codebases are shared across platforms
- Impact: Prevents `UnicodeDecodeError` and `UnicodeEncodeError` exceptions on systems with non-UTF-8 default encodings

**Test Coverage**: Comprehensive test suite in `tests/test_mcp_server.py::TestListHives`:
- Success case with multiple hives
- Empty list when config doesn't exist
- Empty list when config exists but has no hives
- Correct field structure (display_name, normalized_name, path)
- Exception handling (graceful failure on errors)
- Single hive edge case
- Multiple hives (5+) stress test

### abandon_hive MCP Tool

**abandon_hive MCP Tool** (`_abandon_hive()` in `src/mcp_server.py`) provides a clean way to stop tracking a hive without deleting ticket files. This enables users to remove hive registrations from configuration while preserving all data on disk, allowing for future re-colonization or reference.

**Architecture**: The tool integrates with the config management system to safely remove hive entries:
- Normalizes hive name using `normalize_hive_name()` for lookup consistency
- Loads configuration using `load_bees_config()` to access current hive registry
- Validates hive exists before attempting removal
- Removes hive from `config.hives` dictionary
- Persists changes using `save_bees_config()` with atomic write guarantees

**Design Decisions**:
- **File preservation**: All ticket files, `.hive` marker, `/eggs`, and `/evicted` directories remain untouched on filesystem
- **When to use abandon vs delete**: Use `abandon_hive()` when you want to stop tracking a hive temporarily or permanently but need to keep the files for reference, migration, or future re-colonization. Use filesystem commands (`rm -rf`) if you want to permanently delete both registration and files.
- **Re-colonization support**: After abandoning a hive, you can re-colonize the same directory using `colonize_hive()` with the same or different display name, as long as the normalized name doesn't conflict with existing hives.

**Implementation Details**:
- Config modification approach: Direct dictionary deletion (`del config.hives[normalized_name]`) followed by atomic save
- Error handling strategy: Raises `ValueError` for all errors (hive not found, config errors) - consistent with `colonize_hive()` and other MCP tools
- Name normalization: Uses `normalize_hive_name()` to ensure both display names and normalized names work as input
- Validation: Checks hive exists in config before attempting removal, raises `ValueError` if not found

**Integration**:
- How it fits with `colonize_hive()`: Inverse operation - colonize adds to config, abandon removes from config. Both use consistent ValueError error handling.
- How it fits with `list_hives()`: Can be used together - list to discover hives, abandon to remove specific hive
- Edge cases handled:
  - Hive doesn't exist: Raises `ValueError` with message indicating normalized name not found
  - Last hive removal: Works correctly - results in empty `config.hives` dictionary
  - Multiple hives: Only removes specified hive, leaves others intact
  - Display name vs normalized name: Both work as input due to normalization before lookup

**Return Structure**:

Success case:
```python
{
  'status': 'success',
  'message': 'Hive "Back End" abandoned successfully',
  'display_name': 'Back End',
  'normalized_name': 'back_end',
  'path': '/absolute/path/to/hive'
}
```

Error case (hive not found):
```python
# Raises ValueError with message:
# "Hive 'backend' (normalized: 'backend') does not exist in config"
```

**Test Coverage**: Comprehensive test suite in `tests/test_mcp_server.py::TestAbandonHive` (13 tests):
- Hive removal from config verification
- File preservation (tickets, .hive marker, /eggs, /evicted)
- Error handling for non-existent hive
- Success message with display name
- Normalized name input handling
- Display name input handling
- Path return in success response
- Multiple hive handling (only target removed)
- Last hive removal (empty config)
- Name normalization (various input forms)
- Directory preservation (/eggs, /evicted)
- Response structure validation

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

