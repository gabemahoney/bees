# Bees Test Suite Documentation

Complete guide to the pytest fixture architecture and testing patterns for the Bees ticket management system.

## Table of Contents

- [Fixture Overview](#fixture-overview)
- [Quick Start Guide](#quick-start-guide)
- [Mock Patching Strategy](#mock-patching-strategy)
- [Decision Tree: Choosing the Right Fixture](#decision-tree-choosing-the-right-fixture)
- [Fixture Reference](#fixture-reference)

---

## Fixture Overview

Fixtures are organized into three categories: **autouse**, **opt-in context**, and **test data builders**.

### Autouse Fixtures (Apply to All Tests)

These fixtures run automatically for every test unless explicitly opted out:

#### 1. backup_project_config (session scope)
- Backs up `.bees/config.json` before tests, restores after
- Prevents test pollution of development environment
- Session-scoped: runs once per pytest session

#### 2. mock_git_repo_check (function scope)
- Mocks git repo validation to accept tmp_path directories
- Patches `get_repo_root_from_path()` and config functions
- Opt-out: `@pytest.mark.needs_real_git_check`

#### 3. set_repo_root_context (function scope)
- Sets repo_root context to `Path.cwd()` for all tests
- Enables `get_repo_root()` calls in production code
- Opt-out: `@pytest.mark.no_repo_context`

### Opt-In Context Fixtures

Use these when you need explicit control over context or MCP mocking:

#### 4. repo_root_ctx
- Sets context to tmp_path (not `Path.cwd()`)
- Use when you need specific path without chdir
- Creates `.bees` directory automatically

#### 5. mock_mcp_context
- Factory for creating mock MCP Context objects
- Returns `create_mock_context(repo_path=None)` function
- Use for testing MCP tool functions (`_create_ticket`, etc.)

#### 6. isolated_bees_env
- Complete isolated environment with BeesTestHelper
- Changes to tmp_path, creates `.bees`, returns helper
- Helper methods: `create_hive()`, `write_config()`, `create_ticket()`
- Use for integration tests with complex setup

### Test Data Builder Fixtures

These fixtures create pre-configured test scenarios:

#### 7. bees_repo
- Minimal setup: tmp_path with `.bees` directory
- Foundation for parameterized fixtures

#### 8. hive_tier_config (PARAMETERIZED)
- Tests different tier structures: bees-only, 2-tier, 3-tier, 4-tier
- Returns `(repo_root, hive_path, tier_config_dict)`
- Automatically runs tests with all tier configurations

#### 9. multi_hive_config (PARAMETERIZED)
- Tests multi-hive scenarios with different hive configurations
- Params: isolated (2 hives), connected (2 hives), mixed (3 hives)
- Returns `(repo_root, hive_paths_list, config_dict)`
- Automatically tests multi-hive interactions (cross-hive relationships are always supported)

#### 10. ticket_hierarchy (PARAMETERIZED)
- Tests different ticket structures: single bee, bee+task, full hierarchy, siblings, dependencies
- Creates actual ticket files with proper relationships
- Returns `(repo_root, hive_path, ticket_ids_dict)`
- Automatically tests common ticket relationship scenarios

### Removed Deprecated Fixtures
The following fixtures were removed from conftest.py and migrated to parameterized alternatives:
- `single_hive` -> `hive_tier_config`
- `multi_hive` -> `multi_hive_config`
- `hive_with_tickets` -> `ticket_hierarchy`
- `temp_tickets_dir` -> local fixture in `test_create_ticket.py`

---

## Fixture Relationships

### Dependency Hierarchy

```
tmp_path (pytest built-in)
    │
    ├─→ bees_repo
    │   ├─→ hive_tier_config (PARAMETERIZED - tests 4 tier configs)
    │   ├─→ multi_hive_config (PARAMETERIZED - tests 3 multi-hive scenarios)
    │   ├─→ ticket_hierarchy (PARAMETERIZED - tests 5 ticket structures)
    │   │
    │
    ├─→ repo_root_ctx
    ├─→ mock_mcp_context
    └─→ isolated_bees_env
```

Autouse fixtures work alongside any of these fixtures.

### Using Parameterized Fixtures

Parameterized fixtures automatically run your test multiple times with different configurations. Access the current parameter via `request.param` or use the fixture's return value which contains config details.

**Example:**
```python
def test_with_tiers(hive_tier_config):
    repo_root, hive_path, tier_config = hive_tier_config
    # Test runs 4 times: bees-only, 2-tier, 3-tier, 4-tier
    # tier_config tells you which configuration is active
```

---

## Quick Start Guide

### Simple Unit Test (Uses Autouse Fixtures Only)

```python
def test_create_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()

    # Autouse fixtures provide context and mock git validation
    create_config()  # Works! Context is set to Path.cwd()
    assert (tmp_path / ".bees" / "config.json").exists()
```

### Integration Test with Isolated Environment

```python
def test_query_across_hives(isolated_bees_env):
    helper = isolated_bees_env

    backend = helper.create_hive("backend")
    frontend = helper.create_hive("frontend")
    helper.write_config()

    helper.create_ticket(backend, "b.Amx", "bee", "Epic")

    results = execute_named_query("all_epics")
    assert len(results) == 1
```

### Testing MCP Functions

```python
async def test_mcp_create_ticket(mock_mcp_context, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()

    ctx = mock_mcp_context()  # Creates mock Context

    result = await _create_ticket(
        ctx=ctx,
        ticket_type="bee",
        title="Test",
        hive_name="backend"
    )
    assert result["status"] == "success"
```

### Testing Core Functions with Explicit Context

```python
def test_with_explicit_context(repo_root_ctx):
    # Context is set to tmp_path (from fixture)
    config_path = get_config_path()
    assert config_path == repo_root_ctx / ".bees" / "config.json"
```

### Pre-Built Test Scenario (Parameterized)

```python
def test_ticket_relationships(ticket_hierarchy):
    repo_root, hive_path, tickets = ticket_hierarchy

    # Test runs 5 times with different structures
    # Access tickets via dictionary keys
    if "bee" in tickets and "task" in tickets:
        # This runs for bee_with_task and full_hierarchy params
        bee = show_ticket(tickets["bee"])
        assert tickets["task"] in bee["children"]
```

---

## Mock Patching Strategy

This test suite uses **SOURCE-LEVEL PATCHING** for all mocks to ensure reliable test isolation. Understanding this pattern is critical for writing and maintaining tests.

### Why Source-Level Patching?

Python creates name bindings at import time. When a module does:
```python
from some_module import some_function
```

It creates a LOCAL binding in its own namespace. Patching only the original module won't affect already-imported names in other modules.

### Example Problem (Import-Level Patching - INCORRECT)

```python
# production_code.py
from shutil import rmtree  # Creates local binding to shutil.rmtree

def delete_dir(path):
    rmtree(path)  # Uses the local binding

# test_code.py
@patch('shutil.rmtree')  # ❌ WRONG: Only patches shutil module
def test_delete():
    delete_dir("/tmp/test")  # Still calls real rmtree!
```

**The Problem:**
- `production_code.py` imported `rmtree` before the test ran
- The local binding in `production_code.py` still points to the real function
- `@patch('shutil.rmtree')` only affects code that imports shutil AFTER the patch

### Correct Solution (Source-Level Patching)

```python
# production_code.py
import shutil  # Import the module, not the function

def delete_dir(path):
    shutil.rmtree(path)  # Uses module.function syntax

# test_code.py
@patch('production_code.shutil.rmtree')  # ✅ CORRECT: Patches the local binding
def test_delete():
    delete_dir("/tmp/test")  # Safely mocked!
```

**The Solution:**
- Patch where the function is USED, not where it's DEFINED
- Use `'module_that_imports.module.function'` pattern
- This patches the local binding created by the import statement

### Real Example from Bees Codebase

```python
# bees/paths.py
import shutil  # Source-level import

def delete_hive(hive_path):
    if hive_path.exists():
        shutil.rmtree(hive_path)  # Uses shutil.rmtree

# tests/test_paths.py
@patch('bees.paths.shutil.rmtree')  # Patch where it's used, not shutil.rmtree
def test_delete_hive():
    delete_hive(Path("/tmp/test"))
    # Mock is called, real filesystem is safe
```

### Mock Patching Patterns in This Test Suite

**CORRECT Patterns (Use These):**
- ✅ `@patch('bees.paths.shutil.rmtree')` - Patches bees.paths module's shutil binding
- ✅ `@patch('bees.config.json.dumps')` - Patches bees.config module's json binding
- ✅ `monkeypatch.setattr('src.module.func')` - monkeypatch uses source-level by default

**INCORRECT Patterns (Never Use):**
- ❌ `@patch('shutil.rmtree')` - Only affects code that imports shutil after patch
- ❌ `@patch('json.dumps')` - Won't affect already-imported json modules
- ❌ `mock.patch('builtin.open')` - Won't affect modules that imported open

### How to Determine Correct Patch Target

1. Find where the function is USED (not where it's defined)
2. Check the import statement in that module
3. Patch using the pattern: `'using_module.imported_module.function'`

**Example:**
```python
# Step 1: Find usage
# File: src/writer.py, Line 45
shutil.copy2(src, dst)

# Step 2: Check import
# File: src/writer.py, Line 3
import shutil

# Step 3: Build patch target
@patch('src.writer.shutil.copy2')  # ✅ Correct!
```

### Module Reload Mechanism

Some tests use `importlib.reload()` to reset module state between tests. This is necessary when testing import-time side effects or module-level state.

**When to Use reload():**
- Testing module initialization code
- Resetting module-level variables
- Testing different import configurations
- Coordinating with `@pytest.mark.needs_real_git_check`

**Example:**
```python
import importlib
import src.config

def test_config_initialization():
    # Reset config module to test initialization
    importlib.reload(src.config)
    # Now test import-time behavior
```

### Relationship with needs_real_git_check Marker

The `@pytest.mark.needs_real_git_check` marker disables `mock_git_repo_check` fixture. Use this when you need to test actual git repository validation logic.

**When to Use:**
- ✅ Testing `get_repo_root_from_path()` function itself
- ✅ Testing error handling for non-git directories
- ✅ Integration tests that interact with real git repos

**When NOT to Use:**
- ❌ Regular unit tests (mocks make tests faster and more reliable)
- ❌ Tests in tmp_path (tmp_path isn't a git repo)
- ❌ Testing ticket creation/updates (doesn't need git validation)

**Example:**
```python
@pytest.mark.needs_real_git_check
def test_repo_validation():
    # This test uses REAL git validation (no mocking)
    # Will fail if not run in a git repository
    repo_root = get_repo_root_from_path(Path.cwd())
    assert (repo_root / '.git').exists()
```

### Common Pitfalls and Solutions

**Pitfall 1: "Mock not called" errors**
- Problem: Patched wrong target (used import-level instead of source-level)
- Solution: Patch where function is USED: `@patch('using_module.imported.func')`

**Pitfall 2: Real filesystem/network calls in tests**
- Problem: Forgot to mock external dependencies
- Solution: Use source-level patching for ALL external calls (shutil, requests, subprocess)

**Pitfall 3: Mock works in one test file but not another**
- Problem: Different modules import the same function differently
- Solution: Patch each usage location separately or standardize imports

**Pitfall 4: Tests pass individually but fail when run together**
- Problem: Module-level state persists between tests
- Solution: Use `importlib.reload()` or ensure proper fixture cleanup

### Summary: Golden Rules

1. ALWAYS use source-level patching: `@patch('using_module.imported.function')`
2. NEVER patch at the definition site: `@patch('original_module.function')`
3. Production code should use "import module" not "from module import function"
4. Find the import statement to determine the correct patch target
5. Use `@pytest.mark.needs_real_git_check` only for testing validation logic itself

---

## Decision Tree: Choosing the Right Fixture

### Question 1: What are you testing?

**MCP tool function (_create_ticket, _show_ticket, etc.)**
- → Use: `mock_mcp_context`

**Core function (create_bee, get_config_path, etc.)**
- Need custom environment setup?
  - → Use: `isolated_bees_env` (for complex scenarios)
- Simple test?
  - → Use: `tmp_path + monkeypatch.chdir` (autouse handles rest)

**Testing ticket operations/queries?**
- Need pre-existing tickets?
  - → Use: `ticket_hierarchy` (tests 5 structures automatically)
- Need multiple hives?
  - → Use: `multi_hive_config` (tests 3 scenarios automatically)

### Question 2: Do you need to override autouse fixtures?

**Need real git validation?**
- → Add: `@pytest.mark.needs_real_git_check`

**Need to control context manually?**
- → Add: `@pytest.mark.no_repo_context + repo_root_ctx`

### Question 3: What's the simplest fixture for your needs?

Always prefer simpler fixtures:
- `tmp_path + autouse` > `repo_root_ctx`
- Parameterized fixtures > `isolated_bees_env` (for common scenarios)
- Pre-built fixtures > manual setup

### Question 4: Should I use parameterized fixtures?

**Testing tier-related behavior (ticket types, hierarchies)?**
- → Use: `hive_tier_config` (tests all tier configs automatically)

**Testing multi-hive behavior?**
- → Use: `multi_hive_config` (tests different hive configurations)

**Testing ticket relationships/queries?**
- → Use: `ticket_hierarchy` (tests different structures automatically)

---

## Fixture Reference

### backup_project_config

**Scope:** Session
**Autouse:** Yes

Backup and restore the project's `.bees/config.json` to prevent test pollution.

**Purpose:**
Ensures the actual project's config.json is preserved during test runs. Without this, tests that modify config (e.g., colonize_hive tests) would corrupt the development environment's hive registry.

**Scope & Behavior:**
- Session-scoped: Runs once at test session start/end
- Autouse: Applies to all tests automatically (no explicit declaration needed)
- Backs up `.bees/config.json` before any tests run
- Restores original config after all tests complete

**When This Matters:**
- Tests that call `colonize_hive()` or modify `.bees/config.json`
- Running pytest from within the actual bees project directory
- Development workflow where you're actively using bees to track tasks

**Note:**
Most tests run in isolated tmp_path environments and won't affect the project config. This is a safety net for integration tests or accidental mutations to the real project state.

---

### mock_git_repo_check

**Scope:** Function
**Autouse:** Yes
**Opt-out:** `@pytest.mark.needs_real_git_check`

Mock git repository detection to allow tests in non-git temporary directories.

**Purpose:**
Production code validates repo_root by checking for `.git` directories. Tests run in temporary directories (tmp_path) that aren't git repos. This fixture mocks `get_repo_root_from_path()` to treat tmp_path as valid.

**What Gets Mocked:**
1. `get_repo_root_from_path()` - Returns path with `.git`/`.bees` or falls back to cwd
2. `get_config_path()` - Uses `Path.cwd()` when repo_root is None
3. `ensure_bees_dir()` - Uses `Path.cwd()` when repo_root is None

**Why Multiple Patches Are Needed:**
Python creates name bindings at import time. When `mcp_server.py` does:
```python
from .mcp_repo_utils import get_repo_root_from_path
```

It creates a local binding in mcp_server's namespace. Patching only mcp_repo_utils won't affect the already-imported name in mcp_server.

We must patch all 5 import locations:
- `src.mcp_repo_utils.get_repo_root_from_path`
- `src.mcp_server.get_repo_root_from_path`
- `src.mcp_ticket_ops.get_repo_root_from_path`
- `src.mcp_query_ops.get_repo_root_from_path`
- `src.main.get_repo_root_from_path`

**Interaction with set_repo_root_context:**
This fixture mocks the repo detection logic, while `set_repo_root_context` sets the contextvars for `get_repo_root()`. They work together:
- `mock_git_repo_check`: Makes validation functions accept tmp_path
- `set_repo_root_context`: Provides context for `get_repo_root()` calls

---

### set_repo_root_context

**Scope:** Function
**Autouse:** Yes
**Opt-out:** `@pytest.mark.no_repo_context`

Automatically set repo_root context for all tests using contextvars.

**Purpose:**
Many core functions call `get_repo_root()` from `src.repo_context` to access the repository root. Tests need this context set, but manually wrapping every test with `repo_root_context()` is verbose and error-prone.

This autouse fixture automatically sets the context to `Path.cwd()` for all tests, enabling seamless use of context-dependent functions.

**What It Does:**
- Sets `repo_root_context` to `Path.cwd()` (typically a tmp_path in tests)
- Wraps the entire test in a context manager
- Automatically cleans up context after test completes

**Common Pattern:**
Most tests combine this with `monkeypatch.chdir(tmp_path)`:

```python
def test_something(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # Sets cwd to tmp_path
    # set_repo_root_context uses Path.cwd(), so context = tmp_path
    result = some_function()  # Can safely call get_repo_root()
```

---

### isolated_bees_env

**Scope:** Function

Create isolated Bees environment with helper for building test scenarios.

**Purpose:**
Provides a complete, isolated Bees environment with a helper object that simplifies creating hives, config, and tickets for integration tests.

Use this for tests that need full environment setup: multiple hives, complex ticket hierarchies, or testing cross-hive operations.

**What It Provides:**
1. Changes cwd to tmp_path (isolated from project)
2. Creates `.bees/` directory
3. Returns BeesTestHelper with methods for building test data

**BeesTestHelper Methods:**

`create_hive(hive_name: str, display_name: str | None = None) -> Path`
- Creates hive directory at base_path / hive_name
- Registers hive in internal registry (call `write_config()` after)
- Returns Path to hive directory

`write_config() -> None`
- Writes `.bees/config.json` with all registered hives
- Call after creating all hives

`create_ticket(hive_dir: Path, ticket_id: str, ticket_type: str, title: str, status: str = "open", **extra_fields) -> Path`
- Creates ticket markdown file with YAML frontmatter
- Writes to hive_dir / "{ticket_id}.md"
- Returns Path to created ticket file

**Complete Usage Example:**
```python
def test_cross_hive_query(isolated_bees_env):
    helper = isolated_bees_env

    # Create hives
    backend_dir = helper.create_hive("backend", "Backend")
    frontend_dir = helper.create_hive("frontend", "Frontend")
    helper.write_config()

    # Create tickets
    helper.create_ticket(
        backend_dir,
        "b.Amx",
        "bee",
        "Backend Epic",
        status="open",
        children=[]
    )

    # Test query across hives
    results = execute_named_query("open_tickets")
    assert len(results) == 2
```

---

### repo_root_ctx

**Scope:** Function

Opt-in fixture for explicitly managing repo_root context in tests.

**Purpose:**
Provides explicit control over repo_root context when you need to:
- Override the autouse `set_repo_root_context` fixture
- Use a specific path different from `Path.cwd()`
- Test context behavior with controlled setup

**What It Provides:**
1. Creates `.bees` directory in tmp_path
2. Sets `repo_root_context` to tmp_path (not `Path.cwd()`)
3. Yields tmp_path for test use
4. Automatically cleans up context after test

**Difference from set_repo_root_context (autouse):**
- `set_repo_root_context`: Uses `Path.cwd()` as repo_root (autouse)
- `repo_root_ctx`: Uses tmp_path directly as repo_root (opt-in)

This matters when you don't call `monkeypatch.chdir(tmp_path)`.

---

### mock_mcp_context

**Scope:** Function

Factory fixture for creating mock MCP Context objects for testing MCP tool functions.

**Purpose:**
MCP tool functions (in `mcp_ticket_ops.py`, `mcp_query_ops.py`) receive a `ctx: Context` parameter from FastMCP. This fixture creates mock Context objects that implement the MCP Roots protocol for testing.

**What It Provides:**
Returns a factory function: `create_mock_context(repo_path=None)`
- `repo_path`: Optional path to use as repo root (defaults to tmp_path)
- Returns: Mock Context object with `list_roots()` method

**Mock Context Behavior:**
`ctx.list_roots()` returns a list with one mock root:
- `root.uri = "file://{repo_path}"`

This allows `resolve_repo_root(ctx)` to extract repo_path from the URI.

**Usage Example:**
```python
async def test_create_ticket_mcp(mock_mcp_context, tmp_path, monkeypatch):
    # Setup environment
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".bees").mkdir()

    # Create mock context
    ctx = mock_mcp_context()  # Uses tmp_path by default

    # Call MCP tool function
    result = await _create_ticket(
        ctx=ctx,
        ticket_type="bee",
        title="Test Epic",
        hive_name="backend"
    )

    assert result["status"] == "success"
```

---

### bees_repo

**Scope:** Function

Foundation fixture providing minimal bees repository structure.

**Purpose:**
Creates the absolute minimum structure needed for a bees repository: just a temporary directory with a `.bees/` subdirectory. This is the building block that parameterized fixtures build upon.

**What Gets Created:**
1. Temporary directory (via pytest's tmp_path)
2. `.bees/` subdirectory (no config.json yet)
3. That's it - minimal setup only

**Return Value:**
`Path`: The repository root (tmp_path with `.bees/` directory)

**When to Use:**
- ✅ Building custom test scenarios with manual hive/config setup
- ✅ Testing config initialization logic
- ✅ Base for other fixtures (internal use)

Don't use if you need hives or tickets - use parameterized fixtures instead.

---

### hive_tier_config (PARAMETERIZED)

**Scope:** Function
**Parameters:** `bees_only`, `two_tier`, `three_tier`, `four_tier`

PARAMETERIZED fixture for testing different tier configurations automatically.

**Purpose:**
Tests that need to verify behavior across different tier structures should use this fixture. Pytest will automatically run your test 4 times - once for each tier configuration.

**What Gets Created:**
1. Single hive (backend) with `.hive` identity marker
2. `.bees/config.json` with tier configuration
3. Changes cwd to repo_root (via monkeypatch)

**Parameterization Details:**

1. **bees_only**: `child_tiers = {}` (only bees allowed, no child tickets)
2. **two_tier**: `child_tiers = {t1: ["Task", "Tasks"]}`
3. **three_tier**: `child_tiers = {t1: ["Task", "Tasks"], t2: ["Subtask", "Subtasks"]}`
4. **four_tier**: `child_tiers = {t1: ["Task", "Tasks"], t2: ["Subtask", "Subtasks"], t3: ["Work Item", "Work Items"]}`

**Return Value:**
`tuple: (repo_root, hive_path, tier_config_dict)`

**Usage Example:**
```python
def test_create_child_ticket(hive_tier_config):
    repo_root, hive_path, tier_config = hive_tier_config

    # Create bee (works in all tier configs)
    bee_id = create_bee("Test Bee", hive_name="backend")

    # Conditional logic based on tier config
    if "t1" in tier_config:
        # This runs for two_tier, three_tier, four_tier (not bees_only)
        task_id = create_child_tier(ticket_type="t1", title="Test Task", parent=bee_id, hive_name="backend")
        assert ticket_exists(task_id)
```

---

### multi_hive_config (PARAMETERIZED)

**Scope:** Function
**Parameters:** `two_hives_isolated`, `two_hives_connected`, `three_hives_mixed`

PARAMETERIZED fixture for testing multi-hive scenarios automatically.

**Purpose:**
Tests that need to verify multi-hive behavior should use this fixture. Pytest will automatically run your test 3 times with different hive configurations.

**Parameterization Details:**

1. **two_hives_isolated:**
   - Hives: backend, frontend
   - child_tiers: {t1: Task, t2: Subtask}

2. **two_hives_connected:**
   - Hives: backend, frontend
   - child_tiers: {t1: Task, t2: Subtask}

3. **three_hives_mixed:**
   - Hives: backend, frontend, api
   - child_tiers: {t1: Task, t2: Subtask, t3: Work Item}

**Return Value:**
`tuple: (repo_root, hive_paths_list, config_dict)`

**Usage Example:**
```python
def test_multi_hive_queries(multi_hive_config):
    repo_root, hive_paths, config = multi_hive_config
    backend_path, frontend_path = hive_paths[0], hive_paths[1]

    # Create tickets in different hives
    bee1 = create_bee("Backend Epic", hive_name="backend")
    bee2 = create_bee("Frontend Epic", hive_name="frontend")

    # Cross-hive relationships are now always supported
    update_ticket(bee2, up_dependencies=[bee1])
```

---

### ticket_hierarchy (PARAMETERIZED)

**Scope:** Function
**Parameters:** `single_bee`, `bee_with_task`, `full_hierarchy`, `bee_with_siblings`, `tickets_with_deps`

PARAMETERIZED fixture for testing with pre-existing ticket structures.

**Purpose:**
Tests that operate on existing tickets (queries, relationship updates, validation) should use this fixture. Pytest will automatically run your test 5 times - once for each ticket structure.

**Parameterization Details:**

1. **single_bee:**
   - Creates: 1 bee ticket
   - Returns: `{"bee": "b.Xxx"}`

2. **bee_with_task:**
   - Creates: 1 bee, 1 task (task.parent = bee)
   - Returns: `{"bee": "b.Xxx", "task": "t1.Xxxx"}`

3. **full_hierarchy:**
   - Creates: 1 bee, 1 task, 1 subtask (bee→task→subtask)
   - Returns: `{"bee": "b.Xxx", "task": "t1.Xxxx", "subtask": "t2.Xxxxx"}`

4. **bee_with_siblings:**
   - Creates: 3 independent bee tickets (no relationships)
   - Returns: `{"bee1": "...", "bee2": "...", "bee3": "..."}`

5. **tickets_with_deps:**
   - Creates: 2 bees with dependency (bee2.up_dependencies = [bee1])
   - Returns: `{"blocker": "...", "blocked": "..."}`

**Return Value:**
`tuple: (repo_root, hive_path, ticket_ids_dict)`

**Usage Example:**
```python
def test_parent_query(ticket_hierarchy):
    repo_root, hive_path, tickets = ticket_hierarchy

    # Check which structure we're testing
    if "task" in tickets:
        # Runs for bee_with_task and full_hierarchy
        task_id = tickets["task"]
        bee_id = tickets["bee"]

        # Test querying parent relationship
        task = show_ticket(task_id)
        assert task["parent"] == bee_id
```

---

### Deprecated Fixtures

The following fixtures remain for backward compatibility but should not be used in new tests:

- **single_hive**: Removed. Use `hive_tier_config` instead
- **multi_hive**: Removed. Use `multi_hive_config` instead
- **hive_with_tickets**: Removed. Use `ticket_hierarchy` instead
- **temp_tickets_dir**: Removed from conftest. Local fixture in `test_create_ticket.py`
