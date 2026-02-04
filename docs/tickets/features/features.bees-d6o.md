---
id: features.bees-d6o
type: epic
title: Refactor mcp_server.py into modular components
description: '## Problem


  mcp_server.py is 3,222 lines long (~34k tokens) and cannot be loaded into LLM context
  windows. This makes it difficult to:

  - Understand the codebase

  - Make changes safely

  - Debug issues

  - Maintain code quality

  - Get AI assistance on the code


  ## Goal


  Break down mcp_server.py into logical, focused modules following best practices:

  - Each module should be < 500-800 lines (easily fits in LLM context)

  - Single responsibility principle

  - Clear separation of concerns

  - Maintain all existing functionality

  - Keep imports clean and avoid circular dependencies


  ## Proposed Module Structure


  ### 1. mcp_id_utils.py (~50-100 lines)

  Ticket ID parsing utilities:

  - `parse_ticket_id()` - Parse ticket ID to extract hive name and base ID

  - `parse_hive_from_ticket_id()` - Extract hive prefix from ticket ID


  ### 2. mcp_repo_utils.py (~150-200 lines)

  Repository root detection:

  - `get_repo_root_from_path()` - Find git repo root from a path

  - `get_client_repo_root()` - Get repo root from MCP context using roots protocol

  - `get_repo_root()` - Main wrapper with fallback logic


  ### 3. mcp_hive_utils.py (~200-250 lines)

  Hive path validation and discovery:

  - `validate_hive_path()` - Validate hive path is absolute, exists, within repo

  - `scan_for_hive()` - Scan filesystem for hive by .hive/identity.json marker


  ### 4. mcp_relationships.py (~400-500 lines)

  Bidirectional relationship synchronization (9 functions):

  - `_update_bidirectional_relationships()` - Main sync coordinator

  - `_remove_child_from_parent()` / `_add_child_to_parent()`

  - `_remove_parent_from_child()` / `_set_parent_on_child()`

  - `_remove_from_down_dependencies()` / `_add_to_down_dependencies()`

  - `_remove_from_up_dependencies()` / `_add_to_up_dependencies()`


  ### 5. mcp_ticket_ops.py (~700-800 lines)

  Ticket CRUD operations:

  - `_create_ticket()` - Create epic/task/subtask with validation

  - `_update_ticket()` - Update ticket with relationship sync

  - `_delete_ticket()` - Delete with cascade and cleanup

  - `_show_ticket()` - Retrieve and display ticket data


  ### 6. mcp_hive_ops.py (~700-800 lines)

  Hive lifecycle operations:

  - `colonize_hive_core()` - Core hive creation logic

  - `_colonize_hive()` - MCP tool wrapper

  - `_list_hives()` - List all registered hives

  - `_abandon_hive()` - Stop tracking hive without deleting files

  - `_rename_hive()` - Rename hive and update all ticket IDs

  - `_sanitize_hive()` - Run linter to validate and fix issues


  ### 7. mcp_query_ops.py (~300-400 lines)

  Query operations:

  - `_add_named_query()` - Register and save named query

  - `_execute_query()` - Execute named query with hive filtering

  - `_execute_freeform_query()` - Execute ad-hoc YAML query


  ### 8. mcp_index_ops.py (~100-150 lines)

  Index generation:

  - `_generate_index()` - Generate markdown index with filtering


  ### 9. mcp_help.py (~200-300 lines)

  Help documentation:

  - `_help()` - Generate comprehensive help for MCP tools


  ### 10. mcp_server.py (slimmed to ~300-500 lines)

  Server initialization and tool registration only:

  - FastMCP initialization

  - Logging setup

  - Server lifecycle: `start_server()`, `stop_server()`, `_health_check()`

  - All `@mcp.tool()` decorators as thin wrappers calling extracted functions


  ## Implementation Strategy


  **Phase 1: Extract utilities (parallel)**

  - Extract ID utils, repo utils, hive utils (independent modules)


  **Phase 2: Extract operations (parallel)**

  - Extract relationships, ticket ops, hive ops, query ops, index ops, help

  - These depend on Phase 1 modules but are independent of each other


  **Phase 3: Final refactoring (sequential)**

  - Update mcp_server.py to import and use all extracted modules

  - Remove extracted function implementations

  - Keep only server setup and tool registration


  **Phase 4: Verification**

  - Run full test suite

  - Verify all tests pass

  - Check no circular imports

  - Confirm each module < 800 lines


  ## Success Criteria


  - ✅ All existing tests pass

  - ✅ Each new module is < 800 lines

  - ✅ mcp_server.py reduced to ~300-500 lines

  - ✅ No functionality lost

  - ✅ No circular dependencies

  - ✅ Code is maintainable and LLM-friendly'
