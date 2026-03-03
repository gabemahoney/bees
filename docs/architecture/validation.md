# Validation Architecture

This document covers the linter infrastructure, index generation, and corruption detection systems that maintain data integrity in the Bees ticket management system.

## Overview

Bees uses three complementary systems to prevent data corruption:

1. **Linter**: Validates ticket schema and relationship consistency
2. **Index Generator**: Creates per-hive markdown indexes with validation
3. **Corruption Detection**: Identifies integrity issues and generates structured reports

These systems work together to ensure the ticket database remains consistent despite having no centralized database or daemon processes.

## Validation Levels

Bees implements a three-level validation strategy to separate concerns between the Model (permissive), Reader (structural), and Linter (strict):

**Model Validation** (`Ticket.__post_init__` in `src/models.py`):
- Accepts ANY type value and parent configuration
- No business rule validation at model instantiation
- Allows corrupt tickets to instantiate for linter processing
- Purpose: Enable linter to load and analyze corrupt tickets without blocking on instantiation

**Structural Validation** (`validate_structure()` in `src/validator.py`):
- Used by Reader when loading tickets from disk
- Checks only required fields exist: `id`, `type`, `title`, `ticket_status`
- Validates fields are not empty and have basic correct types (id and title are strings)
- Does NOT validate business rules (valid ticket types, subtask parent requirements)
- Allows Reader to load tickets with invalid types for later Linter inspection
- Purpose: Ensure tickets can be parsed without enforcing config-dependent rules

**Business Validation** (`validate_ticket_business()` in `src/validator.py`):
- Used by Linter for strict validation
- Validates ticket type against config `child_tiers`
- Validates subtasks have parent field
- Validates field types (lists are lists of strings, parent is string or None)
- Enforces all business rules and config dependencies
- Purpose: Enforce referential integrity and config compliance

**Validation Functions** (`src/validator.py`):
- `validate_structure()` - Structural validation for Reader
- `validate_ticket_business()` - Business validation orchestrator for Linter
- `validate_ticket_type()` - Type validation against config
- `validate_subtask_parent()` - Subtask parent requirement check
- `validate_field_types()` - List and parent field type validation
- `validate_id_format()` - ID format regex check (reusable utility)

**Design Rationale**:
- Permissive model enables instantiation of corrupt tickets for linter analysis
- Separation enables Reader to load tickets with type issues (e.g., `t99` when only `t1-t3` exist)
- Linter can then report business rule violations without Reader failing on load
- Supports future use case: config changes that make existing tickets temporarily invalid
- Model/Reader remain permissive while Linter maintains strict integrity checks

**Example Validation Flow**:
```python
# Corrupt ticket with invalid type
ticket = Ticket(id="t1.amx.12", type="invalid_type", title="Test")
# ✅ Model accepts any type - instantiation succeeds

# Reader structural validation
validate_structure(ticket_dict)
# ✅ Passes - required fields present

# Linter business validation
validate_ticket_business(ticket, config)
# ❌ Fails - "Invalid ticket type: 'invalid_type'"
```

## Per-Hive Ticket Type Enforcement

Ticket operations validate ticket types against hive-resolved child_tiers configuration, enabling per-hive tier customization and enforcement of bees-only hives.

### create_ticket Enforcement

**Type Validation** (`_create_ticket()` in `src/mcp_ticket_ops.py`):
- Resolves child_tiers for target hive using `resolve_child_tiers_for_hive()`
- Validates ticket_type against resolved child_tiers via `validate_ticket_type()`
- Enforces bees-only restriction when resolved child_tiers is `{}`
- Accepts friendly tier names in addition to canonical tier IDs — if child_tiers configures t1 = ["Task", "Tasks"], then `ticket_type="Task"` and `ticket_type="Tasks"` are both valid and resolve to `"t1"` internally

**Bees-Only Hive Enforcement**:
Before type validation, resolves child_tiers for the target hive. If the resolved child_tiers is an empty dict (`{}`), only bee (t0) tickets are allowed. Attempting to create any child tier raises a ValueError with a descriptive bees-only message.

