---
id: features.bees-abe
type: subtask
title: Refactor paths.py functions to use get_repo_root()
description: |
  Context: Remove repo_root parameter from paths.py functions and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - For each function (get_ticket_path, infer_ticket_type_from_id, list_tickets):
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from calls to other paths functions
  - Update any internal function calls within paths.py to not pass repo_root

  Files: src/paths.py

  Success Criteria:
  - No repo_root parameters in function signatures
  - All functions call get_repo_root() internally
  - Path resolution still works correctly
  - Ticket listing still works correctly
parent: features.bees-aa4
status: completed
created_at: '2026-02-04T19:15:13.000000'
updated_at: '2026-02-04T19:15:13.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from paths.py functions and use context instead.

What to Change:
- Import get_repo_root from repo_context
- For each function (get_ticket_path, infer_ticket_type_from_id, list_tickets):
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from calls to other paths functions
- Update any internal function calls within paths.py to not pass repo_root

Files: src/paths.py

Success Criteria:
- No repo_root parameters in function signatures
- All functions call get_repo_root() internally
- Path resolution still works correctly
- Ticket listing still works correctly
