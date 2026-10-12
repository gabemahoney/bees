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

### Reference Materials Field Validation

**CLI Input Validation** (`src/cli.py` — `create-ticket` and `update-ticket`):
- The `--reference-materials` argument is validated at the CLI entry point before any core logic runs
- Valid values: `null` (omitted/None) or a JSON array of dicts
- If the parsed value is non-null and not a list of dicts, the command returns exit 1 with:
  ```json
  {"status": "error", "error_type": "invalid_argument", "message": "reference_materials must be a list of dicts or null"}
  ```
- This rejects malformed input before any ticket creation or mutation occurs

**Bee Tickets (Linter Validation)**:
- `reference_materials` field may be present in frontmatter for bee tickets
- `null` is a valid value for the `reference_materials` field
- When present, must be a list of dicts, each with a `value` key and an optional `resolver` key

**Child Tier Tickets**:
- `reference_materials` field must NOT be present in child tier frontmatter (t1, t2, t3, etc.)
- Child tiers do not inherit or store reference materials from their parent bees

### Priority Field Validation

This is entry-point validation of caller input. It is separate from the linter's Priority Validator, which checks tickets already on disk (see Linter Architecture).

**Core ops** (`create_ticket` and `update_ticket`):
- `priority` must be an integer or null. A boolean, float, or string returns `invalid_priority`
- The check runs first, before any file write and before relationship sync, so a rejected call changes nothing
- On create, null or omitted means no priority. On update, omitted leaves the stored value alone and null clears it
- Batch update checks the value once, up front: an invalid value rejects the whole call before any ticket is written

**MCP schema**:
- The advertised schema for `priority` is integer or null, with no string branch and no default on `update_ticket` (omitted still means unchanged). Internally the parameter is typed to accept any value, so the schema layer never rejects it and a bad value reaches the core op, which returns the normal `invalid_priority` result (a tool result with `status: error`, not a raw input-validation error)
- LLM tool-call layers may deliver a value as raw text
- No coercion: `true`, `1.0`, `"2"`, a list, a dict, and every string other than the exact lowercase text `null` (including `__UNSET__`) return `invalid_priority` and no file changes, on both tools and in a batch. The exact text `null` is treated as null (update clears, create stores none), mirroring CLI `--priority null`. `Null`, `NULL`, `"null"` with quotes, and padded forms are invalid

**CLI** (`create-ticket` and `update-ticket`):
- `--priority` takes an optional `-` followed by ASCII digits, or the word `null`; `-3` and `=-3` forms work
- Anything else (`1.5`, `true`, `abc`, `+3`, `1e3`, `1_000`, a leading space, an empty value) returns `invalid_priority` with exit 1 before any core logic runs

## Linter Architecture

The linter validates ticket structure and relationships through a two-phase scanning and validation process. Implementation spans `src/linter.py`, `src/linter_report.py`, and integrates with existing reader and ID utilities.

### Core Components

**LinterReport Module** (`src/linter_report.py`):
- `ValidationError` dataclass represents individual validation errors with fields: `ticket_id`, `error_type`, `message`, `severity`
- Severity levels: `error` (critical) or `warning` (non-critical)
- `LinterReport` class collects and queries validation errors
- Methods: `add_error()`, `get_errors()` with filtering, `is_corrupt()` for database health check, `add_fix()` to record an auto-fix, `withdraw_fixes()` to drop a ticket's fixes whose write failed
- Output formats: `to_json()`, `to_markdown()`, `to_dict()` for different consumers
- Summary statistics via `get_summary()` for error counts by type and severity