**Validation Flow**:
1. Normalize hive_name to get normalized_hive
2. Call `validate_ticket_type(ticket_type, normalized_hive)`
3. Resolve child_tiers for hive
4. Check bees-only restriction if child_tiers is `{}`
5. Proceed with ticket creation if validation passes

### update_ticket Hive Resolution

**Hive Name Resolution** (`_update_ticket()` in `src/mcp_ticket_ops.py`):
- Accepts optional `hive_name` parameter for O(1) lookup
- Falls back to O(n) scan via `find_hive_for_ticket()` if hive_name not provided
- Validates resolved hive exists in config
- Does NOT validate ticket type (parent/children/type are immutable after creation)

**Resolution Modes**:
- **With hive_name**: Validate hive exists in config, use provided name
- **Without hive_name**: Scan all configured hives to find ticket location

### Error Messages

**Bees-only rejection**:
```
Hive 'my_hive' is configured as bees-only. Only bee (t0) tickets can be created.
```

**Invalid type for hive**:
```
Invalid ticket type 't3' for hive 'my_hive'. Valid types: ['bee', 't1', 't2']
```
When child_tiers are configured, the valid types list also includes friendly names (singular and plural). For example, if t1 = ["Task", "Tasks"], the list becomes `['bee', 't1', 'Task', 'Tasks', 't2', ...]`.

**Hive not found**:
```
Hive 'unknown_hive' not found in configuration
```

### Egg Field Validation

**Bee Tickets**:
- `egg` field is required in frontmatter for bee tickets
- `null` is a valid value for the egg field
- Any type is accepted for egg values (`str`, `int`, `dict`, etc.)

**Child Tier Tickets**:
- `egg` field must NOT be present in child tier frontmatter (t1, t2, t3, etc.)
- Child tiers do not inherit or store egg values from their parent bees

## Linter Architecture

The linter validates ticket structure and relationships through a two-phase scanning and validation process. Implementation spans `src/linter.py`, `src/linter_report.py`, and integrates with existing reader and ID utilities.

### Core Components

**LinterReport Module** (`src/linter_report.py`):
- `ValidationError` dataclass represents individual validation errors with fields: `ticket_id`, `error_type`, `message`, `severity`
- Severity levels: `error` (critical) or `warning` (non-critical)
- `LinterReport` class collects and queries validation errors
- Methods: `add_error()`, `get_errors()` with filtering, `is_corrupt()` for database health check
- Output formats: `to_json()`, `to_markdown()`, `to_dict()` for different consumers
- Summary statistics via `get_summary()` for error counts by type and severity

**Linter Module** (`src/linter.py`):
- `TicketScanner` class loads tickets from filesystem using `src/reader.py`
- Scans hive directories recursively (hierarchical storage: `{hive_name}/**/*.md`)
- Validates hierarchical pattern: directory name must match file stem (`{ticket_id}/{ticket_id}.md`)
- Excludes special directories (`eggs/`, `evicted/`, `.hive/`) and `index.md` files
- Returns generator of `Ticket` objects with types validated against `~/.bees/config.json`
- Handles filesystem errors gracefully, logging and skipping invalid files
- `Linter` class orchestrates validation through `run()` method:
  - Loads all tickets via TicketScanner
  - Runs per-ticket validations
  - Runs cross-ticket validations (uniqueness, relationships)
  - Enforces directory structure (auto-moves misplaced tickets)
  - Returns `LinterReport` with collected errors and fixes

### Validation Rules

**Schema Validation**:
- ID format validation: matches `{type_prefix}.{shortID}` pattern with length validation
  - Bee: `b.XXX` (3-char shortID)
  - Tier N: `t{N}.{N+3 char shortID}`
  - Charset: Base58-style (58 chars: 1-9, A-H, J-N, P-Z, a-k, m-z)
  - Excludes visually ambiguous: 0, O, I, l
  - Reuses `is_valid_ticket_id()` from `src/id_utils.py` for consistency
  - Error: `invalid_id` - ID does not match type-prefixed format
