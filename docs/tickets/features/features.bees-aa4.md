---
id: features.bees-aa4
type: task
title: Refactor paths.py functions
description: |
  Context: Core path resolution functions used throughout codebase. These are high-traffic functions that benefit from simplified signatures.

  What Needs to Change:
  - Remove `repo_root: Path | None = None` parameter from 3 functions:
    - get_ticket_path
    - infer_ticket_type_from_id
    - list_tickets
  - Replace with `repo_root = get_repo_root()` call internally
  - Update any internal calls between these functions to remove repo_root parameter

  Why: Critical path operations used everywhere. Simplifying these improves readability across the entire codebase.

  Files: src/paths.py

  Note: See parent Epic features.bees-nho for detailed implementation patterns and code examples.

  Success Criteria:
  - No repo_root parameters in paths.py function signatures
  - Functions use get_repo_root() internally
  - Path resolution works correctly with context
  - Ticket listing and path inference work as before
parent: features.bees-nho
children: ["features.bees-abe", "features.bees-abf", "features.bees-abg"]
status: completed
priority: 0
up_dependencies: ["features.bees-aa2"]
created_at: '2026-02-04T19:00:03.000000'
updated_at: '2026-02-04T19:00:03.000000'
bees_version: '1.1'
---

Context: Core path resolution functions used throughout codebase. These are high-traffic functions that benefit from simplified signatures.

What Needs to Change:
- Remove `repo_root: Path | None = None` parameter from 3 functions:
  - get_ticket_path
  - infer_ticket_type_from_id
  - list_tickets
- Replace with `repo_root = get_repo_root()` call internally
- Update any internal calls between these functions to remove repo_root parameter

Why: Critical path operations used everywhere. Simplifying these improves readability across the entire codebase.

Files: src/paths.py

Success Criteria:
- No repo_root parameters in paths.py function signatures
- Functions use get_repo_root() internally
- Path resolution works correctly with context
- Ticket listing and path inference work as before
