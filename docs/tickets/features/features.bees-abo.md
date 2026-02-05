---
id: features.bees-abo
type: subtask
title: Refactor watcher.py to use get_repo_root()
description: |
  Context: Remove repo_root parameter from start_watcher and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - In start_watcher function:
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from any downstream calls

  Files: src/watcher.py

  Success Criteria:
  - No repo_root parameter in function signature
  - Function calls get_repo_root() internally
  - Watcher still works correctly
parent: features.bees-aa6
status: completed
created_at: '2026-02-04T19:15:23.000000'
updated_at: '2026-02-05T00:00:00.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from start_watcher and use context instead.

What to Change:
- Import get_repo_root from repo_context
- In start_watcher function:
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from any downstream calls

Files: src/watcher.py

Success Criteria:
- No repo_root parameter in function signature
- Function calls get_repo_root() internally
- Watcher still works correctly
