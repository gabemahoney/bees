---
id: features.bees-g3z
type: subtask
title: Add test for _delete_ticket with explicit repo_root parameter
description: 'Add test_delete_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py
  that verifies _delete_ticket accepts and uses the explicit repo_root parameter when
  ctx=None.


  Context: _delete_ticket was modified to accept repo_root parameter but lacks test
  coverage.


  Requirements:

  - Test should call _delete_ticket with repo_root=str(test_repo) and ctx=None

  - Should verify repo_root is used by attempting to delete a nonexistent ticket

  - Should validate the appropriate error is raised (ticket not found)


  Acceptance: Test passes and validates repo_root parameter works for _delete_ticket.'
parent: features.bees-v4d
created_at: '2026-02-03T12:42:45.209297'
updated_at: '2026-02-03T13:02:12.054369'
status: completed
bees_version: '1.1'
---

Add test_delete_ticket_with_explicit_repo_root() to tests/test_mcp_roots.py that verifies _delete_ticket accepts and uses the explicit repo_root parameter when ctx=None.

Context: _delete_ticket was modified to accept repo_root parameter but lacks test coverage.

Requirements:
- Test should call _delete_ticket with repo_root=str(test_repo) and ctx=None
- Should verify repo_root is used by attempting to delete a nonexistent ticket
- Should validate the appropriate error is raised (ticket not found)

Acceptance: Test passes and validates repo_root parameter works for _delete_ticket.
