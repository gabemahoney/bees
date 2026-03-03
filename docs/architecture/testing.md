# Test Architecture

Unit tests: 
- Pytest with tiered fixtures for test isolation and hive-based architecture validation.
- Real filesystem operations over mocking.

Integration tests:
- In a Bee in the Testplans hive called b.qi9
- Use for high level end-to-end test of an actual instance of Bees, used by an LLM
- Use Plain English, do not list bees commands
- Try to write tests that can be run in isolation
- If you must write tests that depend on previous tests, ensure the ticket dependencies represent this

## Unit Testing Deep Dive

**Full fixture docs**: `tests/TESTING.md` (fixture reference, mock patching strategy, decision tree, code examples).

### Core Principles

1. **Test behavior, not implementation** - Focus on outputs, not internals
2. **Integration over isolation** - Bees is filesystem-based; real operations catch real bugs
3. **Parametrize over duplication** - 3+ similar tests → `@pytest.mark.parametrize`
4. **DRY with fixtures and factories** - No copy-paste setup
5. **No meta-tests** - Don't test fixtures/helpers; real tests validate them
6. **Coverage through cases, not count** - 10 parametrized tests > 50 same-path tests

### Standards

- **Coverage**: ≥85% overall, ≥70% per-file. Simple functions get 4-5 test cases max.
- **File size**: Max 1,600 lines per test file. Split by feature area if larger.
- **Test-to-source ratio**: Target 2.0-2.5:1 (currently ~2.3:1)
- **Prefer integration tests** over heavy mocking. Mocking hides path resolution and file I/O bugs.

**Don't bother covering**: error message exact text, internal helpers only called by tested code, framework features (dict.get(), Path.exists()).

### Fixtures Summary

#### Autouse (always active)
- `backup_global_config`: Backs up/restores `~/.bees/config.json` (session-scoped)
- `mock_global_bees_dir`: Redirects `~/.bees/` to `tmp_path/global_bees/` for isolation
- `mock_git_repo_check`: Mocks git repo validation (opt-out: `@pytest.mark.needs_real_git_check`)
- `set_repo_root_context`: Sets repo context to `Path.cwd()` (opt-out: `@pytest.mark.no_repo_context`)

#### Opt-in
- `mock_mcp_context`: Factory for mock MCP Context objects
- `isolated_bees_env`: Full environment with BeesTestHelper

### Parameterized
- `hive_tier_config`: 4 tier configs (bees-only, 2-tier, 3-tier, 4-tier)
- `multi_hive_config`: 3 multi-hive scenarios (isolated, connected, mixed)
- `ticket_hierarchy`: 5 ticket structures (single, parent-child, hierarchy, siblings, deps)

#### Choosing fixtures
| Scenario | Fixture |
|----------|---------|
| MCP tool function | `mock_mcp_context` |
| Core function | `tmp_path + monkeypatch.chdir` |
| Test across tier configs | `hive_tier_config` |
| Test multi-hive scenarios | `multi_hive_config` |
| Test with existing tickets | `ticket_hierarchy` |
| Complex integration | `isolated_bees_env` |

### Data Factories (helpers.py)

```python
from tests.helpers import make_ticket, write_ticket_file

ticket = make_ticket(title="Test", status="open")  # sensible defaults
write_ticket_file(hive_path, ticket)                # handles YAML frontmatter + file naming
```

Also available: `setup_child_tiers()`, `assert_ticket_id_format()`, `assert_relationship_bidirectional()`, `build_test_scenario()`.

### Parametrization

When 3+ tests follow the same structure, parametrize:

```python
@pytest.mark.parametrize("field,value", [
    pytest.param("title", "Test", id="with_title"),
    pytest.param("description", "Desc", id="with_description"),
    pytest.param("tags", ["test"], id="with_tags"),
])
def test_create_bee_with_optional_fields(field, value):
    ...
```

Always use descriptive `id=` strings for clear failure messages.

### Mock Patching

**Golden Rule**: Patch where functions are **used**, not where defined.
- ✅ `@patch('module_using_it.shutil.rmtree')`
- ❌ `@patch('shutil.rmtree')`

Minimize mocking: use real filesystem with `tmp_path`. If mocking > 3 things, write an integration test instead.

## Constants

Create constants for complex formats used in 5+ places. Inline simple strings like `"open"`, `"completed"`, `"bee"`. Run `ruff check tests/ --select F401` to catch unused imports.

### Test Placement

**Always read the target file's module docstring before adding tests** - docstrings are the authoritative scope source.

| Scenario | File |
|----------|------|
| Core creation logic, validation, relationships | `test_create_ticket.py` |
| N-tier creation chains (bee→t1→t2→t3) | `test_tier_hierarchy_validation.py` |
| Single ticket tier rules ("can t1 have bee parent?") | `test_create_ticket.py` |
| Multi-tier edge cases (3-tier, 4-tier systems) | `test_tier_hierarchy_validation.py` |

**Before adding a test**: search for similar scenarios in existing files. Prefer adding to existing files over creating new ones.

## Key Test Suites

| Area | Files | Notes |
|------|-------|-------|
| Hive management | `test_colonize_hive.py`, `test_mcp_rename_hive.py`, `test_hive_utils.py` | |
| Ticket lifecycle | `test_create_ticket.py`, `test_ticket_factory.py`, `test_delete_ticket.py` | |
| Path & ID | `test_paths.py`, `test_id_utils.py` | |
| Config | `test_config.py`, `test_config_registration.py` | |
| Queries | `test_query_tools.py`, `test_multi_hive_query.py`, `test_graph_executor.py` | |
| MCP server | `test_mcp_server.py` (~1600 lines), `test_mcp_server_lifecycle.py`, `test_mcp_scan_validate.py` | |
| Dynamic tiers | `test_tier_hierarchy_validation.py`, `test_dynamic_tier_validation.py`, `test_parent_requirement_logic.py` | |

**Current**: ~1,578 tests across ~64 files.

### Test Execution

```bash
poetry run pytest tests/ -v                              # all tests
poetry run pytest tests/test_create_ticket.py -v         # specific file
poetry run pytest tests/ --cov=src --cov-report=term-missing  # with coverage
```

## Integration Testing Deep Dive
Integration tests are describe in plain English in a Bee in the Testplans hive called b.qi9.
There is a t1 level ticket for each area of testing. These are executed as a group in a docker container.
Each testcase is a t2 level ticket under those t1s.
Add new t2 tickets if needed based on the changes. Modify or remove existing t2 tickets if needed, as well.
Use for high level end-to-end test of an actual instance of Bees, used by an LLM
Use Plain English, do not list bees commands
Try to write tests that can be run in isolation
If you must write tests that depend on previous tests, ensure the ticket dependencies represent this

## Checklist for New Tests

1. Can I parametrize instead of writing N separate tests?
2. Can I use a shared fixture instead of copy-paste setup?
3. Am I testing behavior or implementation?
4. Does this constant wrap a simple string? (inline it)
5. Is this a meta-test? (delete it)
6. Did I read the target file's docstring?
7. Is a similar test already written?
8. Have you added some tests to the Integration test bee?