**Linter Module** (`src/linter.py`):
- `TicketScanner` class loads tickets from filesystem using `src/reader.py`
- Scans hive directories recursively (hierarchical storage: `{hive_name}/**/*.md`)
- Validates hierarchical pattern: directory name must match file stem (`{ticket_id}/{ticket_id}.md`)
- Skips hidden directories (`.hive/`), `evicted/`, `cemetery/`, `index.md` files, and any hive nested inside the hive (see [Nested Hives](#nested-hives))
- Leaves out tickets in a foreign subtree (see [Foreign Ticket Subtrees](#foreign-ticket-subtrees)): it reads every ticket file first, since whether a subtree is foreign depends on the tickets found in it and above it, and records the subtrees in `foreign_subtrees`
- Returns generator of `Ticket` objects with types validated against `~/.bees/config.json`
- Handles filesystem errors gracefully, logging and skipping invalid files
- `Linter` class orchestrates validation through `run()` method:
  - Loads all tickets via TicketScanner, remembering the file each was scanned from
  - Runs per-ticket validations
  - Runs cross-ticket validations (uniqueness, relationships)
  - Enforces directory structure (auto-moves misplaced tickets)
  - Detects empty ticket directories (removes them in auto-fix mode)
  - Warns once per foreign subtree the scan left out (`foreign_ticket_subtree`), last, so the warning names the subtree where it is after any move
  - Returns `LinterReport` with collected errors and fixes

### Validation Rules

**Schema Validation**:
- ID format validation: matches `{type_prefix}.{shortID}` pattern with length validation
  - Bee: `b.XXX` (3-char shortID)
  - Tier N: `t{N}.XXX.YY...` (shortID of 3 + 2N chars: the 3-char Bee shortID, then N 2-char segments, each after a period, e.g. `t1.qi9.de`, `t2.qi9.de.7z`)
  - Charset: 34 chars, lowercase only: 1-9, a-k, m-z
  - Excludes 0, l and all uppercase letters
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
  - GUID prefix must match the ticket's short_id (the ticket ID after its first dot, dots removed: `t1.qi9.de` gives `qi9de`)
  - Error: `missing_guid` - Ticket has no guid field (guid is None); in auto-fix mode a guid is generated instead (`add_guid`)
  - Error: `invalid_guid_length` - GUID length is not 32 characters
  - Error: `invalid_guid_charset` - GUID contains characters not in ID_CHARSET
  - Error: `invalid_guid_prefix` - GUID does not start with the ticket's short_id
  - The linter never replaces an existing guid: a guid with the wrong length, characters or prefix stays as it is, even in auto-fix mode, and must be fixed by hand
- GUID is immutable after ticket creation (enforced by `_update_ticket()`)

**Type/Value Validation**:

*Status Field Validator*:
- Type check: status must be a string (error: `invalid_field_type`)
- Value check: If status_values configured via three-level resolution (hive → scope → global), validates status is in the list (error: `invalid_status`). If not configured, any string is valid (freeform mode).

*Reference Materials Validator*:
- Only applies to bee tickets (child tiers skipped)
- Validates `reference_materials` is a list of dicts, each with a `value` key (error: `invalid_field_type`)
- Null/None `reference_materials` value is valid

*Priority Validator*:
- Applies to every tier; `priority` is optional, so a ticket without the key is valid
- When the key is present, the value must be an integer. A boolean is not an integer.
- A non-integer value (string, float, boolean, list, or an explicit null or empty value) generates one `invalid_field_type` error: "Field 'priority' must be integer, got <type>"
- Detect-only, no auto-fix: the linter never rewrites or removes a priority
- The model loads `priority` permissively (any stored value passes through, null or empty reads as unset), so the linter is where a bad value is caught

**Disallowed Fields Detection**:
- Scans raw YAML frontmatter for deprecated fields removed in schema cleanup (SR-6.3)
- Accesses raw frontmatter via `parse_frontmatter()` since Ticket model filters these fields
- Disallowed fields: `owner`, `description`, `created_by`, `updated_at`, `bees_version` (`priority` is a valid field, see Priority Validator)
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
- Dangling reference detection: Checks parent ID exists across all in-scope hives via `all_scope_ticket_map`. If the ID is absent from every hive, reports `dangling_parent` rather than `orphaned_ticket`. Skipped if any hive fails to load during map construction (see `hive_load_failure` below). An ID found only in a foreign subtree of any in-scope hive is reported the same way, with the subtree named in the message, and is never auto-cleared (see [Foreign Ticket Subtrees](#foreign-ticket-subtrees)).

*Children Field Validators*:
- ID format validation: Checks child IDs match ticket ID format (error: `invalid_child_id`)
- Type hierarchy validation: Verifies child ticket type matches expected tier (error: `invalid_child_type`)

*Removed/Renamed Errors*:
- `orphaned_parent` error no longer generated (per asymmetric policy)
- `orphaned_child` renamed to `orphaned_ticket` for clarity

*Dependency Field Validators*:
- ID format validation: Checks dependency IDs match ticket ID format (error: `invalid_dependency_id`)
- Same-type restriction: Dependencies must be between tickets of the same type — bees depend on bees, t1 on t1, etc. (error: `cross_type_dependency`)
- Dangling reference detection: Checks each dependency ID exists in any in-scope hive via `all_scope_ticket_map` cross-scope lookup (error: `dangling_dependency`). Only runs when the map builds successfully; skipped entirely if any hive fails to load (see `hive_load_failure` below). An ID found only in a foreign subtree of any in-scope hive is reported the same way, naming the subtree, and is never auto-cleared.

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
- **Parents first**: `_order_parents_first()` orders the tickets by how many ancestors each has through `parent` links, bees first, keeping scan order among equals; a parent cycle stops the count, so the run still ends. A child's expected directory is therefore computed from where its parent is after the parent's own move: a parent misplaced inside its child's directory (e.g. bee `b.abc` at `<hive>/t1.abc.aa/b.abc/`) moves out first, and the child follows in the same run
- **Auto-correction behavior**: Automatically moves misplaced ticket directories to correct location
- `_move_ticket_dir()` relocates the entire directory subtree (preserves all children) and never deletes anything:
  - Target missing: the ticket's directory is moved there whole
  - Target exists: `_merge_dir_into()` moves the entries of the ticket's directory into it, everything the target already holds stays, and the emptied ticket directory is removed (its empty parents stay). Each entry name is checked again just before that entry moves; if the name was taken in the target since the conflict check, the merge stops with an error and nothing is overwritten or nested (entries already moved stay moved, the rest stay where they were)
  - Target exists and holds the ticket's directory (a ticket misplaced inside its own expected directory, e.g. a bee at `<hive>/b.abc/misc/b.abc/`): the ticket's directory is first moved into a temporary directory `<ticket_id>.moving-XXXX` beside the target, so no entry is moved into itself, and its entries are then merged into the target. Afterwards, whether the merge succeeded or failed, `_remove_staging_leftovers()` removes the temporary directory and the directories left empty between the old location and the target, innermost first, using only `rmdir`: a directory that still holds anything stays, and on the way back up so does every directory above it. A failure to remove one is logged and never replaces the move's own error
- **Rationale for never deleting**: an existing target can hold the ticket itself (misplaced inside its own expected directory), other children, or unrelated files; deleting it before the move would lose them
- **Failed moves**: a move that fails partway (e.g. a name taken during the merge, or an `OSError` from the filesystem) is reported as error `directory_enforcement_failed` for that ticket, with no `move_directory` fix; nothing is lost, every file is in the target, the old directory or the temporary directory. The temporary directory is not hidden, so a ticket stranded there is found as misplaced: a stranded child ticket is usually moved later in the same run (it is checked after its parent), otherwise on the next run. A non-ticket file stranded in the old directory or in `<ticket_id>.moving-XXXX/` is not moved by any later run and stays until moved by hand; the error names the entry that failed to move. An empty `<ticket_id>.moving-XXXX/` can remain after a later run recovers the ticket from it
- Reports fixes via `LinterReport.add_fix()` with type `"move_directory"`
- Looks up each ticket's file, and its parent's, with `find_ticket_file()` without entering a foreign subtree, so a copy of the ticket inside one is never taken for it. A foreign subtree inside a moved ticket directory moves along with it, untouched (see [Foreign Ticket Subtrees](#foreign-ticket-subtrees))
- Never makes a move that crosses the boundary of a hive nested inside this one. Before each move, `_move_crosses_hive()` blocks it, through the shared `hive_crossing_reason()` (`src/paths.py`), when any of these holds (see [Nested Hives](#nested-hives)):
  - The ticket's current directory is inside another hive (`find_enclosing_hive_root()`)
  - The target directory itself is another hive's root or inside another hive (`find_enclosing_hive_root()`)
  - The ticket's current directory holds another hive anywhere below it, which the move would carry off its path (`find_nested_hive_root()`)
  - The target directory exists and holds another hive anywhere below it, so the ticket's directory would land in a directory holding that hive (`find_nested_hive_root()`)
- A blocked move is skipped, nothing is moved or deleted, and error `cross_hive_move_blocked` is reported naming the reason
- A move that passes the hive guard is then checked by `_find_move_conflict()`, which refuses it when any of these holds:
  - The target lies inside the ticket's own directory (a directory cannot be moved into itself)
  - The target exists but is a symlink or not a directory
  - An entry of the ticket's directory has the same name as an entry the target keeps (the ticket's own directory sitting directly in the target does not count, since it leaves before its entries arrive)
- A refused move touches nothing, and error `move_target_conflict` is reported naming the reason; it stays until the conflict is fixed by hand. A child whose parent sits misplaced inside the child's own directory is not such a conflict: the parent moves out first (see Parents first)
- Triggered on every linter run (manual `sanitize_hive`, and the watcher loop when `start_watcher()` is running)

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

*Bee misplaced inside its own expected directory*:
- Frontmatter: `parent: null`
- Current location: `hive_root/b.abc/misc/b.abc/`
- Expected location: `hive_root/b.abc/`
- Action: Linter moves `misc/b.abc/` out into a temporary directory beside `b.abc/`, merges its entries into `b.abc/`, then removes the temporary directory, and `misc/` if left empty; nothing else in `b.abc/` is touched

**Empty Ticket Directory Cleanup**:
- `detect_empty_ticket_dirs()` finds ticket-ID directories with no `{ticket_id}.md` inside, left behind when ticket creation claims a directory but the write fails; such a directory blocks that ID from reuse
- Skips directories modified in the last 10 minutes, to avoid racing in-flight ticket creation
- In auto-fix mode removes each one (fix type `"remove_empty_dir"`); otherwise reports error `empty_ticket_dir`
- Runs on every linter run, including detect-only runs
- Walks the hive with `walk_hive()`, so directories of a nested hive are never checked or removed, and skips foreign subtrees through its `skip_dirs`, so their directories are neither reported nor removed

### Nested Hives

A hive may sit inside another hive's directory, e.g. hive `plans` at `Ideas/Plans/` inside hive `ideas` at `Ideas/`. The nested hive's tickets belong to it alone: linting the enclosing hive never scans, fixes, moves or removes anything in the nested hive's directory.

- **Boundary**: a directory below the hive root starts another hive when it holds its own `.hive/` directory or is the root of a hive registered in any scope (see [storage.md](storage.md#nested-hives))
- **Pruned walks**: TicketScanner, `find_ticket_file()`, directory enforcement and empty-directory cleanup all walk through `walk_hive()`, which stops at that boundary. The nested hive's tickets get no `unknown_tier`, `invalid_tier_parent` or other errors from the enclosing hive's config, and no fixes
- **Move guard**: if a planned directory move would cross the boundary, carry a nested hive along with the ticket's directory, or go into an existing target directory that holds one, directory enforcement skips it and reports `cross_hive_move_blocked` (see Directory Structure Enforcement)
- **Cross-hive references**: `sanitize_hive` builds `all_scope_ticket_map` by scanning each in-scope hive on its own, so the tickets of a nested hive registered in scope resolve like any other hive's. The tickets of a nested hive that is not registered in scope (e.g. one marked only by `.hive/`) are not in the map: a reference to one of them from the enclosing hive is reported as dangling, and is removed when `auto_fix_dangling_refs: true`
- **Rationale**: the nested hive has its own tiers, status values and layout. Linting its tickets against the enclosing hive's config would flag tiers the enclosing hive does not define as `unknown_tier`, and directory enforcement would move the nested hive's bees to the enclosing hive's root, out of their own hive

### Foreign Ticket Subtrees

A ticket's folder can hold arbitrary content, e.g. a test fixture with a copy of another hive's tickets, at `b.abc/fixtures/tickets/` inside bug `b.abc`. Unlike a nested hive it need not have a `.hive/` marker. The linter treats such a tree as foreign: it never scans, fixes, moves or removes anything in it.

- **Rule** (`find_foreign_subtrees()` in `src/paths.py`): the decision is made per directory, outermost first, from the ticket files below the hive root. Only `{dir}/{dir}.md` files whose stem is a ticket ID count; any other such file (e.g. `b.abc/design/design.md`) never makes a foreign subtree
  - A *candidate* X is a directory that is not a ticket ID and has a ticket-ID directory among its ancestors below the hive root
  - The *top tickets* of X are the ticket files under X with no other ticket file's directory between X and them
  - A top ticket is *vouched for* when (a) it is the same ticket as, an ancestor of, or a descendant of a ticket-ID directory above X, or its own frontmatter `parent` has a settled file whose `children` lists it, and (b) no copy of its ID sits at a settled location outside X. The relation in (a) is found through the ticket's own frontmatter `parent`, then the frontmatter chain above it (a parent missing from the hive ends the chain), plus the lineage the ID itself spells (`t2.abc.de.fg` is a child of `t1.abc.de`, whose parent is `b.abc`). The parent that lists it need not be above X. A settled location is a path with no candidate directory in it, so copies inside other fixtures or other misplacements do not count and the verdict does not depend on the order candidates are examined in
  - X is foreign when it has at least one top ticket and either none is vouched for, or any top ticket has a copy of its ID at a settled location outside X (a real misplaced ticket never has a settled duplicate, so the copy marks X as a fixture even when its other tickets look related). It is then the subtree's root, and nothing under it is examined further. Otherwise the candidates below X are examined; a directory mixing vouched and unvouched tickets, none with a settled duplicate, is not foreign
- **Root and owner**: the subtree's root is the directory X; its owner is the nearest ticket-ID directory above X. The subtree's ticket IDs are the stems of every ticket file under the root
- **Not foreign**: a ticket misplaced in a way the linter fixes is still moved: a bee at `<hive>/wrong/b.abc/` (no ticket-ID directory above), a child under the wrong parent, a ticket in a child's directory (`t1.abc.de/misc/b.abc/`), or in a directory under its own ID's (`b.abc/misc/b.abc/`), including the `<id>.moving-XXXX` directory a failed move leaves. A mixed directory is not foreign either: its vouched tickets and its unvouched ones are the linter's to move
- **Limit**: a hive ticket misplaced under a plain folder of an unrelated ticket (e.g. `t1.par.aa` at `b.other/misc/t1.par.aa/`) is indistinguishable from a fixture unless its parent lists it as a child. If it does, it is vouched for and moved home; if nobody claims it, it counts as foreign: it is skipped, not moved, and references to it are reported as dangling and not cleared
- **Skipped**: the scan leaves out the subtree's tickets: they are not validated, rewritten or moved, their load failures are not logged, and they are not in `sanitize_hive`'s cross-hive ticket map. Empty-directory cleanup and the linter's file lookups never enter the subtree, so a copy of a hive ticket's ID inside it is never mistaken for the ticket
- **References**: a parent, up or down dependency reference to an ID found only in a foreign subtree is reported as `dangling_parent` or `dangling_dependency`, with the message "found only in foreign subtree '<root>'". The foreign subtrees of every hive in scope count, not just this hive's: `sanitize_hive` collects them while building the cross-hive map and passes them to the `Linter` as `foreign_ticket_roots`. It is never auto-cleared, even with `auto_fix_dangling_refs: true`, since the ticket may be one the hive lost track of. A reference to an ID found nowhere is cleared as usual
- **Warning**: one `foreign_ticket_subtree` warning per subtree root, in detect-only, auto-fix and report-only runs alike, with the owner's ID as `ticket_id`. The message names the directory and its owner, the number of ticket files the linter treats as foreign to this hive (not claimed by the owner or its lineage), and up to five of their IDs, then how many more, and says they are skipped and left untouched. Warnings do not mark the report corrupt. They are emitted at the end of `Linter.run()`, after directory enforcement, so they name the root where it is now
- **Moves with its owner**: when a directory holding a subtree is moved, the subtree goes along untouched. The linter follows each root through the move, also when the move fails partway, keeping the old, `<id>.moving-XXXX` and new spellings of its path out of every search and cleanup
- **Nested hives**: a fixture with its own `.hive/` is pruned earlier, as a nested hive, and gets no `foreign_ticket_subtree` warning; this rule covers the ones without a marker
- **Not covered**: the undertaker's archive rename pass (phase 2) walks an archived bee's folder without knowing foreign subtrees, so it renames fixture tickets inside it

### Algorithm Choices

**DFS with Path Tracking**: Selected for cycle detection to achieve O(V+E) time complexity while naturally maintaining the path from root to current node. DFS is proven correct for detecting cycles in directed graphs.

**Dual Representation for Path Tracking**: Uses both a list (ordered cycle extraction) and a set (O(1) cycle detection) to balance human-readable error reporting with performance. Global visited set prevents redundant traversals across disconnected components.

**Separate Passes by Relationship Type**: Runs independent DFS traversals for blocking dependencies versus hierarchical relationships, enabling targeted error messages and preventing false positives from mixing relationship semantics.

### Integration Points

- Uses `src/reader.py` to load tickets with schema validation
- Uses `Ticket` model from `src/models.py` with dynamic type validation against `~/.bees/config.json`
- Reader's validator catches schema violations during load; linter focuses on cross-ticket validation

## Watcher-Linter Integration Pipeline

While running, the watcher automatically triggers linter validation and index regeneration when ticket files change, maintaining data integrity through a debounced pipeline. Implementation in `src/watcher.py`. Nothing in the CLI or MCP server starts it (see Watcher Lifecycle below).

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
- Accepts `hive` parameter to target specific hive
- Runs linter with `auto_fix=True` on specified hive only, not on hives nested inside its directory
- Returns structured report with fixes applied and remaining errors
- Does not trigger watcher pipeline (synchronous operation)

### Watcher Lifecycle

**Start watcher** (`start_watcher()` in `src/watcher.py`):
- Not wired into the CLI or MCP server: no `bees` subcommand or flag calls `start_watcher()`, and neither `bees serve --stdio` nor `bees serve --http` starts it. Run `sanitize_hive` and `generate_index` to lint and re-index.
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
- Automatically moves misplaced ticket directories to correct location, parents before their children
- Relocates entire directory subtrees (preserves all children) and never deletes anything: an existing target directory is merged into, and a move that would overwrite an entry of the target or nest the target inside the ticket's own directory is refused (`move_target_conflict`); a move that fails partway is reported as `directory_enforcement_failed` (see Directory Structure Enforcement under [Validation Rules](#validation-rules))
- Never moves a ticket into or out of a nested hive, carries one along, or moves it into an existing target directory that holds one (`cross_hive_move_blocked`, see [Nested Hives](#nested-hives))
- Triggered by manual `sanitize_hive` calls and any direct linter invocation
- Reported as fixes in `LinterReport` (type: `"move_directory"`)

**2. Bidirectional Field Repair** (when `auto_fix=True`):
- Implemented via `validate_parent_children_bidirectional()` and `validate_dependencies_bidirectional()` methods
- Repairs the child→parent direction of parent↔children relationships (the parent→child direction is not enforced, per the asymmetric policy above):
  - If child lists parent but parent doesn't list child in children array, adds child to parent's children
- Repairs up_dependencies↔down_dependencies relationship inconsistencies:
  - If ticket A lists B in up_dependencies but B doesn't list A in down_dependencies, adds A to B's down_dependencies
  - If ticket A lists B in down_dependencies but B doesn't list A in up_dependencies, adds A to B's up_dependencies
- Modified tickets are written back to filesystem via `_save_modified_tickets()`
- Reported as fixes in `LinterReport` (types: `"add_child"`, `"add_down_dependency"`, `"add_up_dependency"`)

**3. Dangling Reference Removal** (when `auto_fix_dangling_refs: true` in global config):
- Controlled by `auto_fix_dangling_refs` global config flag — separate from `auto_fix`; dangling ref removal is not triggered by `auto_fix=True` alone
- Requires a successfully built `all_scope_ticket_map` (skipped if `hive_load_failure` occurs)
- Removes dangling dependency IDs: deletes the offending ID from `up_dependencies` or `down_dependencies` and writes the ticket to disk (fix type: `"remove_dangling_dependency"`)
- Clears dangling parent refs: sets the `parent` field to `null` and writes the ticket to disk (fix type: `"clear_dangling_parent"`)
- Leaves a reference to an ID found only in a foreign subtree alone: it is reported, not cleared (see [Foreign Ticket Subtrees](#foreign-ticket-subtrees))
- Reported as fixes in `LinterReport` with the respective fix types above

**Fixes Are Listed Only Once Written**:
- Applies to every auto-fix that rewrites a ticket file: `add_child`, `add_down_dependency`, `add_up_dependency`, `remove_dangling_dependency`, `clear_dangling_parent`, and `add_guid` (GUID generation for a ticket with none)
- The fix is recorded in the report first, then `_save_modified_tickets()` writes the ticket to the file it was scanned from, not to the path computed from its ID. A fix to a misplaced ticket therefore lands in its only copy, which directory enforcement then moves
- If a ticket's write fails, the fixes recorded for it by the pass awaiting that write are withdrawn from the report (`LinterReport.withdraw_fixes()`) and each is reported as error `fix_not_applied`, naming the fix and the write error
- A ticket whose write failed is not written again in the same linter run: its unwritten fixes are still on the in-memory ticket, so a later write would put them on disk. Later passes' fixes to it are withdrawn and reported as `fix_not_applied` too, with the reason that an earlier write of the ticket failed in this run. The set of such tickets (`_unwritten_ids`) is reset at the start of each run
- `fixes_applied` in the `sanitize_hive` response therefore lists only fixes that are on disk

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

**validate_id_format() Function** (`src/validator.py`):
- Validates ticket ID format and length by delegating to `is_valid_ticket_id()` in `src/id_utils.py` (see [Schema Validation](#validation-rules) for the format)
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
- Signature: `generate_index(hive_name=None) -> str` (no status or type filters)
- With `hive_name` provided: generates index only for specified hive, writes to `{hive_path}/index.md`
- With `hive_name` omitted: iterates all registered hives from `~/.bees/config.json`, generates separate index.md for each
- Returns markdown content as string
- Requires at least one configured hive

**scan_tickets()** (`src/index_generator.py`):
- Uses `list_tickets()` from `paths.py` which scans hive directories recursively
- Validates `bees_version` field presence and filters by YAML `type` field
- Validates hierarchical pattern: directory name matches file stem
- Excludes `/evicted`, `.hive` and any hive nested inside the hive automatically
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

The `generate_index` MCP tool accepts an optional `hive` parameter, enabling per-hive or all-hive index regeneration via the MCP protocol.

### Use Cases

- Regenerate index for specific hive: `generate_index(hive="backend")`
- Regenerate all hive indexes: `generate_index()`

## Corruption Detection

Corruption detection identifies database integrity issues through linter validation and generates structured reports for troubleshooting and recovery.

### Error Categories

**Critical Errors** (mark database as corrupt):
- Malformed ticket IDs not matching type-prefixed pattern (`b.XXX`, `t1.XXXX`, etc.)
- Duplicate ticket IDs across system (IDs are globally unique)
- Bidirectional relationship inconsistencies (parent/children, dependencies)
- Circular dependencies in blocking relationships or hierarchical structure
- Misplaced ticket directories not matching parent relationships
- Directory moves blocked at a nested hive's boundary (`cross_hive_move_blocked`)
- Directory moves refused because the target conflicts with the ticket's directory (`move_target_conflict`)
- Directory moves that failed partway (`directory_enforcement_failed`)
- Auto-fixes whose ticket write failed (`fix_not_applied`)

**Warnings** (non-critical):
- Missing optional fields
- Style guideline violations
- Deprecated field usage
- Ticket trees in a ticket's folder skipped as foreign (`foreign_ticket_subtree`)

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
- Directory move conflicts (`move_target_conflict`: requires choosing which of two same-named entries to keep, or where the ticket's directory belongs)

### Database Integrity Guarantees

**sanitize_hive Tool** (`src/mcp_server.py`):
- Runs linter on specified hive with comprehensive validations
- Validates ticket IDs match type-prefixed format
- Enforces directory structure (auto-moves misplaced tickets)
- Validates bidirectional relationships (parent/children, dependencies)
- Attempts automatic fixes where possible
- Leaves any hive nested inside the hive's directory untouched
- Returns structured report with fixes applied (only those written to disk) and remaining errors

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
