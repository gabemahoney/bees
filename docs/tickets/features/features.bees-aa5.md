---
id: features.bees-aa5
type: task
title: Refactor ticket_factory.py functions
description: |
  Context: Ticket creation functions are frequently called from MCP entry points and internally. Simplifying these makes the ticket creation API cleaner.

  What Needs to Change:
  - Remove `repo_root: Path | None = None` parameter from 3 functions:
    - create_epic
    - create_task
    - create_subtask
  - Replace with `repo_root = get_repo_root()` call internally
  - Remove repo_root from any downstream calls these functions make

  Why: Simplify ticket creation API. These are core operations used throughout the system.

  Files: src/ticket_factory.py

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - No repo_root parameters in ticket_factory.py function signatures
  - Ticket creation works correctly with context
  - ID generation, validation, and file writing still work
  - Created tickets have correct paths and metadata
parent: features.bees-nho
children: ["features.bees-abh", "features.bees-abi", "features.bees-abj"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa2"]
created_at: '2026-02-04T19:00:04.000000'
updated_at: '2026-02-04T19:00:04.000000'
bees_version: '1.1'
---

Context: Ticket creation functions are frequently called from MCP entry points and internally. Simplifying these makes the ticket creation API cleaner.

What Needs to Change:
- Remove `repo_root: Path | None = None` parameter from 3 functions:
  - create_epic
  - create_task
  - create_subtask
- Replace with `repo_root = get_repo_root()` call internally
- Remove repo_root from any downstream calls these functions make

Why: Simplify ticket creation API. These are core operations used throughout the system.

Files: src/ticket_factory.py

Success Criteria:
- No repo_root parameters in ticket_factory.py function signatures
- Ticket creation works correctly with context
- ID generation, validation, and file writing still work
- Created tickets have correct paths and metadata
