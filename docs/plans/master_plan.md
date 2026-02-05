# Bees Master Plan

## System Overview

Bees is a markdown-based ticket management system designed for simplicity and human readability. All tickets are stored as markdown files with YAML frontmatter, organized into hives (isolated directories), and managed through an MCP server interface.

The system operates without databases, daemons, or caches, making it lightweight and easy to understand. Design constraints include: no external dependencies for storage, no background processes, and a practical limit of tens of directories and thousands of tickets. This constraint-driven architecture enables git-based workflows and direct file editing while maintaining referential integrity through bidirectional relationship synchronization.

Core capabilities include multi-stage query pipelines for filtering and traversing ticket relationships, hive-based namespacing for multi-team repositories, and automatic index generation for navigation. The architecture prioritizes explicit operations, fail-fast validation, and clear error messages over automatic recovery.

## Architecture Documentation

Detailed technical documentation is organized into focused architecture documents:

- [**Design Principles**](../architecture/design_principles.md) - Core design philosophy and constraints
- [**Configuration**](../architecture/configuration.md) - Config system, hive registry, and normalization
- [**Storage**](../architecture/storage.md) - Hive structure, flat storage, and schema versioning
- [**Relationships**](../architecture/relationships.md) - Bidirectional sync and dependency management
- [**Queries**](../architecture/queries.md) - Multi-stage pipeline and query execution
- [**MCP Server**](../architecture/mcp_server.md) - HTTP transport and tool interfaces
- [**Validation**](../architecture/validation.md) - Linter architecture and corruption detection
- [**Testing**](../architecture/testing.md) - Test organization and coverage strategy

## Module Organization

The codebase follows a modular architecture where mcp_server.py acts as a thin orchestration layer that registers MCP tools and delegates to specialized modules. This design emerged from Epic features.bees-d6o which systematically extracted functionality from a monolithic 3,222-line mcp_server.py into 9 focused modules.

### Modularization Strategy

**Design Goal:** Keep each module under 1000 lines to fit comfortably in LLM context windows, enabling better code comprehension and maintenance.

**Orchestration Pattern:** mcp_server.py is now a ~200-line file that:
- Initializes the FastMCP server
- Sets up logging configuration
- Provides lifecycle functions (start_server, stop_server, health_check)
- Registers all MCP tools as 1-2 line wrappers that delegate to extracted modules
- Contains no business logic or implementation details

**Import Structure:** Modules are organized to avoid circular dependencies:
- Utility modules (mcp_id_utils, mcp_repo_utils, mcp_hive_utils) have no internal dependencies
- Relationship module (mcp_relationships) depends only on core modules (paths, reader, writer)
- Operation modules (mcp_ticket_ops, mcp_hive_ops, mcp_query_ops) depend on utilities and relationships
- Server orchestration (mcp_server.py) imports all modules but is imported by none

**Core Infrastructure Modules:**
- **mcp_server.py** - FastMCP server registration and orchestration (~200 lines, reduced from 3,222)
- **mcp_relationships.py** - Bidirectional relationship synchronization (~400-500 lines)
- **mcp_ticket_ops.py** - Ticket CRUD operations (create, update, delete, show) (~800 lines)
- **mcp_hive_ops.py** - Hive lifecycle operations (colonize, list, abandon, rename, sanitize) (~1000 lines)
- **mcp_query_ops.py** - Query operations (add named query, execute named/freeform queries) (~250 lines)
- **mcp_index_ops.py** - Index generation operations with filtering (~64 lines)
- **mcp_help.py** - Help system documentation and MCP tool reference (~230 lines)

**Utility Modules:**
- **mcp_hive_utils.py** - Hive path validation and scanning utilities
- **mcp_repo_utils.py** - Repository root detection
- **mcp_id_utils.py** - Ticket ID parsing utilities

