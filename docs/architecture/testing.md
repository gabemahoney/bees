# Test Architecture

Bees uses pytest with a fixture-based approach for test isolation and hive-based architecture validation. Tests emphasize real filesystem operations over mocking to validate production behavior.

## Fixture Design Patterns

Bees uses a tiered fixture system organized into three categories: autouse fixtures (automatically applied), opt-in context fixtures (explicit control), and test data builder fixtures (pre-configured scenarios).

### Autouse Fixtures (Automatic Application)

These fixtures run automatically for every test unless explicitly opted out. They provide fundamental test infrastructure.

#### 1. `backup_project_config` (Session Scope)

**Purpose**: Protect development environment from test pollution.

**Implementation** (`tests/conftest.py:190-236`):
- Session-scoped: Runs once per pytest session
- Backs up `.bees/config.json` before tests
- Restores original config after all tests complete
- Prevents tests that modify config from corrupting development hive registry

**When It Matters**: Tests calling `colonize_hive()` or modifying config, running pytest from within actual bees project directory.

**Usage**: No explicit usage needed - autouse fixture applies to all tests.

#### 2. `mock_git_repo_check` (Function Scope)

**Purpose**: Enable testing in temporary directories that aren't git repositories.

**Implementation** (`tests/conftest.py:239-353`):
- Mocks `get_repo_root_from_path()` to accept `tmp_path` directories
- Patches multiple import locations due to Python's name binding at import time
- Also patches `get_config_path()` and `ensure_bees_dir()` for test isolation
- Opt-out: `@pytest.mark.needs_real_git_check`

**Patching Strategy**: Patches both `mcp_repo_utils` and `mcp_server` namespaces because Python's `from X import Y` creates local name bindings at import time. Patching only the source module doesn't affect already-imported names.

**Design Rationale**: Tests run in `tmp_path` which aren't git repos. Production code validates repo boundaries, but tests need to bypass validation for isolation.

**Usage**: No explicit usage needed - autouse fixture. Opt-out with marker when testing actual git detection logic.

#### 3. `set_repo_root_context` (Function Scope)

**Purpose**: Automatically set `repo_root` context for all tests using contextvars.

**Implementation** (`tests/conftest.py:356-415`):
- Sets `repo_root_context` to `Path.cwd()` for all tests
- Enables `get_repo_root()` calls in production code
- Automatically cleans up context after test completes
- Opt-out: `@pytest.mark.no_repo_context`

**Interaction with `mock_git_repo_check`**: These work together - `mock_git_repo_check` mocks validation to accept non-git directories, while `set_repo_root_context` provides context for `get_repo_root()` calls.

**Usage**: No explicit usage needed - autouse fixture. Most tests combine this with `monkeypatch.chdir(tmp_path)` to set both cwd and context to `tmp_path`.

### Opt-In Context Fixtures

Use these when you need explicit control over context or MCP mocking.

#### 4. `repo_root_ctx`

**Purpose**: Explicitly manage `repo_root` context with specific path different from `Path.cwd()`.

**Implementation** (`tests/conftest.py:573-629`):
- Creates `.bees` directory in `tmp_path`
- Sets `repo_root_context` to `tmp_path` (not `Path.cwd()`)
- Yields `tmp_path` for test use
- Automatically cleans up context

**When to Use**:
- Need specific path without changing cwd
- Testing context behavior with controlled setup
- Overriding autouse `set_repo_root_context` fixture

**Usage**:
```python
@pytest.mark.no_repo_context  # Disable autouse context
def test_specific_context(repo_root_ctx):
    # Context explicitly set to tmp_path from fixture
    result = some_function()
    assert get_repo_root() == repo_root_ctx
```

#### 5. `mock_mcp_context`

**Purpose**: Factory for creating mock MCP Context objects for testing MCP tool functions.

**Implementation** (`tests/conftest.py:632-720`):
- Returns factory function: `create_mock_context(repo_path=None)`
- Mock context implements MCP Roots protocol with `list_roots()` method
- Returns mock root with `file://{repo_path}` URI
- Defaults to `tmp_path` if no path provided

**When to Use**: Testing MCP tool functions (`_create_ticket`, `_show_ticket`, etc.) that require `ctx` parameter.

**Usage**:
```python
async def test_mcp_create_ticket(mock_mcp_context, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()
    
    ctx = mock_mcp_context()  # Creates mock Context
    
    result = await _create_ticket(
        ctx=ctx,
        ticket_type="epic",
        title="Test",
        hive_name="backend"
    )
    assert result["status"] == "success"
```

#### 6. `isolated_bees_env`

**Purpose**: Complete isolated environment with `BeesTestHelper` for complex integration tests.

