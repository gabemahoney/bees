---
id: features.bees-4mj
type: subtask
title: Add test for _update_ticket with explicit repo_root parameter
description: 'Add test_update_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _update_ticket accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _update_ticket was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _update_ticket with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to update a nonexistent ticket

  - Should validate the appropriate error is raised (ticket not found)


  Acceptance: Test passes and validates repo_root parameter works for _update_ticket.'
down_dependencies:
- features.bees-y5t
- features.bees-k4v
parent: features.bees-v4d
created_at: '2026-02-03T12:42:41.210248'
updated_at: '2026-02-03T13:02:11.450267'
status: completed
bees_version: '1.1'
---

Add test_update_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _update_ticket accepts and uses the explicit repo_root parameter when ctx=None.

Context: _update_ticket was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _update_ticket with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to update a nonexistent ticket
- Should validate the appropriate error is raised (ticket not found)

Acceptance: Test passes and validates repo_root parameter works for _update_ticket.