- Path/ID consistency validation: ticket directory name and filename stem must match the ticket's `id` field
  - Implemented via `validate_path_matches_id()` in `src/linter.py` (SR-7.3)
  - Checks that the containing directory name equals the ticket ID (e.g., `b.amx/` for ticket `b.amx`)
  - Checks that the filename stem equals the ticket ID (e.g., `b.amx.md` for ticket `b.amx`)
  - Error: `path_id_mismatch` - Ticket directory name or filename stem does not match the ticket ID
- ID uniqueness check across all ticket types and hives (IDs are globally unique)
- Title format validation: no newlines allowed
  - Rejects `\n` or `\r` characters in title field
  - Warning: `multiline_title` - Title contains newline characters
- Schema version validation: must be valid semver format
  - Must match pattern `x.y.z` where x, y, z are numeric (e.g., `1.0.0`)
  - Error: `invalid_schema_version` - Schema version is missing or not in valid semver format
- Created_at validation: should be present and in valid ISO 8601 format
  - Warning: `missing_date` - created_at field is null or missing
  - Warning: `invalid_date_format` - created_at is not valid ISO 8601 format

**GUID Validation**:
- Every ticket must have a `guid` field (32-char globally unique identifier)
  - Generated at ticket creation from the ticket's short_id + random ID_CHARSET suffix
  - GUID_LENGTH: 32 characters
  - GUID prefix must match the ticket's short_id (portion after the dot in ticket ID)
  - Error: `missing_guid` - Ticket has no guid field (guid is None)
  - Error: `invalid_guid_length` - GUID length is not 32 characters
  - Error: `invalid_guid_charset` - GUID contains characters not in GUID_CHARSET (0, O, I, l)
  - Error: `invalid_guid_prefix` - GUID does not start with the ticket's short_id
- GUID is immutable after ticket creation (enforced by `_update_ticket()`)

**Type/Value Validation**:

*Status Field Validator*:
- Type check: status must be a string (error: `invalid_field_type`)
- Value check: If status_values configured via three-level resolution (hive → scope → global), validates status is in the list (error: `invalid_status`). If not configured, any string is valid (freeform mode).

*Egg JSON-Serializable Validator*:
- Only applies to bee tickets (child tiers skipped)
- Validates egg field is JSON-serializable (error: `invalid_field_type`)
- Null/None egg value is valid

**Disallowed Fields Detection**:
- Scans raw YAML frontmatter for deprecated fields removed in schema cleanup (SR-6.3)
- Accesses raw frontmatter via `parse_frontmatter()` since Ticket model filters these fields
- Disallowed fields: `owner`, `priority`, `description`, `created_by`, `updated_at`, `bees_version`
- Each disallowed field generates a separate error: `disallowed_field`
- Detect-only, no auto-removal

**Relationship Validation**:

*Asymmetric Parent/Child Validation Policy (SR-6.2)*:
- **Parents referencing missing children**: NOT an error (allows forward references during ticket creation)
- **Children referencing missing parents**: Error `orphaned_ticket` (children cannot exist without valid parent)
- This asymmetry supports natural ticket creation workflow while preventing orphaned tickets

*Parent Field Validators*:
- ID format validation: Checks parent field matches ticket ID format (error: `invalid_parent_id`)
- Existence validation: Verifies parent ticket exists in database (error: `orphaned_ticket`)
- Dangling reference detection: Checks parent ID exists across all in-scope hives via `all_scope_ticket_map`. If the ID is absent from every hive, reports `dangling_parent` rather than `orphaned_ticket`. Skipped if any hive fails to load during map construction (see `hive_load_failure` below).

*Children Field Validators*:
- ID format validation: Checks child IDs match ticket ID format (error: `invalid_child_id`)
- Type hierarchy validation: Verifies child ticket type matches expected tier (error: `invalid_child_type`)

*Removed/Renamed Errors*:
- `orphaned_parent` error no longer generated (per asymmetric policy)
- `orphaned_child` renamed to `orphaned_ticket` for clarity