children:
- features.bees-pt9
- features.bees-alr
- features.bees-wvm
- features.bees-t9t
- features.bees-jzd
- features.bees-2hp
- features.bees-txe
- features.bees-zy7
- features.bees-jlu
- features.bees-4u5
- features.bees-dkp
- features.bees-tho
- features.bees-w4v
- features.bees-yss
created_at: '2026-02-03T16:58:33.622973'
updated_at: '2026-02-03T19:07:13.560290'
priority: 2
status: open
bees_version: '1.1'
---

## Problem

mcp_server.py is 3,222 lines long (~34k tokens) and cannot be loaded into LLM context windows. This makes it difficult to:
- Understand the codebase
- Make changes safely
- Debug issues
- Maintain code quality
- Get AI assistance on the code

## Goal

Break down mcp_server.py into logical, focused modules following best practices:
- Each module should be < 500-800 lines (easily fits in LLM context)
- Single responsibility principle
- Clear separation of concerns
- Maintain all existing functionality
- Keep imports clean and avoid circular dependencies

## Proposed Module Structure

### 1. mcp_id_utils.py (~50-100 lines)
Ticket ID parsing utilities:
- `parse_ticket_id()` - Parse ticket ID to extract hive name and base ID
- `parse_hive_from_ticket_id()` - Extract hive prefix from ticket ID

### 2. mcp_repo_utils.py (~150-200 lines)
Repository root detection:
- `get_repo_root_from_path()` - Find git repo root from a path
- `get_client_repo_root()` - Get repo root from MCP context using roots protocol
- `get_repo_root()` - Main wrapper with fallback logic

### 3. mcp_hive_utils.py (~200-250 lines)
Hive path validation and discovery:
- `validate_hive_path()` - Validate hive path is absolute, exists, within repo
- `scan_for_hive()` - Scan filesystem for hive by .hive/identity.json marker

### 4. mcp_relationships.py (~400-500 lines)
Bidirectional relationship synchronization (9 functions):
- `_update_bidirectional_relationships()` - Main sync coordinator
- `_remove_child_from_parent()` / `_add_child_to_parent()`
- `_remove_parent_from_child()` / `_set_parent_on_child()`
- `_remove_from_down_dependencies()` / `_add_to_down_dependencies()`
- `_remove_from_up_dependencies()` / `_add_to_up_dependencies()`

### 5. mcp_ticket_ops.py (~700-800 lines)
Ticket CRUD operations:
- `_create_ticket()` - Create epic/task/subtask with validation
- `_update_ticket()` - Update ticket with relationship sync
- `_delete_ticket()` - Delete with cascade and cleanup
- `_show_ticket()` - Retrieve and display ticket data

### 6. mcp_hive_ops.py (~700-800 lines)
Hive lifecycle operations:
- `colonize_hive_core()` - Core hive creation logic
- `_colonize_hive()` - MCP tool wrapper
- `_list_hives()` - List all registered hives
- `_abandon_hive()` - Stop tracking hive without deleting files
- `_rename_hive()` - Rename hive and update all ticket IDs
- `_sanitize_hive()` - Run linter to validate and fix issues

### 7. mcp_query_ops.py (~300-400 lines)
Query operations:
- `_add_named_query()` - Register and save named query
- `_execute_query()` - Execute named query with hive filtering
- `_execute_freeform_query()` - Execute ad-hoc YAML query

### 8. mcp_index_ops.py (~100-150 lines)
Index generation:
- `_generate_index()` - Generate markdown index with filtering

### 9. mcp_help.py (~200-300 lines)
Help documentation:
- `_help()` - Generate comprehensive help for MCP tools

### 10. mcp_server.py (slimmed to ~300-500 lines)
Server initialization and tool registration only:
- FastMCP initialization
- Logging setup
- Server lifecycle: `start_server()`, `stop_server()`, `_health_check()`
- All `@mcp.tool()` decorators as thin wrappers calling extracted functions

## Implementation Strategy

**Phase 1: Extract utilities (parallel)**
- Extract ID utils, repo utils, hive utils (independent modules)

**Phase 2: Extract operations (parallel)**
- Extract relationships, ticket ops, hive ops, query ops, index ops, help
- These depend on Phase 1 modules but are independent of each other

**Phase 3: Final refactoring (sequential)**
- Update mcp_server.py to import and use all extracted modules
- Remove extracted function implementations
- Keep only server setup and tool registration

**Phase 4: Verification**
- Run full test suite
- Verify all tests pass
- Check no circular imports
- Confirm each module < 800 lines

## Success Criteria

- ✅ All existing tests pass
- ✅ Each new module is < 800 lines
- ✅ mcp_server.py reduced to ~300-500 lines
- ✅ No functionality lost
- ✅ No circular dependencies
- ✅ Code is maintainable and LLM-friendly
