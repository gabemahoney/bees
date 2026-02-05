---
id: features.bees-abh
type: subtask
title: Refactor ticket_factory.py functions to use get_repo_root()
description: |
  Context: Remove repo_root parameter from ticket creation functions and use context instead.

  What to Change:
  - Import get_repo_root from repo_context
  - For each function (create_epic, create_task, create_subtask):
    1. Remove `repo_root: Path | None = None` parameter
    2. Add at start: `repo_root = get_repo_root()`
    3. Remove repo_root from calls to downstream functions (write_ticket_file, etc.)
  - Update any internal function calls to not pass repo_root

  Files: src/ticket_factory.py

  Success Criteria:
  - No repo_root parameters in function signatures
  - All functions call get_repo_root() internally
  - Ticket creation still works correctly
  - Files written to correct locations
parent: features.bees-aa5
status: completed
created_at: '2026-02-04T19:15:16.000000'
updated_at: '2026-02-04T19:15:16.000000'
bees_version: '1.1'
---

Context: Remove repo_root parameter from ticket creation functions and use context instead.

What to Change:
- Import get_repo_root from repo_context
- For each function (create_epic, create_task, create_subtask):
  1. Remove `repo_root: Path | None = None` parameter
  2. Add at start: `repo_root = get_repo_root()`
  3. Remove repo_root from calls to downstream functions (write_ticket_file, etc.)
- Update any internal function calls to not pass repo_root

Files: src/ticket_factory.py

Success Criteria:
- No repo_root parameters in function signatures
- All functions call get_repo_root() internally
- Ticket creation still works correctly
- Files written to correct locations
