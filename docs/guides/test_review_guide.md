# Test Review Guide

## Purpose

This guide provides guidance for writing integration and unit tests.
Writing Integration tests is covered in docs/testing.md

## Integration Test Guide
Integration test cases are described in plain English in a bee called b.qi9 in the `testplans` hive.
- If a new feature is introduced, there must be one or more plain English t2 level testcase that covers it.
- Do not describe the bees commands required to test it, use plain English. The LLM should figure out what bees commands to run.
- Write positive, negative and edge case tests
- If you introduce multiple tests with depedencies, mark the dependencies between the t2s in the bee.


## Unit Test Code Review Checklist

### Overview

This unit test guide prevents test bloat by codifying lessons learned from multiuple attempts at test suite reduction.
Use this checklist when reviewing test PRs to avoid recreating the problems we eliminated.

The overarching goal of any test development is to keep test suite lines of code as low as possible while keeping
testing coverage about 80%.

- Find ways to remove redundant tests
- Find ways to parameterize to reduce lines of code
- Do not gold-plate. Use the 80/20 rule. 80% code coverage means you dont have to test every scenario.

**Before approving new test code:**

- [ ] **Uses parametrize** - 3+ similar test cases should use `@pytest.mark.parametrize`
- [ ] **Uses shared fixtures** - Setup uses `hive_tier_config` or `multi_hive_config`, not manual setup
- [ ] **Uses data factories** - Creates tickets with `make_ticket()` or `write_ticket_file()` from helpers.py
- [ ] **No unused imports** - Run `ruff check tests/ --select F401` shows zero unused imports
- [ ] **No trivial constants** - Simple strings like "open", "completed" are inlined, not wrapped in constants
- [ ] **Tests behavior** - Minimal mocking (< 3 mocks per test), tests what functions produce, not how
- [ ] **No meta-tests** - Doesn't test test infrastructure (fixtures, helpers, conftest.py)
- [ ] **Concise docstrings** - Fixture docstrings are 1-2 lines; detailed docs go in tests/TESTING.md
- [ ] **Follows patterns** - New test files follow structure of existing test suite

### Red Flags (What NOT to Do)

**Test file > 500 lines without parametrize:**
- Likely has copy-paste test functions that differ only in input values
- **Fix:** Use `@pytest.mark.parametrize` to collapse similar tests

**More than 3 mocks in a single test:**
- Testing implementation details, not behavior
- Brittle tests that break on internal refactoring
- **Fix:** Test at integration level with real filesystem operations

**Copy-pasted setup boilerplate:**
```python
# ❌ Repeated in every test
def test_something():
    repo_root.mkdir(parents=True)
    git_dir = repo_root / ".git"
    git_dir.mkdir()
    bees_dir = repo_root / ".bees"
    bees_dir.mkdir()
    config = BeesConfig()
    # ... 10 more lines
```
- **Fix:** Use `hive_tier_config` or `multi_hive_config` fixture

**Imports 10+ constants but uses < 3:**
- Mass import of unused constants pollutes namespace
- **Fix:** Import only what you need

**Tests verifying internal implementation:**
```python
# ❌ Testing how it works, not what it produces
@patch('builtins.open')
def test_writes_with_utf8_encoding(mock_open):
    create_ticket(...)
    mock_open.assert_called_with(..., encoding='utf-8')
```
- **Fix:** Test that ticket file exists with correct content, not open() kwargs

**Meta-tests (tests of test infrastructure):**
```python
# ❌ If fixture breaks, real tests will fail anyway
def test_hive_env_fixture_creates_git_dir(hive_env):
    assert (hive_env / ".git").exists()
```
- **Fix:** Delete meta-tests; trust that real tests validate fixtures

**Verbose inline test data:**
```python
# ❌ Repeated 15-line YAML block in 8 tests
ticket_yaml = """---
id: b.Amx
type: bee
title: Test Bee
description: Test description
status: open
# ... 10 more fields
---"""
```
- **Fix:** Use `make_ticket()` factory with defaults