*Dependency Field Validators*:
- ID format validation: Checks dependency IDs match ticket ID format (error: `invalid_dependency_id`)
- Same-type restriction: Dependencies must be between tickets of the same type — bees depend on bees, t1 on t1, etc. (error: `cross_type_dependency`)
- Dangling reference detection: Checks each dependency ID exists in any in-scope hive via `all_scope_ticket_map` cross-scope lookup (error: `dangling_dependency`). Only runs when the map builds successfully; skipped entirely if any hive fails to load (see `hive_load_failure` below).

*Dependency Bidirectional Consistency*:
- up_dependencies ↔ down_dependencies bidirectional consistency (existing check)
- Cycle detection in both blocking dependencies and hierarchical relationships

*Cross-Scope Ticket Map*:
- Before running dangling reference checks, the linter builds `all_scope_ticket_map`: a flat map of ticket ID → ticket covering every ticket in every in-scope hive
- If any hive fails to load during map construction, the linter records a `hive_load_failure` error and skips all dangling reference detection for that run — a partial map would produce false-positive `dangling_*` errors
- When map construction succeeds, `dangling_dependency` and `dangling_parent` checks use this map to distinguish valid cross-hive refs from truly missing refs

**Hive Validation**:
- Validates ticket IDs match type-prefixed format (no hive prefix in IDs)
- IDs are globally unique across all hives in repository
- Dependencies can reference tickets in any hive (same-tier restriction still applies)
- Integrates with `sanitize_hive` MCP tool for per-hive checks

**Tier Validation**:
- Validates ticket types are defined in child_tiers config (validate_tier_exists)
- 'bee' type is always valid (immutable base type)
- Returns blocking errors (error_type="unknown_tier") for undefined tier types
- Prevents orphaned ticket types after config changes (e.g., removing t3 tier)
- Validates parent type matches tier hierarchy expectations (validate_parent_children_bidirectional)
  - For each parent-child relationship, verifies parent's type matches expected type based on child's tier
  - Helper function `_get_expected_parent_type()` determines expected parent type from config
  - Tier hierarchy rules: t1 expects bee parent, t2 expects t1 parent, t3 expects t2 parent, etc.
  - Returns blocking errors (error_type="invalid_tier_parent") when parent type doesn't match config expectation
  - Works with N-tier configs (t1 expects bee parent, t2 expects t1 parent, etc.)

**Directory Structure Enforcement**:
- `enforce_directory_structure()` method ensures filesystem matches frontmatter relationships
- Validates each ticket's directory location based on `parent` field in frontmatter
- For bees (no parent): Verifies directory is at hive root level
- For child tickets: Verifies directory is directly under parent's directory
- **Auto-correction behavior**: Automatically moves misplaced ticket directories to correct location
- Uses `shutil.move()` to relocate entire directory subtree (preserves all children)
- Reports fixes via `LinterReport.add_fix()` with type `"move_directory"`
- Triggered on every linter run (part of watcher loop and manual `sanitize_hive`)

**Directory Enforcement Rules**:
- **Source of truth**: Frontmatter `parent` field is authoritative, not filesystem location
- **Bee placement**: Directory must be at `{hive_root}/{ticket_id}/`
- **Child placement**: Directory must be at `{parent_dir}/{ticket_id}/`
- **Subtree moves**: Moving a ticket directory automatically includes all nested children
- **Recovery from accidents**: Manual file manager moves are auto-corrected on next linter run

**Example Enforcement Scenarios**:

*Misplaced child ticket*:
- Frontmatter: `parent: "b.amx"`
- Current location: `hive_root/wrong_location/t1.amx.12/`
- Expected location: `hive_root/b.amx/t1.amx.12/`
- Action: Linter moves `t1.amx.12/` directory under `b.amx/` directory

*Misplaced bee*:
- Frontmatter: `parent: null` (bee has no parent)
- Current location: `hive_root/some_dir/b.xyz/`
- Expected location: `hive_root/b.xyz/`
- Action: Linter moves `b.xyz/` directory to hive root

### Algorithm Choices