**Implementation** (`tests/conftest.py:418-568`):
- Changes to `tmp_path` via monkeypatch
- Creates `.bees/` directory
- Returns `BeesTestHelper` with methods:
  - `create_hive(hive_name, display_name)`: Creates hive directory, registers in memory
  - `write_config()`: Writes `.bees/config.json` with registered hives
  - `create_ticket(hive_dir, ticket_id, ticket_type, title, **fields)`: Creates ticket file

**When to Use**: Integration tests with complex setup - multiple hives, cross-hive operations, complex ticket hierarchies.

**Usage**:
```python
def test_cross_hive_query(isolated_bees_env):
    helper = isolated_bees_env
    
    backend = helper.create_hive("backend", "Backend")
    frontend = helper.create_hive("frontend", "Frontend")
    helper.write_config()
    
    helper.create_ticket(backend, "backend.bees-abc", "epic", "Epic")
    
    results = execute_query("all_epics")
    assert len(results) == 1
```

### Test Data Builder Fixtures

Pre-configured test scenarios that build on each other for common testing patterns.

#### 7. `bees_repo`

**Purpose**: Minimal foundation - temporary directory with `.bees/` subdirectory.

**Implementation** (`tests/conftest.py:723-737`):
- Creates `tmp_path` with `.bees/` directory
- Yields repo root Path object
- Foundation for `single_hive`, `multi_hive`, and other tiered fixtures

**Usage**: Use as base for custom test scenarios or use higher-level fixtures built on it.

#### 8. `single_hive`

**Purpose**: Single configured hive for simple test scenarios.

**Implementation** (`tests/conftest.py:740-783`):
- Builds on `bees_repo`
- Creates 'backend' hive with `.hive/identity.json`
- Registers hive in `.bees/config.json`
- Yields tuple: `(repo_root, hive_path)`

**Usage**:
```python
def test_ticket_creation(single_hive):
    repo_root, hive_path = single_hive
    # Create tickets in pre-configured backend hive
```

#### 9. `multi_hive`

**Purpose**: Multiple hives for cross-hive test scenarios.

**Implementation** (`tests/conftest.py:786-843`):
- Builds on `bees_repo`
- Creates 'backend' and 'frontend' hives with identity markers
- Registers both in `.bees/config.json`
- Yields tuple: `(repo_root, backend_path, frontend_path)`

**Usage**:
```python
def test_cross_hive_operation(multi_hive):
    repo_root, backend_path, frontend_path = multi_hive
    # Test operations across multiple hives
```

#### 10. `hive_with_tickets`

**Purpose**: Pre-created ticket hierarchy for relationship testing.

**Implementation** (`tests/conftest.py:846-893`):
- Builds on `single_hive`
- Creates Epic → Task → Subtask hierarchy using `create_epic()`, `create_task()`, `create_subtask()`
- Yields tuple: `(repo_root, hive_path, epic_id, task_id, subtask_id)`

**Usage**:
```python
def test_ticket_relationships(hive_with_tickets):
    repo_root, hive_path, epic_id, task_id, subtask_id = hive_with_tickets
    # Test with pre-existing hierarchy
    epic = show_ticket(epic_id)
    assert task_id in epic["children"]
```

### Fixture Relationships

Dependency hierarchy showing how fixtures build on each other:

```
tmp_path (pytest built-in)
    │
    ├─→ bees_repo
    │   ├─→ single_hive
    │   │   └─→ hive_with_tickets
    │   └─→ multi_hive
    │
    ├─→ repo_root_ctx
    ├─→ mock_mcp_context
    └─→ isolated_bees_env

Autouse fixtures (backup_project_config, mock_git_repo_check, set_repo_root_context)
work alongside any of these fixtures.
```

### Decision Tree: Choosing the Right Fixture

**Question 1: What are you testing?**

- **MCP tool function** (`_create_ticket`, `_show_ticket`, etc.)
  - Use: `mock_mcp_context`
  
- **Core function** (`create_epic`, `get_config_path`, etc.)
  - Need custom environment setup?
    - Use: `isolated_bees_env` (for complex scenarios)
  - Simple test?
    - Use: `tmp_path + monkeypatch.chdir` (autouse handles rest)
  
- **Testing ticket operations/queries?**
  - Need pre-existing tickets?
    - Use: `hive_with_tickets` (or `single_hive + manual tickets`)
  - Need multiple hives?
    - Use: `multi_hive`

**Question 2: Do you need to override autouse fixtures?**

- Need real git validation?
  - Add: `@pytest.mark.needs_real_git_check`
  
- Need to control context manually?
  - Add: `@pytest.mark.no_repo_context + repo_root_ctx`

**Question 3: What's the simplest fixture for your needs?**

Always prefer simpler fixtures:
- `tmp_path + autouse` > `repo_root_ctx`
- `single_hive` > `isolated_bees_env`
- Pre-built fixtures > manual setup

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