**Query Subsystem (mcp_query_ops.py):**
Extracted from mcp_server.py as part of Epic features.bees-d6o to improve modularity and maintainability. The module provides:
- Named query registration with validation (`_add_named_query`)
- Named query execution with hive filtering (`_execute_query`)
- Ad-hoc freeform query execution without persistence (`_execute_freeform_query`)

Dependencies:
- **query_storage** - Query persistence to disk
- **pipeline** - PipelineEvaluator for query execution
- **mcp_repo_utils** - Repository root detection for hive resolution
- **config** - Hive configuration loading and validation

Integration: Functions are imported by mcp_server.py and registered as MCP tools for external access. The extraction maintains identical functionality while isolating the query subsystem for better code organization.

**Index Generation Subsystem (mcp_index_ops.py):**
Extracted from mcp_server.py as part of Epic features.bees-d6o (Task features.bees-zy7) to follow single responsibility principle. The module provides:
- Markdown index generation with filtering (`_generate_index`)
- Support for status, type, and hive_name filters
- Per-hive and all-hive index generation capabilities

Dependencies:
- **index_generator** - Core index generation logic

Integration: The `_generate_index` function is imported by mcp_server.py and registered as an MCP tool. This extraction isolates index generation as a discrete operation for better maintainability.

**Help Documentation Subsystem (mcp_help.py):**
Extracted from mcp_server.py as part of Epic features.bees-d6o (Task features.bees-jlu) to isolate help documentation for easier maintenance. The help system is ~230 lines of documentation that was bloating mcp_server.py, making it harder to navigate and maintain. The module provides:
- Comprehensive documentation for all available MCP tools (`_help`)
- Command details with parameters and descriptions
- Technical reference for core concepts (HIVES, TICKET TYPES, RELATIONSHIPS, DEPENDENCIES, QUERIES)

Dependencies:
- **typing** - Type hints for Dict and Any

Integration: The `_help` function is imported by mcp_server.py and registered as an MCP tool. This extraction isolates help documentation as a discrete module, making both mcp_server.py more focused on coordination and help documentation easier to maintain as new features are added.

**Organization:**
- **mcp_hive_utils.py** handles validation/scanning
- **mcp_hive_ops.py** handles lifecycle (create, rename, delete)

## Test Infrastructure

### Pytest Fixtures Architecture

Bees uses a tiered fixture design pattern in `tests/conftest.py` that supports test isolation while avoiding code duplication. The fixture hierarchy enables tests to request the appropriate level of setup complexity for their needs.

**Design Philosophy:**
- **Function scope** - All fixtures use `scope="function"` for complete test isolation and parallelization
- **Composition** - Fixtures build on each other to create increasingly complex scenarios
- **Explicit cleanup** - Uses pytest's tmp_path for automatic cleanup, no manual teardown needed
- **Realistic structure** - Higher-tier fixtures use actual create_ticket() functions to ensure valid ticket relationships

**Fixture Hierarchy:**

1. **bees_repo** (base)
   - Creates temporary directory with `.bees/` subdirectory
   - Yields repo root Path object
   - Foundation for all other fixtures

2. **single_hive** (builds on bees_repo)
   - Creates 'backend' hive with `.hive/identity.json` marker
   - Registers hive in `.bees/config.json`
   - Yields `(repo_root, hive_path)`
   - Use for: Single-hive operations, basic ticket CRUD tests

3. **multi_hive** (builds on bees_repo)
   - Creates 'backend' and 'frontend' hives with identity markers
   - Registers both hives in config
   - Yields `(repo_root, backend_path, frontend_path)`
   - Use for: Cross-hive queries, multi-hive operations, dependency validation

4. **hive_with_tickets** (builds on single_hive)
   - Pre-creates epic → task → subtask hierarchy using raw ticket_factory functions
   - Yields `(repo_root, hive_path, epic_id, task_id, subtask_id)`
   - Use for: Relationship testing, query operations on existing tickets, update/delete operations
   - **Architectural Decision:** Fixture uses raw `create_epic()`, `create_task()`, `create_subtask()` functions that only set parent fields (child→parent direction) without syncing children arrays (parent→child direction). This minimal approach keeps fixture setup simple while allowing tests to verify the full bidirectional sync behavior of MCP functions.