**DFS with Path Tracking**: Selected for cycle detection to achieve O(V+E) time complexity while naturally maintaining the path from root to current node. DFS is proven correct for detecting cycles in directed graphs.

**Dual Representation for Path Tracking**: Uses both a list (ordered cycle extraction) and a set (O(1) cycle detection) to balance human-readable error reporting with performance. Global visited set prevents redundant traversals across disconnected components.

**Separate Passes by Relationship Type**: Runs independent DFS traversals for blocking dependencies versus hierarchical relationships, enabling targeted error messages and preventing false positives from mixing relationship semantics.

### Integration Points

- Uses `src/reader.py` to load tickets with schema validation
- Uses `Ticket` model from `src/models.py` with dynamic type validation against `~/.bees/config.json`
- Reader's validator catches schema violations during load; linter focuses on cross-ticket validation

## Watcher-Linter Integration Pipeline

The watcher automatically triggers linter validation and index regeneration when ticket files change, maintaining data integrity through a debounced pipeline. Implementation in `src/watcher.py`.

### Pipeline Flow

```
File change detected (watchdog observer)
  ↓
Debounce timer resets (2 second default)
  ↓
After quiet period:
  ↓
Linter runs on ALL hives (with auto-fix enabled)
  ↓
Index regenerated for all hives
  ↓
Linter file moves trigger new watch events
  ↓
Debounced normally → cycle repeats until stable
```

### Core Integration

**TicketChangeHandler** (`src/watcher.py`):
- Monitors all configured hive directories recursively using watchdog observer
- Debounces file change events using `threading.Timer` (default 2 seconds)
- Triggers `_do_regeneration()` callback after debounce quiet period
- Filters events: only processes `.md` files, ignores `index.md` to prevent loops

**_do_regeneration() Callback** (`src/watcher.py:62-116`):
- Loads config to enumerate all registered hives
- For each hive: instantiates Linter with `auto_fix=True` and runs validation
- Error isolation: linter failure on one hive logs error but continues to next hive
- After all hives linted: calls `generate_index()` to regenerate all hive indexes
- Linter never blocks index generation - errors are logged and processing continues

### Linter Auto-Fix Triggers File Moves

**Directory enforcement behavior**:
- Linter's `enforce_directory_structure()` method auto-moves misplaced ticket directories
- File moves trigger new watchdog events (created/modified/deleted)
- New events reset debounce timer → linter runs again after quiet period
- Cycle repeats until filesystem structure matches frontmatter (stable state)

**Convergence guarantee**:
- Each linter run moves tickets closer to correct locations
- Eventually reaches stable state where no moves are needed
- Debouncing prevents infinite loops by consolidating rapid changes

### Error Isolation Design

**Hive-level isolation**:
- Linter failure on one hive doesn't prevent linting other hives
- Each hive wrapped in try-except block with continue on error
- Errors logged with `exc_info=True` for debugging

**Index generation isolation**:
- Index regeneration always runs after linter phase completes
- Linter errors never block index generation for successfully linted hives
- Ensures ticket changes are reflected in index even if validation fails

### Manual Trigger Independence

**sanitize_hive MCP tool**:
- Remains independent manual trigger for linter validation
- Accepts `hive_name` parameter to target specific hive
- Runs linter with `auto_fix=True` on specified hive only
- Returns structured report with fixes applied and remaining errors
- Does not trigger watcher pipeline (synchronous operation)

### Watcher Lifecycle

**Start watcher** (`start_watcher()` in `src/watcher.py`):
- Loads config and schedules recursive observer on each hive directory
- Runs in foreground loop until interrupted (Ctrl+C)
- Validates at least one hive is configured before starting

**Cleanup**:
- SIGINT handler calls `event_handler.cleanup()` to cancel pending timers
- Stops observer and joins threads for graceful shutdown
- Prevents orphaned timer threads on exit

### Debounce Configuration

**Default settings**:
- Debounce period: 2 seconds (configurable via `debounce_seconds` parameter)
- Timer implementation: `threading.Timer` for thread-safe debouncing
- Lock mechanism: `_timer_lock` prevents race conditions on timer cancellation