**Constants wrapping simple strings:**
```python
# ❌ In test_constants.py
STATUS_OPEN = "open"
STATUS_COMPLETED = "completed"

# ❌ In tests
from test_constants import STATUS_OPEN
assert ticket.status == STATUS_OPEN
```
- **Fix:** Inline simple domain strings: `assert ticket.status == "open"`
- **Note:** Constants are only valuable for complex formats or values used 5+ places

---

### Anti-Patterns from Epic 1-5 Elimination

**What we eliminated and why:**

#### 1. Meta-Tests (Eliminated: ~50 tests)
Tests of test infrastructure that provided no value:
- `test_hive_env_creates_directories()` - If fixture breaks, 500+ real tests fail
- `test_make_ticket_returns_ticket_object()` - Type checking doesn't need tests
- `test_write_ticket_file_writes_yaml()` - Real tests use this; they validate it

**Lesson:** If a fixture breaks, real tests will fail. Meta-tests are redundant.

#### 2. Mock-Heavy Implementation Tests (Eliminated: ~100 tests)
Tests that mocked 5-8 components to verify internal details:
```python
# Eliminated pattern:
@patch('builtins.open')
@patch('pathlib.Path.write_text')
@patch('yaml.safe_dump')
@patch('src.utils.validate_yaml')
@patch('src.utils.generate_id')
def test_create_ticket_uses_utf8_encoding(...):
    # 30 lines of mock setup
    # Assert open() was called with encoding='utf-8'
```

**Lesson:** Test behavior (ticket exists with correct content), not implementation (how open() was called).

#### 3. Docstring Bloat in conftest.py (Eliminated: 2,000 lines)
Fixtures had 20-30 line docstrings explaining every detail:
```python
# Old:
@pytest.fixture
def hive_env(tmp_path):
    """
    Creates an isolated hive environment for testing.

    This fixture creates a complete hive directory structure with:
    - A .git directory for repository validation
    - A .bees directory for configuration
    - A hive directory with .hive marker file
    - An eggs subdirectory for active tickets

    The fixture also sets up proper permissions and...
    [20 more lines]
    """
```

**Lesson:** Keep fixture docstrings to 1-2 lines. Detailed docs go in tests/TESTING.md.

#### 4. Unused Imports (Eliminated: ~200 occurrences)
Files imported 20+ constants, used 3:
```python
# Old:
from tests.test_constants import (
    HIVE_TEST, HIVE_BACKEND, HIVE_FRONTEND, HIVE_DEFAULT,
    TITLE_TEST_BEE, TITLE_TEST_TASK, TITLE_TEST_SUBTASK,
    STATUS_OPEN, STATUS_CLOSED, STATUS_IN_PROGRESS,
    # ... 15 more lines
)

# Only used: HIVE_TEST, TITLE_TEST_BEE
```

**Lesson:** Import only what you use. Dead imports obscure actual dependencies.

#### 5. Unnecessary Constants (Eliminated: 40+ constants)
Wrapped stable domain strings in constants:
```python
# Eliminated from test_constants.py:
STATUS_OPEN = "open"
STATUS_COMPLETED = "completed"
TYPE_BEE = "bee"

# Now inlined in tests:
assert ticket.status == "open"  # Not STATUS_OPEN
```

**Lesson:** Constants are for complex formats (ID patterns, YAML templates) or high reuse (5+ places). Don't wrap "open".

#### 6. Duplicated Setup Boilerplate (Eliminated: 3,000+ lines)
20-line setup blocks copy-pasted across 150+ tests:
```python
# Eliminated pattern:
def test_something(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    git_dir = repo_root / ".git"
    git_dir.mkdir()
    bees_dir = repo_root / ".bees"
    bees_dir.mkdir()
    # ... 15 more lines
```

**Lesson:** Use `hive_tier_config` or `multi_hive_config` fixtures. They provide this in 1 line.

#### 7. Missing Parametrization (Created: ~100 parametrized tests)
Separate test functions for each input variation:
```python
# Old: 8 separate test functions
def test_create_bee_with_title(): ...
def test_create_bee_with_description(): ...
def test_create_bee_with_tags(): ...
# ... 5 more identical functions

# New: 1 parametrized test
@pytest.mark.parametrize("field,value", [
    ("title", "Test Bee"),
    ("description", "Test description"),
    ("tags", ["test", "beta"]),
    # ... 5 more cases
])
def test_create_bee_with_optional_fields(field, value): ...
```

