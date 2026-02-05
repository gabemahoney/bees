---
id: features.bees-abm
type: subtask
title: Refactor index_generator.py to use get_repo_root()
description: |
  Context: Remove repo_root parameter from is_index_stale and generate_index and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - For each function (is_index_stale, generate_index):
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from any downstream calls

  Files: src/index_generator.py

  Success Criteria:
  - No repo_root parameters in function signatures
  - Functions call get_repo_root() internally
  - Index generation still works correctly
parent: features.bees-aa6
status: completed
created_at: '2026-02-04T19:15:21.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from is_index_stale and generate_index and use context instead.

What to Change:
- Import get_repo_root from repo_context
- For each function (is_index_stale, generate_index):
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from any downstream calls

Files: src/index_generator.py

Success Criteria:
- No repo_root parameters in function signatures
- Functions call get_repo_root() internally
- Index generation still works correctly