**Rationale for 2 second default**:
- Long enough to consolidate rapid file changes (e.g., linter moving multiple tickets)
- Short enough for responsive feedback during development
- Prevents redundant linter runs during batch operations

### Auto-Fix Capability

The linter implements three categories of auto-fix rules that automatically repair data integrity issues.

**1. Directory Structure Enforcement** (always enabled):
- Implemented via `enforce_directory_structure()` method
- Runs on every linter invocation (not gated by `auto_fix` flag)
- Ensures filesystem structure matches frontmatter `parent` field (source of truth)
- Automatically moves misplaced ticket directories to correct location
- Uses `shutil.move()` to relocate entire directory subtrees (preserves all children)
- Triggered by manual `sanitize_hive` calls and any direct linter invocation
- Reported as fixes in `LinterReport` (type: `"move_directory"`)

**2. Bidirectional Field Repair** (when `auto_fix=True`):
- Implemented via `validate_parent_children_bidirectional()` and `validate_dependencies_bidirectional()` methods
- Repairs parent↔children relationship inconsistencies:
  - If child lists parent but parent doesn't list child in children array, adds child to parent's children
  - If parent lists child but child doesn't list parent, sets parent field on child
- Repairs up_dependencies↔down_dependencies relationship inconsistencies:
  - If ticket A lists B in up_dependencies but B doesn't list A in down_dependencies, adds A to B's down_dependencies
  - If ticket A lists B in down_dependencies but B doesn't list A in up_dependencies, adds A to B's up_dependencies
- Modified tickets are written back to filesystem via `_save_modified_tickets()`
- Reported as fixes in `LinterReport` (types: `"add_child"`, `"set_parent"`, `"add_down_dependency"`, `"add_up_dependency"`)

**3. Dangling Reference Removal** (when `auto_fix_dangling_refs: true` in global config):
- Controlled by `auto_fix_dangling_refs` global config flag — separate from `auto_fix`; dangling ref removal is not triggered by `auto_fix=True` alone
- Requires a successfully built `all_scope_ticket_map` (skipped if `hive_load_failure` occurs)
- Removes dangling dependency IDs: deletes the offending ID from `up_dependencies` or `down_dependencies` and writes the ticket to disk (fix type: `"remove_dangling_dependency"`)
- Clears dangling parent refs: sets the `parent` field to `null` and writes the ticket to disk (fix type: `"clear_dangling_parent"`)
- Reported as fixes in `LinterReport` with the respective fix types above

**Source of Truth**: Frontmatter fields (`parent`, `children`, `up_dependencies`, `down_dependencies`) are authoritative. Directory structure, bidirectional consistency, and dangling reference state are all derived from frontmatter and enforced by these auto-fix rules.

**`sanitize_hive` Integration**: The `sanitize_hive` MCP tool triggers all three auto-fix categories by running the linter with `auto_fix=True`, ensuring comprehensive repair of directory structure, bidirectional relationships, and dangling references (the last requires `auto_fix_dangling_refs: true` in global config).

## Input Validation and Security

Bees implements defense-in-depth input validation to prevent path traversal attacks and malicious file operations.

### Design Decision: Validate at Entry Point

**Rationale**: Input validation must occur at the earliest possible point before any filesystem operations to prevent path traversal attacks. The `write_ticket_file()` function in `src/writer.py` is the entry point for all ticket file creation operations.

**Implementation**: Validation happens before `get_ticket_path()` call, ensuring malicious ticket IDs never reach filesystem path construction logic.

**Alternative Rejected**: Validating inside `get_ticket_path()` would be too late - path construction might already have security implications. Entry point validation provides strongest security guarantee.

### Security Validation Architecture

**write_ticket_file() Entry Point** (`src/writer.py:67-102`):
```python
def write_ticket_file(ticket_id: str, ticket_type: TicketType, ...):
    # Validate ticket_id format before any filesystem operations
    if not validate_id_format(ticket_id):
        raise ValueError(f"Invalid ticket ID format: {ticket_id}")
    
    # Only after validation do we construct filesystem paths
    target_path = get_ticket_path(ticket_id, ticket_type)
    ...
```

