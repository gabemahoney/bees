# Test Architecture

Bees uses pytest with a fixture-based approach for test isolation and hive-based architecture validation. Tests emphasize real filesystem operations over mocking to validate production behavior.

## Fixture Design Patterns

### Git Repository Mock (`mock_git_repo_check`)

**Purpose**: Enable testing in temporary directories that aren't git repositories.

**Implementation** (`tests/conftest.py:10-72`):
- Auto-injected fixture (autouse=True) that mocks git repository validation
- Returns `Path.cwd()` as repo root for test environments
- Patches `mcp_repo_utils.get_repo_root_from_path()` (single patch point)
- Also patches `get_config_path()` and `ensure_bees_dir()` for test isolation
- Tests requiring real git validation can opt out using `@pytest.mark.needs_real_git_check`

**Patching Strategy**: The fixture patches both `mcp_repo_utils.get_repo_root_from_path` and `mcp_server.get_repo_root_from_path`. Both patches are required because Python's `from X import Y` syntax creates a local name binding at import time. When `mcp_server.py:32` executes:
```python
from .mcp_repo_utils import get_repo_root_from_path, get_client_repo_root, get_repo_root
```
This creates a binding in `mcp_server`'s namespace that points to the function object. Patching only `mcp_repo_utils` after import doesn't affect the already-bound name in `mcp_server`. Therefore, both module namespaces must be patched to ensure the mock is used consistently.

**Design Rationale**: Tests create temporary directories via pytest's `tmp_path` fixture, which aren't git repositories. Production code validates repository boundaries, but tests need to bypass this validation to work in isolated temp directories.

### Isolated Environment (`isolated_bees_env`)

**Purpose**: Create a complete Bees environment in an isolated temporary directory.

**Implementation** (`tests/conftest.py:75-145`):
- Changes to tmp_path via monkeypatch
- Creates `.bees/` directory
- Returns `BeesTestHelper` object with methods:
  - `create_hive()`: Register hive in test environment
  - `write_config()`: Write `.bees/config.json`
  - `create_ticket()`: Generate ticket files with proper YAML frontmatter

**Usage Pattern**:
```python
def test_example(isolated_bees_env):
    helper = isolated_bees_env
    hive_dir = helper.create_hive("backend", "Backend")
    helper.write_config()
    helper.create_ticket(hive_dir, "backend.bees-abc", "epic", "Test Epic")
```

### Hive Setup Fixture (`setup_tickets_dir`)

**Purpose**: Initialize test environment with default hive and config.

**Common Pattern** (e.g., `tests/test_create_ticket.py:17-44`):
- Creates temporary directory and changes to it via `monkeypatch.chdir()`
- Creates default hive directory
- Initializes `.bees/config.json` with `BeesConfig` and `HiveConfig`
- Returns `tmp_path` for test use

**Why `monkeypatch.chdir()`**: Config functions use `Path.cwd()` to find `.bees/config.json`, so tests must change working directory to temp path.

### MCP Context Mock (`mock_mcp_context`)

**Purpose**: Simulate MCP context for functions requiring `ctx` parameter.

**Implementation** (`tests/conftest.py:148-174`):
- Returns factory function `create_mock_context(repo_path=None)`
- Mock context includes `list_roots()` async method returning file URI
- Enables testing MCP tools without real MCP server

## Test Organization Strategy

### Unit vs Integration Tests

**Unit Tests**: Test single functions in isolation
- Mock external dependencies (filesystem I/O, config loading)
- Fast execution (milliseconds)
- Example: `tests/test_id_utils.py` tests ID generation without filesystem

**Integration Tests**: Test multiple components together
- Use real filesystem via `tmp_path`
- Validate end-to-end workflows
- Example: `tests/test_create_ticket.py` tests ticket creation, persistence, and reading

**Architecture Decision**: Prefer integration tests over heavy mocking
- Rationale: Bees is filesystem-based; mocking filesystem obscures bugs in path resolution, file locking, atomic writes
- Benefits: Tests validate actual production behavior, catch filesystem-specific issues (permissions, encoding, locking)
- Trade-off: Slightly slower tests (still under 1 second per test suite)

### Test Class Organization

Tests group related functionality into classes with descriptive names:
- `TestCreateEpic`, `TestCreateTask`, `TestCreateSubtask`: Ticket creation by type
- `TestRenameHiveSuccess`, `TestRenameHiveErrors`, `TestRenameHiveEdgeCases`: Success/error/edge case separation
- `TestFlatStorageArchitecture`: Validates flat storage requirements

**Pattern**: One test class per function or feature area, with nested classes for success/error/edge cases when complexity warrants.

## Key Test Suites

### Hive Management Tests

**`tests/test_colonize_hive.py`**: Hive creation and registration (33 tests)
- Unit tests: Mock config system to validate orchestration logic
- Integration tests: Real filesystem operations with git repo fixture
- Coverage: Successful colonization, validation errors (empty name, invalid path, duplicate name), filesystem errors, config errors