**Integration with Test Suite:**
- Fixtures are automatically available to all tests via conftest.py
- Tests request only the complexity level they need via fixture parameters
- Function scope ensures no state pollution between tests
- Integration with existing `repo_root_context` ensures proper context handling

**Example Usage:**
```python
def test_simple_config(bees_repo):
    # Only needs basic repo structure
    repo_root = bees_repo
    config_path = repo_root / ".bees" / "config.json"
    assert config_path.parent.exists()

def test_ticket_creation(single_hive):
    # Needs configured hive but no existing tickets
    repo_root, hive_path = single_hive
    create_epic(title="New Epic", hive_name="backend")

def test_query_relationships(hive_with_tickets):
    # Needs existing ticket hierarchy
    repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
    # Test queries against pre-created tickets
```

### Centralized Fixture Migration

**Architectural Decision (Epic features.bees-74p):** All test files now use shared fixtures from `conftest.py` instead of local fixture definitions. This eliminates 500+ lines of duplicate fixture code across test files and ensures consistent test isolation patterns.

**Migration Approach:**
- Local fixtures in individual test files were replaced with appropriate shared fixtures (`single_hive`, `multi_hive`, `isolated_bees_env`)
- Tests requiring complex multi-hive setups now use `isolated_bees_env` helper with its `create_hive()` and `write_config()` methods
- Tests needing simple single-hive setups use `single_hive` fixture
- Tests requiring backend + frontend hives use `multi_hive` fixture

**Files Migrated:**
- `test_paths.py` - Migrated from local `setup_hive_config` to `multi_hive` fixture
- `test_ticket_factory_hive.py` - Migrated from local `temp_hive_config` to `single_hive`, `multi_hive`, and `isolated_bees_env` fixtures
- `test_pipeline.py` - Migrated from local `temp_tickets_dir` to `isolated_bees_env` fixture with helper methods
- `test_generate_demo_tickets.py` - Migrated from local `setup_tickets_dir` to `isolated_bees_env` fixture

**Benefits:**
- Reduced code duplication from 500+ lines to zero
- Consistent test isolation patterns across all test files
- Easier maintenance of fixture logic in one central location
- Improved discoverability of available test fixtures

### Test Suite Organization

The test suite follows a module-based organization principle where tests are located alongside the modules they test:

- **test_reader.py** - Tests for reader, parser, and validator modules
- **test_writer_factory.py** - Tests for ticket_factory functions and frontmatter serialization
- **test_relationships.py** - Tests for bidirectional relationship synchronization
- **test_query_pipeline.py** - Tests for query execution and multi-stage filtering

#### Test Cleanup History

As part of the "Remove Legacy Skipped Tests" epic (features.bees-5va), test organization was cleaned up:

1. **Task 1 (features.bees-nkt)**: Migrated unique test coverage from `test_writer.py` to appropriate test files:
   - Moved `TestSerializeFrontmatter` → `test_writer_factory.py` (frontmatter serialization tests)
   - Moved `TestWriteTicketFile` validations → `test_reader.py` (ticket ID format validation tests)
   - All unique coverage preserved, ensuring no regression in test coverage

2. **Task 2 (features.bees-uwi)**: Removed `test_writer.py` after verifying all unique coverage was migrated
   - File was entirely skipped with no active tests
   - Deletion verified through full test suite pass with unchanged coverage metrics
   - Removed dead code that could confuse developers

**Rationale**: Skipped test files create maintenance debt and confusion. By migrating unique coverage to active test files before deletion, we maintained test quality while removing dead code. The consolidated test organization makes it clearer where to find tests for specific functionality.