**validate_id_format() Function** (`src/validator.py:104-124`):
- Validates ticket ID matches type-prefixed format: `^(b\.[1-9A-HJ-NP-Za-km-z]{3}|t(\d+)\.[1-9A-HJ-NP-Za-km-z]+)$`
- Rejects path traversal attempts: `../etc/passwd`, `../../sensitive/file`
- Rejects malformed IDs: `b.OOOL`, `invalid-format`, empty strings
- Returns boolean: `True` for valid format, `False` for invalid

**Integration with Existing Validator Module**:
- `validate_id_format()` was already present in `src/validator.py` for schema validation
- Import and validation call added to `write_ticket_file()` for security
- Reuses existing ID validation logic for consistency across codebase

### Attack Surface Reduction

**Before**: `write_ticket_file()` accepted any string as `ticket_id` parameter and passed it directly to filesystem operations without validation.

**After**: All ticket IDs validated against strict format requirements before filesystem path construction.

**Prevented Attack Vectors**:
- Path traversal: `../../../etc/passwd` rejected before filesystem access
- Directory escaping: `../../sensitive/data.md` blocked by format validation
- Malformed paths: empty strings, special characters, uppercase rejected
- Cross-hive attacks: IDs without proper hive prefix format rejected

### Error Handling

**User-Facing Errors**: Invalid ticket IDs raise `ValueError` with descriptive message: `"Invalid ticket ID format: {ticket_id}"`

**Early Failure**: Validation fails immediately before any filesystem operations, preventing partial state or security vulnerabilities.

**Consistency**: Error messages match existing validator module patterns for consistent user experience.

## Index Generation Architecture

Index generation creates per-hive markdown indexes that provide isolated ticket visibility at hive roots. Implementation in `src/index_generator.py`.

### Design Rationale: Per-Hive vs Global

**Decision**: Each hive maintains its own `index.md` at hive root directory.

**Rationale**: Hives represent separate ticket collections; independent indexing avoids mixing concerns across projects. Enables per-project ticket visibility and simplifies navigation.

**Alternative Rejected**: Single global index would require filtering logic in all readers and complicate multi-project workflows.

### Implementation Flow

```
generate_index(hive_name="backend")
  ↓
scan_tickets(hive_name="backend")
  ↓
Filter tickets by hive membership (tickets in backend hive directory)
  ↓
format_index_markdown(tickets)
  ↓
Write to {hive_path}/index.md
```

### Core Functions

**generate_index()** (`src/index_generator.py`):
- Signature: `generate_index(status_filter, type_filter, hive_name) -> str`
- With `hive_name` provided: generates index only for specified hive, writes to `{hive_path}/index.md`
- With `hive_name` omitted: iterates all registered hives from `~/.bees/config.json`, generates separate index.md for each
- Returns markdown content as string
- Requires at least one configured hive

**scan_tickets()** (`src/index_generator.py`):
- Uses `list_tickets()` from `paths.py` which scans hive directories recursively
- Validates `bees_version` field presence and filters by YAML `type` field
- Validates hierarchical pattern: directory name matches file stem
- Excludes `/eggs`, `/evicted`, and `.hive` subdirectories automatically
- Groups tickets by type using YAML frontmatter `type` field
- With `hive_name` parameter: only returns tickets from specified hive
- Without `hive_name`: returns all tickets from all hives

**format_index_markdown()** (`src/index_generator.py`):
- Builds a parent-child hierarchy tree then renders collapsible `<details>/<summary>` blocks
- Each bee renders as a `<details>` block with an `id` attribute derived from its ticket ID
- Non-leaf children (tickets with their own children) nest as inner `<details>` blocks
- Leaf children render as plain list items inside their parent's `<details>` body
- Empty parents display a tier-aware message (e.g., "*No epics*") using configured plural display names
- Unparented tickets (not reachable from any bee root) appear under a separate collapsible "Unparented Tickets" section
- Zero tickets produces only the `# Ticket Index` header and timestamp — no `<details>` blocks emitted
- Link format: `[ticket-id: title](relative-path) (status)` — paths computed relative to hive root
- Includes Mermaid `graph TD` dependency diagrams (see below)