**`tests/test_mcp_rename_hive.py`**: Hive rename operations (22 tests)
- Validates 10-step rename workflow: config update, ID regeneration, file rename, frontmatter update, cross-reference patching, marker update
- Tests cross-hive references and bidirectional relationship updates
- Fixture strategy: Creates multiple hives with pre-populated tickets and cross-references

**`tests/test_hive_utils.py`**: Hive utility functions (coverage of name normalization, path validation)

### Ticket Lifecycle Tests

**`tests/test_create_ticket.py`**: Ticket creation (tests for epic/task/subtask)
- Validates factory functions, bidirectional relationships, parent/child constraints
- Tests hive-prefixed ID generation and validation

**`tests/test_delete_ticket.py`**: Ticket deletion
- Validates cascade deletion (parent deletion recursively deletes all children)
- Tests relationship cleanup (removed from parent's children, dependencies updated)

### Path Resolution and ID Validation

**`tests/test_paths.py`**: Path resolution (45 tests)
- Validates hive-prefixed ID routing to correct hive directories
- Tests error handling for unprefixed IDs (ValueError raised)
- Edge cases: None, empty string, whitespace, multiple dots

**`tests/test_id_utils.py`**: ID generation and validation
- Tests `generate_ticket_id()` with required hive_name parameter
- Validates ID pattern regex: `^([a-z_][a-z0-9_]*\.)?bees-[a-z0-9]{3}$`
- Tests normalization rules: lowercase, underscores, special character removal

### Configuration Tests

**`tests/test_config.py`**: Configuration management (53 tests)
- Config loading, saving, validation
- Hive registration and name normalization
- Atomic writes and error handling

**`tests/test_config_registration.py`**: Hive registration validation (14 tests)

### Query System Tests

**`tests/test_query_tools.py`**: Named query execution
- Query registration, validation, execution
- Hive filtering validation

**`tests/test_multi_hive_query.py`**: Multi-hive query filtering
- Validates hive_names parameter filtering at pipeline entry point

**`tests/test_graph_executor.py`**: Graph traversal
- Tests parent/children/up_dependencies/down_dependencies traversal
- Validates bidirectional relationship consistency

### Validation and Linting Tests

**`tests/test_linter.py`**: Schema validation and relationship consistency

**`tests/test_linter_hive_validation.py`**: Hive-specific linter rules
- Validates ticket IDs match hive prefix
- Validates cross-hive dependency rules

### Storage Architecture Tests

**`tests/test_generate_demo_tickets.py`**: Flat storage validation (28 tests)
- `TestFlatStorageArchitecture` class validates tickets in hive root, not subdirectories
- Tests bidirectional constraints (exists in root AND not in old subdirs)
- Validates `bees_version: 1.1` field presence

## Test Execution

**Run all tests**:
```bash
poetry run pytest tests/ -v
```

**Run specific test file**:
```bash
poetry run pytest tests/test_create_ticket.py -v
```

**Run tests with coverage**:
```bash
poetry run pytest tests/ --cov=src --cov-report=term-missing
```

**Current Status** (as of hive-based architecture migration):
- 750+ tests passing (80% pass rate)
- All tests use hive-prefixed IDs (`default.bees-abc`)
- All tests validate hive_name requirement

## Test Maintenance Principles

1. **Use real filesystem operations** - Avoid mocking filesystem unless testing error conditions
2. **Validate production behavior** - Integration tests catch real-world issues
3. **Fixture isolation** - Each test gets fresh `tmp_path`, no state leakage
4. **Descriptive test names** - Test names explain what is validated and expected outcome
5. **Hive-based architecture** - All new tests must use hive-prefixed IDs and validate hive requirements
6. **Fast feedback** - Test suites complete in under 10 seconds for rapid iteration

## Directory Structure

```
tests/
├── conftest.py                      # Shared fixtures (git mock, isolated env, MCP context)
├── test_create_ticket.py            # Ticket creation tests
├── test_delete_ticket.py            # Ticket deletion tests
├── test_paths.py                    # Path resolution tests
├── test_id_utils.py                 # ID generation and validation tests
├── test_colonize_hive.py            # Hive creation and registration tests
├── test_mcp_rename_hive.py          # Hive rename tests
├── test_config.py                   # Configuration management tests
├── test_query_tools.py              # Named query tests
├── test_multi_hive_query.py         # Multi-hive query filtering tests
├── test_linter.py                   # Schema validation tests
├── test_linter_hive_validation.py   # Hive-specific linter tests
├── test_generate_demo_tickets.py    # Flat storage architecture tests
└── integration/                     # End-to-end integration tests
```

## References

- Fixture implementations: `tests/conftest.py`
- Test organization patterns: `tests/test_create_ticket.py`, `tests/test_mcp_rename_hive.py`
- Flat storage validation: `tests/test_generate_demo_tickets.py:TestFlatStorageArchitecture`
- Hive architecture: `docs/architecture/storage.md`
- Query system: `docs/architecture/queries.md`