3. **Task 3 (features.bees-uxl)**: Removed duplicate port validation tests from TestLoadConfig class
   - Deleted 3 integration-level tests: `test_load_config_with_invalid_port_number`, `test_load_config_with_negative_port`, `test_load_config_with_string_port`
   - These tests duplicated coverage already provided by unit-level TestPortValidation class
   - Removed ~39 lines of redundant test code
   - TestLoadConfig is designed for integration-level testing (file loading, YAML parsing), not unit-level port validation

**Rationale**: TestLoadConfig tests were redundant with TestPortValidation which provides comprehensive unit-level coverage for port validation logic. The deleted tests added no unique value since they tested the same Config port validation through a different code path (via load_config). This cleanup reduces test duplication and focuses TestLoadConfig on its intended purpose: integration-level configuration file loading.

### Integration Testing Strategy

**Bidirectional Relationship Sync Testing** (`tests/integration/test_bidirectional_sync.py`)

The integration test suite documents and verifies the architectural distinction between fixture behavior and MCP function behavior:

**Design Decision:**
- **Fixture Functions** (`create_epic()`, `create_task()`, `create_subtask()`): Set parent fields only (child→parent direction) without bidirectional sync. This keeps fixture setup minimal and fast.
- **MCP Functions** (`_create_ticket()`, `_update_ticket()`): Call `_update_bidirectional_relationships()` to sync both parent fields AND children arrays (bidirectional). This ensures referential integrity for production operations.

**Test Coverage:**
- **Fixture Behavior Tests**: Document that `hive_with_tickets` creates one-way parent relationships without syncing children arrays
- **MCP Behavior Tests**: Verify MCP functions populate both directions (parent↔children, up_dependencies↔down_dependencies)
- **Edge Case Tests**: Multiple children, empty children arrays, dependency bidirectional sync

**Rationale:**
This two-tier approach balances performance (minimal fixture setup) with correctness (full MCP sync). The integration tests ensure the distinction is documented and verified, preventing confusion about when bidirectional sync occurs. Addresses coverage gap noted in `test_fixtures.py:174`.

### Validation Test Strategy

**Architectural Decision: Essential Test Coverage for Simple Validation Functions**

For simple validation functions, we adopted a focused testing strategy that prioritizes essential coverage over exhaustive permutations:

**Ticket ID Validation (5-Case Pattern):**
1. **Valid format** - Representative valid inputs demonstrating expected patterns
2. **Invalid prefix format** - Uppercase, hyphens, leading numbers (combined into one test)
3. **Invalid suffix format** - Malformed bees-xxx suffixes
4. **Missing/multiple separators** - Dot separator edge cases
5. **Empty/None input** - Boundary conditions

Applied to `tests/test_id_utils.py::TestIsValidTicketIdWithHive` which was reduced from 9 granular tests to 5 essential cases while maintaining comprehensive validation coverage.

**Port Validation (2-Case Pattern):**
1. **Valid port range (1024-65535)** - Tests minimum recommended port, typical port, maximum port, and string type coercion
2. **Invalid ports** - Tests below range (0, negative), above range (65536+), and non-numeric values (string, empty, float, None)

Applied to `tests/test_config.py::TestPortValidation` which was reduced from 16 granular tests to 2 essential cases. The reduced suite covers all validation branches while eliminating redundant permutations.

**Rationale:**
- Simple validators (regex, range checks) have predictable behavior - testing every invalid permutation adds little value
- Combining related invalid cases reduces test count while maintaining coverage
- This approach reduces test maintenance overhead without sacrificing confidence
- Focus shifted to edge cases (empty, None, boundary conditions) rather than combinatorial invalid patterns

## Quick Reference

For implementation details, see the architecture documentation linked above. Key integration points:

- MCP server provides HTTP transport for ticket operations (create, update, delete, query)
- Relationship synchronization maintains bidirectional consistency automatically
- Query system enables multi-stage filtering and graph traversal
- Hive-based architecture supports multi-team repositories with isolated namespaces