**Mermaid Dependency Graphs**:
- Visualize **dependency relationships** (`up_dependencies` edges between tickets) — NOT parent/child hierarchy
- Generated by a private graph builder that accepts a flat list of tickets and returns a fenced mermaid code block
- **Bee-level graph**: placed between the timestamp and the first `<details>` block, covering all bee-to-bee dependencies
- **Child-tier graphs**: placed inside each parent's `<details>` body before its children elements, covering dependencies among that parent's children
- Graph block is **omitted entirely** when no dependency edges exist at that level — no empty diagram is rendered
- Nodes are styled with status-based CSS classes (larva, pupa, worker, finished) and include click directives linking to the ticket's anchor ID in the index
- External dependencies (tickets outside the current graph scope) render with a distinct stadium shape

### Index Staleness Detection

Staleness detection scans each hive directory recursively and compares ticket file modification times against the index file. If any ticket file is newer than `index.md`, the index is considered stale. Skips `index.md` itself and non-ticket files during the scan.

### MCP Integration

The index generation MCP tool accepts an optional `hive_name` parameter, enabling per-hive or all-hive index regeneration via the MCP protocol.

### Use Cases

- Regenerate index for specific hive: `generate_index(hive_name="backend")`
- Regenerate all hive indexes: `generate_index()`
- Generate filtered index: `generate_index(hive_name="backend", status="open")`

## Corruption Detection

Corruption detection identifies database integrity issues through linter validation and generates structured reports for troubleshooting and recovery.

### Error Categories

**Critical Errors** (mark database as corrupt):
- Malformed ticket IDs not matching type-prefixed pattern (`b.XXX`, `t1.XXXX`, etc.)
- Duplicate ticket IDs across system (IDs are globally unique)
- Bidirectional relationship inconsistencies (parent/children, dependencies)
- Circular dependencies in blocking relationships or hierarchical structure
- Misplaced ticket directories not matching parent relationships

**Warnings** (non-critical):
- Missing optional fields
- Style guideline violations
- Deprecated field usage

### Corruption Report Structure

Reports contain structured error information:
- Ticket ID and error type for each validation failure
- Error message and severity level
- Summary statistics (error counts by type and severity)
- Timestamp of validation run

### Detection Flow

```
Linter.run()
  ↓
Validate all tickets
  ↓
Generate LinterReport
  ↓
Return LinterReport to caller
```

### Auto-Fix vs Manual Intervention

**Auto-fixable Issues**:
- Future capability using relationship sync functions
- Bidirectional relationship repairs
- ID normalization where safe

**Requires Manual Intervention**:
- Circular dependency resolution (requires understanding intended structure)
- Duplicate ID conflicts (requires choosing which ticket to preserve)

### Database Integrity Guarantees

**sanitize_hive Tool** (`src/mcp_server.py`):
- Runs linter on specified hive with comprehensive validations
- Validates ticket IDs match type-prefixed format
- Enforces directory structure (auto-moves misplaced tickets)
- Validates bidirectional relationships (parent/children, dependencies)
- Attempts automatic fixes where possible
- Returns structured report with fixes applied and remaining errors

### Error Reporting Formats

**JSON Format**: Machine-readable for tooling integration, includes full error details and summary statistics.

**Markdown Format**: Human-readable for CLI display, formatted for terminal output with section headers.

**Dict Format**: Internal representation for programmatic access within Python codebase.

## References

- Linter implementation: `src/linter.py`, `src/linter_report.py`
- Hive utilities: `src/hive_utils.py`
- Index generator: `src/index_generator.py`
- ID utilities: `src/id_utils.py`
- Reader module: `src/reader.py`, `src/parser.py`, `src/validator.py`
- Writer module: `src/writer.py`, `src/ticket_factory.py`
- Relationship sync: `src/relationship_sync.py`
- MCP server tools: `src/mcp_server.py`
