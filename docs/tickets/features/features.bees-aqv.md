---
id: features.bees-aqv
type: subtask
title: Update README.md with test behavior change documentation
description: '**Context:**

  Task features.bees-o0l fixed a failing test that was out of sync with the implementation.
  The get_client_repo_root() function now returns None instead of raising ValueError
  when roots are empty (intentional behavior from commit 715e452).


  **Task:**

  Update README.md to document (if applicable):

  - Behavior of get_client_repo_root() when roots protocol returns empty list

  - Graceful degradation approach for clients without roots support

  - Note: If README doesn''t cover MCP roots protocol or internal implementation details,
  this may be a no-op


  **Acceptance:**

  - README updated if relevant sections exist

  - Documentation accurately reflects None return behavior for empty roots'
up_dependencies:
- features.bees-8u7
parent: features.bees-o0l
created_at: '2026-02-03T12:36:10.877414'
updated_at: '2026-02-03T12:37:15.243968'
status: completed
bees_version: '1.1'
---

**Context:**
Task features.bees-o0l fixed a failing test that was out of sync with the implementation. The get_client_repo_root() function now returns None instead of raising ValueError when roots are empty (intentional behavior from commit 715e452).

**Task:**
Update README.md to document (if applicable):
- Behavior of get_client_repo_root() when roots protocol returns empty list
- Graceful degradation approach for clients without roots support
- Note: If README doesn't cover MCP roots protocol or internal implementation details, this may be a no-op

**Acceptance:**
- README updated if relevant sections exist
- Documentation accurately reflects None return behavior for empty roots