**Lesson:** If 3+ tests follow same structure with different inputs, parametrize.

---

### Best Practices (What TO Do)

#### 1. Use Parametrization Aggressively

**When:** 3+ tests follow same structure with different inputs

**How:**
```python
@pytest.mark.parametrize("status", ["open", "in_progress", "completed"])
def test_ticket_status_validation(status):
    ticket = create_ticket(status=status)
    assert ticket.status == status
```

**Use descriptive IDs for clarity:**
```python
@pytest.mark.parametrize("invalid_id", [
    pytest.param("", id="empty_string"),
    pytest.param("no-prefix", id="missing_type_prefix"),
    pytest.param("b.", id="missing_shortid"),
])
def test_invalid_ticket_id(invalid_id):
    with pytest.raises(ValueError):
        validate_ticket_id(invalid_id)
```

#### 2. Use Shared Fixtures and Factories

**For single-hive tests:**
```python
def test_create_ticket(hive_tier_config):
    repo_root, hive_path, tier_config = hive_tier_config
    # Test with pre-configured hive and tier structure
```

**For multi-hive tests:**
```python
def test_cross_hive_dependencies(multi_hive_config):
    repo_root, hive_paths, config = multi_hive_config
    # Test with multiple hives and cross-hive settings
```

**For ticket creation:**
```python
from tests.helpers import make_ticket, write_ticket_file

ticket = make_ticket(title="Test", status="open")  # Defaults handled
write_ticket_file(hive_path, ticket)  # Writes YAML correctly
```

#### 3. Test Behavior, Not Implementation

**Good (tests observable behavior):**
```python
def test_create_ticket_writes_file():
    ticket_id = create_ticket(title="Test")
    ticket_path = hive_path / f"{ticket_id}.md"
    assert ticket_path.exists()

    content = ticket_path.read_text()
    assert "title: Test" in content
```

**Bad (tests internal implementation):**
```python
@patch('builtins.open')
def test_create_ticket_uses_utf8(mock_open):
    create_ticket(title="Test")
    mock_open.assert_called_with(..., encoding='utf-8')
```

**When to mock:**
- External services (network, database)
- Expensive operations in integration tests
- Error injection for error path testing

**When NOT to mock:**
- Filesystem operations (use tmp_path)
- Ticket creation/reading (use real functions)
- Validation logic (test directly)

#### 4. Keep It DRY

**Use conftest.py for repeated setup:**
```python
# conftest.py
@pytest.fixture
def configured_hive(tmp_path):
    # Shared setup for 50+ tests
    return setup_hive(tmp_path)
```

**Use helpers.py for data factories:**
```python
# helpers.py
def make_ticket(**overrides):
    defaults = {"title": "Test", "status": "open"}
    return Ticket(**{**defaults, **overrides})
```

**If you copy-paste in tests, extract it.**

#### 5. Documentation Belongs in Docs

**conftest.py fixture docstrings: 1-2 lines**
```python
@pytest.fixture
def hive_tier_config():
    """Pre-configured hive with tier structure (4 variants)."""
    ...
```

**Detailed fixture docs: tests/TESTING.md**
- Comprehensive fixture reference with usage examples
- Decision tree for choosing fixtures
- Mock patching strategy guide

**Test architecture: docs/architecture/testing.md**
- Testing philosophy and principles
- Test organization rationale
- File placement decision tree

**PR review checklist: docs/test_review_guide.md (this file)**
- Anti-patterns to avoid
- Best practices to follow
- Red flags to watch for

---

### Quick Reference

**New test for ticket creation?** Read file docstrings first:
- Complete N-tier chain → `test_tier_hierarchy_validation.py`
- Core validation/relationships/hive behavior → `test_create_ticket.py`

**New fixture?** Check conftest.py first to avoid duplication.

**New helper?** Check helpers.py first to avoid duplication.

**File > 500 lines?** Consider parametrization or splitting by feature.

**Mocking > 3 things?** Test at integration level instead.


