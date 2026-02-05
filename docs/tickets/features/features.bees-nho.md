---
id: features.bees-nho
type: epic
title: Refactor repo_root Threading with contextvars
description: |
  Simplify repo_root parameter passing by using Python contextvars module. Currently repo_root is manually threaded through ~24 functions across 6+ files, which is error-prone (bug: _update_ticket uses repo_root before defining it) and verbose.

  Solution: Use contextvars for async-safe, request-scoped state. Only MCP entry points set the context; downstream functions read from it. All MCP entry points keep optional repo_root parameter as fallback for non-Roots clients.

  Affected files: config.py (10 functions), paths.py (3), ticket_factory.py (3), writer.py (1), id_utils.py (1), index_generator.py (2), hive_utils.py (2), watcher.py (1), mcp_hive_utils.py (1), plus ~15 MCP entry points.

  Acceptance: No functions outside MCP entry points have repo_root parameter. All entry points have optional repo_root for non-Roots clients. All tests pass. Concurrent requests work correctly. Clear error messages when neither Roots nor explicit param provides repo_root.
children: ["features.bees-aa1", "features.bees-aa2", "features.bees-pg9", "features.bees-aa3", "features.bees-pga", "features.bees-aa4", "features.bees-pgb", "features.bees-aa5", "features.bees-pgc", "features.bees-aa6", "features.bees-pgd", "features.bees-pge", "features.bees-aa7", "features.bees-pgf", "features.bees-pgg", "features.bees-pgh", "features.bees-pgi", "features.bees-pgj", "features.bees-pgk"]
status: completed
created_at: '2026-02-04T18:25:28.892523'
updated_at: '2026-02-04T18:25:28.892530'
bees_version: '1.1'
---

## Problem Statement

The repo_root parameter is manually threaded through ~24 functions across 6+ files. This is error-prone (bug found: _update_ticket uses repo_root before defining it), verbose, and makes the codebase harder to maintain.

## Solution

Use Python's contextvars module for async-safe, request-scoped state. Only MCP entry points set the context; all downstream functions read from it.

## Files Affected

| File | Functions to Modify | Current repo_root params |
|------|---------------------|---------------------------|
| config.py | 10 | get_config_path, ensure_bees_dir, load_bees_config, save_bees_config, init_bees_config_if_needed, validate_unique_hive_name, load_hive_config_dict, write_hive_config_dict, register_hive_dict |
| paths.py | 3 | get_ticket_path, infer_ticket_type_from_id, list_tickets |
| ticket_factory.py | 3 | create_epic, create_task, create_subtask |
| writer.py | 1 | write_ticket_file |
| id_utils.py | 1 | extract_existing_ids_from_all_hives |
| index_generator.py | 2 | is_index_stale, generate_index |
| hive_utils.py | 2 | get_hive_config, load_hives_config |
| watcher.py | 1 | start_watcher |
| mcp_hive_utils.py | 1 | validate_hive_path |
| MCP entry points | ~15 | Keep `repo_root: str | None = None` as explicit fallback |

## Tasks

**Task 1: Create repo_context module**
- Create src/repo_context.py with:
  - `_repo_root: contextvars.ContextVar[Path | None]`
  - `get_repo_root() -> Path` - raises if not set
  - `set_repo_root(path: Path) -> Token`
  - `reset_repo_root(token: Token) -> None`
  - Context manager `repo_root_context(path: Path)` for cleaner try/finally

**Task 2: Update MCP entry points**
- Files: mcp_ticket_ops.py, mcp_hive_ops.py, mcp_query_ops.py, mcp_index_ops.py
- Pattern for each entry point:
```python
async def _create_ticket(
    ctx: Context,
    repo_root: str | None = None,  # Explicit fallback for non-Roots clients
    ...
):
    resolved_root = await resolve_repo_root(ctx, repo_root)
    with repo_root_context(resolved_root):
        # existing logic, but remove repo_root from all downstream calls
```
- Create helper `resolve_repo_root(ctx, explicit_root)` in mcp_repo_utils.py

**Task 3: Refactor config.py**
- Remove `repo_root: Path | None = None` from all 10 functions
- Replace with `get_repo_root()` call at start of each function
- Remove all repo_root parameter passing between functions

**Task 4: Refactor paths.py**
- Remove repo_root param from get_ticket_path, infer_ticket_type_from_id, list_tickets
- Use `get_repo_root()` internally

**Task 5: Refactor ticket_factory.py**
- Remove repo_root param from create_epic, create_task, create_subtask
- Use `get_repo_root()` internally

**Task 6: Refactor remaining files**
- writer.py: write_ticket_file
- id_utils.py: extract_existing_ids_from_all_hives
- index_generator.py: is_index_stale, generate_index
- hive_utils.py: get_hive_config, load_hives_config
- watcher.py: start_watcher
- mcp_hive_utils.py: validate_hive_path

**Task 7: Fix existing bug**
- mcp_ticket_ops.py:441 - _update_ticket uses repo_root before defining it
- This will be fixed as part of Task 2, but verify it's addressed

**Task 8: Update tests**
- Tests that call these functions directly need to either:
  - Wrap calls in `with repo_root_context(test_path):`
  - Or use fixtures that set up the context

**Task 9: Update mcp_repo_utils.py**
- Simplify get_repo_root() - it now only needs to handle MCP Context → Path resolution
- Add `resolve_repo_root(ctx, explicit_root)` helper for entry points

## Acceptance Criteria

1. No function outside MCP entry points has repo_root parameter
2. All MCP entry points have optional repo_root: str | None = None for non-Roots clients
3. All tests pass
4. Concurrent requests with different repos work correctly (test with multiple async tasks)
5. Clear error message when neither Roots protocol nor explicit param provides repo_root
6. All skipped tests resolved - either fixed or removed with clear justification

## Design Notes

**Why contextvars over alternatives:**
- Thread-local: Not async-safe
- Global singleton: Can't handle concurrent requests with different roots
- Dependency injection framework: Overkill for one value
- contextvars: Built-in, async-safe, request-scoped, zero dependencies

**Error handling:**
```python
def get_repo_root() -> Path:
    root = _repo_root.get()
    if root is None:
        raise RuntimeError(
            "repo_root not set in context. This is a bug - "
            "MCP entry points must call set_repo_root() before invoking core functions."
        )
    return root
```
